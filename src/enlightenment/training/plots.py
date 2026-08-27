"""Seeded data series for the drill surfaces. Deterministic, and physics where physics applies.

Three surfaces, one generator each, matching :class:`~enlightenment.content.PlotKind`. Every
generator takes the item id and a seed and returns the same series every time, which is what makes
the debrief able to redraw exactly what the operator was looking at from the run log alone.

**The Hill-frame surface uses the real Clohessy-Wiltshire solution from the physics core**, not a
drawn shape. That matters more than it looks: the discrimination the RPO items train is bounded
versus unbounded relative motion, and the closed-loop condition is a property of the dynamics
(`no_drift_alongtrack_rate_km_s`). Drawing a loop by hand would teach operators to recognise a
picture I invented rather than a signature the orbit produces.

**The longitude and range surfaces are shaped, and that is a stated limitation.** A real drift
history comes from a fit sequence over days and a real fragmentation spread comes from an energy
distribution; both are authoring jobs with a physics model behind them, and the flight plan puts
the noise model behind an offline characterisation pass that has not run yet. So these two
generators produce a series with the right SHAPE and the right sign conventions, with the noise
amplitude as a single parameter that the characterisation output replaces when it lands. Marked
here rather than left for a reader to discover, because a shaped series presented as measured data
is the "clean training data is negative training" failure the plan warns about.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from enlightenment.content import PlotKind
from enlightenment.physics import (
    RelativeState,
    no_drift_alongtrack_rate_km_s,
    propagate_relative,
)
from enlightenment.scenario import SeededRandom

#: Points per series. Enough to read a shape, few enough that the payload stays small and the
#: client can draw it inside the paint budget without decimating.
SERIES_POINTS: Final = 96

#: Geostationary mean motion, radians per second: one revolution per sidereal day. Written as the
#: division rather than a magic constant so the reader can see which day it is.
GEO_MEAN_MOTION_RAD_S: Final = 2.0 * 3.141592653589793 / 86164.0905

#: Noise amplitude, as a fraction of the series range. **Provisional.** The real figure is a
#: distribution per sensor, and it arrives from the offline UDL characterisation pass (flight plan
#: step 4) as versioned content. Until then this is one number and it is deliberately modest: too
#: much invented noise trains operators against imperfection that is not the real imperfection.
PROVISIONAL_NOISE_FRACTION: Final = 0.012


@dataclass(frozen=True, slots=True)
class Series:
    """One drawable series: a label, x values, y values, and the axis units.

    Units travel with the data rather than living in the client, so a surface cannot be relabelled
    by a front-end change while the numbers stay the same.
    """

    label: str
    x: tuple[float, ...]
    y: tuple[float, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "x": list(self.x), "y": list(self.y)}


@dataclass(frozen=True, slots=True)
class PlotData:
    """Everything the client needs to draw one drill surface, and nothing more.

    Deliberately carries NO answer, no accepted classification and no expert cue. This object is
    serialised to an unanswered drill, so anything in it is visible to the operator before they
    commit. The answer key never enters it.
    """

    kind: PlotKind
    x_label: str
    y_label: str
    series: tuple[Series, ...]
    #: Text equivalent of the surface, from the authored `plot_description`. Mandatory on the
    #: content model and carried through here, because a plot with no text equivalent fails the
    #: accessibility floor and the floors are code standards in this project.
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "x_label": self.x_label,
            "y_label": self.y_label,
            "series": [item.as_dict() for item in self.series],
            "description": self.description,
        }


def _jitter(rng: SeededRandom, value: float, scale: float) -> float:
    """Symmetric noise of amplitude `scale` about `value`."""
    return value + rng.uniform(-scale, scale)


def _longitude_drift(item_id: str, rng: SeededRandom, description: str) -> PlotData:
    """Sub-satellite longitude against time, for the manoeuvre items.

    The shape carries the discrimination: station keeping saws about a fixed mean, repositioning
    breaks out and holds a new rate, and the two artefact items produce a rate no platform can
    make. Which shape is drawn is chosen by item id rather than by a random draw, because the
    authored answer key belongs to a specific shape and pairing a random shape with a fixed key
    would score the operator against data they were never shown.
    """
    hours = tuple(index * 0.5 for index in range(SERIES_POINTS))
    centre = rng.uniform(-60.0, 60.0)
    noise = 0.004

    values: list[float] = []
    if item_id == "drill-station-keeping":
        # Saw about a fixed mean: drift one way, corrected back on a regular interval.
        period = 24.0
        amplitude = rng.uniform(0.05, 0.09)
        for hour in hours:
            phase = (hour % period) / period
            values.append(_jitter(rng, centre - amplitude / 2.0 + amplitude * phase, noise))
    elif item_id == "drill-repositioning":
        # Held box, then a break-out at a new constant rate that persists.
        break_at = rng.uniform(14.0, 20.0)
        rate = rng.uniform(0.35, 0.75) * rng.choice([-1.0, 1.0])
        for hour in hours:
            if hour < break_at:
                values.append(_jitter(rng, centre + 0.03 * ((hour % 12.0) / 12.0), noise))
            else:
                values.append(_jitter(rng, centre + rate * (hour - break_at) / 24.0, noise))
    else:
        # Both artefact items: a step between two fits whose epochs are almost coincident, so the
        # implied rate is absurd. Drawn as a near-vertical jump at the midpoint, which is exactly
        # how it presents to an analyst looking at two fits on one axis.
        step = rng.uniform(0.8, 1.6) * rng.choice([-1.0, 1.0])
        midpoint = SERIES_POINTS // 2
        for index, hour in enumerate(hours):
            base = centre + 0.02 * ((hour % 12.0) / 12.0)
            values.append(_jitter(rng, base + (step if index >= midpoint else 0.0), noise))

    return PlotData(
        kind=PlotKind.LONGITUDE_DRIFT,
        x_label="Hours since first fit",
        y_label="Sub-satellite longitude, degrees east",
        series=(Series(label="Sub-satellite longitude", x=hours, y=tuple(values)),),
        description=description,
    )


def _hill_relative(item_id: str, rng: SeededRandom, description: str) -> PlotData:
    """Relative motion in the along-track and radial plane, from the real CW solution.

    The bounded case sets the along-track rate to the no-drift value, which is the condition for a
    closed relative track; the unbounded case perturbs it, which opens the track. That is the
    discrimination the RPO items train, and it comes out of the dynamics rather than out of a
    drawing.
    """
    n = GEO_MEAN_MOTION_RAD_S
    radial = rng.uniform(0.6, 1.8)
    cross = 0.0

    if item_id == "drill-drift-by":
        # Along-track rate deliberately off the no-drift value, so the track does not close.
        along_rate = no_drift_alongtrack_rate_km_s(radial, n) * rng.uniform(2.2, 3.4)
    else:
        along_rate = no_drift_alongtrack_rate_km_s(radial, n)

    state = RelativeState(position_km=(radial, 0.0, cross), velocity_km_s=(0.0, along_rate, 0.0))
    period_seconds = 2.0 * 3.141592653589793 / n
    span = period_seconds * (1.0 if item_id == "drill-drift-by" else 2.0)
    step = span / (SERIES_POINTS - 1)

    radial_values: list[float] = []
    along_values: list[float] = []
    noise = radial * PROVISIONAL_NOISE_FRACTION

    for index in range(SERIES_POINTS):
        moment = propagate_relative(state, n, step * index)
        x, y, _z = moment.position_km
        if item_id == "drill-corrected-hold":
            # A loop that grows, then is pulled back. The growth is a slow radial inflation and
            # the snap-back is a reset of it: control authority made visible, which is the cue.
            cycle = (step * index) / period_seconds
            growth = 1.0 + 0.30 * (cycle % 1.0)
            x, y = x * growth, y * growth
        if item_id == "drill-indeterminate-rpo" and index % 11 != 0:
            # Wide gaps, so both a closed loop and an open pass fit the points. The item's correct
            # answer is "indeterminate", and it has to be genuinely indeterminate on the data.
            continue
        radial_values.append(_jitter(rng, x, noise))
        along_values.append(_jitter(rng, y, noise))

    return PlotData(
        kind=PlotKind.HILL_RELATIVE,
        x_label="Along-track offset, kilometres",
        y_label="Radial offset, kilometres",
        series=(Series(label="Relative position", x=tuple(along_values), y=tuple(radial_values)),),
        description=description,
    )


def _range_time(item_id: str, rng: SeededRandom, description: str) -> PlotData:
    """Range from the parent against time, one series per associated object.

    Piece count, spread and sign are what the separation-versus-breakup discrimination turns on,
    so those three are what vary between items: a couple of pieces one way and low energy, or many
    pieces both ways with a wide spread.
    """
    hours = tuple(index * 0.25 for index in range(SERIES_POINTS))

    if item_id == "drill-fragmentation":
        count, spread, symmetric = rng.integer(9, 14), 3.4, True
    elif item_id == "drill-early-ambiguity":
        count, spread, symmetric = 2, 1.1, True
    elif item_id == "drill-piece-manoeuvres":
        count, spread, symmetric = 4, 0.9, False
    else:
        count, spread, symmetric = 2, 0.6, False

    series: list[Series] = []
    for piece in range(count):
        rate = rng.uniform(0.15, spread)
        if symmetric and piece % 2 == 1:
            rate = -rate
        values: list[float] = []
        # One piece changes its own rate part-way through: a piece under control, which is the
        # decisive evidence against fragmentation and the cue that item trains.
        manoeuvres = item_id == "drill-piece-manoeuvres" and piece == 1
        change_at = rng.uniform(8.0, 14.0)
        second_rate = rate * rng.uniform(2.0, 3.0)
        for hour in hours:
            if manoeuvres and hour > change_at:
                distance = rate * change_at + second_rate * (hour - change_at)
            else:
                distance = rate * hour
            values.append(_jitter(rng, distance, spread * PROVISIONAL_NOISE_FRACTION))
        series.append(Series(label=f"Piece {piece + 1}", x=hours, y=tuple(values)))

    return PlotData(
        kind=PlotKind.RANGE_TIME,
        x_label="Hours since first detection",
        y_label="Range from parent, kilometres",
        series=tuple(series),
        description=description,
    )


def build_plot(*, item_id: str, plot_kind: PlotKind, seed: int, description: str) -> PlotData:
    """The plot for one drill instance. Same item and seed, same series, every time.

    The seed is the drill instance's, so the same item served twice looks different while the
    authored answer stays right: an operator who has seen this item before still has to read THIS
    instantiation, which is the plan's template-versus-instance split applied to the drill layer.
    """
    rng = SeededRandom(seed)
    if plot_kind is PlotKind.LONGITUDE_DRIFT:
        return _longitude_drift(item_id, rng, description)
    if plot_kind is PlotKind.HILL_RELATIVE:
        return _hill_relative(item_id, rng, description)
    return _range_time(item_id, rng, description)
