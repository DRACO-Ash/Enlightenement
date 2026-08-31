"""The generator contract, enforced by reading the contract out of the content.

**The generator is code, the contract is data, and this file is the join.** Every requirement
below is read from the `generator_contract` block of `product-layouts.json` rather than restated
here, so a corrected layout fails a test and names the renderer to fix. One layout has already
been corrected once, which is the whole argument for doing it this way.

An idealised renderer produces a trainer that is easier than the job, and that is the worst kind
of failure because nobody notices it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest

from enlightenment.content import PRODUCT_RENDERERS, ContentPackage
from enlightenment.generators import build_registry, compose

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

#: How many of the 140 drills carry no authored parameter the renderers ignore. A RATCHET: it may
#: rise as renderers learn the content's vocabulary and must never fall. Raised on 31 August from
#: 0, when the renderers read a vocabulary they had invented for themselves.
FULLY_EXPRESSED_BASELINE = 11
SEED = 0x4F1A


@pytest.fixture(scope="module")
def package() -> ContentPackage:
    loaded = ContentPackage(CONTENT)
    loaded.load()
    return loaded


@pytest.fixture(scope="module")
def requirements() -> tuple[str, ...]:
    """The contract, read from the content. Not a copy kept in the test."""
    layouts = json.loads((CONTENT / "product-layouts.json").read_text(encoding="utf-8"))
    stated = layouts["generator_contract"]["requirements"]
    assert stated, "the generator contract block is empty, so this file asserts nothing"
    return tuple(stated)


def test_the_contract_block_still_states_the_requirements_these_tests_check(
    requirements: tuple[str, ...],
) -> None:
    """A guard on the guard: if the contract is reworded, the tests below stop matching it.

    Each phrase is the load-bearing part of one requirement. A rewrite that drops a requirement
    fails here rather than leaving a test below quietly checking something nobody asks for.
    """
    joined = " ".join(requirements).casefold()
    for phrase in (
        "observation-level scatter",
        "independent per-panel axis scales",
        "tight vertical scale",
        "inverted magnitude axis",
        "days to longitude crossing",
        "noise model",
    ):
        assert phrase in joined, phrase


def test_every_product_the_content_references_has_a_registered_renderer(
    package: ContentPackage,
) -> None:
    """Content pointing at an unbuilt product must fail at LOAD, not at the request needing it."""
    registry = build_registry()
    referenced = {d.stimulus.product_id for d in package.drills}
    assert registry.unbuilt(referenced) == ()
    assert registry.names == PRODUCT_RENDERERS


def test_every_shipped_drill_renders(package: ContentPackage) -> None:
    """All 140, including the composition modes. A drill that cannot render cannot be served."""
    registry = build_registry()
    for drill in package.drills:
        rendered = compose(
            registry,
            drill.stimulus.generator,
            drill.stimulus.params,
            SEED,
            drill.stimulus.product_id,
        )
        assert rendered, drill.id
        for stimulus in rendered:
            assert stimulus.panels or stimulus.rows, drill.id


def test_the_same_params_and_seed_draw_the_same_surface_every_time() -> None:
    """The debrief redraws exactly what the operator saw, from the run log alone.

    Determinism is not a convenience here: without it a debrief on another machine shows a
    different picture and the comparison it exists for is meaningless.

    In-process only, and that is why the test below exists: this one CANNOT fail on the fault
    that actually shipped, because a single interpreter always agrees with itself.
    """
    registry = build_registry()
    for name in sorted(PRODUCT_RENDERERS):
        first = compose(registry, name, {}, SEED)[0]
        second = compose(registry, name, {}, SEED)[0]
        assert first.for_client() == second.for_client(), name


_FINGERPRINT_SCRIPT = """
import hashlib, json, sys
from enlightenment.generators import build_registry, compose
registry = build_registry()
surfaces = []
for name in sorted(registry.names):
    surfaces.append(compose(registry, name, {}, 20260831)[0].for_client())
print(hashlib.sha256(json.dumps(surfaces, sort_keys=True).encode()).hexdigest())
"""


def test_the_same_seed_draws_the_same_surface_in_a_separate_process() -> None:
    """The test the shipped fault needed, and the one an in-process comparison cannot be.

    `rng()` salted the seed with the builtin `hash()` of the product name. Python randomises str
    hashing per process, so every process drew a different surface from the same seed while every
    in-process test passed. Two subprocesses under DIFFERENT `PYTHONHASHSEED` values is the only
    arrangement that sees it, so the assertion is made there: the fingerprint of every renderer's
    surface must be identical across both.
    """
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    fingerprints = []
    for hash_seed in ("0", "1", "4242"):
        env["PYTHONHASHSEED"] = hash_seed
        finished = subprocess.run(  # noqa: S603 - fixed argv, this interpreter
            [sys.executable, "-c", _FINGERPRINT_SCRIPT],
            capture_output=True,
            text=True,
            env=env,
            check=True,
            timeout=180,
        )
        fingerprints.append(finished.stdout.strip())
    assert len(set(fingerprints)) == 1, f"surface depends on PYTHONHASHSEED: {fingerprints}"
    assert len(fingerprints[0]) == 64


def test_a_different_seed_draws_a_different_surface() -> None:
    """The converse, so determinism cannot be a constant surface."""
    registry = build_registry()
    a = compose(registry, "waterfall", {"days": 5}, SEED)[0]
    b = compose(registry, "waterfall", {"days": 5}, SEED + 1)[0]
    assert a.for_client() != b.for_client()


def test_the_wire_form_never_carries_the_derived_expected_value() -> None:
    """`derived` is server-side only, and this is the one place the strip is performed.

    Several numeric items carry `computed_from_params` instead of an answer, because stating the
    number in content would fix the stimulus too. The generator computes it and it must stay on
    the server: in the browser it is the answer.
    """
    registry = build_registry()
    for name in sorted(PRODUCT_RENDERERS):
        stimulus = compose(registry, name, {}, SEED)[0]
        assert "derived" not in stimulus.for_client(), name
        serialised = json.dumps(stimulus.for_client())
        for key in stimulus.derived:
            assert f'"{key}"' not in serialised, f"{name}: {key} reached the wire"


def test_the_photometry_magnitude_axis_is_inverted() -> None:
    """Contract requirement. Brighter is a smaller number and an analyst reads brightness upward.

    A photometry surface drawn the other way up is not a styling choice, it is wrong, and an
    operator reading it would learn the opposite of the signature.
    """
    stimulus = compose(build_registry(), "light_curve", {}, SEED)[0]
    panel = stimulus.panels[0]
    assert panel.y.inverted is True
    assert "phase angle" in panel.x.label.casefold()


def test_the_waterfall_is_observation_level_scatter_with_gaps() -> None:
    """Contract requirement: realistic density and realistic collection gaps, not clean traces.

    Density is asserted as a floor rather than a figure, because the real product's count depends
    on the window. What is asserted about the GAPS is the shape: geostationary electro-optical
    collects through local night and not in daylight, so the observation times must leave holes
    far wider than the spacing inside a night.
    """
    stimulus = compose(build_registry(), "waterfall", {"days": 5}, SEED)[0]
    panel = stimulus.panels[0]
    total = sum(len(group.x) for group in panel.marks)
    assert total > 800, total
    assert all(group.glyph == "cross" for group in panel.marks)

    times = sorted(t for group in panel.marks for t in group.y)
    gaps = [b - a for a, b in pairwise(times)]
    assert max(gaps) > 20 * (sum(gaps) / len(gaps)), "the coverage has no real gaps in it"


def test_the_waterfall_time_axis_runs_newest_at_the_bottom() -> None:
    """The observed product runs time down the page. Reversing it reverses every drift streak."""
    stimulus = compose(build_registry(), "waterfall", {"days": 5}, SEED)[0]
    assert stimulus.panels[0].y.inverted is True


def test_the_residual_scale_is_tight_and_labels_the_time_and_beta_series() -> None:
    """Contract requirement. Beta reveals a plane change and time reveals a size change.

    The labels are the discrimination, not decoration: a renderer that moved both series together
    would destroy every item that asks which one departed.
    """
    stimulus = compose(build_registry(), "residual", {"days": 7}, SEED)[0]
    panel = stimulus.panels[0]
    assert panel.y.minimum == pytest.approx(-0.08)
    assert panel.y.maximum == pytest.approx(0.08)
    labels = {group.label.casefold() for group in panel.marks}
    assert "time association" in labels
    assert "beta association" in labels


def test_the_residual_departs_in_the_series_the_params_name() -> None:
    """An in-plane departure moves the time series and leaves beta alone, and vice versa."""
    registry = build_registry()
    in_plane = compose(registry, "residual", {"departure_component": "in_plane"}, SEED)[0]
    cross = compose(registry, "residual", {"departure_component": "cross_track"}, SEED)[0]

    def spread(stimulus: object, label: str) -> float:
        panel = stimulus.panels[0]  # type: ignore[attr-defined]
        group = next(g for g in panel.marks if g.label == label)
        return max(group.y) - min(group.y)

    assert spread(in_plane, "Time association") > spread(in_plane, "Beta association")
    assert spread(cross, "Beta association") > spread(cross, "Time association")


def test_the_relative_motion_panels_use_independent_scales() -> None:
    """Contract requirement, and the reason is measured rather than aesthetic.

    The observed panels differ by an order of magnitude between projections, and a shared scale
    flattens two of the three into a line. Independence is asserted as: the panels do not all
    report the same vertical extent.
    """
    stimulus = compose(build_registry(), "tric", {}, SEED)[0]
    assert len(stimulus.panels) == 6
    extents = []
    for panel in stimulus.panels:
        values = [v for group in panel.marks for v in group.y]
        if values:
            extents.append(round(max(values) - min(values), 6))
    assert len(set(extents)) > 1, extents


def test_the_relative_motion_surface_marks_state_changes_distinctly_from_the_track() -> None:
    """Contract requirement. A refit is not a manoeuvre and the two must not share a glyph."""
    stimulus = compose(build_registry(), "tric", {}, SEED)[0]
    first = stimulus.panels[0]
    roles = {group.role: group.glyph for group in first.marks}
    assert roles["track"] != roles["state-change"]
    assert roles["state-change"] != roles["minimum"]


def test_the_bounded_relative_track_closes_and_the_unbounded_one_does_not() -> None:
    """The discrimination the rendezvous items train, and it is a property of the dynamics.

    The track comes from the real Clohessy-Wiltshire solution, so this asserts the physics rather
    than a drawn shape: with the no-drift along-track rate the loop returns near its start, and
    without it the object walks away.

    Driven by the CONTENT's vocabulary. This test used to pass `bounded`, which no drill in the
    library authors: it was a name this module invented for itself, so the test proved a property
    of a parameter nothing could set. `nmc_stable` and `fmc` are what the items actually say.
    """
    registry = build_registry()
    closed = compose(registry, "tric", {"geometry": "nmc_stable"}, SEED)[0].panels[0].marks[0]
    open_track = compose(registry, "tric", {"geometry": "fmc"}, SEED)[0].panels[0].marks[0]
    closed_walk = abs(closed.x[-1] - closed.x[0])
    open_walk = abs(open_track.x[-1] - open_track.x[0])
    assert closed_walk < open_walk / 5, (closed_walk, open_walk)


def test_the_right_ascension_panel_is_drawn_as_a_staircase() -> None:
    """Discrete state changes are steps in the real product; a curve asserts a transition."""
    stimulus = compose(build_registry(), "tric", {}, SEED)[0]
    panel = next(p for p in stimulus.panels if "ascension" in p.title.casefold())
    assert panel.steps
    assert all(group.glyph == "step" for group in panel.steps)


def test_the_determination_table_column_order_is_initial_final_delta() -> None:
    """Corrected on 31 August, and load-bearing: the answer column must be in the right place.

    An earlier note read Initial, Delta, Final, which would have put the delta column second in
    every rendered stimulus. The specifics block runs apogee before perigee for the same reason:
    that block is scored positionally.
    """
    stimulus = compose(build_registry(), "dc_table", {}, SEED)[0]
    keys = [column.key for column in stimulus.columns]
    assert keys.index("initial") < keys.index("final") < keys.index("delta")
    elements = [row["element"] for row in stimulus.rows]
    assert elements.index("Apogee height") < elements.index("Perigee height")


def test_the_determination_table_marks_the_row_that_is_natural_regression() -> None:
    """The delta column is not the manoeuvre.

    On the observed screen a right ascension change of about seven degrees across a fit interval
    of a day and a half is natural nodal regression. The renderer reproduces that deliberately,
    so an item can ask which row is the burn.
    """
    stimulus = compose(build_registry(), "dc_table", {}, SEED)[0]
    natural = [row["element"] for row in stimulus.rows if row["natural"]]
    assert natural == ["Right ascension"]
    assert stimulus.derived["natural_element"] == "Right ascension"


def test_the_neighbourhood_carries_every_observed_column() -> None:
    """Contract requirement, named column by column.

    Delta-v, score and days to longitude crossing are what turn a list of nearby objects into a
    ranked set worth attention. A renderer missing them produces a screen that cannot support the
    decision the drill asks for.
    """
    stimulus = compose(build_registry(), "neighbourhood", {}, SEED)[0]
    keys = {column.key for column in stimulus.columns}
    for required in ("delta_v_ms", "score", "days_to_crossing"):
        assert required in keys, required
    assert stimulus.rows
    assert any(row["days_to_crossing"] is not None for row in stimulus.rows)


def test_the_neighbourhood_header_shows_the_threshold_block_and_the_filters() -> None:
    """Contract requirement: the filter toggles must be visible in their real state."""
    stimulus = compose(build_registry(), "neighbourhood", {}, SEED)[0]
    header = {key.casefold(): value for key, value in stimulus.header}
    assert "thresholds" in header
    assert any(key.startswith("filter") for key in header)


def test_every_surface_carries_a_text_equivalent_of_how_it_reads() -> None:
    """Accessibility is a code standard here, not polish. A plot with no prose is unreadable."""
    registry = build_registry()
    for name in sorted(PRODUCT_RENDERERS):
        stimulus = compose(registry, name, {}, SEED)[0]
        assert stimulus.reads_as.strip(), name
        assert stimulus.footer.strip(), name


def test_every_surface_declares_its_axes_with_units() -> None:
    """ "Cross-Track (km)" and not "Cross-Track". A number with no unit is not a measurement."""
    registry = build_registry()
    for name in sorted(PRODUCT_RENDERERS):
        for panel in compose(registry, name, {}, SEED)[0].panels:
            assert panel.x.label.strip(), name
            assert panel.y.label.strip(), name


def test_the_provisional_noise_figures_are_marked_as_provisional() -> None:
    """The last contract requirement is NOT satisfied and must not be quietly claimed.

    Every generator is supposed to draw its imperfection from the noise model the offline
    characterisation pass produces. That pass has not run, so the amplitudes here are figures
    chosen rather than measured. Making a surface convincing before it runs makes the shortfall
    harder to see, not smaller, so the marker is asserted rather than trusted.
    """
    source = (ROOT / "src" / "enlightenment" / "generators" / "products.py").read_text(
        encoding="utf-8"
    )
    provisional = re.findall(r"^PROVISIONAL_[A-Z_]+", source, re.MULTILINE)
    assert len(provisional) >= 3, provisional
    registry = build_registry()
    marked = [
        name
        for name in sorted(PRODUCT_RENDERERS)
        if "PROVISIONAL" in compose(registry, name, {}, SEED)[0].footer
    ]
    assert marked, "no surface tells the reader its imperfection is provisional"


def test_the_composite_mode_renders_every_product_on_the_board() -> None:
    """`composite` presents several products for cross-product reconciliation."""
    registry = build_registry()
    board = compose(registry, "composite", {"products": "all"}, SEED)
    assert len(board) == len(PRODUCT_RENDERERS)
    named = compose(registry, "composite", {"products": ["PRD-RESIDUAL", "PRD-TRIC"]}, SEED)
    assert [s.product_id for s in named] == ["PRD-RESIDUAL", "PRD-TRIC"]


def test_the_probe_mode_resolves_the_product_from_the_stimulus() -> None:
    """The eight live probe items carry the product on the stimulus rather than in params."""
    registry = build_registry()
    rendered = compose(
        registry, "probe", {"event": "routine_station_keep"}, SEED, "PRD-NEIGHBORHOOD"
    )
    assert rendered[0].product_id == "PRD-NEIGHBORHOOD"


def test_an_unresolvable_generator_fails_closed() -> None:
    """A drill served with no stimulus is a drill an operator answers by guessing."""
    registry = build_registry()
    with pytest.raises(LookupError, match="canonical twelve"):
        compose(registry, "residual_series", {}, SEED)
    with pytest.raises(LookupError, match="no renderer"):
        compose(registry, "probe", {}, SEED, "PRD-NOT-A-PRODUCT")


#: What a rendered surface must AGREE with when the content authors it. Each entry names an
#: authored parameter, the derived fact it governs, and the value the fact must take. This table
#: is the contract that DRL-0034 broke: it authored `beta_departs` with `time_stable`, the
#: renderer ignored both and drew an in-plane departure, and the plot then said the opposite of
#: the answer key it was serving. An operator reading it correctly was marked wrong.
AGREEMENTS: tuple[tuple[str, object, str, object], ...] = (
    ("beta_departs", True, "departure_component", "out_of_plane"),
    ("time_stable", True, "departure_component", "out_of_plane"),
    ("departure_component", "out_of_plane", "departure_component", "out_of_plane"),
    ("departure_component", "in_plane", "departure_component", "in_plane"),
    ("geometry", "fmc", "bounded", False),
    ("geometry", "nmc_stable", "bounded", True),
    ("actual_manoeuvres", 0, "manoeuvres", 0),
)


def test_no_rendered_stimulus_contradicts_its_own_authored_scene(
    package: ContentPackage,
) -> None:
    """Every drill in the library, checked against the table above.

    Not a sample and not a fixture: the whole bank, because the fault that shipped was invisible
    exactly where nobody was looking. A renderer that ignores a parameter draws a plausible
    picture, so there is no crash, no warning and no failing test - only an item that teaches the
    wrong lesson.
    """
    registry = build_registry()
    contradictions: list[str] = []
    for drill in package.drills:
        params = drill.stimulus.params
        rendered = compose(
            registry,
            drill.stimulus.generator,
            params,
            SEED,
            drill.stimulus.product_id,
        )
        derived: dict[str, object] = {}
        for stimulus in rendered:
            derived.update(stimulus.derived)
        for key, authored, fact, required in AGREEMENTS:
            if params.get(key) != authored or fact not in derived:
                continue
            if derived[fact] != required:
                contradictions.append(
                    f"{drill.id}: authored {key}={authored!r} but rendered {fact}={derived[fact]!r}"
                )
    assert not contradictions, contradictions


def test_a_numeric_item_resolves_the_value_it_will_be_scored_against(
    package: ContentPackage,
) -> None:
    """`computed_from_params` is answered by the generator or the item cannot be marked.

    The matcher reads `derived["expected_value"]` and NO generator set it, so both numeric items
    in the library resolved to `unscorable` every time. The resolution branch had never once
    executed against real content, which is a control that exists only on paper.
    """
    registry = build_registry()
    numeric = [d for d in package.drills if "computed_from_params" in d.answer.accept]
    assert numeric, "no computed item in the library, so this test asserts nothing"
    resolved = 0
    for drill in numeric:
        rendered = compose(
            registry,
            drill.stimulus.generator,
            drill.stimulus.params,
            SEED,
            drill.stimulus.product_id,
        )
        derived: dict[str, object] = {}
        for stimulus in rendered:
            derived.update(stimulus.derived)
        if "expected_value" in derived:
            resolved += 1
    assert resolved, "no computed item resolves a value, so every one of them is unscorable"


def test_the_unread_parameter_census_does_not_regress(package: ContentPackage) -> None:
    """A ratchet on the content-and-code agreement, not a pass mark.

    129 of 140 drills carry authored parameters no renderer reads, and the honest treatment is to
    count them rather than to claim otherwise. This test fails if that number GROWS - a new
    renderer that quietly stops reading a parameter, or content authored against a vocabulary
    nobody implemented - and the baseline is lowered by hand as renderers learn the vocabulary.
    """
    registry = build_registry()
    expressed = sum(
        1
        for drill in package.drills
        if not registry.unread(drill.stimulus.generator, drill.stimulus.params)
    )
    assert expressed >= FULLY_EXPRESSED_BASELINE, (
        f"{expressed} drills fully express their authored scene, down from"
        f" {FULLY_EXPRESSED_BASELINE}. A renderer stopped reading a parameter."
    )
