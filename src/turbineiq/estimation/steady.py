"""Steady-state detection: when a quasi-steady twin may be compared with the plant."""

from __future__ import annotations

import statistics
from collections import deque

from .data import Observation


class SteadyStateGate:
    """True once the unit has been loaded with unchanged inputs and flat readings for a while.

    Conditions over the last ``window_s`` seconds: unit loaded with the breaker closed, the
    load setpoint, IGV position and ambient unchanged, and the standard deviation of power
    and exhaust temperature below the given limits (a little above measurement noise). The
    window restarts whenever an input changes.
    """

    def __init__(
        self,
        window_s: float = 120.0,
        power_std_mw: float = 0.25,
        exhaust_std_k: float = 1.5,
    ) -> None:
        self.window_s = window_s
        self.power_std_mw = power_std_mw
        self.exhaust_std_k = exhaust_std_k
        self._window: deque[Observation] = deque()

    def reset(self) -> None:
        self._window.clear()

    def update(self, obs: Observation) -> bool:
        if not (obs.state == "loaded" and obs.breaker_closed):
            self._window.clear()
            return False
        if self._window:
            last = self._window[-1]
            if (
                obs.load_setpoint_mw != last.load_setpoint_mw
                or obs.igv_position != last.igv_position
                or obs.ambient_temperature_c != last.ambient_temperature_c
            ):
                self._window.clear()
        self._window.append(obs)
        while self._window and obs.t_s - self._window[0].t_s > self.window_s:
            self._window.popleft()
        if obs.t_s - self._window[0].t_s < self.window_s - 1e-9:
            return False
        powers = [o.power_mw for o in self._window]
        exhausts = [o.exhaust_k for o in self._window]
        return (
            statistics.pstdev(powers) <= self.power_std_mw
            and statistics.pstdev(exhausts) <= self.exhaust_std_k
        )
