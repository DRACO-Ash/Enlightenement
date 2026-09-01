"""The drill loop: select, serve, score, and the two things that must never happen.

**The answer key must not cross the wire before the operator commits.** Asserted on the raw
response BODY rather than on a parsed object, because the body is what a browser receives and a
field added to a model would show up in the bytes whether or not anything parsed it.

**A submission must be idempotent.** A double-click, a retry or a resend must not move a rating
twice.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from enlightenment.content import ContentPackage
from enlightenment.generators import build_registry
from enlightenment.training import (
    DEMONSTRATION_OPERATOR,
    DrillError,
    DrillLoop,
    ProgressStore,
)

CONTENT = Path(__file__).resolve().parents[1] / "content"

#: What a single renderer may produce from a deliberately absurd content count. Far below the
#: service budget, because a renderer that needs megabytes for one panel is drawing something
#: nobody can read.
HOSTILE_PARAM_BUDGET = 2 * 1024 * 1024


@pytest.fixture(scope="module")
def package() -> ContentPackage:
    loaded = ContentPackage(CONTENT)
    loaded.load()
    return loaded


@pytest.fixture
def loop(package: ContentPackage, tmp_path: Path) -> DrillLoop:
    return DrillLoop(
        content=package,
        registry=build_registry(),
        progress=ProgressStore(tmp_path / "progress.json"),
    )


def test_a_served_drill_carries_no_answer_key(package: ContentPackage, loop: DrillLoop) -> None:
    """The production-format rule, asserted on the bytes.

    Every accept value, every partial value, every reject value and the explanation must be
    absent from the payload. A convenient combined endpoint is the easy way to defeat this, and
    this is the test that would catch it.
    """
    served = loop.serve(operator_id=DEMONSTRATION_OPERATOR)
    body = json.dumps(served.as_dict()).casefold()
    item = package.drill(served.item_id)
    assert item is not None

    for value in item.answer.accept:
        if value and value != "computed_from_params":
            assert value.casefold() not in body, value
    for partial in item.answer.partial:
        assert partial.value.casefold() not in body, partial.value
        if partial.note:
            assert partial.note.casefold() not in body
    for rejected in item.answer.reject:
        assert rejected.value.casefold() not in body, rejected.value
        if rejected.why_wrong:
            assert rejected.why_wrong.casefold() not in body
    if item.explain:
        assert item.explain.casefold() not in body
    assert "answer" not in served.as_dict()
    assert "explain" not in served.as_dict()


def test_a_served_drill_carries_no_derived_value_for_a_computed_item(
    package: ContentPackage, loop: DrillLoop
) -> None:
    """A numeric item's expected value is computed server-side and must stay there.

    In the browser it IS the answer, and the sentinel `computed_from_params` exists precisely so
    the number is not written into content where a client could read it.
    """
    numeric = [d for d in package.drills if "computed_from_params" in d.answer.accept]
    assert numeric, "no computed item in the library, so this test asserts nothing"
    served = loop.serve(operator_id=DEMONSTRATION_OPERATOR)
    payload = served.as_dict()
    for stimulus in payload["stimulus"]:
        assert "derived" not in stimulus
        assert "expected_value" not in json.dumps(stimulus)


def test_the_reveal_carries_everything_the_service_withheld(loop: DrillLoop) -> None:
    """The other half of the rule: after submission, nothing is held back."""
    served = loop.serve(operator_id=DEMONSTRATION_OPERATOR)
    result = loop.score(
        run_id=served.run_id,
        response="manoeuvre",
        confidence=4,
        operator_id=DEMONSTRATION_OPERATOR,
    )
    payload = result.as_dict()
    assert "score_components" in payload
    assert "matched" in payload
    assert payload["content_hash"] == served.content_hash


def test_a_second_submission_returns_the_first_result_rather_than_rescoring(
    loop: DrillLoop,
) -> None:
    """Idempotent on the run id, so a double-click cannot move a rating twice."""
    served = loop.serve(operator_id=DEMONSTRATION_OPERATOR)
    first = loop.score(
        run_id=served.run_id,
        response="manoeuvre",
        confidence=5,
        operator_id=DEMONSTRATION_OPERATOR,
    )
    second = loop.score(
        run_id=served.run_id,
        response="something completely different",
        confidence=1,
        operator_id=DEMONSTRATION_OPERATOR,
    )
    assert second.as_dict() == first.as_dict()


def test_an_unknown_run_id_is_refused(loop: DrillLoop) -> None:
    """A submission against a run nobody served is not scorable and must not be invented."""
    with pytest.raises(DrillError, match="unknown or has expired"):
        loop.score(
            run_id="not-a-run",
            response="manoeuvre",
            confidence=3,
            operator_id=DEMONSTRATION_OPERATOR,
        )


def test_a_scored_run_records_the_content_hash_it_was_scored_under(
    package: ContentPackage, loop: DrillLoop, tmp_path: Path
) -> None:
    """Otherwise a result from last week cannot be interpreted against content that has changed."""
    served = loop.serve(operator_id=DEMONSTRATION_OPERATOR)
    loop.score(
        run_id=served.run_id,
        response="manoeuvre",
        confidence=3,
        operator_id=DEMONSTRATION_OPERATOR,
    )
    stored = ProgressStore(tmp_path / "progress.json").load(DEMONSTRATION_OPERATOR)
    assert stored.runs
    assert stored.runs[-1].content_hash == package.content_hash


def test_the_same_operator_and_item_draw_the_same_stimulus_until_they_answer(
    loop: DrillLoop,
) -> None:
    """The seed is a function of the content, the operator, the item and the attempt number.

    So a page reload before answering shows the same picture, and the attempt AFTER answering
    shows a different one. Recognition is not retrieval: an operator who has seen this exact
    surface before is not being tested on the cue.
    """
    first = loop.serve(operator_id=DEMONSTRATION_OPERATOR)
    again = loop.serve(operator_id=DEMONSTRATION_OPERATOR)
    assert again.item_id == first.item_id
    assert again.seed == first.seed

    loop.score(
        run_id=first.run_id,
        response="manoeuvre",
        confidence=3,
        operator_id=DEMONSTRATION_OPERATOR,
    )
    after = loop.serve(operator_id=DEMONSTRATION_OPERATOR)
    if after.item_id == first.item_id:
        assert after.seed != first.seed


def test_two_operators_on_one_item_get_different_stimuli(loop: DrillLoop) -> None:
    """Hashed rather than combined arithmetically, so adjacent operators do not correlate."""
    a = loop.serve(operator_id="operator-a")
    b = loop.serve(operator_id="operator-b")
    if a.item_id == b.item_id:
        assert a.seed != b.seed


def test_selection_targets_the_band_just_above_the_operator(
    package: ContentPackage, loop: DrillLoop, tmp_path: Path
) -> None:
    """The item that teaches sits at the edge of what the operator can already do.

    One they answer without thinking produces a correct response and no learning, so the target
    is above the rating rather than at it.
    """
    store = ProgressStore(tmp_path / "progress.json")
    progress = store.load(DEMONSTRATION_OPERATOR)
    progress.rating = 1000
    store.save(progress)
    chosen = loop.select(store.load(DEMONSTRATION_OPERATOR))
    assert chosen.elo >= 1000, chosen.elo
    assert chosen.elo <= 1400, chosen.elo


def test_selection_prefers_a_due_item_over_a_better_matched_one(
    package: ContentPackage, loop: DrillLoop, tmp_path: Path
) -> None:
    """Spacing wins. An item at its due date is the one the memory system needs served."""
    store = ProgressStore(tmp_path / "progress.json")
    progress = store.load(DEMONSTRATION_OPERATOR)
    progress.rating = 2000
    far_from_rating = min(package.drills, key=lambda d: d.elo)
    for drill in package.drills:
        progress.cue(drill.id).due_at = "2999-01-01T00:00:00+00:00"
    progress.cue(far_from_rating.id).due_at = "2000-01-01T00:00:00+00:00"
    store.save(progress)
    assert loop.select(store.load(DEMONSTRATION_OPERATOR)).id == far_from_rating.id


def test_the_dashboard_never_reports_a_bare_competency_estimate(loop: DrillLoop) -> None:
    """The interval is part of the value.

    A figure with no interval invites a claim the data cannot support, and this is the number a
    supervisor would read. "Not measured" and "measured at zero" are also rendered as different
    statements, because they are.
    """
    served = loop.serve(operator_id=DEMONSTRATION_OPERATOR)
    loop.score(
        run_id=served.run_id,
        response="manoeuvre",
        confidence=3,
        operator_id=DEMONSTRATION_OPERATOR,
    )
    dashboard = loop.dashboard(operator_id=DEMONSTRATION_OPERATOR)
    assert dashboard["competencies"]
    for competency in dashboard["competencies"]:
        assert "measured" in competency
        if competency["measured"]:
            assert competency["interval"] is not None
            assert competency["estimate"] is not None
        else:
            assert competency["estimate"] is None


def test_the_dashboard_says_identity_does_not_exist_yet(loop: DrillLoop) -> None:
    """A screen that recorded personal performance without saying so would be the DPIA problem."""
    dashboard = loop.dashboard(operator_id=DEMONSTRATION_OPERATOR)
    assert "synthetic" in dashboard["identity"].casefold()


def test_an_unloaded_package_refuses_to_serve_rather_than_inventing_an_item(
    tmp_path: Path,
) -> None:
    """No content, no drill. Inventing one would teach whatever the engine happened to draw."""
    empty = ContentPackage(tmp_path / "nothing")
    empty.load()
    loop = DrillLoop(
        content=empty,
        registry=build_registry(),
        progress=ProgressStore(tmp_path / "progress.json"),
    )
    assert loop.ready is False
    with pytest.raises(DrillError, match="not loaded"):
        loop.serve(operator_id=DEMONSTRATION_OPERATOR)


def test_the_manifest_reports_what_is_loaded_and_what_is_not_wired(loop: DrillLoop) -> None:
    """Provenance and honesty in one place: the hash, the counts, and the unwired rules."""
    manifest = loop.manifest()
    assert manifest["ok"] is True
    assert len(manifest["content_hash"]) == 64
    assert manifest["counts"]["drills"] == 140
    assert manifest["scored_scenarios_ready"] is False
    assert len(manifest["generators"]) == 10
    assert "D-CORRECT" in manifest["rubric_rules_implemented"]


def test_an_unscorable_item_does_not_move_a_rating_or_the_schedule(
    package: ContentPackage, loop: DrillLoop, tmp_path: Path
) -> None:
    """**Nobody is marked against a question the service could not mark.**

    `computed_from_params` is the content's sentinel for a numeric answer the generator must
    compute. The matcher refuses when no value was supplied, which is right; the loop then scored
    the refusal as WRONG - rating down six, cue schedule reset as a miss, a run row appended.
    Marking an operator against nothing is worse than not serving the item, and it was invisible:
    they saw a note and a rating move with no way to tell which caused which.
    """
    numeric = [d for d in package.drills if "computed_from_params" in d.answer.accept]
    assert numeric, "no computed item in the library, so this test asserts nothing"

    store = ProgressStore(tmp_path / "progress.json")
    before = store.load("operator-unscorable")
    before.rating = 1400
    store.save(before)

    #: Drive the item directly, because selection is due-and-rating driven and may not reach it.
    served = loop.serve(operator_id="operator-unscorable", item_id=numeric[0].id)

    #: Every computed item in the library now resolves a value, which is the OTHER half of this
    #: repair and means the end-to-end path no longer reaches the refusal on its own. The branch
    #: still has to be exercised, so the derived facts are emptied here: that is exactly the
    #: state a generator which supplied nothing would leave, and it is how the item behaved on
    #: every attempt before the values were wired.
    loop.pending[served.run_id].derived.clear()

    result = loop.score(
        run_id=served.run_id,
        response="7",
        confidence=4,
        operator_id="operator-unscorable",
    )
    payload = result.as_dict()
    assert payload["matched"] == "unscorable"
    assert payload["rating_delta"] is None
    assert payload["rating_before"] is None
    after = store.load("operator-unscorable")
    assert after.rating == 1400, "an unscorable item moved the rating"
    assert after.runs == [], "an unscorable item wrote a history row"
    assert after.cue(numeric[0].id).streak == 0


def test_the_speed_bonus_is_decided_by_the_server_clock_not_the_client_s(
    package: ContentPackage, loop: DrillLoop
) -> None:
    """A score derived from a value the client asserts is a client-side control.

    `elapsed_ms` arrives in the submission body, and a client posting zero collected
    `D-FAST-AND-CORRECT` on every item however long it had actually been sitting there.
    `served_at` was recorded server-side at service and then read nowhere.

    Driven honestly: the run is aged past its own time target using the server's timestamp, and
    the submission then LIES about it. The bonus must not be awarded.
    """
    from datetime import timedelta

    item = next(d for d in package.drills if "manoeuvre" in d.answer.accept)
    fast = loop.serve(operator_id="operator-fast", item_id=item.id)
    quick = loop.score(
        run_id=fast.run_id,
        response="manoeuvre",
        confidence=4,
        operator_id="operator-fast",
    )
    assert quick.correct, "the fixture answer no longer matches, so this test asserts nothing"
    assert "D-FAST-AND-CORRECT" in {c["rule_id"] for c in quick.as_dict()["score_components"]}

    slow = loop.serve(operator_id="operator-slow", item_id=item.id)
    held = loop.pending[slow.run_id]
    held.served_at = held.served_at - timedelta(seconds=item.time_target_s + 120)
    #: Every claim a client can make, not just zero. The first repair took `min(measured,
    #: claimed)`, which closed 0 and negatives and left everything else open: `elapsed_ms: 1` on
    #: a run the server had watched for 21.5 seconds still collected the bonus over the real
    #: route. A concession on a value the client controls is the same hole with a nicer reason.
    for claimed in (0, 1, 500, -4000):
        replayed = loop.serve(operator_id=f"operator-slow-{claimed}", item_id=item.id)
        held_again = loop.pending[replayed.run_id]
        held_again.served_at = held_again.served_at - timedelta(seconds=item.time_target_s + 120)
        lied = loop.score(
            run_id=replayed.run_id,
            response="manoeuvre",
            confidence=4,
            operator_id=f"operator-slow-{claimed}",
        )
        assert lied.correct
        fired = {c["rule_id"] for c in lied.as_dict()["score_components"]}
        assert "D-FAST-AND-CORRECT" not in fired, (
            f"a claim of {claimed} ms bought the speed bonus on a run the server timed at"
            f" more than {item.time_target_s} seconds"
        )
    del slow, held


def test_the_served_drill_map_is_bounded_by_count(loop: DrillLoop) -> None:
    """An unauthenticated route that inserts an entry per call and never removes one is a memory
    exhaustion surface. 4000 serves retained 4000 entries; nothing evicted, nothing expired, and
    the error message advertised an expiry that did not exist."""
    from enlightenment.training.drill import MAX_PENDING

    for _ in range(MAX_PENDING + 40):
        loop.serve(operator_id=DEMONSTRATION_OPERATOR)
    assert len(loop.pending) <= MAX_PENDING


def test_an_expired_run_is_refused_with_the_message_that_promises_it(loop: DrillLoop) -> None:
    """The message said "unknown or has expired" while nothing ever expired. Now it is true."""
    from datetime import timedelta

    from enlightenment.training.drill import PENDING_TTL_SECONDS

    served = loop.serve(operator_id=DEMONSTRATION_OPERATOR)
    aged = loop.pending[served.run_id]
    aged.served_at = aged.served_at - timedelta(seconds=PENDING_TTL_SECONDS + 60)
    loop.serve(operator_id="operator-b")  # any serve runs the eviction pass
    with pytest.raises(DrillError, match="unknown or has expired"):
        loop.score(
            run_id=served.run_id,
            response="manoeuvre",
            confidence=3,
            operator_id=DEMONSTRATION_OPERATOR,
        )


def test_the_manifest_discloses_what_is_not_wired(loop: DrillLoop) -> None:
    """Two counts that were honest everywhere except the product.

    61 of 67 rubric rules have no predicate, and 129 of 140 stimuli carry authored parameters no
    renderer reads. Both were stated in the commit, the changelog and three docstrings, and
    neither reached a surface a supervisor could look at.
    """
    manifest = loop.manifest()
    assert manifest["rubric_rules_unwired"] > 0
    unread = manifest["stimulus_params_unread"]
    assert unread["drills_total"] == 140
    assert 0 < unread["drills_fully_expressed"] <= unread["drills_total"]
    assert unread["params"], "the unread census names nothing, so it proves nothing"


def test_a_content_supplied_version_is_length_capped_before_it_is_stored(
    package: ContentPackage, loop: DrillLoop, tmp_path: Path
) -> None:
    """The register claimed this and cited a test about ROW COUNT, which is a different bound.

    `extra="allow"` is the deliberate reversal that lets the package load unedited, and its
    residual is length: a 5,000-character `version` was stored verbatim on every run row, in a
    file read whole on every request. Deleting the cap left the whole suite green, so the row
    named a control nothing checked - the same fault corrected on the frozen-model row.
    """
    from enlightenment.training.drill import MAX_ITEM_VERSION, _bounded

    assert len(_bounded("v" * 5000)) == MAX_ITEM_VERSION
    assert _bounded("2.10.0") == "2.10.0"
    assert _bounded(None) == ""

    served = loop.serve(operator_id="operator-version")
    loop.score(
        run_id=served.run_id,
        response="manoeuvre",
        confidence=3,
        operator_id="operator-version",
    )
    stored = ProgressStore(tmp_path / "progress.json").load("operator-version")
    assert stored.runs
    assert len(stored.runs[-1].item_version) <= MAX_ITEM_VERSION


def test_an_unknown_item_id_is_refused_rather_than_substituted(loop: DrillLoop) -> None:
    """`serve(item_id=...)` bypasses selection, so it must not quietly serve something else."""
    with pytest.raises(DrillError, match="no drill"):
        loop.serve(operator_id=DEMONSTRATION_OPERATOR, item_id="DRL-9999")


def test_the_reveal_names_the_aggregation_the_evaluator_does_not_apply(loop: DrillLoop) -> None:
    """Disclosure that reaches an actual response body, not a method nothing calls."""
    served = loop.serve(operator_id="operator-aggregation")
    result = loop.score(
        run_id=served.run_id,
        response="manoeuvre",
        confidence=4,
        operator_id="operator-aggregation",
    )
    assert "calibration_weight" in result.as_dict()["unimplemented_aggregation"]


def test_every_served_stimulus_stays_inside_a_stated_payload_budget(
    package: ContentPackage, loop: DrillLoop
) -> None:
    """A content-supplied count reaching an unauthenticated route needs a bound, and had none.

    `obs_count: 18000` was briefly read as a headcount: 18,000 tracks, 2.6 million points and
    159 MB of JSON from one anonymous GET, which is a larger availability surface than the
    unbounded pending map closed in the same commit. Asserted over the WHOLE library rather than
    a sample, because the fault was in one item nobody had rendered.
    """
    from enlightenment.training.drill import MAX_PAYLOAD_BYTES

    oversized: list[str] = []
    for drill in package.drills:
        served = loop.serve(operator_id=DEMONSTRATION_OPERATOR, item_id=drill.id)
        size = len(json.dumps(served.as_dict()))
        if size > MAX_PAYLOAD_BYTES:
            oversized.append(f"{drill.id}: {size:,} bytes")
    assert not oversized, oversized


def test_a_stimulus_over_the_budget_is_refused_rather_than_served(
    package: ContentPackage, loop: DrillLoop, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The budget was DECLARED as a runtime bound and referenced only by a test.

    So it held for the library as it stands and for nothing else - and `CONTENT_DIR` is a
    supported operator knob whose tree that test never runs. A control that exists only in the
    suite is a control the deployment does not have.
    """
    monkeypatch.setattr("enlightenment.training.drill.MAX_PAYLOAD_BYTES", 512)
    with pytest.raises(DrillError, match="byte budget"):
        loop.serve(operator_id=DEMONSTRATION_OPERATOR, item_id=package.drills[0].id)


def test_a_hostile_content_count_cannot_make_a_large_payload(loop: DrillLoop) -> None:
    """Nine parameters other than `headcount` produced 8 MB to 146 MB payloads, and three did not
    finish rendering at all - a cost a byte budget cannot see, because it is spent before there
    are any bytes to measure. Each count is now bounded at the renderer that consumes it."""
    from enlightenment.generators import build_registry, compose

    registry = build_registry()
    hostile = (
        ("light_curve", {"intervals": 20_000}),
        ("gabbard", {"fragments": 500_000}),
        ("neighbourhood", {"rows": 200_000}),
        ("coco", {"rows": 200_000}),
        ("pass_schedule", {"hours": 100_000}),
        ("pass_schedule", {"sensors": 20_000}),
        ("tric", {"state_change_markers": 200_000}),
        ("tric", {"revolutions": 100_000}),
        ("residual", {"days": 100_000}),
        ("waterfall", {"cycles_shown": 100_000}),
        ("waterfall", {"headcount": 200_000}),
        ("ephemeris", {"elapsed_min": 1_000_000}),
    )
    for name, params in hostile:
        body = json.dumps(compose(registry, name, params, 7)[0].for_client())
        assert len(body) < HOSTILE_PARAM_BUDGET, f"{name} {params}: {len(body):,} bytes"


def test_an_item_that_cannot_resolve_its_answer_is_not_served_twice_in_a_row(
    loop: DrillLoop, tmp_path: Path
) -> None:
    """An unscorable item became an ABSORBING STATE that ended the operator's session.

    Refusing to score it was right and was not enough. `select` is a pure function of due-state
    and rating, and the unscored path records no run and advances no schedule, so the same item
    was chosen on every turn: measured on the real package at rating 1340, six consecutive serves
    returned DRL-0008, six unscorable results, no rating movement. The penalty that behaviour
    replaced cost six rating points; this cost the whole sitting.

    A "does not move the rating" assertion is exactly what let it through, so this asserts
    PROGRESS: serve, score, serve again, and the second item must differ.
    """
    store = ProgressStore(tmp_path / "progress.json")
    progress = store.load("operator-absorbing")
    progress.rating = 1340
    store.save(progress)

    served: list[str] = []
    for _ in range(4):
        drill = loop.serve(operator_id="operator-absorbing")
        served.append(drill.item_id)
        loop.score(
            run_id=drill.run_id,
            response="manoeuvre",
            confidence=3,
            operator_id="operator-absorbing",
        )
    assert len(set(served)) > 1, f"the loop served the same item every turn: {served}"
    assert store.load("operator-absorbing").runs, "no attempt was recorded, so nothing advances"


def test_the_withheld_items_are_named_rather_than_silently_dropped(loop: DrillLoop) -> None:
    """Excluding an item from selection hides a content gap unless the exclusion is disclosed."""
    manifest = loop.manifest()
    withheld = manifest["items_without_a_resolvable_answer"]
    assert isinstance(withheld, list)
    #: One today: DRL-0008, whose manoeuvre count is not readable off the relative-motion track.
    #: If this grows, a renderer has stopped answering an item it used to answer.
    assert withheld == ["DRL-0008"], withheld


def test_two_products_on_one_board_cannot_both_supply_the_answer(
    package: ContentPackage, tmp_path: Path
) -> None:
    """A composite merges its renderers' server-side facts, so draw order could pick the answer.

    Deleting this guard left the whole suite green, which is the reason for the test rather than
    a footnote to it: it is a fail-closed control on answer integrity and CLAUDE.md's rule is
    that a control nothing verifies is a failed control.
    """
    from enlightenment.content import Drill
    from enlightenment.generators import GeneratorRegistry
    from enlightenment.generators.base import Axis, Marks, Panel, Stimulus

    class _Twin:
        """Two of these on one board both claim to have computed the answer."""

        def __init__(self, product_id: str) -> None:
            self.product_id = product_id
            self.name = product_id
            self.reads: frozenset[str] = frozenset()

        def render(self, params: dict[str, Any], seed: int) -> Stimulus:
            del params
            return Stimulus(
                product_id=self.product_id,
                generator=self.name,
                title=self.product_id,
                panels=(
                    Panel("p", Axis("x"), Axis("y"), marks=(Marks("m", "track", (0.0,), (0.0,)),)),
                ),
                derived={"expected_value": float(seed % 7)},
            )

    registry = GeneratorRegistry()
    registry.register(_Twin("PRD-ONE"))
    registry.register(_Twin("PRD-TWO"))

    clash = Drill(
        id="DRL-CLASH",
        stimulus={
            "product_id": "PRD-ONE",
            "generator": "composite",
            "params": {"products": ["PRD-ONE", "PRD-TWO"]},
        },
        prompt="Both products computed this. Which one wins?",
        response_format="numeric_estimate",
        answer={"accept": ["computed_from_params"], "tolerance": {"absolute": 0}},
    )
    package_with_clash = ContentPackage(CONTENT)
    package_with_clash.load()
    package_with_clash.drills = (*package_with_clash.drills, clash)
    #: The id index is built at load and does not follow an append, so it is set here too.
    #: Worth knowing rather than working around silently: `drills` is public and mutable while
    #: the index behind `drill()` is private, so the two can disagree. Nothing in production
    #: mutates `drills`, which is why this is a note and not a change.
    package_with_clash._by_id[clash.id] = clash

    loop = DrillLoop(
        content=package_with_clash,
        registry=registry,
        progress=ProgressStore(tmp_path / "progress.json"),
    )
    with pytest.raises(DrillError, match="depend on render order"):
        loop.serve(operator_id=DEMONSTRATION_OPERATOR, item_id="DRL-CLASH")


#: Content values that make a renderer's arithmetic fail. Every one is a plain number a content
#: author could type: NaN survives `json.loads` by default, and `elapsed_min: 0` is an integer.
HOSTILE_NUMBERS: tuple[tuple[str, str, object], ...] = (
    ("DRL-0030", "days", float("nan")),
    ("DRL-0030", "headcount", float("nan")),
    ("DRL-0008", "revolutions", float("nan")),
    ("DRL-0008", "separation_km", float("nan")),
)


def test_a_renderer_arithmetic_fault_never_stops_the_container_starting(tmp_path: Path) -> None:
    """The load-time answer probe raised out of `create_app`, so the worker never booted.

    `_items_without_a_resolvable_answer` renders every sentinel drill at construction, and it
    guarded only `LookupError`. A single NaN in a content parameter raised `ValueError: cannot
    convert float NaN to integer` straight out of the probe; `asgi.py` calls `create_app()` at
    import, so the result is a crash loop with no health path to screenshot. Four of five probe
    cases did it, one commit after the loader's decode faults were closed for the same reason.
    """
    import os
    from http import HTTPStatus
    from unittest import mock

    from fastapi.testclient import TestClient

    from enlightenment.app import create_app

    for index, (drill_id, key, value) in enumerate(HOSTILE_NUMBERS):
        root = tmp_path / f"content-{index}"
        shutil.copytree(CONTENT, root)
        document = json.loads((root / "drills.json").read_text(encoding="utf-8"))
        rows = document["drills"] if isinstance(document, dict) else document
        for row in rows:
            if row["id"] == drill_id:
                row.setdefault("stimulus", {}).setdefault("params", {})[key] = value
        (root / "drills.json").write_text(json.dumps(document), encoding="utf-8")

        with mock.patch.dict(os.environ, {"CONTENT_DIR": str(root)}):
            client = TestClient(create_app())
        assert client.get("/healthz").status_code == HTTPStatus.OK, (drill_id, key)
        assert client.get("/livez").status_code == HTTPStatus.OK, (drill_id, key)


def test_a_renderer_arithmetic_fault_is_an_author_facing_503_not_a_500(
    package: ContentPackage, tmp_path: Path
) -> None:
    """`serve` caught only `LookupError`, so `elapsed_min: 0` became a generic 500.

    A renderer dividing by a content value is a CONTENT fault and earns the 503 that names the
    item, which is what this module documents. Driven directly, because selection never reaches
    the ephemeris item.
    """
    from enlightenment.generators import build_registry

    for value in (0, 1e308):
        root = tmp_path / f"eph-{value}"
        shutil.copytree(CONTENT, root)
        document = json.loads((root / "drills.json").read_text(encoding="utf-8"))
        rows = document["drills"] if isinstance(document, dict) else document
        target = ""
        for row in rows:
            if (row.get("stimulus") or {}).get("generator") == "ephemeris":
                row["stimulus"].setdefault("params", {})["elapsed_min"] = value
                target = target or row["id"]
        (root / "drills.json").write_text(json.dumps(document), encoding="utf-8")
        assert target, "no ephemeris item in the library, so this test asserts nothing"

        broken = ContentPackage(root)
        broken.load()
        loop = DrillLoop(
            content=broken,
            registry=build_registry(),
            progress=ProgressStore(tmp_path / f"p-{value}.json"),
        )
        with pytest.raises(DrillError):
            loop.serve(operator_id=DEMONSTRATION_OPERATOR, item_id=target)
