"""Tests for the Rowen-type dynamic core, its maps, and replayable sessions."""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from turbineiq.engineering import CALIBRATED_6B03, simulate_real_gas_cycle
from turbineiq.simulation import (
    CommandError,
    GasTurbinePlant,
    InvalidCommand,
    PlantParameters,
    Session,
    SessionConfig,
    UnitState,
    operating_maps,
    replay,
)
from turbineiq.simulation.maps import igv_air_factor, pressure_ratio_at_speed


def run(plant: GasTurbinePlant, seconds: float) -> None:
    for _ in range(round(seconds / plant.p.dt_s)):
        plant.step()


def started_plant(**kwargs) -> GasTurbinePlant:
    plant = GasTurbinePlant(operating_maps(kwargs.pop("ambient", 15.0)), **kwargs)
    plant.command_start()
    run(plant, 250.0)
    return plant


@pytest.fixture(scope="module")
def synced_plant() -> GasTurbinePlant:
    plant = started_plant()
    assert plant.state == UnitState.LOADED
    return plant


@pytest.fixture
def plant(synced_plant: GasTurbinePlant) -> GasTurbinePlant:
    return copy.deepcopy(synced_plant)


# ----------------------------------------------------------------------------- maps
def test_rated_point_of_maps_is_the_calibrated_cycle() -> None:
    maps = operating_maps(15.0)
    rated = simulate_real_gas_cycle(CALIBRATED_6B03)
    power_pu, exhaust_k = maps.lookup(1.0, 1.0, 1.0)
    assert maps.electrical_mw(power_pu) == pytest.approx(rated.net_electrical_power_mw, rel=1e-3)
    assert exhaust_k == pytest.approx(rated.exhaust_temperature_k, abs=0.5)
    assert maps.rated_fuel_kg_s == pytest.approx(rated.fuel_mass_flow_kg_s)


def _cycle_at_fuel(ambient_c: float, speed: float, air_factor: float, fuel_kg_s: float):
    """Independent route: bisect the firing temperature of the cycle model to a fuel flow."""

    base = CALIBRATED_6B03
    t_base = base.ambient_temperature_c + 273.15
    inputs = replace(
        base,
        ambient_temperature_c=ambient_c,
        pressure_ratio=pressure_ratio_at_speed(base.pressure_ratio, speed),
        air_mass_flow_kg_s=(
            base.air_mass_flow_kg_s * speed * air_factor * t_base / (ambient_c + 273.15)
        ),
    )
    lo, hi = 400.0, 1900.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        result = simulate_real_gas_cycle(
            replace(inputs, effective_firing_temperature_k=mid), allow_negative_work=True
        )
        if result.fuel_mass_flow_kg_s < fuel_kg_s:
            lo = mid
        else:
            hi = mid
    return simulate_real_gas_cycle(
        replace(inputs, effective_firing_temperature_k=0.5 * (lo + hi)), allow_negative_work=True
    )


@pytest.mark.parametrize("speed,igv,fuel_pu", [(1.0, 1.0, 0.55), (0.85, 0.5, 0.3), (0.6, 0.0, 0.2)])
def test_maps_agree_with_direct_cycle_solution_off_design(
    speed: float, igv: float, fuel_pu: float
) -> None:
    maps = operating_maps(15.0)
    g = igv_air_factor(igv)
    power_pu, exhaust_k = maps.lookup(speed, g, fuel_pu)
    direct = _cycle_at_fuel(15.0, speed, g, fuel_pu * maps.rated_fuel_kg_s)
    assert power_pu == pytest.approx(direct.shaft_power_mw / maps.rated_shaft_power_mw, abs=0.01)
    assert exhaust_k == pytest.approx(direct.exhaust_temperature_k, abs=6.0)


def test_maps_depend_on_ambient_and_reject_out_of_range() -> None:
    cold = operating_maps(-10.0).lookup(1.0, 1.0, 1.0)[0]
    hot = operating_maps(40.0).lookup(1.0, 1.0, 1.0)[0]
    assert cold > 1.0 > hot  # same fuel, denser air, more shaft power
    with pytest.raises(ValueError):
        operating_maps(80.0)


# ------------------------------------------------------------------ start and steady state
def test_start_sequence_visits_states_in_order_without_trip() -> None:
    plant = GasTurbinePlant(operating_maps(15.0))
    plant.command_start()
    seen: list[UnitState] = []
    for _ in range(round(400 / plant.p.dt_s)):
        plant.step()
        if not seen or plant.state != seen[-1]:
            seen.append(plant.state)
    assert seen[:7] == [
        UnitState.CRANK,
        UnitState.PURGE,
        UnitState.IGNITION,
        UnitState.WARMUP,
        UnitState.ACCELERATE,
        UnitState.FSNL,
        UnitState.LOADED,
    ]
    assert plant.trip_cause is None
    assert plant.breaker_closed
    assert plant.n == pytest.approx(1.0, abs=1e-6)


@pytest.mark.parametrize("fraction", [0.25, 0.5, 0.75, 1.0])
def test_steady_states_match_the_cycle_model(plant: GasTurbinePlant, fraction: float) -> None:
    rated_mw = plant.maps.rated_electrical_power_mw
    plant.command_set_load(fraction * rated_mw, 120.0)
    run(plant, 360.0)
    assert plant.limiter == "governor"
    assert plant.electrical_power_mw() == pytest.approx(fraction * rated_mw, rel=2e-3)
    direct = _cycle_at_fuel(15.0, 1.0, 1.0, plant.wfc * plant.maps.rated_fuel_kg_s)
    assert plant.electrical_power_mw() == pytest.approx(direct.net_electrical_power_mw, rel=3e-3)
    assert plant.tm == pytest.approx(direct.exhaust_temperature_k, abs=2.0)


def test_rated_load_reproduces_the_published_point(plant: GasTurbinePlant) -> None:
    plant.command_set_load(45.0, 120.0)
    run(plant, 360.0)
    assert plant.electrical_power_mw() == pytest.approx(45.0, rel=2e-3)
    assert plant.tm - 273.15 == pytest.approx(561.0, abs=1.5)


def test_load_ramp_respects_the_rate_limit(plant: GasTurbinePlant) -> None:
    plant.command_set_load(30.0, 6.0)  # 0.1 MW/s
    start = plant.electrical_power_mw()
    run(plant, 60.0)
    gained = plant.electrical_power_mw() - start
    assert gained == pytest.approx(6.0, rel=0.1)


# --------------------------------------------------------------------- dynamics
def test_infinite_bus_load_step_is_monotone_with_fuel_system_lag(plant: GasTurbinePlant) -> None:
    plant.command_set_load(20.0, 120.0)
    run(plant, 120.0)
    plant.command_set_load(40.0, 120.0)  # ramp-limited: 20 MW takes 10 s
    history = []
    for _ in range(round(60.0 / plant.p.dt_s)):
        plant.step()
        history.append(plant.electrical_power_mw())
    assert history[-1] == pytest.approx(40.0, rel=3e-3)
    assert max(history) < 40.0 * 1.01  # no overshoot
    assert all(b >= a - 0.05 for a, b in zip(history, history[1:], strict=False))
    # Delayed by the valve, fuel and combustor lags: not at target after one second.
    assert history[round(1.0 / plant.p.dt_s)] < 25.0


def test_load_rejection_overspeed_is_bounded_and_recovers(plant: GasTurbinePlant) -> None:
    plant.command_set_load(45.0, 120.0)
    run(plant, 300.0)
    plant.open_breaker()
    peak = 0.0
    for _ in range(round(40.0 / plant.p.dt_s)):
        plant.step()
        peak = max(peak, plant.n)
    assert 1.02 < peak < plant.p.overspeed_trip_pu
    assert plant.state == UnitState.FSNL and plant.trip_cause is None
    assert plant.n == pytest.approx(1.0, abs=1e-3)


def test_island_load_step_dips_speed_then_recovers() -> None:
    plant = started_plant(grid="island", island_load_mw=20.0)
    run(plant, 60.0)
    assert plant.state == UnitState.LOADED
    plant.command_set_island_load(30.0)
    lowest = 2.0
    for _ in range(round(30.0 / plant.p.dt_s)):
        plant.step()
        lowest = min(lowest, plant.n)
    assert 0.95 < lowest < 0.995
    plant.command_set_load(30.0, 60.0)
    run(plant, 120.0)
    assert plant.n == pytest.approx(1.0, abs=2e-3)
    assert plant.electrical_power_mw() == pytest.approx(30.0, rel=2e-2)


def test_island_rotor_energy_balance() -> None:
    """d(H N^2)/dt = P_shaft - P_load, checked by integrating over a load step."""

    plant = started_plant(grid="island", island_load_mw=20.0)
    run(plant, 60.0)
    plant.command_set_island_load(32.0)
    h = plant.p.two_h_s / 2.0
    n0 = plant.n
    imbalance = 0.0
    dt = plant.p.dt_s
    for _ in range(round(20.0 / dt)):
        before = plant.shaft_power_pu() - plant._island_load_pu(plant.n)
        plant.step()
        after = plant.shaft_power_pu() - plant._island_load_pu(plant.n)
        imbalance += 0.5 * (before + after) * dt / plant.n
    kinetic = h * (plant.n**2 - n0**2)
    # Divide by N because the rotor equation is written as torque / N in the model.
    assert kinetic == pytest.approx(imbalance * plant.n * 1.0, abs=2e-3 + 0.05 * abs(kinetic))


def test_grid_frequency_event_shows_droop_response(plant: GasTurbinePlant) -> None:
    plant.command_set_load(30.0, 120.0)
    run(plant, 120.0)
    plant.command_set_grid_frequency(49.5)  # -1 percent speed
    run(plant, 60.0)
    expected_gain = 0.01 / plant.p.droop * plant.maps.rated_electrical_power_mw
    assert plant.electrical_power_mw() - 30.0 == pytest.approx(expected_gain, rel=0.08)


# ------------------------------------------------------------- trips and protection
def test_manual_trip_cuts_fuel_opens_breaker_and_needs_reset(plant: GasTurbinePlant) -> None:
    plant.command_set_load(45.0, 120.0)
    run(plant, 300.0)
    plant.command_trip()
    assert plant.state == UnitState.TRIPPED and plant.trip_cause == "manual_emergency_trip"
    assert not plant.breaker_closed
    peak = 0.0
    for _ in range(round(30.0 / plant.p.dt_s)):
        plant.step()
        peak = max(peak, plant.n)
    assert peak < plant.p.overspeed_trip_pu
    assert plant.wfc < 1e-3
    with pytest.raises(CommandError):
        plant.command_reset()  # still turning
    run(plant, 2500.0)
    assert plant.n < plant.p.standstill_speed_pu
    plant.command_reset()
    assert plant.state == UnitState.STANDSTILL


def test_overspeed_trip_with_a_lowered_threshold(plant: GasTurbinePlant) -> None:
    plant.p = replace(plant.p, overspeed_trip_pu=1.03)
    plant.command_set_load(45.0, 120.0)
    run(plant, 300.0)
    plant.open_breaker()
    run(plant, 5.0)
    assert plant.state == UnitState.TRIPPED and plant.trip_cause == "overspeed"


def test_temperature_control_holds_a_hot_day_below_rated_output() -> None:
    plant = started_plant(ambient=40.0)
    plant.command_set_load(45.0, 30.0)
    peak = 0.0
    for _ in range(round(700.0 / plant.p.dt_s)):
        plant.step()
        peak = max(peak, plant.tm)
    assert plant.trip_cause is None
    assert plant.limiter == "temperature"
    assert 34.0 < plant.electrical_power_mw() < 42.0
    assert plant.tm == pytest.approx(plant.temperature_limit_k, abs=1.0)
    assert peak < plant.trip_temperature_k


def test_exhaust_over_temperature_trip_without_temperature_control() -> None:
    params = PlantParameters(temperature_limit_margin_k=500.0)  # limit far above the trip
    plant = started_plant(ambient=40.0, params=params)
    plant.command_set_load(45.0, 30.0)
    run(plant, 700.0)
    assert plant.state == UnitState.TRIPPED
    assert plant.trip_cause == "exhaust_over_temperature"


def test_normal_stop_unloads_cools_and_coasts_to_standstill(plant: GasTurbinePlant) -> None:
    plant.command_set_load(20.0, 120.0)
    run(plant, 120.0)
    plant.command_stop()
    assert plant.state == UnitState.UNLOADING
    run(plant, 30.0)  # 17 MW at 120 MW/min
    assert plant.state == UnitState.COOLDOWN and not plant.breaker_closed
    run(plant, 70.0)
    assert plant.state == UnitState.COASTDOWN and not plant.flame
    run(plant, 2500.0)
    assert plant.state == UnitState.STANDSTILL and plant.n == 0.0


def test_commands_are_refused_in_the_wrong_state() -> None:
    plant = GasTurbinePlant(operating_maps(15.0))
    for call in (plant.command_stop, plant.command_trip, plant.command_reset, plant.open_breaker):
        with pytest.raises(CommandError):
            call()
    plant.command_start()
    with pytest.raises(CommandError):
        plant.command_start()
    with pytest.raises(CommandError):
        plant.command_set_load(500.0, None)
    with pytest.raises(CommandError):
        plant.command_set_island_load(10.0)


def test_manual_igv_changes_the_exhaust_temperature_at_equal_load(plant: GasTurbinePlant) -> None:
    plant.command_set_load(30.0, 120.0)
    run(plant, 120.0)
    open_temperature = plant.tm
    plant.command_set_igv("manual", 0.3)
    run(plant, 240.0)
    assert plant.electrical_power_mw() == pytest.approx(30.0, rel=5e-3)  # trim restores load
    assert plant.tm > open_temperature + 10.0  # less air for the same power: hotter exhaust
    plant.command_set_igv("auto", None)
    run(plant, 240.0)
    assert plant.tm == pytest.approx(open_temperature, abs=2.0)


# --------------------------------------------------------------- sessions and replay
def _scripted_session(seed: int = 3, noise: bool = True) -> Session:
    session = Session(SessionConfig(seed=seed, measurement_noise=noise))
    session.apply("start")
    session.advance_seconds(250.0)
    session.apply("set_load", {"mw": 35.0, "ramp_mw_per_min": 40.0})
    session.advance_seconds(100.0)
    session.apply("set_igv", {"mode": "manual", "position": 0.6})
    session.advance_seconds(50.0)
    session.apply("set_ambient", {"temperature_c": 25.0})
    session.advance_seconds(60.0)
    session.apply("open_breaker")
    session.advance_seconds(15.0)
    session.apply("trip")
    session.advance_seconds(5.0)
    return session


def test_replay_reproduces_the_run_bit_for_bit() -> None:
    session = _scripted_session()
    log = session.log()
    again = replay(log)
    assert again.trace_digest() == log["trace_digest"]
    assert again.snapshot() == session.snapshot()
    assert [e.to_dict() for e in again.events] == log["events"]


def test_replay_digest_changes_with_seed_and_with_events() -> None:
    base = _scripted_session(seed=3)
    other_seed = _scripted_session(seed=4)
    assert base.trace_digest() != other_seed.trace_digest()
    # The true plant state does not depend on the seed, only the measurements do.
    assert base.plant.n == other_seed.plant.n and base.plant.tm == other_seed.plant.tm
    tampered = base.log()
    tampered["events"] = [e for e in tampered["events"] if e["command"] != "set_igv"]
    assert replay(tampered).trace_digest() != base.trace_digest()


def test_replay_rejects_malformed_logs() -> None:
    log = _scripted_session().log()
    log["events"] = list(reversed(log["events"]))
    with pytest.raises(ValueError):
        replay(log)


def test_rejected_commands_are_not_logged_and_do_not_change_state() -> None:
    session = Session(SessionConfig(seed=1))
    before = session.trace_digest()
    with pytest.raises(CommandError):
        session.apply("stop")
    with pytest.raises(InvalidCommand):
        session.apply("set_load", {"mw": "lots"})
    with pytest.raises(InvalidCommand):
        session.apply("start", {"extra": 1})
    with pytest.raises(InvalidCommand):
        session.apply("self_destruct")
    assert session.events == [] and session.trace_digest() == before


def test_measurements_are_noisy_but_true_state_is_exact() -> None:
    noisy = _scripted_session(noise=True)
    clean = _scripted_session(noise=False)
    assert noisy.plant.n == clean.plant.n
    assert (
        clean.snapshot()["measured"]["electrical_power_mw"]
        == clean.snapshot()["electrical_power_mw"]
    )
