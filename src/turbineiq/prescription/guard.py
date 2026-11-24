"""The deterministic safety guard: hard limits, rate limits and twin trust.

The guard never optimises anything. It is given a candidate action, the monitor's status
and a forward run of the twin with that action applied, and returns a verdict: a list of
named checks, each with the value found, the limit and whether it passed. Any failed check
means the action is not applied automatically and goes to the operator. The limits are
labelled assumptions for this simulated unit, not OEM values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .monitor import TwinStatus
from .twin import ForwardResult


@dataclass(frozen=True)
class GuardLimits:
    #: Largest load ramp the layer may command on its own (MW/min).
    max_ramp_mw_per_min: float = 10.0
    #: Largest load setpoint change in one decision (MW).
    max_setpoint_step_mw: float = 6.0
    #: Minimum time between two automatic actions of the same decision problem (s).
    min_action_interval_s: float = 120.0
    #: Peak twin exhaust temperature must stay this far below the trip threshold (K).
    trip_margin_k: float = 25.0
    #: Peak twin exhaust during the forward run may exceed the temperature control limit by
    #: at most this (K). The evaluation counts more than 5 K above the limit as a hard-limit
    #: violation; without this check an IGV closure applied during a fast dispatcher ramp
    #: passed the trip-margin check and overshot the control limit by 8.7 K for 4 s
    #: (clean_load_cycling, tuning seeds 1000-1002).
    transient_over_limit_k: float = 3.0
    #: Settled twin exhaust must stay this far below the temperature control limit (K),
    #: plus the twin's own exhaust uncertainty (the mean exhaust residual magnitude).
    control_margin_k: float = 5.0
    #: Speed band during the forward run (per unit).
    speed_band_pu: tuple[float, float] = (0.98, 1.02)
    #: Settled twin power must be within this of the target and inside the demand band (MW).
    power_tolerance_mw: float = 0.6
    #: Twin trust: largest standardised mean residual of the non-exhaust channels.
    max_mismatch_index: float = 3.0
    #: Twin trust: health estimate standard deviations (flow, compressor eff, turbine eff).
    max_health_std: tuple[float, float, float] = (0.006, 0.003, 0.003)
    #: Whether an offline wash (a shutdown) may run without the operator. Off by default:
    #: a shutdown changes availability and is outside the stated autonomy envelope.
    autonomous_wash: bool = False


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    value: float | str | None
    limit: float | str | None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class GuardVerdict:
    approved: bool
    checks: tuple[Check, ...] = field(default_factory=tuple)
    forward: ForwardResult | None = None

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def reason(self) -> str:
        if self.approved:
            return "all guard checks passed"
        return "; ".join(f"{c.name}: {c.detail or 'failed'}" for c in self.failed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "reason": self.reason(),
            "checks": [c.to_dict() for c in self.checks],
            "forward": None if self.forward is None else self.forward.to_dict(),
        }


class SafetyGuard:
    def __init__(self, limits: GuardLimits | None = None) -> None:
        self.limits = limits or GuardLimits()

    # ------------------------------------------------------------------ twin trust
    def trust_checks(self, status: TwinStatus, *, need_exhaust: bool) -> list[Check]:
        lim = self.limits
        checks = [
            Check(
                "unit_loaded",
                status.loaded,
                "loaded" if status.loaded else "not loaded",
                "loaded",
                "" if status.loaded else "the unit is not loaded on the grid",
            ),
            Check(
                "estimator_ready",
                status.estimator_updates > 0,
                status.estimator_updates,
                ">= 1 update",
                "" if status.estimator_updates else "no steady data for the health estimate yet",
            ),
        ]
        std = tuple(status.health_std)
        ok = all(s <= m for s, m in zip(std, lim.max_health_std, strict=True))
        checks.append(
            Check(
                "health_converged",
                ok,
                ", ".join(f"{s:.4f}" for s in std),
                ", ".join(f"{m:.4f}" for m in lim.max_health_std),
                "" if ok else "the health estimate is still too uncertain",
            )
        )
        mm = status.mismatch_index
        ok = mm is not None and mm <= lim.max_mismatch_index
        checks.append(
            Check(
                "model_mismatch",
                ok,
                None if mm is None else round(mm, 2),
                lim.max_mismatch_index,
                ""
                if ok
                else (
                    "no steady residuals yet"
                    if mm is None
                    else "the twin no longer matches the plant's instruments"
                ),
            )
        )
        if need_exhaust:
            ok = not status.exhaust_suspect
            checks.append(
                Check(
                    "exhaust_reading_trusted",
                    ok,
                    status.exhaust_reason or "trusted",
                    "trusted",
                    "" if ok else "the exhaust thermocouple is distrusted",
                )
            )
        return checks

    # ------------------------------------------------------------------ load and IGV
    def verify_load(
        self,
        status: TwinStatus,
        *,
        current_setpoint_mw: float,
        target_mw: float,
        band: tuple[float, float],
        ramp_mw_per_min: float,
        forward: ForwardResult,
        exhaust_trusted_or_substituted: bool,
        since_last_action_s: float | None,
    ) -> GuardVerdict:
        lim = self.limits
        checks = self.trust_checks(status, need_exhaust=False)
        checks.append(
            Check(
                "exhaust_feedback_valid",
                exhaust_trusted_or_substituted,
                "ok" if exhaust_trusted_or_substituted else "distrusted thermocouple in control",
                "trusted or substituted",
                ""
                if exhaust_trusted_or_substituted
                else "the temperature control acts on a distrusted thermocouple",
            )
        )
        step = abs(target_mw - current_setpoint_mw)
        checks.append(
            Check(
                "setpoint_step",
                step <= lim.max_setpoint_step_mw + 1e-9,
                round(step, 3),
                lim.max_setpoint_step_mw,
                "" if step <= lim.max_setpoint_step_mw + 1e-9 else "setpoint change too large",
            )
        )
        checks.append(
            Check(
                "ramp_rate",
                ramp_mw_per_min <= lim.max_ramp_mw_per_min + 1e-9,
                ramp_mw_per_min,
                lim.max_ramp_mw_per_min,
                "" if ramp_mw_per_min <= lim.max_ramp_mw_per_min + 1e-9 else "ramp too fast",
            )
        )
        if since_last_action_s is not None:
            ok = since_last_action_s >= lim.min_action_interval_s
            checks.append(
                Check(
                    "action_interval",
                    ok,
                    round(since_last_action_s, 1),
                    lim.min_action_interval_s,
                    "" if ok else "too soon after the last automatic action",
                )
            )
        checks.extend(self._forward_checks(status, forward, target_mw, band))
        return GuardVerdict(all(c.passed for c in checks), tuple(checks), forward)

    def _forward_checks(
        self,
        status: TwinStatus,
        fw: ForwardResult,
        target_mw: float,
        band: tuple[float, float],
    ) -> list[Check]:
        lim = self.limits
        checks = [
            Check(
                "no_trip",
                not fw.tripped,
                fw.trip_cause or "none",
                "none",
                "" if not fw.tripped else f"the twin trips ({fw.trip_cause})",
            )
        ]
        peak_limit = fw.trip_temperature_k - lim.trip_margin_k
        checks.append(
            Check(
                "peak_exhaust",
                fw.max_exhaust_k <= peak_limit,
                round(fw.max_exhaust_k, 1),
                round(peak_limit, 1),
                "" if fw.max_exhaust_k <= peak_limit else "exhaust peak too close to the trip",
            )
        )
        transient_limit = fw.temperature_limit_k + lim.transient_over_limit_k
        ok = fw.max_exhaust_k <= transient_limit
        checks.append(
            Check(
                "transient_exhaust",
                ok,
                round(fw.max_exhaust_k, 1),
                round(transient_limit, 1),
                "" if ok else "the exhaust overshoots the temperature control limit on the way",
            )
        )
        uncertainty = abs((status.exhaust_residual_k or 0.0)) if not status.exhaust_suspect else 0.0
        settled_limit = fw.temperature_limit_k - lim.control_margin_k - uncertainty
        ok = fw.end_exhaust_k <= settled_limit
        checks.append(
            Check(
                "settled_exhaust",
                ok,
                round(fw.end_exhaust_k, 1),
                round(settled_limit, 1),
                "" if ok else "would run on (or too near) the exhaust temperature limit",
            )
        )
        lo, hi = lim.speed_band_pu
        ok = lo <= fw.min_speed_pu and fw.max_speed_pu <= hi
        checks.append(
            Check(
                "speed_band",
                ok,
                f"{fw.min_speed_pu:.4f}..{fw.max_speed_pu:.4f}",
                f"{lo}..{hi}",
                "" if ok else "speed leaves the band",
            )
        )
        tol = lim.power_tolerance_mw
        ok = (
            abs(fw.end_power_mw - target_mw) <= tol
            and band[0] - tol <= fw.end_power_mw <= band[1] + tol
        )
        checks.append(
            Check(
                "meets_demand",
                ok,
                round(fw.end_power_mw, 2),
                f"{target_mw:.2f} ± {tol} within {band[0]:.1f}..{band[1]:.1f}",
                "" if ok else "the twin does not reach the target inside the demand band",
            )
        )
        return checks

    # ------------------------------------------------------------------ exhaust substitute
    def verify_substitute(self, status: TwinStatus) -> GuardVerdict:
        """Switching the temperature control to the model exhaust estimate.

        The model value replaces a reading the monitor already distrusts, so the check is
        that the model itself can be trusted: the twin matches the other instruments, the
        health estimate has converged, and the model value lies inside the limits.
        """

        checks = self.trust_checks(status, need_exhaust=False)
        value = status.model_exhaust_k
        ok = value is not None and 250.0 <= value <= 1200.0
        checks.append(
            Check(
                "model_exhaust_available",
                ok,
                None if value is None else round(value, 1),
                "250..1200 K",
                "" if ok else "no model exhaust estimate",
            )
        )
        return GuardVerdict(all(c.passed for c in checks), tuple(checks))

    # ------------------------------------------------------------------ wash
    def verify_wash(self, status: TwinStatus) -> GuardVerdict:
        checks = self.trust_checks(status, need_exhaust=False)
        ok = self.limits.autonomous_wash
        checks.append(
            Check(
                "shutdown_allowed",
                ok,
                "allowed" if ok else "operator only",
                "allowed",
                "" if ok else "an offline wash needs a shutdown, which only the operator decides",
            )
        )
        return GuardVerdict(all(c.passed for c in checks), tuple(checks))
