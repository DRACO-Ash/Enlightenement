"""Elo, calibration and spacing: the eight controls the retired suite held.

These assertions existed in `tests/test_training.py` and went out with it in the V0.24.0 rewrite,
even though `training/scoring.py` itself survived. The module then sat at 87% coverage with ZERO
tests naming any of its symbols: incidental execution through the drill loop, not assertion. Two
mutations proved the gap - the rating clamp reduced to `round(value)` and the Brier score reduced
to an absolute difference - and the full suite passed with both applied.

`tests/test_progress.py` was written for exactly this reason, for `progress.py`. This is the
other half, and the general rule the two of them exist to enforce: **deleting a suite for a
module that still exists takes its controls with it**, and coverage will not tell you, because
coverage counts lines executed rather than claims proved.
"""

from __future__ import annotations

import pytest

from enlightenment.training.scoring import (
    CONFIDENCE_STEPS,
    ITEM_K,
    MAX_RATING,
    MIN_RATING,
    OPERATOR_K,
    SPACING_DAYS,
    brier_score,
    calibration_verdict,
    confidence_probability,
    expected_score,
    next_interval_days,
    update_ratings,
)


def test_two_equally_rated_players_expect_a_draw() -> None:
    """The anchor of the whole rating system. If this is wrong, every exchange is wrong."""
    assert expected_score(1500, 1500) == pytest.approx(0.5)
    assert expected_score(2000, 1200) > 0.9
    assert expected_score(1200, 2000) < 0.1


def test_the_exchange_is_symmetric_so_ratings_are_not_created_or_destroyed() -> None:
    """What the operator gains on an item, the item loses, scaled by the two K factors.

    Without this an operator's rating drifts upward simply by answering, which makes the number
    meaningless as a measure of anything.
    """
    change = update_ratings(operator_rating=1500, item_difficulty=1500, correct=True)
    operator_gain = change.operator_after - change.operator_before
    item_loss = change.item_before - change.item_after
    assert operator_gain > 0
    assert item_loss > 0
    assert operator_gain / OPERATOR_K == pytest.approx(item_loss / ITEM_K, abs=0.05)


def test_a_rating_cannot_leave_the_band_however_long_the_streak() -> None:
    """The band is what stops a rating becoming a number nobody can interpret.

    Two hundred consecutive right answers must not produce a four-figure rating that means
    nothing, and two hundred wrong ones must not produce a negative one.

    Driven with the item difficulty tracking the operator, which is BOTH the realistic case - the
    selector targets the band just above the rating - and the only case that reaches the bound. An
    earlier version of this test drove 200 wins against the easiest item in the library and passed
    against a mutant with the clamp removed, because the Elo gain against an item you are certain
    to beat converges to zero: the rating never approached the ceiling, so the ceiling was never
    tested. A bound test has to push at the bound.
    """
    rating = 2000
    for _ in range(200):
        rating = update_ratings(
            operator_rating=rating, item_difficulty=rating, correct=True
        ).operator_after
    assert rating <= MAX_RATING, rating

    rating = 1000
    for _ in range(200):
        rating = update_ratings(
            operator_rating=rating, item_difficulty=rating, correct=False
        ).operator_after
    assert rating >= MIN_RATING, rating


def test_a_wrong_answer_lowers_the_operator_and_raises_the_item() -> None:
    """The direction, asserted separately from the size, because a sign error is silent."""
    change = update_ratings(operator_rating=1500, item_difficulty=1500, correct=False)
    assert change.operator_after < change.operator_before
    assert change.item_after > change.item_before


def test_an_off_scale_confidence_is_refused_rather_than_coerced() -> None:
    """Five steps, and a sixth is a caller fault rather than a value to round into range.

    Coercing it would record a confidence the operator never expressed and then score their
    calibration against it, which is worse than an error.
    """
    for step in sorted(CONFIDENCE_STEPS):
        assert 0.0 < confidence_probability(step) < 1.0
    for bad in (0, 6, -1, 99):
        with pytest.raises(ValueError, match="confidence"):
            confidence_probability(bad)


def test_no_confidence_step_asserts_certainty() -> None:
    """Nothing on a five-point scale is 0 or 1.

    A Brier score punishes a stated certainty that turns out wrong with the maximum penalty
    available, and no operator on a real watch is ever entitled to that step.
    """
    for probability in CONFIDENCE_STEPS.values():
        assert 0.0 < probability < 1.0


def test_the_brier_score_punishes_a_confident_error_quadratically() -> None:
    """A PROPER scoring rule, which is the entire reason for choosing Brier over an error rate.

    Quadratic means the honest answer is your true belief: overstating confidence costs more than
    the accuracy it buys. An absolute difference would be linear and would not, so this asserts
    the curve rather than only the ordering.
    """
    confident_wrong = brier_score(0.93, correct=False)
    unsure_wrong = brier_score(0.55, correct=False)
    confident_right = brier_score(0.93, correct=True)
    assert confident_wrong > unsure_wrong > confident_right
    #: The signature of the square. Under an absolute difference this ratio is 1.7, not 2.9.
    assert confident_wrong / unsure_wrong > 2.0


def test_the_calibration_verdict_names_the_costly_case_in_words() -> None:
    """ "Confident and wrong" is the failure this product exists to remove, so it is said."""
    assert "wrong" in calibration_verdict(0.93, correct=False)
    assert "costliest" in calibration_verdict(0.93, correct=False)
    assert "target" in calibration_verdict(0.93, correct=True)


def test_a_miss_returns_the_cue_to_the_front_of_the_spacing_ladder() -> None:
    """Not a reduced interval. A miss means the operator does not have it yet."""
    assert next_interval_days(streak=6, correct=False) == SPACING_DAYS[0]
    assert next_interval_days(streak=0, correct=True) == SPACING_DAYS[0]
    assert next_interval_days(streak=3, correct=True) == SPACING_DAYS[3]


def test_the_spacing_ladder_only_ever_grows_and_is_bounded() -> None:
    """An interval that shrank with a longer streak would re-teach what is already known."""
    assert list(SPACING_DAYS) == sorted(SPACING_DAYS)
    assert next_interval_days(streak=999, correct=True) == SPACING_DAYS[-1]
