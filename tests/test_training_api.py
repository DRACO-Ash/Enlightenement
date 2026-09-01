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
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import ok_probe
from enlightenment.app import Limiters, TrainingPaths, create_app
from enlightenment.config import Config
from enlightenment.content import ContentPackage
from enlightenment.ratelimit import RateLimiter
from enlightenment.storage import TrainingStore
from enlightenment.training.drill import MAX_WITHHOLD_REASON

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
    assert "releasePlotRefits" in script, "a redraw discards the frame and keeps its observer"
    assert ".disconnect()" in script, "the observers are tracked and never released"
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
