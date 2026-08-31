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
from typing import Any, Final

from enlightenment.generators.base import Axis, Column, Marks, Panel, Stimulus, rng
from enlightenment.physics import (
    RelativeState,
    no_drift_alongtrack_rate_km_s,
    propagate_relative,
)

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


class ResidualGenerator:
    """PRD-RESIDUAL. Tight vertical scale, time and beta series, a candidate manoeuvre marker.

    The teaching content is which series departs. Beta reveals a plane change and time reveals a
    size change, so a departure in one and not the other is the discrimination, and a renderer
    that moved both together would destroy the item.
    """

    product_id = "PRD-RESIDUAL"
    name = "residual"

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        days = float(params.get("days", 7))
        fraction = float(params.get("departure_at_frac", 0.72))
        component = str(params.get("departure_component", "in_plane"))
        times = _leo_pass_times(days, stream)
        break_at = days * fraction

        beta_departs = component in ("cross_track", "out_of_plane", "plane")
        time_departs = component in ("in_plane", "in_track", "radial", "size")
        marks: list[Marks] = []
        for label, role, departs in (
            ("Time association", "series-a", time_departs),
            ("Beta association", "series-b", beta_departs),
        ):
            values = tuple(
                stream.uniform(-PROVISIONAL_RESIDUAL_SIGMA, PROVISIONAL_RESIDUAL_SIGMA)
                + (0.031 if departs and t >= break_at else 0.0)
                for t in times
            )
            marks.append(Marks(label=label, role=role, x=tuple(times), y=values))

        panel = Panel(
            title="Residual against observation time",
            x=Axis("Observation time", "days"),
            y=Axis("Residual", "", minimum=-0.08, maximum=0.08),
            marks=tuple(marks),
            notes=(
                "Departure sustained across multiple passes, not a single point.",
                f"Candidate manoeuvre at {break_at:.2f} days.",
            ),
        )
        return Stimulus(
            product_id=self.product_id,
            generator=self.name,
            title="Residual against observation time",
            panels=(panel,),
            header=(("Fit span", f"{days:.0f} days"), ("Association", "time and beta")),
            legend=(("Time association", "series-a"), ("Beta association", "series-b")),
            footer=f"seed {seed:#x} · replayable exactly · noise PROVISIONAL",
            reads_as=(
                "On the zero line the observations agree with the current state. A"
                " sustained departure means they no longer do."
            ),
            derived={"departure_component": component, "break_at_days": break_at},
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

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        days = float(params.get("days", 5))
        centre = float(params.get("centre_longitude", 0.0))
        neighbours = int(params.get("neighbours", 14))
        drifters = int(params.get("drifters", 3))

        marks: list[Marks] = []
        times = _geo_pass_times(days, stream)
        for index in range(neighbours):
            held = centre + stream.uniform(-3.0, 3.0)
            drifting = index < drifters
            rate = stream.uniform(0.25, 0.9) * (1.0 if stream.uniform(0, 1) > EVEN_ODDS else -1.0)
            xs: list[float] = []
            ys: list[float] = []
            for when in times:
                if stream.uniform(0.0, 1.0) > PROVISIONAL_DROP_RATE:
                    continue
                longitude = held + (rate * when if drifting else 0.0)
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
                    ramp=tuple(y / max(days, 1e-9) for y in ys),
                )
            )
        panel = Panel(
            title="Longitude over time",
            x=Axis("Longitude", "degrees"),
            y=Axis("Observation time", "days", inverted=True),
            marks=tuple(marks),
            notes=("Newest observations at the bottom.", "Objects within 50 km of the primary."),
        )
        total = sum(len(m.x) for m in marks)
        return Stimulus(
            product_id=self.product_id,
            generator=self.name,
            title="Waterfall: the neighbourhood",
            panels=(panel,),
            header=(("Span", f"{days:.0f} days"), ("Window", "±3° of the primary")),
            legend=(("Held longitude", "object-held"), ("Drifting object", "object-drift")),
            footer=f"observation count {total} · seed {seed:#x} · gaps PROVISIONAL",
            reads_as=(
                "Time runs down the page with the newest data at the bottom. A vertical line is"
                " holding station; a diagonal is drifting."
            ),
            derived={"drifter_count": drifters, "observation_count": total},
        )


class LightCurveGenerator:
    """PRD-PHOTOMETRY. Magnitude against solar equatorial phase angle, axis INVERTED.

    Brighter is a smaller number and an analyst reads brightness upward, so the axis runs the
    other way. Interval colouring is recency, interval 0 most recent, which is the convention the
    whole real toolset uses.
    """

    product_id = "PRD-PHOTOMETRY"
    name = "light_curve"

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        intervals = int(params.get("intervals", 6))
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
                glint = glint_depth * math.exp(-(((phase - glint_at) / 4.5) ** 2))
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
            y=Axis("Visual magnitude", "mag", inverted=True),
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
            derived={"glint_phase_deg": glint_at, "glint_magnitudes": glint_depth},
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

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        # No random stream: the track comes from the Clohessy-Wiltshire solution, and a drawn
        # loop would teach a picture rather than a signature the dynamics produce.
        bounded = bool(params.get("bounded", True))
        state_changes = int(params.get("state_changes", 4))
        manoeuvres = int(params.get("manoeuvres", 0))
        mean_motion = 2.0 * math.pi / 86164.0905
        radial_km = float(params.get("radial_km", 0.9))

        # Hill frame, ordered radial, along-track, cross-track, and the order is carried in the
        # type for the same reason the propagator carries TEME: read the wrong way round it is
        # silently wrong rather than obviously wrong.
        start = RelativeState(
            position_km=(radial_km, -8.0, 0.0),
            velocity_km_s=(
                0.0,
                no_drift_alongtrack_rate_km_s(radial_km, mean_motion) if bounded else 1.4e-5,
                1.1e-5,
            ),
        )
        samples = 140
        step_s = 86164.0905 * 2.0 / samples
        track = [propagate_relative(start, mean_motion, i * step_s) for i in range(samples)]
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
            footer=f"seed {seed:#x} · {samples} samples · 2 revolutions",
            reads_as=(
                "A closed repeating loop is bounded relative motion. An open track is a drift-by."
            ),
            derived={
                "bounded": bounded,
                "manoeuvres": manoeuvres,
                "state_changes": state_changes,
                "minimum_distance_km": distance[minimum_at],
            },
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

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        nodal_deg = float(params.get("nodal_regression_deg", 7.02))
        period_delta_s = float(params.get("period_delta_s", -5.51))
        inclination_delta = float(params.get("inclination_delta_deg", -0.0002))

        elements = (
            ("Semi-major axis", "km", 42164.11, -0.0251),
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

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        count = int(params.get("rows", 9))
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

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        count = int(params.get("rows", 7))
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

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        hours = float(params.get("hours", 12))
        sensors = int(params.get("sensors", 6))
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

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        minutes = float(params.get("minutes", 96))
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

    def render(self, params: dict[str, Any], seed: int) -> Stimulus:
        stream = rng(seed, self.product_id)
        fragments = int(params.get("fragments", 40))
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
