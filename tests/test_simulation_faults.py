"""Tests for fault and degradation injection in the simulated plant (roadmap WP3 injection)."""

from __future__ import annotations

import copy
import statistics

import pytest

from turbineiq.simulation import (
    CommandError,
    GasTurbinePlant,
    Session,
    SessionConfig,
    UnitState,
    operating_maps,
    replay,
)
from turbineiq.simulation.faults import FOULING_EFFICIENCY_RATIO
from turbineiq.simulation.maps import CLEAN, Health, direct_health_maps, health_maps


def run(plant: GasTurbinePlant, seconds: float) -> None:
    for _ in range(round(seconds / plant.p.dt_s)):
        plant.step()


@pytest.fixture(scope="module")
def loaded_35() -> GasTurbinePlant:
    plant = GasTurbinePlant(operating_maps(15.0))
    plant.command_start()
    run(plant, 250.0)
    plant.command_set_load(35.0, 60.0)
    run(plant, 400.0)
    assert plant.state == UnitState.LOADED
    return plant


@pytest.fixture
def plant(loaded_35: GasTurbinePlant) -> GasTurbinePlant:
    return copy.deepcopy(loaded_35)


def fouling_health(severity_pct: float) -> Health:
    f = severity_pct / 100.0
    return Health(-f, -FOULING_EFFICIENCY_RATIO * f, 0.0)


# ----------------------------------------------------------------------------- maps
@pytest.mark.parametrize(
    "health",
    [fouling_health(3.0), Health(0.0, 0.0, -0.015), Health(-0.03, -0.015, -0.015)],
    ids=["fouling", "erosion", "combined"],
)
def test_linearised_health_maps_agree_with_direct_cycle_solutions(health: Health) -> None:
    linear = health_maps(15.0)
    direct = direct_health_maps(15.0, health)
    for n in (0.9, 0.95, 1.0):
        for g in (0.7, 0.85, 1.0):
            for wf in (0.3, 0.6, 0.9, 1.1):
                p_lin, t_lin = linear.lookup(health, n, g, wf)
                p_dir, t_dir = direct.lookup(n, g, wf)
                assert p_lin == pytest.approx(p_dir, abs=2e-3)
                assert t_lin == pytest.approx(t_dir, abs=1.5)


def test_clean_health_returns_the_clean_maps_exactly() -> None:
    maps = health_maps(15.0)
    assert maps.lookup(CLEAN, 1.0, 1.0, 0.8) == maps.clean.lookup(1.0, 1.0, 0.8)


def test_degraded_maps_keep_the_clean_per_unit_bases() -> None:
    clean = operating_maps(15.0)
    fouled = direct_health_maps(15.0, fouling_health(4.0))
    assert fouled.rated_fuel_kg_s == clean.rated_fuel_kg_s
    assert fouled.rated_exhaust_k == clean.rated_exhaust_k
    # Same fuel flow, fouled compressor: less power and a hotter exhaust.
    p_clean, t_clean = clean.lookup(1.0, 1.0, 1.0)
    p_foul, t_foul = fouled.lookup(1.0, 1.0, 1.0)
    assert p_foul < p_clean and t_foul > t_clean


# ----------------------------------------------------------------------------- plant
def test_fouling_at_part_load_costs_fuel_not_output(plant: GasTurbinePlant) -> None:
    before_fuel, before_tx = plant.wfc, plant.tm
    cdt_before = plant.compressor_discharge()[0]
    plant.command_inject_degradation("compressor_fouling", 3.0, None)
    run(plant, 600.0)
    assert plant.electrical_power_mw() == pytest.approx(35.0, rel=2e-3)
    assert plant.wfc > before_fuel * 1.005
    assert plant.tm > before_tx + 10.0
    assert plant.compressor_discharge()[0] > cdt_before + 5.0


def test_fouling_at_the_temperature_limit_costs_output_as_the_degraded_cycle_predicts() -> None:
    plant = GasTurbinePlant(operating_maps(15.0))
    plant.command_start()
    run(plant, 250.0)
    plant.command_set_load(47.0, 60.0)
    plant.command_inject_degradation("compressor_fouling", 3.0, None)
    run(plant, 900.0)
    assert plant.limiter == "temperature"
    # Steady state of the degraded cycle with the exhaust at the control limit.
    direct = direct_health_maps(15.0, fouling_health(3.0))
    lo, hi = 0.5, 1.5
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if direct.lookup(1.0, 1.0, mid)[1] < plant.temperature_limit_k:
            lo = mid
        else:
            hi = mid
    expected_mw = direct.electrical_mw(direct.lookup(1.0, 1.0, lo)[0])
    assert plant.electrical_power_mw() == pytest.approx(expected_mw, rel=5e-3)
    assert plant.electrical_power_mw() < 0.98 * 45.0


def test_progressive_fouling_grows_at_its_rate_only_with_air_flowing(
    plant: GasTurbinePlant,
) -> None:
    plant.command_inject_degradation("compressor_fouling", 1.0, 2.0)
    run(plant, 900.0)  # a quarter of an hour at 2 percent per hour
    severity = plant.faults.degradation["compressor_fouling"].severity_pct
    assert severity == pytest.approx(1.5, abs=1e-6)
    assert plant.faults.health.compressor_flow == pytest.approx(-0.015)

    stopped = GasTurbinePlant(operating_maps(15.0))
    stopped.command_inject_degradation("compressor_fouling", 1.0, 2.0)
    run(stopped, 900.0)
    assert stopped.faults.degradation["compressor_fouling"].severity_pct == 1.0


def test_progressive_degradation_stops_at_its_maximum(plant: GasTurbinePlant) -> None:
    plant.command_inject_degradation("turbine_erosion", 4.9, 10.0)
    run(plant, 120.0)
    assert plant.faults.degradation["turbine_erosion"].severity_pct == 5.0


def test_offline_wash_needs_standstill_and_keeps_the_fouling_rate(plant: GasTurbinePlant) -> None:
    plant.command_inject_degradation("compressor_fouling", 2.0, 1.0)
    with pytest.raises(CommandError):
        plant.command_wash_compressor()
    idle = GasTurbinePlant(operating_maps(15.0))
    idle.command_inject_degradation("compressor_fouling", 2.0, 1.0)
    idle.command_wash_compressor()
    fouling = idle.faults.degradation["compressor_fouling"]
    assert fouling.severity_pct == 0.0 and fouling.rate_pct_per_h == 1.0
    assert idle.faults.health == CLEAN


def test_exhaust_thermocouple_bias_moves_the_true_temperature_limit() -> None:
    plant = GasTurbinePlant(operating_maps(15.0))
    plant.command_start()
    run(plant, 250.0)
    plant.command_set_load(47.0, 60.0)
    run(plant, 600.0)
    assert plant.limiter == "temperature"
    clean_mw = plant.electrical_power_mw()

    reads_low = copy.deepcopy(plant)
    reads_low.command_inject_sensor_fault("exhaust_temperature", "bias", -5.0)
    run(reads_low, 600.0)
    # The controller holds the reading at the limit, so the true exhaust runs 5 K hotter.
    assert reads_low.readings["exhaust_temperature"] == pytest.approx(
        reads_low.temperature_limit_k, abs=0.3
    )
    assert reads_low.tm == pytest.approx(reads_low.temperature_limit_k + 5.0, abs=0.3)
    assert reads_low.electrical_power_mw() > clean_mw

    reads_high = copy.deepcopy(plant)
    reads_high.command_inject_sensor_fault("exhaust_temperature", "bias", 15.0)
    run(reads_high, 600.0)
    assert reads_high.tm == pytest.approx(reads_high.temperature_limit_k - 15.0, abs=0.3)
    assert reads_high.electrical_power_mw() < clean_mw


def test_stuck_exhaust_thermocouple_blinds_the_temperature_control(
    plant: GasTurbinePlant,
) -> None:
    plant.command_inject_sensor_fault("exhaust_temperature", "stuck", None)
    frozen = plant.readings["exhaust_temperature"]
    plant.command_set_load(47.0, 60.0)
    run(plant, 600.0)
    assert plant.readings["exhaust_temperature"] == frozen
    assert plant.limiter != "temperature"
    assert plant.tm > plant.temperature_limit_k  # overfired without the controller noticing
    assert plant.state == UnitState.LOADED  # the protection reads the same thermocouple


def test_monitoring_sensor_faults_do_not_change_the_plant(plant: GasTurbinePlant) -> None:
    faulty = copy.deepcopy(plant)
    for channel, mode, magnitude in (
        ("electrical_power", "bias", 1.5),
        ("speed", "noise", 0.01),
        ("compressor_discharge_temperature", "drift", 20.0),
        ("compressor_discharge_pressure", "stuck", None),
        ("fuel_flow", "bias", -0.05),
    ):
        faulty.command_inject_sensor_fault(channel, mode, magnitude)
    run(plant, 300.0)
    run(faulty, 300.0)
    assert (faulty.n, faulty.wfc, faulty.tm) == (plant.n, plant.wfc, plant.tm)
    assert faulty.readings["electrical_power"] == pytest.approx(
        plant.electrical_power_mw() + 1.5, abs=1e-9
    )
    assert faulty.readings["fuel_flow"] == pytest.approx(plant.readings["fuel_flow"] - 0.05)
    cdt_true = plant.compressor_discharge()[0]
    assert faulty.readings["compressor_discharge_temperature"] == pytest.approx(
        cdt_true + 20.0 * 300.0 / 3600.0, abs=1e-6
    )


def test_noise_fault_has_the_requested_spread(plant: GasTurbinePlant) -> None:
    plant.command_inject_sensor_fault("electrical_power", "noise", 0.5)
    errors = []
    for _ in range(2000):
        plant.step()
        errors.append(plant.readings["electrical_power"] - plant.electrical_power_mw())
    assert abs(statistics.fmean(errors)) < 0.05
    assert statistics.pstdev(errors) == pytest.approx(0.5, rel=0.1)


def test_slow_fuel_valve_slows_the_load_response(plant: GasTurbinePlant) -> None:
    def time_to_reach(p: GasTurbinePlant, target_mw: float) -> float:
        p.command_set_load(40.0, 120.0)
        t = 0.0
        while p.electrical_power_mw() < target_mw:
            p.step()
            t += p.p.dt_s
            assert t < 120.0
        return t

    healthy = time_to_reach(copy.deepcopy(plant), 39.5)
    plant.command_set_fuel_valve_lag(3.0)
    slow = time_to_reach(plant, 39.5)
    assert slow > healthy + 1.0


def test_fault_commands_validate_their_arguments(plant: GasTurbinePlant) -> None:
    with pytest.raises(ValueError):
        plant.command_inject_degradation("bearing_wear", 1.0, None)
    with pytest.raises(ValueError):
        plant.command_inject_degradation("compressor_fouling", 11.0, None)
    with pytest.raises(ValueError):
        plant.command_inject_sensor_fault("vibration", "bias", 1.0)
    with pytest.raises(ValueError):
        plant.command_inject_sensor_fault("speed", "bias", None)
    with pytest.raises(ValueError):
        plant.command_inject_sensor_fault("speed", "stuck", 1.0)
    with pytest.raises(ValueError):
        plant.command_inject_sensor_fault("exhaust_temperature", "bias", 500.0)
    with pytest.raises(ValueError):
        plant.command_set_fuel_valve_lag(0.0)
    with pytest.raises(ValueError):
        plant.command_clear_fault("turbine_erosion")  # nothing to clear
    assert not plant.faults.any_active()


def test_clear_restores_the_healthy_plant(plant: GasTurbinePlant) -> None:
    clean = copy.deepcopy(plant)
    plant.command_inject_degradation("compressor_fouling", 4.0, None)
    plant.command_inject_sensor_fault("exhaust_temperature", "bias", -10.0)
    plant.command_set_fuel_valve_lag(1.0)
    run(plant, 200.0)
    plant.command_clear_fault("all")
    assert not plant.faults.any_active() and plant.faults.health == CLEAN
    run(plant, 900.0)
    run(clean, 1100.0)
    assert plant.electrical_power_mw() == pytest.approx(clean.electrical_power_mw(), rel=1e-4)
    assert plant.tm == pytest.approx(clean.tm, abs=0.05)


# ----------------------------------------------------------------------------- sessions
def _faulted_session(seed: int = 3) -> Session:
    session = Session(SessionConfig(seed=seed, record_interval_s=5.0))
    session.apply(
        "inject_sensor_fault", {"channel": "fuel_flow", "mode": "drift", "magnitude": 0.1}
    )
    session.apply("start")
    session.advance_seconds(250.0)
    session.apply("set_load", {"mw": 40.0, "ramp_mw_per_min": 60.0})
    session.apply(
        "inject_degradation",
        {"kind": "compressor_fouling", "severity_pct": 1.0, "rate_pct_per_h": 6.0},
    )
    session.advance_seconds(120.0)
    session.apply(
        "inject_sensor_fault",
        {"channel": "exhaust_temperature", "mode": "noise", "magnitude": 2.0},
    )
    session.apply("set_fuel_valve_lag", {"tau_s": 1.5})
    session.advance_seconds(120.0)
    session.apply("clear_fault", {"target": "exhaust_temperature"})
    session.apply("inject_degradation", {"kind": "turbine_erosion", "severity_pct": 1.0})
    session.advance_seconds(60.0)
    return session


def test_runs_with_faults_replay_bit_for_bit() -> None:
    session = _faulted_session()
    log = session.log()
    assert log["trace_format"] == 2
    again = replay(log)
    assert again.trace_digest() == log["trace_digest"]
    assert again.snapshot() == session.snapshot()


def test_removing_a_fault_event_changes_the_digest() -> None:
    log = _faulted_session().log()
    log["events"] = [e for e in log["events"] if e["command"] != "set_fuel_valve_lag"]
    assert replay(log).trace_digest() != _faulted_session().trace_digest()


def test_snapshot_reports_ground_truth_separately_from_measurements() -> None:
    snap = _faulted_session().snapshot()
    truth = snap["injected_faults"]
    assert set(truth["degradation"]) == {"compressor_fouling", "turbine_erosion"}
    assert truth["degradation"]["compressor_fouling"]["severity_pct"] == pytest.approx(1.5)
    assert truth["health"]["turbine_efficiency_delta"] == pytest.approx(-0.01)
    assert truth["sensors"]["fuel_flow"]["mode"] == "drift"
    assert "exhaust_temperature" not in truth["sensors"]
    assert truth["fuel_valve_lag_s"] == 1.5
    measured = snap["measured"]
    assert set(measured) == {
        "electrical_power_mw",
        "exhaust_temperature_k",
        "speed_pu",
        "compressor_discharge_temperature_k",
        "compressor_discharge_pressure_kpa",
        "fuel_flow_kg_s",
    }
    # 0.1 kg/s per hour of drift for 550 s, plus 0.5 percent noise.
    expected = snap["fuel_flow_kg_s"] + 0.1 * 550.0 / 3600.0
    assert measured["fuel_flow_kg_s"] == pytest.approx(expected, rel=0.03)


def test_fault_commands_are_available_in_every_state_and_wash_only_at_standstill() -> None:
    session = Session(SessionConfig(seed=1))
    assert "inject_degradation" in session.allowed_commands()
    assert "wash_compressor" in session.allowed_commands()
    session.apply("start")
    session.advance_seconds(5.0)
    assert "inject_sensor_fault" in session.allowed_commands()
    assert "wash_compressor" not in session.allowed_commands()
    with pytest.raises(CommandError):
        session.apply("wash_compressor")
    with pytest.raises(CommandError):
        session.apply("clear_fault", {"target": "all"})
    assert [e.command for e in session.events] == ["start"]
