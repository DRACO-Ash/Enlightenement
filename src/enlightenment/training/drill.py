"""The drill loop over the real content package: select, serve, score.

Replaces the illustrative engine. The shape is the same because the shape was right; what changed
is that every item, key, prompt and explanation now comes from Ash's authored library rather than
from a placeholder, and every stimulus comes from a registered product renderer rather than from
one of three shaped series.

Two properties this module exists to hold, both easy to lose:

● **The served payload carries no answer.** Not the accept list, not the reject list, not the
  explanation, not the derived expected value for a numeric item. `ServedDrill.as_dict` is the
  only thing that crosses the wire and it is built by naming fields rather than by serialising an
  object, because a field added to a model would otherwise appear in the payload silently.
● **Submission is idempotent on the run id.** A second submission returns the first result rather
  than rescoring, so a double-click or a retry cannot move a rating twice.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any, Final

from enlightenment.audit import log_event
from enlightenment.content import ContentPackage, Drill
from enlightenment.generators import GeneratorRegistry, board_for, compose
from enlightenment.identifiers import MAX_CONTENT_STRING as _MAX_CONTENT_STRING
from enlightenment.identifiers import served_identifier
from enlightenment.scoring import (
    COMPUTED_SENTINEL,
    UNSCORABLE,
    Facts,
    Match,
    RubricEvaluator,
    match,
)
from enlightenment.training.progress import OperatorProgress, ProgressStore, RunRecord, now_utc
from enlightenment.training.scoring import (
    brier_score,
    calibration_verdict,
    confidence_probability,
    next_interval_days,
    update_ratings,
)

#: The rubric the drill layer scores against, by id. Named here rather than inlined at the call
#: site so a content author renaming it produces one failure with one fix.
DRILL_RUBRIC_ID = "RUB-DRILL"

#: Until identity exists (flight plan step 10), every write goes to one synthetic operator and no
#: record of a named individual is created before the DPIA is closed.
DEMONSTRATION_OPERATOR = "synthetic-operator"

#: How long a served drill stays answerable, seconds, and how many may be held at once. Both are
#: bounds on an UNAUTHENTICATED route: every serve inserts an entry, so without them the map is a
#: memory-exhaustion surface. Twenty minutes is generous against the longest authored time target
#: in the library and short enough that an abandoned run does not accumulate.
PENDING_TTL_SECONDS: Final = 20 * 60
MAX_PENDING: Final = 512

#: Longest content-supplied string stored on a run row: the version, the item id, the procedure
#: id, the competency axis. Capping the version alone left the other three unbounded from the
#: same source into the same file, which is read whole on every request. `content/models.py`
#: declares no maximum length on any of them.
#: Re-exported from `identifiers`, which is where the rule lives now: `content/` cannot import
#: from `training/`, so a rule kept here was one a whole layer was unable to obey.
MAX_CONTENT_STRING: Final = _MAX_CONTENT_STRING

#: Longest withhold reason recorded, and the marker that says one was cut. A refusal message
#: embeds the `repr` of the authored parameter that caused it, and `content/models.py` declares no
#: maximum length on any value in `params` - so a 3,000-character `newest_at` produced a
#: 3,100-character reason, stored verbatim on the UNAUTHENTICATED manifest and in the run log,
#: across up to 140 items. Content does not get to set the size of an anonymous response.
#:
#: 256 is measured, not chosen: the longest reason any real content fault produces in this library
#: is 190 characters, the unknown-generator refusal, whose sentence is a fixed string. Every
#: legitimate diagnosis therefore survives whole, and a cut one SAYS it was cut, because a
#: truncated explanation that reads as complete sends an author looking in the wrong place.
#:
#: **256 CODE POINTS, not bytes, and the difference is 4x.** Measured: 256 astral characters are
#: 988 UTF-8 bytes, so the 140-item ceiling is about 138 kB rather than the 36 kB the naive
#: reading of "256 x 140" suggests. Stated rather than silently corrected, because the figure a
#: reviewer computes from this constant should be the figure the wire carries. The code-point cap
#: is kept deliberately: a byte cap has to avoid splitting a code point, and buying 4x on a
#: response that is already bounded is not worth a new way to emit invalid UTF-8.
MAX_WITHHOLD_REASON: Final = 256

#: How many unread parameter names the census serves. Named rather than a literal in the slice,
#: because the count cap is half of the bound: per-entry length and entry count are different
#: limits, and a test cannot assert a limit it cannot name.
MAX_SERVED_PARAMS: Final = 25

#: How many withheld items the manifest names, and how many reasons it gives. NINTH surface: both
#: were bounded per entry and uncapped in COUNT, so their size was set by the number of drills and
#: by accumulated runtime state. Measured on a tree that loads clean and answers 200: 140 drills
#: gave a 17,014-byte manifest - already over the 16 kB ceiling this project's own sweep asserts -
#: and 560 drills gave 64,675. The runtime path is the worse of the two, because `_withhold` adds
#: an entry per render refusal with a reason up to `MAX_WITHHOLD_REASON` rather than the
#: 32-character load-time one, so the route grew over the container's life.
#:
#: Every sibling field on this same dict was already count-capped. These two were the odd ones out,
#: against this module's own sentence that entry count and per-entry length are different limits.
#: The UNTRUNCATED TOTAL is served beside them, so a shortened list cannot read as a complete one.
MAX_SERVED_WITHHELD: Final = 25

#: How many due item ids and competency rows `/api/v1/me` serves. Both were UNBOUNDED in count or
#: length until V0.26.8: `due_items` had a bare `[:20]` over raw ids, and the competency id and name
#: had neither cap. Measured on the shipped library with ids stretched to 3,010 characters and
#: names to 20,000: a 221,589-byte response on a route that needs no token even when one is
#: configured. FOURTH round in which this class was recorded closed while a surface was live, which
#: is why the test that holds it now enumerates ROUTES and asserts a body ceiling rather than
#: naming fields - a field nobody thought of is exactly what kept getting through.
#: Operator-facing prose served on an anonymous route, capped. Measured against the shipped
#: library: the longest prompt is 202 characters and the longest authored `explain` is 562, so 512
#: and 1024 hold every legitimate string with headroom. SEVENTH surface, and the one that finally
#: forced the sweep to stop filtering on the HTTP verb: `POST /api/v1/drill/answer` takes no token
#: and `ScoredDrill.as_dict` served raw `explain`, `note` and `why_wrong`, measured at 201,084
#: bytes from one stretched authored field. `prompt`, `item_id` and `cue_id` on
#: `/api/v1/drill/next` were the same class - 206,027 bytes - and the exclusion of that route from
#: the sweep rested on `MAX_PAYLOAD_BYTES`, which governs the rendered stimuli only and saw 2,904
#: bytes of that body.
MAX_SERVED_PROMPT: Final = 512
MAX_SERVED_PROSE: Final = 1024

MAX_SERVED_DUE_ITEMS: Final = 20
MAX_SERVED_COMPETENCIES: Final = 32
TRUNCATION_MARK: Final = " [truncated]"

#: How many candidate drills one request may try before giving up. Bounded so pathological content
#: cannot spin a request, and greater than one so a single unservable item does not end a session.
MAX_SELECTION_ATTEMPTS: Final = 4

#: The derived keys that ARE an answer. A composite merging two renderers must not resolve a
#: clash on one of these by render order: the answer is not a matter of which product drew second.
ANSWER_KEYS: Final = frozenset({"expected_value", "expected_text"})

#: The seed used once at construction to ask whether a sentinel item can resolve an answer at all.
#: Any seed does: resolution is a property of the content and the renderer, not of the draw.
RESOLUTION_PROBE_SEED: Final = 20260901
MAX_ITEM_VERSION: Final = MAX_CONTENT_STRING

#: Largest serialised drill payload, bytes. A budget rather than a limit on any one field: the
#: 159 MB waterfall that prompted it came from a plausible-looking parameter read as a count, and
#: the next one will come from somewhere else. Generous against the largest legitimate stimulus
#: in the library, which is a dense waterfall at a few hundred kilobytes.
MAX_PAYLOAD_BYTES: Final = 4 * 1024 * 1024


class DrillError(RuntimeError):
    """Raised when a drill cannot be served or scored. Carries an operator-facing reason."""


@dataclass(frozen=True, slots=True)
class ServedDrill:
    """What the operator is given. **No answer, no explanation, no derived value.**"""

    run_id: str
    item_id: str
    cue_id: str
    prompt: str
    response_format: str
    elo: int
    confidence_required: bool
    time_target_s: int
    stimuli: tuple[dict[str, Any], ...]
    content_hash: str
    seed: int

    def as_dict(self) -> dict[str, Any]:
        """The wire form, built by naming every field.

        Deliberately not `asdict`: a field added to this dataclass should NOT appear in the
        payload until somebody decides it should, and a reflexive serialiser makes that decision
        for you at the moment of least attention.
        """
        return {
            "drill_run_id": self.run_id,
            #: BOUNDED. `MAX_PAYLOAD_BYTES` governs `stimulus` and nothing else, so these three
            #: were content-sized on an anonymous route: measured 206,027 bytes, of which the
            #: rendered stimuli - the only part the budget sees - were 2,904.
            "item_id": served_identifier(self.item_id),
            "cue_id": served_identifier(self.cue_id),
            "prompt": capped(self.prompt, MAX_SERVED_PROMPT),
            "response_format": self.response_format,
            "elo": self.elo,
            "confidence_required": self.confidence_required,
            "time_target_s": self.time_target_s,
            "stimulus": list(self.stimuli),
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True, slots=True)
class ScoredDrill:
    """The reveal. Everything withheld above arrives here, and only here."""

    run_id: str
    item_id: str
    matched: str
    correct: bool
    credit: float
    explain: str
    note: str
    why_wrong: str
    brier: float | None
    calibration: str
    rating_before: int | None
    rating_after: int | None
    next_due_in_days: int | None
    score_components: tuple[dict[str, Any], ...]
    total: float
    unimplemented_rules: tuple[str, ...]
    unimplemented_aggregation: tuple[str, ...]
    content_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "drill_run_id": self.run_id,
            #: BOUNDED, on the route the sweep could not see because it filtered on GET.
            "item_id": served_identifier(self.item_id),
            "matched": self.matched,
            "correct": self.correct,
            "credit": round(self.credit, 4),
            "explain": capped(self.explain, MAX_SERVED_PROSE),
            "note": capped(self.note, MAX_SERVED_PROSE),
            "why_wrong": capped(self.why_wrong, MAX_SERVED_PROSE),
            "brier": None if self.brier is None else round(self.brier, 4),
            "calibration": self.calibration,
            "rating_delta": (
                None
                if self.rating_after is None or self.rating_before is None
                else self.rating_after - self.rating_before
            ),
            "rating_before": self.rating_before,
            "rating_after": self.rating_after,
            "next_due_in_days": self.next_due_in_days,
            "score_components": list(self.score_components),
            "total": round(self.total, 4),
            "unimplemented_rules": list(self.unimplemented_rules),
            #: What the rubric ASKED FOR and this evaluator does not apply. Computed since
            #: V0.24.1 and, until now, serialised only by a method nothing called: a disclosure
            #: that reaches no surface is the silence it was written to replace.
            "unimplemented_aggregation": list(self.unimplemented_aggregation),
            "content_hash": self.content_hash,
        }


@dataclass(slots=True)
class _Pending:
    """A served drill awaiting its submission, held server-side with its derived values."""

    drill: Drill
    seed: int
    derived: dict[str, Any]
    served_at: datetime
    result: ScoredDrill | None = field(default=None)


def _bounded(value: Any) -> str:
    """A content-supplied string, length-capped before it is written to the progress file.

    `extra="allow"` carries fields the engine does not model, which is the deliberate reversal
    that let the package load unedited. The residual is length: a 5000-character `version` was
    stored verbatim on every run row, and the progress file is read whole on every request.
    """
    text = str(value or "")
    return text[:MAX_CONTENT_STRING] if len(text) > MAX_CONTENT_STRING else text


def capped(value: Any, limit: int) -> str:
    """A content-supplied string, capped at `limit` and MARKED when it is cut.

    The generic form of `bounded_reason`, for the served fields whose honest length is not a
    refusal reason: a prompt, an authored explanation, a scorer's note. Marked for the same reason
    - a shortened string that reads as complete sends a reader to the wrong place.
    """
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: limit - len(TRUNCATION_MARK)] + TRUNCATION_MARK


def bounded_reason(reason: str) -> str:
    """A content-supplied diagnostic string, length-capped and MARKED when it is cut.

    Public, and named for the job rather than for this module: `training_api` bounds the content
    load errors it serves on the anonymous 503 with the same helper, and a cross-module import of
    a private name is how two copies of one rule start diverging.

    Separate from `_bounded` because the two answer different questions. `_bounded` protects a
    file read whole on every request and truncates silently, which is right for a version string
    nobody reads for meaning. A reason is a DIAGNOSIS an author acts on, so it gets a wider bound
    and says when it was shortened.
    """
    if len(reason) <= MAX_WITHHOLD_REASON:
        return reason
    return reason[: MAX_WITHHOLD_REASON - len(TRUNCATION_MARK)] + TRUNCATION_MARK


class DrillLoop:
    """Selection, service and scoring over the content package.

    Selection is due-first then rating-matched, interleaved across procedures. The rating match
    targets the band just above the operator, because the item that teaches is the one at the
    edge of what they can already do; an item they answer without thinking produces a correct
    response and no learning.
    """

    def __init__(
        self,
        *,
        content: ContentPackage,
        registry: GeneratorRegistry,
        progress: ProgressStore,
        evaluator: RubricEvaluator | None = None,
    ) -> None:
        self._content = content
        self._registry = registry
        self._progress = progress
        self._evaluator = evaluator if evaluator is not None else RubricEvaluator()
        self._pending: OrderedDict[str, _Pending] = OrderedDict()
        #: Mutable, because an item can also prove unservable at REQUEST time. See `_withhold`.
        #: KEYED ON THE RAW ID, and bounded only where it is SERVED. V0.26.6 bounded these keys to
        #: stop 3,003-character ids reaching the anonymous manifest - a real fault fixed in the
        #: wrong place - and `select` compares a raw `d.id` against this map, so from V0.26.6 to
        #: V0.26.11 any authored id over `MAX_CONTENT_STRING` was DECLARED withheld and still
        #: SELECTED. Measured at 65 characters: 94 declared, zero excluded. That defeats both the
        #: absorbing state closed at V0.26 and the serve-time withhold feedback added at V0.26.1,
        #: on an anonymous route, while `CLAUDE.md` and `docs/SECURITY.md` recorded it as closed.
        #: A bound belongs at the wire, where the string is a disclosure, not at the key, where it
        #: is an identity.
        self._unresolvable: dict[str, str] = dict.fromkeys(
            self._items_without_a_resolvable_answer(), "no generator supplies its answer"
        )

    @property
    def ready(self) -> bool:
        return self._content.result.ok and bool(self._content.drills)

    def _seed(self, operator_id: str, item_id: str, attempt: int) -> int:
        """A stable seed per operator, item and attempt, so a debrief redraws exactly.

        Hashed rather than combined arithmetically: two operators on adjacent items must not get
        correlated stimuli, and a sum or an exclusive-or gives exactly that.
        """
        material = f"{self._content.content_hash}:{operator_id}:{item_id}:{attempt}"
        return int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")

    def _items_without_a_resolvable_answer(self) -> frozenset[str]:
        """Drills whose `computed_from_params` answer no generator can supply.

        Resolved ONCE, at construction, because it is a property of the content and the renderer
        rather than of the seed: measured across five seeds spanning eight orders of magnitude,
        each of the three sentinel items resolves or fails identically every time.
        """
        unresolvable: set[str] = set()
        for drill in self._content.drills:
            if COMPUTED_SENTINEL not in drill.answer.accept:
                continue
            try:
                rendered = compose(
                    self._registry,
                    drill.stimulus.generator,
                    drill.stimulus.params,
                    RESOLUTION_PROBE_SEED,
                    drill.stimulus.product_id,
                )
            except Exception:  # any failure to produce an answer means "cannot resolve"
                #: DELIBERATELY broad, and this breadth is the fix. Guarding only `LookupError`
                #: let a renderer's arithmetic escape `create_app` itself: a single NaN in a
                #: content parameter raised `ValueError: cannot convert float NaN to integer` out
                #: of this probe, `asgi.py` calls `create_app()` at import, and the worker then
                #: never boots - a crash loop with no health path to screenshot. Four of five
                #: probe cases did it, and `ephemeris` with `elapsed_min: 0` raises
                #: `ZeroDivisionError` from a plain authored integer.
                #:
                #: This is a PROBE, not the render path. Any failure to produce an answer means
                #: exactly "this item cannot resolve one", which is the fail-closed result, and
                #: the item is then withheld AND NAMED, so nothing is hidden by the breadth.
                unresolvable.add(drill.id)
                continue
            facts: dict[str, Any] = {}
            for stimulus in rendered:
                facts.update(stimulus.derived)
            if not (ANSWER_KEYS & facts.keys()):
                unresolvable.add(drill.id)
        return frozenset(unresolvable)

    def select(self, progress: OperatorProgress) -> Drill:
        """Due first, then the item just above the operator's rating.

        **An item that cannot resolve its own answer is not selected.** Refusing to SCORE such an
        item was right and was not enough: `select` is a pure function of due-state and rating, and
        `_unscored` records no run and advances no schedule, so the same item was chosen again on
        every turn. Measured on the real package at rating 1340: six consecutive serves returned
        DRL-0008, six unscorable results, and no rating movement - an absorbing state that ends
        the session. The penalty it replaced cost six rating points; this cost the whole sitting.
        The gap is disclosed on the manifest rather than hidden by the exclusion.
        """
        now = now_utc()
        scorable = [d for d in self._content.drills if d.id not in self._unresolvable]
        if not scorable:
            raise DrillError(
                "no drill in the loaded package can resolve its own answer, so there is nothing"
                " to serve for score"
            )
        due = [d for d in scorable if progress.cue(d.id).is_due(now)]
        pool = due or scorable
        # Just above, not at: the item that teaches sits at the edge of what the operator can
        # already do. One they answer without thinking produces a correct response and no
        # learning.
        target = progress.rating + 60
        return min(pool, key=lambda d: (abs(d.elo - target), d.id))

    @property
    def pending(self) -> Mapping[str, _Pending]:
        """The served drills still awaiting a submission. Read-only, and for diagnostics.

        A mapping view rather than the dictionary itself, so a caller can count and inspect but
        cannot insert: the bounds in `_evict` are the whole point of this collection and a caller
        that could add to it directly would be outside them.
        """
        return MappingProxyType(self._pending)

    def serve(self, *, operator_id: str, item_id: str | None = None) -> ServedDrill:
        """Serve the next drill, or a named one.

        `item_id` bypasses selection. It exists for a debrief redrawing a specific run and for
        tests that must reach a specific item; selection is due-and-rating driven, so a test
        that needs one particular item cannot get there by asking repeatedly.
        """
        if not self.ready:
            raise DrillError("the content package is not loaded")
        progress = self._progress.load(operator_id)
        #: **A refusal must feed back into selection.** `select` is a pure function of rating and
        #: due-state, and a refusal records no run and advances no schedule, so an item whose
        #: renderer RAISES was chosen again on every request: measured, one NaN on a content
        #: parameter produced six consecutive 503s on the same item with no progress. That is the
        #: absorbing state closed in V0.26 for one cause, reached through the handler added in
        #: V0.26.1 for another. The load-time probe cannot see it, because it only inspects items
        #: whose answer is computed; this one raised while rendering.
        #:
        #: So a refusal WITHHOLDS the item and the loop tries the next candidate, bounded.
        last: DrillError | None = None
        for _ in range(MAX_SELECTION_ATTEMPTS):
            item = self.select(progress) if item_id is None else self._named(item_id)
            #: COMPARED LIKE WITH LIKE. `RunRecord.item_id` is stored shortened, because the
            #: progress file is read whole on every request, and this compared it against the raw
            #: id: for any id over `MAX_CONTENT_STRING` the count was permanently zero, so `_seed`
            #: lost its attempt component and every re-drill of that item redrew the identical
            #: stimulus against a docstring promising "a stable seed per operator, item and
            #: attempt". Measured: three attempts, one distinct seed.
            stored_id = served_identifier(item.id)
            attempt = sum(1 for run in progress.runs if run.item_id == stored_id)
            seed = self._seed(operator_id, item.id, attempt)
            try:
                return self._serve_one(item, seed)
            except DrillError as exc:
                self._withhold(item.id, str(exc))
                #: An explicitly named item is NEVER substituted and never retried: the caller
                #: asked for that item, so a refusal is the answer. `_named` returns the same item
                #: every call, so without this the loop withholds it four times to reach the same
                #: outcome - and the substitution test cannot see that, because the budget message
                #: below still carries the item id it matches on. The attempt count is the effect,
                #: so a test asserts the count.
                if item_id is not None:
                    raise
                last = exc
        #: Reached when every candidate refused, and it says so. This used to re-raise the last
        #: item's error on the final attempt, which made this line unreachable - it existed for the
        #: return type and nothing else - and told the operator "one item is broken" when the true
        #: fact is "the budget was spent". The last reason is carried, because a bare "budget
        #: spent" is the half of the message an author cannot act on.
        #: BOUNDED, like every other reason. `{last}` is a content-sized string and this message
        #: reaches the unauthenticated `/api/v1/drill/next` as a 503 detail, which is the principle
        #: `MAX_WITHHOLD_REASON` was added for two commits earlier and that this line reintroduced.
        #: Not a regression - the code this replaced re-raised the same unbounded error directly -
        #: but a bound applied at one of two exits is a bound at neither.
        raise DrillError(
            f"no drill could be rendered within the selection budget of"
            f" {MAX_SELECTION_ATTEMPTS}: {bounded_reason(str(last))}"
        )

    def _withhold(self, item_id: str, reason: str) -> None:
        """Take an item out of selection and say why, once.

        Disclosed on the manifest and logged, so a withheld item is a visible content gap rather
        than a drill that quietly stops appearing.

        **FIRST REASON WINS, and that is a choice.** An item withheld at load time for "no
        generator supplies its answer" can later refuse at render with a more specific message,
        and the specific one is dropped. Kept anyway: the load-time reason is causally first and
        explains why the item was never served, a later render refusal on an item already out of
        selection is a consequence rather than a cause, and "more specific" has no rule an
        implementation could apply - only a judgement, which is how a silent overwrite of the
        useful reason by a useless one would arrive. One reason, one log line, per item.
        """
        if item_id not in self._unresolvable:
            bounded = bounded_reason(reason)
            #: The RAW id is the key, so `select` can exclude it. The log line is bounded, because
            #: that is a wire too: an unbounded id in the append-only run log is the same fault one
            #: sink along.
            self._unresolvable[item_id] = bounded
            log_event("drill.withheld", item=served_identifier(item_id), reason=bounded)

    def _serve_one(self, item: Drill, seed: int) -> ServedDrill:
        """Render, validate and hold one drill. Raises `DrillError` on any refusal.

        **The id is bounded HERE, where the reason is composed, and not only where it is stored.**
        Every refusal below prefixes the message with the item id, and an id is a raw content
        string. Measured with a 3,004-character id: the reason reached `MAX_WITHHOLD_REASON` before
        the sentence began, so the served reason was the id and the marker, and the diagnosis - the
        one thing an author reads it for - was truncated away. Bounding the key alone fixed the
        response size and left the message useless.
        """
        named = served_identifier(item.id)
        try:
            rendered = compose(
                self._registry,
                item.stimulus.generator,
                item.stimulus.params,
                seed,
                item.stimulus.product_id,
            )
        except LookupError as exc:
            raise DrillError(f"{named}: {exc}") from None
        except ArithmeticError as exc:
            #: A renderer's arithmetic on a content value is a CONTENT fault, so it earns the
            #: author-facing 503 this module documents rather than a generic 500. `elapsed_min: 0`
            #: divides by zero and `1e308` overflows a domain, both from plain authored numbers.
            raise DrillError(f"{named}: the stimulus could not be computed: {exc}") from None
        except (ValueError, TypeError) as exc:
            raise DrillError(f"{named}: the stimulus parameters are not usable: {exc}") from None

        #: A composite renders several products and their server-side facts are merged, so a key
        #: one renderer owns can be overwritten by the next in render order.
        #:
        #: For an item scored against a computed answer that would decide the answer by draw
        #: order, silently, because the loser leaves no trace - so it is refused. For every other
        #: item the answer keys are not read at all, and several renderers emit them
        #: unconditionally, so they are DROPPED rather than merged: carrying a value nothing reads
        #: is how a collision becomes load-bearing later without anyone choosing it.
        scored_on_a_computed_value = COMPUTED_SENTINEL in item.answer.accept
        derived: dict[str, Any] = {}
        for stimulus in rendered:
            facts = dict(stimulus.derived)
            if not scored_on_a_computed_value:
                for key in ANSWER_KEYS:
                    facts.pop(key, None)
            collisions = ANSWER_KEYS & derived.keys() & facts.keys()
            if collisions:
                raise DrillError(
                    f"{named}: two products on this board both computed"
                    f" {sorted(collisions)}, so the answer would depend on render order"
                )
            derived.update(facts)

        #: The budget, ENFORCED rather than merely tested. It was declared as a runtime bound and
        #: referenced only by a test, so it held for the library as it stands and for nothing
        #: else - and `CONTENT_DIR` is a supported operator knob whose tree that test never runs.
        #: Each count is also capped at its own renderer, which is where the cost is actually
        #: spent; this is the backstop for the next parameter nobody thought of.
        wire = tuple(stimulus.for_client() for stimulus in rendered)
        size = len(json.dumps(wire))
        if size > MAX_PAYLOAD_BYTES:
            raise DrillError(
                f"{named}: the rendered stimulus is {size:,} bytes, over the"
                f" {MAX_PAYLOAD_BYTES:,} byte budget, so it is refused rather than served"
            )

        run_id = uuid.uuid4().hex
        self._pending[run_id] = _Pending(
            drill=item, seed=seed, derived=derived, served_at=now_utc()
        )
        self._evict()
        return ServedDrill(
            run_id=run_id,
            item_id=item.id,
            cue_id=item.cue_id,
            prompt=item.prompt,
            response_format=str(item.response_format),
            elo=item.elo,
            confidence_required=item.confidence_required,
            time_target_s=item.time_target_s,
            stimuli=wire,
            content_hash=self._content.content_hash,
            seed=seed,
        )

    def _evict(self) -> None:
        """Bound the served-drill map, by age first and then by count.

        It was unbounded, and `GET /api/v1/drill/next` is unauthenticated: 4000 serves retained
        4000 entries and nothing ever removed one, so a few source addresses reached a
        container-sized heap within the hour and the outcome was an out-of-memory kill. That is
        availability loss on the very thing the split health probes exist to protect. Every other
        collection in this project is capped - sessions, run history, limiter keys - so this was
        the odd one out rather than a new principle.

        The message the caller already receives says a run "is unknown or has expired". Until
        this method existed, that expiry was advertised and not implemented.
        """
        cutoff = now_utc() - timedelta(seconds=PENDING_TTL_SECONDS)
        for run_id in [k for k, v in self._pending.items() if v.served_at < cutoff]:
            del self._pending[run_id]
        while len(self._pending) > MAX_PENDING:
            #: Oldest first. A drill served two hundred serves ago is the one least likely to be
            #: answered, and the newest must survive because it is the one on screen.
            self._pending.popitem(last=False)

    def score(
        self,
        *,
        run_id: str,
        response: str,
        confidence: int,
        operator_id: str,
    ) -> ScoredDrill:
        """Score one submission. Idempotent: a second call returns the first result.

        There is no `elapsed_ms` parameter. The client sends one and `DrillAnswer` validates it at
        the boundary, which is where a wire contract belongs; threading it in here and then
        suppressing the unused-argument warning was arguing both sides of the same point.
        """
        pending = self._pending.get(run_id)
        if pending is None:
            raise DrillError("that drill run is unknown or has expired")
        if pending.result is not None:
            return pending.result

        #: **The server's own clock decides the speed bonus. Full stop.** `elapsed_ms` arrives in
        #: the submission body, and a client posting `0` collected `D-FAST-AND-CORRECT` every
        #: time. The first repair took `min(measured, claimed)`, reasoning that a slow network
        #: should not cost an operator a bonus they earned - which closed `0` and negatives and
        #: left every other value open, because `min` lets the client only ever REDUCE elapsed.
        #: Posting `elapsed_ms: 1` on a run that genuinely took 21.5 seconds against a 20 second
        #: target collected the bonus over the real route. A concession to the client on a value
        #: the client controls is not a smaller hole, it is the same hole with a nicer reason.
        #:
        #: `elapsed_ms` is accepted on the request and then DISCARDED. It is not recorded either:
        #: a value nothing reads is better dropped than carried, and "kept as telemetry" is the
        #: kind of half-claim this register has already been caught making twice.
        elapsed = int((now_utc() - pending.served_at).total_seconds() * 1000)

        item = pending.drill
        outcome = match(response, item.answer, item.response_format, pending.derived)
        result = self._record(item, outcome, confidence, elapsed, operator_id, run_id)
        pending.result = result
        return result

    def _record(
        self,
        item: Drill,
        outcome: Match,
        confidence: int,
        elapsed_ms: int,
        operator_id: str,
        run_id: str,
    ) -> ScoredDrill:
        """Score one submission. `elapsed_ms` here is the SERVER's measurement, always."""
        rubric = self._content.rubric(DRILL_RUBRIC_ID)
        if rubric is None:
            raise DrillError(f"{DRILL_RUBRIC_ID} is missing from the content package")
        if outcome.matched == UNSCORABLE:
            #: **An unscorable item must not mark an operator.** The matcher refuses when a
            #: `computed_from_params` answer has no value behind it, which is right; the loop
            #: then scored the refusal as WRONG, dropped the rating six points, reset the cue
            #: schedule as a miss and wrote a run row. Marking somebody against a question nobody
            #: could answer is worse than not serving it, and it was silent: the operator saw the
            #: note and the rating move and had no way to tell which caused which.
            return self._unscored(item, outcome, run_id)
        facts = Facts(
            matched=outcome.matched,
            correct=outcome.correct,
            within_tolerance=outcome.within_tolerance,
            confidence_given=confidence > 0,
            elapsed_ms=elapsed_ms,
            time_target_s=item.time_target_s,
            numeric_expected=outcome.expected,
            partial_credit=outcome.credit,
        )
        evaluation = self._evaluator.evaluate(rubric, facts)

        progress = self._progress.load(operator_id)
        change = update_ratings(
            operator_rating=progress.rating,
            item_difficulty=item.elo,
            correct=outcome.correct,
        )
        probability = confidence_probability(confidence)
        brier = brier_score(probability, outcome.correct)
        schedule = progress.cue(item.id)
        schedule.record(correct=outcome.correct, now=now_utc())
        interval = next_interval_days(streak=schedule.streak, correct=outcome.correct)
        progress.rating = change.operator_after
        axis = progress.axis(self._competency_for(item))
        axis.attempts += 1
        axis.correct += 1 if outcome.correct else 0
        axis.brier_total += brier
        progress.runs.append(
            RunRecord(
                #: `served_identifier`, not `_bounded`: two long ids sharing a prefix would
                #: otherwise merge their run histories, corrupting the attempt count and the seed
                #: for both items rather than only losing them.
                item_id=served_identifier(item.id),
                item_version=_bounded(item.model_extra.get("version") if item.model_extra else ""),
                content_hash=self._content.content_hash,
                procedure_id=served_identifier(self._procedure_for(item)),
                axis=served_identifier(self._competency_for(item)),
                seed=self._pending_seed(run_id),
                answered_at=now_utc().isoformat(),
                classification=outcome.matched,
                first_action="",
                confidence=confidence,
                correct=outcome.correct,
                action_correct=outcome.correct,
                brier=brier,
                points=evaluation.total,
                rating_before=change.operator_before,
                rating_after=change.operator_after,
                lines=[dict(c) for c in evaluation.components()],
            )
        )
        self._progress.save(progress)

        return ScoredDrill(
            run_id=run_id,
            item_id=item.id,
            matched=outcome.matched,
            correct=outcome.correct,
            credit=outcome.credit,
            explain=item.explain,
            note=outcome.note,
            why_wrong=outcome.why_wrong,
            brier=brier,
            calibration=calibration_verdict(probability, outcome.correct),
            rating_before=change.operator_before,
            rating_after=change.operator_after,
            next_due_in_days=interval,
            score_components=evaluation.components(),
            total=evaluation.total,
            unimplemented_rules=evaluation.unimplemented,
            unimplemented_aggregation=evaluation.unimplemented_aggregation,
            content_hash=self._content.content_hash,
        )

    def _unscored(self, item: Drill, outcome: Match, run_id: str) -> ScoredDrill:
        """A result that teaches and records nothing: no rating, no schedule, no history row.

        The reveal still carries the item's own explanation, because an operator who has thought
        about the question has earned the answer whether or not the service could mark it.
        """
        return ScoredDrill(
            run_id=run_id,
            item_id=item.id,
            matched=outcome.matched,
            correct=False,
            credit=0.0,
            explain=item.explain,
            note=outcome.note,
            why_wrong=outcome.why_wrong,
            brier=None,
            calibration="not assessed: this item could not be scored",
            rating_before=None,
            rating_after=None,
            next_due_in_days=None,
            score_components=(),
            total=0.0,
            unimplemented_rules=(),
            unimplemented_aggregation=(),
            content_hash=self._content.content_hash,
        )

    def _named(self, item_id: str) -> Drill:
        """One drill by id, refused rather than substituted if the library does not have it."""
        item = self._content.drill(item_id)
        if item is None:
            raise DrillError(
                #: Shortened, matching `_serve_one` one method away. Latent rather than live - no
                #: route passes an `item_id` today - but the message reaches `bounded_reason` and a
                #: 503 the moment one does.
                f"no drill {served_identifier(item_id)!r} in the loaded content package"
            )
        return item

    def _pending_seed(self, run_id: str) -> int:
        pending = self._pending.get(run_id)
        return pending.seed if pending is not None else 0

    def _cue(self, item: Drill) -> Any:
        return next((c for c in self._content.cues if c.id == item.cue_id), None)

    def _procedure_for(self, item: Drill) -> str:
        """The procedure the item's cue belongs to, from content rather than from a mapping here."""
        cue = self._cue(item)
        return getattr(cue, "procedure_id", "") if cue is not None else ""

    def _competency_for(self, item: Drill) -> str:
        """The competency axis the cue measures. Empty is honest when the cue does not say."""
        cue = self._cue(item)
        return getattr(cue, "competency_id", "") if cue is not None else ""

    def dashboard(self, *, operator_id: str) -> dict[str, Any]:
        """Where the operator stands, and never a bare estimate.

        Every competency figure carries its interval, computed with an Agresti-Coull adjustment
        rather than a plain Wald one: on three attempts out of three a Wald interval reports zero
        width, which is the most confident and least true thing this could say.

        "Not measured" and "measured at zero" are rendered as different statements, because they
        are. An axis with no attempts has no figure at all.
        """
        progress = self._progress.load(operator_id)
        competencies = []
        for competency in self._content.competencies[:MAX_SERVED_COMPETENCIES]:
            axis = progress.axes.get(competency.id)
            interval = axis.interval if axis is not None else None
            competencies.append(
                {
                    "competency_id": served_identifier(competency.id),
                    #: `capped`, not `_bounded`: a competency name is operator-facing PROSE and
                    #: the interface renders it as the primary label, so a silent cut reads as the
                    #: name somebody chose. Prose is not an identity, so it needs the marker rather
                    #: than the digest.
                    "name": capped(competency.name, MAX_CONTENT_STRING),
                    "attempts": axis.attempts if axis is not None else 0,
                    "measured": axis is not None and axis.attempts > 0,
                    "estimate": None if axis is None else axis.accuracy,
                    "interval": None
                    if interval is None
                    else [round(interval[0], 3), round(interval[1], 3)],
                    "mean_brier": None if axis is None else axis.mean_brier,
                }
            )
        now = now_utc()
        due = [d.id for d in self._content.drills if progress.cue(d.id).is_due(now)]
        return {
            "operator": operator_id,
            "drill_rating": progress.rating,
            "runs_total": len(progress.runs),
            "competencies": competencies,
            "due_now": len(due),
            #: `served_identifier` here too. `_bounded` collapsed three distinct authored due
            #: ids into one served name - a fabricated identifier on an anonymous route, which is
            #: the fault `served_identifier` exists to end and which this line still carried after
            #: the manifest was fixed.
            "due_items": [served_identifier(item_id) for item_id in due[:MAX_SERVED_DUE_ITEMS]],
            "content_hash": self._content.content_hash,
            "identity": (
                "Operator identity does not exist yet (flight plan step 10). Every run is"
                " recorded against a synthetic operator, so no record of a named individual is"
                " created before the DPIA is closed."
            ),
        }

    def manifest(self) -> dict[str, Any]:
        """What is loaded, so a run record stays interpretable and a client can show provenance."""
        return {
            "ok": self._content.result.ok,
            "content_hash": self._content.content_hash,
            "counts": dict(self._content.result.counts),
            "errors": list(self._content.result.errors),
            "thresholds_source": self._content.thresholds.source,
            "scored_scenarios_ready": self._content.scored_scenarios_ready,
            "generators": sorted(self._registry.names),
            "rubric_rules_implemented": sorted(self._evaluator.implemented),
            "rubric_rules_unwired": self._unwired_rules(),
            #: Named, not merely excluded. An item withheld from selection because its stimulus
            #: cannot support its key is a content gap somebody has to decide about, and a silent
            #: exclusion is how it would be forgotten.
            "items_without_a_resolvable_answer": [
                served_identifier(item_id)
                for item_id in sorted(self._unresolvable)[:MAX_SERVED_WITHHELD]
            ],
            #: Why each was withheld. A bare list of ids says a gap exists; this says what it is.
            "withheld_reasons": {
                served_identifier(item_id): reason
                for item_id, reason in sorted(self._unresolvable.items())[:MAX_SERVED_WITHHELD]
            },
            #: The TOTAL, untruncated. Capping a disclosure without saying how much was cut turns
            #: "these are the gaps" into "here are twenty-five of an unstated number", which is a
            #: worse disclosure than the uncapped list it replaces.
            "items_without_a_resolvable_answer_total": len(self._unresolvable),
            "stimulus_params_unread": self._unread_params(),
        }

    def _unwired_rules(self) -> int:
        """How many rubric rules have no predicate. The count belongs in the product, not only
        in a commit message: 61 of 67 rules are prose `when` clauses the evaluator cannot
        evaluate, and until this field existed no HTTP surface said so."""
        return sum(
            1
            for rubric in self._content.rubrics
            for rule in rubric.rules
            if rule.id not in self._evaluator.implemented
        )

    def _unread_params(self) -> dict[str, Any]:
        """Authored stimulus parameters no renderer honours, counted and named.

        The realism gap, made countable. A renderer that ignores `beta_departs` draws a plot
        that contradicts its own answer key, and the only reason that shipped is that nothing
        counted it. `drills_fully_expressed` is the number to watch: it rises as renderers learn
        the content's vocabulary, and it is a content-and-code agreement rather than a score.
        """
        names: dict[str, int] = {}
        expressed = 0
        for drill in self._content.drills:
            unread = self._registry.unread(
                drill.stimulus.generator,
                drill.stimulus.params,
                board_for(
                    self._registry,
                    drill.stimulus.generator,
                    drill.stimulus.params,
                    drill.stimulus.product_id,
                ),
            )
            if not unread:
                expressed += 1
            for key in unread:
                names[key] = names.get(key, 0) + 1
        return {
            "drills_fully_expressed": expressed,
            "drills_total": len(self._content.drills),
            #: The param NAME is a raw content string on an unauthenticated route, and the entry
            #: count alone did not bound it: measured, a 500-character authored key was served
            #: verbatim. Twenty-five entries of unbounded length is not a bound.
            "params": {
                #: And the census keys. Two authored parameter names over the cap sharing a
                #: prefix would collapse to one entry with the second count overwriting the first,
                #: under-reporting a disclosed gap. Not reproduced through `registry.unread`, so
                #: this is consistency rather than a demonstrated fault - and consistency is the
                #: point: one function for every shortened identifier, so the next one is right by
                #: default instead of right if somebody remembers.
                served_identifier(key): count
                for key, count in sorted(names.items(), key=lambda kv: (-kv[1], kv[0]))[
                    :MAX_SERVED_PARAMS
                ]
            },
        }
