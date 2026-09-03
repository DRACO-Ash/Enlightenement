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
import logging
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from conftest import ok_probe
from enlightenment.app import (
    MAX_SERVED_SESSIONS,
    MAX_SERVED_SESSIONS_BYTES,
    Limiters,
    TrainingPaths,
    create_app,
)
from enlightenment.config import Config
from enlightenment.content import ContentPackage
from enlightenment.identifiers import MAX_NESTING_DEPTH
from enlightenment.ratelimit import RateLimiter
from enlightenment.storage import MAX_SESSIONS, TrainingStore
from enlightenment.training.drill import (
    MAX_CONTENT_STRING,
    MAX_PAYLOAD_BYTES,
    MAX_SERVED_COMPETENCIES,
    MAX_SERVED_DUE_ITEMS,
    MAX_SERVED_PARAMS,
    MAX_SERVED_PROMPT,
    MAX_SERVED_WITHHELD,
    MAX_WITHHOLD_REASON,
    TRUNCATION_MARK,
)
from enlightenment.training_api import MAX_SERVED_DOCUMENT_BYTES, MAX_SERVED_ERRORS

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


def _event_name(record: logging.LogRecord) -> str | None:
    """The `event` field of a structured audit line, or `None` if the record is not one.

    `log_event` emits one JSON object per line, so the event NAME is what identifies a sink;
    the logger name identifies only the module that owns every sink. Same idiom as
    `test_every_accepted_answer_emits_one_audit_line_carrying_no_performance_data`.
    """
    message = record.getMessage()
    if not message.startswith("{"):
        return None
    try:
        parsed = json.loads(message)
    except json.JSONDecodeError:
        return None
    return parsed.get("event") if isinstance(parsed, dict) else None


def test_a_submitted_answer_is_neither_echoed_nor_persisted(
    client: TestClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The property that makes `DrillAnswer.response` exempt from the control-character rule.

    `SessionUpsert` and `SessionPatch` refuse a control character because `json.dumps` escapes one
    as `\\u00XX` at SIX rendered bytes against an astral character's four, and those fields fill
    a served byte ceiling. `response` is exempt, and the whole justification is that it reaches
    neither a served surface nor the store: the matcher returns a verdict plus the AUTHORED
    `note`/`why_wrong`, and the run row records `classification=outcome.matched` with
    `first_action=""`.

    That was a reading of the code, and a reading is what a future change breaks in silence -
    which is the exact shape of fault this release exists to close. So the exemption is bound
    here instead: a marker planted in a hostile answer must appear in no response body, no
    `progress.json` and no log line. If someone ever echoes or records the operator's own words,
    this test goes red and `response` needs `FreeText` before it ships.

    The marker is checked as well as the control characters, because an implementation that
    SANITISED the answer and then echoed it would pass a search for `\\u0000` while still
    putting an operator's words on a served surface.
    """
    marker = "qqmarkerqq"
    hostile = f"{marker}\x00\x07\U0001f600"
    served = client.get("/api/v1/drill/next").json()
    with caplog.at_level("INFO"):
        response = client.post(
            "/api/v1/drill/answer",
            json={**ANSWER_BODY, "drill_run_id": served["drill_run_id"], "response": hostile},
        )
    assert response.status_code == 200, response.text
    assert marker not in response.text.casefold(), (
        f"the reveal echoed the operator's own words: {response.text[:240]}"
    )
    assert "\\u0000" not in response.text, "an escaped control from the answer reached the wire"

    persisted = (tmp_path / "progress.json").read_text(encoding="utf-8")
    assert marker not in persisted.casefold(), "the run record stored the operator's own words"
    assert "\\u0000" not in persisted, "an escaped control from the answer reached the store"

    #: Refuse an empty measurement, the rule this file already applies to the route sweep and the
    #: listing cap: `for record in []` passes, and one of the three sinks this test exists to bind
    #: would be unbound with the test still green.
    #:
    #: **The GUARD names the audit sink; the ASSERTION stays over every record.** Two separate
    #: properties, and collapsing them into one list cost the second. The first guard was
    #: `assert caplog.records`, which `httpx` satisfies with one record per request, so deleting
    #: the `drill.answered` sink left this test green while its sibling correctly failed - a
    #: guard no mutation can falsify. Narrowing fixed that and then narrowed the marker loop with
    #: it, so an answer echoed on ANY OTHER logger passed: `logging.getLogger(
    #: "enlightenment.training_api").info("answer text: %s", payload.response)` survived the
    #: whole suite. The docstring above claims "no log line", not "no audit log line", so the
    #: assertion has to be as wide as the claim while the guard stays narrow enough to bite.
    #: The guard binds the `drill.answered` EVENT, not merely its logger. Filtering on
    #: `record.name == "enlightenment.event"` alone would be satisfied by any second event on
    #: this route with the sink deleted, so the guard would claim to hold a sink it did not.
    audited = [
        record
        for record in caplog.records
        if record.name == "enlightenment.event" and _event_name(record) == "drill.answered"
    ]
    assert audited, (
        "no `drill.answered` audit record was captured, so the log arm of this test proved"
        " nothing; that sink is the one it exists to hold"
    )
    #: **Measured as the DEPLOYED HANDLER writes it, not as `getMessage()` returns it.** Both
    #: entry points configure `logging.basicConfig(format="%(message)s")`, and
    #: `logging.Formatter.format` appends `exc_text` and `stack_info` whatever the format string
    #: says - so a traceback is part of the shipped line while `getMessage()` omits it entirely.
    #: The V0.26.39 fix widened this loop from the audit records to ALL records and left the unit
    #: alone, so the same leak walked through the wider arm: raising `RuntimeError(
    #: payload.response)` and calling `.exception()` still returned 200 and still passed all
    #: 1,012 tests, with the answer text and its unsanitised control characters in a production
    #: log line. Widening the set is not widening the measurement.
    formatter = logging.Formatter("%(message)s")
    for record in caplog.records:
        assert marker not in formatter.format(record).casefold(), (
            f"the answer text reached the log on {record.name}"
        )


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
#: How long the hostile tree makes every operator-facing string. Named, because an assertion in
#: the sweep is guarded on it and a reshape to a shorter value must not turn that guard false.
HOSTILE_TEXT_LENGTH = 20000

DRAWS = 24
DRAWS_EXPECTED = 20

#: How many of the 140 drills have no generator supplying their answer once every item is authored
#: with the `computed_from_params` sentinel. Measured, and a LITERAL: the remaining 46 are drawn by
#: renderers that do emit `expected_text` or `expected_value`. Pinning the value is what kills a
#: hardcoded total - a range check admits any number over the cap, and a hardcoded 26 survived one.
WITHHELD_ON_THE_HOSTILE_TREE = 94

#: The GLOBAL widest rendered width, in bytes, of any code point the free-text rule accepts.
#: Measured over all 1,112,064 Unicode scalar values under `json.dumps(..., ensure_ascii=False)`,
#: which is what Starlette serialises with: accepted widths are {1: 93, 2: 1825, 3: 53593,
#: 4: 93490} and nothing accepted renders above four. `ensure_ascii=False` escapes only `"`, `\`
#: and the C0 controls, and a C0 control is not printable, so four is simply UTF-8's maximum.
GLOBAL_WIDEST_ACCEPTED_BYTES = 4

#: Every anonymous route this sweep covers, and for the ones it does not, WHY. Asserted as an exact
#: set: narrowing the discovery filter to a single route previously left the test green, so the
#: control's one load-bearing property - that it enumerates - was held by nothing.
#:
#: **`GET /api/v1/sessions` is SWEPT, and the two reasons it was excluded on were both wrong.**
#: The first said the session routes are TOKEN-GATED and therefore "not anonymous surfaces at
#: all". True of the writes, false of the read: it answers 200 with no `Authorization` header, by
#: the decision recorded as accepted risk 5 in `docs/SECURITY.md`. The second said their size is
#: governed by `storage.MAX_SESSIONS` and the field caps "which their own tests hold" - and
#: `MAX_SESSIONS` appeared nowhere in this suite except that sentence, so nothing held it.
#:
#: The security gate measured the consequence on the wire: filling the store to `MAX_SESSIONS`
#: through the gated write route, with every field inside its declared cap and accepted with 201,
#: served **1,231,926 bytes of ASCII and 4,711,926 with astral characters** from one
#: unauthenticated request. The second figure is past `MAX_PAYLOAD_BYTES`.
#:
#: The earlier objection to sweeping it was real and is answered rather than argued with: an EMPTY
#: fixture store measures 33 bytes and certifies nothing, so `_fill_sessions` drives the store to
#: `MAX_SESSIONS` at the field caps with astral characters - the worst case the boundary model
#: accepts - and the non-vacuity guard below then means something.
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
    "GET /api/v1/sessions": MAX_SERVED_SESSIONS_BYTES,
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
#: ● The session WRITE routes are token-gated: both answer 401 without an `Authorization` header,
#:   measured, so neither is an anonymous surface. The session READ is not excluded - it is swept
#:   above, because the claim that it was gated was false.
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

    **One field is ASTRAL, and that is a dimension this tree was blind to.** Every cap in this
    project is declared in CODE POINTS and every ceiling in this sweep is in BYTES, and one
    `U+1F600` is one code point and four bytes. A tree poisoned only with `"X"` therefore
    certifies the byte ceilings for single-byte content and says nothing about the rest, which the
    security gate demonstrated by reaching 21,823 bytes on a 16 kB ceiling with astral content.
    The competency NAME carries it: it is served, it is capped in code points, and its cut is
    marked, so one field exercises the code-point bound and the byte ceiling together.
    """
    shutil.copytree(CONTENT_ROOT, destination)
    long_text = "X" * HOSTILE_TEXT_LENGTH
    #: The IDS are astral too, and that is where the bytes actually are. Poisoning only the
    #: competency NAME left the byte ceilings certified for ASCII identifiers: measured, astral ids
    #: took `GET /api/v1/me` to 17,407 bytes against a 16,384-byte ceiling the suite reported as
    #: held, because `served_identifier` capped 64 CODE POINTS while the ceiling counted BYTES.
    #: Both are bytes now, so this tree measures the ceiling in the unit the ceiling is written in.
    long_id = "\U0001f600" * 3000
    astral_text = "\U0001f600" * HOSTILE_TEXT_LENGTH

    document = json.loads((destination / "drills.json").read_text(encoding="utf-8"))
    rows = document["drills"] if isinstance(document, dict) else document
    for index, row in enumerate(rows):
        #: The distinguishing part goes AFTER the cap, deliberately. With the index first, every
        #: id differed inside 64 characters and nothing collapsed, so the distinctness assertions
        #: below could not fail: `_bounded` on `due_items` survived inversion until this changed.
        #: A hostile tree has to be hostile in the SHAPE the fault needs, not only in length.
        row["id"] = f"DRL-{long_id}-{index}"
        #: `cue_id` too. The assertion for it existed and asserted nothing, because real cue ids are
        #: seven characters and this tree never stretched the field: deleting its bound left the
        #: whole suite green, and the changelog claimed the mutation was killed. A hostile tree that
        #: skips a field certifies that field.
        row["cue_id"] = f"CUE-{long_id}-{index}"
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
        entry["id"] = f"CMP-{long_id}-{index}"
        entry["name"] = astral_text
    while len(entries) <= MAX_SERVED_COMPETENCIES:
        clone = dict(template)
        clone["id"] = f"CMP-EXTRA-{len(entries)}"
        clone["name"] = astral_text
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
    #: The session store is DRIVEN, not left empty. `GET /api/v1/sessions` is an anonymous route
    #: whose body is set by stored state rather than by content, so an empty fixture measures 33
    #: bytes and certifies nothing - which is why it was excluded for seven releases.
    stored_sessions = _fill_sessions(store)
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
            #: SPLIT where a body legitimately carries a stimulus. A whole-body ceiling on
            #: `/api/v1/drill/next` cannot tell a large picture from a large envelope, which is the
            #: distinction the stateful test exists to make - and it was green here only because
            #: the selection bug fixed in this release drew the one small item. With selection
            #: working, that route serves 120,000 bytes of legitimate stimulus on this tree.
            payload = response.json() if response.status_code == 200 else {}
            if isinstance(payload, dict) and "stimulus" in payload:
                stimulus_bytes = _wire_bytes(payload["stimulus"])
                assert stimulus_bytes <= MAX_PAYLOAD_BYTES, (
                    f"{spec}: {stimulus_bytes}-byte stimulus against {MAX_PAYLOAD_BYTES}"
                )
                size = _wire_bytes({k: v for k, v in payload.items() if k != "stimulus"})
            else:
                size = len(response.content)
            measured[spec] = size
            if size > ceiling:
                oversized[spec] = size
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
        _assert_the_session_listing_is_capped(client, stored_sessions)
        me = client.get("/api/v1/me").json()
        assert me["due_items"], "no item is due, so the due-item caps assert nothing"
        assert len(me["due_items"]) <= MAX_SERVED_DUE_ITEMS, len(me["due_items"])
        assert len(me["competencies"]) == MAX_SERVED_COMPETENCIES, len(me["competencies"])
        for item_id in me["due_items"]:
            assert len(item_id) <= MAX_CONTENT_STRING, f"{len(item_id)} characters as a due id"
        #: DISTINCT, not merely short. `_bounded` collapsed three distinct authored due ids into one
        #: served name - a fabricated identifier on an anonymous route, and the fault
        #: `served_identifier` exists to end, still live on this line after the manifest was fixed.
        #: This tree's ids share the `DRL-` prefix and differ only past the cap.
        assert len(set(me["due_items"])) == len(me["due_items"]), sorted(me["due_items"])
        for row in me["competencies"]:
            assert len(row["name"]) <= MAX_CONTENT_STRING, len(row["name"])
            #: And a cut NAME says it was cut. The name had an identity's silent cap while the
            #: interface renders it as the primary label, so a shortened name read as the one
            #: somebody chose. Prose gets the marker; an identity gets the digest.
            #: The PRECONDITION is asserted, not used as a condition. Guarding the assertion with
            #: `if HOSTILE_TEXT_LENGTH > MAX_CONTENT_STRING` made it self-disabling: a reshape to
            #: shorter text would remove the control silently instead of telling anyone, which is
            #: the pattern this release's own record is about.
            assert HOSTILE_TEXT_LENGTH > MAX_CONTENT_STRING, (
                "the tree is no longer hostile enough for the marker to be measurable"
            )
            assert row["name"].endswith(TRUNCATION_MARK), row["name"][-20:]
            assert len(row["competency_id"]) <= MAX_CONTENT_STRING, len(row["competency_id"])
        assert len({row["competency_id"] for row in me["competencies"]}) == len(
            me["competencies"]
        ), sorted(row["competency_id"] for row in me["competencies"])[:3]
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


def _wire_bytes(value: Any) -> int:
    """Serialised size as the ROUTE renders it, not as `json.dumps` defaults would.

    `json.dumps` uses `(", ", ": ")` and `ensure_ascii=True`; `JSONResponse` renders `(",", ":")`
    and `ensure_ascii=False`. Measuring an envelope by subtracting a default-serialised stimulus
    overstated the subtrahend by up to 7,643 bytes and produced a NEGATIVE envelope on six of
    twenty-four draws, where the assertion held nothing and would have printed a negative byte
    count as its diagnosis.

    **A named approximation.** Reconstructing the envelope from the remaining keys omits the
    `"stimulus":` key name and its separators, about twelve bytes. Immaterial against a 16 kB
    ceiling, and it cannot go negative, which was the fault.
    """
    return len(
        json.dumps(value, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
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


def test_the_anonymous_session_listing_is_count_capped_and_reports_an_honest_total(
    token_config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """The write path ACCEPTS the values that made this route serve megabytes, and the read caps.

    `GET /api/v1/sessions` is unauthenticated by decision, and it was excluded from the anonymous
    body sweep on two claims that were both false: that the session routes are token-gated, and
    that `storage.MAX_SESSIONS` and the field caps govern the body "which their own tests hold".
    Nothing held it. Measured on the wire at `MAX_SESSIONS`, every field inside its declared cap:
    1,231,926 bytes of ASCII and 4,711,926 with astral characters, from one anonymous request -
    the second past `MAX_PAYLOAD_BYTES`.

    This test is the half the sweep cannot make: that the boundary model ACCEPTS these rows with
    201, so the amplification needs no invalid input and no bug, only a token holder writing
    inside the caps the API advertises. The byte measurement at full cap is the sweep's job.

    The listing keeps the NEWEST, because `storage._enforce_cap` keeps the newest and appends the
    fresh entry at the end, and it serves the untruncated `total` beside the short list: a
    shortened disclosure that reads as a complete one is the fault this project has closed four
    times in other fields.
    """
    written = MAX_SERVED_SESSIONS + 5
    app = create_app(
        config=token_config,
        store=store,
        probe=ok_probe,
        #: Permissive, because the strict write limiter is 20 per minute and this drives 30
        #: writes. The limiter has its own tests; borrowing its bound here would only make this
        #: one fail for the wrong reason.
        limiters=Limiters(
            coarse=RateLimiter(999_999, 60),
            strict=RateLimiter(999_999, 60),
            drill=RateLimiter(999_999, 60),
        ),
        training=TrainingPaths(content_root=CONTENT_ROOT, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app) as client:
        for index in range(written):
            response = client.post(
                "/api/v1/sessions",
                json={"id": f"session-{index:04d}", **_widest_session_fields()},
                headers={"x-team-token": token_config.team_token},
            )
            assert response.status_code == 201, (
                f"the boundary model refused a row inside its own declared caps at index"
                f" {index}: {response.status_code} {response.content[:200]!r}"
            )

        #: NO header. This is the whole point: the read is anonymous.
        listing = client.get("/api/v1/sessions")
        assert listing.status_code == 200, listing.status_code
        body = listing.json()

    assert body["total"] == written, f"the total is not the honest count: {body['total']}"
    assert body["count"] == MAX_SERVED_SESSIONS, f"the listing is not capped: {body['count']}"
    assert len(body["sessions"]) == MAX_SERVED_SESSIONS, len(body["sessions"])
    assert body["truncated"] is True, "a shortened listing does not say it was shortened"
    #: The NEWEST are kept. Dropping the newest would make the route useless while still passing
    #: a count assertion, which is the shape of mistake a cap invites.
    assert body["sessions"][-1]["id"] == f"session-{written - 1:04d}", body["sessions"][-1]["id"]
    assert len(listing.content) <= MAX_SERVED_SESSIONS_BYTES, (
        f"{len(listing.content)} bytes against a ceiling of {MAX_SERVED_SESSIONS_BYTES}"
    )


#: The marker planted into every authored parameter value. Distinctive enough that finding it in
#: a response body is unambiguous, and it is not a number, so every coercion site refuses on it.
AUTHORED_VALUE_MARKER = "MARKER-AUTHORED-VALUE-MUST-NOT-BE-SERVED"

#: The NUMERIC poison, and it holds a different branch. A string marker cannot reach the
#: `ArithmeticError` handler at all: it fails coercion first and takes the `ContentParameterError`
#: path. This value coerces cleanly and then overflows `timedelta`, which interpolates its own
#: argument - `OverflowError: days=-1000000007; must have magnitude <= 999999999`. So the claim
#: this project briefly wrote into `docs/SECURITY.md`, that no `ArithmeticError` message on
#: CPython 3.12 carries its operand, was FALSE, and the branch was held by nothing while the
#: register recorded a measured universal. The security gate constructed this counter-example.
#: The digits are the marker: any anonymous body containing them is serving an authored value.
AUTHORED_OVERFLOW_POISON = -1000000007


def _tree_whose_every_parameter_is_poisoned(destination: Path, poison: object) -> Path:
    """The shipped content tree with every stimulus parameter set to `AUTHORED_VALUE_MARKER`.

    Every drill is also forced onto ONE renderer, `waterfall`, whose coerced key `days` is among
    the poisoned ones. That is the load-bearing part and the reason three earlier attempts at this
    fixture measured nothing: `select` returns one deterministic item, so poisoning a key the
    selected item's generator does not read renders fine and returns 200. With every candidate on
    a renderer that must coerce a poisoned key, the whole selection budget refuses in ONE request
    and both anonymous surfaces compose a reason. The same "one draw hid every item after the
    first" filter failure the size sweep already records, one class along.

    `answer.accept` is set to a literal so the load-time probe stays clean: the tree must LOAD, or
    the manifest serves a load error instead of the withhold reasons this test is about.

    `poison` is a PARAMETER because the two refusal branches need different shapes of bad value: a
    string cannot reach the arithmetic handler, and a number cannot reach the coercion one.
    """
    shutil.copytree(CONTENT_ROOT, destination)
    document = json.loads((destination / "drills.json").read_text(encoding="utf-8"))
    rows = document["drills"] if isinstance(document, dict) else document
    for row in rows:
        row["stimulus"] = {
            "product_id": "PRD-WATERFALL",
            "generator": "waterfall",
            "params": {
                "days": poison,
                "headcount": poison,
                "gap_len_hours": poison,
                "derived_rate_deg_day": poison,
            },
        }
        row["answer"] = {"accept": ["manoeuvre"]}
    (destination / "drills.json").write_text(json.dumps(document), encoding="utf-8")
    return destination


@pytest.mark.parametrize(
    ("poison", "needle", "branch"),
    [
        (AUTHORED_VALUE_MARKER, AUTHORED_VALUE_MARKER, "coercion"),
        (AUTHORED_OVERFLOW_POISON, str(abs(AUTHORED_OVERFLOW_POISON)), "arithmetic"),
    ],
    ids=["coercion", "arithmetic"],
)
def test_no_anonymous_route_serves_an_authored_content_value_in_a_refusal(
    token_config: Config,
    store: TrainingStore,
    tmp_path: Path,
    poison: object,
    needle: str,
    branch: str,
) -> None:
    """A refusal names the KEY and its DOMAIN, never the value that failed - held over the ROUTE
    TABLE rather than on one renderer's message, and over BOTH refusal branches.

    `docs/SECURITY.md` recorded this control as closed from V0.26.3, and the security gate defeated
    it in TWO anonymous requests against a copy of the shipped tree. V0.26.3 removed the one
    explicit interpolation and left the mechanism that actually carried values: `float("...")` puts
    the string it could not parse into its own message, and `training/drill.py` reflected that
    message verbatim into both the anonymous `503` on `/api/v1/drill/next` and the
    `withheld_reasons` map on the anonymous `/api/v1/content/manifest`.

    The cited test passed throughout because it asserted ONE refusal on ONE renderer - the
    `newest_at` domain check, the message that had been fixed. That is the same defect as a
    per-field size assertion: it holds the field somebody thought of. So this enumerates the whole
    route table, drives the refusal, and asserts the marker appears in NO body, 200 or 503 alike.

    **Both branches, because a string cannot reach the arithmetic one.** The coercion case fails
    `float()` and takes the `ContentParameterError` path. The arithmetic case coerces cleanly and
    then overflows `timedelta`, which interpolates its own argument. V0.26.23 recorded in the code
    and in the register that no `ArithmeticError` message on CPython 3.12 carries its operand, so
    the branch was "unheld rather than exploitable" - **that was false**, and with the exception
    re-interpolated the authored operand reached both anonymous surfaces with the whole suite
    green. A measured universal in a security register is exactly the claim that stops anyone
    looking, so the branch is held now rather than excused.

    What this deliberately does NOT forbid: a generator name or a product id. Those are structural
    identifiers inside the register's carve-out, because a typo in one is undiagnosable otherwise,
    and both are shortened at the raise site so neither can size a response.
    """
    root = _tree_whose_every_parameter_is_poisoned(tmp_path / "content", poison)
    app = create_app(
        config=token_config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=root, progress_path=tmp_path / "progress.json"),
    )
    discovered = {
        f"{method} {route.path}"
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method not in {"HEAD", "OPTIONS"}
    }
    #: The same exact-set assertion the size sweep makes, for the same reason: a discovery that
    #: silently narrows to one route is a control that holds one route.
    known = ANONYMOUS_ROUTES_SWEPT.keys() | ANONYMOUS_ROUTES_EXCLUDED
    assert discovered == known, (
        f"the route table changed and this sweep was not updated: {sorted(discovered ^ known)}"
    )

    with TestClient(app) as client:
        #: NON-VACUITY, first. The tree must load, and the refusal must actually fire, or the
        #: absence of the marker below is the absence of any refusal at all.
        manifest = client.get("/api/v1/content/manifest")
        assert manifest.json()["ok"], manifest.json()["errors"][:2]
        refusal = client.get("/api/v1/drill/next")
        assert refusal.status_code == 503, (
            "no candidate refused, so this test measures nothing:"
            f" {refusal.status_code} {refusal.content[:160]!r}"
        )
        assert "selection budget" in refusal.text, refusal.text[:200]
        #: And the refusal came from the branch this case exists to drive. Without this the
        #: arithmetic case could silently take the coercion path and hold nothing new.
        expected = "must be a number" if branch == "coercion" else "could not be computed from its"
        assert expected in refusal.text, (
            f"the {branch} branch was not the one that refused: {refusal.text[:240]}"
        )
        withheld = client.get("/api/v1/content/manifest").json()["withheld_reasons"]
        assert withheld, "no item was withheld, so no reason was composed"

        leaked: dict[str, str] = {}
        for spec in sorted(discovered):
            method, template = spec.split(" ", 1)
            path = _resolved(template, client)
            if path is None:
                continue
            response = (
                client.get(path)
                if method == "GET"
                else client.request(method, path, json={"id": "s-1", "title": "t", "scenario": "s"})
            )
            if needle in response.text:
                leaked[spec] = response.text[:240]

    assert leaked == {}, (
        "these anonymous routes served an authored content value inside a refusal, which"
        f" docs/SECURITY.md promises they never do: {leaked}"
    )


#: Legal JSON that `str.encode("utf-8")` refuses. `json.loads('"\\ud800"')` returns this, so a
#: content author can write one with an escape sequence and no invalid byte in the file.
LONE_SURROGATE = "\ud800"


def _poison_a_drill_value(root: Path) -> str:
    """A surrogate in unvalidated PROSE. The 500 that pydantic's serialiser raised."""
    path = root / "drills.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = document["drills"] if isinstance(document, dict) else document
    rows[0]["prompt"] = f"SECRET-AUTHORED-PROSE-{LONE_SURROGATE}"
    path.write_text(json.dumps(document), encoding="utf-8")
    return "/drills/0/prompt"


def _poison_a_drill_key(root: Path) -> str:
    """A surrogate in a dict KEY. Loaded with zero errors and 200 on every route before the walk
    covered keys, held only by two downstream accidents in two different layers."""
    path = root / "drills.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = document["drills"] if isinstance(document, dict) else document
    params = rows[1].setdefault("stimulus", {}).setdefault("params", {})
    params[f"SECRET-AUTHORED-KEY{LONE_SURROGATE}"] = 1
    path.write_text(json.dumps(document), encoding="utf-8")
    return "/stimulus/params/SECRET-AUTHORED-KEY"


def _poison_with_depth(root: Path) -> str:
    """A value nested past the serialiser's limit, on the CONTENT side.

    `loader.py`'s depth arm was one of eight lines the suite never executed, so the content-side
    depth message had no driver at all while the register described it. Fail-closed held either
    way; what was unheld was the DIAGNOSIS, and this project treats a wrong diagnosis as
    load-bearing - a 503 naming an encoding fault for a nesting fault sends an author to the
    wrong file.
    """
    path = root / "drills.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = document["drills"] if isinstance(document, dict) else document
    node: Any = 1
    for _ in range(MAX_NESTING_DEPTH + 4):
        node = {"d": node}
    rows[0].setdefault("stimulus", {}).setdefault("params", {})["deep"] = node
    path.write_text(json.dumps(document), encoding="utf-8")
    return "/drills/0/stimulus/params/deep"


def _poison_a_library_array(root: Path) -> str:
    """A surrogate in an ARRAY-held string, the third branch and the one with no driver at all.

    Coverage named `identifiers.py:158` as never executed in 994 tests. Deleting that branch left
    the whole suite green while `GET /api/v1/content/procedure/PROC-MNV` went back to **500** on a
    poisoned `entry_conditions` entry - the identical defect `docs/SECURITY.md` records as closed
    for "an unvalidated PROSE leaf of a procedure". Every shipped content file carries arrays of
    strings and several are served prose, so splitting one walk into three left one third holding
    an anonymous 500 by nothing. **Holding the walk is not holding its branches**, the same lesson
    as holding a function rather than its call sites, one level down.
    """
    path = root / "procedures" / "procedures-core.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    procedures = document["procedures"] if isinstance(document, dict) else document
    procedures[0]["entry_conditions"][0] = f"SECRET-ARRAY-PROSE-{LONE_SURROGATE}"
    path.write_text(json.dumps(document), encoding="utf-8")
    return "/procedures/0/entry_conditions/0"


@pytest.mark.parametrize(
    ("poison", "marker"),
    [
        (_poison_a_drill_value, "SECRET-AUTHORED-PROSE"),
        (_poison_a_drill_key, "SECRET-AUTHORED-KEY"),
        (_poison_a_library_array, "SECRET-ARRAY-PROSE"),
        (_poison_with_depth, "no marker"),
    ],
    ids=["value", "key", "array", "depth"],
)
def test_a_lone_surrogate_in_content_fails_the_load_closed_rather_than_crashing_a_route(
    token_config: Config,
    store: TrainingStore,
    tmp_path: Path,
    poison: Callable[[Path], str],
    marker: str,
) -> None:
    """A traceback on an unauthenticated route, from authored data, through four routes.

    A lone surrogate is legal JSON and legal in a Python `str`, and encoding one to UTF-8 raises.
    Nothing expected that. Measured: three drills whose ids carried one produced a **500 on the
    anonymous `/api/v1/me`**, because `served_identifier` encodes to measure a length; and a
    surrogate in an unvalidated PROSE leaf of a procedure produced a **500 on the anonymous
    `/api/v1/content/procedure/{id}`**, raised by pydantic's own serialiser while rendering the
    response, which no application code touches.

    **Sanitising at each serve site was tried first and was the wrong shape.** The identifier path
    was fixed and the 500 simply moved to the next unvalidated field, which is the per-field fault
    this suite has now recorded in three separate classes. The rejection is at
    `content/loader._read_json`, the one place content enters the process, so the whole tree fails
    closed to the documented `content_unavailable` 503 rather than one route crashing.

    **Parametrised over the three shapes a string can be held in, because the walk has a branch
    per shape and one tree cannot drive them all**: `_read_json` raises on the first file it
    fails, so a tree poisoned in two files reports one error and the second branch goes unproven.
    That is how the array branch reached this release uncovered.

    Two properties per case: no anonymous route answers 5xx except that documented 503, and the
    load error names the FILE and a JSON POINTER and never the offending value - except a KEY,
    which is named because a pointer to a key IS the key, the same structural-identifier carve-out
    the register records for a generator name.
    """
    root = tmp_path / "content"
    shutil.copytree(CONTENT_ROOT, root)
    pointer = poison(root)

    app = create_app(
        config=token_config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=root, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        manifest = client.get("/api/v1/content/manifest")
        assert manifest.status_code == 200, manifest.status_code
        errors = manifest.json()["errors"]
        assert errors, "the tree loaded with a value that cannot be serialised"
        joined = " ".join(str(error) for error in errors)
        #: The message names the RIGHT FAULT. The depth case is a different refusal with a
        #: different sentence, and asserting only "a refusal happened" is what left that
        #: arm unheld while the register described it.
        expected_fault = "nests deeper than" if poison is _poison_with_depth else "lone surrogate"
        assert expected_fault in joined, joined[:300]
        assert pointer in joined, f"the error names no JSON pointer for {pointer}: {joined[:400]}"
        #: A KEY is named and a VALUE is not. The key case asserts the pointer above, which
        #: contains its marker by construction; the other two must not leak theirs.
        if poison not in {_poison_a_drill_key, _poison_with_depth}:
            assert marker not in joined, (
                f"the load error quoted the authored value that failed it: {joined[:300]}"
            )

        crashed: dict[str, int] = {}
        for spec in sorted(ANONYMOUS_ROUTES_SWEPT.keys() | ANONYMOUS_ROUTES_EXCLUDED):
            method, template = spec.split(" ", 1)
            path = _resolved(template, client)
            if path is None:
                continue
            response = (
                client.get(path)
                if method == "GET"
                else client.request(method, path, json={"id": "s-1", "title": "t", "scenario": "s"})
            )
            #: 503 is the documented fail-closed branch. Anything else in the 5xx range is a
            #: traceback reaching an anonymous caller.
            if response.status_code >= 500 and response.status_code != 503:
                crashed[spec] = response.status_code

    assert crashed == {}, (
        f"these anonymous routes crashed on content carrying a lone surrogate: {crashed}"
    )

    #: AND on the loader's UNCUT output. The served form above is bounded to 256 bytes by
    #: `bounded_reason`, so a message that appended the whole document would have its disclosure
    #: truncated away and pass this test - measured: that exact mutation survived. The
    #: non-disclosure is a property of the MESSAGE, so it is asserted where the message is whole.
    package = ContentPackage(root)
    package.load()
    raw = " ".join(str(error) for error in package.result.errors)
    assert expected_fault in raw, raw[:300]
    if poison not in {_poison_a_drill_key, _poison_with_depth}:
        assert marker not in raw, f"the loader's own error quoted the authored value: {raw[:300]}"


#: An authored rating outside the band, used to drive a LOAD-time validation failure. Its digits
#: are the marker: they are the authored value, and a refusal must not repeat them.
OUT_OF_BAND_ELO = 99999999


def test_no_anonymous_route_serves_an_authored_value_from_a_load_failure(
    token_config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """The load-failure surface of the same rule, which the render-time sweep cannot reach.

    A tree that FAILS to load serves its validation errors on two anonymous surfaces - the
    manifest's `errors` list and the `content_unavailable` 503 on `/api/v1/drill/next` - and a
    pydantic validator's message is composed by this project, not by pydantic. `content/models.py`
    interpolated the authored `elo` into its own refusal, so an authored 99999999 was served back
    from both. Measured by the security gate; killed by this test.

    The sibling render-time test cannot see this class, and the difference is structural rather
    than incidental: it asserts the tree LOADS, because withhold reasons only exist for a tree
    that loaded. This one asserts the opposite precondition. A single test cannot hold both.

    Pydantic's OWN messages are checked in the same pass and are already value-free - "Input
    should be a valid string", "Input should be a valid integer" - so the rule needs enforcing
    only where this project writes the sentence.
    """
    root = tmp_path / "content"
    shutil.copytree(CONTENT_ROOT, root)
    document = json.loads((root / "drills.json").read_text(encoding="utf-8"))
    rows = document["drills"] if isinstance(document, dict) else document
    for row in rows[:3]:
        row["elo"] = OUT_OF_BAND_ELO
    (root / "drills.json").write_text(json.dumps(document), encoding="utf-8")

    app = create_app(
        config=token_config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=root, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app) as client:
        manifest = client.get("/api/v1/content/manifest")
        #: NON-VACUITY: the tree must actually have failed, and on the field this test poisons.
        assert manifest.status_code == 200, manifest.status_code
        errors = manifest.json()["errors"]
        assert errors, "the tree loaded, so no validation error was served"
        assert any("elo" in str(error) for error in errors), errors[:3]

        refusal = client.get("/api/v1/drill/next")
        assert refusal.status_code == 503, refusal.status_code
        assert "content_unavailable" in refusal.text, refusal.text[:200]

        for label, text in (("manifest", manifest.text), ("drill/next", refusal.text)):
            assert str(OUT_OF_BAND_ELO) not in text, (
                f"the anonymous {label} served the authored value that failed validation:"
                f" {text[:240]}"
            )
        #: And the diagnosis survives: the KEY and its DOMAIN are what an author needs.
        assert "rated band" in manifest.text, manifest.text[:240]


def _widest_accepted_character(field: str) -> str:
    """The most expensive character the write boundary accepts IN THIS FIELD, on the wire.

    **The lengths were derived and the CHARACTER was hardcoded to an emoji**, which bound one axis
    of the worst case and reported 66% of it as the whole. `json.dumps` escapes a C0 control as
    `\\u00XX` even with `ensure_ascii=False`, so `U+0000` cost SIX rendered bytes per code point
    where an astral character costs four - and `SessionUpsert` accepted it. Measured by the
    security gate: twenty API-accepted writes at the declared caps rendered to 281,353 bytes
    against the 262,144 ceiling, and twenty-five rows to 351,327, so the emoji basis under-measured
    the true worst case by 1.48x.

    That is the same "measured in the wrong unit" class V0.26.33 closed on the `ensure_ascii` axis,
    one level along - and the reasoning was already in that very commit, in `audit.py`, which
    derives 6.0 at `U+0000` and names the `isprintable()` filter as load-bearing for its bound. The
    sibling ceiling did not get it.

    So the filler is CHOSEN BY MEASUREMENT over a candidate set spanning every UTF-8 width, the
    short-escape characters and the C0 controls, keeping only what the boundary accepts. A
    boundary change admitting a more expensive character makes this test choose it rather than
    quietly keep testing the cheap one.

    **PER FIELD, and the probe is a RUN rather than one trailing character.** Both corrections came
    from the same finding. The probe validated `f"x{candidate}"` on `title` alone and then the
    single winner filled every field, `notes` included, which is 8,000 of the roughly 9,280 rendered
    bytes in a row - so `notes` accepting a six-byte character while `title` refused it would leave
    this derivation returning the four-byte emoji and reporting 90% of a ceiling the API could
    exceed at 335,264 bytes on the planted snapshot at twelve character ids. A run also fixes what
    "accepts" means: `str_strip_whitespace` removes a lone trailing `\n`, `\t` or `U+2028`, so the
    old probe recorded those as ACCEPTED when a field of them collapses to empty and they can never
    fill anything. Accepted here now means the model KEEPS the run.

    **There is no assertion that a refused candidate costs more than the winner, and the earlier one
    was withdrawn as false rather than tightened.** The security gate asked for it strict (`>`
    rather than `>=`); measured, the premise does not hold in either form. Over ALL of Unicode,
    7,950 code points are refused at strictly under four rendered bytes and 955,086 more at exactly
    four, so the strict form fails by 963,036 counterexamples. **Those two figures are measured
    against the `FreeText` RULE, not against this function's KEEPS-the-run probe**, and the
    distinction is not academic here: on the probe's definition the same scan gives 7,954 and
    963,040, because the space and the three free-text controls strip away and so count as refused.
    Either basis buries the premise; the rule is the one quoted because it is the boundary's own
    test. Within THIS candidate list it fails on three: the boundary refuses `\n` and `\t` at 2
    rendered bytes and `U+2028` at 3, all CHEAPER than the four-byte winner, because those refusals
    are about hygiene and bidi spoofing rather than size. An earlier version of this paragraph also
    cited `U+00A0`, `U+200B`, `U+200D`, `U+FEFF` and `U+202E` as though they were in the list below;
    they are not, so they belong to the scan and not to this set. Claiming more than the fixture
    holds is the same fault, one sentence along. The old form passed only because the
    trailing-character probe mis-recorded the cheap ones as accepted. A cheap character being
    refused cannot widen a worst case that is `max` over the accepted set, so the assertion never
    bound anything; what does bind is the width spread of the candidate list, asserted below, which
    stops anyone deleting the astral member and leaving a cheap filler chosen in silence.
    """
    candidates = [
        "a",
        "\u00e9",
        "\u4e2d",
        "\U0001f600",
        "\\",
        '"',
        "\n",
        "\t",
        "\x00",
        "\x07",
        "\u2028",
    ]

    from enlightenment.models import SessionUpsert

    def rendered(character: str) -> int:
        return len(json.dumps(character, ensure_ascii=False).encode("utf-8")) - 2

    #: A fact about the LITERAL LIST, not about the boundary: the set must still span every
    #: UTF-8 width, or the derivation quietly picks a cheap filler and reports a ceiling met.
    assert {rendered(candidate) for candidate in candidates} >= {1, 2, 3, 4}, (
        "the candidate set no longer spans one, two, three and four rendered bytes, so the"
        " widest accepted character cannot be derived from it"
    )

    accepted: list[str] = []
    for candidate in candidates:
        values: dict[str, str | None] = {"id": "probe", "title": "x", "scenario": "s"}
        values[field] = candidate * 3
        try:
            model = SessionUpsert.model_validate(values)
        except ValidationError:
            continue
        #: Accepted means KEPT. `str_strip_whitespace` collapses a field of `\n`, `\t` or
        #: `U+2028` to empty, so a stripped candidate cannot fill this field at any length.
        if getattr(model, field) == candidate * 3:
            accepted.append(candidate)
    assert accepted, f"the write boundary accepts no character at all in {field}"
    filler = max(accepted, key=rendered)
    #: `max` makes "no accepted candidate costs more than the filler" unfalsifiable, so the
    #: assertion that stood here could not go red under any mutation: dead code inside a control,
    #: which `app.py` itself condemns. This one bites. Four is the GLOBAL maximum over every code
    #: point the rule accepts, so the emoji is not merely the widest of eleven candidates but the
    #: worst case Unicode admits - and a boundary change admitting a six-byte control fails HERE,
    #: one line from the cause, rather than three layers away as a 503 against a 200.
    assert rendered(filler) == GLOBAL_WIDEST_ACCEPTED_BYTES, (
        f"{filler!r} in {field} renders at {rendered(filler)} bytes, not"
        f" {GLOBAL_WIDEST_ACCEPTED_BYTES}: the write boundary's accepted set has changed, so"
        " every published byte figure resting on it needs re-measuring"
    )
    return filler


def _widest_session_fields() -> dict[str, str]:
    """Every writable session field at its DECLARED maximum, derived from the model.

    The lengths were hardcoded as 200, 120 and 2,000, which binds less than the test claims:
    widening `notes` on `SessionUpsert` would leave this green while the real worst case grew past
    the served byte ceiling and made the refusal at `app.py` - "a row was not written through this
    API" - false. `MAX_SERVED_SESSIONS` was already bound symbolically beside it; the field caps
    were not, which is the asymmetry the engineering gate found.

    Measured, each figure with the fixture that produces it, because a bare 237,138 published
    here reproduced on nothing and then a bare 237,163 named a fixture it does not hold on. The
    listing serves `MAX_SERVED_SESSIONS` rows whatever is written, so **ROWS WRITTEN is a
    variable of the measurement**, not a detail: it decides `total`'s digit count, `rev`'s digit
    count, and whether `truncated` renders as `true` or `false`, one byte. THREE variables, and
    an earlier version of this sentence named two - which left the sequence 235,863, 235,862,
    235,864 unreconcilable from the stated mechanism, so a reader computing it would have
    concluded a figure was wrong. Measured: 99 rows written gives 235,862 and 100 gives 235,864,
    the two bytes being one extra digit in `total` AND one in `rev`.

    All four figures below are astral filler at these caps; the first three are driven through the
    real gated POST route and the fourth is a planted snapshot, which is stated on each because it
    is the difference between them:

    ● **235,862 bytes, 89.97%, headroom 26,282**, at 30 rows written and twelve character ids.
      **This is THIS FUNCTION'S only caller**,
      `test_the_anonymous_session_listing_is_count_capped_and_reports_an_honest_total`, which
      writes `MAX_SERVED_SESSIONS + 5` rows through the gated POST route. It is the figure that
      describes the fixture actually running, and it was the one figure never published. An
      earlier version of this bullet named the hostile-tree sweep instead; that sweep calls
      `_fill_sessions`, whose figure is the fourth bullet, so the correction for a
      wrongly-attributed fixture attributed one wrongly.
    ● **237,162 bytes, 90.47%, headroom 24,982**, at 30 rows written and sixty-four character ids,
      the widest ids the boundary accepts.
    ● **237,163 bytes, 90.47%, headroom 24,981**, at exactly 25 rows written and sixty-four
      character ids. The single byte is `truncated: false`, because 25 written is 25 served.
    ● **235,264 bytes, 89.75%**, on a planted 500-row snapshot at twelve character ids and twenty
      character timestamps, which is `_fill_sessions`'s fixture rather than this one's.

    The variance mechanism published here before, "a byte or two with the timestamp's microsecond
    width", was invented rather than measured and is wrong in kind: `datetime.isoformat()` emits
    six microsecond digits or omits `.ffffff` altogether, so a timestamp moves a row by 0 or 7
    bytes, 14 per row across both stamps and up to 350 across the served 25. The byte that
    actually separated two of these figures was the `truncated` flag.

    About 25 kB of headroom on the widest of them is why deriving matters rather than being tidy -
    that margin is one field widening away.

    The FILLER is derived per field for the same reason the LENGTH is: one winner chosen on
    `title` and applied to `notes` binds the wrong field, and `notes` carries 8,000 of the
    roughly 9,280 rendered bytes in a row. All three fields choose the same character today.
    """
    from enlightenment.models import SessionUpsert

    widest: dict[str, str] = {}
    for name, field in SessionUpsert.model_fields.items():
        if name == "id":
            continue
        #: Derived INSIDE the loop, so each field is filled with the worst character THAT FIELD
        #: accepts rather than the worst character `title` accepts.
        filler = _widest_accepted_character(name)
        limit = next(
            (
                item.max_length
                for item in field.metadata
                if getattr(item, "max_length", None) is not None
            ),
            None,
        )
        assert limit is not None, f"{name} declares no max_length, so this test cannot derive it"
        widest[name] = filler * limit
    assert widest, "SessionUpsert declares no writable field but `id`"
    return widest


def _assert_the_session_listing_is_capped(client: TestClient, stored: int) -> None:
    """The listing's COUNT cap and honest total, checked inside the route sweep.

    A helper rather than three more statements in the sweep, which is at ruff's limit. It is
    asserted HERE as well as in its own test because a byte ceiling cannot tell a capped list from
    a lucky one: twenty-five rows of short ASCII pass the ceiling with no cap in place at all.
    """
    listing = client.get("/api/v1/sessions").json()
    assert listing["total"] == stored, listing["total"]
    assert listing["count"] == MAX_SERVED_SESSIONS, listing["count"]
    assert listing["truncated"] is True, listing["truncated"]


def _fill_sessions(store: TrainingStore) -> int:
    """Drive the session store to its cap at the field caps, so the sweep measures a worst case.

    Written straight to the snapshot rather than through 500 gated writes, because each write
    takes the advisory lock and an `fsync` and the sweep does not need to re-prove the write path.
    What the write path accepts IS asserted, once, by
    `test_the_anonymous_session_listing_is_count_capped_and_reports_an_honest_total`.

    ASTRAL characters, not ASCII. Every cap in this project is declared in CODE POINTS and every
    ceiling is in BYTES, and a `U+1F600` is one code point and four bytes: the ASCII fill measures
    61,264 bytes where the same row count measures 235,264. A sweep that only ever poisons with
    `"X"` certifies the byte ceiling for single-byte content and says nothing about the rest.

    **Both figures carry their FIXTURE now, because both were published without one and both went
    stale by the same 150 bytes.** They are measured on THIS fixture: a planted snapshot, twelve
    character `session-NNNN` ids and twenty character timestamps. Change the id width or the
    timestamp width and the number moves without any control changing, which is how a figure
    published bare becomes a figure nobody can reproduce.
    """
    rows = [
        {
            "id": f"session-{index:04d}",
            "title": "\U0001f600" * 200,
            "scenario": "\U0001f600" * 120,
            "notes": "\U0001f600" * 2000,
            "createdAt": "2026-09-02T00:00:00Z",
            "updatedAt": "2026-09-02T00:00:00Z",
        }
        for index in range(MAX_SESSIONS)
    ]
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps({"rev": MAX_SESSIONS, "sessions": rows}), encoding="utf-8")
    return len(rows)


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


def test_the_unbuilt_product_log_line_names_two_long_ids_distinctly(
    token_config: Config, store: TrainingStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed line with ZERO coverage, cited in the register as a closed cousin.

    `if unbuilt:` never executes in the suite by construction: the binding check keeps every
    referenced product renderable for the shipped tree, so the branch is dead in every other test.
    An inversion of a line that never runs cannot change a test outcome, which means the claim
    "every call site inverted individually" was not true of this one - the survey recorded a result
    for a line nothing executed.

    `log_event` sanitises only string FIELDS, so a list of content ids reached the line raw and at
    full length. Boot-only, and not the collapse class since nothing was cut, but this codebase's
    own principle is that a log line is a wire too.
    """
    root = tmp_path / "content"
    shutil.copytree(CONTENT_ROOT, root)
    document = json.loads((root / "drills.json").read_text(encoding="utf-8"))
    rows = document["drills"] if isinstance(document, dict) else document
    #: Two product ids no renderer claims, sharing a prefix longer than the cap, so a plain
    #: truncation collapses them and a raw value is unbounded.
    shared = "PRD-" + "N" * 300
    for index, row in enumerate(rows[:2]):
        row.setdefault("stimulus", {})["product_id"] = f"{shared}-{index}"
    (root / "drills.json").write_text(json.dumps(document), encoding="utf-8")

    lines: list[str] = []

    class _Sink:
        @staticmethod
        def info(line: str) -> None:
            lines.append(line)

    monkeypatch.setattr("enlightenment.audit._event_logger", _Sink())
    create_app(
        config=token_config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=root, progress_path=tmp_path / "progress.json"),
    )
    emitted = [line for line in lines if "content.unbuilt_products" in line]
    assert emitted, f"the branch did not run, so this asserts nothing: {len(lines)} lines"
    named = [name for name in json.loads(emitted[0])["products"] if "PRD-NNN" in name]
    assert len(named) == 2, named
    assert len(set(named)) == 2, f"two unbuilt product ids logged as one name: {named}"
    for name in named:
        assert len(name) <= MAX_CONTENT_STRING, f"{len(name)} characters in a log line"


def test_the_answer_route_logs_two_distinct_names_for_two_long_ids(
    token_config: Config, store: TrainingStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Driven through the ROUTE, because holding the function is not holding the call site.

    `training_api` passed a raw content id to `log_event`, and `audit.py` cuts a log value at 256
    with no marker and no digest, so two ids differing only past 256 characters produced
    byte-identical lines. The first test for this called `served_identifier` in its own body: it
    held the function and the emitter, and the production line stayed revertible with the whole
    suite green. A call site is held by driving the caller.
    """
    root = tmp_path / "content"
    shutil.copytree(CONTENT_ROOT, root)
    document = json.loads((root / "drills.json").read_text(encoding="utf-8"))
    rows = document["drills"] if isinstance(document, dict) else document
    #: Differing only past the 256-character log cut, so a silent truncation collapses them.
    shared = "DRL-" + "W" * 300
    #: EVERY id shares the prefix, so any two draws are two long ids. Poisoning two named items
    #: instead left selection free not to draw them: thirty draws returned only one of the pair,
    #: because selection is due-first then rating-matched and owes this test nothing.
    for index, row in enumerate(rows):
        row["id"] = f"{shared}-{index}"
    (root / "drills.json").write_text(json.dumps(document), encoding="utf-8")

    lines: list[str] = []

    class _Sink:
        @staticmethod
        def info(line: str) -> None:
            lines.append(line)

    monkeypatch.setattr("enlightenment.audit._event_logger", _Sink())
    app = create_app(
        config=token_config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=root, progress_path=tmp_path / "progress.json"),
        limiters=Limiters(drill=RateLimiter(200, 60.0)),
    )
    with TestClient(app) as client:
        answered: set[str] = set()
        for _ in range(8):
            drill = client.get("/api/v1/drill/next").json()
            reply = client.post(
                "/api/v1/drill/answer",
                json={
                    "drill_run_id": drill["drill_run_id"],
                    "response": "manoeuvre",
                    "confidence": 3,
                    "elapsed_ms": 1000,
                },
            )
            assert reply.status_code == 200, reply.content[:160]
            if drill["item_id"].startswith("DRL-WWW"):
                answered.add(drill["item_id"])
            if len(answered) == 2:
                break
    assert len(answered) == 2, f"the two long-id items were not both served: {sorted(answered)}"
    logged = {line for line in lines if "drill.answered" in line and "DRL-WWW" in line}
    assert len(logged) == 2, (
        f"two long-id items produced {len(logged)} distinct log lines:"
        f" {[line[:110] for line in sorted(logged)]}"
    )


def test_two_oversized_library_documents_are_named_distinctly_in_the_refusal(
    token_config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """The SIXTH instance of the shortened-identifier class, and the one outside `drill.py`.

    `training_api` imported the private `_bounded` across a module boundary - which
    `bounded_reason`'s own docstring forbids, and while `served_identifier` was already public - and
    used it to name an authored identifier in the anonymous `document_too_large` 503. Two procedure
    ids sharing an 85-character prefix, both over the reference budget, were served as ONE name
    matching neither id an author wrote, on a route that needs no token.

    A `drill.py`-scoped sweep missed it, which is why the rule is now "one function, everywhere"
    rather than "this module is clean".
    """
    root = tmp_path / "content"
    shutil.copytree(CONTENT_ROOT, root)
    core = root / "procedures" / "procedures-core.json"
    document = json.loads(core.read_text(encoding="utf-8"))
    entries = document["procedures"] if isinstance(document, dict) else document
    shared = "PROC-" + "Z" * 85
    #: Over the document budget, so both refuse, and distinguishable only past the cap.
    #: ONE template cloned for both, so the two documents are byte-identical apart from the id and
    #: serialise to the SAME size. The first version used two different source procedures, so the
    #: messages differed by their byte counts (138,369 against 139,695) whatever the name did:
    #: comparing whole messages passed with the identifier collapsed, and the audit row claimed
    #: mutation killed. Third consecutive round carrying a false killed-by-its-own-test claim.
    template = dict(entries[0])
    template["name"] = "Y" * (MAX_SERVED_DOCUMENT_BYTES * 2)
    entries[:2] = [dict(template, id=f"{shared}-{index}") for index in range(2)]
    core.write_text(json.dumps(document), encoding="utf-8")

    app = create_app(
        config=token_config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=root, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app) as client:
        named: list[str] = []
        sizes: list[int] = []
        for index in range(2):
            response = client.get(f"/api/v1/content/procedure/{shared}-{index}")
            assert response.status_code == 503, (
                f"the document is under budget, so this asserts nothing: {response.status_code}"
            )
            message = response.json()["detail"]["message"]
            assert "document_too_large" in response.text, message
            #: The NAME, extracted, not the whole message. The message carries a byte count, so
            #: comparing messages compares the counts and never reaches the identifier.
            named.append(message.split("'")[1])
            sizes.append(len(response.content))
        assert sizes[0] == sizes[1], (
            f"the two documents differ in size ({sizes}), so a message comparison would pass on the"
            " byte count and this test would not reach the identifier"
        )
        assert named[0] != named[1], (
            f"two distinct authored documents are refused under one name: {named[0]}"
        )
        #: And BOUNDED. Distinctness alone left this line revertible to the raw identifier, which is
        #: distinct and unbounded: 982 tests stayed green with a content-sized id on an anonymous
        #: 503. The two assertions catch different mutations and neither implies the other.
        for name in named:
            assert len(name) <= MAX_CONTENT_STRING, f"{len(name)} characters named on a 503"


def test_the_withheld_collections_are_count_capped_and_report_an_honest_total(
    token_config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """The ninth surface: bounded per entry, uncapped in COUNT.

    Measured on a tree that loads clean and answers 200: 140 drills served a 17,014-byte manifest,
    already over this project's own 16 kB ceiling, and 560 served 64,675. The runtime path is worse
    than the content path, because a serve-time refusal carries a reason up to 256 characters rather
    than the 32-character load-time one, so the route grew over the container's life.

    The body ceiling cannot see this and was never going to: with ids bounded to 64 and load-time
    reasons at 32 characters, 140 uncapped entries are about 13 kB. That is this file's own lesson -
    a body ceiling and a count cap are different controls - applied to the two fields on the
    manifest that were the odd ones out while every sibling was already capped.
    """
    root = _hostile_content(tmp_path / "content", withhold_all=True)
    app = create_app(
        config=token_config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=root, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app) as client:
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
        #: The TOTAL's VALUE, against a count this test works out for itself. The first version of
        #: this assertion ended `or total > MAX_SERVED_WITHHELD`, which is the exact condition
        #: asserted four lines above, so the disjunction was unconditionally true and the equality
        #: branch was dead: replacing the total with `len(...) * 7 + 1000`, and with a hardcoded 26,
        #: both left the whole suite green. A binding test that binds less than it claims, on the
        #: line written to end that.
        #:
        #: A LITERAL, measured, with a range check either side of it so a content change gives a
        #: legible failure rather than a bare inequality. Every drill in this tree is authored with
        #: the `computed_from_params` sentinel, and 94 of the 140 have no generator that supplies
        #: the answer - the other 46 are drawn by renderers that do emit `expected_text` or
        #: `expected_value`, which is why the total is not the library size. Pinning the value is
        #: the only thing that kills a hardcoded total: a range alone admits any number over the
        #: cap, and 26 survived.
        authored = len(json.loads((root / "drills.json").read_text(encoding="utf-8"))["drills"])
        assert MAX_SERVED_WITHHELD < total <= authored, (
            f"{total} withheld against {authored} authored and a cap of {MAX_SERVED_WITHHELD}"
        )
        assert total == WITHHELD_ON_THE_HOSTILE_TREE, (
            f"the manifest reports {total} withheld where {WITHHELD_ON_THE_HOSTILE_TREE} is"
            " measured. If the library changed, update the figure and say so; if it did not, the"
            " total is no longer counting what it claims to count"
        )


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
        cue_ids: set[str] = set()
        revealed: set[str] = set()
        for _ in range(DRAWS):
            served = client.get("/api/v1/drill/next")
            assert served.status_code == 200, served.content[:200]
            body = served.json()
            drawn.add(body["item_id"])

            stimulus_bytes = _wire_bytes(body["stimulus"])
            envelope = _wire_bytes({k: v for k, v in body.items() if k != "stimulus"})
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
            if body["cue_id"]:
                cue_ids.add(body["cue_id"])
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
            #: LENGTH AND DISTINCTNESS, both. Each mutation is invisible to the other's test: a
            #: truncated id collides, which distinctness catches and a length check does not; a raw
            #: id is distinct but unbounded, which a length check catches and distinctness does
            #: not. Asserting one of the two leaves the line revertible to the other.
            if answered.status_code == 200:
                revealed_id = answered.json()["item_id"]
                assert len(revealed_id) <= MAX_CONTENT_STRING, len(revealed_id)
                revealed.add(revealed_id)
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
        #: DISTINCTNESS on every served identity, not only length. Each of these was a separate
        #: live instance of one fault: a shortened id that collides reads as an identifier no author
        #: wrote. `cue_id` in particular was named by this file's own comment as the field that
        #: "asserted nothing" once before, and it asserted nothing again - because the tree put the
        #: distinguishing part BEFORE the cap for that field while fixing it for the drill id.
        assert len(cue_ids) == len(drawn), (
            f"{len(drawn)} items drew {len(cue_ids)} distinct served cue ids: {sorted(cue_ids)[:3]}"
        )
        assert len(revealed) == len(drawn), (
            f"{len(drawn)} items revealed {len(revealed)} distinct item ids on the answer route"
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
    #: TWO names sharing a prefix past the cap. One long name proves the length bound and is blind
    #: to a collision: the census key survived truncation with 983 tests green, and its keys are a
    #: DICT, so two collapsing names merge their counts and under-report the very census the code
    #: says must not be under-reported.
    sibling_key = long_key + "-sibling"
    #: MORE distinct names than the census serves, so the count cap is load-bearing here too.
    for row in rows:
        params = row.setdefault("stimulus", {}).setdefault("params", {})
        params[long_key] = 1
        params[sibling_key] = 1
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
        #: DISTINCT as well as short. Two authored names sharing a prefix past the cap must remain
        #: two entries with two counts, or the census silently halves itself.
        beta_keys = [name for name in params if name.startswith("beta_KKK")]
        assert len(beta_keys) == 2, f"two authored names collapsed to {len(beta_keys)}: {beta_keys}"
        assert len(set(beta_keys)) == 2, beta_keys


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
