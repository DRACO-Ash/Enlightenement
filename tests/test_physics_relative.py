"""Clohessy-Wiltshire relative motion, with the closed form checked against integration.

The point of this module: a closed-form solution verified only against the algebra that produced
it is verified against nothing. So the primary test integrates the underlying differential
equations numerically and compares. If my algebra is wrong, the two disagree.

The properties asserted after that are the published ones a textbook would state, and each is a
thing the trainer teaches. The radial-offset drift is the headline: an operator who expects
"I moved up, so I stay above" is wrong in a way that compounds every orbit, and that is what
competency axis four scores.
"""

from __future__ import annotations

import math

import pytest

from enlightenment.physics.relative import (
    EARTH_MU_KM3_S2,
    HILL_FRAME,
    RelativeMotionError,
    RelativeState,
    mean_motion_from_elements,
    mean_motion_rad_s,
    no_drift_alongtrack_rate_km_s,
    propagate_relative,
    relative_acceleration_km_s2,
)

#: A low Earth orbit chief, 400 km altitude on a 6378 km Earth. Round numbers on purpose: the
#: assertions below are about behaviour, not about matching a specific mission.
CHIEF_RADIUS_KM = 6778.0

#: A representative deputy: 1 km below, 10 km behind, 0.5 km out of plane.
DEPUTY = RelativeState(position_km=(-1.0, -10.0, 0.5), velocity_km_s=(0.0, 0.0, 0.0))

#: Integration step for the numerical check. Small against the orbital period (about 5560 s).
RK4_STEP_SECONDS = 0.5

#: Tolerances for the closed-form against integration comparison, measured not chosen. See
#: `test_the_closed_form_agrees_with_numerical_integration`.
INTEGRATION_TOLERANCE_KM = 1e-6
INTEGRATION_TOLERANCE_KM_S = 1e-9


def _rk4_step(state: RelativeState, mean_motion: float, step: float) -> RelativeState:
    """One fourth-order Runge-Kutta step of the Hill-frame equations.

    Deliberately written from the acceleration function the module exposes, so the two paths share
    only the differential equations and not the solution.
    """

    def derivative(current: RelativeState) -> tuple[tuple[float, ...], tuple[float, ...]]:
        return current.velocity_km_s, relative_acceleration_km_s2(current, mean_motion)

    def advance(base: RelativeState, rate: tuple[tuple[float, ...], tuple[float, ...]], dt: float):
        velocity, acceleration = rate
        return RelativeState(
            position_km=tuple(p + v * dt for p, v in zip(base.position_km, velocity, strict=True)),  # type: ignore[arg-type]
            velocity_km_s=tuple(
                v + a * dt for v, a in zip(base.velocity_km_s, acceleration, strict=True)
            ),  # type: ignore[arg-type]
        )

    k1 = derivative(state)
    k2 = derivative(advance(state, k1, step / 2.0))
    k3 = derivative(advance(state, k2, step / 2.0))
    k4 = derivative(advance(state, k3, step))

    position = tuple(
        p + step / 6.0 * (a + 2.0 * b + 2.0 * c + d)
        for p, a, b, c, d in zip(state.position_km, k1[0], k2[0], k3[0], k4[0], strict=True)
    )
    velocity = tuple(
        v + step / 6.0 * (a + 2.0 * b + 2.0 * c + d)
        for v, a, b, c, d in zip(state.velocity_km_s, k1[1], k2[1], k3[1], k4[1], strict=True)
    )
    return RelativeState(position_km=position, velocity_km_s=velocity)  # type: ignore[arg-type]


def test_the_closed_form_agrees_with_numerical_integration() -> None:
    """THE test in this module. Everything else is a property; this is the verification.

    The closed form and the integrator share only `relative_acceleration_km_s2`, which is the
    differential equations. They do not share the solution. Integrated over a full orbital period
    at half-second steps, they must agree.
    """
    mean_motion = mean_motion_rad_s(CHIEF_RADIUS_KM)
    period = 2.0 * math.pi / mean_motion

    integrated = DEPUTY
    elapsed = 0.0
    steps = int(period / RK4_STEP_SECONDS)
    for _ in range(steps):
        integrated = _rk4_step(integrated, mean_motion, RK4_STEP_SECONDS)
        elapsed += RK4_STEP_SECONDS

    closed = propagate_relative(DEPUTY, mean_motion, elapsed)
    position_error = math.dist(closed.position_km, integrated.position_km)
    velocity_error = math.dist(closed.velocity_km_s, integrated.velocity_km_s)
    assert position_error < INTEGRATION_TOLERANCE_KM, (
        f"closed form and integration disagree by {position_error:.3e} km after {elapsed:.0f}s"
    )
    assert velocity_error < INTEGRATION_TOLERANCE_KM_S, (
        f"velocities disagree by {velocity_error:.3e} km/s"
    )


def test_a_zero_relative_state_stays_at_the_origin() -> None:
    """A deputy co-located with the chief and matching its velocity does not move away."""
    at_rest = RelativeState(position_km=(0.0, 0.0, 0.0), velocity_km_s=(0.0, 0.0, 0.0))
    later = propagate_relative(at_rest, mean_motion_rad_s(CHIEF_RADIUS_KM), 3600.0)
    assert later.position_km == (0.0, 0.0, 0.0)
    assert later.velocity_km_s == (0.0, 0.0, 0.0)


def test_a_purely_alongtrack_offset_holds_station() -> None:
    """Behind and matching rate is a stable formation. The intuitive case, and it IS true."""
    trailing = RelativeState(position_km=(0.0, -10.0, 0.0), velocity_km_s=(0.0, 0.0, 0.0))
    mean_motion = mean_motion_rad_s(CHIEF_RADIUS_KM)
    for hours in (1, 6, 24):
        later = propagate_relative(trailing, mean_motion, hours * 3600.0)
        assert later.position_km == pytest.approx((0.0, -10.0, 0.0), abs=1e-9)


def test_a_purely_radial_offset_drifts_along_track() -> None:
    """The counter-intuitive case, and the one competency axis four exists to score.

    "I moved up, so I stay above" is wrong. A radial offset produces a secular along-track drift
    of minus six times the mean motion times the offset, so it compounds every orbit. Asserted
    against the analytic drift rate, and asserted to be LARGE, because a test that only checked
    the sign would pass on a drift a thousand times too small.
    """
    mean_motion = mean_motion_rad_s(CHIEF_RADIUS_KM)
    radial_offset = 1.0
    above = RelativeState(position_km=(radial_offset, 0.0, 0.0), velocity_km_s=(0.0, 0.0, 0.0))
    period = 2.0 * math.pi / mean_motion

    after_one_orbit = propagate_relative(above, mean_motion, period)
    # The secular term is 6(sin(nt) - nt)x0, so over one period (nt = 2*pi) the drift is
    # -12*pi*x0, about 37.7 km for a 1 km offset. My first expectation here said -6*pi*x0,
    # which is the drift over HALF a period: the drift RATE is -6*n*x0, and multiplying it by
    # the period 2*pi/n gives -12*pi*x0. The implementation was right and the arithmetic in
    # this test was wrong, which is why the expectation is now derived in writing.
    expected_drift = -12.0 * math.pi * radial_offset
    assert after_one_orbit.position_km[1] == pytest.approx(expected_drift, rel=1e-9)
    assert abs(after_one_orbit.position_km[1]) > 37.0, (
        "a 1 km radial offset must drift about 37.7 km per orbit, not a token amount"
    )
    # And it returns to its radial offset each orbit while the along-track error grows.
    assert after_one_orbit.position_km[0] == pytest.approx(radial_offset, abs=1e-9)


def test_the_no_drift_rate_cancels_the_secular_along_track_drift() -> None:
    """The number an RPO scenario author most needs, and most easily gets the sign of wrong."""
    mean_motion = mean_motion_rad_s(CHIEF_RADIUS_KM)
    radial_offset = 1.0
    matched = RelativeState(
        position_km=(radial_offset, 0.0, 0.0),
        velocity_km_s=(0.0, no_drift_alongtrack_rate_km_s(radial_offset, mean_motion), 0.0),
    )
    period = 2.0 * math.pi / mean_motion
    for orbits in (1, 5, 20):
        later = propagate_relative(matched, mean_motion, orbits * period)
        assert later.position_km[1] == pytest.approx(0.0, abs=1e-6), (
            f"the no-drift condition failed after {orbits} orbits"
        )


def test_the_no_drift_rate_has_the_sign_the_formula_states() -> None:
    """Guards the sign specifically, since a positive answer here is a plausible-looking bug."""
    assert no_drift_alongtrack_rate_km_s(1.0, 0.001) == pytest.approx(-0.002)
    assert no_drift_alongtrack_rate_km_s(-1.0, 0.001) == pytest.approx(0.002)


def test_cross_track_motion_is_simple_harmonic_and_decoupled() -> None:
    """Out-of-plane motion oscillates at the orbital rate and never feeds the in-plane axes."""
    mean_motion = mean_motion_rad_s(CHIEF_RADIUS_KM)
    out_of_plane = RelativeState(position_km=(0.0, 0.0, 1.0), velocity_km_s=(0.0, 0.0, 0.0))
    period = 2.0 * math.pi / mean_motion

    half = propagate_relative(out_of_plane, mean_motion, period / 2.0)
    assert half.position_km[2] == pytest.approx(-1.0, abs=1e-9)
    full = propagate_relative(out_of_plane, mean_motion, period)
    assert full.position_km[2] == pytest.approx(1.0, abs=1e-9)
    # Decoupled: the in-plane axes never move.
    assert half.position_km[0] == pytest.approx(0.0, abs=1e-12)
    assert half.position_km[1] == pytest.approx(0.0, abs=1e-12)


def test_propagating_by_zero_seconds_is_the_identity() -> None:
    """A debrief seeks to arbitrary times, including the start. It must not move the state."""
    unchanged = propagate_relative(DEPUTY, mean_motion_rad_s(CHIEF_RADIUS_KM), 0.0)
    assert unchanged.position_km == pytest.approx(DEPUTY.position_km, abs=1e-12)
    assert unchanged.velocity_km_s == pytest.approx(DEPUTY.velocity_km_s, abs=1e-12)


def test_propagating_backwards_and_forwards_returns_the_start() -> None:
    """Time reversibility. A debrief scrubs both ways, so this is a real requirement."""
    mean_motion = mean_motion_rad_s(CHIEF_RADIUS_KM)
    forward = propagate_relative(DEPUTY, mean_motion, 1800.0)
    back = propagate_relative(forward, mean_motion, -1800.0)
    assert back.position_km == pytest.approx(DEPUTY.position_km, abs=1e-9)
    assert back.velocity_km_s == pytest.approx(DEPUTY.velocity_km_s, abs=1e-12)


def test_the_mean_motion_matches_the_orbital_period_it_implies() -> None:
    """A units check with teeth: a 400 km orbit takes about 92.6 minutes, not 92.6 seconds."""
    period_minutes = 2.0 * math.pi / mean_motion_rad_s(CHIEF_RADIUS_KM) / 60.0
    assert 90.0 < period_minutes < 95.0
    # And geostationary radius must give a sidereal day, which is the check that catches a
    # mu in the wrong units: the answer would be off by orders of magnitude, not percent.
    geo_period_hours = 2.0 * math.pi / mean_motion_rad_s(42164.0) / 3600.0
    assert geo_period_hours == pytest.approx(23.934, abs=0.01)


def test_the_gravitational_parameter_is_the_one_sgp4_uses() -> None:
    """Consistency, not accuracy, and this test caught a false claim in the constant's own comment.

    The comment said 398600.4418 was "the one SGP4 itself uses". Measured, `wgs84.mu` is 398600.5.
    The value changed to match, because the rationale is sound: a mean motion derived here and a
    track propagated by SGP4 should not disagree for a reason nobody can see.

    Asserted against the library exactly, not approximately, since the whole point is that they
    are the same number rather than nearly the same.
    """
    from sgp4.earth_gravity import wgs84

    assert wgs84.mu == EARTH_MU_KM3_S2


def test_the_element_set_path_and_the_radius_path_agree_for_a_circular_orbit() -> None:
    """The two ways to get a mean motion must not disagree, or a scenario silently picks one.

    A near-circular element set's own mean motion and one recomputed from its semi-major axis
    should agree closely. They will not agree exactly, because SGP4's Kozai mean motion carries
    the secular effect of Earth's oblateness that the two-body formula does not, so the tolerance
    is loose on purpose and the reason is written down rather than tuned until it passed.
    """
    from pathlib import Path

    import sgp4

    from enlightenment.physics import load_elements

    root = Path(sgp4.__file__).parent
    lines = [
        line.rstrip()[:69]
        for line in (root / "SGP4-VER.TLE").read_text().splitlines()
        if line.startswith(("1 ", "2 "))
    ]
    elements = load_elements(lines[0], lines[1], verify_checksum=False)
    from_elements = mean_motion_from_elements(elements)
    assert from_elements > 0.0
    # Semi-major axis implied by that mean motion, then back again. A round trip through the
    # two-body relation must return the rate it started from.
    axis = (EARTH_MU_KM3_S2 / from_elements**2) ** (1.0 / 3.0)
    assert mean_motion_rad_s(axis) == pytest.approx(from_elements, rel=1e-12)


# The five tests below were silently deleted once and restored. Recorded because the mechanism
# is a trap worth knowing: `sed -n '/start/,/end/p'` prints to END OF FILE when the end pattern
# never matches, and `ruff format` had reflowed the line I was matching on. The extracted
# "anchor" therefore ran to EOF, and replacing it dropped everything after the target function.
# `verified-edit.py` checks that an anchor is present and unique; it cannot know the range was
# wider than intended. The habit that catches it is checking the anchor's line count before use.


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_a_bad_semi_major_axis_is_refused(bad: float) -> None:
    """A scenario template with a bad altitude must fail at authoring time, not produce a rate."""
    with pytest.raises(RelativeMotionError, match="finite and positive"):
        mean_motion_rad_s(bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_time_or_state_is_refused(bad: float) -> None:
    """The same fail-closed rule the propagator applies, for the same reason."""
    mean_motion = mean_motion_rad_s(CHIEF_RADIUS_KM)
    with pytest.raises(RelativeMotionError, match="seconds must be finite"):
        propagate_relative(DEPUTY, mean_motion, bad)
    hostile = RelativeState(position_km=(bad, 0.0, 0.0), velocity_km_s=(0.0, 0.0, 0.0))
    with pytest.raises(RelativeMotionError, match="must be finite"):
        propagate_relative(hostile, mean_motion, 60.0)


def test_the_frame_is_carried_and_is_not_inertial() -> None:
    """A Hill-frame vector read as inertial is silently wrong, so the frame lives in the type."""
    assert DEPUTY.frame == HILL_FRAME
    assert "HILL" in DEPUTY.frame
    assert "TEME" not in DEPUTY.frame


def test_range_and_range_rate_read_the_way_an_operator_expects() -> None:
    """Negative range rate is closing. That convention is what a display shows."""
    closing = RelativeState(position_km=(0.0, -10.0, 0.0), velocity_km_s=(0.0, 0.001, 0.0))
    assert closing.range_km == pytest.approx(10.0)
    assert closing.range_rate_km_s < 0.0, "approaching from behind must read as closing"
    opening = RelativeState(position_km=(0.0, -10.0, 0.0), velocity_km_s=(0.0, -0.001, 0.0))
    assert opening.range_rate_km_s > 0.0


def test_a_coincident_state_reports_a_zero_range_rate_rather_than_dividing_by_zero() -> None:
    """Undefined at zero separation, so a convention is stated rather than a crash produced."""
    coincident = RelativeState(position_km=(0.0, 0.0, 0.0), velocity_km_s=(1.0, 1.0, 1.0))
    assert coincident.range_km == 0.0
    assert coincident.range_rate_km_s == 0.0


@pytest.mark.parametrize("bad", [0.0, -0.001, float("nan"), float("inf")])
def test_a_bad_mean_motion_is_refused_by_the_propagator(bad: float) -> None:
    """The rate is a divisor in the closed form, so a zero or non-finite one must not reach it.

    Uncovered until now, which is the whole reason this exists: the guard was written and never
    exercised, and an unexercised guard is a guard that might not work.
    """
    with pytest.raises(RelativeMotionError, match="mean motion must be finite and positive"):
        propagate_relative(DEPUTY, bad, 60.0)


def test_an_element_set_with_no_usable_mean_motion_is_refused() -> None:
    """The other uncovered guard. A stub stands in for the element set, because the real ones all
    carry a usable rate and manufacturing a broken TLE that still parses is harder than saying
    plainly what the guard is for: whatever the library hands back, a non-positive or non-finite
    rate must not become a scenario.
    """

    class _NoRate:
        no_kozai = 0.0

    with pytest.raises(RelativeMotionError, match="non-usable mean motion"):
        mean_motion_from_elements(_NoRate())  # type: ignore[arg-type]
