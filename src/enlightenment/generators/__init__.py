"""Product generators: the twelve, and the registry that proves content and code agree.

Ten renderers plus two composition modes. `composite` presents several renderers together for
cross-product reconciliation, and `probe` presents one and asks a single anatomy or no-action
question; neither draws anything itself, which is why neither is a class in `products.py`.
"""

from __future__ import annotations

from typing import Any

from enlightenment.content import COMPOSITION_MODES, PRODUCT_RENDERERS
from enlightenment.generators.base import (
    Axis,
    Column,
    Generator,
    GeneratorRegistry,
    Marks,
    Panel,
    Stimulus,
    rng,
)
from enlightenment.generators.products import ALL_GENERATORS


def build_registry() -> GeneratorRegistry:
    """The registry, with every renderer in `products.py` registered against its product id."""
    registry = GeneratorRegistry()
    for generator in ALL_GENERATORS:
        registry.register(generator)
    return registry


def board_for(
    registry: GeneratorRegistry,
    generator: str,
    params: dict[str, Any],
    product_id: str = "",
) -> tuple[str, ...]:
    """The product ids a stimulus actually renders, resolved ONCE and used by two callers.

    `compose` needs it to render and `GeneratorRegistry.unread` needs it to census, and the two
    must not disagree: the census briefly subtracted the vocabulary of EVERY renderer for a
    composition mode, which forgives a parameter no product on the board reads. Nothing
    under-reported on the shipped library, but it is a served figure and the direction of the
    error had turned from conservative to wrong.
    """
    if generator in PRODUCT_RENDERERS:
        renderer = registry.by_name(generator)
        return () if renderer is None else (renderer.product_id,)
    if generator == "probe":
        named = product_id or str(params.get("product_id") or params.get("product") or "")
        return (named,) if named else ()
    requested = params.get("products", "all")
    if requested == "all" or not isinstance(requested, list):
        return tuple(sorted(registry.product_ids))
    return tuple(str(product) for product in requested)


def compose(
    registry: GeneratorRegistry,
    generator: str,
    params: dict[str, Any],
    seed: int,
    product_id: str = "",
) -> tuple[Stimulus, ...]:
    """Resolve a stimulus, whether it names a renderer or a composition mode.

    Returns a tuple because `composite` is one stimulus per product on the board. A single
    renderer returns a tuple of one, so the caller has no special case and cannot forget one.

    Fails closed: an unresolvable generator or product raises rather than returning an empty
    board, because a drill served with no stimulus is a drill an operator answers by guessing.
    """
    if generator in PRODUCT_RENDERERS:
        renderer = registry.by_name(generator)
        if renderer is None:
            raise LookupError(f"no renderer registered for generator {generator!r}")
        return (renderer.render(params, seed),)

    if generator not in COMPOSITION_MODES:
        raise LookupError(
            f"generator {generator!r} is outside the canonical twelve. Legacy names in params"
            " are traceability only and must not be implemented."
        )

    if generator == "probe":
        # The contract says probe "uses whichever renderer the params name", and in the drill
        # bank the product is on the STIMULUS rather than in params. Both are honoured, stimulus
        # first, because that is where the 8 live probe items actually carry it.
        named = product_id or str(params.get("product_id") or params.get("product") or "")
        target = registry.for_product(named)
        if target is None:
            raise LookupError(f"probe names product {named!r}, which has no renderer")
        return (target.render(params, seed),)

    requested = params.get("products", "all")
    product_ids = (
        sorted(registry.product_ids)
        if requested == "all" or not isinstance(requested, list)
        else [str(p) for p in requested]
    )
    rendered: list[Stimulus] = []
    for index, wanted in enumerate(product_ids):
        target = registry.for_product(wanted)
        if target is None:
            raise LookupError(f"composite names product {wanted!r}, which has no renderer")
        # A different seed per product on the board, so two panels of a composite are not the
        # same surface drawn twice.
        rendered.append(target.render(params, seed + index))
    return tuple(rendered)


__all__ = [
    "Axis",
    "Column",
    "Generator",
    "GeneratorRegistry",
    "Marks",
    "Panel",
    "Stimulus",
    "board_for",
    "build_registry",
    "compose",
    "rng",
]
