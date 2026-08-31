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

from dataclasses import dataclass, field
from typing import Any, Protocol

from enlightenment.scenario import SeededRandom


@dataclass(frozen=True, slots=True)
class Axis:
    """One axis of a rendered surface, carrying its own units and direction.

    `inverted` exists for one reason and it is not a preference: a magnitude axis runs brighter
    upward, which means the smaller number is at the top. A photometry surface drawn the other
    way up is not a styling choice, it is wrong, and an operator reading it would learn the
    opposite of the signature.
    """

    label: str
    unit: str = ""
    inverted: bool = False
    minimum: float | None = None
    maximum: float | None = None


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
    """A product renderer. One class per product, registered against its product id."""

    product_id: str
    name: str

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        """Produce the surface. Same params and same seed give the same surface, always."""
        ...


class GeneratorRegistry:
    """Which products have a renderer, and the load-time check that content agrees.

    The check runs at load rather than at request time on purpose. Content referencing a product
    nobody built is a content-and-code disagreement, and the cheapest place to catch a
    disagreement is the moment both sides are present.
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


def rng(seed: int, salt: str) -> SeededRandom:
    """One deterministic stream per surface, salted by product so two panels never correlate.

    Determinism is not a convenience here. The debrief redraws exactly what the operator was
    looking at from the run log alone, which needs the same seed to produce the same surface on a
    machine that has never seen the original.
    """
    return SeededRandom(seed ^ (hash(salt) & 0xFFFFFFFF))
