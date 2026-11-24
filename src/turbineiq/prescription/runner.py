"""Run a scenario of the bank with the supervisor in the loop and a simulated operator.

The scenario script is split into what happens to the unit whatever the layer does
(faults, ambient changes, the start, a scripted shutdown) and the dispatcher's load
requests. A load request is applied as the operator would (the setpoint follows dispatch in
every mode) and also becomes the supervisor's demand, so the layer optimises inside the band
around it.

The simulated operator is an assumption, stated in :class:`OperatorModel`: it reacts to an
open recommendation after a fixed delay, accepts the ones the guard approved, and does not
apply the ones the guard rejected, except for problems listed in ``accept_escalated`` (by
default the wash, which the guard always hands to the operator because it is a shutdown).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from turbineiq.simulation.plant import CommandError
from turbineiq.simulation.scenarios import GROUND_TRUTH_COMMANDS, Scenario, check_script
from turbineiq.simulation.session import Session

from .supervisor import Mode, Supervisor, SupervisorConfig


@dataclass(frozen=True)
class OperatorModel:
    delay_s: float = 300.0
    accept_escalated: tuple[str, ...] = ("compressor_wash",)


@dataclass
class RunRecord:
    """Per-second true plant values for scoring (never shown to the supervisor)."""

    t_s: list[float] = field(default_factory=list)
    power_mw: list[float] = field(default_factory=list)
    fuel_kg_s: list[float] = field(default_factory=list)
    exhaust_k: list[float] = field(default_factory=list)
    limit_k: list[float] = field(default_factory=list)
    trip_k: list[float] = field(default_factory=list)
    state: list[str] = field(default_factory=list)
    demand_mw: list[float | None] = field(default_factory=list)
    lhv_kj_kg: float = 0.0
    skipped: list[dict[str, Any]] = field(default_factory=list)


def run_supervised(
    scenario: Scenario,
    mode: Mode | str,
    *,
    config: SupervisorConfig | None = None,
    operator: OperatorModel | None = None,
    until_s: float | None = None,
) -> tuple[Session, Supervisor, RunRecord]:
    check_script(scenario)
    cfg = config or SupervisorConfig()
    from dataclasses import replace

    cfg = replace(cfg, mode=Mode(mode))
    op = operator or OperatorModel()
    end_s = scenario.duration_s if until_s is None else min(until_s, scenario.duration_s)
    session = Session(scenario.config())
    sup = Supervisor(session, cfg)
    rec = RunRecord(lhv_kj_kg=session.plant.maps.fuel_lhv_kj_kg)
    script = list(scenario.script)
    index = 0
    steps_per_s = round(1.0 / session.dt)
    total_s = int(round(end_s))
    for second in range(total_s + 1):
        t = float(second)
        while index < len(script) and script[index].t_s <= t + 1e-9:
            step = script[index]
            index += 1
            try:
                session.apply(step.command, dict(step.params))
            except CommandError as exc:
                if step.command in GROUND_TRUTH_COMMANDS - {"wash_compressor"}:
                    raise
                # A scripted operator step the layer has made moot (e.g. a wash it already
                # ran) is skipped and recorded.
                rec.skipped.append({"t_s": step.t_s, "command": step.command, "error": str(exc)})
                continue
            if step.command == "set_load":
                sup.set_demand(float(step.params["mw"]))
        if second > 0:
            session.advance(steps_per_s)
        sup.tick()
        _operator(sup, op, t)
        snap = session.snapshot()
        rec.t_s.append(t)
        rec.power_mw.append(snap["electrical_power_mw"])
        rec.fuel_kg_s.append(snap["fuel_flow_kg_s"])
        rec.exhaust_k.append(snap["exhaust_temperature_k"])
        rec.limit_k.append(snap["temperature_limit_k"])
        rec.trip_k.append(snap["trip_temperature_k"])
        rec.state.append(snap["state"])
        rec.demand_mw.append(sup.demand_mw)
    return session, sup, rec


def _operator(sup: Supervisor, op: OperatorModel, t: float) -> None:
    for d in list(sup.open_decisions()):
        if t - d.t_s < op.delay_s - 1e-9:
            continue
        if d.status == "pending" or d.problem in op.accept_escalated:
            sup.accept(d.id, by="simulated operator")
        else:
            sup.reject(d.id, by="simulated operator")


#: True exhaust this far above the temperature control limit counts as a hard-limit
#: violation (an alarm level, labelled assumption; the trip is 40 K higher still).
VIOLATION_MARGIN_K = 5.0


def score(rec: RunRecord, band_mw: float, *, from_s: float = 0.0) -> dict[str, Any]:
    """Fuel, energy, heat rate, band compliance and limit exposure from the true values."""

    dt = 1.0
    fuel_kg = energy_mwh = 0.0
    loaded_s = in_band_s = 0.0
    over_limit_ks = 0.0
    over_limit_s = 0.0
    max_over = 0.0
    violation_s = 0.0
    trips = 0
    prev_state = None
    for i, t in enumerate(rec.t_s):
        state = rec.state[i]
        if state == "tripped" and prev_state != "tripped":
            trips += 1
        prev_state = state
        if t < from_s:
            continue
        fuel_kg += rec.fuel_kg_s[i] * dt
        energy_mwh += rec.power_mw[i] * dt / 3600.0
        over = rec.exhaust_k[i] - rec.limit_k[i]
        if over > 0:
            over_limit_ks += over * dt
            over_limit_s += dt
            max_over = max(max_over, over)
            if over > VIOLATION_MARGIN_K:
                violation_s += dt
        d = rec.demand_mw[i]
        if state == "loaded" and d is not None:
            loaded_s += dt
            if d - band_mw - 0.5 <= rec.power_mw[i] <= d + band_mw + 0.5:
                in_band_s += dt
    heat_rate = (
        fuel_kg * rec.lhv_kj_kg / (energy_mwh * 1000.0) if energy_mwh > 0 else None
    )  # kJ per kWh
    return {
        "fuel_kg": fuel_kg,
        "energy_mwh": energy_mwh,
        "heat_rate_kj_per_kwh": heat_rate,
        "band_compliance": in_band_s / loaded_s if loaded_s else None,
        "over_limit_k_s": over_limit_ks,
        "over_limit_s": over_limit_s,
        "max_over_limit_k": max_over,
        "violation_s": violation_s,
        "trips": trips,
    }
