"""The ten product renderers. Hand-written, one class per product, matching the real layouts.

**An idealised renderer produces a trainer that is easier than the job, which is the worst kind
of failure because nobody notices it.** Every requirement below is transcribed from the
`generator_contract` block of `product-layouts.json` and asserted by contract tests that read
that block, so a corrected layout fails the test and names the renderer:

● Waterfall is observation-level scatter at realistic density with realistic collection gaps.
● TRIC uses independent per-panel scales and marks state changes distinctly from manoeuvres.
● Residual uses a tight vertical scale with time and beta association series.
● Photometry plots against solar equatorial phase angle with an INVERTED magnitude axis.
● Neighbourhood populates every observed column, including delta-v, score and days to crossing.
● Every generator draws its imperfection from the noise model, not from uniform noise.

That last one is not yet satisfiable and is marked wherever it applies. The offline
characterisation pass has not run, so the amplitude, the pass cadence, the sensor bias and the
outlier rate remain parameters chosen here rather than figures measured there. `PROVISIONAL`
marks every one of them. Making a surface convincing before that pass runs makes the shortfall
harder to see, not smaller.

Pass structure IS implemented, from figures the owner supplied: a low-orbit object gets eight
passes a day in two groups, geostationary electro-optical is continuous through local night
except for solar exclusion, and passive radio frequency is essentially constant. Evenly sampled
data never makes an operator ask "is that a real change or the edge of a pass?", which is one of
the first questions the job requires.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from enlightenment.generators.base import Axis, Column, Marks, Panel, Stimulus, rng
from enlightenment.physics import (
    RelativeState,
    no_drift_alongtrack_rate_km_s,
    propagate_relative,
)
from enlightenment.scenario import SeededRandom

#: PROVISIONAL, every one of them. Replaced by the characterisation pass output as versioned
#: content; until then a single figure each, deliberately modest, because too much invented
#: imperfection trains an operator against imperfection that is not the real imperfection.
PROVISIONAL_RESIDUAL_SIGMA: Final = 0.004
PROVISIONAL_MAG_SIGMA: Final = 0.18
PROVISIONAL_LONGITUDE_SIGMA: Final = 0.012

#: Owner-supplied cadence, 30 August. Low orbit: eight passes a day in two groups.
LEO_PASSES_PER_DAY: Final = 8
LEO_PASS_GROUPS: Final = 2
#: Observations within one pass. A pass is minutes long against a day-scale axis, so a pass reads
#: as a tight vertical cluster rather than a segment.
OBS_PER_PASS: Final = 9

#: Geostationary electro-optical works through local night. Expressed as hours past midnight so
#: the window can cross it, which is why the end is past 24.
GEO_NIGHT_HOURS: Final = (18.0, 30.0)
HOURS_PER_DAY: Final = 24.0

#: Fraction of neighbourhood observations dropped, standing in for the gaps a real collection
#: schedule leaves. PROVISIONAL, like every other imperfection figure here.
PROVISIONAL_DROP_RATE: Final = 0.72

#: A coin flip, named so the comparison is not a bare literal. Drift direction is arbitrary.
EVEN_ODDS: Final = 0.5

#: How often a co-orbital row reports a sustained close approach as possible. PROVISIONAL.
PROVISIONAL_SUSTAINED_RATE: Final = 0.6

#: Residual departure sizes, in the plot's own units. PROVISIONAL like every other imperfection
#: figure here, and named separately because the two axes answer different questions: beta a
#: change of orbit PLANE, time a change of orbit SIZE.
BETA_DEPARTURE_DEG: Final = 0.031
TIME_DEPARTURE_S: Final = 0.028

#: Vertical half-range. `tight_y_scale` is authored on the items whose whole point is that the
#: departure is small against the noise, so the scale is part of the discrimination.
TIGHT_RESIDUAL_LIMIT: Final = 0.05
WIDE_RESIDUAL_LIMIT: Final = 0.08

#: Marker tooltip conversions. The residual axis is dimensionless in the product; the marker
#: quotes a period change in seconds and an inclination change in degrees, so the tooltip needs a
#: stated scale rather than an implied one. PROVISIONAL: the real product's scaling is not
#: documented in the material supplied, so these carry the same status as the noise figures.
PERIOD_SECONDS_PER_UNIT: Final = 200.0
INCLINATION_DEG_PER_UNIT: Final = 0.02

#: Geostationary semi-major axis, kilometres, and sidereal rotation in degrees per day. Standard
#: figures, both needed to turn an authored altitude change into the drift rate an item asks the
#: operator to estimate.
GEO_SEMI_MAJOR_AXIS_KM: Final = 42164.11
SIDEREAL_DEGREES_PER_DAY: Final = 360.9856

#: Range for a seeded altitude change, kilometres: large enough that the drift is worth reporting,
#: small enough to be an ordinary station-keeping error rather than a transfer.
SEEDED_ALTITUDE_DELTA_KM: Final = (4.0, 24.0)
DEFAULT_ALTITUDE_DELTA_KM: Final = -0.0251

#: Orbital periods, seconds. GEO is the sidereal day, which is the figure a geostationary
#: relative-motion plot is drawn against; the low-orbit figure is a representative 92-minute
#: revolution, matching the pass cadence used above.
GEO_PERIOD_S: Final = 86164.0905
LEO_PERIOD_S: Final = 92.0 * 60.0

#: Samples per revolution of relative motion. Enough that a loop reads as a curve rather than a
#: polygon, and the count scales with the authored revolutions so a six-revolution item is not
#: drawn at lower resolution than a two-revolution one.
TRIC_SAMPLES_PER_REVOLUTION: Final = 70

#: Residual along-track rates added to the no-drift condition, kilometres per second. PROVISIONAL.
#: `seeded_slow` is the authored case where the drift is only visible over several revolutions.
SLOW_DRIFT_RATE_KM_S: Final = 3.0e-6
FORCED_DRIFT_RATE_KM_S: Final = 1.4e-5
#: A small cross-track rate, so the three projections are genuinely three views and not two.
CROSS_TRACK_RATE_KM_S: Final = 1.1e-5

#: Size of an authored step change in brightness, magnitudes. PROVISIONAL: large enough to be
#: unambiguous against the scatter, because the item asking about it is about whether a change
#: happened at all, not about reading a marginal one.
STEP_CHANGE_MAGNITUDES: Final = 0.9

#: Labelled instants on a timeline axis. Five, to match the interface's five gridlines.
TIME_TICKS: Final = 5

#: The only two meaningful values for the waterfall's time direction. Validated rather than
#: defaulted, because the value reaches a sentence an operator reads.
NEWEST_AT_VALUES: Final = frozenset({"top", "bottom"})

#: Waterfall defaults, used only where the content states nothing.
DEFAULT_NEIGHBOURS: Final = 14
DEFAULT_DRIFTERS: Final = 3

#: Ceilings on every content-supplied count that sizes a loop, an allocation or a mark list.
#: `headcount` was capped alone, and nine other parameters then produced payloads between 8 MB
#: and 146 MB, three of which did not finish rendering at all - which a byte budget cannot see,
#: because the cost is spent before there are any bytes to measure. A count that reaches a range
#: needs a bound at the point it reaches it, not a check on what it produced.
MAX_INTERVALS: Final = 24
MAX_FRAGMENTS: Final = 400
MAX_TABLE_ROWS: Final = 60
MAX_SCHEDULE_HOURS: Final = 168.0
MAX_SENSORS: Final = 24
MAX_STATE_CHANGE_MARKS: Final = 40
MAX_REVOLUTIONS: Final = 12.0
MAX_SPAN_DAYS: Final = 60.0

#: The base of the SYNTHETIC epoch a waterfall's timeline is labelled from, and how far past it a
#: seed may place a window. Fixed rather than taken from the clock, because the same seed must
#: relabel the same surface identically on any machine and at any time.
SYNTHETIC_EPOCH_BASE: Final = datetime(2026, 1, 1, tzinfo=UTC)

#: How far past the base a seed may place a window START. Deliberately short of a full year by the
#: longest span a waterfall can cover, so no window crosses into a second calendar year: the tick
#: labels omit the year, and with a full-year span a window beginning in late December ran into
#: January, so "03 Jan 12:00Z" denoted either 2026 or 2027. Measured before the change: 80 labels
#: each denoting two instants a year apart. Constraining the span is cheaper than lengthening
#: every label, which would widen the axis gutter for no analytical gain.
SYNTHETIC_EPOCH_SPAN_HOURS: Final = int((365 - MAX_SPAN_DAYS) * 24)

#: Hard ceiling on tracks in one neighbourhood panel. A bound on a CONTENT-supplied count that
#: reaches an unauthenticated route, and a readability limit besides: `obs_count: 18000` was
#: briefly read as a headcount and produced 159 MB of JSON from one anonymous request.
MAX_NEIGHBOURHOOD_TRACKS: Final = 40

#: How far a CLAMPED drifter travels across the whole window, as a multiple of the station-keeping
#: box width. The travel is exactly `box x factor`, because the clamp divides by the window length
#: and the track then runs for that length.
#:
#: **Figures corrected at V0.26.3 to the measured ones.** This comment said 2.5 "put nineteen
#: degrees on an axis whose box is six". Nineteen is not reproducible from anything here: measured
#: at the shipped seed, factor 2.5 draws a 15.0° sweep across a 6.0° box, factor 1.2 draws 7.2°,
#: and factor 25.0 draws 150.0°. Fifteen is also the figure the test's own comment quotes, so the
#: two records disagreed and the unverifiable one was the one in the source.
#:
#: 2.5 was rejected for squeezing the held objects - the reference an operator judges the drifter
#: against - into the right-hand quarter of the panel. The drifter has to leave the box visibly
#: and the box has to stay readable, and 2.5 bought the first at the cost of the second.
DRIFT_EXCURSION_FACTOR: Final = 1.2

#: Where a drift starts when the content says only THAT it starts, as a fraction of the window.
DEFAULT_DRIFT_ONSET_FRACTION: Final = 0.35
DEFAULT_LONGITUDE_HALF_WIDTH_DEG: Final = 3.0
DEFAULT_GAP_START_FRACTION: Final = 0.45
DEFAULT_GAP_DAYS: Final = 1.4
#: Geostationary electro-optical passes in a day, used to turn a missed-pass count into a span.
GEO_PASSES_PER_DAY: Final = 12.0

#: A manoeuvre's along-track velocity change, as a FRACTION of the no-drift rate the track is
#: already flying. PROVISIONAL in size, but not in kind: expressed as a fraction because an
#: absolute figure is legible at one geometry and invisible at another, which is exactly how a
#: burn of 0.7% of the along-track rate came to be drawn as nothing while the item scored it.
BURN_FRACTION: Final = 0.08

#: Fewest samples in one segment between burns, so a large burn count cannot flatten the curve.
MIN_SEGMENT_SAMPLES: Final = 8

#: Fewest samples in a whole relative-motion track, whatever revolution count the content states.
MIN_TRIC_SAMPLES: Final = 24

#: Default separation where the content states none, kilometres.
DEFAULT_SEPARATION_KM: Final = 8.0
#: The authored words for a separation. `just_outside_threshold` is relative to the reporting
#: threshold in the content's own threshold block, so it is read from there, not fixed here.
CLOSE_SEPARATION_KM: Final = 1.2

#: Observation thinning by authored density. `starved` is the case an operator has to reason
#: about: a departure after a starved run may be a manoeuvre or a fit that simply decayed.
OBS_DENSITY_KEEP: Final[dict[str, float]] = {"dense": 1.0, "nominal": 0.55, "starved": 0.18}


def _departure_component(params: dict[str, Any]) -> str:
    """Which association departs, resolved from the content's OWN vocabulary.

    Three authored spellings reach this, and they must agree: an explicit
    `departure_component`, or the pair `beta_departs`/`time_stable`. The pair wins where both
    appear, because it is the more specific statement. Nothing is guessed: an item that names
    neither gets the in-plane case, which is the commonest departure and is stated in the
    derived facts so a debrief can see what was drawn.
    """
    if params.get("beta_departs"):
        return "out_of_plane"
    if params.get("time_stable"):
        return "out_of_plane"
    component = str(params.get("departure_component", "in_plane"))
    if component in ("cross_track", "out_of_plane", "plane"):
        return "out_of_plane"
    return "in_plane"


def _magnitude(authored: Any, default: float, stream: SeededRandom) -> float:
    """A departure size from the content, which may be a number, a word, or absent.

    `near_zero` and `seeded` both appear in the library. `near_zero` is not zero: the item that
    uses it asks an operator to read an inclination change that is present but small against a
    period change that is not, and rendering it as exactly zero would remove the judgement.
    """
    if isinstance(authored, int | float) and not isinstance(authored, bool):
        return float(authored)
    if authored == "near_zero":
        return default * 0.12
    if authored == "seeded":
        return default * stream.uniform(0.8, 1.4)
    return default


def _collection_gap(params: dict[str, Any], days: float) -> tuple[float, float]:
    """The authored observation gap, in days. Equal bounds mean no gap.

    A gap is not decoration. `departure_after_gap` is the item where the correct answer is that
    the departure is NOT assessable as a manoeuvre, because a long unobserved stretch degrades
    the fit on its own. Drawing the gap is what makes that answer available to the operator.
    """
    if not params.get("departure_after_gap"):
        return (0.0, 0.0)
    start = float(params.get("gap_start_frac", 0.55)) * days
    length = float(params.get("gap_len_hours", 40)) / HOURS_PER_DAY
    return (start, min(start + length, days))


def _thinned(times: list[float], density: Any, stream: SeededRandom) -> list[float]:
    """Keep a fraction of the pass observations according to the authored density."""
    keep = OBS_DENSITY_KEEP.get(str(density), 1.0)
    if keep >= 1.0:
        return times
    return [t for t in times if stream.uniform(0.0, 1.0) < keep]


def _leo_pass_times(days: float, stream: Any) -> list[float]:
    """Observation times in days, clustered into passes with the gaps between them real.

    Two groups a day, four passes to a group, one revolution apart inside a group. The long gap
    between groups is the part that matters: it is where an operator has to decide whether a
    change happened or the sensor simply stopped looking.
    """
    revolution_days = 92.0 / 1440.0
    per_group = LEO_PASSES_PER_DAY // LEO_PASS_GROUPS
    times: list[float] = []
    for day in range(math.ceil(days)):
        for group in range(LEO_PASS_GROUPS):
            group_start = day + 0.08 + group * 0.5 + stream.uniform(-0.02, 0.02)
            for index in range(per_group):
                start = group_start + index * revolution_days
                if start >= days:
                    continue
                times.extend(start + stream.uniform(0.0, 0.0035) for _ in range(OBS_PER_PASS))
    return sorted(t for t in times if 0.0 <= t <= days)


def _geo_pass_times(days: float, stream: Any) -> list[float]:
    """Geostationary electro-optical: continuous through local night, nothing in daylight."""
    times: list[float] = []
    night_start, night_end = GEO_NIGHT_HOURS
    for day in range(math.ceil(days)):
        hour = night_start
        while hour < night_end:
            when = day + (hour % HOURS_PER_DAY) / HOURS_PER_DAY
            if 0.0 <= when <= days:
                times.append(when + stream.uniform(-0.002, 0.002))
            hour += 0.25 + stream.uniform(0.0, 0.1)
    return sorted(times)


def _separation_km(params: dict[str, Any], stream: SeededRandom) -> float:
    """Separation in kilometres, from whichever of the three authored spellings is present.

    `separation_km` and `distance_km` may be a number or one of the content's words. The words
    are not decoration: `seeded_close` and `just_outside_threshold` are the cases where the whole
    item turns on how near the pair is, and rendering them all at the same distance removed the
    judgement the item exists to train.
    """
    for key in ("separation_km", "distance_km", "separation"):
        authored = params.get(key)
        if isinstance(authored, int | float) and not isinstance(authored, bool):
            return float(authored)
        if authored == "seeded_close":
            return CLOSE_SEPARATION_KM * stream.uniform(0.7, 1.3)
        if authored == "just_outside_threshold":
            return CLOSE_SEPARATION_KM
    return DEFAULT_SEPARATION_KM


def _drifter_count(params: dict[str, Any], neighbours: int) -> int:
    """How many of the neighbourhood are drifting, from the content's two authored spellings."""
    for key in ("drifting", "drifting_object"):
        authored = params.get(key)
        if isinstance(authored, bool):
            return 1 if authored else 0
        if isinstance(authored, int):
            return min(authored, neighbours)
    return min(DEFAULT_DRIFTERS, neighbours)


def _longitude_bounds(params: dict[str, Any]) -> tuple[float, float]:
    """The station-keeping box, degrees either side of the primary.

    Authored as a pair, a single half-width, or absent. A held object sits inside it and a
    drifter leaves it, which is the shape the product reads by.
    """
    authored = params.get("longitudinal_bounds")
    if isinstance(authored, list | tuple) and len(authored) == 2:  # noqa: PLR2004 - a pair
        return (float(authored[0]), float(authored[1]))
    if isinstance(authored, int | float) and not isinstance(authored, bool):
        return (-float(authored), float(authored))
    return (-DEFAULT_LONGITUDE_HALF_WIDTH_DEG, DEFAULT_LONGITUDE_HALF_WIDTH_DEG)


def _drift_rate(
    authored: Any, bounds: tuple[float, float], days: float, stream: SeededRandom
) -> tuple[float, float]:
    """The rate to DRAW and the rate to REPORT, which are not always the same number.

    DRL-0005 authors `derived_rate_deg_day: -22900000`, the real ASTRA 1M artefact from the
    flight plan: a tooling output that is physically impossible and that the operator is being
    trained to recognise as such. Drawn literally it spans 114 million degrees on an axis labelled
    in degrees, every station-kept object collapses into one pixel column, and the plot conveys
    nothing - so the item that teaches "distrust this figure" became the item that shows nothing.

    The absurd figure is REPORTED verbatim, in the header where the tooling would put it, and the
    drawn track is clamped to something the panel can express. The clamp is stated in the header
    and in `derived`, because a silently clamped plot would be its own lie.
    """
    if isinstance(authored, int | float) and not isinstance(authored, bool):
        reported = float(authored)
        span = abs(bounds[1] - bounds[0]) or DEFAULT_LONGITUDE_HALF_WIDTH_DEG
        limit = span * DRIFT_EXCURSION_FACTOR / max(days, 1.0)
        return (max(-limit, min(limit, reported)), reported)
    drawn = stream.uniform(0.25, 0.9) * (1.0 if stream.uniform(0, 1) > EVEN_ODDS else -1.0)
    return (drawn, drawn)


def _waterfall_gap(params: dict[str, Any], days: float) -> tuple[float, float]:
    """An authored collection gap, in days. Equal bounds mean continuous collection.

    `collection_gaps` and `missed_passes` are the two authored spellings. The gap is the reason
    an operator cannot say whether something changed, so it is drawn as absence rather than
    smoothed over.
    """
    for key in ("collection_gaps", "missed_passes"):
        authored = params.get(key)
        if isinstance(authored, bool) and authored:
            start = days * DEFAULT_GAP_START_FRACTION
            return (start, min(start + DEFAULT_GAP_DAYS, days))
        if isinstance(authored, int | float) and not isinstance(authored, bool) and authored > 0:
            start = days * DEFAULT_GAP_START_FRACTION
            return (start, min(start + float(authored) / GEO_PASSES_PER_DAY, days))
    return (0.0, 0.0)


def _burned_track(
    start: RelativeState,
    mean_motion: float,
    step_s: float,
    samples: int,
    burns: int,
    burn_km_s: float,
) -> list[RelativeState]:
    """The relative track, propagated in segments with a velocity change at each junction.

    **What a burn does here, stated accurately after getting it wrong twice.** An along-track
    velocity change is very nearly PARALLEL to the velocity it modifies, so it does not turn the
    track: measured at the burn vertices, the local turn angle is smaller than at a median
    sample. What it changes is the subsequent drift rate, in a discrete step - three burns give
    four segments whose along-track rates differ by roughly an order of magnitude, and with no
    burns the rate is constant. That step is the real signature and it is what makes the forced
    motion look forced.

    It is NOT a cusp, and two earlier versions of this docstring claimed one. Nor is the count
    reliably readable: a blind change-point detector over the distance panel finds no events at
    any burn count, because the natural loop dominates every local window. `_tric_derived`
    therefore refuses to score the count, and the gap is recorded there.

    The duplicate vertex the first version produced is gone, which was a separate and real fault:
    two identical samples draw as nothing while looking, in the data, like an event.
    """
    if burns <= 0:
        return [propagate_relative(start, mean_motion, i * step_s) for i in range(samples)]

    track: list[RelativeState] = []
    state = start
    #: At least a few samples per segment, so a burn count larger than the sample budget cannot
    #: divide by zero or leave a segment with no curve in it.
    segment = max(samples // (burns + 1), MIN_SEGMENT_SAMPLES)
    elapsed = 0
    for index in range(samples):
        if index and index % segment == 0 and track and index // segment <= burns:
            here = track[-1]
            state = RelativeState(
                position_km=here.position_km,
                velocity_km_s=(
                    here.velocity_km_s[0],
                    here.velocity_km_s[1] + burn_km_s,
                    here.velocity_km_s[2],
                ),
            )
            #: One step, not zero. Propagating by zero time reproduces the previous position
            #: exactly, which is the duplicate vertex this rewrite exists to remove: invisible to
            #: look at, and shaped in the data like a point where something happened.
            elapsed = 1
        track.append(propagate_relative(state, mean_motion, elapsed * step_s))
        elapsed += 1
    return track


def _tric_derived(facts: dict[str, Any], *, asks_for_count: bool) -> dict[str, Any]:
    """Server-side facts about the rendered track, including the answer when the item asks for it.

    `expected_value` is the fix for a control that had never executed: `computed_from_params` is
    the content's sentinel for a numeric answer the renderer must compute, the matcher reads it
    from `derived["expected_value"]`, and NO generator ever set it. Both numeric items in the
    library therefore resolved to `unscorable` every time. It is set here and only here for the
    item that asks how many manoeuvres are visible, and `Stimulus.for_client` strips the whole
    `derived` map, because in the browser this number IS the answer.
    """
    #: **The count is NOT scored, and this is a recorded gap rather than a shortcut.**
    #:
    #: `expected_value` was set here so DRL-0008 - "how many manoeuvres are visible in this
    #: relative motion?", tolerance zero - could be marked. Twice I claimed the burn was legible
    #: enough to support that, and twice the measurement said otherwise. What an along-track burn
    #: actually does is step the subsequent DRIFT RATE; it does not put a cusp in the track,
    #: because the velocity change is nearly parallel to the velocity it modifies. The step is
    #: real and measurable over a whole segment, and a blind change-point detector run over the
    #: distance panel finds NOTHING at any burn count, because the natural loop dominates every
    #: local window. An operator counting off the plot cannot reliably reach the authored number.
    #:
    #: So the item fails closed: no expected value, `match` refuses it as unscorable, and no
    #: rating moves. That is strictly better than the alternative it replaced, which took six
    #: rating points off an operator whose reading of the plot was correct.
    #:
    #: **For the content author:** this needs a decision, not more engine work. Either the item
    #: wants a product that marks state changes explicitly, or it wants a longer window where
    #: each regime is several revolutions, or it wants a different stimulus.
    del asks_for_count
    return facts


def _altitude_delta(params: dict[str, Any], stream: SeededRandom) -> float:
    """The semi-major axis change in kilometres, from the content or seeded on its instruction."""
    authored = params.get("altitude_delta_km")
    if isinstance(authored, int | float) and not isinstance(authored, bool):
        return float(authored)
    if authored == "seeded":
        return stream.uniform(SEEDED_ALTITUDE_DELTA_KM[0], SEEDED_ALTITUDE_DELTA_KM[1])
    return DEFAULT_ALTITUDE_DELTA_KM


def _geo_drift_rate_deg_day(altitude_delta_km: float) -> float:
    """Longitude drift rate in degrees per day for a semi-major axis change at geostationary.

    A raised orbit has a longer period, so the object falls behind the Earth's rotation and
    drifts WEST; the sign is negative on an eastward-positive longitude axis. To first order the
    rate is `-1.5 * (delta_a / a) * 360.99` - the derivative of the sidereal rotation rate with
    respect to semi-major axis, and the estimate an analyst makes at the desk. DRL-0004 asks for
    exactly this, so without it the item was permanently unscorable.
    """
    return -1.5 * (altitude_delta_km / GEO_SEMI_MAJOR_AXIS_KM) * SIDEREAL_DEGREES_PER_DAY


def _drift_onset(params: dict[str, Any], days: float) -> float:
    """When a drift starts, in days. A BOOLEAN is not a fraction, and reading it as one erased it.

    `drift_begins: true` multiplied by `days` put the onset at the END of the window, so not one
    sample drifted and DRL-0019 drew a perfectly held longitude while its key says the object has
    stopped station-keeping. The plot contradicted its own key - the fault this whole vocabulary
    rewrite exists to remove, reintroduced by a type confusion.

    `ceased_at_cycle` names the cycle station-keeping stopped, the same fact expressed the way
    the waterfall's own axis counts.
    """
    ceased = params.get("ceased_at_cycle")
    cycles = params.get("cycles_shown")
    if isinstance(ceased, int | float) and not isinstance(ceased, bool):
        if isinstance(cycles, int | float) and not isinstance(cycles, bool) and cycles:
            return days * min(float(ceased) / float(cycles), 1.0)
        return min(float(ceased), days)
    authored = params.get("drift_begins")
    if isinstance(authored, bool):
        return days * DEFAULT_DRIFT_ONSET_FRACTION if authored else 0.0
    if isinstance(authored, int | float):
        return days * float(authored)
    return 0.0


def _recency(observation_day: float, days: float) -> float:
    """Age of one observation as a fraction of the window: 0.0 is the newest, 1.0 the oldest.

    The interface's `ramp()` treats 0.0 as the most recent stop, so this must be AGE and not
    elapsed time. Passing elapsed time coloured the oldest end of the plot as the newest, in a
    product where red-for-recency is the first thing an operator reads.
    """
    if days <= 0:
        return 0.0
    return max(0.0, min(1.0, (days - observation_day) / days))


def _synthetic_window(days: float, seed: int) -> tuple[datetime, datetime]:
    """The window a synthetic waterfall covers, derived from the SEED and never from the clock.

    Deterministic on purpose, and it has to be: the debrief redraws exactly what the operator
    saw from the run log alone, so a timestamp read off the wall clock would relabel the same
    surface differently on every render and break the replay this project gates on.

    The epoch is therefore SYNTHETIC and the footer says so. It is not a claim about a real
    collection: no real observation is being asserted, the same way the noise amplitudes are
    marked PROVISIONAL rather than presented as measured.
    """
    offset_hours = seed % SYNTHETIC_EPOCH_SPAN_HOURS
    start = SYNTHETIC_EPOCH_BASE + timedelta(hours=offset_hours)
    return (start, start + timedelta(days=days))


def _moment(instant: datetime) -> str:
    """One timestamp, in the day-month-time form an operator reads on the real product."""
    return instant.strftime("%d %b %H:%MZ")


def _stamp(window_start: datetime, observation_day: float) -> str:
    """The timestamp of an observation given as a day offset into the window."""
    return _moment(window_start + timedelta(days=observation_day))


def _time_ticks(days: float, window_start: datetime) -> tuple[tuple[float, str], ...]:
    """Five labelled instants across the window, matching the interface's five gridlines."""
    return tuple(
        (days * index / (TIME_TICKS - 1), _stamp(window_start, days * index / (TIME_TICKS - 1)))
        for index in range(TIME_TICKS)
    )


class ResidualGenerator:
    """PRD-RESIDUAL. Tight vertical scale, time and beta series, a candidate manoeuvre marker.

    The teaching content is which series departs. **Beta reveals a change of orbit PLANE and time
    reveals a change of orbit SIZE**, so a departure in one and not the other is the whole
    discrimination, and a renderer that moved both together would destroy the item.

    Which is what the first version did, in the worst possible direction. It read only `days`,
    `departure_at_frac` and `departure_component`, so DRL-0034 - authored `beta_departs: true`
    with `time_stable: true` - fell to the in-plane default and drew TIME departing while beta
    stayed flat. The plot said the opposite of the key, and the operator who read it correctly
    was marked wrong. The vocabulary below is the content's, not this module's.
    """

    product_id = "PRD-RESIDUAL"
    name = "residual"
    reads = frozenset(
        {
            "days",
            "departure_at_frac",
            "departure_component",
            "beta_departs",
            "time_stable",
            "delta_inc_deg",
            "delta_period_s",
            "departure_after_gap",
            "gap_start_frac",
            "gap_len_hours",
            "obs_density",
            "tight_y_scale",
            "manoeuvre_marker",
        }
    )

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        days = min(float(params.get("days", 7)), MAX_SPAN_DAYS)
        fraction = float(params.get("departure_at_frac", 0.72))
        component = _departure_component(params)
        beta_departs = component == "out_of_plane"
        time_departs = component == "in_plane"

        times = _thinned(_leo_pass_times(days, stream), params.get("obs_density"), stream)
        gap_start, gap_end = _collection_gap(params, days)
        if gap_end > gap_start:
            times = [t for t in times if not gap_start <= t <= gap_end]
        break_at = max(days * fraction, gap_end)

        #: An item that names the sizes wants them legible against each other; one that does not
        #: gets the same provisional step. Either way the figure is stated, never implied.
        beta_step = _magnitude(params.get("delta_inc_deg"), BETA_DEPARTURE_DEG, stream)
        time_step = _magnitude(params.get("delta_period_s"), TIME_DEPARTURE_S, stream)

        marks: list[Marks] = []
        for label, role, departs, step in (
            ("Time association", "series-a", time_departs, time_step),
            ("Beta association", "series-b", beta_departs, beta_step),
        ):
            values = tuple(
                stream.uniform(-PROVISIONAL_RESIDUAL_SIGMA, PROVISIONAL_RESIDUAL_SIGMA)
                + (step if departs and t >= break_at else 0.0)
                for t in times
            )
            marks.append(Marks(label=label, role=role, x=tuple(times), y=values))

        limit = TIGHT_RESIDUAL_LIMIT if params.get("tight_y_scale") else WIDE_RESIDUAL_LIMIT
        notes = ["Departure sustained across multiple passes, not a single point."]
        if gap_end > gap_start:
            notes.append(
                f"No observations between {gap_start:.2f} and {gap_end:.2f} days"
                f" ({(gap_end - gap_start) * HOURS_PER_DAY:.0f} hour gap)."
            )
        if params.get("manoeuvre_marker"):
            notes.append(f"Provider marker at {break_at:.2f} days.")

        panel = Panel(
            title="Residual against observation time",
            x=Axis("Observation time", "days"),
            y=Axis("Residual", "", minimum=-limit, maximum=limit),
            marks=tuple(marks),
            notes=tuple(notes),
        )
        header = [("Fit span", f"{days:.0f} days"), ("Association", "time and beta")]
        if params.get("manoeuvre_marker"):
            header.append(
                (
                    "Marker",
                    f"period {time_step * PERIOD_SECONDS_PER_UNIT:+.1f} s,"
                    f" inclination {beta_step * INCLINATION_DEG_PER_UNIT:+.4f} deg",
                )
            )
        return Stimulus(
            product_id=self.product_id,
            generator=self.name,
            title="Residual against observation time",
            panels=(panel,),
            header=tuple(header),
            legend=(("Time association", "series-a"), ("Beta association", "series-b")),
            footer=f"seed {seed:#x} · replayable exactly · noise PROVISIONAL",
            reads_as=(
                "On the zero line the observations agree with the current state. A"
                " sustained departure means they no longer do."
            ),
            derived={
                "departure_component": component,
                "break_at_days": break_at,
                "gap_hours": (gap_end - gap_start) * HOURS_PER_DAY,
                "observations": len(times),
            },
        )


class WaterfallGenerator:
    """PRD-WATERFALL. Dense observation scatter, newest at the bottom, realistic gaps.

    Not clean traces. The structure IS the content: vertical stripes where an object is holding
    a longitude, diagonals where one is drifting, and empty regions where nothing was looking.
    The observed product shows objects within 50 km of the queried satellite, so this is the
    neighbourhood rather than a whole-sky view.
    """

    product_id = "PRD-WATERFALL"
    name = "waterfall"
    reads = frozenset(
        {
            "days",
            "cycles_shown",
            "headcount",
            "drifting",
            "drifting_object",
            "longitudinal_bounds",
            "drift_begins",
            "ceased_at_cycle",
            "derived_rate_deg_day",
            "newest_at",
            "collection_gaps",
            "missed_passes",
        }
    )

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        #: `cycles_shown` is the content's other spelling for the span. One product, two authored
        #: names, and reading only the first left every item drawn over the same window.
        days = min(float(params.get("days", params.get("cycles_shown", 5))), MAX_SPAN_DAYS)
        centre = 0.0

        #: How many objects are in the neighbourhood. The content authors `headcount` because on
        #: three items it IS the answer: the operator counts the distinct tracks.
        #:
        #: **`obs_count` is NOT a headcount and must never fall back to one.** It was briefly read
        #: as one, and DRL-0030 authors `obs_count: 18000`: 18,000 tracks, 2.6 million points and
        #: 159 MB of JSON from a single unauthenticated request. The cap is a second line, and it
        #: costs nothing an operator would notice: a waterfall panel is unreadable well below it.
        neighbours = min(int(params.get("headcount", DEFAULT_NEIGHBOURS)), MAX_NEIGHBOURHOOD_TRACKS)
        drifters = _drifter_count(params, neighbours)

        bounds = _longitude_bounds(params)
        drift_start = _drift_onset(params, days)

        #: Newest at the bottom is the convention of the real product, and one item authors the
        #: other direction on purpose: reading a plot whose axis has been flipped is the skill.
        #: Validated, because it reaches served PROSE. `{"newest_at": "sideways"}` rendered
        #: "Newest observations at the sideways." - an unvalidated content string in an
        #: operator-facing sentence, which is the boundary rule this project holds everywhere
        #: else. Two values are meaningful and anything else is a content fault.
        newest_at = str(params.get("newest_at", "bottom"))
        if newest_at not in NEWEST_AT_VALUES:
            raise ValueError(
                f"newest_at must be one of {sorted(NEWEST_AT_VALUES)}, not {newest_at!r}"
            )
        newest_at_bottom = newest_at == "bottom"

        marks: list[Marks] = []
        times = _geo_pass_times(days, stream)
        gap_start, gap_end = _waterfall_gap(params, days)
        drift_rate, reported_rate = _drift_rate(
            params.get("derived_rate_deg_day"), bounds, days, stream
        )
        for index in range(neighbours):
            held = centre + stream.uniform(bounds[0], bounds[1])
            drifting = index < drifters
            rate = drift_rate
            xs: list[float] = []
            ys: list[float] = []
            for when in times:
                if gap_start <= when <= gap_end:
                    continue
                if stream.uniform(0.0, 1.0) > PROVISIONAL_DROP_RATE:
                    continue
                elapsed = max(when - drift_start, 0.0)
                longitude = held + (rate * elapsed if drifting else 0.0)
                xs.append(
                    longitude
                    + stream.uniform(-PROVISIONAL_LONGITUDE_SIGMA, PROVISIONAL_LONGITUDE_SIGMA)
                )
                ys.append(when)
            marks.append(
                Marks(
                    label=("Drifting object" if drifting else "Held longitude"),
                    role=("object-drift" if drifting else "object-held"),
                    x=tuple(xs),
                    y=tuple(ys),
                    #: **Recency, and it was backwards.** `ramp(0)` is the most recent stop, and
                    #: this passed `y / days`, so the window START - the OLDEST observation in the
                    #: plot - was drawn in the most-recent colour while the newest end was drawn
                    #: as oldest. The geometry said newest at the bottom and the colour said
                    #: newest at the top, on the same panel, in a product where red-for-recency
                    #: is the convention an operator reads first. Age, normalised.
                    ramp=tuple(_recency(y, days) for y in ys),
                )
            )
        #: The vertical axis is a TIMELINE, so it is labelled with timestamps. "0.003" and "4.99"
        #: are the internals of the plot; an operator reads a date, correlates it against a pass
        #: schedule and a provider post, and says when something happened. Numbers cannot be
        #: correlated with anything.
        window_start, window_end = _synthetic_window(days, seed)
        panel = Panel(
            title="Longitude over time",
            x=Axis("Longitude", "degrees"),
            y=Axis(
                "Observation time",
                "UTC",
                #: Newest nearest the longitude axis at the bottom, which is the real product's
                #: convention. The parameter is honoured because the content authors it, and both
                #: live items say "bottom": NO item authors "top" today. An earlier comment here
                #: claimed one did "deliberately", which was invention about the content.
                inverted=newest_at_bottom,
                #: Only stated when the axis IS inverted. For the top case it said "newest
                #: nearest the longitude axis at the top" while the panel note on the same panel
                #: said the longitude axis is at the bottom: two opposite statements about one
                #: geometry, both served, which is the fault the register row itself names.
                inversion_note=(
                    "newest nearest the longitude axis at the bottom" if newest_at_bottom else ""
                ),
                ticks=_time_ticks(days, window_start),
            ),
            marks=tuple(marks),
            notes=(
                (
                    f"Newest observations at the {newest_at}, nearest the longitude axis."
                    if newest_at_bottom
                    else f"Newest observations at the {newest_at}. The longitude axis is at the"
                    " bottom, so time runs UP the page on this one."
                ),
                "Objects within 50 km of the primary.",
            )
            + (
                (
                    "No collection between"
                    f" {_stamp(window_start, gap_start)} and {_stamp(window_start, gap_end)}.",
                )
                if gap_end > gap_start
                else ()
            ),
        )
        total = sum(len(m.x) for m in marks)
        return Stimulus(
            product_id=self.product_id,
            generator=self.name,
            title="Waterfall: the neighbourhood",
            panels=(panel,),
            header=(
                ("Span", f"{days:.0f} days"),
                #: Marked HERE and not only in the footer. The timestamps appear in the header,
                #: the panel notes and five axis ticks, while the disclosure was one lowercase
                #: clause at the end of a four-part footer - and a screenshot carries the header
                #: without it. `gaps PROVISIONAL` on the same footer shows what an unmissable
                #: marker looks like in this codebase; this matches it.
                ("From (synthetic)", _stamp(window_start, 0.0)),
                ("To", _moment(window_end)),
                ("Window", f"{bounds[0]:+.1f}° to {bounds[1]:+.1f}° of the primary"),
            )
            + (
                (
                    (
                        "Reported rate",
                        f"{reported_rate:,.0f}°/day as reported; the track is drawn at"
                        f" {drift_rate:+.2f}°/day so the panel can show it",
                    ),
                )
                if drift_rate != reported_rate
                else ()
            ),
            legend=(("Held longitude", "object-held"), ("Drifting object", "object-drift")),
            footer=(
                f"observation count {total} · seed {seed:#x} · gaps PROVISIONAL"
                " · synthetic epoch, seeded"
            ),
            reads_as=(
                "Time runs down the page with the newest data at the bottom. A vertical line is"
                " holding station; a diagonal is drifting."
            ),
            derived={
                "drifter_count": drifters,
                "observation_count": total,
                "headcount": neighbours,
                "newest_at": newest_at,
                "gap_days": max(gap_end - gap_start, 0.0),
                "drift_onset_days": drift_start,
                #: Whether a drift is actually DRAWN. `drift_begins: true` was multiplied by the
                #: window and put the onset at its end, so nothing drifted while the item's key
                #: said the object had stopped station-keeping. A fact nobody could assert on is
                #: how that survived.
                "drift_visible": bool(drifters) and drift_start < days and drift_rate != 0.0,
                "drawn_rate_deg_day": drift_rate,
                "reported_rate_deg_day": reported_rate,
                "rate_clamped": drift_rate != reported_rate,
                #: The direction the renderer actually drew. DRL-0030 asks the operator to find
                #: the drifter and state its direction with `computed_from_params` as the key, so
                #: the answer is a fact about the surface. Longitude increases eastward.
                "expected_text": ("east",) if drift_rate > 0 else ("west",),
            },
        )


class LightCurveGenerator:
    """PRD-PHOTOMETRY. Magnitude against solar equatorial phase angle, axis INVERTED.

    Brighter is a smaller number and an analyst reads brightness upward, so the axis runs the
    other way. Interval colouring is recency, interval 0 most recent, which is the convention the
    whole real toolset uses.
    """

    product_id = "PRD-PHOTOMETRY"
    name = "light_curve"
    reads = frozenset({"intervals", "step_change", "phase_angle_shift"})

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        intervals = min(int(params.get("intervals", 6)), MAX_INTERVALS)
        #: A step change in brightness is a change of the object, not of the geometry. The item
        #: that authors it asks the operator to separate the two, so it has to be drawn.
        step_change = bool(params.get("step_change", False))
        phase_shift = float(params.get("phase_angle_shift", 0.0))
        glint_at = float(params.get("glint_phase_deg", 5.0))
        glint_depth = float(params.get("glint_magnitudes", 3.6))
        base = float(params.get("base_magnitude", 12.4))

        marks: list[Marks] = []
        for interval in range(intervals):
            low = -88.0 + interval * (176.0 / intervals)
            xs: list[float] = []
            ys: list[float] = []
            for _ in range(120):
                phase = low + stream.uniform(0.0, 176.0 / intervals)
                trend = base - 0.028 * abs(phase) * -1.0
                #: A step change is a real change of the object: the later intervals sit at a
                #: different brightness from the earlier ones, at the SAME phase angle, which is
                #: what separates it from a geometry effect.
                if step_change and interval < intervals / 2:
                    trend -= STEP_CHANGE_MAGNITUDES
                centre = glint_at + phase_shift * (interval / max(intervals - 1, 1))
                glint = glint_depth * math.exp(-(((phase - centre) / 4.5) ** 2))
                ys.append(
                    trend - glint + stream.uniform(-PROVISIONAL_MAG_SIGMA, PROVISIONAL_MAG_SIGMA)
                )
                xs.append(phase)
            marks.append(
                Marks(
                    label=f"Interval {interval}",
                    role=f"interval-{interval}",
                    x=tuple(xs),
                    y=tuple(ys),
                    ramp=(interval / max(intervals - 1, 1),) * len(xs),
                )
            )
        panel = Panel(
            title="Visual magnitude against solar equatorial phase angle",
            x=Axis("Solar equatorial phase angle", "degrees", minimum=-90.0, maximum=90.0),
            y=Axis("Visual magnitude", "mag", inverted=True, inversion_note="brighter upward"),
            marks=tuple(marks),
            notes=(f"Specular feature near {glint_at:.0f}°.", "Interval 0 is the most recent."),
        )
        return Stimulus(
            product_id=self.product_id,
            generator=self.name,
            title="Light curve",
            panels=(panel,),
            header=(("Display mode", "interval"), ("Intervals", str(intervals))),
            legend=tuple((f"Interval {i}", f"interval-{i}") for i in range(intervals)),
            footer=f"seed {seed:#x} · magnitude scatter PROVISIONAL",
            reads_as=(
                "Magnitude runs brighter upward. A narrow brightening near zero phase angle is a"
                " specular return."
            ),
            derived={
                "glint_phase_deg": glint_at,
                "glint_magnitudes": glint_depth,
                "step_change": step_change,
                "phase_angle_shift": phase_shift,
            },
        )


class TricGenerator:
    """PRD-TRIC. Six panels, INDEPENDENT per-panel scales, state changes marked distinctly.

    Three of the six are projections of the same relative motion, because one projection of a
    three-dimensional relative track is ambiguous. The Hill-frame track comes from the real
    Clohessy-Wiltshire solution in the physics core rather than a drawn shape: the discrimination
    is bounded against unbounded motion, and that is a property of the dynamics.
    """

    product_id = "PRD-TRIC"
    name = "tric"
    reads = frozenset(
        {
            "geometry",
            "revolutions",
            "ratio",
            "regime",
            "drift_rate",
            "manoeuvre_count",
            "actual_manoeuvres",
            "state_change_markers",
            "separation_km",
            "distance_km",
            "separation",
        }
    )

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        # A stream is drawn only for the authored quantities that say "seeded". The track itself
        # comes from the Clohessy-Wiltshire solution, because a drawn loop would teach a picture
        # rather than a signature the dynamics produce.
        stream = rng(seed, self.product_id)
        geometry = str(params.get("geometry", "nmc_stable"))

        #: The content's four geometries. `nmc_stable` and `nmc_entry` are bounded natural motion,
        #: `nmc_drifting` is natural motion with a residual along-track rate, and `fmc` is forced
        #: motion, which is the case that costs fuel. Bounded against unbounded IS the
        #: discrimination, so it is read from the authored geometry and never defaulted silently.
        bounded = geometry in ("nmc_stable", "nmc_entry")
        drifting = geometry == "nmc_drifting"

        # GEO is the regime in every tric item in the library, and it is stated rather than
        # assumed: a low-orbit mean motion draws a visibly different loop over the same window.
        regime = str(params.get("regime", "GEO"))
        period_s = GEO_PERIOD_S if regime.upper() == "GEO" else LEO_PERIOD_S
        mean_motion = 2.0 * math.pi / period_s

        #: How many manoeuvres the track actually contains. `actual_manoeuvres` is explicit;
        #: `manoeuvre_count: "seeded"` asks this renderer to choose, and the number it chooses is
        #: the answer to the item, so it reaches `derived["expected_value"]` and nowhere else.
        if "actual_manoeuvres" in params:
            manoeuvres = int(params["actual_manoeuvres"])
        elif params.get("manoeuvre_count") == "seeded":
            manoeuvres = stream.integer(1, 3)
        else:
            #: Natural motion is natural motion. Every `nmc_` geometry contains no burn by
            #: definition, INCLUDING the drifting one: a drifting circumnavigation is what an
            #: unmaintained relative orbit does, and calling it a manoeuvre teaches the operator
            #: to read decay as intent, which is the misconception the item exists to correct.
            manoeuvres = 1 if geometry == "fmc" else 0

        #: Marks along the track. **A reference state change is not a manoeuvre.** DRL-0026
        #: authors six markers with zero manoeuvres precisely so an operator learns to separate a
        #: new element set from a burn, so the two counts are independent by construction.
        state_changes = min(int(params.get("state_change_markers", 4)), MAX_STATE_CHANGE_MARKS)

        #: Separation sets the scale of the loop. Three authored spellings, all in kilometres or
        #: a word, and none of them invented here.
        separation_km = _separation_km(params, stream)
        radial_km = separation_km / max(float(params.get("ratio", 2.0)), 0.5)

        # Hill frame, ordered radial, along-track, cross-track, and the order is carried in the
        # type for the same reason the propagator carries TEME: read the wrong way round it is
        # silently wrong rather than obviously wrong.
        no_drift = no_drift_alongtrack_rate_km_s(radial_km, mean_motion)
        along_rate = no_drift
        if drifting:
            #: A drifting natural-motion circumnavigation is the no-drift rate plus a residual.
            #: `drift_rate: "seeded_slow"` is the authored case: slow enough that the drift is
            #: only visible over several revolutions, which is what makes the item a judgement.
            along_rate = no_drift + (
                SLOW_DRIFT_RATE_KM_S
                if params.get("drift_rate") == "seeded_slow"
                else FORCED_DRIFT_RATE_KM_S
            )
        elif not bounded:
            along_rate = no_drift + FORCED_DRIFT_RATE_KM_S

        start = RelativeState(
            position_km=(radial_km, -separation_km, 0.0),
            velocity_km_s=(0.0, along_rate, CROSS_TRACK_RATE_KM_S),
        )
        #: Authored revolutions, so a six-revolution item shows six and a four-revolution item
        #: does not show six. The window was fixed at two before, which erased the parameter.
        revolutions = min(float(params.get("revolutions", 2)), MAX_REVOLUTIONS)
        #: Floored. `samples` is content-driven arithmetic, and a revolution count below 1/70
        #: rounds it to zero, which divides by zero in the segment length. Not reachable from
        #: today's library - the authored values are 4 and 6 - but a bound on a content-supplied
        #: number costs one call and does not depend on the library staying as it is.
        samples = max(int(TRIC_SAMPLES_PER_REVOLUTION * revolutions), MIN_TRIC_SAMPLES)
        step_s = period_s * revolutions / samples
        #: The burn is a fraction of the motion the track already has, so it stays legible at
        #: whatever scale the geometry is drawn at.
        track = _burned_track(
            start, mean_motion, step_s, samples, manoeuvres, abs(no_drift) * BURN_FRACTION
        )
        radial = tuple(state.position_km[0] for state in track)
        along = tuple(state.position_km[1] for state in track)
        cross = tuple(state.position_km[2] for state in track)
        ramp = tuple(i / (samples - 1) for i in range(samples))
        distance = tuple(
            math.sqrt(a * a + r * r + c * c) for a, r, c in zip(along, radial, cross, strict=True)
        )
        minimum_at = distance.index(min(distance))

        change_x = tuple(
            along[int(i * samples / max(state_changes, 1))] for i in range(state_changes)
        )
        change_y = tuple(
            cross[int(i * samples / max(state_changes, 1))] for i in range(state_changes)
        )

        panels = (
            Panel(
                "Cross-track over in-track",
                Axis("In-track", "km"),
                Axis("Cross-track", "km"),
                marks=(
                    Marks("Relative track", "track", along, cross, glyph="line", ramp=ramp),
                    Marks(
                        "Reference state change", "state-change", change_x, change_y, glyph="square"
                    ),
                    Marks(
                        "Minimum distance",
                        "minimum",
                        (along[minimum_at],),
                        (cross[minimum_at],),
                        glyph="dot",
                    ),
                ),
            ),
            Panel(
                "Radial over in-track",
                Axis("In-track", "km"),
                Axis("Radial", "km"),
                marks=(Marks("Relative track", "track", along, radial, glyph="line", ramp=ramp),),
            ),
            Panel(
                "Radial over cross-track",
                Axis("Cross-track", "km"),
                Axis("Radial", "km"),
                marks=(Marks("Relative track", "track", cross, radial, glyph="line", ramp=ramp),),
            ),
            Panel(
                "Distance",
                Axis("Time", "hours"),
                Axis("Distance", "km"),
                marks=(
                    Marks(
                        "Separation",
                        "track",
                        tuple(i * step_s / 3600.0 for i in range(samples)),
                        distance,
                        glyph="line",
                        ramp=ramp,
                    ),
                    Marks(
                        "Minimum distance",
                        "minimum",
                        (minimum_at * step_s / 3600.0,),
                        (distance[minimum_at],),
                        glyph="dot",
                    ),
                ),
            ),
            Panel(
                "Solar aspect angle",
                Axis("Time", "hours"),
                Axis("Angle", "degrees"),
                marks=(
                    Marks(
                        "Aspect",
                        "track",
                        tuple(i * step_s / 3600.0 for i in range(samples)),
                        tuple(90.0 + 70.0 * math.sin(2.0 * math.pi * r) for r in ramp),
                        glyph="line",
                        ramp=ramp,
                    ),
                ),
            ),
            Panel(
                "Right ascension delta",
                Axis("Time", "hours"),
                Axis("Right ascension", "degrees"),
                steps=(
                    Marks(
                        "Fitted right ascension",
                        "state-change",
                        tuple(i * step_s / 3600.0 for i in range(samples)),
                        tuple(41.1 - 0.6 * float(int(r * state_changes)) for r in ramp),
                        glyph="step",
                    ),
                ),
                notes=("A staircase, not a curve. Each tread is a refit.",),
            ),
        )
        return Stimulus(
            product_id=self.product_id,
            generator=self.name,
            title="Relative motion",
            panels=panels,
            header=(
                ("Frame", "Hill, from the Clohessy-Wiltshire solution"),
                ("Panel scales", "independent"),
            ),
            legend=(
                ("Relative track, time gradient", "track"),
                ("Reference state change", "state-change"),
                ("Minimum distance", "minimum"),
            ),
            footer=f"seed {seed:#x} · {samples} samples · {revolutions:g} revolutions",
            reads_as=(
                "A closed repeating loop is bounded relative motion. An open track is a drift-by."
            ),
            derived=_tric_derived(
                {
                    "bounded": bounded,
                    "geometry": geometry,
                    "manoeuvres": manoeuvres,
                    "state_changes": state_changes,
                    "separation_km": separation_km,
                    "revolutions": revolutions,
                    "minimum_distance_km": distance[minimum_at],
                },
                asks_for_count=params.get("manoeuvre_count") == "seeded",
            ),
        )


class DcTableGenerator:
    """PRD-DC-TABLE. Initial, Final, Delta, in that fixed order.

    The order is load-bearing and it was corrected on 31 August: an earlier note read Initial,
    Delta, Final, which would have put the answer column in the wrong place in every rendered
    stimulus. Apogee runs before perigee in the specifics block, and that block is scored
    positionally, so an operator trained on the wrong order would be marked down for reproducing
    it.

    The delta column is not the manoeuvre. On the observed screen a right ascension change of
    about seven degrees is natural nodal regression across a fit interval of a day and a half.
    The manoeuvre is in the small in-plane numbers, and this renderer reproduces that deliberately
    rather than drawing a clean table.
    """

    product_id = "PRD-DC-TABLE"
    name = "dc_table"
    reads = frozenset(
        {
            "period_change_s",
            "period_delta_s",
            "plane_change_deg",
            "inclination_delta_deg",
            "include_natural_secular_drift",
            "nodal_regression_deg",
            "altitude_delta_km",
        }
    )

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        #: The content's spellings first, this module's older names second. `period_change_s` and
        #: `plane_change_deg` are what the items author; reading only the internal names meant a
        #: table authored with a 12-second period change rendered the default 5.51.
        nodal_deg = float(params.get("nodal_regression_deg", 7.02))
        if not params.get("include_natural_secular_drift", True):
            #: One item states the natural nodal regression is excluded, which changes which
            #: column an operator should attribute to the burn.
            nodal_deg = 0.0
        period_delta_s = float(params.get("period_change_s", params.get("period_delta_s", -5.51)))

        #: An altitude change at geostationary DETERMINES a longitude drift rate, and DRL-0004
        #: asks the operator to derive it. So the renderer must both draw the altitude change and
        #: know the answer it will be scored against; until this existed the sentinel resolved to
        #: nothing on every attempt and the item was permanently unscorable.
        altitude_delta_km = _altitude_delta(params, rng(seed, self.product_id))
        drift_deg_day = _geo_drift_rate_deg_day(altitude_delta_km)
        inclination_delta = float(
            params.get("plane_change_deg", params.get("inclination_delta_deg", -0.0002))
        )

        elements = (
            ("Semi-major axis", "km", GEO_SEMI_MAJOR_AXIS_KM, altitude_delta_km),
            ("Eccentricity", "", 0.000418, 0.000019),
            ("Inclination", "deg", 2.4471, inclination_delta),
            ("Right ascension", "deg", 40.02, nodal_deg),
            ("Argument of perigee", "deg", 271.4, 0.38),
            ("Mean anomaly", "deg", 88.7, 0.11),
            ("Period", "s", 86164.09, period_delta_s),
            ("Apogee height", "km", 35800.6, -0.019),
            ("Perigee height", "km", 35765.2, -0.031),
        )
        rows = tuple(
            {
                "element": name,
                "unit": unit,
                "initial": round(initial, 6),
                "final": round(initial + delta, 6),
                "delta": round(delta, 6),
                "natural": name == "Right ascension",
            }
            for name, unit, initial, delta in elements
        )
        return Stimulus(
            product_id=self.product_id,
            generator=self.name,
            title="Verified manoeuvre determination",
            columns=(
                Column("element", "Element"),
                Column("unit", "Unit"),
                Column("initial", "Initial", align="right"),
                Column("final", "Final", align="right"),
                Column("delta", "Delta", align="right", emphasis=True),
            ),
            rows=rows,
            header=(
                ("Fit interval", "1.5 days"),
                ("Column order", "Initial, Final, Delta"),
                ("Specifics order", "Apogee before perigee"),
            ),
            footer=f"seed {seed:#x} · one row is natural regression, not a burn",
            reads_as=(
                "The delta column is not the manoeuvre. A large right ascension change across a"
                " long fit is nodal regression."
            ),
            derived={
                "nodal_regression_deg": nodal_deg,
                "period_delta_s": period_delta_s,
                "manoeuvre_in": "in-plane",
                "natural_element": "Right ascension",
                "altitude_delta_km": altitude_delta_km,
                "expected_value": drift_deg_day,
                "expected_text": ("west",) if drift_deg_day < 0 else ("east",),
            },
        )


class NeighbourhoodGenerator:
    """PRD-NEIGHBORHOOD. Every observed column, the threshold block, filter toggles in real state.

    The columns are the product. Delta-v, score and days to longitude crossing are what turn a
    list of nearby objects into a ranked set of things worth attention, and a renderer missing
    them produces a screen that cannot support the decision the drill asks for.
    """

    product_id = "PRD-NEIGHBORHOOD"
    name = "neighbourhood"
    reads = frozenset({"rows"})

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        count = min(int(params.get("rows", 9)), MAX_TABLE_ROWS)
        rows: list[dict[str, Any]] = []
        for index in range(count):
            drifting = index % 4 == 0
            days_to_crossing = stream.uniform(0.4, 45.0) if drifting else None
            rows.append(
                {
                    "designator": f"OBJ-{1000 + index * 7}",
                    "class": "Payload" if index % 3 else "Rocket body",
                    "rank": stream.integer(0, 5),
                    "separation_km": round(stream.uniform(2.0, 190.0), 1),
                    "delta_v_ms": round(stream.uniform(0.0, 14.0), 2),
                    "score": round(stream.uniform(0.0, 1.0), 3),
                    "days_to_crossing": None
                    if days_to_crossing is None
                    else round(days_to_crossing, 1),
                    "drifting": drifting,
                    "elset_age_h": round(stream.uniform(0.5, 96.0), 1),
                }
            )
        rows.sort(key=lambda r: -float(r["score"]))
        return Stimulus(
            product_id=self.product_id,
            generator=self.name,
            title="Neighbourhood",
            columns=(
                Column("designator", "Object"),
                Column("class", "Class"),
                Column("rank", "Rank", align="right"),
                Column("separation_km", "Separation (km)", align="right"),
                Column("delta_v_ms", "Delta-v (m/s)", align="right"),
                Column("score", "Score", align="right", emphasis=True),
                Column("days_to_crossing", "Days to crossing", align="right"),
                Column("elset_age_h", "Element set age (h)", align="right"),
            ),
            rows=tuple(rows),
            header=(
                ("Thresholds", "resolved from the local file, PLACEHOLDER while unpopulated"),
                ("Filter: drifting", "on"),
                ("Filter: element set currency", "on"),
                ("Filter: 60-day exclusion", "on"),
            ),
            footer=f"seed {seed:#x} · {count} objects in the neighbourhood",
            reads_as=(
                "Proximity alone is not a signal. A drifting object crosses the belt"
                " continuously and almost none of its close approaches mean anything; slowing"
                " is the signal."
            ),
            derived={"drifting_count": sum(1 for r in rows if r["drifting"])},
        )


class CocoGenerator:
    """PRD-COCO. ASTAT bands, coplanar angle, right ascension rate, days to right ascension zero."""

    product_id = "PRD-COCO"
    name = "coco"
    reads = frozenset({"rows"})

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        count = min(int(params.get("rows", 7)), MAX_TABLE_ROWS)
        rows = tuple(
            {
                "designator": f"OBJ-{2000 + index * 3}",
                "astat": stream.choice([1, 2]),
                "coplanar_angle_deg": round(stream.uniform(0.02, 4.5), 3),
                "ra_dot_deg_day": round(stream.uniform(-0.08, 0.08), 4),
                "days_to_ra_zero": round(stream.uniform(1.0, 120.0), 1),
                "sustained_ca_possible": stream.uniform(0.0, 1.0) > PROVISIONAL_SUSTAINED_RATE,
            }
            for index in range(count)
        )
        return Stimulus(
            product_id=self.product_id,
            generator=self.name,
            title="Co-orbital coplanar",
            columns=(
                Column("designator", "Object"),
                Column("astat", "ASTAT", align="right"),
                Column("coplanar_angle_deg", "Coplanar angle (deg)", align="right"),
                Column("ra_dot_deg_day", "RA rate (deg/day)", align="right"),
                Column("days_to_ra_zero", "Days to RA zero", align="right", emphasis=True),
                Column("sustained_ca_possible", "Sustained CA possible"),
            ),
            rows=rows,
            header=(
                ("ASTAT 1", "fully associated"),
                ("ASTAT 2", "closely associated"),
                ("Bands", "resolved from the local threshold file"),
            ),
            footer=f"seed {seed:#x}",
            reads_as=(
                "Days to right ascension zero is when the planes align. A sustained close"
                " approach needs the planes to stay together, not merely to cross."
            ),
            derived={"sustained_count": sum(1 for r in rows if r["sustained_ca_possible"])},
        )


class PassScheduleGenerator:
    """PRD-PASS-SCHEDULE. One row per sensor with site identifiers, a now marker, and crossings."""

    product_id = "PRD-PASS-SCHEDULE"
    name = "pass_schedule"
    reads = frozenset({"hours", "sites", "sensors"})

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        hours = min(float(params.get("hours", 12)), MAX_SCHEDULE_HOURS)
        sensors = min(int(params.get("sites", params.get("sensors", 6))), MAX_SENSORS)
        phenomenology = ["Optical", "Radar", "Phased array", "Passive RF", "On orbit"]
        marks: list[Marks] = []
        for index in range(sensors):
            kind = phenomenology[index % len(phenomenology)]
            constant = kind == "Passive RF"
            xs: list[float] = []
            ys: list[float] = []
            when = stream.uniform(0.0, 1.5)
            while when < hours:
                span = 0.25 if not constant else 1.0
                for step in range(4):
                    xs.append(when + step * span / 4.0)
                    ys.append(float(index))
                when += span + (0.0 if constant else stream.uniform(0.8, 3.2))
            marks.append(
                Marks(
                    label=f"SITE-{index + 1} · {kind}",
                    role=f"phenomenology-{index % len(phenomenology)}",
                    x=tuple(xs),
                    y=tuple(ys),
                    glyph="bar",
                )
            )
        panel = Panel(
            title="Sensor availability",
            x=Axis("Time from now", "hours"),
            y=Axis("Sensor", ""),
            marks=tuple(marks),
            notes=(
                "Passive radio frequency is essentially constant; optical is not.",
                "Node, apogee and perigee crossings marked on the time axis.",
            ),
        )
        return Stimulus(
            product_id=self.product_id,
            generator=self.name,
            title="Pass schedule",
            panels=(panel,),
            header=(("Group mode", "phenomenology"), ("Window", f"{hours:.0f} hours")),
            legend=tuple(
                (phenomenology[i % len(phenomenology)], f"phenomenology-{i % len(phenomenology)}")
                for i in range(min(sensors, len(phenomenology)))
            ),
            footer=f"seed {seed:#x} · now marker at zero",
            reads_as=(
                "A sensor type that physically cannot collect in the window is not a tasking"
                " option, whatever the schedule shows."
            ),
            derived={"sensor_count": sensors},
        )


class EphemerisGenerator:
    """PRD-EPHEMERIS. A state vector series with the reference frame stated.

    The reading rule that matters on an ascent profile: an osculating perigee radius below the
    Earth's surface separates a ballistic ascent from an orbit, and it is the fastest read there
    is. Exercise data is fitted rather than propagated, so specific orbital energy drifts across
    the file; a generator emitting a clean two-body propagation would not look like the real
    thing.
    """

    product_id = "PRD-EPHEMERIS"
    name = "ephemeris"
    reads = frozenset({"minutes", "elapsed_min", "ballistic"})

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        #: NOT clamped. This renderer draws a fixed 96 samples whatever the span, so a ceiling
        #: here bounds no cost, and its only possible effect is to silently redraw an authored
        #: time span as a shorter one - the fault class this whole line of work is about. A clamp
        #: CHANGES the authored scene rather than refusing it, so it is only justified where it
        #: prevents a real cost. `MAX_EPHEMERIS_MINUTES` was deleted for exactly that reason.
        minutes = float(params.get("elapsed_min", params.get("minutes", 96)))
        ballistic = bool(params.get("ballistic", False))
        samples = 96
        earth_radius = 6378.137
        xs = tuple(i * minutes / samples for i in range(samples))
        apogee = tuple(earth_radius + 180.0 + 1200.0 * math.sin(math.pi * x / minutes) for x in xs)
        perigee_value = earth_radius - 240.0 if ballistic else earth_radius + 165.0
        perigee = tuple(
            perigee_value + 26.0 * math.sin(2.4 * math.pi * x / minutes) + stream.uniform(-4.0, 4.0)
            for x in xs
        )
        energy = tuple(-29.5 * (1.0 + 0.06 * x / minutes) for x in xs)
        panels = (
            Panel(
                "Osculating radii",
                Axis("Time from epoch", "minutes"),
                Axis("Radius", "km"),
                marks=(
                    Marks("Apogee radius", "series-a", xs, apogee, glyph="line"),
                    Marks("Perigee radius", "series-b", xs, perigee, glyph="line"),
                    Marks(
                        "Earth radius",
                        "reference",
                        (xs[0], xs[-1]),
                        (earth_radius, earth_radius),
                        glyph="line",
                    ),
                ),
                notes=(
                    "A perigee radius below the Earth's surface is a ballistic ascent,"
                    " not an orbit.",
                ),
            ),
            Panel(
                "Specific orbital energy",
                Axis("Time from epoch", "minutes"),
                Axis("Energy", "km²/s²"),
                marks=(Marks("Energy", "series-a", xs, energy, glyph="line"),),
                notes=(
                    "Fitted, not propagated: energy drifts about six per cent across the file.",
                ),
            ),
        )
        return Stimulus(
            product_id=self.product_id,
            generator=self.name,
            title="Ephemeris",
            panels=panels,
            header=(("Reference frame", "TEME of epoch"), ("Source", "exercise, fitted")),
            legend=(
                ("Apogee radius", "series-a"),
                ("Perigee radius", "series-b"),
                ("Earth radius", "reference"),
            ),
            footer=f"seed {seed:#x} · {samples} states · {minutes:.0f} minutes",
            reads_as=(
                "Read the perigee against the Earth's radius first. Everything else follows"
                " from whether this is an orbit."
            ),
            derived={"ballistic": ballistic, "perigee_below_surface": perigee_value < earth_radius},
        )


class GabbardGenerator:
    """PRD-GABBARD. Apogee and perigee altitude against period, parent orbit marked.

    The only product with no observed layout, so this renderer is built from the product
    definition alone, which is weaker. The validator warns about it and the warning is correct.
    """

    product_id = "PRD-GABBARD"
    name = "gabbard"
    reads = frozenset({"fragments", "parent_period_min", "parent_altitude_km", "spread"})

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        fragments = min(int(params.get("fragments", 40)), MAX_FRAGMENTS)
        parent_period = float(params.get("parent_period_min", 101.4))
        parent_altitude = float(params.get("parent_altitude_km", 780.0))
        spread = float(params.get("spread", 1.0))

        apogee_x: list[float] = []
        apogee_y: list[float] = []
        perigee_x: list[float] = []
        perigee_y: list[float] = []
        for _ in range(fragments):
            kick = stream.uniform(-1.0, 1.0) * spread
            period = parent_period + kick * 6.0
            apogee_x.append(period)
            apogee_y.append(parent_altitude + abs(kick) * 260.0)
            perigee_x.append(period)
            perigee_y.append(parent_altitude - abs(kick) * 240.0)
        panel = Panel(
            title="Apogee and perigee altitude against period",
            x=Axis("Period", "minutes"),
            y=Axis("Altitude", "km"),
            marks=(
                Marks("Apogee", "series-a", tuple(apogee_x), tuple(apogee_y), glyph="cross"),
                Marks("Perigee", "series-b", tuple(perigee_x), tuple(perigee_y), glyph="cross"),
                Marks(
                    "Parent orbit", "reference", (parent_period,), (parent_altitude,), glyph="dot"
                ),
            ),
            notes=("The crossing point is the parent orbit.",),
        )
        return Stimulus(
            product_id=self.product_id,
            generator=self.name,
            title="Gabbard diagram",
            panels=(panel,),
            header=(("Fragments", str(fragments)), ("Layout", "from the product definition only")),
            legend=(("Apogee", "series-a"), ("Perigee", "series-b"), ("Parent orbit", "reference")),
            footer=f"seed {seed:#x} · no observed layout for this product",
            reads_as=(
                "A narrow X opening from one point is a low-energy event. A wide fan is energetic."
            ),
            derived={"fragments": fragments, "spread": spread},
        )


ALL_GENERATORS: Final = (
    ResidualGenerator(),
    WaterfallGenerator(),
    LightCurveGenerator(),
    TricGenerator(),
    DcTableGenerator(),
    NeighbourhoodGenerator(),
    CocoGenerator(),
    PassScheduleGenerator(),
    EphemerisGenerator(),
    GabbardGenerator(),
)
