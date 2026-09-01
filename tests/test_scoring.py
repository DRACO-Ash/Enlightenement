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
    FULL_CREDIT,
    MAX_ANSWER_LENGTH,
    Facts,
    RubricEvaluator,
    match,
    match_derived_text,
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


def test_partial_credit_scales_the_rule_award_by_the_item_s_own_fraction(
    package: ContentPackage,
) -> None:
    """The composition is engine policy, and an untested constant is a constant nobody owns.

    `FULL_CREDIT` was introduced to replace a hardcoded `0.5` that silently equalled the rule's
    own award, which was the finding. Naming it was half the repair: its VALUE was asserted
    nowhere, so changing 1.0 to 0.25 left the entire suite green and quadrupled every partial
    award. A named constant with no test is a magic number with a better name.
    """
    rubric = package.rubric("RUB-DRILL")
    assert rubric is not None
    rule = next(r for r in rubric.rules if r.id == "D-PARTIAL")
    evaluation = RubricEvaluator().evaluate(
        rubric, Facts(matched="partial", correct=False, partial_credit=0.4)
    )
    award = next(a for a in evaluation.awards if a.rule_id == "D-PARTIAL")
    assert award.award == pytest.approx(rule.award * 0.4 / FULL_CREDIT)
    assert award.award == pytest.approx(0.2), "a half-credit answer no longer earns half the award"


def test_the_speed_cap_in_the_content_actually_caps(package: ContentPackage) -> None:
    """Asserted against a rubric whose cap BITES, because the shipped one cannot.

    `RUB-DRILL` sets `speed_factor.max_bonus` to 0.25 and gives `D-FAST-AND-CORRECT` an award and
    a `cap` of 0.25 as well, so reading the content's cap changes nothing there: the branch was
    written, and proved nothing on the real library. A test that only exercises the no-op case
    reports the feature works when it has never once been the binding constraint.
    """
    generous = Rubric(
        id="RUB-SPEED",
        rules=(
            {
                "id": "D-FAST-AND-CORRECT",
                "when": "prose",
                "award": 2.0,
                "competency_id": "CMP-02",
            },
        ),
        aggregation={"method": "weighted_sum", "speed_factor": {"enabled": True, "max_bonus": 0.5}},
    )
    fast = Facts(matched="accept", correct=True, elapsed_ms=500, time_target_s=30)
    evaluation = RubricEvaluator().evaluate(generous, fast)
    assert evaluation.total == pytest.approx(0.5), (
        "the content's max_bonus did not cap a rule award above it, so the aggregation block is"
        " still being ignored"
    )


def test_a_declared_aggregation_this_evaluator_does_not_apply_is_named(
    package: ContentPackage,
) -> None:
    """The other half of failing closed: silently ignoring a content instruction reads exactly
    like honouring it. `RUB-DRILL` weights a Brier score at 0.3 and states no formula for folding
    it into a points total, so the weight is reported rather than invented."""
    rubric = package.rubric("RUB-DRILL")
    assert rubric is not None
    evaluation = RubricEvaluator().evaluate(rubric, Facts(matched="accept", correct=True))
    assert "calibration_weight" in evaluation.unimplemented_aggregation


def test_a_derived_answer_token_is_matched_whole_and_never_as_a_pattern() -> None:
    """Three ways this matcher could give away an item, all closed.

    A bare string `expected_text` was iterated CHARACTER BY CHARACTER - `tuple("east")` is
    `('e','a','s','t')` - so typing one letter scored full credit. Both generators emit tuples
    today, which made it latent rather than live, and a plain string is the natural thing for the
    next generator author to write.

    The token is escaped before it reaches a regex, so a token containing a metacharacter is
    INERT rather than wild: `.*` matches nothing, because normalisation strips the punctuation
    from the operator's side too. Inert is the safe direction - a wild token would accept every
    answer - and the escape is what makes it inert rather than universal.

    A token matches the START of a word, so "drifting eastwards" is accepted - it is a fully
    correct prose answer that a strict word boundary rejected - while "southwest" is not accepted
    for "west", because the token must begin the word rather than appear anywhere in it.
    """
    assert match_derived_text("e", {"expected_text": "east"}).matched == "none"
    assert match_derived_text("drifting east", {"expected_text": "east"}).matched == "accept"
    assert match_derived_text("anything at all", {"expected_text": (".*",)}).matched == "none"
    assert match_derived_text("eastwards", {"expected_text": ("east",)}).matched == "accept"
    assert match_derived_text("southwest", {"expected_text": ("west",)}).matched == "none"
    assert match_derived_text("west", {}).matched == "unscorable"


def test_a_numeric_answer_scores_its_magnitude_and_its_direction_separately(
    package: ContentPackage,
) -> None:
    """DRL-0004: "estimate the resulting longitude drift rate ... and state the direction".

    The generator's expected value is SIGNED, negative for a westward drift, so an operator
    answering "0.12 deg/day west" was marked wrong for omitting a minus sign the prompt never
    asked for - while the direction word the prompt did ask for was not scored at all. Before the
    value was wired this item refused harmlessly; wiring it turned a harmless refusal into an
    active penalty on the correct answer.
    """
    from enlightenment.generators import build_registry, compose

    drill = package.drill("DRL-0004")
    assert drill is not None
    derived: dict[str, object] = {}
    for stimulus in compose(
        build_registry(),
        drill.stimulus.generator,
        drill.stimulus.params,
        20260901,
        drill.stimulus.product_id,
    ):
        derived.update(stimulus.derived)
    expected = derived["expected_value"]
    assert isinstance(expected, float)
    assert expected < 0, "this item's expected rate is no longer signed, so it proves nothing"

    signed = match(f"{expected:.3f} deg/day west", drill.answer, drill.response_format, derived)
    unsigned = match(
        f"{abs(expected):.3f} deg/day west", drill.answer, drill.response_format, derived
    )
    silent = match(f"{abs(expected):.3f} deg/day", drill.answer, drill.response_format, derived)
    wrong_rate = match("5 deg/day west", drill.answer, drill.response_format, derived)

    assert signed.matched == "accept"
    assert unsigned.matched == "accept", "a correct unsigned magnitude is still marked wrong"
    assert silent.matched == "partial", "the direction the prompt asks for is not scored"
    assert 0 < silent.credit < 1
    assert wrong_rate.matched == "none"


def test_a_computed_item_still_awards_the_credit_its_content_authors(
    package: ContentPackage,
) -> None:
    """Driven through `match()` on the REAL content, because the register cited a token test.

    DRL-0030's key is the computed sentinel and its content also authors one partial answer worth
    half credit, with a note explaining where the direction comes from, plus two rejects with
    teaching text. The matcher that scores a computed answer consulted none of them, so the
    partly-correct operator scored zero and both authored explanations were replaced by a generic
    string. Deleting that block leaves the whole suite green unless this test exists.
    """
    from enlightenment.generators import build_registry, compose

    drill = package.drill("DRL-0030")
    assert drill is not None
    assert drill.answer.partial, "this item no longer authors a partial answer"
    assert drill.answer.reject, "this item no longer authors a rejected answer"

    derived: dict[str, object] = {}
    for stimulus in compose(
        build_registry(),
        drill.stimulus.generator,
        drill.stimulus.params,
        20260901,
        drill.stimulus.product_id,
    ):
        derived.update(stimulus.derived)

    authored_partial = drill.answer.partial[0]
    scored = match(authored_partial.value, drill.answer, drill.response_format, derived)
    assert scored.matched == "partial"
    assert scored.credit == pytest.approx(authored_partial.credit)
    assert scored.note == authored_partial.note, "the authored note was replaced"

    for rejected in drill.answer.reject:
        outcome = match(rejected.value, drill.answer, drill.response_format, derived)
        assert outcome.matched == "reject", rejected.value
        assert outcome.why_wrong == rejected.why_wrong, "the authored reason was replaced"

    #: And the direction still scores, so honouring the authored lists did not shadow it.
    direction = derived["expected_text"]
    assert isinstance(direction, tuple)
    right = match(f"it is drifting {direction[0]}", drill.answer, drill.response_format, derived)
    assert right.matched == "accept"


def test_a_direction_answer_is_refused_when_it_names_more_than_one_or_denies_one() -> None:
    """The contradiction check, which was wrong in BOTH directions before this.

    It refused correct answers: any "no", "not", "never" or "neither" anywhere in the response
    triggered it, so "drifting east, no doubt about it", "east, definitely not stationary" and
    "0.279 deg/day west, no reversal in the trend" all lost credit for a correct reading. And it
    missed the denials it existed for: "it doesn't drift east", "cannot be east" and "east is
    wrong" all scored full credit.

    Now two rules. Naming a direction that was not drawn is exact and sound. Denying the drawn one
    is scoped to a short window BEFORE the direction, which is what stops it firing on a negation
    about something else.

    **The residual is named rather than claimed closed** - see the group D cases, which still
    score. Open-ended denial is a semantics problem, and two attempts at widening this check each
    created a worse fault than the one they closed. Over-refusing a correct reading is the more
    expensive error, so the check stays narrow and this test records what it does not catch.
    """
    drawn = {"expected_text": ("east",)}

    # A. Correct readings, including ones carrying an unrelated negation.
    for right in (
        "east",
        "drifting east",
        "drifting eastwards",
        "eastern drift",
        "drifting east, no doubt about it",
        "east, definitely not stationary",
        "east neither fast nor slow",
        "drifting east and the rate is not constant",
        "the object is drifting east rather than holding station",
    ):
        assert match_derived_text(right, drawn).matched == "accept", right

    # B. Denials of the drawn direction, and answers naming another one.
    for wrong in (
        "not east",
        "definitely not east",
        "isnt drifting east",
        #: The apostrophe form. `normalise` strips punctuation to a space, so this arrived as
        #: "isn t drifting east" and matched no negation at all - while the docstring claimed it
        #: was caught, and the entry in NEGATIONS it relied on was reachable only if the operator
        #: happened to omit the apostrophe.
        "isn't drifting east",
        "aren't drifting east",
        "no east",
        "east or west",
        "it is drifting west, not east",
        "southwest",
        "west",
        "eastwest",
        "eastasdfgh",
        "e",
    ):
        assert match_derived_text(wrong, drawn).matched != "accept", wrong

    # C. Token spelling and compounds must not refuse a correct answer.
    assert match_derived_text("drifting east", {"expected_text": ("eastward",)}).matched == "accept"
    assert match_derived_text("north-east", {"expected_text": ("northeast",)}).matched == "accept"
    assert match_derived_text("northeast", {"expected_text": ("northeast",)}).matched == "accept"
    assert match_derived_text("south", {"expected_text": ("northeast",)}).matched != "accept"

    # D. THE RECORDED GAP. These are denials the scoped rule does not catch, and they score.
    #    Listed so the limit is visible and a future widening starts from the truth.
    for uncaught in ("it doesnt drift east", "cannot be east", "east is wrong", "hardly east"):
        assert match_derived_text(uncaught, drawn).matched == "accept", (
            f"{uncaught!r} is now refused, which is an improvement - move it into group B and"
            " delete it from this list"
        )

    # E. OVER-REFUSALS, the fault group D's narrowness was supposed to prevent and did not.
    #    A window of "up to two words" is wide enough to jump a clause: in "not station-keeping,
    #    drifting east" the denial is about station-keeping and the direction is the answer, and
    #    all six of these were refused. The window is now ADJACENCY across a closed vocabulary of
    #    motion words, so a denial has to be a denial OF THE DIRECTION to count as one.
    for right in (
        "not station-keeping, drifting east at 0.279 deg/day",
        "no doubt drifting east",
        "not stationary, east",
        "rather than holding, east",
        "instead of holding, east",
        "no manoeuvre, east drift",
        "not in the box any more, east",
        "the rate is not what was reported, drifting east",
    ):
        assert match_derived_text(right, drawn).matched == "accept", right

    # F. A SPACED compound is the compound. "north-east" was accepted and "north east" refused,
    #    from the same operator reading the same plot, because closing hyphens was the whole of
    #    the compound handling and a space is the commoner spelling of the two.
    compound = {"expected_text": ("northeast",)}
    for right in ("north east", "drifting north east", "north eastwards", "northeast"):
        assert match_derived_text(right, compound).matched == "accept", right
    #: Folding must not invent a compound that was not typed. THESE ARE THE CASES THAT REACH THE
    #: GUARD: "north west" and "south east" do not - both fold, because "northwest" and "southeast"
    #: are real compounds, and both are then refused by the names-another-direction rule. The guard
    #: only ever fires on a pair that forms NO compound, and deleting it gave "east west east" full
    #: credit for an eastward drift while this test stayed green.
    for wrong in ("east west east", "east west, definitely east", "north south east"):
        assert match_derived_text(wrong, drawn).matched != "accept", wrong
    #: And the pairs that DO fold, refused by the other rule, so the two paths stay distinguishable.
    for wrong in ("north west", "south east"):
        assert match_derived_text(wrong, compound).matched != "accept", wrong


def test_a_derived_direction_token_is_never_compiled_as_a_pattern() -> None:
    """`re.escape` on the drawn token, held before a generator ever derives it from content.

    The contradiction check interpolates the drawn direction into a regex. Today `expected_text` is
    only ever one of the four literals at `products.py:886` and `:1310`, so nothing content-shaped
    reaches the pattern and deleting the escape leaves the suite green - which the security gate
    found and reported as unheld rather than as exploitable. Both readings are right, and the guard
    is the cheaper of the two things to keep.

    The failure it prevents is not subtle: a token containing a metacharacter either raises
    `re.error` inside scoring, which fails an operator's submission on content they cannot see, or
    silently matches something the plot never drew. This asserts both halves - no exception, and
    the bracket is treated as text rather than as a character class.
    """
    #: A token no generator produces today. That is the point: the guard exists for the day one
    #: does, and the sibling test at `test_a_derived_answer_token_is_matched_whole_and_never_as_a_
    #: pattern` holds the same property for the positive match.
    hostile = {"expected_text": ("east[a-z",)}
    #: No `re.error`. Refused, because the response does not name the literal token that was drawn.
    assert match_derived_text("east", hostile).matched != "accept"
    #: And the class is not honoured: with the escape removed, `east[a-z` compiles to "east"
    #: followed by one letter, so "eastx" would read as a denial-free correct answer.
    assert match_derived_text("eastx", hostile).matched != "accept"
    #: The escape is on the DENIAL path, so drive that too: a denial of the hostile token must not
    #: raise on its way to a verdict.
    assert match_derived_text("not east[a-z", hostile).matched != "accept"


def test_an_unrelated_negation_does_not_cost_a_correct_numeric_answer(
    package: ContentPackage,
) -> None:
    """The same fault through the magnitude-and-direction path, on real content.

    DRL-0004 asks for a rate and a direction. "0.279 deg/day west, no reversal in the trend" is a
    complete correct answer and was scored `partial 0.5` with a note telling the operator to state
    the direction they had just stated.
    """
    from enlightenment.generators import build_registry, compose

    drill = package.drill("DRL-0004")
    assert drill is not None
    derived: dict[str, object] = {}
    for stimulus in compose(
        build_registry(),
        drill.stimulus.generator,
        drill.stimulus.params,
        20260901,
        drill.stimulus.product_id,
    ):
        derived.update(stimulus.derived)
    expected = derived["expected_value"]
    assert isinstance(expected, float)

    for answer in (
        f"{abs(expected):.3f} deg/day west",
        f"{abs(expected):.3f} deg/day west, no reversal in the trend",
        f"{abs(expected):.3f} deg/day west, definitely not station-keeping",
    ):
        assert match(answer, drill.answer, drill.response_format, derived).matched == "accept", (
            answer
        )
