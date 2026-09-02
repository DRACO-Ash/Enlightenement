"""The generator contract: what a product renderer is, and the registry that proves one exists.

**The generator is code, the contract is data, the tests are the join.** Ten product renderers
and two composition modes, and the count moves roughly never, so they are hand-written classes.
A waterfall producing twenty thousand observations with realistic collection gaps and drift
streaks emerging from populated regions is not derivable from a JSON description of required
fields; attempting it means writing Python in JSON and losing both.

What the JSON drives instead is the contract, by two cheap mechanisms. This module carries the
first: a registry keyed by product id, checked against every product the content references, so
a drill pointing at a product nobody built fails at LOAD rather than at the request that needs
it. The second is in `tests/test_generators.py`, which reads the `generator_contract`
requirements out of `product-layouts.json` and asserts each renderer honours them, so a
corrected layout fails the test and names the renderer to fix.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from enlightenment.identifiers import served_identifier, utf8
from enlightenment.scenario import SeededRandom


@dataclass(frozen=True, slots=True)
class Axis:
    """One axis of a rendered surface, carrying its own units and direction.

    `inverted` exists for two distinct reasons, and they need distinguishing because the
    interface used to caption both of them "brighter upward":

    ● A magnitude axis runs brighter UPWARD, so the smaller number is at the top. A photometry
      surface drawn the other way up is not a styling choice, it is wrong, and an operator
      reading it would learn the opposite of the signature.
    ● A waterfall's time axis runs with the NEWEST observations nearest the longitude axis, which
      on the two items that author it is the bottom - the convention of the real product.
      "Brighter upward" said of a time axis is nonsense, and it was rendered on every waterfall.

    So the reason travels with the axis in `inversion_note` rather than being assumed by the
    renderer of the caption.

    `ticks` carries explicit value-and-label pairs for an axis whose numbers are not the thing an
    operator reads. A waterfall's vertical axis is a TIMELINE: "0.003" and "4.99" are the
    internals of the plot, and the operator needs the timestamp. Empty means the interface
    computes numeric ticks as before.
    """

    label: str
    unit: str = ""
    inverted: bool = False
    minimum: float | None = None
    maximum: float | None = None
    inversion_note: str = ""
    ticks: tuple[tuple[float, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Marks:
    """One drawable group: a class of point with a shared meaning, and its own colour role.

    Colour is a variable here, never decoration. In every real product the colour IS the
    analysis: it separates one pass from another, one association type from another, one source
    from another. `role` names what the colour means so the interface resolves it against the
    palette rather than the generator choosing a hex value.
    """

    label: str
    role: str
    x: tuple[float, ...]
    y: tuple[float, ...]
    glyph: str = "cross"
    #: Per-point index into a sequential ramp, where the surface encodes a second variable such
    #: as recency or time along track. Empty when the group is a single flat colour.
    ramp: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class Panel:
    """One panel of a surface. A surface may carry several, with INDEPENDENT scales.

    Independent per-panel scaling is a contract requirement rather than a nicety: the observed
    relative-motion panels differ by an order of magnitude between projections, and a shared
    scale flattens two of the three into a line.
    """

    title: str
    x: Axis
    y: Axis
    marks: tuple[Marks, ...] = ()
    #: Piecewise-constant series, drawn as a staircase rather than interpolated. Discrete state
    #: changes are steps in the real products and a curve through them asserts a transition that
    #: did not happen.
    steps: tuple[Marks, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Column:
    """One column of a tabular product, with its alignment and whether it is the answer column."""

    key: str
    label: str
    align: str = "left"
    emphasis: bool = False


@dataclass(frozen=True, slots=True)
class Stimulus:
    """A rendered stimulus: everything the client needs to draw, and nothing it must not know.

    **No accept value, no reject value, no explanation.** The production-format rule is
    architectural: a drill payload carries the stimulus and the prompt, and the key arrives only
    in the response to a submission.

    `derived` is the exception that proves it. Several numeric items carry the sentinel
    `computed_from_params` instead of an answer, because stating the number in content would fix
    the stimulus too. The generator computes it and puts it HERE, server-side, where the
    evaluator reads it and the client never sees it.
    """

    product_id: str
    generator: str
    title: str
    panels: tuple[Panel, ...] = ()
    columns: tuple[Column, ...] = ()
    rows: tuple[dict[str, Any], ...] = ()
    header: tuple[tuple[str, str], ...] = ()
    legend: tuple[tuple[str, str], ...] = ()
    footer: str = ""
    reads_as: str = ""
    #: Server-side only. Stripped before the stimulus crosses the wire.
    derived: dict[str, Any] = field(default_factory=dict)

    def for_client(self) -> dict[str, Any]:
        """The wire form, with `derived` removed. The one place the strip is performed."""
        return {
            "product_id": self.product_id,
            "generator": self.generator,
            "title": self.title,
            "panels": [_panel_dict(p) for p in self.panels],
            "columns": [
                {"key": c.key, "label": c.label, "align": c.align, "emphasis": c.emphasis}
                for c in self.columns
            ],
            "rows": list(self.rows),
            "header": [list(pair) for pair in self.header],
            "legend": [list(pair) for pair in self.legend],
            "footer": self.footer,
            "reads_as": self.reads_as,
        }


def _axis_dict(axis: Axis) -> dict[str, Any]:
    return {
        "label": axis.label,
        "unit": axis.unit,
        "inverted": axis.inverted,
        "minimum": axis.minimum,
        "maximum": axis.maximum,
        "inversion_note": axis.inversion_note,
        "ticks": [[value, label] for value, label in axis.ticks],
    }


def _marks_dict(marks: Marks) -> dict[str, Any]:
    return {
        "label": marks.label,
        "role": marks.role,
        "x": list(marks.x),
        "y": list(marks.y),
        "glyph": marks.glyph,
        "ramp": list(marks.ramp),
    }


def _panel_dict(panel: Panel) -> dict[str, Any]:
    return {
        "title": panel.title,
        "x": _axis_dict(panel.x),
        "y": _axis_dict(panel.y),
        "marks": [_marks_dict(m) for m in panel.marks],
        "steps": [_marks_dict(m) for m in panel.steps],
        "notes": list(panel.notes),
    }


class Generator(Protocol):
    """A product renderer. One class per product, registered against its product id.

    `reads` is the load-bearing addition. It names the authored parameters this renderer
    actually honours, and it exists because the first version of this module invented its own
    vocabulary: the renderers read `centre_longitude`, `glint_phase_deg` and `state_changes`
    while the content authored `beta_departs`, `separation_km` and `headcount`. Two disjoint
    vocabularies, so every drill of a given generator drew very nearly the same picture and the
    authored scene was silently discarded. On DRL-0034 that produced a stimulus showing the
    OPPOSITE of its own answer key: the item states `beta_departs` with `time_stable`, the
    renderer defaulted to an in-plane departure, and an operator reading the plot correctly was
    marked wrong.

    Declaring the vocabulary makes the gap countable instead of invisible. A parameter outside
    `reads` is reported, and a drill carrying one is served for study rather than scored, because
    a stimulus that cannot express the discrimination the key rewards must not move a rating.
    """

    product_id: str
    name: str
    reads: frozenset[str]

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        """Produce the surface. Same params and same seed give the same surface, always."""
        ...


#: What the two composition modes read, resolved in `compose()` rather than in a renderer.
#: `composite` selects the board from `products` and `probe` selects one renderer; `tier` is the
#: authored difficulty band, which the selector reads and the surface does not.
COMPOSITION_READS: Final[dict[str, frozenset[str]]] = {
    "composite": frozenset({"products", "tier"}),
    "probe": frozenset({"product_id", "product", "question", "tier"}),
}


class GeneratorRegistry:
    """Which products have a renderer, and the load-time check that content agrees.

    `unbuilt` is CALLED at load and its result is logged; the binding check is in the test suite,
    where a product the content references and no renderer claims fails the verification loop. A
    request for one still answers 503. Stating that the check "runs at load" implied a refusal to
    start that this does not perform, which is the kind of overstatement that gets believed.
    """

    def __init__(self) -> None:
        self._by_product: dict[str, Generator] = {}
        self._by_name: dict[str, Generator] = {}

    def register(self, generator: Generator) -> None:
        self._by_product[generator.product_id] = generator
        self._by_name[generator.name] = generator

    def for_product(self, product_id: str) -> Generator | None:
        return self._by_product.get(product_id)

    def by_name(self, name: str) -> Generator | None:
        return self._by_name.get(name)

    @property
    def product_ids(self) -> frozenset[str]:
        return frozenset(self._by_product)

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._by_name)

    def unbuilt(self, referenced: set[str]) -> tuple[str, ...]:
        """Product ids the content references and no renderer claims. Empty is the healthy case."""
        return tuple(sorted(referenced - self.product_ids))

    def unread(
        self, generator_name: str, params: dict[str, Any], board: tuple[str, ...] = ()
    ) -> tuple[str, ...]:
        """Authored parameters this renderer does not honour. Empty means the scene is expressed.

        Keys beginning with an underscore are excluded by design: `_legacy_generator` is the
        traceability marker the content package carries for the 58 retired generator names, and
        it is deliberately not implemented.

        An unknown generator name returns every key rather than none. A censor that reports
        nothing when it cannot see is worse than no censor, because it reads as a clean result.
        """
        authored = {key for key in params if not key.startswith("_")}
        if generator_name in COMPOSITION_READS:
            #: The two composition modes are not renderers, so they have no class to declare a
            #: vocabulary on. What they read is resolved in `compose()` and named here - and the
            #: renderers UNDERNEATH read the rest, so their vocabularies are subtracted here too.
            #:
            #: The previous comment said the caller censused them and the caller did no such
            #: thing, so the manifest named `headcount` unread on DRL-0104 and `step_change`
            #: unread on DRL-0086 while the waterfall and the light curve beneath them read
            #: exactly those. A wrong figure in a served disclosure, against the hard rule on
            #: inventing figures in user-facing data - conservative in direction, which is why
            #: it survived, but a floor presented as a count.
            #: Only the renderers ON THE BOARD. Subtracting every renderer's vocabulary forgives
            #: a parameter nobody present reads, in a figure served on the manifest. The board is
            #: resolved by `generators.board_for`, the same function `compose` renders from, so
            #: the census and the render cannot disagree about what is on screen.
            beneath: set[str] = set()
            for product in board:
                renderer = self._by_product.get(product)
                if renderer is not None:
                    beneath |= renderer.reads
            return tuple(sorted(authored - COMPOSITION_READS[generator_name] - beneath))
        generator = self._by_name.get(generator_name)
        if generator is None:
            return tuple(sorted(authored))
        return tuple(sorted(authored - generator.reads))


def rng(seed: int, salt: str) -> SeededRandom:
    """One deterministic stream per surface, salted by product so two panels never correlate.

    Determinism is not a convenience here. The debrief redraws exactly what the operator was
    looking at from the run log alone, which needs the same seed to produce the same surface on a
    machine that has never seen the original.

    **The salt is digested with SHA-256, never with the builtin `hash`.** Python randomises the
    hash of a `str` per process unless `PYTHONHASHSEED` is fixed, so the first version of this
    function drew a DIFFERENT surface in every process from the same seed: three runs of one
    forty-drill render produced three different fingerprints. That voids the whole determinism
    gate and the replay claim with it, silently, because a single process always agrees with
    itself and so does a test that renders twice in one interpreter. `determinism.py` already
    records this hazard class for set iteration; this is the same fault reintroduced one module
    later. A digest is stable across processes, releases and machines, which is the actual
    requirement.
    """
    digest = hashlib.sha256(utf8(salt)).digest()[:4]
    return SeededRandom(seed ^ int.from_bytes(digest, "big"))


class ContentParameterError(ValueError):
    """A stimulus parameter that cannot be used, described WITHOUT quoting the authored value.

    **The reason this type exists rather than a plain `ValueError`.** A renderer's refusal becomes
    a withhold reason and reaches the unauthenticated manifest and an anonymous 503, so the
    boundary rule in `docs/SECURITY.md` is that a refusal names the KEY and its DOMAIN and never
    the value that failed. V0.26.3 removed the one explicit interpolation and left the mechanism
    that actually carried values: `float("...")` puts the string it could not parse into its own
    message, and `training/drill.py` reflected that message verbatim. Measured, against a copy of
    the shipped tree in TWO anonymous requests: an authored parameter value was served on both
    `GET /api/v1/drill/next` and `GET /api/v1/content/manifest`.

    So the caller cannot be trusted to interpolate a foreign exception, and it no longer does. This
    type is the marker for a message the code AUTHORED and can therefore vouch for; anything else
    is reduced to its class name at the boundary and logged in full server-side. That is
    fail-closed: a coercion site added later leaks nothing while it waits to be converted.
    """


def authored_number(params: Mapping[str, Any], *keys: str, default: float) -> float:
    """A number from the authored parameters, refusing by KEY and TYPE rather than by value.

    Several keys may be given, tried in order, because the content spells one fact more than one
    way - `days` and `cycles_shown` are the same span, `sites` and `sensors` the same count - and
    reading only the first left every item on the same window.

    The key is put through `served_identifier`, and that is DEFENCE IN DEPTH rather than a live
    need: every `*keys` argument at all 27 call sites is a code literal, so no content-authored
    name reaches this interpolation today. It is kept because `content/models.py` declares no
    maximum length on a `params` key, so a future call site deriving a key FROM the content would
    otherwise put an unbounded authored string into a message that reaches an anonymous route.
    """
    for key in keys:
        if key in params:
            try:
                return float(params[key])
            except (TypeError, ValueError) as exc:
                raise ContentParameterError(
                    f"the stimulus parameter {served_identifier(key)!r} must be a number"
                ) from exc
    return float(default)


def authored_count(params: Mapping[str, Any], *keys: str, default: int) -> int:
    """A whole number from the authored parameters. `authored_number`'s rule, for a count."""
    for key in keys:
        if key in params:
            try:
                return int(params[key])
            except (TypeError, ValueError) as exc:
                raise ContentParameterError(
                    f"the stimulus parameter {served_identifier(key)!r} must be a whole number"
                ) from exc
    return int(default)
