"""The training layer: answer matching, rating, calibration, spacing, progress, and the engine.

Written against the PROPERTIES the flight plan states, not against the current implementation's
shape. Two of them are the product itself and get the most attention here:

● The answer is never on screen, so answer matching has to accept what an examiner would accept
  and refuse what an examiner would refuse. The refusals matter more than the acceptances: a fuzzy
  match that let "not a manoeuvre" pass for "manoeuvre" would make the score a lie in exactly the
  discrimination the product trains.
● A miss resets the spacing interval to the front, because the plan re-injects a missed cue class
  and treating a miss as partial credit is how a gap survives a scheduler.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from enlightenment.content import ContentStore, DrillItem, PlotKind
from enlightenment.training import (
    CONFIDENCE_STEPS,
    DEFAULT_OPERATOR_RATING,
    DrillEngine,
    DrillError,
    ProgressStore,
    brier_score,
    calibration_verdict,
    confidence_probability,
    expected_score,
    explain_score,
    next_interval_days,
    update_ratings,
)
from enlightenment.training.answers import matches, near_miss, normalise
from enlightenment.training.plots import build_plot
from enlightenment.training.progress import (
    MAX_RUN_HISTORY,
    AxisProgress,
    CueSchedule,
    OperatorProgress,
    RunRecord,
)
from enlightenment.training.scoring import MAX_RATING, MIN_RATING, SPACING_DAYS

CONTENT_ROOT = Path(__file__).resolve().parents[1] / "content"

# --- answer matching: production, not recognition ----------------------------------------


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        ("Station Keeping", "station keeping"),
        ("  station-keeping  ", "station keeping"),
        ("stationkeeping", "station keeping"),
        ("it is a manoeuvre", "manoeuvre"),
        ("maneuver", "manoeuvre"),
        ("the data artifact", "data artefact"),
        ("looks like a drift-by", "drift by"),
    ],
)
def test_normalisation_folds_the_variants_an_operator_actually_types(
    typed: str, expected: str
) -> None:
    """Each case is a real way to type a right answer, and marking it wrong teaches the operator to
    fight the input box instead of learning the procedure."""
    assert normalise(typed) == expected


def test_matching_refuses_a_near_miss_rather_than_guessing_in_the_operator_s_favour() -> None:
    """The refusals are the load-bearing half.

    Every string below is a DIFFERENT answer from the key, and each is a discrimination the product
    exists to train. A fuzzy or substring match would accept them, the score would rise, and the
    operator would be told they knew something they did not.
    """
    key = ["manoeuvre", "controlled proximity operations"]
    for wrong in (
        "not a manoeuvre",
        "no manoeuvre",
        "possible manoeuvre or artefact",
        "uncontrolled proximity operations",
        "proximity",
        "",
        "   ",
    ):
        assert matches(wrong, key) is None, f"{wrong!r} was accepted for {key}"


def test_matching_returns_the_key_form_so_the_debrief_can_quote_the_expert() -> None:
    assert matches("STATIONKEEPING", ["station keeping", "manoeuvre"]) == "station keeping"


def test_a_named_look_alike_is_reported_so_a_miss_becomes_a_teachable_moment() -> None:
    """ "You called it a fragmentation, and the discriminator is the piece count" beats
    "incorrect"."""
    assert near_miss("Fragmentation", ["fragmentation", "breakup"]) == "fragmentation"
    assert near_miss("something else entirely", ["fragmentation"]) is None


def test_a_pathological_answer_is_bounded_before_any_work_is_done() -> None:
    """A 100k-character paste must cost a fixed amount, not a proportional one."""
    assert len(normalise("a" * 100_000)) <= 300


# --- rating, calibration, spacing ---------------------------------------------------------


def test_the_elo_exchange_is_symmetric_so_the_pool_cannot_inflate() -> None:
    """What the operator gains the item loses, in proportion to the two K factors.

    Asserted as a ratio rather than as two numbers, so the test survives a change to either K while
    still failing if the exchange stops being an exchange.
    """
    change = update_ratings(operator_rating=1200, item_difficulty=1200, correct=True)
    assert change.operator_delta > 0
    assert change.item_after < change.item_before
    assert change.operator_delta == pytest.approx(
        -4.0 * (change.item_after - change.item_before), abs=1.0
    )


def test_a_rating_cannot_leave_the_band_any_authored_item_can_match() -> None:
    """An unbounded rating puts an operator where no item exists, and the drill has nothing to
    serve."""
    high = update_ratings(operator_rating=MAX_RATING, item_difficulty=MIN_RATING, correct=True)
    low = update_ratings(operator_rating=MIN_RATING, item_difficulty=MAX_RATING, correct=False)
    assert high.operator_after <= MAX_RATING
    assert low.operator_after >= MIN_RATING


def test_the_expected_score_is_a_half_when_the_ratings_are_equal() -> None:
    assert expected_score(1500, 1500) == pytest.approx(0.5)
    assert expected_score(1900, 1500) > 0.9


def test_the_confidence_scale_refuses_an_off_scale_step_rather_than_clamping() -> None:
    """Clamping would score a client bug as a real answer, and confidence is the input to the
    calibration measure the plan puts second in its priority list."""
    for step in CONFIDENCE_STEPS:
        assert 0.0 < confidence_probability(step) < 1.0
    for bad in (0, 6, -1, 99):
        with pytest.raises(ValueError, match="not on the scale"):
            confidence_probability(bad)


def test_no_confidence_step_asserts_certainty() -> None:
    """A rule that can return an infinite penalty stops being readable, and an operator who is
    certain is not certain."""
    assert max(CONFIDENCE_STEPS.values()) < 1.0
    assert min(CONFIDENCE_STEPS.values()) > 0.0


def test_the_brier_score_punishes_confident_error_quadratically() -> None:
    """The whole point of a proper scoring rule: the penalty grows faster than the confidence."""
    assert brier_score(0.93, correct=True) < brier_score(0.55, correct=True)
    assert brier_score(0.93, correct=False) > brier_score(0.55, correct=False)
    assert brier_score(0.5, correct=True) == pytest.approx(0.25)


def test_the_calibration_verdict_names_the_failure_mode_the_product_exists_to_remove() -> None:
    assert "confident and wrong" in calibration_verdict(0.93, correct=False)
    assert "target" in calibration_verdict(0.93, correct=True)
    assert "honest" in calibration_verdict(0.15, correct=False)


def test_a_miss_returns_the_spacing_interval_to_the_front() -> None:
    """A miss means the operator does not have it yet. Partial credit for a miss is how a gap
    survives a scheduler."""
    assert next_interval_days(streak=0, correct=False) == SPACING_DAYS[0]
    assert next_interval_days(streak=6, correct=False) == SPACING_DAYS[0]
    assert next_interval_days(streak=1, correct=True) == SPACING_DAYS[1]
    # The tail is clamped rather than raising, so a long streak keeps the longest interval.
    assert next_interval_days(streak=99, correct=True) == SPACING_DAYS[-1]


def test_every_score_names_the_rule_and_the_evidence_and_the_lines_sum_to_the_total() -> None:
    """The plan's explainability requirement, asserted rather than described: "no scoring decision
    the debrief cannot explain"."""
    lines, total = explain_score(
        classification_match="station keeping",
        action_match="confirm in a second independent fit",
        confused_with=None,
        probability=0.93,
        expert_cue="the mean longitude does not move",
    )
    assert total == pytest.approx(sum(line.awarded for line in lines))
    assert total > 95.0
    assert {line.rule for line in lines} == {
        "event-named",
        "first-action-named",
        "confidence-calibrated",
        "expert-cue",
    }
    for line in lines:
        assert line.evidence.strip(), f"{line.rule} awarded points with no evidence"


def test_a_miss_that_names_the_look_alike_says_so_in_the_evidence() -> None:
    lines, total = explain_score(
        classification_match=None,
        action_match=None,
        confused_with="fragmentation",
        probability=0.93,
        expert_cue="the count stopped growing",
    )
    named = next(line for line in lines if line.rule == "event-named")
    assert "fragmentation" in named.evidence
    assert "look-alike" in named.evidence
    # Confidently wrong: the calibration line should award almost nothing.
    assert total < 5.0


# --- progress store ----------------------------------------------------------------------


def test_an_axis_with_no_attempts_reports_nothing_rather_than_zero() -> None:
    """ "Not measured" and "measured at zero" are different facts, and collapsing them is how a
    dashboard lies about coverage."""
    axis = AxisProgress()
    assert axis.accuracy is None
    assert axis.interval is None
    assert axis.mean_brier is None


def test_a_perfect_small_sample_still_reports_a_non_zero_interval() -> None:
    """A plain Wald interval on three out of three reports zero width, which is the most confident
    and least true thing this could say."""
    axis = AxisProgress(attempts=3, correct=3)
    interval = axis.interval
    assert interval is not None
    assert interval[1] - interval[0] > 0.05


def test_a_cue_with_no_recorded_due_date_is_due() -> None:
    """Never seen means due. The safe direction to fail for a value that only schedules."""
    now = datetime(2026, 8, 27, tzinfo=UTC)
    assert CueSchedule().is_due(now)
    assert CueSchedule(due_at="not a date at all").is_due(now)
    future = CueSchedule(due_at=(now + timedelta(days=3)).isoformat())
    assert not future.is_due(now)


def test_saving_one_operator_preserves_every_other_operator() -> None:
    """The anti-shrink rule for a store that is read whole and written whole."""
    with tempfile.TemporaryDirectory() as directory:
        store = ProgressStore(Path(directory) / "progress.json")
        first = OperatorProgress(operator_id="alpha", rating=1300)
        second = OperatorProgress(operator_id="beta", rating=1400)
        store.save(first)
        store.save(second)
        assert store.load("alpha").rating == 1300
        assert store.load("beta").rating == 1400


def test_the_progress_file_is_never_world_readable() -> None:
    """This is the file that will hold personal performance data."""
    if os.name == "nt":  # pragma: no cover - the suite's CI is Linux
        pytest.skip("Windows has no meaningful POSIX mode bits")
    previous = os.umask(0o000)
    try:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "progress.json"
            ProgressStore(path).save(OperatorProgress(operator_id="alpha"))
            assert path.stat().st_mode & 0o077 == 0, "progress is readable beyond its owner"
    finally:
        os.umask(previous)


@pytest.mark.parametrize(
    "content",
    ["", "not json at all", "[]", '{"alpha": "not a dict"}', '{"alpha": {"rating": "x"}}'],
)
def test_a_damaged_progress_file_degrades_to_defaults_rather_than_a_500(content: str) -> None:
    """One bad write must not take the training loop offline. Progress is valuable; it is not the
    loop."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "progress.json"
        path.write_text(content, encoding="utf-8")
        loaded = ProgressStore(path).load("alpha")
        assert loaded.operator_id == "alpha"
        assert loaded.rating == DEFAULT_OPERATOR_RATING


def test_a_missing_progress_file_is_not_an_error() -> None:
    with tempfile.TemporaryDirectory() as directory:
        loaded = ProgressStore(Path(directory) / "absent.json").load("alpha")
        assert loaded.rating == DEFAULT_OPERATOR_RATING


def test_run_history_is_capped_so_the_file_cannot_grow_without_limit() -> None:
    """The file is read whole on every request. The cap is an engineering bound and NOT the
    retention policy, which is still open with Ash as Data Protection Lead."""
    with tempfile.TemporaryDirectory() as directory:
        store = ProgressStore(Path(directory) / "progress.json")
        progress = OperatorProgress(operator_id="alpha")
        for index in range(MAX_RUN_HISTORY + 40):
            progress.runs.append(
                RunRecord(
                    item_id=f"item-{index}",
                    item_version="v1",
                    content_hash="",
                    procedure_id="p",
                    axis="cue-detection",
                    seed=index,
                    answered_at="2026-08-27T00:00:00+00:00",
                    classification="x",
                    first_action="y",
                    confidence=3,
                    correct=True,
                    action_correct=True,
                    brier=0.0,
                    points=1.0,
                    rating_before=1200,
                    rating_after=1200,
                )
            )
        store.save(progress)
        assert len(store.load("alpha").runs) == MAX_RUN_HISTORY


def test_a_run_row_of_an_unknown_shape_is_skipped_rather_than_fatal() -> None:
    """Losing one history row costs less than refusing to serve the dashboard."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "progress.json"
        path.write_text(
            json.dumps({"alpha": {"rating": 1250, "runs": [{"unknown_field": 1}]}}),
            encoding="utf-8",
        )
        loaded = ProgressStore(path).load("alpha")
        assert loaded.rating == 1250
        assert loaded.runs == []


# --- plots -------------------------------------------------------------------------------


def test_the_same_item_and_seed_draw_the_same_series_every_time() -> None:
    """The debrief redraws exactly what the operator saw from the stored seed. A surface nobody can
    regenerate makes a run uninterpretable later."""
    first = build_plot(
        item_id="drill-station-keeping",
        plot_kind=PlotKind.LONGITUDE_DRIFT,
        seed=42,
        description="d",
    )
    second = build_plot(
        item_id="drill-station-keeping",
        plot_kind=PlotKind.LONGITUDE_DRIFT,
        seed=42,
        description="d",
    )
    assert first.as_dict() == second.as_dict()


def test_a_different_seed_draws_a_different_instantiation() -> None:
    """An operator who has seen this item before still has to read THIS instantiation."""
    first = build_plot(
        item_id="drill-station-keeping", plot_kind=PlotKind.LONGITUDE_DRIFT, seed=1, description="d"
    )
    second = build_plot(
        item_id="drill-station-keeping", plot_kind=PlotKind.LONGITUDE_DRIFT, seed=2, description="d"
    )
    assert first.as_dict() != second.as_dict()


def test_the_bounded_relative_track_closes_and_the_unbounded_one_does_not() -> None:
    """The RPO discrimination, asserted on the DYNAMICS rather than on a drawn shape.

    The bounded item sets the along-track rate to the no-drift value, which closes the relative
    track; the drift-by item perturbs it, which opens it. If this ever stopped coming out of the
    Clohessy-Wiltshire solution, the drill would be teaching operators to recognise a picture
    somebody drew rather than a signature the orbit produces.
    """
    bounded = build_plot(
        item_id="drill-bounded-rpo", plot_kind=PlotKind.HILL_RELATIVE, seed=7, description="d"
    )
    drift = build_plot(
        item_id="drill-drift-by", plot_kind=PlotKind.HILL_RELATIVE, seed=7, description="d"
    )

    def along_track_span(plot: object) -> float:
        series = plot.series[0]  # type: ignore[attr-defined]
        return max(series.x) - min(series.x)

    # A closed loop stays within a few kilometres; an unbounded pass sweeps much further along
    # track over the same number of points.
    assert along_track_span(drift) > along_track_span(bounded) * 3.0


def test_every_plot_carries_a_text_equivalent() -> None:
    """A plot with no text equivalent fails the accessibility floor, and the floors are code
    standards in this project rather than polish."""
    for kind in PlotKind:
        plot = build_plot(
            item_id="drill-station-keeping", plot_kind=kind, seed=3, description="the description"
        )
        assert plot.description == "the description"
        assert plot.x_label
        assert plot.y_label
        assert plot.series
        assert all(len(s.x) == len(s.y) for s in plot.series)


# --- the engine --------------------------------------------------------------------------


@pytest.fixture
def engine(tmp_path: Path) -> DrillEngine:
    store = ContentStore(CONTENT_ROOT)
    result = store.reload()
    assert result.ok, f"the shipped content tree does not load: {result.errors[:5]}"
    return DrillEngine(content=store, progress=ProgressStore(tmp_path / "progress.json"))


def test_a_served_drill_carries_no_answer_key(engine: DrillEngine) -> None:
    """The product's central design choice, asserted on the SERIALISED payload rather than on the
    dataclass: the payload is what crosses the wire, and a field added to the model would show up
    here."""
    served = engine.serve(operator_id="alpha")
    payload = json.dumps(served.as_dict()).lower()
    for forbidden in ("accepted_", "expert_cue", "confusable", "seed"):
        assert forbidden not in payload, f"{forbidden!r} reached an unanswered drill payload"


def test_answering_correctly_raises_the_rating_and_records_the_run(engine: DrillEngine) -> None:
    served = engine.serve(operator_id="alpha")
    item = engine._items()[f"{served.item_id}@{served.item_version}"]
    assert isinstance(item, DrillItem)
    scored = engine.score(
        operator_id="alpha",
        item_id=served.item_id,
        classification=item.accepted_classifications[0],
        first_action=item.accepted_first_actions[0],
        confidence=4,
    )
    assert scored.correct
    assert scored.action_correct
    assert scored.rating_after > scored.rating_before
    assert scored.points > 90.0
    dashboard = engine.dashboard(operator_id="alpha")
    assert dashboard["runs_total"] == 1
    assert dashboard["rating"] == scored.rating_after


def test_a_scored_run_records_the_content_hash_it_was_scored_under(engine: DrillEngine) -> None:
    """ "Every run records the exact content version hash it was scored under", so a run whose
    content has since changed is still readable against what it actually faced."""
    served = engine.serve(operator_id="alpha")
    engine.score(
        operator_id="alpha",
        item_id=served.item_id,
        classification="something wrong",
        first_action="something wrong",
        confidence=1,
    )
    progress = engine._progress.load("alpha")
    assert progress.runs[-1].content_hash
    assert progress.runs[-1].item_version == served.item_version


def test_scoring_refuses_an_unknown_item_and_an_off_scale_confidence(engine: DrillEngine) -> None:
    with pytest.raises(DrillError, match="not loaded or is not active"):
        engine.score(
            operator_id="alpha",
            item_id="no-such-item",
            classification="x",
            first_action="y",
            confidence=3,
        )
    served = engine.serve(operator_id="alpha")
    with pytest.raises(DrillError, match="not on the scale"):
        engine.score(
            operator_id="alpha",
            item_id=served.item_id,
            classification="x",
            first_action="y",
            confidence=9,
        )


def test_selection_prefers_a_due_item_over_a_better_matched_one(engine: DrillEngine) -> None:
    """Spacing first, then Elo. The product is a memory system that happens to render orbits;
    matching difficulty keeps it playable, spacing is what makes it work."""
    progress = engine._progress.load("alpha")
    now = datetime.now(UTC)
    items = engine._items()
    ids = sorted(item.meta.id for item in items.values())
    # Everything scheduled far ahead except one, which is deliberately the WORST rating match.
    worst = max(items.values(), key=lambda item: abs(item.difficulty - progress.rating))
    for item_id in ids:
        progress.cue(item_id).due_at = (now + timedelta(days=30)).isoformat()
    progress.cue(worst.meta.id).due_at = (now - timedelta(days=1)).isoformat()
    engine._progress.save(progress)
    assert engine.select(engine._progress.load("alpha")).meta.id == worst.meta.id


def test_the_same_item_served_twice_is_a_different_instantiation(engine: DrillEngine) -> None:
    first = engine.serve(operator_id="alpha")
    engine.score(
        operator_id="alpha",
        item_id=first.item_id,
        classification="wrong",
        first_action="wrong",
        confidence=1,
    )
    # A miss puts it back at the front of the queue, so the same item returns with a new attempt
    # number and therefore a new seed.
    second = engine.serve(operator_id="alpha")
    if second.item_id == first.item_id:
        assert second.seed != first.seed
        assert second.instance_id != first.instance_id


def test_the_dashboard_reports_an_interval_on_every_measured_axis(engine: DrillEngine) -> None:
    served = engine.serve(operator_id="alpha")
    item = engine._items()[f"{served.item_id}@{served.item_version}"]
    engine.score(
        operator_id="alpha",
        item_id=served.item_id,
        classification=item.accepted_classifications[0],  # type: ignore[attr-defined]
        first_action="deliberately wrong",
        confidence=3,
    )
    dashboard = engine.dashboard(operator_id="alpha")
    measured = [axis for axis in dashboard["axes"] if axis["attempts"] > 0]
    assert measured, "no axis was credited by a scored answer"
    for axis in measured:
        assert axis["interval"] is not None, f"{axis['axis']} reports no interval"
        assert axis["interval"][0] <= axis["interval"][1]
    unmeasured = [axis for axis in dashboard["axes"] if axis["attempts"] == 0]
    for axis in unmeasured:
        assert axis["accuracy"] is None
        assert axis["interval"] is None


def test_an_empty_content_tree_refuses_to_serve_rather_than_inventing_an_item(
    tmp_path: Path,
) -> None:
    """No drill is a 503 with a reason, never a fabricated item."""
    empty = tmp_path / "content"
    for kind in ("procedures", "drills", "scenarios", "rubrics", "traces"):
        (empty / kind).mkdir(parents=True)
    store = ContentStore(empty)
    store.reload()
    engine = DrillEngine(content=store, progress=ProgressStore(tmp_path / "p.json"))
    with pytest.raises(DrillError, match="no active drill items"):
        engine.serve(operator_id="alpha")
