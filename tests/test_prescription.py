"""WP5 prescriptive layer: exhaust substitute, forward twin, guard and supervisor."""

from __future__ import annotations

import pytest

from turbineiq.prescription import GuardLimits, Mode, SafetyGuard, SupervisorConfig, TwinStatus
from turbineiq.prescription.monitor import twin_engine
from turbineiq.prescription.runner import RunRecord, run_supervised, score
from turbineiq.prescription.twin import forward_run, predictive_twin
from turbineiq.simulation import CommandError, Session, replay
from turbineiq.simulation.maps import CLEAN, Health
from turbineiq.simulation.scenarios import SCENARIOS


@pytest.fixture(scope="module")
def loaded() -> Session:
    session = Session()
    session.apply("start")
    session.advance_seconds(300)
    session.apply("set_load", {"mw": 30.0, "ramp_mw_per_min": 60.0})
    session.advance_seconds(240)
    return session


def _status(**overrides) -> TwinStatus:
    base = dict(
        t_s=0.0,
        loaded=True,
        steady=True,
        health=CLEAN,
        health_std=Health(0.001, 0.0005, 0.0005),
        estimator_updates=10,
        mismatch_index=0.5,
        exhaust_residual_k=-1.0,
    )
    base.update(overrides)
    return TwinStatus(**base)


# ---------------------------------------------------------------- plant: exhaust substitute
def test_exhaust_substitute_drives_the_temperature_control():
    session = Session()
    session.apply("start")
    session.advance_seconds(300)
    session.apply("set_load", {"mw": 47.0, "ramp_mw_per_min": 60.0})
    session.advance_seconds(200)
    on_limit = session.snapshot()
    assert on_limit["limiter"] == "temperature"
    # A substitute reading 20 K hotter than the truth makes the control back off.
    hot = session.plant.tm + 20.0
    session.apply("set_exhaust_feedback", {"source": "model", "value_k": hot})
    session.advance_seconds(30)
    snap = session.snapshot()
    assert snap["exhaust_feedback"] == {"source": "model", "value_k": hot}
    assert snap["electrical_power_mw"] < on_limit["electrical_power_mw"] - 1.0
    session.apply("set_exhaust_feedback", {"source": "thermocouple", "value_k": None})
    assert session.snapshot()["exhaust_feedback"]["source"] == "thermocouple"
    # The command is logged and replays to the same trace.
    assert replay(session.log()).trace_digest() == session.trace_digest()


@pytest.mark.parametrize(
    "params",
    [
        {"source": "model", "value_k": None},
        {"source": "model", "value_k": 2000.0},
        {"source": "radar", "value_k": 700.0},
    ],  # fmt: skip
)
def test_exhaust_substitute_rejects_bad_input(params):
    with pytest.raises(CommandError):
        Session().apply("set_exhaust_feedback", params)


# ---------------------------------------------------------------- forward twin
def test_predictive_twin_does_not_copy_injected_faults(loaded: Session):
    session = Session()
    session.apply("start")
    session.advance_seconds(300)
    session.apply("set_load", {"mw": 30.0, "ramp_mw_per_min": 60.0})
    session.apply("inject_degradation", {"kind": "compressor_fouling", "severity_pct": 3.0})
    session.apply(
        "inject_sensor_fault",
        {"channel": "exhaust_temperature", "mode": "bias", "magnitude": -30.0},
    )
    session.advance_seconds(120)
    m = session.snapshot()["measured"]
    estimate = Health(-0.01, -0.005, 0.0)
    twin = predictive_twin(
        session.plant,
        twin_engine(),
        estimate,
        fuel_kg_s=m["fuel_flow_kg_s"],
        speed_pu=m["speed_pu"],
    )
    assert twin.faults.health.is_clean() and not twin.faults.sensors
    assert twin.twin_health == estimate
    # The plant itself is untouched.
    assert not session.plant.faults.health.is_clean()
    assert twin.temperature_limit_k == session.plant.temperature_limit_k
    assert abs(twin.electrical_power_mw() - 30.0) < 1.0


def test_forward_run_and_guard_catch_an_unsafe_igv_closure(loaded: Session):
    m = loaded.snapshot()["measured"]
    twin = predictive_twin(
        loaded.plant, twin_engine(), CLEAN, fuel_kg_s=m["fuel_flow_kg_s"], speed_pu=m["speed_pu"]
    )
    guard = SafetyGuard()
    actions = [
        {"command": "set_load", "params": {"mw": 40.0, "ramp_mw_per_min": 10.0}},
        {"command": "set_igv", "params": {"mode": "manual", "position": 0.0}},
    ]
    fw = forward_run(twin, actions, 210.0)
    verdict = guard.verify_load(
        _status(),
        current_setpoint_mw=30.0,
        target_mw=40.0,
        band=(38.0, 42.0),
        ramp_mw_per_min=10.0,
        forward=fw,
        exhaust_trusted_or_substituted=True,
        since_last_action_s=None,
    )
    assert not verdict.approved
    failed = {c.name for c in verdict.failed}
    assert failed & {"settled_exhaust", "meets_demand", "no_trip", "peak_exhaust"}
    assert "setpoint_step" in failed  # 10 MW is more than the 6 MW step limit

    igv = {"command": "set_igv", "params": {"mode": "manual", "position": 0.6}}
    safe = forward_run(twin, [igv], 150.0)
    ok = guard.verify_load(
        _status(),
        current_setpoint_mw=30.0,
        target_mw=30.0,
        band=(28.0, 32.0),
        ramp_mw_per_min=10.0,
        forward=safe,
        exhaust_trusted_or_substituted=True,
        since_last_action_s=None,
    )
    assert ok.approved, ok.reason()


# ---------------------------------------------------------------- guard
def test_guard_escalates_on_an_untrusted_twin():
    guard = SafetyGuard()
    checks = {
        c.name: c for c in guard.trust_checks(_status(mismatch_index=None), need_exhaust=True)
    }
    assert not checks["model_mismatch"].passed
    checks = {c.name: c for c in guard.trust_checks(_status(mismatch_index=9.0), need_exhaust=True)}
    assert not checks["model_mismatch"].passed
    checks = {
        c.name: c
        for c in guard.trust_checks(
            _status(exhaust_suspect=True, exhaust_reason="x"), need_exhaust=True
        )
    }
    assert not checks["exhaust_reading_trusted"].passed
    assert not guard.verify_substitute(_status(model_exhaust_k=None)).approved
    assert guard.verify_substitute(_status(model_exhaust_k=780.0)).approved


def test_wash_needs_the_operator_unless_allowed():
    assert not SafetyGuard().verify_wash(_status()).approved
    assert SafetyGuard(GuardLimits(autonomous_wash=True)).verify_wash(_status()).approved


# ---------------------------------------------------------------- supervisor
def _scenario(name: str):
    return next(s for s in SCENARIOS if s.id == name)


def test_manual_mode_only_watches():
    session, sup, _ = run_supervised(_scenario("clean_part_load"), "manual", until_s=1200.0)
    assert sup.decisions == []
    assert sup.status is not None and sup.status.estimator_updates > 0
    assert all(e.command != "set_igv" for e in session.events)


def test_autonomous_mode_applies_a_guard_approved_load_decision():
    session, sup, rec = run_supervised(
        _scenario("clean_part_load"), Mode.AUTONOMOUS, until_s=1300.0
    )
    applied = [d for d in sup.decisions if d.status == "applied"]
    assert applied, [d.to_dict() for d in sup.decisions]
    d = applied[0]
    assert d.problem == "load_setpoint" and d.verdict["approved"]
    assert d.verdict["forward"] is not None
    assert any(e.command == "set_igv" for e in session.events)
    # Every logged decision carries a reason and a verdict with named checks.
    for decision in sup.decisions:
        assert decision.reason and decision.verdict["checks"]
    s = score(rec, 2.0, from_s=600.0)
    assert s["trips"] == 0 and s["violation_s"] == 0.0


def test_advisory_mode_waits_for_the_operator():
    from turbineiq.prescription.runner import OperatorModel

    _, sup, _ = run_supervised(
        _scenario("clean_part_load"),
        "advisory",
        config=SupervisorConfig(),
        operator=OperatorModel(delay_s=10_000.0),
        until_s=1300.0,
    )
    assert sup.decisions and all(d.status != "applied" for d in sup.decisions)
    pending = [d for d in sup.decisions if d.status == "pending"]
    assert pending
    sup.accept(pending[0].id)
    assert sup.get(pending[0].id).status == "accepted"
    with pytest.raises(ValueError):
        sup.accept(pending[0].id)


def test_score_counts_violations_and_band():
    rec = RunRecord(lhv_kj_kg=50_000.0)
    for t in range(10):
        rec.t_s.append(float(t))
        rec.power_mw.append(35.0 if t < 5 else 30.0)
        rec.fuel_kg_s.append(2.0)
        rec.exhaust_k.append(800.0 if t < 8 else 812.0)
        rec.limit_k.append(805.0)
        rec.trip_k.append(845.0)
        rec.state.append("loaded")
        rec.demand_mw.append(35.0)
    s = score(rec, 2.0)
    assert s["band_compliance"] == pytest.approx(0.5)
    assert s["violation_s"] == 2.0 and s["max_over_limit_k"] == pytest.approx(7.0)
