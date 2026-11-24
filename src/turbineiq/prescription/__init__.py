"""Prescriptive and autonomous layer (roadmap WP5, digital-twin levels 4 and 5).

The layer watches the simulated plant only through its instruments and the commands it
knows about, keeps its own twin (a deliberately mismatched copy of the calibrated engine with
an online health estimate), and solves three named decision problems:

* ``load_setpoint``: the load setpoint and IGV position, inside the dispatcher's demand band,
  that give the lowest heat rate without running onto the exhaust temperature limit;
* ``compressor_wash``: when an offline compressor wash pays for itself, from the estimated
  fouling, its growth, the fuel price and the cost of the outage;
* ``exhaust_feedback``: switching the temperature control to a model-based exhaust estimate
  when the exhaust thermocouple disagrees with the twin.

Every candidate it proposes is run forward on the twin and checked by a deterministic guard
(:mod:`.guard`) against hard limits and rate limits; a failed check or a twin that no longer
matches the plant means the decision goes to the operator. In manual mode the layer only
watches, in advisory mode the operator applies recommendations, and in autonomous mode
guard-approved actions are applied without the operator. Every decision is logged with its
reason. No language model takes part in any of this.
"""

from .guard import Check, GuardLimits, GuardVerdict, SafetyGuard
from .monitor import TwinMonitor, TwinStatus
from .supervisor import Decision, Economics, Mode, Supervisor, SupervisorConfig
from .twin import ForwardResult, TwinPlant, forward_run, predictive_twin

__all__ = [
    "Check",
    "Decision",
    "Economics",
    "ForwardResult",
    "GuardLimits",
    "GuardVerdict",
    "Mode",
    "SafetyGuard",
    "Supervisor",
    "SupervisorConfig",
    "TwinMonitor",
    "TwinPlant",
    "TwinStatus",
    "forward_run",
    "predictive_twin",
]
