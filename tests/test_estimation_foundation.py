"""Shared WP4 foundation: observation/truth split, quasi-steady twin, steady-state gate."""

from __future__ import annotations

import dataclasses
import statistics

import pytest

from turbineiq.estimation import (
    Observation,
    QuasiSteadyTwin,
    SteadyStateGate,
    Truth,
    run_streams,
    scenario_with_seed,
)
from turbineiq.simulation.maps import CLEAN
from turbineiq.simulation.scenarios import scenario


@pytest.fixture(scope="module")
def clean_streams():
    return run_streams(scenario("clean_part_load"), until_s=1200.0)


def test_observations_carry_no_ground_truth(clean_streams):
    observations, truths = clean_streams
    assert len(observations) == len(truths) > 1000
    names = {f.name for f in dataclasses.fields(Observation)}
    assert not any("true" in name or "health" in name for name in names)
    assert isinstance(truths[0], Truth) and truths[0].health == CLEAN


def test_the_twin_matches_the_plant_at_steady_state_with_the_true_health(clean_streams):
    observations, truths = clean_streams
    twin, gate = QuasiSteadyTwin(), SteadyStateGate()
    residuals = []
    for obs, truth in zip(observations, truths, strict=True):
        if gate.update(obs):
            p = twin.predict(truth.health, obs)
            residuals.append((obs.power_mw - p.power_mw, obs.exhaust_k - p.exhaust_k))
    assert len(residuals) > 300
    power, exhaust = zip(*residuals, strict=True)
    # Zero mean; the spread is measurement noise, including fuel-meter noise on the input.
    assert abs(statistics.mean(power)) < 0.05
    assert abs(statistics.mean(exhaust)) < 0.5


def test_the_gate_is_closed_during_start_up_and_after_an_input_change(clean_streams):
    observations, _ = clean_streams
    gate = SteadyStateGate(window_s=120.0)
    opened = [obs.t_s for obs in observations if gate.update(obs)]
    assert opened and opened[0] >= 420.0  # loaded near 300 s, then a full quiet window
    moved = dataclasses.replace(observations[-1], t_s=observations[-1].t_s + 1.0)
    moved = dataclasses.replace(moved, load_setpoint_mw=moved.load_setpoint_mw + 5.0)
    assert gate.update(moved) is False


def test_a_seed_variant_is_a_distinct_scenario():
    item = scenario("fouling_step_part_load")
    variant = scenario_with_seed(item, 9001)
    assert variant.seed == 9001 and variant.id == "fouling_step_part_load@9001"
    assert variant.script == item.script
