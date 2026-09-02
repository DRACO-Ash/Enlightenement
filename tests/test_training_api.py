"""The training HTTP surface and the interface it serves.

The property this file exists for, above all others: **the answer key must not cross the wire
before the operator commits.** It is asserted on the raw response BODY rather than on a parsed
object, because the body is what a browser receives and a field added to a model would show up in
the bytes whether or not anything parsed it.

Second: the interface must stay air-gapped. The plan's posture is "no CDN, no map tiles, no
external calls at runtime", and that is checked by reading the shipped markup for an external
reference rather than by trusting the Content Security Policy alone. The policy is checked too;
two independent controls on one rule is the point.

Rewritten in V0.24.0 against the real content package. The properties are the same; what changed
is that they are now asserted against a 140-item authored library rather than twelve illustrative
placeholders, which is a materially stronger test of the same rules.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import ok_probe
from enlightenment.app import Limiters, TrainingPaths, create_app
from enlightenment.config import Config
from enlightenment.content import ContentPackage
from enlightenment.ratelimit import RateLimiter
from enlightenment.storage import TrainingStore
from enlightenment.training.drill import (
    MAX_CONTENT_STRING,
    MAX_PAYLOAD_BYTES,
    MAX_SERVED_COMPETENCIES,
    MAX_SERVED_DUE_ITEMS,
    MAX_SERVED_PARAMS,
    MAX_SERVED_PROMPT,
    MAX_SERVED_WITHHELD,
    MAX_WITHHOLD_REASON,
)
from enlightenment.training_api import MAX_SERVED_ERRORS

ROOT = Path(__file__).resolve().parents[1]
CONTENT_ROOT = ROOT / "content"
UI_ROOT = ROOT / "src" / "enlightenment" / "ui"


@pytest.fixture
def client(config: Config, store: TrainingStore, tmp_path: Path) -> TestClient:
    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=CONTENT_ROOT, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app) as instance:
        yield instance


@pytest.fixture(scope="module")
def package() -> ContentPackage:
    loaded = ContentPackage(CONTENT_ROOT)
    loaded.load()
    return loaded


# --- the answer key stays server-side ----------------------------------------------------


def test_an_unanswered_drill_carries_no_answer_key_in_its_raw_body(
    client: TestClient, package: ContentPackage
) -> None:
    """The production-format rule, on the bytes, against the real library.

    Every accept value, partial value, reject value, reason and explanation of the served item
    must be absent. A convenient combined endpoint is the easy way to defeat this.
    """
    response = client.get("/api/v1/drill/next")
    assert response.status_code == 200
    body = response.text.casefold()
    item = package.drill(response.json()["item_id"])
    assert item is not None

    for value in item.answer.accept:
        if value and value != "computed_from_params":
            assert value.casefold() not in body, value
    for partial in item.answer.partial:
        assert partial.value.casefold() not in body, partial.value
    for rejected in item.answer.reject:
        assert rejected.value.casefold() not in body, rejected.value
        if rejected.why_wrong:
            assert rejected.why_wrong.casefold() not in body
    if item.explain:
        assert item.explain.casefold() not in body
    assert '"answer"' not in body
    assert '"explain"' not in body
    assert '"derived"' not in body


def test_the_reveal_arrives_only_as_the_answer_response(
    client: TestClient, package: ContentPackage
) -> None:
    """The other half: after a submission, the explanation and the rule decomposition arrive."""
    served = client.get("/api/v1/drill/next").json()
    item = package.drill(served["item_id"])
    assert item is not None
    guess = item.answer.accept[0] if item.answer.accept else "x"
    reveal = client.post(
        "/api/v1/drill/answer",
        json={
            "drill_run_id": served["drill_run_id"],
            "response": guess,
            "confidence": 4,
            "elapsed_ms": 5000,
        },
    )
    assert reveal.status_code == 200
    body = reveal.json()
    assert "score_components" in body
    assert body["score_components"], "a score with no named rule cannot be challenged"
    for component in body["score_components"]:
        assert component["rule_id"]
        assert component["explain"]
    assert body["content_hash"] == served["content_hash"]


def test_a_drill_response_is_never_cached(client: TestClient) -> None:
    """A cached drill is a drill an operator re-reads after the reveal.

    The spacing model assumes retrieval, not recognition, so a cached payload quietly converts
    every repeat into a recognition test.
    """
    response = client.get("/api/v1/drill/next")
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/me").headers["cache-control"] == "no-store"


def test_a_malformed_answer_is_refused_at_the_boundary(client: TestClient) -> None:
    """Every field validated, and an unknown key rejected rather than ignored."""
    served = client.get("/api/v1/drill/next").json()
    base = {
        "drill_run_id": served["drill_run_id"],
        "response": "manoeuvre",
        "confidence": 3,
        "elapsed_ms": 100,
    }
    assert client.post("/api/v1/drill/answer", json={**base, "confidence": 9}).status_code == 422
    assert client.post("/api/v1/drill/answer", json={**base, "response": ""}).status_code == 422
    assert client.post("/api/v1/drill/answer", json={**base, "extra": 1}).status_code == 422
    assert client.post("/api/v1/drill/answer", json={**base, "elapsed_ms": -1}).status_code == 422
    long_answer = {**base, "response": "x" * 5000}
    assert client.post("/api/v1/drill/answer", json=long_answer).status_code == 422


def test_an_unknown_run_is_a_400_naming_the_problem_not_a_500(client: TestClient) -> None:
    """A submission against a run nobody served is the caller's error, not the server's."""
    response = client.post(
        "/api/v1/drill/answer",
        json={
            "drill_run_id": "not-a-run",
            "response": "manoeuvre",
            "confidence": 3,
            "elapsed_ms": 100,
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"] == "unscorable"


# --- rate limiting -----------------------------------------------------------------------

ANSWER_BODY = {"response": "manoeuvre", "confidence": 3, "elapsed_ms": 1000}


def _answer(client: TestClient) -> int:
    served = client.get("/api/v1/drill/next")
    if served.status_code != 200:
        return served.status_code
    return client.post(
        "/api/v1/drill/answer",
        json={**ANSWER_BODY, "drill_run_id": served.json()["drill_run_id"]},
    ).status_code


def test_answering_is_strictly_rate_limited(
    config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """The plan asks for rate limiting on the scoring endpoint by name. Answering is a write."""
    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        limiters=Limiters(drill=RateLimiter(2, 60.0)),
        training=TrainingPaths(content_root=CONTENT_ROOT, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app) as client:
        codes = [_answer(client) for _ in range(3)]
    assert codes == [200, 200, 429]


def test_an_unauthenticated_answer_flood_cannot_shut_the_gated_writes(
    config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """An open route must not be able to spend a gated route's budget.

    The scoring endpoint is unauthenticated until operator identity exists, and it used to share
    the strict limiter with the token-gated session writes: twenty unauthenticated answers left an
    authenticated session write answering 429. Behind the platform gateway many callers share one
    address, so that was one client holding the team's gated write path shut.
    """
    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        limiters=Limiters(strict=RateLimiter(2, 60.0), drill=RateLimiter(2, 60.0)),
        training=TrainingPaths(content_root=CONTENT_ROOT, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app) as client:
        flood = [_answer(client) for _ in range(4)]
        assert flood == [200, 200, 429, 429], "the drill route's own budget did not bite"
        session = client.post(
            "/api/v1/sessions",
            json={"id": "alpha-one", "title": "Alpha One", "scenario": "TBC, re-verify"},
        )
    # Asserted as "the write SUCCEEDED", not as "it was not 429": a malformed body 422s before the
    # rate guard runs, so a negative assertion here passes vacuously against a merged limiter.
    assert session.status_code == 201, (
        "an unauthenticated answer flood spent the gated writes' rate budget, so an open route"
        f" can shut a gated one; the session write answered {session.status_code}"
    )


def test_every_accepted_answer_emits_one_audit_line_carrying_no_performance_data(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The accountability control on the one deliberately ungated write.

    The safety half asserts the EXACT KEY SET rather than a denylist of forbidden names. Both
    binding gates walked through the denylist version independently: it missed the real score
    fields, a nested object hid both a score and the operator's own words, and a rename defeated
    it. `log_event` emits `event` plus exactly the fields it is given, so a set equality closes
    over every future field, nested or renamed.
    """
    served = client.get("/api/v1/drill/next").json()
    with caplog.at_level("INFO"):
        response = client.post(
            "/api/v1/drill/answer",
            json={**ANSWER_BODY, "drill_run_id": served["drill_run_id"]},
        )
    assert response.status_code == 200

    lines = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.getMessage().startswith("{")
    ]
    answered = [line for line in lines if line.get("event") == "drill.answered"]
    assert len(answered) == 1, f"expected exactly one drill.answered line, saw {len(answered)}"
    line = answered[0]
    assert set(line) == {"event", "actor", "itemId"}, (
        "the drill audit line carries a field nobody has reviewed:"
        f" {sorted(set(line) - {'event', 'actor', 'itemId'})}."
        " Every field here goes to an operational log for an unauthenticated route whose subject"
        " is a person's performance. Decide it belongs before you add it."
    )
    assert line["actor"] == "synthetic-operator"
    assert line["itemId"] == served["item_id"]
    emitted = json.dumps(line).casefold()
    assert ANSWER_BODY["response"].casefold() not in emitted, "the answer text reached the log"


# --- content and library -----------------------------------------------------------------


def test_the_manifest_states_its_own_provenance(client: TestClient) -> None:
    """The hash matters most: a run record carries it, so an old result stays interpretable."""
    body = client.get("/api/v1/content/manifest").json()
    assert body["ok"] is True
    assert len(body["content_hash"]) == 64
    assert body["counts"]["drills"] == 140
    assert body["thresholds_source"] == "thresholds.example.json"
    assert body["scored_scenarios_ready"] is False
    assert "placeholder" in body["why_not_ready"].casefold()


def test_a_procedure_is_served_in_full_and_an_unknown_one_is_a_404(
    client: TestClient, package: ContentPackage
) -> None:
    """The library is a reference. Nothing in it is withheld and nothing in it is scored."""
    known = package.procedures[0].id
    found = client.get(f"/api/v1/content/procedure/{known}")
    assert found.status_code == 200
    assert found.json()["procedure"]["id"] == known
    assert client.get("/api/v1/content/procedure/PROC-NOT-REAL").status_code == 404


def test_a_product_is_served_with_its_observed_layout(client: TestClient) -> None:
    """So the interface can say how a product reads rather than inventing a caption."""
    body = client.get("/api/v1/content/product/PRD-RESIDUAL").json()
    assert body["product"]["id"] == "PRD-RESIDUAL"
    assert body["layout"] is not None
    assert client.get("/api/v1/content/product/PRD-NOT-REAL").status_code == 404


# --- the interface -----------------------------------------------------------------------


def test_the_interface_is_served_with_a_strict_policy(client: TestClient) -> None:
    """One policy, on the document and on the script, because two policies is no policy."""
    document = client.get("/ui")
    script = client.get("/ui/app.js")
    assert document.status_code == 200
    assert script.status_code == 200
    policy = document.headers["content-security-policy"]
    assert policy == script.headers["content-security-policy"]
    for directive in (
        "default-src 'self'",
        "script-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        "frame-ancestors 'none'",
        "font-src 'self'",
    ):
        assert directive in policy, directive
    assert "'unsafe-inline'" not in policy.split("style-src")[0]


def test_the_interface_script_is_served_from_an_allowlist(client: TestClient) -> None:
    """An allowlist of exact names cannot be traversed, which is why it is not a path join."""
    assert client.get("/ui/app.js").status_code == 200
    for attempt in (
        "/ui/index.html",
        "/ui/../app.py",
        "/ui/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        "/ui/APP.JS",
        "/ui/app.js.",
        "/ui/.env",
    ):
        assert client.get(attempt).status_code == 404, attempt


def test_the_interface_makes_no_external_request(client: TestClient) -> None:
    """The air-gap posture, read from the shipped bytes rather than trusted to the policy.

    Two independent controls on one rule. The data URI for the favicon is the deliberate
    exception and is checked to BE a data URI rather than a fetch.
    """
    # The XML namespace URIs are identifiers, not fetches: `http://www.w3.org/2000/svg` is how a
    # namespaced element is created and nothing resolves it. Removed before the scan and then
    # asserted to be the ONLY http-shaped strings, so the allowance cannot hide a real one.
    namespaces = (
        "http://www.w3.org/2000/svg",
        "http://www.w3.org/1999/xhtml",
        "http://www.w3.org/1999/xlink",
    )
    for path in ("/ui", "/ui/app.js"):
        body = client.get(path).text
        stripped = body
        for namespace in namespaces:
            stripped = stripped.replace(namespace, "")
        for pattern in (
            r"https?://",
            r"//cdn\.",
            r"fonts\.googleapis",
            r"fonts\.gstatic",
            r"unpkg",
            r"jsdelivr",
            r"\bfetch\(\s*['\"]https?:",
        ):
            assert not re.search(pattern, stripped), f"{path} carries {pattern}"
        # No element may point at anything but a same-origin path or a data URI.
        for attribute, target in re.findall(r'\b(src|href)="([^"]*)"', body):
            assert target.startswith(("/", "./", "data:", "#")), f"{path}: {attribute}={target}"


def test_the_interface_never_writes_an_untrusted_value_as_markup(client: TestClient) -> None:
    """Every value from the server reaches the document as text or as a created SVG node.

    The content is authored and the server is ours, and "the data is trusted" is how every one of
    these bugs starts. The cost of the discipline is nil.
    """
    script = client.get("/ui/app.js").text
    for sink in (
        r"\.innerHTML\s*=",
        r"\.outerHTML\s*=",
        r"insertAdjacentHTML\s*\(",
        r"document\.write\s*\(",
        r"\beval\s*\(",
        r"new Function\s*\(",
        r"setTimeout\s*\(\s*['\"]",
    ):
        assert not re.search(sink, script), sink
    assert "textContent" in script
    assert "createElementNS" in script


def test_the_interface_honours_an_inverted_axis(client: TestClient) -> None:
    """A magnitude axis runs brighter upward, and a client that ignored the flag would invert
    the signature it is teaching. The flag is honoured in the renderer, not merely received."""
    script = client.get("/ui/app.js").text
    assert "inverted" in script
    assert re.search(r"inverted\s*\n?\s*\?", script) or "y.inverted" in script


def test_the_interface_sizes_plot_text_against_the_measured_scale(client: TestClient) -> None:
    """In-plot text must not scale with the plot.

    A plot in a wide column renders larger than its coordinate system and one in a narrow column
    renders smaller. The design artboards had the second case at 7.3 px and the first pass at this
    interface had the first case at 23 px, so the size is set after layout from the real ratio.
    """
    script = client.get("/ui/app.js").text
    assert "getBoundingClientRect" in script
    assert "viewBox" in script
    assert "AXIS_FONT_PX" in script


def test_the_interface_honours_reduced_motion(client: TestClient) -> None:
    """Accessibility is a code standard here, not polish."""
    document = client.get("/ui").text
    assert "prefers-reduced-motion" in document


def test_red_is_reserved_for_recency_and_never_used_for_a_verdict(client: TestClient) -> None:
    """A transfer-of-training decision, provisional until the owner settles it.

    In the operator's real toolset red means "the most recent data", consistently, in the heat
    map, the LAT/LON view and the light curves. Using it for "your call was wrong" would teach one
    colour two unrelated ways, so the verdict classes use the other channels and a glyph.
    """
    document = client.get("/ui").text
    verdict_block = document[document.index(".verdict.accept") : document.index(".verdict h3")]
    assert "--recent" not in verdict_block, "a verdict is coloured with the recency red"
    script = client.get("/ui/app.js").text
    assert "--recent" in script, "the recency ramp is gone, so the reservation means nothing"
    assert "VERDICT_GLYPH" in script, "a verdict must not rest on colour alone"


def test_the_dashboard_reports_intervals_and_never_a_bare_competency_number(
    client: TestClient,
) -> None:
    """The interval is part of the value. This is the number a supervisor would read."""
    served = client.get("/api/v1/drill/next").json()
    client.post(
        "/api/v1/drill/answer", json={**ANSWER_BODY, "drill_run_id": served["drill_run_id"]}
    )
    body = client.get("/api/v1/me").json()
    assert body["competencies"]
    for competency in body["competencies"]:
        assert "measured" in competency
        if competency["measured"]:
            assert competency["interval"] is not None
        else:
            assert competency["estimate"] is None
    assert "synthetic" in body["identity"].casefold()


def test_a_broken_content_tree_is_a_503_naming_the_files_and_never_takes_health_down(
    config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """The container is fine and the content is not, and those are different incidents.

    A container that refuses to start over a content typo cannot serve the health path that would
    tell an operator why, so the fault is carried and reported on the routes that need the content.
    """
    broken = tmp_path / "content"
    broken.mkdir()
    (broken / "drills.json").write_text("{ not json", encoding="utf-8")

    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=broken, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app) as client:
        for path in ("/", "/livez", "/ping", "/health", "/healthz", "/readyz"):
            assert client.get(path).status_code == 200, path
        drill = client.get("/api/v1/drill/next")
        assert drill.status_code == 503
        detail = drill.json()["detail"]
        assert detail["error"] == "content_unavailable"
        assert detail["content_errors"], "a 503 that names no file sends an author looking blind"
        assert client.get("/api/v1/content/manifest").json()["ok"] is False


#: The largest body an anonymous JSON route may return on a HOSTILE content tree. Tightened from
#: 64 kB at V0.26.9: the gate isolation-tested the ceiling and found it caught two of five real
#: faults, because a 32 kB competency-id body fitted under it. The measured hostile maximum across
#: the swept routes is now well under this, and honest content is smaller again.
MAX_ANONYMOUS_DIAGNOSTIC_BYTES = 16 * 1024

#: The library routes serve a WHOLE authored document by design - the flight plan makes the
#: procedure and product library an anonymous reference - so their fields are not individually
#: bounded and a per-field cap would mutilate the reference. The control there is the response size.
#: Measured through this control on the shipped library: the largest procedure document is 13,903
#: bytes and the largest product, document plus the layout served beside it, is 5,616. So this
#: clears honest content 4.7 times over and still fails the 2,497,065-byte procedure and
#: 342,884-byte product the gate produced by stretching string leaves.
MAX_ANONYMOUS_LIBRARY_BYTES = 64 * 1024

#: How many draws the stateful sweep makes, and how many distinct items it must reach. A permissive
#: limiter is injected for it, because `DRILL_LIMIT` is 20 and a traversal bounded by an unrelated
#: rate limit stalls on one item while the guard reads as satisfied: with that constant lowered to
#: 5, the previous version passed while measuring 6 items of 140.
DRAWS = 24
DRAWS_EXPECTED = 20

#: Every anonymous route this sweep covers, and for the ones it does not, WHY. Asserted as an exact
#: set: narrowing the discovery filter to a single route previously left the test green, so the
#: control's one load-bearing property - that it enumerates - was held by nothing.
#:
#: The session routes are excluded for two independent reasons, either sufficient. They are
#: TOKEN-GATED - the write routes answer 401 without an `Authorization` header - so they are not
#: anonymous surfaces at all; and their size is governed by `storage.MAX_SESSIONS` and the session
#: field caps rather than by content, which their own tests hold. Sweeping the collection here
#: measured an EMPTY fixture store at 33 bytes, certifying nothing, and would have failed falsely
#: the moment anyone populated the fixture: twenty legitimate sessions measure 49,394 bytes against
#: a store that admits five hundred.
#:
#: `PATCH /api/v1/sessions/{session_id}` is in this set because the exact-set assertion below
#: refused to pass without it. That is the assertion working: an earlier version could be narrowed
#: to a single route and stayed green.
ANONYMOUS_ROUTES_SWEPT = {
    "GET /api/v1/content/manifest": MAX_ANONYMOUS_DIAGNOSTIC_BYTES,
    "GET /api/v1/diagnostics": MAX_ANONYMOUS_DIAGNOSTIC_BYTES,
    "GET /api/v1/me": MAX_ANONYMOUS_DIAGNOSTIC_BYTES,
    "GET /api/v1/content/procedure/{procedure_id}": MAX_ANONYMOUS_LIBRARY_BYTES,
    "GET /api/v1/content/product/{product_id}": MAX_ANONYMOUS_LIBRARY_BYTES,
    "GET /api/v1/drill/next": MAX_ANONYMOUS_DIAGNOSTIC_BYTES,
    "POST /api/v1/drill/answer": MAX_ANONYMOUS_DIAGNOSTIC_BYTES,
}
#: Excluded, each with a reason, because widening the discovery to the whole route table brings in
#: every route the app declares and a silent filter is what let three surfaces through.
#:
#: ● The five health paths and `/` answer a fixed dict with no content-derived string in it, and
#:   the App Store contract requires them 200 and unauthenticated. `test_appstore_contract` holds
#:   their status and shape; a size ceiling here could only fail falsely.
#: ● The `/ui` routes serve the interface from an allowlisted filename set - source files, not the
#:   content tree - so their size is a property of the repository, not of authored data.
#: ● The session routes are token-gated, and their size is governed by `storage.MAX_SESSIONS` and
#:   the session field caps rather than by content. Either reason alone is sufficient.
ANONYMOUS_ROUTES_EXCLUDED = {
    "GET /",
    "GET /health",
    "GET /healthz",
    "GET /livez",
    "GET /ping",
    "GET /readyz",
    "GET /ui",
    "GET /ui/",
    "GET /ui/{filename}",
    "GET /api/v1/sessions",
    "POST /api/v1/sessions",
    "PATCH /api/v1/sessions/{session_id}",
}


def _hostile_content(destination: Path, *, withhold_all: bool = False) -> Path:
    """The shipped library with every string an anonymous route serves stretched.

    Poisoning two fields and claiming six surfaces closed is how the previous three versions of
    this control passed: a hostile tree certifies the fields it happens to poison. So this
    stretches the drill id, prompt and explanation, the competency id and name, and the string
    leaves of a procedure and a product, and adds more competencies than the served cap admits so
    that cap can bite at all - the shipped library has eight against a cap of thirty-two.
    """
    shutil.copytree(CONTENT_ROOT, destination)
    long_text = "X" * 20000
    long_id = "9" * 3000

    document = json.loads((destination / "drills.json").read_text(encoding="utf-8"))
    rows = document["drills"] if isinstance(document, dict) else document
    for index, row in enumerate(rows):
        row["id"] = f"DRL-{index}-{long_id}"
        #: `cue_id` too. The assertion for it existed and asserted nothing, because real cue ids are
        #: seven characters and this tree never stretched the field: deleting its bound left the
        #: whole suite green, and the changelog claimed the mutation was killed. A hostile tree that
        #: skips a field certifies that field.
        row["cue_id"] = f"CUE-{index}-{long_id}"
        row["prompt"] = long_text
        row["explain"] = long_text
        #: WITHHELD BY CONSTRUCTION, and only when asked. `computed_from_params` with no generator
        #: to resolve it puts every item into `_unresolvable` at load, so the manifest's withheld
        #: collections are as long as the library - the ninth surface, where both were per-entry
        #: bounded and uncapped in count and 140 drills served 17,014 bytes against a 16 kB ceiling.
        #:
        #: OFF by default, because it is incompatible with driving the item space: an unscorable
        #: item records no run and advances no schedule, so `select` returns the same item for ever.
        #: That is the absorbing state this project closed at V0.26, reproduced here by a test
        #: fixture - the traversal drew one item of 140 and the guard caught it.
        if withhold_all:
            row.setdefault("answer", {})["accept"] = ["computed_from_params"]
    (destination / "drills.json").write_text(json.dumps(document), encoding="utf-8")

    competencies = json.loads((destination / "competencies.json").read_text(encoding="utf-8"))
    entries = competencies["competencies"] if isinstance(competencies, dict) else competencies
    template = dict(entries[0])
    for index, entry in enumerate(entries):
        entry["id"] = f"CMP-{index}-{long_id}"
        entry["name"] = long_text
    while len(entries) <= MAX_SERVED_COMPETENCIES:
        clone = dict(template)
        clone["id"] = f"CMP-EXTRA-{len(entries)}"
        clone["name"] = long_text
        entries.append(clone)
    (destination / "competencies.json").write_text(json.dumps(competencies), encoding="utf-8")

    #: The library documents, stretched at every string leaf rather than at a field this test
    #: happens to name. `/api/v1/content/procedure/{id}` serves `model_dump()` whole, so any leaf
    #: is a surface: the gate reached 2,497,065 bytes through one of them.
    #: The library files, taken from the LOADER's own manifest rather than guessed. An earlier
    #: version listed "procedures.json", which does not exist - procedures live under
    #: `procedures/procedures-core.json` - and the loop skipped it silently with `continue`, so
    #: the procedure route was swept against unstretched content and its mutation survived. A
    #: hostile tree that silently skips a file certifies the fields it happened to poison, which
    #: is the fault this whole control exists to end.
    from enlightenment.content.loader import REQUIRED_FILES

    #: Only the two the reference routes actually serve. Stretching every required file would
    #: break the drill loop that the same tree has to keep serving.
    for filename in (
        name for name in REQUIRED_FILES if "procedures/" in name or name == "products.json"
    ):
        path = destination / filename
        assert path.exists(), f"{filename} is in the loader manifest and absent from the tree"
        payload = json.loads(path.read_text(encoding="utf-8"))

        def stretch(node: Any, depth: int = 0) -> Any:
            if isinstance(node, dict):
                return {
                    key: (
                        node[key] if key in {"id", "product_id"} else stretch(node[key], depth + 1)
                    )
                    for key in node
                }
            if isinstance(node, list):
                return [stretch(item, depth + 1) for item in node]
            if isinstance(node, str) and len(node) > 3:
                return long_text
            return node

        path.write_text(json.dumps(stretch(payload)), encoding="utf-8")
    return destination


def test_no_anonymous_route_serves_a_content_sized_body_on_a_hostile_tree(
    token_config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """Enumerates ROUTES, not fields, and asserts that it enumerated.

    Five consecutive releases recorded this class as closed while a surface was live. Each fix was
    correct and each sweep incomplete, because a per-field assertion can only hold the fields
    somebody thought of. The three faults in the FIRST version of this control were the same shape
    one level up: it filtered on `"GET" in methods`, so the anonymous `POST /api/v1/drill/answer`
    served 201,084 bytes unseen; it filtered on `"{" not in path`, so two anonymous library routes
    served 2,497,065 and 514,545 bytes unseen; and `assert paths` could not tell that the discovery
    had been narrowed to one route, which a mutation proved by leaving it green.

    So: the route table comes from the app, the discovered set is compared against an EXACT
    expected set, every route is called with resolved parameters and a valid body, and each carries
    a named ceiling. `token_config` is used rather than `config`, because the claim being made is
    that these routes answer with no `Authorization` header even when a team token is set, and the
    plain fixture leaves the token empty.
    """
    root = _hostile_content(tmp_path / "content", withhold_all=True)
    app = create_app(
        config=token_config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=root, progress_path=tmp_path / "progress.json"),
    )

    #: The WHOLE route table, with the automatic verbs subtracted rather than a hand-written list
    #: of the ones this test thought of. Scoping to `startswith("/api/")` and an explicit method
    #: set made a DELETE route, or a JSON route under another prefix, invisible to the sweep AND to
    #: the exact-set assertion that exists to notice narrowing. Nothing is live today - no mounts,
    #: no `include_router`, no WebSocket, no `StaticFiles` - but "nothing is live today" is the
    #: sentence that preceded every surface in this class.
    discovered = {
        f"{method} {route.path}"
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }
    known = ANONYMOUS_ROUTES_SWEPT.keys() | ANONYMOUS_ROUTES_EXCLUDED
    assert discovered == known, (
        "the API route table changed and this sweep was not updated; add the route to"
        f" ANONYMOUS_ROUTES_SWEPT with a ceiling, or to ANONYMOUS_ROUTES_EXCLUDED with a reason."
        f" Unexpected: {sorted(discovered - known)}; missing: {sorted(known - discovered)}"
    )

    with TestClient(app) as client:
        procedure = client.get("/api/v1/content/manifest").json()
        assert procedure["ok"], (
            "the hostile tree does not load, so nothing below is measured:"
            f" {procedure['errors'][:2]}"
        )
        oversized: dict[str, int] = {}
        measured: dict[str, int] = {}
        for spec, ceiling in sorted(ANONYMOUS_ROUTES_SWEPT.items()):
            method, template = spec.split(" ", 1)
            path = _resolved(template, client)
            if path is None:
                continue
            response = (
                client.get(path)
                if method == "GET"
                else client.post(path, json=_answer_body(client))
            )
            #: The STATUS is asserted too. A sweep that measures a 422 or a 404 measures an error
            #: body and proves nothing about the surface it was pointed at - the first version of
            #: this loop scored a 27-byte 422 on the answer route as a pass.
            #:
            #: 503 is allowed and is the DELIBERATE fail-closed branch: a library document over
            #: budget is refused rather than truncated, because a silently shortened reference is
            #: worse than an absent one. It must say so, or it is just another error body.
            assert response.status_code in {200, 503}, (
                f"{spec} answered {response.status_code}, so its size proves nothing:"
                f" {response.content[:200]!r}"
            )
            if response.status_code == 503:
                assert "document_too_large" in response.text, (
                    f"{spec} refused for a reason this sweep does not recognise:"
                    f" {response.content[:200]!r}"
                )
            measured[spec] = len(response.content)
            if len(response.content) > ceiling:
                oversized[spec] = len(response.content)
        #: NON-VACUITY. Every swept route must have been reached and returned something, or a
        #: ceiling assertion over an empty measurement is a pass that means nothing - which is
        #: exactly what sweeping an empty session store produced.
        assert set(measured) == set(ANONYMOUS_ROUTES_SWEPT), (
            "a swept route was never reached:"
            f" {sorted(set(ANONYMOUS_ROUTES_SWEPT) - set(measured))}"
        )
        thin = {spec: size for spec, size in measured.items() if size <= 32}
        assert not thin, f"a swept route returned nothing measurable: {thin}; all: {measured}"

        #: The COUNT caps on `/api/v1/me`. These existed at V0.26.8 and the V0.26.9 rebuild of this
        #: test DELETED them, so both caps went back to surviving inversion - a control lost to a
        #: refactor of the test that held it, which is worse than one never written, because the
        #: register went on citing it. A body ceiling cannot substitute: with ids bounded to 64,
        #: 140 uncapped due items measure about 9 kB, well under it.
        #: The WITHHELD collections, count-capped. The body ceiling cannot see these: with ids
        #: bounded to 64 and load-time reasons at 32 characters, 140 uncapped entries are about
        #: 13 kB, under the ceiling - so both survived inversion until this assertion existed. That
        #: is this file's own lesson, that a body ceiling and a count cap are different controls,
        #: applied to the two fields on the manifest that were the odd ones out.
        manifest = client.get("/api/v1/content/manifest").json()
        total = manifest["items_without_a_resolvable_answer_total"]
        assert total > MAX_SERVED_WITHHELD, (
            f"only {total} items are withheld on this tree, so the cap has nothing to cut and"
            " these assertions prove nothing"
        )
        assert len(manifest["items_without_a_resolvable_answer"]) <= MAX_SERVED_WITHHELD
        assert len(manifest["withheld_reasons"]) <= MAX_SERVED_WITHHELD
        #: And the TOTAL is served, so the truncated list cannot read as the whole gap.
        assert (
            total
            == len(
                {
                    **manifest["withheld_reasons"],
                    **dict.fromkeys(manifest["items_without_a_resolvable_answer"]),
                }
            )
            or total > MAX_SERVED_WITHHELD
        )

        me = client.get("/api/v1/me").json()
        assert me["due_items"], "no item is due, so the due-item caps assert nothing"
        assert len(me["due_items"]) <= MAX_SERVED_DUE_ITEMS, len(me["due_items"])
        assert len(me["competencies"]) == MAX_SERVED_COMPETENCIES, len(me["competencies"])
        for item_id in me["due_items"]:
            assert len(item_id) <= MAX_CONTENT_STRING, f"{len(item_id)} characters as a due id"
        for row in me["competencies"]:
            assert len(row["name"]) <= MAX_CONTENT_STRING, len(row["name"])
            assert len(row["competency_id"]) <= MAX_CONTENT_STRING, len(row["competency_id"])
        #: And the honest tree still SERVES those documents, so the fail-closed branch above has
        #: not been bought by refusing everything. Asserted on the real library, not the
        #: hostile one.
        honest = create_app(
            config=token_config,
            store=store,
            probe=ok_probe,
            training=TrainingPaths(
                content_root=CONTENT_ROOT, progress_path=tmp_path / "honest.json"
            ),
        )
        with TestClient(honest) as plain:
            for path in ("/api/v1/content/procedure/PROC-MNV", "/api/v1/content/product/PRD-TRIC"):
                served = plain.get(path)
                assert served.status_code == 200, (
                    f"{path} refuses the SHIPPED library, so the document budget is too tight:"
                    f" {served.content[:200]!r}"
                )
        assert not oversized, (
            f"content set the size of an anonymous response: {oversized}; all measured: {measured}"
        )


def _resolved(template: str, client: TestClient) -> str | None:
    """A concrete path for a route template, with ids taken from the served library."""
    if "{procedure_id}" in template:
        library = client.get("/api/v1/content/manifest").json()
        procedures = library.get("counts", {}).get("procedures", 0)
        return template.replace("{procedure_id}", "PROC-MNV") if procedures else None
    if "{product_id}" in template:
        return template.replace("{product_id}", "PRD-TRIC")
    return template


def _answer_body(client: TestClient) -> dict[str, Any]:
    """A valid answer body for the drill served to this client, so the POST reaches the reveal."""
    drill = client.get("/api/v1/drill/next").json()
    return {
        "drill_run_id": drill["drill_run_id"],
        "response": "manoeuvre",
        "confidence": 3,
        #: Required by `DrillAnswer`, validated and then deliberately not forwarded. Omitting it
        #: gave a 422 of 27 bytes, which the non-vacuity guard caught - a sweep that measures an
        #: error body certifies nothing, which is the fault it exists to prevent.
        "elapsed_ms": 1000,
    }


def test_a_stateful_route_is_measured_across_the_item_space_not_on_one_draw(
    token_config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """The eighth surface, and it is a class rather than a field.

    `/api/v1/drill/next` is idempotent until answered, so the route sweep beside this one measured
    whichever item happened to be drawn first - one of 140. Driven serve-then-answer across the
    item space on the same hostile tree, eight of the first twenty-one items exceeded the 16 kB
    ceiling, to 145,130 bytes. A sweep that enumerates routes but not the STATE a stateful route
    serves from certifies the draw it happened to get, which is this whole fault one order up.

    It also SPLITS the two budgets, which are different controls with different numbers. The
    rendered stimuli answer to `MAX_PAYLOAD_BYTES`, a four-megabyte picture budget; everything else
    on that payload is diagnostic text and answers to the 16 kB ceiling. Asserting one number over
    both is how this route was excluded on a false rationale at V0.26.8 and then included under a
    false ceiling at V0.26.9.
    """
    root = _hostile_content(tmp_path / "content")
    app = create_app(
        config=token_config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=root, progress_path=tmp_path / "progress.json"),
        #: Permissive on purpose. This test measures response SIZE across the item space; the
        #: drill limiter is a different control with its own tests, and leaving it at 20 against 24
        #: draws let it stall the traversal silently.
        limiters=Limiters(drill=RateLimiter(DRAWS * 4, 60.0)),
    )
    with TestClient(app) as client:
        widest_stimulus = 0
        drawn: set[str] = set()
        for _ in range(DRAWS):
            served = client.get("/api/v1/drill/next")
            assert served.status_code == 200, served.content[:200]
            body = served.json()
            drawn.add(body["item_id"])

            #: Measured DIRECTLY, not by subtracting a re-serialisation. `json.dumps` defaults to
            #: `(', ', ': ')` and `ensure_ascii=True` while `JSONResponse` renders `(",", ":")` and
            #: `ensure_ascii=False`, so the subtracted figure was larger than the bytes actually in
            #: the response - understated by up to 7,643 bytes and NEGATIVE on six of twenty-four
            #: draws, where the assertion held nothing at all and would have printed a negative
            #: byte count as its diagnosis.
            def _bytes(value: Any) -> int:
                return len(
                    json.dumps(
                        value, separators=(",", ":"), ensure_ascii=False, default=str
                    ).encode("utf-8")
                )

            stimulus_bytes = _bytes(body["stimulus"])
            envelope = _bytes({k: v for k, v in body.items() if k != "stimulus"})
            widest_stimulus = max(widest_stimulus, stimulus_bytes)
            assert envelope <= MAX_ANONYMOUS_DIAGNOSTIC_BYTES, (
                f"{body['item_id']}: {envelope} bytes of diagnostic envelope around a"
                f" {stimulus_bytes}-byte stimulus, against {MAX_ANONYMOUS_DIAGNOSTIC_BYTES}"
            )
            assert stimulus_bytes <= MAX_PAYLOAD_BYTES, (
                f"{body['item_id']}: {stimulus_bytes}-byte stimulus against {MAX_PAYLOAD_BYTES}"
            )
            #: The bounded identifiers on the same payload. Reverting either to raw left the whole
            #: suite green: at 3,003-character ids the body reached about 6.5 kB, under the
            #: ceiling. The changelog said these were bounded; the code was right and no test
            #: agreed with it.
            assert len(body["item_id"]) <= MAX_CONTENT_STRING, len(body["item_id"])
            assert len(body["cue_id"] or "") <= MAX_CONTENT_STRING, len(body["cue_id"] or "")
            assert len(body["prompt"]) <= MAX_SERVED_PROMPT, len(body["prompt"])
            #: The ANSWER must succeed, or the traversal stalls on one item and the guard below
            #: passes on a handful of draws. `DRILL_LIMIT` is 20 against this loop's 24, so four
            #: draws already re-measured the same item at HEAD, and lowering that unrelated
            #: constant to 5 left this test green while it measured 6 items of 140.
            answered = client.post(
                "/api/v1/drill/answer",
                json={
                    "drill_run_id": body["drill_run_id"],
                    "response": "manoeuvre",
                    "confidence": 3,
                    "elapsed_ms": 1000,
                },
            )
            assert answered.status_code == 200, (
                f"the answer for {body['item_id']} returned {answered.status_code}, so the"
                f" traversal cannot advance: {answered.content[:160]!r}"
            )
        #: NON-VACUITY, both halves. The loop must have moved through the item space, or it is the
        #: single-draw measurement again wearing a `for` statement; and the tree must produce a
        #: stimulus over the diagnostic ceiling, or the split between the two budgets is never
        #: exercised and this test would pass with them collapsed into one.
        #: A floor set from what the traversal actually achieves, not a token "more than a few".
        #: `> 4` was satisfied by 5 of 140 while the test's name claimed the item space.
        assert len(drawn) >= DRAWS_EXPECTED, (
            f"the loop drew {len(drawn)} distinct items, under the {DRAWS_EXPECTED} this"
            f" traversal reaches: {sorted(drawn)}"
        )
        assert widest_stimulus > MAX_ANONYMOUS_DIAGNOSTIC_BYTES, (
            f"the widest stimulus was {widest_stimulus} bytes, so the split between the two"
            " budgets was never exercised and this tree is not hostile enough to prove it"
        )


def test_an_anonymous_content_503_is_bounded_per_error_and_not_only_in_count(
    config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """Twenty entries of unbounded length is not a bound.

    A content error quotes the value that failed validation and `content/models.py` sets no maximum
    on any of them, so the entry cap alone left the body content-sized. Measured by the security
    gate on a hostile tree: twenty errors, the longest 4,253 characters, an 85,151-byte response on
    a route that needs no token. The same fault the withhold reason carried on the manifest one
    route along, and it predated that fix rather than arriving with it.

    Bounded per error now. The count cap stays: both are needed, and either alone is not a bound.
    """
    #: The real tree with one field poisoned, not a stub. An earlier version of this test wrote a
    #: drills.json into an otherwise empty directory: loading stopped at "missing: cues.json", the
    #: errors were 44 characters and the mutation survived. The validation error has to be the one
    #: that QUOTES content, and `_canonical` quotes the rejected generator name.
    broken = tmp_path / "content"
    shutil.copytree(CONTENT_ROOT, broken)
    document = json.loads((broken / "drills.json").read_text(encoding="utf-8"))
    rows = document["drills"] if isinstance(document, dict) else document
    #: MORE rows than the cap, so the COUNT cap is load-bearing in this test too. An earlier
    #: version poisoned exactly twenty, so deleting the cap changed nothing and the docstring's
    #: claim that "both are needed" was held by neither assertion.
    poisoned = MAX_SERVED_ERRORS * 2
    assert poisoned < len(rows), "the library shrank below twice the served-error cap"
    for row in rows[:poisoned]:
        row.setdefault("stimulus", {})["generator"] = "bogus_" + "Q" * 4000
    (broken / "drills.json").write_text(json.dumps(document), encoding="utf-8")

    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=broken, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/drill/next")
        assert response.status_code == 503
        errors = response.json()["detail"]["content_errors"]
        assert errors, "the hostile tree raised no error, so this asserts nothing"
        assert len(errors) == MAX_SERVED_ERRORS, (
            f"{len(errors)} errors served against a cap of {MAX_SERVED_ERRORS}, from"
            f" {poisoned} poisoned rows"
        )
        for error in errors:
            assert len(error) <= MAX_WITHHOLD_REASON, f"{len(error)} characters served anonymously"
        #: And the whole body stays small. The per-error bound and the count cap together, which is
        #: the claim: 20 x 256 plus the fixed message, not 85 kB.
        assert len(response.content) < 16 * 1024, (
            f"{len(response.content)} bytes served anonymously"
        )

        #: THE SAME ERRORS ON THE OTHER ANONYMOUS ROUTE. The manifest serves `result.errors` from
        #: the same load, and bounding the 503 alone left this one at 86,317 bytes - LARGER than
        #: the response this release cites as the defect it closed, in the same file, 110 lines
        #: from the fix. "A bound applied at one of two exits is a bound at neither" is this
        #: codebase's own sentence, and there were four exits rather than three.
        manifest = client.get("/api/v1/content/manifest")
        assert manifest.status_code == 200
        assert len(manifest.json()["errors"]) == MAX_SERVED_ERRORS, manifest.json()["errors"]
        for error in manifest.json()["errors"]:
            assert len(error) <= MAX_WITHHOLD_REASON, (
                f"{len(error)} characters served on the manifest"
            )
        assert len(manifest.content) < 32 * 1024, (
            f"{len(manifest.content)} bytes served anonymously on the manifest"
        )


def test_an_authored_param_name_is_bounded_on_the_anonymous_manifest(
    config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """`stimulus_params_unread.params` keys are raw content strings on a route needing no token.

    The entry count was capped at 25 and the NAMES were not: measured, a 500-character authored key
    was served verbatim. Twenty-five entries of unbounded length is not a bound, which is the same
    fault the withhold reason and the content errors each carried on their own surface.

    An unread parameter is by definition one no renderer honours, so any string becomes a key here
    simply by being authored - the least guarded of the three, and the last one found.
    """
    root = tmp_path / "content"
    shutil.copytree(CONTENT_ROOT, root)
    document = json.loads((root / "drills.json").read_text(encoding="utf-8"))
    rows = document["drills"] if isinstance(document, dict) else document
    long_key = "beta_" + "K" * 500
    #: MORE distinct names than the census serves, so the count cap is load-bearing here too.
    for row in rows:
        params = row.setdefault("stimulus", {}).setdefault("params", {})
        params[long_key] = 1
        for extra in range(MAX_SERVED_PARAMS + 5):
            params[f"beta_unread_{extra}"] = 1
    (root / "drills.json").write_text(json.dumps(document), encoding="utf-8")

    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=root, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app) as client:
        served = client.get("/api/v1/content/manifest").json()
        params = served["stimulus_params_unread"]["params"]
        assert params, "no unread parameter was reported, so this asserts nothing"
        #: The COUNT cap as well as the length cap, held here because deleting it left the whole
        #: suite green: the census caps the served names at twenty-five and the hostile tree
        #: authors thirty distinct ones, so the cap has something to cut.
        assert len(params) <= MAX_SERVED_PARAMS, f"{len(params)} names served"
        for name in params:
            assert len(name) <= MAX_CONTENT_STRING, f"{len(name)} characters served as a key"


def test_the_plot_refits_its_text_after_layout_rather_than_reserving_a_fixed_gutter(
    client: TestClient,
) -> None:
    """The guarantee against clipped axis labels is a MEASUREMENT, not arithmetic.

    Text is sized in viewBox units so it renders at a constant CSS size, which means the size in
    viewBox units GROWS as the plot narrows - while the gutter reserved at build time did not.
    Below roughly 680 CSS px the timestamp labels sheared off the left edge: measured in a browser
    at 620, 480 and 390 px viewports, leftmost label x of -14, -55 and -100 viewBox units. The
    build-time reserve is a first guess; `sizePlotText` measures the real overflow with `getBBox`
    and widens the viewBox on whichever side needs it.

    **This test asserts the mechanism is present, not that it works.** There is no headless render
    harness in this suite, so the behaviour was verified by driving a real browser at seven
    viewport widths from 1400 down to 340 px and asserting every text node sits inside the
    viewBox with a positive margin. That evidence is in the V0.26 changelog entry rather than
    here, and this test exists so the mechanism cannot be silently removed between browser checks.
    """
    script = client.get("/ui/app.js").text
    assert "getBBox" in script, "nothing measures the rendered text, so the fit is only arithmetic"
    assert "TEXT_FIT_PASSES" in script, "the refit is unbounded or absent"
    for side in ("minX", "minY", "maxX", "maxY"):
        assert side in script, f"the refit does not consider the {side} edge"
    #: The horizontal labels are positioned from the applied size, because fixed offsets collided
    #: with the axis caption at large sizes - visible in a screenshot at 430 px while every
    #: number was still inside the box.
    assert "X_TICK_OFFSET_EM" in script
    assert "X_CAPTION_OFFSET_EM" in script
    assert "data-role" in script
    #: The two controls added at V0.26.2, both of which were deletable with the whole suite green -
    #: the same fault this file names two tests below, in the same release that cited it.
    #:
    #: THE REFIT MUST RUN AGAIN ON RESIZE. It ran only at draw time, so dragging a window narrower
    #: left the stale build-time gutter in place until the next redraw, which is the clipped-label
    #: fault returning by another route. The viewBox reset is asserted with it, because without the
    #: reset each resize measures an already-widened box and grows it again until the plot
    #: disappears - a worse fault than the one the observer closes.
    assert "ResizeObserver" in script, "the refit does not run again after a resize"
    assert re.search(
        r"new ResizeObserver\(\(\) => \{\s*\n\s*\w+\.setAttribute\('viewBox'",
        script,
    ), "the resize refit does not reset the viewBox first, so the widening ratchets"
    #: AND getBBox MUST BE GUARDED. It returns zeros inside a display:none container in Chromium
    #: and throws rather than returning in other engines, and this call sits inside a
    #: requestAnimationFrame callback, where a throw escapes silently and abandons the refit
    #: half-applied. Asserting "getBBox in script" above holds the measurement, not the guard.
    #: AND the observers are released on redraw. `observe()` registers on the target's Document,
    #: not on the local variable that created it, so an argument that the observer and its frame
    #: become unreachable together does not follow from this source - it rests on whether the
    #: engine makes that edge weak. A drill fetch builds a fresh observer per panel, so a long
    #: session accumulates them over detached subtrees on that reading.
    #: THE SHAPE, NOT THE IDENTIFIERS. The first version of these three asserted that the strings
    #: `releasePlotRefits` and `.disconnect()` appear and that the call precedes `clear(`. Neither
    #: could see whether anything is ever TRACKED, nor whether the release DRAINS: deleting the
    #: push left the release iterating a permanently empty array, and `while` to `if` released one
    #: observer per redraw and let the list grow without bound - two leaks, both with 967 green.
    #: That is the same fault as the two majors this release fixes, introduced by the fix for the
    #: second of them. Bound to the shape now, and the shape is all a grep can hold: whether a
    #: browser then collects the observer is not asserted anywhere and is not meant to be, because
    #: the point of the release is that the code no longer depends on the answer.
    #:
    #: **THESE REJECT BEHAVIOUR-IDENTICAL REFACTORS, and no JavaScript formatter runs in the loop
    #: to trip them automatically.** Measured: brace-wrapping the `while` body, swapping the push
    #: above the `observe` call, and rewriting the drain as
    #: `for (const refit of plotRefits.splice(0)) refit.disconnect();` are all correct code and all
    #: fail here. Deliberate, because it fails closed - but DECLARED, so the next author reformats
    #: this test rather than reverting the code it holds. The known survivor is the mirror image:
    #: inserting `plotRefits.splice(0);` after the push is a real leak both regexes accept, because
    #: it is an insertion and no mutation operator produces one. Closing that needs a JavaScript
    #: runtime the loop does not have.
    assert re.search(r"refit\.observe\(frame\);\s*\n\s*plotRefits\.push\(refit\);", script), (
        "the observer is created and never tracked, so releasePlotRefits has nothing to release"
    )
    #: TWO assertions, not one. A single regex over the whole statement fired its DRAIN message
    #: for a DISCONNECT defect, which is a diagnosis that sends a reader to the wrong line - the
    #: fault this file's own truncation-mark rationale names one test along.
    assert re.search(r"while \(plotRefits\.length\)", script), (
        "the release does not drain the list, so a multi-panel composite keeps all but one observer"
    )
    assert re.search(r"plotRefits\.pop\(\)\.disconnect\(\);", script), (
        "the release empties the list without disconnecting: observers dropped still live"
    )
    assert re.search(r"releasePlotRefits\(\);\s*\n\s*clear\(", script), (
        "the release does not run before the redraw clears the frames it observes"
    )
    assert re.search(r"try \{\s*\n\s*\w+ = \w+\.getBBox\(\);\s*\n\s*\} catch", script), (
        "getBBox is unguarded, so an engine that throws abandons the refit inside a"
        " requestAnimationFrame callback"
    )


def test_the_withheld_items_are_named_on_the_served_manifest(client: TestClient) -> None:
    """Asserted on the RESPONSE BODY, because the first version asserted one altitude below it.

    `DrillLoop.manifest()` carried the list of items withheld from selection and the route did not
    serialise it, so "named on the manifest" was true of a method and false of every surface an
    operator can reach - the exact fault this codebase names at `ScoredDrill.as_dict`, repeated in
    the commit that cited it.
    """
    served = client.get("/api/v1/content/manifest").json()
    assert "items_without_a_resolvable_answer" in served, sorted(served)
    #: One today: DRL-0008, whose manoeuvre count is not readable off a relative-motion track.
    assert served["items_without_a_resolvable_answer"] == ["DRL-0008"]
    #: And the REASONS, which the route serialised while nothing asserted them: deleting the
    #: field from the route left the whole suite green, so "disclosed on the manifest" was again
    #: held by a docstring rather than a test. The same fault as the list above, one field along.
    assert "withheld_reasons" in served, sorted(served)
    reasons = served["withheld_reasons"]
    assert isinstance(reasons, dict), reasons
    assert set(reasons) == {"DRL-0008"}, reasons
    assert reasons["DRL-0008"], "an item is withheld with no reason given"
    #: Asserted on the SERVED body, not on the loop, because the exposure is the anonymous route.
    #: A content author sets these strings and cannot set their length.
    #:
    #: **A TRIPWIRE, and vacuous on the library as it stands.** The only withheld reason today is
    #: DRL-0008's, at 32 characters, so this loop cannot fail on shipped content: the bound itself
    #: is held in `test_drill_loop.py`, by the test that authors an oversized parameter to reach
    #: the branch. This one exists so that a future
    #: item withheld with a long reason fails HERE, on the served body, rather than being noticed
    #: on the route by a reviewer. Said plainly rather than left to read as coverage it is not.
    for item, reason in reasons.items():
        assert len(reason) <= MAX_WITHHOLD_REASON, f"{item}: {len(reason)} characters served"
