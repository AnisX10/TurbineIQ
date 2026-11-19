"""The seeded scenario bank: scripts are valid, runs carry their ground truth, logs replay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from turbineiq.simulation.scenarios import (
    GROUND_TRUTH_COMMANDS,
    SCENARIOS,
    check_script,
    run_scenario,
    scenario,
    trace_rows,
)
from turbineiq.simulation.session import replay

MANIFEST = Path(__file__).resolve().parents[1] / "data" / "scenarios" / "manifest.json"


def test_ids_are_unique_and_every_category_is_covered():
    ids = [item.id for item in SCENARIOS]
    assert len(ids) == len(set(ids))
    assert {item.category for item in SCENARIOS} == {
        "baseline",
        "degradation",
        "maintenance",
        "sensor",
        "actuator",
    }
    assert len({item.seed for item in SCENARIOS}) == len(SCENARIOS)


@pytest.mark.parametrize("item", SCENARIOS, ids=lambda item: item.id)
def test_scripts_are_well_formed(item):
    check_script(item)
    has_faults = bool(item.fault_events())
    assert has_faults == (item.category != "baseline")


def test_unknown_scenario_and_bad_scripts_are_rejected():
    with pytest.raises(KeyError):
        scenario("no_such_scenario")
    item = scenario("fouling_step_part_load")
    broken = type(item)(**{**item.__dict__, "duration_s": 100.0})
    with pytest.raises(ValueError, match="within the run"):
        check_script(broken)


def test_a_truncated_run_carries_the_fault_from_its_onset():
    item = scenario("fouling_step_part_load")
    onset = item.fault_events()[0]["t_s"]
    session = run_scenario(item, until_s=onset + 60.0)
    rows = list(trace_rows(session))
    before = [r for r in rows if r["t_s"] < onset]
    after = [r for r in rows if r["t_s"] > onset]
    assert all(r["true_compressor_flow_capacity_delta"] == 0.0 for r in before)
    assert all(r["true_compressor_flow_capacity_delta"] == pytest.approx(-0.03) for r in after)
    assert rows[-1]["state"] == "loaded"
    # The ground truth travels with the measured channels but is clearly separated.
    assert any(key.startswith("meas_") for key in rows[0])
    assert any(key.startswith("true_") for key in rows[0])

    log = session.log()
    assert {e["command"] for e in log["events"]} & GROUND_TRUTH_COMMANDS == {"inject_degradation"}
    assert replay(log).trace_digest() == log["trace_digest"]


def test_manifest_matches_the_scenario_definitions():
    manifest = json.loads(MANIFEST.read_text())
    assert manifest["trace_format"] == 2
    by_id = {entry["id"]: entry for entry in manifest["scenarios"]}
    assert set(by_id) == {item.id for item in SCENARIOS}
    for item in SCENARIOS:
        entry = by_id[item.id]
        assert entry["seed"] == item.seed
        assert entry["duration_s"] == item.duration_s
        assert entry["script"] == [step.to_dict() for step in item.script]
        assert entry["ground_truth_fault_events"] == item.fault_events()
        assert entry["end_state"]["state"] == "loaded"
        assert entry["end_state"]["trip_cause"] is None
        log = json.loads((MANIFEST.parent / "logs" / f"{item.id}.json").read_text())
        assert log["trace_digest"] == entry["trace_digest"]
        assert log["steps"] == entry["steps"] == round(item.duration_s / manifest["dt_s"])
