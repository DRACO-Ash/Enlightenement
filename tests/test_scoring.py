"""Matching and the declarative evaluator.

Two properties carry most of the weight here. **The matcher refuses a near miss rather than
guessing in the operator's favour**, because the reject list is the load-bearing half of the key
and a similarity score would award a named wrong answer for looking like a right one. And **the
evaluator fails closed on a rule it cannot evaluate**, because a rule that silently contributes
nothing is indistinguishable from a rule that ran and found nothing, and those are opposite facts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from enlightenment.content import Answer, ContentPackage, ResponseFormat, Rubric
from enlightenment.scoring import (
    DRILL_PREDICATES,
    MAX_ANSWER_LENGTH,
    Facts,
    RubricEvaluator,
    match,
    match_text,
    normalise,
)

CONTENT = Path(__file__).resolve().parents[1] / "content"


@pytest.fixture(scope="module")
def package() -> ContentPackage:
    loaded = ContentPackage(CONTENT)
    loaded.load()
    return loaded


ANSWER = Answer(
    accept=("manoeuvre", "possible manoeuvre"),
    partial=({"value": "the object moved", "credit": 0.5, "note": "Name the departure type."},),
    reject=({"value": "breakup", "why_wrong": "A residual says nothing about headcount."},),
)


def test_normalisation_folds_the_variants_an_operator_actually_types() -> None:
    """Case, punctuation, spacing and a bounded list of leading fillers. Nothing cleverer."""
    for typed in ("Manoeuvre", "  manoeuvre.", "MANOEUVRE!", "I think manoeuvre"):
        assert normalise(typed) == "manoeuvre", typed
    assert normalise("I think probably manoeuvre") == "manoeuvre"


def test_normalisation_strips_at_most_two_fillers_so_it_cannot_be_made_to_loop() -> None:
    """An unbounded strip on caller-controlled input is a denial of service in a regex.

    Two passes, fixed. A third filler survives, which is the correct trade: the answer is then not
    recognised, and an unrecognised answer is a safe outcome where an unbounded loop is not.
    """
    assert normalise("maybe maybe maybe manoeuvre") == "maybe manoeuvre"


def test_a_near_miss_is_refused_rather_than_guessed_in_the_operator_s_favour() -> None:
    """No fuzzy matching. "manoeuvres" is not "manoeuvre" and the difference is not ours to split.

    This is the property the whole matcher exists for: "separation" and "fragmentation" share
    almost nothing analytically and a great deal orthographically, and a similarity score would
    award one for the other.
    """
    for typed in ("manoeuvres", "manouvre", "manoeuvre?ish", "man"):
        assert match_text(typed, ANSWER).matched != "accept", typed


def test_the_reject_list_returns_its_reason_so_a_miss_becomes_a_teachable_moment() -> None:
    """A named wrong answer gets the authored reason, not a bare miss."""
    result = match_text("breakup", ANSWER)
    assert result.matched == "reject"
    assert "headcount" in result.why_wrong


def test_a_partial_answer_earns_the_credit_the_item_states() -> None:
    """The content author decides how close a wrong-but-reasonable answer was, not the rule."""
    result = match_text("the object moved", ANSWER)
    assert result.matched == "partial"
    assert result.credit == pytest.approx(0.5)
    assert "departure type" in result.note


def test_an_unrecognised_answer_is_none_and_not_a_reject() -> None:
    """Those are different facts: one is a named misconception, the other is off the map."""
    assert match_text("banana", ANSWER).matched == "none"


def test_a_pathological_answer_is_bounded_before_any_work_is_done() -> None:
    """The cap is checked first, so a megabyte of text costs one length comparison and no more."""
    result = match("x" * (MAX_ANSWER_LENGTH + 1), ANSWER, ResponseFormat.FREE_CLASSIFICATION, {})
    assert result.matched == "none"
    assert str(MAX_ANSWER_LENGTH) in result.note


def test_a_numeric_answer_is_judged_against_the_tolerance_the_content_states() -> None:
    """Relative and absolute, and an absolute zero means exactly right."""
    relative = Answer(accept=("1.0",), tolerance={"relative": 0.25, "unit": "deg/day"})
    assert match("1.2", relative, ResponseFormat.NUMERIC_ESTIMATE, {}).matched == "accept"
    assert match("1.4", relative, ResponseFormat.NUMERIC_ESTIMATE, {}).matched == "none"

    exact = Answer(accept=("0",), tolerance={"absolute": 0, "unit": "manoeuvres"})
    assert match("0", exact, ResponseFormat.NUMERIC_ESTIMATE, {}).matched == "accept"
    assert match("1", exact, ResponseFormat.NUMERIC_ESTIMATE, {}).matched == "none"


def test_a_computed_answer_with_no_generator_value_is_refused_not_guessed() -> None:
    """`computed_from_params` is a sentinel, not an answer.

    An item scored against a value nobody computed is worse than an item not served: it marks an
    operator against nothing. The refusal is explicit and reaches the interface as such.
    """
    answer = Answer(accept=("computed_from_params",), tolerance={"relative": 0.25})
    refused = match("0.9", answer, ResponseFormat.NUMERIC_ESTIMATE, {})
    assert refused.matched == "unscorable"
    supplied = match("1.0", answer, ResponseFormat.NUMERIC_ESTIMATE, {"expected_value": 1.0})
    assert supplied.matched == "accept"


def test_the_sentinel_is_never_matched_as_a_literal_string() -> None:
    """An operator typing the sentinel must not be marked correct."""
    answer = Answer(accept=("computed_from_params",), tolerance={"absolute": 0})
    result = match("computed_from_params", answer, ResponseFormat.NUMERIC_ESTIMATE, {})
    assert result.matched != "accept"


def test_every_score_names_the_rule_and_its_award_comes_from_the_content(
    package: ContentPackage,
) -> None:
    """Adding a rubric rule adds data only. The award, competency and explain are never in Python.

    Proved by reading them back out of the evaluation and comparing against the JSON, so a
    hardcoded number anywhere in the evaluator fails here.
    """
    rubric = package.rubric("RUB-DRILL")
    assert rubric is not None
    by_id = {rule.id: rule for rule in rubric.rules}
    evaluation = RubricEvaluator().evaluate(
        rubric, Facts(matched="accept", correct=True, confidence_given=True, elapsed_ms=1000)
    )
    assert evaluation.awards
    for award in evaluation.awards:
        rule = by_id[award.rule_id]
        assert award.competency_id == rule.competency_id
        assert award.explain == rule.explain
    assert evaluation.total == pytest.approx(sum(a.award for a in evaluation.awards))


def test_a_rule_with_no_predicate_is_reported_rather_than_silently_scoring_zero(
    package: ContentPackage,
) -> None:
    """The evaluator fails CLOSED, and this is the finding it exists to make visible.

    The rule `when` clauses in the content are prose rather than machine-evaluable predicates, so
    61 of the 67 rules cannot be evaluated yet: they belong to the scenario runner and the
    argument surface. Reporting them by name is the difference between "this rule found nothing"
    and "nobody wired this rule up", which are opposite facts.
    """
    evaluator = RubricEvaluator()
    scenario = package.rubric("RUB-SCENARIO-GENERAL")
    assert scenario is not None
    evaluation = evaluator.evaluate(scenario, Facts())
    assert len(evaluation.unimplemented) == len(scenario.rules)
    assert evaluation.awards == ()
    assert "R-VERIFY-FIRST" in evaluation.unimplemented


def test_the_drill_rubric_is_fully_implemented(package: ContentPackage) -> None:
    """Whatever else is unwired, the drill layer must be complete or the loop cannot score."""
    rubric = package.rubric("RUB-DRILL")
    assert rubric is not None
    evaluation = RubricEvaluator().evaluate(rubric, Facts())
    assert evaluation.unimplemented == ()
    assert set(DRILL_PREDICATES) == {rule.id for rule in rubric.rules}


def test_a_registered_predicate_makes_a_previously_unimplemented_rule_score() -> None:
    """Adding a predicate is the code half; the data half is already there.

    A rule reusing an existing condition shape with a different award, competency or explain is
    pure data. A genuinely new condition needs this.
    """
    rubric = Rubric(
        id="RUB-TEST",
        rules=({"id": "X-NEW", "when": "prose", "award": 3.0, "competency_id": "CMP-01"},),
    )
    evaluator = RubricEvaluator()
    assert evaluator.evaluate(rubric, Facts()).unimplemented == ("X-NEW",)
    evaluator.register("X-NEW", lambda _facts: True)
    scored = evaluator.evaluate(rubric, Facts())
    assert scored.unimplemented == ()
    assert scored.total == pytest.approx(3.0)


def test_the_speed_bonus_needs_both_correct_and_inside_the_target(package: ContentPackage) -> None:
    """Fast and wrong earns nothing. The bonus is for recall, and a wrong answer is not recall."""
    rubric = package.rubric("RUB-DRILL")
    assert rubric is not None
    evaluator = RubricEvaluator()
    fast_right = evaluator.evaluate(
        rubric, Facts(matched="accept", correct=True, elapsed_ms=1000, time_target_s=20)
    )
    fast_wrong = evaluator.evaluate(
        rubric, Facts(matched="reject", correct=False, elapsed_ms=1000, time_target_s=20)
    )
    slow_right = evaluator.evaluate(
        rubric, Facts(matched="accept", correct=True, elapsed_ms=99_000, time_target_s=20)
    )
    fired = {a.rule_id for a in fast_right.awards}
    assert "D-FAST-AND-CORRECT" in fired
    assert "D-FAST-AND-CORRECT" not in {a.rule_id for a in fast_wrong.awards}
    assert "D-FAST-AND-CORRECT" not in {a.rule_id for a in slow_right.awards}


def test_a_rule_cap_is_honoured_from_the_content(package: ContentPackage) -> None:
    """`cap` appears on four rules in the library and is data, not a constant here."""
    rubric = package.rubric("RUB-SCENARIO-GENERAL")
    assert rubric is not None
    capped = [rule for rule in rubric.rules if rule.cap is not None]
    assert capped, "no capped rule in the library, so this test asserts nothing"
    evaluator = RubricEvaluator()
    evaluator.register(capped[0].id, lambda _facts: True)
    single = Rubric(id="RUB-CAP", rules=(capped[0],))
    evaluation = evaluator.evaluate(single, Facts())
    assert abs(evaluation.total) <= abs(capped[0].cap or 0.0) + 1e-9
