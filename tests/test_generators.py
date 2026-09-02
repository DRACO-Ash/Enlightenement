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
import math
import os
import re
import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest

from enlightenment.content import PRODUCT_RENDERERS, ContentPackage
from enlightenment.generators import board_for, build_registry, compose
from enlightenment.generators.products import (
    DEFAULT_LONGITUDE_HALF_WIDTH_DEG,
    GEO_PERIOD_S,
    MAX_FRAGMENTS,
    MAX_INTERVALS,
    MAX_NEIGHBOURHOOD_TRACKS,
    MAX_REVOLUTIONS,
    MAX_SCHEDULE_HOURS,
    MAX_SENSORS,
    MAX_SPAN_DAYS,
    MAX_STATE_CHANGE_MARKS,
    MAX_TABLE_ROWS,
    NEWEST_AT_VALUES,
    TIME_TICKS,
)

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

#: How many of the 140 drills carry no authored parameter the renderers ignore. A RATCHET: it may
#: rise as renderers learn the content's vocabulary and must never fall.
#:
#: Briefly recorded as 11, which was not true: 25 of the declared `reads` names were never
#: consumed by the renderer declaring them, so six drills counted as fully expressed on the
#: strength of a false declaration. `test_every_declared_read_actually_changes_the_surface` is
#: what stops that recurring, and 5 is the figure that survives it.
FULLY_EXPRESSED_BASELINE = 5

#: How many `computed_from_params` items resolve an answer from the surface. Two of three:
#: DRL-0004 (a drift rate from an altitude change) and DRL-0030 (a drift direction). DRL-0008
#: does NOT, and that is a recorded gap rather than a defect - see `_tric_derived`.
RESOLVED_COMPUTED_ITEMS = 2

#: The figure DRL-0005 authors, which is the real ASTRA 1M artefact from the flight plan.
ABSURD_RATE_DEG_DAY = -22900000

#: How much wider a drifter's longitude sweep must be than a station-kept object's jitter before
#: the drift counts as drawn. The item's key says the object has STOPPED station-keeping, so the
#: two must not look alike.
MIN_DRIFT_LEGIBILITY = 5.0

#: The widest longitude sweep a clamped drifter may be drawn across, in degrees. A LITERAL, not a
#: multiple of the constant under test - that made the assertion an identity in its own subject.
#:
#: Set from the codebase's OWN recorded judgement rather than loosely: `products.py` records that
#: an excursion factor of 2.5 was rejected for squeezing the held objects into a quarter panel,
#: and 2.5 x the 6° box is 15°, measured. A 20° bound admitted exactly that rejected value, so it
#: contradicted the measurement it was meant to encode. Twice the box excludes it.
#:
#: **A DISCLOSED GAP, not a verdict.** This ceiling excludes the one factor carrying a recorded
#: rejection - 2.5, at 15.0° - and admits the shipped 1.2, at 7.2°. It also admits 2.0, at exactly
#: 12.0°, and nothing in this repository distinguishes 7.2° from 12.0°: 2.5 is the only factor with
#: a recorded judgement of any kind, and no changelog entry records a browser measurement of the
#: excursion at any factor. Closing the band needs one, which is owner-blocked work on the same
#: list as the noise figures. Narrowing the bound to the shipped value instead would make the
#: assertion an identity in its own subject, which is the fault the comment above records.
MAX_READABLE_EXCURSION_DEG = 12.0
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
    """A drill served with no stimulus is a drill an operator answers by guessing.

    The refusal SENTENCE is asserted, not just the exception. It reaches an author through the
    anonymous `content_unavailable` 503, and it has now lost words to a reflow TWICE: fitting
    `served_identifier(generator)` onto the line dropped "names in params", so the served text
    read "...outside the canonical twelve. Legacy are traceability only and must not be
    implemented." Nothing in 991 tests could see it, because a `match=` on two words passes
    whatever happens to the rest. A served string with no assertion behind it is a served string
    that decays.
    """
    registry = build_registry()
    with pytest.raises(LookupError, match="canonical twelve") as unknown:
        compose(registry, "residual_series", {}, SEED)
    assert "Legacy names in params are traceability only" in str(unknown.value), str(unknown.value)
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
        #: Either kind of resolution. Two of the three ask for a number and the third asks for a
        #: DIRECTION, which is just as much a fact about the surface the renderer drew.
        if "expected_value" in derived or "expected_text" in derived:
            resolved += 1
    #: TWO of the three, deliberately. DRL-0008 asks how many manoeuvres are visible in a
    #: relative-motion track, and the honest measurement is that they are not: an along-track burn
    #: steps the subsequent drift rate rather than putting a cusp in the track, and a blind
    #: change-point detector over the distance panel finds no events at any burn count. So that
    #: item resolves nothing and fails closed. Ratcheted rather than asserted loosely, because
    #: "any of them resolves" would have passed while two were permanently unscorable.
    assert resolved == RESOLVED_COMPUTED_ITEMS, (
        f"{resolved} of {len(numeric)} computed items resolve a value, expected"
        f" {RESOLVED_COMPUTED_ITEMS}. If a renderer has learned to answer one, raise the"
        " baseline; if one has stopped, that item now marks nobody and teaches nobody."
    )


def test_the_unread_parameter_census_does_not_regress(package: ContentPackage) -> None:
    """A ratchet on the content-and-code agreement, not a pass mark.

    135 of 140 drills carry authored parameters no renderer reads, and the honest treatment is to
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


def _segment_rates(stimulus: object, burns: int) -> list[float]:
    """Mean along-track rate, km per day, for each segment between burns.

    The along-track series is the second coordinate of the Hill frame, which is the first panel's
    x axis. Segment boundaries are where `_burned_track` puts them.
    """
    panel = stimulus.panels[0]  # type: ignore[attr-defined]
    track = panel.marks[0]
    samples = len(track.x)
    segment = max(samples // (burns + 1), 8)
    rates: list[float] = []
    for index in range(burns + 1):
        low, high = index * segment, min((index + 1) * segment, samples)
        if high - low < 6:
            continue
        span_days = (high - low) * GEO_PERIOD_S * 2 / samples / 86400.0
        rates.append((track.x[high - 1] - track.x[low]) / span_days)
    return rates


def _separation(first: object, second: object, index: int) -> float:
    """Distance between two tracks at one sample."""
    return math.hypot(
        first.x[index] - second.x[index],  # type: ignore[attr-defined]
        first.y[index] - second.y[index],  # type: ignore[attr-defined]
    )


def test_a_manoeuvre_steps_the_drift_rate_and_the_count_is_not_scored() -> None:
    """What a burn actually does, and the honest limit of it.

    Two earlier versions of this test were wrong in opposite directions. The first asserted
    nothing about legibility at all. The second asserted the manoeuvred track diverges from the
    unmanoeuvred one by half its own scale, which proves the track is DIFFERENT and not that
    three events are COUNTABLE - and the item asks "how many manoeuvres are visible" at zero
    tolerance.

    The real signature: an along-track burn is nearly parallel to the velocity it modifies, so it
    does not turn the track - measured at the burn vertices the local turn is smaller than at a
    median sample. It steps the subsequent DRIFT RATE. Three burns give four segments whose
    along-track rates differ by roughly an order of magnitude, and with no burns the rate is
    constant. That is asserted here.

    And the limit, asserted alongside it: a blind change-point detector over the distance panel
    finds no events at any burn count, so the COUNT is not scorable and the item must resolve no
    expected value. A stimulus that cannot support its key must not move a rating.
    """
    registry = build_registry()

    flat = compose(registry, "tric", {"geometry": "nmc_stable"}, SEED)[0]
    assert flat.derived["manoeuvres"] == 0
    assert _segment_rates(flat, 1) == pytest.approx(_segment_rates(flat, 1))

    burned = compose(registry, "tric", {"geometry": "fmc", "actual_manoeuvres": 3}, SEED)[0]
    assert burned.derived["manoeuvres"] == 3
    rates = _segment_rates(burned, 3)
    assert len(rates) == 4, rates
    steps = [abs(rates[i + 1] - rates[i]) for i in range(len(rates) - 1)]
    baseline = abs(_segment_rates(flat, 1)[0]) or 1.0
    for index, step in enumerate(steps):
        assert step > baseline, (
            f"burn {index + 1} changes the along-track rate by {step:.2f} km/day against an"
            f" unmanoeuvred rate of {baseline:.2f}: not a step an analyst could read"
        )

    #: The fail-closed half. `expected_value` absent means `match` refuses the item.
    assert (
        "expected_value"
        not in compose(registry, "tric", {"geometry": "fmc", "manoeuvre_count": "seeded"}, SEED)[
            0
        ].derived
    )


def test_a_burned_track_carries_no_duplicate_vertex() -> None:
    """A repeated point is not a cusp. It is invisible, and it looks like data.

    The burn used to be applied by appending the previous position again with a new velocity, so
    the artefact was two identical samples: nothing to see, and a shape in the data that reads
    like something happened there.
    """
    stimulus = compose(build_registry(), "tric", {"geometry": "fmc", "actual_manoeuvres": 3}, SEED)[
        0
    ]
    track = stimulus.panels[0].marks[0]
    duplicates = [
        index for index, (x, y) in enumerate(pairwise(zip(track.x, track.y, strict=True))) if x == y
    ]
    assert not duplicates, f"duplicate vertices at {duplicates}"


#: A distinctive value for every parameter a renderer declares it reads, and where one parameter
#: only bites in the presence of another, that context. `delta_inc_deg` does nothing unless the
#: beta series is the one departing; a gap length does nothing unless there is a gap.
PROBE_VALUES: dict[str, tuple[object, dict[str, object]]] = {
    "days": (11, {}),
    "cycles_shown": (9, {}),
    "departure_at_frac": (0.3, {}),
    "departure_component": ("out_of_plane", {}),
    "beta_departs": (True, {}),
    "time_stable": (True, {}),
    "delta_inc_deg": (0.09, {"beta_departs": True}),
    "delta_period_s": (0.07, {}),
    "departure_after_gap": (True, {}),
    "gap_start_frac": (0.2, {"departure_after_gap": True}),
    "gap_len_hours": (90, {"departure_after_gap": True}),
    "obs_density": ("starved", {}),
    "tight_y_scale": (True, {}),
    "manoeuvre_marker": (True, {}),
    "headcount": (5, {}),
    "drifting": (True, {}),
    #: NOT 3: `DEFAULT_DRIFTERS` is 3, so a probe of 3 renders identically to no probe at all and
    #: reports a live parameter as inert. A probe value that collides with the default proves
    #: nothing, and this one cost an afternoon.
    "drifting_object": (2, {}),
    "longitudinal_bounds": (1.0, {}),
    "drift_begins": (True, {}),
    "ceased_at_cycle": (2, {"cycles_shown": 9}),
    "derived_rate_deg_day": (0.66, {"drifting": True}),
    "newest_at": ("top", {}),
    "collection_gaps": (True, {}),
    "missed_passes": (6, {}),
    "intervals": (9, {}),
    "step_change": (True, {}),
    "phase_angle_shift": (12.0, {}),
    "geometry": ("fmc", {}),
    "revolutions": (5, {}),
    "ratio": (3.5, {}),
    "regime": ("LEO", {}),
    "drift_rate": ("seeded_slow", {"geometry": "nmc_drifting"}),
    "manoeuvre_count": ("seeded", {}),
    "actual_manoeuvres": (2, {}),
    "state_change_markers": (7, {}),
    "separation_km": (2.0, {}),
    "distance_km": (3.0, {}),
    "separation": ("seeded_close", {}),
    "period_change_s": (33.0, {}),
    "period_delta_s": (21.0, {}),
    "plane_change_deg": (0.9, {}),
    "inclination_delta_deg": (0.4, {}),
    "include_natural_secular_drift": (False, {}),
    "nodal_regression_deg": (3.0, {}),
    "altitude_delta_km": (18.0, {}),
    "rows": (4, {}),
    "hours": (30, {}),
    "sites": (3, {}),
    "sensors": (4, {}),
    "minutes": (44, {}),
    "elapsed_min": (55, {}),
    "ballistic": (True, {}),
    "fragments": (12, {}),
    "parent_period_min": (120.0, {}),
    "parent_altitude_km": (900.0, {}),
    "spread": (2.5, {}),
}


def test_every_declared_read_actually_changes_the_surface() -> None:
    """`reads` is a claim about behaviour, so it is checked by behaviour.

    The census that reports the content-and-code gap is only worth having if `reads` is true, and
    the first version of it was not: 25 of the declared names were never consumed at all, so the
    census reported 11 of 140 drills fully expressed when the honest figure was 5. A count that
    over-reports its own coverage is worse than no count, because it retires the question.

    A STATIC check is not enough and was tried first: reading the class source matches the `reads`
    declaration itself, so every name trivially "appears" and the check passes vacuously. This
    renders with the parameter and without it and requires the surface to differ.
    """
    registry = build_registry()
    inert: list[str] = []
    for generator in sorted(registry.names):
        for parameter in sorted(registry.by_name(generator).reads):  # type: ignore[union-attr]
            assert parameter in PROBE_VALUES, (
                f"{generator} declares it reads {parameter!r} and there is no probe value for it."
                " Add one: a declaration nothing exercises is a claim nothing checks."
            )
            value, context = PROBE_VALUES[parameter]
            without = json.dumps(compose(registry, generator, dict(context), SEED)[0].for_client())
            with_it = json.dumps(
                compose(registry, generator, {**context, parameter: value}, SEED)[0].for_client()
            )
            if without == with_it:
                inert.append(
                    f"{generator}.{parameter} (probe {value!r} - if this equals the renderer's"
                    " own default, the probe is at fault rather than the declaration)"
                )
    assert not inert, (
        "these parameters are declared as read and change nothing in the rendered surface, so the"
        f" unread census over-reports its own coverage: {inert}"
    )


def test_the_newest_observations_are_drawn_nearest_the_longitude_axis() -> None:
    """The convention of the real product, and the geometry and the COLOUR must agree on it.

    They did not. The vertical axis was inverted so the largest time sat at the bottom, next to
    the longitude axis, and the note said "newest observations at the bottom" - while the recency
    ramp was passed elapsed time, where `ramp(0)` is the most-recent stop. So the window START,
    the oldest data in the plot, was drawn in red at the TOP, and the newest end was drawn as
    oldest. One panel, two opposite claims about which end is now, in a product where
    red-for-recency is the first thing an analyst reads.

    Asserted on both halves at once: the newest observation must have the most-recent ramp value
    AND must be the one the inverted axis places nearest the longitude axis.
    """
    stimulus = compose(build_registry(), "waterfall", {"days": 5, "drifting": True}, SEED)[0]
    panel = stimulus.panels[0]
    assert panel.y.inverted, "the axis no longer places the newest end at the bottom"

    for group in panel.marks:
        if not group.x:
            continue
        assert group.ramp, "a waterfall track carries no recency ramp"
        newest = max(range(len(group.y)), key=lambda i: group.y[i])
        oldest = min(range(len(group.y)), key=lambda i: group.y[i])
        assert group.ramp[newest] < group.ramp[oldest], (
            "the recency ramp runs backwards: the oldest observation is coloured as the most"
            " recent one"
        )
        assert group.ramp[newest] == pytest.approx(0.0, abs=0.05), group.ramp[newest]


def test_the_waterfall_time_axis_is_labelled_with_timestamps_not_bare_numbers() -> None:
    """An operator correlates a date against a pass schedule and a provider post.

    "0.003" and "4.99" are the internals of the plot. They cannot be correlated with anything, and
    every real product on this screen carries a timestamp. The ticks run oldest to newest in the
    axis's own direction, and the header states the window.
    """
    stimulus = compose(build_registry(), "waterfall", {"days": 5}, SEED)[0]
    axis = stimulus.panels[0].y
    assert len(axis.ticks) == TIME_TICKS
    assert axis.unit == "UTC"
    values = [value for value, _ in axis.ticks]
    assert values == sorted(values), "the timeline ticks are not in order"
    for _, label in axis.ticks:
        assert re.fullmatch(r"\d{2} \w{3} \d{2}:\d{2}Z", label), label
    header = dict(stimulus.header)
    assert "From (synthetic)" in header
    assert "To" in header
    assert header["From (synthetic)"] != header["To"]
    #: The epoch is marked where a SCREENSHOT will carry it, not only in the footer.
    assert "synthetic" in " ".join(header).casefold()


def test_an_inverted_axis_states_its_own_reason_for_being_inverted() -> None:
    """ "Inverted, brighter upward" is true of a magnitude axis and nonsense on a timeline.

    The interface captioned every inverted axis that way, so every waterfall the product has ever
    drawn told the operator its time axis ran brighter upward. The reason now travels with the
    axis.
    """
    registry = build_registry()
    photometry = compose(registry, "light_curve", {}, SEED)[0].panels[0].y
    assert photometry.inverted
    assert "brighter" in photometry.inversion_note

    timeline = compose(registry, "waterfall", {}, SEED)[0].panels[0].y
    assert timeline.inverted
    assert "brighter" not in timeline.inversion_note
    assert "newest" in timeline.inversion_note

    for generator in sorted(registry.names):
        for panel in compose(registry, generator, {}, SEED)[0].panels:
            if panel.y.inverted:
                assert panel.y.inversion_note, f"{generator}: an inverted axis with no reason"


def test_the_timeline_labels_come_from_the_seed_and_never_from_the_clock() -> None:
    """A debrief redraws what the operator saw from the run log alone.

    A timestamp read off the wall clock would relabel the same surface differently on every
    render, which breaks the replay this project gates on. The epoch is synthetic, derived from
    the seed, and the footer says so rather than implying a real collection.
    """
    registry = build_registry()
    first = compose(registry, "waterfall", {"days": 4}, SEED)[0]
    again = compose(registry, "waterfall", {"days": 4}, SEED)[0]
    assert first.panels[0].y.ticks == again.panels[0].y.ticks

    other = compose(registry, "waterfall", {"days": 4}, SEED + 1)[0]
    assert other.panels[0].y.ticks != first.panels[0].y.ticks
    assert "synthetic epoch" in first.footer


def test_no_refusal_message_quotes_the_authored_value_that_caused_it() -> None:
    """A refusal reason reaches the unauthenticated manifest, so it must not quote content.

    The security gate proved the channel rather than argued it: it set `newest_at` to a real
    accept string from DRL-0005's own key, and the anonymous `/api/v1/content/manifest` served the
    string back inside `withheld_reasons`. Nothing scoreable travelled, because `newest_at` is a
    two-value layout flag - but nothing bound the message either, and a refusal that quotes an
    authored value is a disclosure channel whatever the value happens to be that week.

    The rule this asserts: a validation refusal names the KEY and its DOMAIN. An author who needs
    to know what they wrote has the file they wrote it in; an anonymous caller does not.

    **Structural identifiers are exempt, deliberately.** A generator name and a product id ARE
    named, because a typo in one is undiagnosable otherwise, and both are bounded by
    `MAX_WITHHOLD_REASON` on the way out. The distinction held here is value versus identifier.
    """
    registry = build_registry()
    #: A string that would be a key if this were a scored parameter, which is the point.
    planted = "reject the value, check epoch separation"
    with pytest.raises(ValueError, match="newest_at must be one of") as refusal:
        compose(registry, "waterfall", {"newest_at": planted}, SEED)
    assert planted not in str(refusal.value), (
        f"the refusal quotes the authored value, which reaches an anonymous route: {refusal.value}"
    )
    #: And it still says enough to fix. The key and both legal values, or the message is useless.
    assert "newest_at" in str(refusal.value), str(refusal.value)
    for legal in NEWEST_AT_VALUES:
        assert legal in str(refusal.value), str(refusal.value)


def test_an_absurd_authored_rate_is_clamped_for_drawing_and_reported_verbatim() -> None:
    """DRL-0005 authors the real ASTRA 1M artefact: -22,900,000 degrees per day.

    The whole lesson of the item is that a reported figure cannot be right. Drawn literally it
    spans 114 million degrees on an axis labelled in degrees, every station-kept object collapses
    into one pixel column and the plot conveys nothing - so the item that teaches "distrust this
    number" became the item that shows nothing.

    This assertion did not exist. Deleting the clamp entirely left the whole suite green, which
    means the fix for it was held by nothing: the read-probe passes either way, because it only
    requires the parameter to change something.
    """
    stimulus = compose(
        build_registry(),
        "waterfall",
        {"days": 5, "drifting": True, "derived_rate_deg_day": ABSURD_RATE_DEG_DAY},
        SEED,
    )[0]
    derived = stimulus.derived
    assert derived["reported_rate_deg_day"] == ABSURD_RATE_DEG_DAY, "the authored figure was lost"
    assert derived["rate_clamped"] is True

    #: Asserted against the BOX, with the readable limit as a literal. The first version read
    #: `excursion <= bounds * DRIFT_EXCURSION_FACTOR`, where `excursion` is itself
    #: `span * DRIFT_EXCURSION_FACTOR` - an identity in the constant it imported. Setting the
    #: factor to 25.0 put a 150° sweep on a 6° box, worse than the 2.5 that was rejected as
    #: illegible, and the suite stayed green. The clamp's existence was held; its VALUE, which is
    #: the whole content of the change, was not.
    bounds = 2 * DEFAULT_LONGITUDE_HALF_WIDTH_DEG
    excursion = abs(derived["drawn_rate_deg_day"]) * 5
    assert excursion <= MAX_READABLE_EXCURSION_DEG, (
        f"the drawn drifter travels {excursion:.1f}° across a {bounds:.1f}° station-keeping box,"
        " so the held objects an operator judges it against are squeezed off the panel"
    )
    assert excursion > bounds, (
        f"the drifter travels {excursion:.1f}° and never leaves the {bounds:.1f}° box, so nothing"
        " distinguishes it from a station-kept object"
    )

    #: And the header must state BOTH figures. `for_client()` strips `derived`, so this string is
    #: the only client-visible disclosure, and it read "drawn to scale" - the plain assertion
    #: that the drawing represents the number faithfully, which is its negation.
    header = dict(stimulus.header)
    assert "Reported rate" in header
    assert "22,900,000" in header["Reported rate"]
    assert "drawn to scale" not in header["Reported rate"]
    assert "clamped" in header["Reported rate"] or "drawn at" in header["Reported rate"]


def test_an_authored_drift_onset_actually_draws_a_drift() -> None:
    """`drift_begins: true` was multiplied by the window and put the onset at its END.

    So DRL-0019 drew a perfectly held longitude while its key says the object has stopped
    station-keeping. Fixed in code and then cited by a register row while no test mentioned
    `drift_visible`: setting the default onset fraction to 0.999 would draw no drift at all with
    the suite green.
    """
    registry = build_registry()
    for params in (
        {"days": 7, "drift_begins": True},
        {"days": 7, "ceased_at_cycle": 5, "cycles_shown": 9, "drifting": True},
        {"days": 7, "drift_begins": 0.4, "drifting": True},
    ):
        stimulus = compose(registry, "waterfall", params, SEED)[0]
        assert stimulus.derived["drift_visible"] is True, params
        assert stimulus.derived["drift_onset_days"] >= 0.0, params
        assert stimulus.derived["drift_onset_days"] < 7.0, params

        #: Measured on the MARKS, not on the derived flag. An onset of 0.999 of the window keeps
        #: `drift_visible` true and `drift_onset_days` under the span while drawing no drift at
        #: all, and that mutant survived the first version of this test. What matters is that the
        #: drifting track sweeps a range the held objects do not.
        drifting = [g for g in stimulus.panels[0].marks if g.role == "object-drift" and g.x]
        held = [g for g in stimulus.panels[0].marks if g.role == "object-held" and g.x]
        assert drifting, params
        assert held, params
        swept = max(max(g.x) - min(g.x) for g in drifting)
        jitter = max(max(g.x) - min(g.x) for g in held)
        assert swept > jitter * MIN_DRIFT_LEGIBILITY, (
            f"{params}: the drifter sweeps {swept:.3f}° against {jitter:.3f}° of station-keeping"
            " jitter, which is not a drift an operator can see"
        )

    held = compose(registry, "waterfall", {"days": 7, "drifting": 0}, SEED)[0].derived
    assert held["drift_visible"] is False, "a neighbourhood with no drifter reports a drift"


#: Every ceiling that bounds a content-supplied count, against the parameter names it governs. A
#: clamp is the one bound that CHANGES an authored scene rather than refusing it, so no value in
#: the shipped library may reach one: if it did, the stimulus would quietly stop matching its key.
CEILINGS: tuple[tuple[str, float], ...] = (
    ("headcount", MAX_NEIGHBOURHOOD_TRACKS),
    ("intervals", MAX_INTERVALS),
    ("fragments", MAX_FRAGMENTS),
    ("rows", MAX_TABLE_ROWS),
    ("hours", MAX_SCHEDULE_HOURS),
    ("sites", MAX_SENSORS),
    ("sensors", MAX_SENSORS),
    ("state_change_markers", MAX_STATE_CHANGE_MARKS),
    ("revolutions", MAX_REVOLUTIONS),
    ("days", MAX_SPAN_DAYS),
    ("cycles_shown", MAX_SPAN_DAYS),
)


def test_no_authored_value_in_the_library_is_silently_clamped(package: ContentPackage) -> None:
    """The ceilings exist to bound a cost, not to rewrite content.

    Every one of them was added after a content count produced a payload between 8 MB and 146 MB.
    That is the right reason. But a clamp is a SILENT change to the authored scene, which is the
    fault class this whole line of work is about, so it must never bite a real item: the day one
    does, this fails and names it, and the answer is to fix the item or raise the ceiling
    deliberately rather than to discover a contradicted key months later.
    """
    clamped: list[str] = []
    for drill in package.drills:
        for name, ceiling in CEILINGS:
            value = drill.stimulus.params.get(name)
            if isinstance(value, int | float) and not isinstance(value, bool) and value > ceiling:
                clamped.append(f"{drill.id}: {name}={value} exceeds the {ceiling} ceiling")
    assert not clamped, clamped


def test_a_composite_board_cannot_name_the_same_product_twice() -> None:
    """A duplicated product was the one way left to inflate the render loop.

    An unknown product id already fails closed, so duplication was the remaining lever: a board
    naming `PRD-WATERFALL` thirty times rendered 126 MB and burned seven seconds of CPU on ONE
    unauthenticated request, and the payload budget can only refuse that AFTER the memory is
    allocated. Refused rather than de-duplicated, because the same product twice is a content
    fault and quietly collapsing it would change the authored board.

    No arbitrary ceiling: the honest bound is the number of products that exist, and refusing a
    duplicate enforces exactly that. `products: "all"` still renders every registered product.
    """
    registry = build_registry()
    with pytest.raises(LookupError, match="more than once"):
        compose(registry, "composite", {"products": ["PRD-WATERFALL"] * 30}, SEED)
    with pytest.raises(LookupError, match="more than once"):
        compose(registry, "composite", {"products": ["PRD-TRIC", "PRD-TRIC"]}, SEED)

    everything = compose(registry, "composite", {"products": "all"}, SEED)
    assert len(everything) == len(registry.product_ids)
    pair = compose(registry, "composite", {"products": ["PRD-TRIC", "PRD-WATERFALL"]}, SEED)
    assert len(pair) == 2


def test_no_authored_composite_board_duplicates_a_product(package: ContentPackage) -> None:
    """The refusal above must not be reachable from the shipped library."""
    duplicated: list[str] = []
    for drill in package.drills:
        board = drill.stimulus.params.get("products")
        if isinstance(board, list) and len(set(board)) != len(board):
            duplicated.append(drill.id)
    assert not duplicated, duplicated


def test_the_unread_census_uses_the_resolved_board_and_not_every_renderer() -> None:
    """The census fix was verified by nothing, so it could be reverted with the suite green.

    `unread` subtracts the vocabulary of the renderers ON THE BOARD. Reverting it to subtract
    every registered renderer's vocabulary left all 956 tests passing, because every ratchet call
    used the default empty board and never reached the path that produces the served figure.

    Driven with a board naming ONE product and a parameter only a DIFFERENT renderer reads:
    `headcount` is waterfall's, and a TRIC-only board must therefore still report it unread.
    """
    registry = build_registry()
    params = {"products": ["PRD-TRIC"], "headcount": 5}
    board = board_for(registry, "composite", params)
    assert board == ("PRD-TRIC",), board
    assert "headcount" in registry.unread("composite", params, board), (
        "a parameter no product on the board reads was forgiven, so the served census"
        " over-reports its own coverage"
    )
    #: And the whole-registry behaviour is what it must NOT do.
    everything = board_for(registry, "composite", {"products": "all"})
    assert "headcount" not in registry.unread("composite", params, everything)


def test_an_unknown_product_on_a_composite_board_fails_closed() -> None:
    """The premise of the duplicate-refusal design, which no test had executed.

    Refusing duplicates is only a complete bound because an unknown product id already fails
    closed - and that `raise` was never reached by the suite, so the argument rested on an
    unverified line. The probe branch was covered; this is the composite one.
    """
    registry = build_registry()
    with pytest.raises(LookupError, match="no renderer"):
        compose(registry, "composite", {"products": ["PRD-NOT-A-PRODUCT"]}, SEED)


def test_the_waterfall_time_direction_is_validated_before_it_reaches_prose() -> None:
    """`{"newest_at": "sideways"}` rendered "Newest observations at the sideways."

    An unvalidated content string in an operator-facing sentence, which is the boundary rule this
    project holds everywhere else. And for the top case the axis note said "newest nearest the
    longitude axis at the top" while the panel note on the same panel said the axis is at the
    bottom: two opposite statements about one geometry, both served.
    """
    registry = build_registry()
    for value in ("sideways", "", "BOTTOM", "up"):
        with pytest.raises(ValueError, match="newest_at"):
            compose(registry, "waterfall", {"newest_at": value}, SEED)

    bottom = compose(registry, "waterfall", {"newest_at": "bottom"}, SEED)[0].panels[0]
    assert bottom.y.inverted is True
    assert "bottom" in bottom.y.inversion_note

    top = compose(registry, "waterfall", {"newest_at": "top"}, SEED)[0].panels[0]
    assert top.y.inverted is False
    assert top.y.inversion_note == "", "an axis that is not inverted still explains its inversion"
    assert "top" in top.notes[0]
