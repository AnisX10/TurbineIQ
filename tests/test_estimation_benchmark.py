"""WP4 benchmark harness: seeds, stream cache, registry, metrics and runner."""

from __future__ import annotations

import dataclasses
import json
import math
import sys
import textwrap

import numpy as np
import pytest

from turbineiq.estimation import run_streams
from turbineiq.estimation.benchmark import (
    DETECTOR,
    ESTIMATOR,
    REGISTRY,
    Entry,
    ReferenceEstimate,
    ReferenceOutput,
    ScoringConfig,
    StreamContext,
    cache_key,
    cache_path,
    convergence_time,
    ensure_streams,
    evaluation_seeds,
    expected_isolation,
    format_markdown,
    is_evaluation_seed,
    load_streams,
    resolve,
    run_benchmark,
    run_detector,
    run_estimator,
    score_detections,
    score_estimates,
    score_isolation,
    scoring_window,
    seed_cache_from_traces,
    seeds_for,
    select_scenarios,
    source_fingerprint,
    summarize,
    t_quantile_975,
)
from turbineiq.simulation.maps import Health
from turbineiq.simulation.scenarios import Scenario, ScriptStep, scenario

# A short fouling scenario so that end-to-end tests run in seconds: loaded near 237 s,
# 3 percent fouling at 600 s, end at 900 s.
SHORT = Scenario(
    "short_fouling",
    "degradation",
    "Test scenario: 3 percent fouling at 600 s.",
    77,
    900.0,
    (
        ScriptStep(0.0, "start"),
        ScriptStep(300.0, "set_load", {"mw": 35.0, "ramp_mw_per_min": 60.0}),
        ScriptStep(
            600.0,
            "inject_degradation",
            {"kind": "compressor_fouling", "severity_pct": 3.0, "rate_pct_per_h": None},
        ),
    ),
)


def _ctx(n=3600, onset=None, loaded_from=0.0, steady_from=None, health=None, more_events=()):
    t = np.arange(n, dtype=float)
    return StreamContext(
        t_s=t,
        health=np.zeros((n, 3)) if health is None else health,
        loaded=t >= loaded_from,
        steady=t >= (loaded_from if steady_from is None else steady_from),
        event_times=(() if onset is None else (float(onset),)) + tuple(more_events),
        dt_s=1.0,
    )


# ----------------------------------------------------------------------------------- seeds


def test_seed_policies_keep_tuning_and_evaluation_apart():
    item = scenario("fouling_step_part_load")
    assert evaluation_seeds(item) == [201, 10201, 20201, 30201, 40201]
    assert seeds_for(item, "eval") == evaluation_seeds(item)
    assert seeds_for(item, "bank") == [201] and seeds_for(item, "eval:2") == [201, 10201]
    assert seeds_for(item, "tune:3") == [1000, 1001, 1002]
    assert seeds_for(item, "1500,10201") == [1500, 10201]
    with pytest.raises(ValueError):
        seeds_for(item, "999")  # neither a tuning seed nor one of this scenario's trials
    assert is_evaluation_seed(40201) and not is_evaluation_seed(1500)
    assert not any(is_evaluation_seed(s) for s in range(1000, 2000))


def test_scenario_selection_by_id_glob_and_category():
    ids = [s.id for s in select_scenarios(["fouling_*,cdt_sensor_bias"])]
    assert ids[0] == "fouling_step_part_load" and "cdt_sensor_bias" in ids and len(ids) == 5
    assert all(s.category == "sensor" for s in select_scenarios(["category:sensor"]))
    assert len(select_scenarios(None)) == 19
    with pytest.raises(ValueError):
        select_scenarios(["no_such_*"])


# ----------------------------------------------------------------------------------- cache


def test_cache_key_follows_the_definition_seed_and_model():
    key = cache_key(SHORT, 5, fingerprint="m1")
    assert key.startswith("short_fouling__seed5__")
    assert cache_key(SHORT, 6, fingerprint="m1") != key
    assert cache_key(SHORT, 5, fingerprint="m2") != key  # changed plant code
    later = SHORT.script[:2] + (dataclasses.replace(SHORT.script[2], t_s=650.0),)
    assert cache_key(dataclasses.replace(SHORT, script=later), 5, fingerprint="m1") != key
    hotter = dataclasses.replace(SHORT, ambient_temperature_c=25.0)
    assert cache_key(hotter, 5, fingerprint="m1") != key
    relabelled = dataclasses.replace(SHORT, description="new words", category="other")
    assert cache_key(relabelled, 5, fingerprint="m1") == key  # labels do not matter
    assert "__until60__" in cache_key(SHORT, 5, 60.0, fingerprint="m1")
    assert cache_key(SHORT, 5, 900.0, fingerprint="m1") == key  # until >= duration is full


def test_source_fingerprint_ignores_comments_and_docstrings_only():
    base = 'def f(x):\n    """Doc."""\n    return x + 1\n'
    same = "# note\ndef f(x):\n    '''Other doc.'''\n\n    return x + 1  # one\n"
    assert source_fingerprint(base) == source_fingerprint(same)
    assert source_fingerprint(base) != source_fingerprint(base.replace("+ 1", "+ 2"))


def test_cached_stream_round_trips_and_a_changed_script_regenerates(tmp_path):
    item = dataclasses.replace(SHORT, duration_s=60.0, script=SHORT.script[:1])
    stats = ensure_streams([(item, 1000)], tmp_path, workers=1)
    assert stats["generated"] == 1
    path = cache_path(tmp_path, item, 1000)
    assert path.exists() and path.name.endswith(".csv.gz")
    assert load_streams(item, 1000, tmp_path, generate=False) == run_streams(item, 1000)
    assert ensure_streams([(item, 1000)], tmp_path, workers=1)["generated"] == 0
    # A truncated stream is cut from the full one without a new run.
    obs, truths = load_streams(item, 1000, tmp_path, until_s=30.0, generate=False)
    assert obs[-1].t_s == 30.0 and len(obs) == len(truths) == 31
    # Any change to the script gives a new key, so the old file is not used.
    changed = dataclasses.replace(item, script=(dataclasses.replace(item.script[0], t_s=1.0),))
    assert not cache_path(tmp_path, changed, 1000).exists()
    with pytest.raises(FileNotFoundError):
        load_streams(changed, 1000, tmp_path, generate=False)


def test_the_process_pool_fills_the_cache(tmp_path):
    item = dataclasses.replace(SHORT, duration_s=20.0, script=SHORT.script[:1])
    stats = ensure_streams([(item, 1000), (item, 1001)], tmp_path, workers=2)
    assert stats["generated"] == 2
    assert all(cache_path(tmp_path, item, s).exists() for s in (1000, 1001))


def test_bank_traces_seed_the_cache_only_if_they_match(tmp_path):
    item = dataclasses.replace(SHORT, duration_s=20.0, script=SHORT.script[:1], seed=3)
    traces = tmp_path / "traces"
    traces.mkdir()
    ensure_streams([(item, 3)], tmp_path / "ref", workers=1)
    import gzip

    text = gzip.open(cache_path(tmp_path / "ref", item, 3), "rt", newline="").read()
    (traces / "short_fouling.csv").write_text(text, newline="")
    report = seed_cache_from_traces(traces, tmp_path / "a", [item], check_s=10.0)
    assert report["seeded"] == ["short_fouling"]
    lines = text.split("\r\n")
    lines[3] = lines[3].replace(",", ",9", 1)  # tamper with a value inside the check window
    (traces / "short_fouling.csv").write_text("\r\n".join(lines), newline="")
    report = seed_cache_from_traces(traces, tmp_path / "b", [item], check_s=10.0)
    assert report["rejected"] == ["short_fouling"]


# -------------------------------------------------------------------------------- registry


def test_the_registry_skips_a_missing_module_with_a_message():
    registry = dict(REGISTRY)
    registry["future"] = Entry(
        "future", ESTIMATOR, "turbineiq.estimation._not_written_yet:Thing", "not there"
    )
    registry["renamed"] = Entry("renamed", DETECTOR, "turbineiq.estimation:NoSuchClass", "")
    missing = resolve("future", ESTIMATOR, registry)
    assert not missing.available and "turbineiq.estimation._not_written_yet" in missing.reason
    renamed = resolve("renamed", DETECTOR, registry)
    assert not renamed.available and "NoSuchClass" in renamed.reason
    assert resolve("clean", ESTIMATOR).available
    assert resolve("turbineiq.estimation.benchmark:NeverDetector", DETECTOR).available
    with pytest.raises(KeyError):
        resolve("nonsense", ESTIMATOR)
    with pytest.raises(ValueError):
        resolve("never", ESTIMATOR)


def test_a_broken_import_inside_an_existing_module_is_not_hidden(tmp_path, monkeypatch):
    (tmp_path / "bench_broken_entry.py").write_text("import no_such_dependency_xyz\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ModuleNotFoundError):
        resolve("bench_broken_entry:Thing", ESTIMATOR)
    sys.modules.pop("bench_broken_entry", None)


# --------------------------------------------------------------------------------- running


class _Scripted:
    """Returns the scripted output for each update (None keeps the previous one)."""

    def __init__(self, outputs):
        self._outputs = iter(outputs)

    def update(self, obs):
        return next(self._outputs)


def test_outputs_are_held_until_replaced_and_look_ahead_is_refused():
    obs = [dataclasses.replace(o, t_s=float(i)) for i, o in enumerate(_observations(4))]
    est = ReferenceEstimate
    h1, h2, s = Health(-0.01, 0.0, 0.0), Health(-0.02, 0.0, 0.0), Health(0.001, 0.001, 0.001)
    mean, std = run_estimator(_Scripted([None, est(1.0, h1, s), None, est(3.0, h2, s)]), obs)
    assert np.isnan(mean[0]).all()
    assert mean[1, 0] == mean[2, 0] == -0.01 and mean[3, 0] == -0.02 and std[2, 1] == 0.001
    with pytest.raises(ValueError):
        run_estimator(_Scripted([est(1.0, h1, s)] * 4), obs)
    out = ReferenceOutput
    alarm, stat, channel = run_detector(
        _Scripted([None, out(1.0, True, 5.0, "egt"), None, out(3.0, False, 1.0)]), obs
    )
    assert alarm.tolist() == [False, True, True, False] and channel[2] == "egt"
    assert np.isnan(stat[0]) and stat[2] == 5.0


def _observations(n):
    obs, _ = _short_streams()
    return obs[:n]


_STREAMS: dict = {}


def _short_streams():
    if "short" not in _STREAMS:
        _STREAMS["short"] = run_streams(SHORT, 1000)
    return _STREAMS["short"]


# --------------------------------------------------------------------------------- metrics


def test_scoring_window_skips_settling_after_loading_and_events():
    ctx = _ctx(3000, onset=1800.0, loaded_from=100.0)
    window = scoring_window(ctx, settle_s=300.0)
    assert window.sum() == (1800 - 400) + (3000 - 2100)
    assert not window[399] and window[400] and not window[2099] and window[2100]


def test_error_bias_and_coverage_on_a_known_track():
    n = 2000
    ctx = _ctx(n, loaded_from=0.0)
    mean = np.zeros((n, 3))
    mean[:, 1] = 0.01  # one point too high on compressor efficiency, everywhere
    std = np.full((n, 3), 0.001)
    std[::2, 1] = 0.006  # 2 sigma covers the one-point error on every other sample
    result = score_estimates(ctx, mean, std, settle_s=100.0)
    assert result["window_samples"] == result["scored_samples"] == 1900
    assert result["rms_compressor_efficiency_pts"] == pytest.approx(1.0)
    assert result["bias_compressor_efficiency_pts"] == pytest.approx(1.0)
    assert result["rms_compressor_flow_pct"] == 0.0
    assert result["coverage_compressor_efficiency"] == pytest.approx(0.5)
    assert result["coverage_compressor_flow"] == 1.0
    assert result["coverage_joint"] == pytest.approx(0.5)
    assert result["converged"] is None  # no onset: convergence does not apply
    # No estimate before t = 1000: availability halves and errors use only the rest.
    mean[:1000] = np.nan
    late = score_estimates(ctx, mean, std, settle_s=100.0)
    assert late["scored_samples"] == 1000 and late["availability"] == pytest.approx(1000 / 1900)


def test_convergence_time_is_measured_to_the_last_exit_from_the_band():
    n = 7200
    health = np.zeros((n, 3))
    health[1800:, 0] = -0.03
    ctx = _ctx(n, onset=1800.0, loaded_from=0.0, health=health)
    mean = health.copy()
    mean[1800:2400, 0] = 0.0  # still clean for ten minutes
    mean[3000, 0] = -0.02  # one excursion of one point
    assert convergence_time(ctx, mean, (0.005,) * 3) == 3001.0 - 1800.0
    assert convergence_time(ctx, health, (0.005,) * 3) == 0.0
    mean[-1, 2] = -0.01  # out of band at the end: not converged
    assert convergence_time(ctx, mean, (0.005,) * 3) == math.inf
    result = score_estimates(ctx, mean, np.zeros((n, 3)))
    assert result["converged"] is False and result["convergence_s"] is None
    # Samples while the unit is not loaded are not considered.
    offline = dataclasses.replace(ctx, loaded=(ctx.t_s < 3000) | (ctx.t_s > 3000))
    mean[-1, 2] = 0.0
    assert convergence_time(offline, mean, (0.005,) * 3) == 2400.0 - 1800.0


def test_detection_delay_and_missed_detection():
    ctx = _ctx(3600, onset=1800.0, loaded_from=100.0, steady_from=300.0)
    alarm = np.zeros(3600, dtype=bool)
    alarm[1830:] = True
    hit = score_detections(ctx, alarm, ["egt"] * 3600)
    assert hit["detected"] is True and hit["delay_s"] == 30.0
    assert hit["channel_at_detection"] == "egt"
    miss = score_detections(ctx, np.zeros(3600, dtype=bool))
    assert miss["detected"] is False and miss["delay_s"] is None
    # An alarm still on from before the onset counts from the onset (delay 0) and as one
    # pre-onset false alarm.
    alarm[1700:] = True
    early = score_detections(ctx, alarm)
    assert early["delay_s"] == 0.0 and early["false_alarms_steady"] == 1


def test_false_alarms_per_hour_count_alarm_onsets_in_the_exposure():
    n = 7200
    ctx = _ctx(n, loaded_from=0.0, steady_from=600.0)  # clean: the whole run is exposure
    alarm = np.zeros(n, dtype=bool)
    alarm[100:110] = True  # loaded but not steady: counts only per loaded hour
    alarm[1000:1001] = True
    alarm[3000:3600] = True  # a long alarm is one false alarm
    alarm[5000:5002] = True
    result = score_detections(ctx, alarm)
    assert result["detected"] is None and result["delay_s"] is None
    assert result["false_alarms_steady"] == 3 and result["false_alarms_loaded"] == 4
    assert result["steady_h"] == pytest.approx(6600 / 3600)
    assert result["false_alarms_steady_per_h"] == pytest.approx(3 / (6600 / 3600))
    assert result["false_alarms_loaded_per_h"] == pytest.approx(4 / 2.0)
    assert result["alarm_fraction_steady"] == pytest.approx(603 / 6600)
    # On a fault scenario only the samples before the onset are exposure.
    fault = _ctx(n, onset=2000.0, loaded_from=0.0, steady_from=600.0)
    pre = score_detections(fault, alarm)
    assert pre["false_alarms_steady"] == 1 and pre["steady_h"] == pytest.approx(1400 / 3600)


def test_isolation_is_scored_against_the_first_fault_event():
    assert expected_isolation(scenario("cdt_sensor_bias")) == ("cdt_sensor", "cdt_k")
    assert expected_isolation(scenario("fuel_meter_drift")) == ("fuel_meter", None)
    assert expected_isolation(scenario("fouling_then_erosion")) == ("compressor_fouling", None)
    assert expected_isolation(scenario("slow_fuel_valve_load_steps")) == (None, None)
    assert expected_isolation(scenario("clean_part_load")) == (None, None)
    item = scenario("cdt_sensor_bias")
    ctx = _ctx(3600, onset=1800.0)
    right = score_isolation(item, ctx, {"detected": True, "channel_at_detection": "cdt_k"})
    assert right["channel_correct"] is True and "label_correct" not in right
    wrong = score_isolation(
        item, ctx, {"detected": True, "channel_at_detection": "cdp_kpa"}, "compressor_fouling"
    )
    assert wrong["channel_correct"] is False and wrong["label_correct"] is False
    missed = score_isolation(item, ctx, {"detected": False}, None)
    assert missed["channel_correct"] is None and missed["label_correct"] is None


def test_summary_uses_a_student_t_interval():
    stat = summarize([1.0, 2.0, None, 3.0, 4.0, 5.0])
    assert stat["n"] == 5 and stat["mean"] == 3.0
    assert stat["half_width"] == pytest.approx(2.776 * np.std([1, 2, 3, 4, 5], ddof=1) / 5**0.5)
    assert summarize([2.0])["half_width"] is None and summarize([None])["n"] == 0
    assert t_quantile_975(31) == pytest.approx(2.0395, abs=1e-3)
    assert t_quantile_975(200) == pytest.approx(1.9719, abs=1e-3)


# ---------------------------------------------------------------------------------- runner


def test_reference_entries_score_as_expected_end_to_end(tmp_path):
    obs, truths = _short_streams()
    ensure_streams([(SHORT, 1000)], tmp_path, workers=1)
    registry = dict(REGISTRY)
    registry["future"] = Entry("future", DETECTOR, "turbineiq.estimation._absent:X", "")
    results = run_benchmark(
        ["oracle", "clean"],
        ["never", "future"],
        [SHORT],
        seed_policy="tune:1",
        cache_dir=tmp_path,
        workers=1,
        config=ScoringConfig(settle_s=120.0),
        registry=registry,
    )
    assert len(results["skipped"]) == 1 and "_absent" in results["skipped"][0]
    runs = {run["name"]: run for run in results["runs"]}
    assert set(runs) == {"oracle", "clean", "never"}
    oracle, clean, never = runs["oracle"], runs["clean"], runs["never"]
    assert oracle["rms_compressor_flow_pct"] == 0.0 and oracle["coverage_joint"] == 1.0
    assert oracle["converged"] is True and oracle["convergence_s"] == 0.0
    # The clean estimator's error is the truth itself on the scored samples.
    t = np.array([o.t_s for o in obs])
    loaded = np.array([o.state == "loaded" and o.breaker_closed for o in obs])
    first = t[loaded][0]
    window = loaded & ~((t >= first) & (t < first + 120)) & ~((t >= 600) & (t < 720))
    flow = np.array([tr.health.compressor_flow for tr in truths])[window] * 100
    assert flow.min() == pytest.approx(-3.0)
    assert clean["rms_compressor_flow_pct"] == pytest.approx(np.sqrt(np.mean(flow**2)))
    assert clean["bias_compressor_flow_pct"] == pytest.approx(-np.mean(flow))
    assert clean["converged"] is False
    assert never["detected"] is False and never["false_alarms_steady"] == 0
    assert never["steady_h"] > 0
    text = format_markdown(results)
    assert "NOT an estimator" in text and "`short_fouling`" in text and "_absent" in text


def test_the_command_line_writes_json_and_markdown(tmp_path):
    sys.path.insert(0, "scripts")
    try:
        import run_estimation_benchmark as cli
    finally:
        sys.path.remove("scripts")
    out, md = tmp_path / "r.json", tmp_path / "r.md"
    code = cli.main(
        [
            *("--estimator", "clean", "--detector", "never", "--estimator", "ukf"),
            *("--scenarios", "fouling_step_part_load", "--seeds", "tune:1", "--until-s", "300"),
            *("--workers", "1", "--cache-dir", str(tmp_path / "cache")),
            *("--out", str(out), "--markdown", str(md)),
        ]
    )
    assert code == 0
    results = json.loads(out.read_text())
    assert results["protocol"]["until_s"] == 300.0
    assert {run["name"] for run in results["runs"]} == {"clean", "never"}
    assert md.read_text().startswith("# Estimation benchmark results")


def test_an_entry_that_raises_is_recorded_not_fatal(tmp_path, monkeypatch):
    module = tmp_path / "bench_raising_entry.py"
    module.write_text(
        textwrap.dedent(
            """
            class Boom:
                def update(self, obs):
                    raise RuntimeError("boom")
            """
        )
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    item = dataclasses.replace(SHORT, duration_s=20.0, script=SHORT.script[:1])
    results = run_benchmark(
        ["bench_raising_entry:Boom", "clean"],
        [],
        [item],
        seed_policy="tune:1",
        cache_dir=tmp_path,
        workers=1,
    )
    errors = [run for run in results["runs"] if "error" in run]
    assert len(errors) == 1 and "boom" in errors[0]["error"]
    assert results["summary"][0]["scenarios"]["short_fouling"]["errors"] == 1
    sys.modules.pop("bench_raising_entry", None)
