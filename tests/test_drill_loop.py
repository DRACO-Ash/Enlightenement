"""The drill loop: select, serve, score, and the two things that must never happen.

**The answer key must not cross the wire before the operator commits.** Asserted on the raw
response BODY rather than on a parsed object, because the body is what a browser receives and a
field added to a model would show up in the bytes whether or not anything parsed it.

**A submission must be idempotent.** A double-click, a retry or a resend must not move a rating
twice.
"""

from __future__ import annotations

import json
from pathlib import Path

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
        elapsed_ms=5000,
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
        elapsed_ms=1000,
        operator_id=DEMONSTRATION_OPERATOR,
    )
    second = loop.score(
        run_id=served.run_id,
        response="something completely different",
        confidence=1,
        elapsed_ms=90_000,
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
            elapsed_ms=1000,
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
        elapsed_ms=4000,
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
        elapsed_ms=1000,
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
        elapsed_ms=3000,
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
    result = loop.score(
        run_id=served.run_id,
        response="7",
        confidence=4,
        elapsed_ms=3000,
        operator_id="operator-unscorable",
    )
    payload = result.as_dict()
    if payload["matched"] != "unscorable":
        pytest.skip("this item resolved a value, so there is no refusal to assert on")

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
        elapsed_ms=800,
        operator_id="operator-fast",
    )
    assert quick.correct, "the fixture answer no longer matches, so this test asserts nothing"
    assert "D-FAST-AND-CORRECT" in {c["rule_id"] for c in quick.as_dict()["score_components"]}

    slow = loop.serve(operator_id="operator-slow", item_id=item.id)
    held = loop.pending[slow.run_id]
    held.served_at = held.served_at - timedelta(seconds=item.time_target_s + 120)
    lied = loop.score(
        run_id=slow.run_id,
        response="manoeuvre",
        confidence=4,
        elapsed_ms=0,
        operator_id="operator-slow",
    )
    assert lied.correct
    fired = {c["rule_id"] for c in lied.as_dict()["score_components"]}
    assert "D-FAST-AND-CORRECT" not in fired, "the client's own timer decided the bonus"


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
            elapsed_ms=1000,
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
