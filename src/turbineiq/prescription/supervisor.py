"""The supervisor: decision problems, autonomy modes and the decision log.

:class:`Supervisor` sits next to a :class:`~turbineiq.simulation.session.Session`. Call
:meth:`Supervisor.tick` once per simulated second (after advancing the session). It reads a
snapshot, but only the instrument readings and known operating inputs go to the monitor;
the injected ground truth in the snapshot is never used.

Modes
    ``manual``: the layer estimates and watches but proposes nothing.
    ``advisory`` (level 4): every proposal waits for the operator (:meth:`accept`).
    ``autonomous`` (level 5): a proposal the guard approves is applied at once; one it
    rejects waits for the operator, marked ``escalated`` with the failed checks.

Every proposal becomes a :class:`Decision` with its candidates, objective values, guard
verdict and outcome, whether or not it is applied.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from turbineiq.simulation.maps import Health
from turbineiq.simulation.plant import CommandError

from .guard import GuardLimits, GuardVerdict, SafetyGuard
from .monitor import DEFAULT_TWIN_ENGINE, TwinMonitor, TwinStatus, observation_from_snapshot
from .twin import forward_run, predictive_twin


class Mode(str, Enum):
    MANUAL = "manual"
    ADVISORY = "advisory"
    AUTONOMOUS = "autonomous"


#: The IGV setting "auto" is evaluated as fully open (the auto schedule at rated speed).
AUTO = "auto"


@dataclass(frozen=True)
class Economics:
    """Prices for the wash decision. Illustrative values, not market data.

    ``time_compression`` is how many times faster degradation runs in the simulation than in
    service (the bank uses percent per hour where service sees percent per month, about
    720). The wash cost is divided by it so that the optimal wash interval, which scales as
    sqrt(wash cost / fouling cost growth), scales by the same factor.
    """

    fuel_price_usd_per_gj: float = 8.0
    wash_cost_usd: float = 30_000.0  # outage, lost margin and crew for one offline wash
    planning_horizon_h: float = 8760.0  # service hours a wash benefit is counted over at most
    time_compression: float = 720.0

    @property
    def effective_wash_cost_usd(self) -> float:
        return self.wash_cost_usd / self.time_compression

    @property
    def effective_horizon_h(self) -> float:
        return self.planning_horizon_h / self.time_compression


@dataclass(frozen=True)
class SupervisorConfig:
    mode: Mode = Mode.ADVISORY
    demand_band_mw: float = 2.0
    igv_options: tuple[str | float, ...] = (AUTO, 0.8, 0.6, 0.4, 0.2, 0.0)
    review_interval_s: float = 300.0
    wash_review_interval_s: float = 60.0
    min_improvement_pct: float = 0.15
    #: ``track_demand``: hold the dispatcher's target and choose the IGV setting with the
    #: lowest heat rate; use the rest of the band only when the target is not reachable.
    #: ``heat_rate``: the lowest heat rate anywhere in the band (it tends to run at an edge).
    load_objective: str = "track_demand"
    screening_margin_k: float = 3.0  # extra exhaust margin when screening on the steady twin
    settle_extra_s: float = 150.0  # forward horizon beyond the ramp time
    max_forward_checks: int = 3
    substitute_refresh_s: float = 5.0
    min_fouling_for_wash: float = 0.005  # flow-capacity loss below this is within twin bias
    twin_engine: str | None = DEFAULT_TWIN_ENGINE
    economics: Economics = field(default_factory=Economics)
    limits: GuardLimits = field(default_factory=GuardLimits)


OPEN_STATUSES = ("pending", "escalated")


@dataclass
class Decision:
    id: int
    t_s: float
    problem: str  # load_setpoint, compressor_wash or exhaust_feedback
    mode: str
    summary: str
    actions: list[dict[str, Any]]
    objective: dict[str, Any]
    verdict: dict[str, Any]
    status: str  # applied, pending, escalated, accepted, rejected, expired, superseded
    reason: str
    resolved_t_s: float | None = None
    resolved_by: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @property
    def open(self) -> bool:
        return self.status in OPEN_STATUSES


class Supervisor:
    def __init__(self, session, config: SupervisorConfig | None = None) -> None:
        self.session = session
        self.config = config or SupervisorConfig()
        self.mode = Mode(self.config.mode)
        self.guard = SafetyGuard(self.config.limits)
        self.monitor = TwinMonitor(self.config.twin_engine)
        self.decisions: list[Decision] = []
        self.status: TwinStatus | None = None
        self.demand_mw: float | None = None
        self._demand_changed = False
        self._ambient: float | None = None
        self._last_review_s: float | None = None
        self._last_wash_review_s: float | None = None
        self._last_action_s: dict[str, float] = {}
        self._last_substitute_s: float | None = None
        self.substitute_active = False
        self._procedure: list[str] = []
        self._procedure_decision: int | None = None
        self._last_wash_s = 0.0
        self.last_load_evaluation: dict[str, Any] | None = None
        self.last_wash_evaluation: dict[str, Any] | None = None
        self.counters = {"forward_runs": 0, "substitute_updates": 0}

    # ------------------------------------------------------------------ operator API
    def set_mode(self, mode: Mode | str) -> None:
        self.mode = Mode(mode)

    def set_demand(self, mw: float) -> None:
        """The dispatcher's target; the layer may run anywhere in target ± band."""

        if not math.isfinite(mw) or mw < 0:
            raise ValueError("demand must be a finite, non-negative number of MW")
        if self.demand_mw is None or abs(mw - self.demand_mw) > 1e-9:
            self._demand_changed = True
        self.demand_mw = float(mw)

    @property
    def band(self) -> tuple[float, float] | None:
        if self.demand_mw is None:
            return None
        d = self.config.demand_band_mw
        return (self.demand_mw - d, self.demand_mw + d)

    def open_decisions(self) -> list[Decision]:
        return [d for d in self.decisions if d.open]

    def get(self, decision_id: int) -> Decision:
        for d in self.decisions:
            if d.id == decision_id:
                return d
        raise KeyError(decision_id)

    def accept(self, decision_id: int, by: str = "operator") -> Decision:
        """The operator applies an open recommendation (also an escalated one: the operator
        is the authority the guard escalates to)."""

        d = self.get(decision_id)
        if not d.open:
            raise ValueError(f"decision {decision_id} is {d.status}, not open")
        t = self._now()
        if d.problem == "load_setpoint" and not self._still_valid(d):
            self._resolve(d, "expired", t, by, "the demand or unit state changed since")
            return d
        self._execute(d)
        self._resolve(d, "accepted", t, by, d.reason)
        return d

    def reject(self, decision_id: int, by: str = "operator") -> Decision:
        d = self.get(decision_id)
        if not d.open:
            raise ValueError(f"decision {decision_id} is {d.status}, not open")
        self._resolve(d, "rejected", self._now(), by, d.reason)
        return d

    def trust_thermocouple(self) -> None:
        """Operator: the thermocouple is repaired; return the control to it."""

        self.monitor.trust_thermocouple()
        if self.substitute_active:
            self.session.apply("set_exhaust_feedback", {"source": "thermocouple", "value_k": None})
            self.substitute_active = False

    # ------------------------------------------------------------------ main loop
    def tick(self) -> TwinStatus:
        snap = self.session.snapshot()
        obs = observation_from_snapshot(snap)
        status = self.monitor.update(obs)
        self.status = status
        t = obs.t_s
        if self.demand_mw is None and status.loaded:
            self.set_demand(obs.load_setpoint_mw)
        ambient = obs.ambient_temperature_c
        if self._ambient is not None and ambient != self._ambient:
            self._demand_changed = True  # re-optimise after an ambient change too
        self._ambient = ambient

        self._refresh_substitute(t, status)
        if self._procedure:
            self._advance_procedure(snap)
            return status
        if self.mode == Mode.MANUAL:
            self._demand_changed = False
            return status
        self._review_exhaust(t, status)
        self._review_load(t, obs, snap, status)
        self._review_wash(t, obs, snap, status)
        return status

    # ------------------------------------------------------------------ (c) thermocouple
    def _review_exhaust(self, t: float, status: TwinStatus) -> None:
        if not status.exhaust_suspect or self.substitute_active:
            return
        if any(d.problem == "exhaust_feedback" and d.open for d in self.decisions):
            return
        verdict = self.guard.verify_substitute(status)
        value = status.model_exhaust_k
        actions = [
            {
                "command": "set_exhaust_feedback",
                "params": {
                    "source": "model",
                    "value_k": None if value is None else round(value, 2),
                },
            }
        ]
        self._decide(
            t,
            "exhaust_feedback",
            "Switch the temperature control to the model exhaust estimate "
            f"({status.exhaust_reason}).",
            actions,
            {
                "model_exhaust_k": value,
                "exhaust_residual_k": status.exhaust_residual_k,
                "exhaust_scatter_k": status.exhaust_scatter_k,
            },
            verdict,
        )

    def _refresh_substitute(self, t: float, status: TwinStatus) -> None:
        if not self.substitute_active or status.model_exhaust_k is None:
            return
        last = self._last_substitute_s
        if last is not None and t - last < self.config.substitute_refresh_s - 1e-9:
            return
        self.session.apply(
            "set_exhaust_feedback",
            {"source": "model", "value_k": round(status.model_exhaust_k, 2)},
        )
        self._last_substitute_s = t
        self.counters["substitute_updates"] += 1

    # ------------------------------------------------------------------ (a) load and IGV
    def _review_load(self, t: float, obs, snap: dict[str, Any], status: TwinStatus) -> None:
        cfg = self.config
        if not status.loaded or self.band is None:
            return
        due = self._last_review_s is None or t - self._last_review_s >= cfg.review_interval_s
        if not (due or self._demand_changed):
            return
        if status.estimator_updates == 0:
            return
        self._last_review_s = t
        self._demand_changed = False
        lo, hi = self.band
        lim = cfg.limits
        plant = self.session.plant
        limit_k = plant.temperature_limit_k
        uncertainty = 0.0 if status.exhaust_suspect else abs(status.exhaust_residual_k or 0.0)
        screen_limit = limit_k - lim.control_margin_k - uncertainty - cfg.screening_margin_k
        floor = plant.p.min_load_mw
        loads = sorted({round(x, 3) for x in (lo, self.demand_mw, hi) if x >= floor})
        candidates = []
        for load in loads:
            for igv in cfg.igv_options:
                position = 1.0 if igv == AUTO else float(igv)
                try:
                    fuel, exhaust, hr = self.monitor.steady_point(obs, load, position)
                except (ValueError, ZeroDivisionError):
                    continue
                candidates.append(
                    {
                        "load_mw": load,
                        "igv": igv,
                        "fuel_kg_s": round(fuel, 5),
                        "exhaust_k": round(exhaust, 2),
                        "heat_rate_kj_per_kwh": round(hr, 2),
                        "feasible": exhaust <= screen_limit,
                    }
                )
        current_igv: str | float = AUTO if snap["igv_mode"] == "auto" else float(plant.igv_manual)
        setpoint = float(snap["load_setpoint_mw"])
        cur_position = 1.0 if current_igv == AUTO else float(current_igv)
        try:
            _, cur_exhaust, cur_hr = self.monitor.steady_point(obs, setpoint, cur_position)
        except (ValueError, ZeroDivisionError):
            return
        current_ok = lo - 1e-9 <= setpoint <= hi + 1e-9 and cur_exhaust <= screen_limit
        if cfg.load_objective not in ("track_demand", "heat_rate"):
            raise ValueError("load_objective must be 'track_demand' or 'heat_rate'")
        demand = self.demand_mw

        def key(c: dict[str, Any]) -> tuple[float, float]:
            if cfg.load_objective == "heat_rate":
                return (0.0, c["heat_rate_kj_per_kwh"])
            return (round(abs(c["load_mw"] - demand), 3), c["heat_rate_kj_per_kwh"])

        feasible = sorted((c for c in candidates if c["feasible"]), key=key)
        self.last_load_evaluation = {
            "t_s": t,
            "band_mw": [lo, hi],
            "current": {
                "load_mw": setpoint,
                "igv": current_igv,
                "exhaust_k": round(cur_exhaust, 2),
                "heat_rate_kj_per_kwh": round(cur_hr, 2),
                "within_limits": current_ok,
            },
            "screen_exhaust_limit_k": round(screen_limit, 2),
            "candidates": candidates,
        }
        if not feasible:
            return
        best = feasible[0]
        gain = 100.0 * (cur_hr - best["heat_rate_kj_per_kwh"]) / cur_hr
        tol = lim.power_tolerance_mw
        meeting_band = lo - tol <= obs.power_mw <= hi + tol
        if current_ok:
            moves_toward_target = (
                cfg.load_objective == "track_demand"
                and abs(best["load_mw"] - self.demand_mw) < abs(setpoint - self.demand_mw) - 1e-6
            )
            if gain < cfg.min_improvement_pct and not moves_toward_target:
                return
        elif meeting_band:
            # Running on the exhaust temperature limit while delivering inside the band is
            # normal base-load operation; the layer does not back off from it.
            return
        open_load = [d for d in self.decisions if d.problem == "load_setpoint" and d.open]
        best_actions = self._load_actions(best, setpoint, current_igv)
        if any(d.actions == best_actions for d in open_load):
            return  # the same recommendation is still waiting; keep its place in the queue
        for d in open_load:
            self._resolve(d, "superseded", t, "layer", "a newer evaluation replaced it")
        last = self._last_action_s.get("load_setpoint")
        since = None if last is None else t - last
        tried = []
        chosen = None
        verdict: GuardVerdict | None = None
        twin = None
        for cand in feasible[: cfg.max_forward_checks]:
            actions = self._load_actions(cand, setpoint, current_igv)
            if not actions:
                continue
            if twin is None:
                twin = predictive_twin(
                    plant,
                    self.monitor.engine,
                    status.health,
                    fuel_kg_s=obs.fuel_kg_s,
                    speed_pu=obs.speed_pu,
                )
            step = abs(cand["load_mw"] - setpoint)
            horizon = step / lim.max_ramp_mw_per_min * 60.0 + cfg.settle_extra_s
            fw = forward_run(twin, actions, horizon)
            self.counters["forward_runs"] += 1
            v = self.guard.verify_load(
                status,
                current_setpoint_mw=setpoint,
                target_mw=cand["load_mw"],
                band=(lo, hi),
                ramp_mw_per_min=lim.max_ramp_mw_per_min,
                forward=fw,
                exhaust_trusted_or_substituted=(not status.exhaust_suspect)
                or self.substitute_active,
                since_last_action_s=since if self.mode == Mode.AUTONOMOUS else None,
            )
            tried.append({"candidate": cand, "approved": v.approved, "reason": v.reason()})
            if chosen is None or (v.approved and not verdict.approved):
                chosen, verdict = (cand, actions), v
            if v.approved:
                break
        if chosen is None or verdict is None:
            return
        cand, actions = chosen
        igv_text = "IGV auto" if cand["igv"] == AUTO else f"IGV {float(cand['igv']):.0%} open"
        hr_gain = 100.0 * (cur_hr - cand["heat_rate_kj_per_kwh"]) / cur_hr
        summary = (
            f"Run at {cand['load_mw']:.1f} MW with {igv_text}: heat rate "
            f"{cand['heat_rate_kj_per_kwh']:.0f} kJ/kWh, {hr_gain:+.2f} % against now "
            f"({cur_hr:.0f} kJ/kWh), inside the {lo:.1f}-{hi:.1f} MW band."
        )
        self._decide(
            t,
            "load_setpoint",
            summary,
            actions,
            {
                "current": self.last_load_evaluation["current"],
                "proposed": cand,
                "heat_rate_gain_pct": round(hr_gain, 3),
                "band_mw": [lo, hi],
                "demand_mw": self.demand_mw,
                "forward_checked": tried,
            },
            verdict,
        )

    def _load_actions(
        self, cand: dict[str, Any], setpoint: float, current_igv: str | float
    ) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        lim = self.config.limits
        if abs(cand["load_mw"] - setpoint) > 1e-6:
            actions.append(
                {
                    "command": "set_load",
                    "params": {"mw": cand["load_mw"], "ramp_mw_per_min": lim.max_ramp_mw_per_min},
                }
            )
        if cand["igv"] != current_igv:
            if cand["igv"] == AUTO:
                actions.append({"command": "set_igv", "params": {"mode": "auto", "position": None}})
            else:
                actions.append(
                    {
                        "command": "set_igv",
                        "params": {"mode": "manual", "position": float(cand["igv"])},
                    }
                )
        return actions

    def _still_valid(self, d: Decision) -> bool:
        st = self.status
        if st is None or not st.loaded:
            return False
        band = d.objective.get("band_mw")
        return band is not None and self.band is not None and list(self.band) == list(band)

    # ------------------------------------------------------------------ (b) wash
    def wash_economics(self, obs, status: TwinStatus) -> dict[str, Any] | None:
        """Excess fuel cost of the estimated compressor fouling and the wash threshold.

        The loss rate is the extra fuel the twin needs at the present power and IGV with the
        estimated health against the same health with the compressor washed clean (the
        turbine part stays). The threshold is the long-run average cost per hour of an
        optimal wash cycle under linear fouling growth, sqrt(2 W a) (W the wash cost, a the
        growth of the loss rate per hour), and at least W / H (H the planning horizon), so a
        fouling level that does not grow is still washed when it pays back within H.
        """

        eco = self.config.economics
        h = status.health
        washed = Health(0.0, 0.0, h.turbine_efficiency)
        power = obs.power_mw
        if power <= 1.0:
            return None
        position = float(obs.igv_position)
        try:
            fuel_now = self.monitor.steady_point(obs, power, position, h)[0]
            fuel_clean = self.monitor.steady_point(obs, power, position, washed)[0]
        except (ValueError, ZeroDivisionError):
            return None
        lhv = self.monitor.twin.maps(obs.ambient_temperature_c).clean.fuel_lhv_kj_kg
        usd_per_kg = lhv / 1.0e6 * eco.fuel_price_usd_per_gj
        loss = max(0.0, fuel_now - fuel_clean) * 3600.0 * usd_per_kg  # $/h
        growth = 0.0
        rate = None
        try:
            r = self.monitor.forecaster.rate_per_h if self.monitor.forecaster.used >= 3 else None
        except Exception:  # noqa: BLE001
            r = None
        if r is not None:
            rate = (float(r.compressor_flow), float(r.compressor_efficiency))
            ahead = Health(
                min(0.0, h.compressor_flow + min(0.0, rate[0])),
                min(0.0, h.compressor_efficiency + min(0.0, rate[1])),
                h.turbine_efficiency,
            )
            try:
                fuel_ahead = self.monitor.steady_point(obs, power, position, ahead)[0]
                growth = max(0.0, (fuel_ahead - fuel_now) * 3600.0 * usd_per_kg)
            except (ValueError, ZeroDivisionError):
                growth = 0.0
        w = eco.effective_wash_cost_usd
        cycle_cost = math.sqrt(2.0 * w * growth)
        threshold = max(cycle_cost, w / eco.effective_horizon_h)
        interval_h = math.sqrt(2.0 * w / growth) if growth > 0 else None
        return {
            "t_s": obs.t_s,
            "loss_usd_per_h": round(loss, 3),
            "loss_growth_usd_per_h2": round(growth, 4),
            "threshold_usd_per_h": round(threshold, 3),
            "optimal_interval_h": None if interval_h is None else round(interval_h, 3),
            "fouling_flow_delta": round(h.compressor_flow, 5),
            "fouling_rate_per_h": None if rate is None else [round(x, 5) for x in rate],
            "effective_wash_cost_usd": round(w, 2),
            "wash_now": loss >= threshold
            and h.compressor_flow <= -self.config.min_fouling_for_wash,
        }

    def _review_wash(self, t: float, obs, snap: dict[str, Any], status: TwinStatus) -> None:
        cfg = self.config
        if not status.loaded or status.estimator_updates == 0:
            return
        last = self._last_wash_review_s
        if last is not None and t - last < cfg.wash_review_interval_s:
            return
        self._last_wash_review_s = t
        econ = self.wash_economics(obs, status)
        self.last_wash_evaluation = econ
        if econ is None or not econ["wash_now"]:
            return
        if any(d.problem == "compressor_wash" and d.open for d in self.decisions):
            return
        if not all(c.passed for c in self.guard.trust_checks(status, need_exhaust=False)):
            # The economics rest on the health estimate; with an untrusted twin there is
            # nothing sound to recommend yet.
            return
        verdict = self.guard.verify_wash(status)
        summary = (
            f"Offline compressor wash now: fouling costs {econ['loss_usd_per_h']:.2f} $/h, above "
            f"the {econ['threshold_usd_per_h']:.2f} $/h an optimal wash cycle costs "
            "(time-compressed prices)."
        )
        actions = [
            {"command": "stop", "params": {}},
            {"command": "wash_compressor", "params": {}},
            {"command": "start", "params": {}},
            {"command": "set_load", "params": {"mw": self.demand_mw, "ramp_mw_per_min": 10.0}},
        ]
        self._decide(t, "compressor_wash", summary, actions, econ, verdict)

    def _advance_procedure(self, snap: dict[str, Any]) -> None:
        state = snap["state"]
        nxt = self._procedure[0]
        try:
            if nxt == "stop":
                self.session.apply("set_igv", {"mode": "auto", "position": None})
                self.session.apply("stop")
                self._procedure.pop(0)
            elif nxt == "wash_compressor" and state == "standstill":
                self.session.apply("wash_compressor")
                self.monitor.note_wash()
                self._last_wash_s = float(snap["t_s"])
                self._procedure.pop(0)
            elif nxt == "start" and state == "standstill":
                self.session.apply("start")
                self._procedure.pop(0)
            elif (
                nxt == "set_load"
                and state in ("full_speed_no_load", "loaded")
                and snap["breaker_closed"]
            ):
                mw = self.demand_mw if self.demand_mw is not None else 35.0
                self.session.apply("set_load", {"mw": mw, "ramp_mw_per_min": 10.0})
                self._procedure.pop(0)
        except CommandError:
            return
        if not self._procedure:
            self._procedure_decision = None
            self._last_review_s = None  # re-optimise once loaded again

    # ------------------------------------------------------------------ bookkeeping
    def _now(self) -> float:
        return float(self.session.step_count * self.session.dt)

    def _decide(
        self,
        t: float,
        problem: str,
        summary: str,
        actions: list[dict[str, Any]],
        objective: dict[str, Any],
        verdict: GuardVerdict,
    ) -> Decision:
        if self.mode == Mode.AUTONOMOUS and verdict.approved:
            status, reason = "applied", "guard approved; applied autonomously"
        elif self.mode == Mode.AUTONOMOUS:
            status, reason = "escalated", f"escalated to the operator: {verdict.reason()}"
        elif verdict.approved:
            status, reason = "pending", "guard approved; waiting for the operator (advisory)"
        else:
            status, reason = "escalated", f"guard rejected: {verdict.reason()}"
        d = Decision(
            id=len(self.decisions) + 1,
            t_s=t,
            problem=problem,
            mode=self.mode.value,
            summary=summary,
            actions=actions,
            objective=objective,
            verdict=verdict.to_dict(),
            status=status,
            reason=reason,
        )
        self.decisions.append(d)
        if status == "applied":
            self._execute(d)
            d.resolved_t_s = t
            d.resolved_by = "layer"
        return d

    def _execute(self, d: Decision) -> None:
        t = self._now()
        if d.problem == "compressor_wash":
            self._procedure = [a["command"] for a in d.actions]
            self._procedure_decision = d.id
        elif d.problem == "exhaust_feedback":
            value = self.status.model_exhaust_k if self.status else None
            params = dict(d.actions[0]["params"])
            if value is not None:
                params["value_k"] = round(value, 2)
            self.session.apply("set_exhaust_feedback", params)
            self.substitute_active = True
            self._last_substitute_s = t
        else:
            for action in d.actions:
                self.session.apply(action["command"], dict(action["params"]))
        self._last_action_s[d.problem] = t

    @staticmethod
    def _resolve(d: Decision, status: str, t: float, by: str, reason: str) -> None:
        d.status = status
        d.resolved_t_s = t
        d.resolved_by = by
        d.reason = reason

    def summary(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "demand_mw": self.demand_mw,
            "band_mw": None if self.band is None else list(self.band),
            "substitute_active": self.substitute_active,
            "procedure": list(self._procedure),
            "status": None if self.status is None else self.status.to_dict(),
            "open_decisions": [d.to_dict() for d in self.open_decisions()],
            "last_load_evaluation": self.last_load_evaluation,
            "last_wash_evaluation": self.last_wash_evaluation,
            "counters": dict(self.counters),
        }


__all__ = ["AUTO", "Decision", "Economics", "Mode", "Supervisor", "SupervisorConfig"]
