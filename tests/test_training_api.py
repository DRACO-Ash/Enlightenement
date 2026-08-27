"""The training HTTP surface and the interface it serves.

The property this file exists for, above all others: **the answer key must not cross the wire
before the operator commits.** It is asserted on the raw response BODY rather than on a parsed
object, because the body is what a browser receives and a field added to a model would show up in
the bytes whether or not anything parsed it.

Second: the interface must stay air-gapped. The plan's posture is "no CDN, no map tiles, no
external calls at runtime", and that is checked by reading the shipped markup for an external
reference rather than by trusting the Content Security Policy alone. The policy is checked too;
two independent controls on one rule is the point.
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
from enlightenment.ratelimit import RateLimiter
from enlightenment.storage import TrainingStore

CONTENT_ROOT = Path(__file__).resolve().parents[1] / "content"
UI_ROOT = Path(__file__).resolve().parents[1] / "src" / "enlightenment" / "ui"


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


# --- the answer key stays server-side ----------------------------------------------------


def test_an_unanswered_drill_carries_no_answer_key_in_its_raw_body(client: TestClient) -> None:
    """Checked on the bytes, not on a parsed object.

    A future field named `accepted_classifications` or `expert_cue` on the served model would leak
    silently through any assertion that inspected only the keys it already knew about.
    """
    response = client.get("/api/v1/drill/next")
    assert response.status_code == 200
    body = response.text.lower()
    for forbidden in ("accepted_", "expert_cue", "confusable", "first_step", '"seed"'):
        assert forbidden not in body, f"{forbidden!r} reached an unanswered drill response"


def test_the_reveal_arrives_only_as_the_answer_response(client: TestClient) -> None:
    """The reveal is the reward for committing, which is what makes it production not
    recognition."""
    served = client.get("/api/v1/drill/next").json()
    reveal = client.post(
        "/api/v1/drill/answer",
        json={
            "item_id": served["item_id"],
            "classification": "deliberately wrong",
            "first_action": "deliberately wrong",
            "confidence": 2,
        },
    )
    assert reveal.status_code == 200
    payload = reveal.json()
    assert payload["accepted_classifications"], "the reveal withheld the answer key"
    assert payload["expert_cue"]
    assert payload["correct"] is False
    # Every point names its rule and its evidence: the plan's explainability acceptance test.
    assert payload["lines"]
    for line in payload["lines"]:
        assert line["rule"], "a score line has no rule name"
        assert line["axis"], "a score line names no competency axis"
        assert line["evidence"], "a score line awarded points with no evidence"


def test_a_drill_response_is_never_cached(client: TestClient) -> None:
    """A cached drill is the same instantiation twice, and a cached reveal is a stale answer."""
    assert client.get("/api/v1/drill/next").headers["cache-control"] == "no-store"
    assert client.get("/api/v1/dashboard").headers["cache-control"] == "no-store"


# --- boundary validation -----------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"item_id": "drill-station-keeping", "classification": "x", "first_action": "y"},
        {
            "item_id": "drill-station-keeping",
            "classification": "x",
            "first_action": "y",
            "confidence": 0,
        },
        {
            "item_id": "drill-station-keeping",
            "classification": "x",
            "first_action": "y",
            "confidence": 6,
        },
        {
            "item_id": "drill-station-keeping",
            "classification": "",
            "first_action": "y",
            "confidence": 3,
        },
        {
            "item_id": "Not A Slug",
            "classification": "x",
            "first_action": "y",
            "confidence": 3,
        },
        {
            "item_id": "drill-station-keeping",
            "classification": "x",
            "first_action": "y",
            "confidence": 3,
            "unexpected": "key",
        },
        {
            "item_id": "drill-station-keeping",
            "classification": "x" * 301,
            "first_action": "y",
            "confidence": 3,
        },
    ],
)
def test_a_malformed_answer_is_refused_at_the_boundary(
    client: TestClient, payload: dict[str, object]
) -> None:
    """`extra="forbid"` and every cap, exercised. An unknown key is a rejected request, never a
    silently coerced one."""
    assert client.post("/api/v1/drill/answer", json=payload).status_code == 422


def test_an_unknown_item_is_a_400_naming_the_problem_not_a_500(client: TestClient) -> None:
    response = client.post(
        "/api/v1/drill/answer",
        json={
            "item_id": "no-such-item",
            "classification": "x",
            "first_action": "y",
            "confidence": 3,
        },
    )
    assert response.status_code == 400
    assert "not loaded" in json.dumps(response.json())


def test_answering_is_strictly_rate_limited(
    config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """The plan asks for rate limiting on the scoring endpoint by name. Answering is a write: it
    moves a rating, schedules a cue and appends a run record."""
    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        limiters=Limiters(strict=RateLimiter(2, 60.0)),
        training=TrainingPaths(content_root=CONTENT_ROOT, progress_path=tmp_path / "progress.json"),
    )
    body = {
        "item_id": "drill-station-keeping",
        "classification": "station keeping",
        "first_action": "confirm in a second independent fit",
        "confidence": 3,
    }
    with TestClient(app) as client:
        codes = [client.post("/api/v1/drill/answer", json=body).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# --- content and library -----------------------------------------------------------------


def test_the_content_endpoint_states_its_own_provenance(client: TestClient) -> None:
    """The current content set is ILLUSTRATIVE and the interface has to be able to say so.

    A trainer that cannot tell an operator whether the procedure they just learned is authoritative
    is worse than no trainer, so this is asserted rather than left to a reviewer to notice.
    """
    payload = client.get("/api/v1/content").json()
    assert payload["ok"] is True, payload["errors"]
    assert payload["counts"]["procedures"] >= 3
    assert payload["counts"]["drills"] >= 3
    assert "ILLUSTRATIVE" in payload["content_provenance"]
    assert "not validated by a" in payload["content_provenance"]
    # And the identity gap is stated on the same payload the interface renders.
    assert payload["operator_id"] == "synthetic-operator"
    assert "DPIA" in payload["identity"]


def test_a_procedure_is_served_in_full_and_an_unknown_one_is_a_404(client: TestClient) -> None:
    listing = client.get("/api/v1/content").json()["procedures"]
    detail = client.get(f"/api/v1/library/{listing[0]['id']}").json()
    assert detail["steps"]
    assert detail["steps"][0]["ordinal"] == 1
    assert detail["purpose"]
    assert detail["closure_criteria"]
    assert client.get("/api/v1/library/no-such-procedure").status_code == 404


def test_the_library_never_holds_a_protected_object_identifier(client: TestClient) -> None:
    """The redaction discipline, checked at the EDGE as well as at load.

    The loader refuses a catalogue-number shape in an authored file. This asserts the same property
    on what actually reaches a browser, because that is the artefact whose exposure the rule is
    about: "ENLIGHTENMENT teaches that such a list exists and must be checked; it never holds the
    list."
    """
    catalogue = re.compile(r"(?<![0-9A-Za-z_-])(?<![0-9]\.)[0-9]{5,8}(?![0-9A-Za-z_-])(?!\.[0-9])")
    for procedure in client.get("/api/v1/content").json()["procedures"]:
        text = client.get(f"/api/v1/library/{procedure['id']}").text
        assert not catalogue.search(text), f"{procedure['id']} served a catalogue-number shape"


# --- the interface -----------------------------------------------------------------------


def test_the_interface_is_served_with_a_strict_policy(client: TestClient) -> None:
    response = client.get("/ui")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    policy = response.headers["content-security-policy"]
    # script-src must stay strict. 'unsafe-inline' is admitted for STYLE only, because the
    # stylesheet is inline in the document; admitting it for script would make the policy
    # decorative.
    assert "script-src 'self'" in policy
    assert "script-src 'self' 'unsafe-inline'" not in policy
    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert response.headers["referrer-policy"] == "no-referrer"


def test_the_interface_script_is_served_from_an_allowlist(client: TestClient) -> None:
    """A two-entry allowlist cannot be traversed. Every path-normalisation bug in this class comes
    from believing the check was right."""
    ok = client.get("/ui/app.js")
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("text/javascript")
    assert "script-src 'self'" in ok.headers["content-security-policy"]
    # `..` on its own is absent deliberately: the client normalises `/ui/..` to `/` before the
    # request leaves, so asserting on it would test the client's URL handling and not this route.
    # The encoded form IS included, because that one does arrive as a path segment.
    for hostile in ("index.html", "%2e%2e%2fapp.py", "app.js.map", "config.py", "APP.JS"):
        assert client.get(f"/ui/{hostile}").status_code in (404, 400), hostile


def test_the_interface_makes_no_external_request(client: TestClient) -> None:
    """The air-gap posture, read off the shipped assets rather than trusted to the policy.

    Two controls on one rule: the policy would block an external fetch at run time, and this fails
    the build if one is ever authored. A control that only exists in a header is a control one
    header edit away from gone.
    """
    for path in ("/ui", "/ui/app.js"):
        body = client.get(path).text
        for external in ("http://", "https://", "//cdn", "fonts.googleapis", "unpkg", "jsdelivr"):
            assert external not in body, f"{path} references {external!r}"


def test_the_interface_never_writes_an_untrusted_value_with_innerhtml() -> None:
    """Every value from the content tree is written with `textContent`.

    The content tree is edited without a code deployment, so an authoring mistake would otherwise
    become a scripting bug. Read from the source rather than exercised, because the property is
    "this construct does not appear" and no input can prove that.
    """
    script = (UI_ROOT / "app.js").read_text(encoding="utf-8")
    # An assignment, not the bare word: the file's own header explains the rule, and a grep that
    # fails on its own documentation gets deleted rather than obeyed.
    for sink in (
        r"\.innerHTML\s*=",
        r"\.outerHTML\s*=",
        r"insertAdjacentHTML\s*\(",
        r"document\.write\s*\(",
        # The two dynamic-code sinks. Strict script-src blocks an injected <script>; these would
        # execute a string without needing one.
        r"\beval\s*\(",
        r"new\s+Function\s*\(",
    ):
        assert not re.search(sink, script), f"app.js uses {sink!r}"


def test_the_interface_honours_the_measured_palette_rules() -> None:
    """The palette rules are CODE STANDARDS in this project, from measured contrast figures.

    Blue 1 `#385FAF` measures 2.45:1 on navy, failing the text floor AND the 3:1 graphic floor, so
    it is a structural fill and border colour only. `#C0504D` measures 3.21:1 and is retained only
    for large fills, with `#E06C69` used wherever alert carries text or a small mark. This is the
    grep gate the plan asks for.
    """
    markup = (UI_ROOT / "index.html").read_text(encoding="utf-8")
    script = (UI_ROOT / "app.js").read_text(encoding="utf-8")

    # Copper-amber is excluded from product UI by house rule.
    for banned in ("#C67C00", "#c67c00"):
        assert banned not in markup, f"{banned} is in the markup"
        assert banned not in script, f"{banned} is in the script"

    # Blue 1 may define a token and be used for fill, border and stroke. It must never be assigned
    # to `color`, and it must never be a canvas fillStyle for text.
    for line in markup.splitlines():
        stripped = line.strip()
        if "#385FAF" not in stripped.upper():
            continue
        assert not re.match(r"^\s*color\s*:", stripped), f"Blue 1 carries text: {stripped}"
    # In the canvas the rule is that the grid stroke may be Blue 1 while every fillText colour is
    # Blue 2 or brighter, which is what `PALETTE.axis` is for.
    assert "grid: '#385FAF'" in script
    assert "axis: '#739BCF'" in script
    assert re.search(r"fillStyle\s*=\s*PALETTE\.grid", script) is None


def test_the_interface_honours_reduced_motion_with_an_equivalent_rather_than_a_removal() -> None:
    """The reveal is where the product earns its "one more" feeling, so the non-motion path still
    has to MARK the moment rather than drop the signal."""
    markup = (UI_ROOT / "index.html").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in markup
    reduced = markup.split("prefers-reduced-motion", 1)[1].split("}", 3)[0]
    assert "animation: none" in reduced
    assert "border-left-width" in reduced, "the reduced-motion path removes the signal entirely"


def test_every_status_in_the_interface_carries_a_shape_and_a_label() -> None:
    """Red and green as the alert and nominal pair is the classic deuteranopia trap. A labelled
    triangle, not a red dot."""
    script = (UI_ROOT / "app.js").read_text(encoding="utf-8")
    assert "'▲'" in script, "the correct glyph is gone"
    assert "'▼'" in script, "the missed glyph is gone"
    assert "▲ correct" in script, "the dashboard outcome lost its glyph or its label"
    assert "▼ missed" in script, "the dashboard outcome lost its glyph or its label"


def test_the_dashboard_endpoint_reports_intervals_and_never_a_bare_axis_number(
    client: TestClient,
) -> None:
    payload = client.get("/api/v1/dashboard").json()
    assert payload["operator_id"] == "synthetic-operator"
    assert len(payload["axes"]) == 6
    for axis in payload["axes"]:
        assert "interval" in axis
        if axis["attempts"] == 0:
            assert axis["accuracy"] is None
            assert axis["interval"] is None


def test_a_broken_content_tree_is_a_503_naming_the_files_and_never_takes_health_down(
    config: Config, store: TrainingStore, tmp_path: Path
) -> None:
    """The container is fine and the content is not. Those are different incidents.

    A container that refuses to start over a content typo cannot serve the health paths that would
    tell an operator why, which is why the load failure is carried rather than raised.
    """
    broken = tmp_path / "content"
    (broken / "procedures").mkdir(parents=True)
    for kind in ("drills", "scenarios", "rubrics", "traces"):
        (broken / kind).mkdir(parents=True)
    (broken / "procedures" / "bad.json").write_text("{ not json", encoding="utf-8")

    app = create_app(
        config=config,
        store=store,
        probe=ok_probe,
        training=TrainingPaths(content_root=broken, progress_path=tmp_path / "progress.json"),
    )
    with TestClient(app) as client:
        # Health is untouched: this is the split the App Store contract depends on.
        for path in ("/", "/livez", "/ping", "/health", "/healthz", "/readyz"):
            assert client.get(path).status_code == 200, path
        drill = client.get("/api/v1/drill/next")
        assert drill.status_code == 503
        detail = drill.json()["detail"]
        assert detail["error"] in ("content_unavailable", "no_drill")
        assert client.get("/api/v1/content").json()["ok"] is False
