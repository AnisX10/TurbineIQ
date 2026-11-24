"""Fast checks of the WP5 evaluation harness (statistics, pairing, wash study, one short run)."""

from __future__ import annotations

import json

import pytest

from turbineiq.estimation.mismatch import MISMATCHES
from turbineiq.prescription import evaluation as ev
from turbineiq.prescription.runner import RunRecord, score
from turbineiq.simulation.scenarios import check_script


def _fake(scenario: str, mode: str, seed: int, hr: float, energy: float = 10.0, **extra):
    fuel = hr * energy * 1000.0 / 50_000.0
    return {
        "spec": ev.RunSpec(scenario, mode, seed).to_dict() | extra.pop("spec", {}),
        "category": "baseline",
        "score": {
            "fuel_kg": fuel,
            "energy_mwh": energy,
            "heat_rate_kj_per_kwh": hr,
            "band_compliance": extra.pop("band", 1.0),
            "violation_s": extra.pop("violation_s", 0.0),
            "over_limit_k_s": 0.0,
            "over_limit_s": 0.0,
            "max_over_limit_k": 0.0,
            "trips": 0,
            "fuel_cost_usd": fuel * 50_000.0 / 1e6 * 8.0,
        },
        "decisions": extra.pop("decisions", []),
        "skipped": [],
        "trust": {"mismatch_median": 0.2, "mismatch_share_over_limit": 0.0, "mismatch_p95": 0.4},
        "thermocouple": {},
        "wash": extra.pop("wash", {"washes": 0, "mean_fouling_pct": 0.0, "max_fouling_pct": 0.0}),
    }


def test_bootstrap_ci_brackets_the_mean_and_is_stratified():
    ci = ev.bootstrap_ci([1.0, 2.0, 3.0, 4.0], n_boot=2000, seed=1)
    assert ci["n"] == 4 and ci["mean"] == pytest.approx(2.5)
    assert ci["lo"] < 2.5 < ci["hi"]
    # Within-group resampling of constant groups has no spread at all.
    flat = ev.bootstrap_ci([1.0, 1.0, 5.0, 5.0], groups=["a", "a", "b", "b"], n_boot=500)
    assert flat["lo"] == pytest.approx(3.0) and flat["hi"] == pytest.approx(3.0)
    assert ev.bootstrap_ci([])["mean"] is None


def test_paired_differences_against_manual_of_the_same_seed():
    results = [
        _fake("clean_part_load", "manual", 2000, 11000.0, band=0.9),
        _fake("clean_part_load", "autonomous", 2000, 10780.0, band=1.0),
        _fake("clean_part_load", "manual", 2001, 12000.0),
        _fake("clean_part_load", "autonomous", 2001, 12000.0),
        _fake("clean_part_load", "advisory", 2002, 10000.0),  # no manual: left out
    ]
    diffs = ev.paired_differences(results)
    assert len(diffs) == 2
    first = next(d for d in diffs if d["seed"] == 2000)
    assert first["heat_rate_pct"] == pytest.approx(-2.0)
    assert first["fuel_per_mwh_pct"] == pytest.approx(-2.0)
    assert first["band_pp"] == pytest.approx(10.0)
    summary = ev.summarise_main(results)
    auto = summary["modes"]["autonomous"]
    assert auto["heat_rate_pct"]["mean"] == pytest.approx(-1.0)
    assert auto["violations"]["runs_with_violation"] == 0


def test_decision_counts_use_the_status_at_creation():
    dec = [
        {"problem": "load_setpoint", "initial_status": "applied", "status": "applied",
         "approved": True, "failed_checks": []},
        {"problem": "load_setpoint", "initial_status": "escalated", "status": "superseded",
         "approved": False, "failed_checks": ["model_mismatch"]},
    ]  # fmt: skip
    counts = ev._initial_counts([_fake("clean_part_load", "autonomous", 2000, 1.0, decisions=dec)])
    assert counts["decisions"] == 2 and counts["escalated"] == 1
    assert counts["approved_share"] == pytest.approx(0.5)
    assert counts["escalation_reasons"] == {"model_mismatch": 1}


def test_score_on_a_synthetic_record():
    rec = RunRecord(lhv_kj_kg=50_000.0)
    for t in range(10):
        rec.t_s.append(float(t))
        rec.power_mw.append(36.0)
        rec.fuel_kg_s.append(2.0)
        rec.exhaust_k.append(800.0 + (10.0 if t >= 7 else 0.0))
        rec.limit_k.append(803.0)
        rec.trip_k.append(843.0)
        rec.state.append("loaded")
        rec.demand_mw.append(35.0)
    s = score(rec, 2.0, from_s=2.0)
    assert s["fuel_kg"] == pytest.approx(16.0)
    assert s["violation_s"] == 3.0 and s["max_over_limit_k"] == pytest.approx(7.0)
    assert s["band_compliance"] == pytest.approx(1.0)
    assert s["heat_rate_kj_per_kwh"] == pytest.approx(16.0 * 50_000.0 / (36.0 * 8 / 3.6))


def test_wash_study_scripts_and_cost_accounting():
    for h in (None, *ev.WASH_INTERVALS_H):
        item = ev.wash_study_scenario(h)
        check_script(item)
        assert ev.get_scenario(item.id).script == item.script
    w = ev.Economics().effective_wash_cost_usd
    results = [
        _fake("wash_study_never", "manual", 2000, 11000.0, energy=200.0),
        _fake("wash_study_every_1h", "manual", 2000, 10500.0, energy=190.0,
              wash={"washes": 4, "mean_fouling_pct": 1.0, "max_fouling_pct": 2.0}),
    ]  # fmt: skip
    summary = ev.summarise_wash(results)
    rows = {r["policy"]: r for r in summary["per_run"]}
    never, every = rows["never"], rows["every_1h"]
    # Fuel cost is compared at the no-wash run's energy, plus the effective wash cost.
    assert every["fuel_cost_eq_usd"] == pytest.approx(never["fuel_cost_usd"] * 10500 / 11000)
    assert every["total_cost_usd"] == pytest.approx(every["fuel_cost_eq_usd"] + 4 * w)


def test_large_mismatch_is_registered_and_larger():
    assert ev.LARGE_MISMATCH in MISMATCHES
    base = MISMATCHES["combined"].engine()
    big = MISMATCHES[ev.LARGE_MISMATCH].engine()
    assert big.air_mass_flow_kg_s < base.air_mass_flow_kg_s
    assert big.inlet_pressure_loss_fraction > base.inlet_pressure_loss_fraction


def test_run_spec_key_depends_on_settings():
    a = ev.RunSpec("clean_part_load", "advisory", 2000)
    assert a.key() == ev.RunSpec("clean_part_load", "advisory", 2000).key()
    assert a.key() != ev.RunSpec("clean_part_load", "advisory", 2000, operator_delay_s=60).key()
    assert a.key() != ev.RunSpec("clean_part_load", "advisory", 2001).key()


def test_short_supervised_run_logs_decisions(tmp_path):
    spec = ev.RunSpec("clean_part_load", "autonomous", 1000, until_s=900.0)
    stats = ev.ensure_results([spec], tmp_path, workers=1, progress=False)
    assert stats["computed"] == 1
    (result,) = ev.load_results([spec], tmp_path)
    json.dumps(result)
    assert result["score"]["energy_mwh"] > 0 and result["score"]["trips"] == 0
    assert result["decisions"], "the layer should have evaluated the load setpoint"
    assert {d["problem"] for d in result["decisions"]} <= {"load_setpoint"}
    assert ev.ensure_results([spec], tmp_path, workers=1)["cached"] == 1


def test_a_refused_wash_does_not_strand_the_unit_at_standstill():
    from turbineiq.prescription import Supervisor, SupervisorConfig
    from turbineiq.simulation.session import Session, SessionConfig

    session = Session(SessionConfig(seed=1))
    assert session.snapshot()["state"] == "standstill"
    sup = Supervisor(session, SupervisorConfig(mode="advisory"))
    sup._procedure = ["wash_compressor", "start"]  # as an accepted wash leaves it
    sup.tick()  # no fouling: the plant refuses the wash
    assert sup.counters["washes_refused"] == 1 and sup.last_procedure_error
    sup.tick()
    assert sup._procedure == [] and session.snapshot()["state"] != "standstill"
