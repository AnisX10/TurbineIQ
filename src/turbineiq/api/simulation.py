"""HTTP API for simulated operating sessions (commands, state, event log, replay).

Everything here drives a simulated plant held in memory. There is no connection to any
real machine or control system, and no persistence beyond the running process.

A session may carry a WP5 :class:`~turbineiq.prescription.Supervisor` (create it with
``supervisor_mode`` or ``POST /sessions/{id}/supervisor``). The supervisor is ticked once
per simulated second whenever the session advances, through the advance endpoint and the
stream alike, so its view does not depend on how the client chops up time.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from turbineiq.prescription import Mode, Supervisor, SupervisorConfig
from turbineiq.simulation import (
    COMMANDS,
    MODEL_NOTE,
    CommandError,
    InvalidCommand,
    Session,
    SessionConfig,
    replay,
)

router = APIRouter(prefix="/api/sim", tags=["simulation"])

MAX_SESSIONS = 16
MAX_ADVANCE_SECONDS = 3600.0
MAX_REPLAY_STEPS = 200_000
MAX_REPLAY_EVENTS = 2_000


SupervisorMode = Literal["manual", "advisory", "autonomous"]


class _Entry:
    def __init__(self, session: Session, supervisor: Supervisor | None = None) -> None:
        self.session = session
        self.supervisor = supervisor
        self.lock = threading.Lock()
        self.last_used = time.monotonic()

    def advance(self, seconds: float) -> None:
        """Advance the session; with a supervisor, tick it at every whole simulated second.

        The caller holds ``self.lock``.
        """

        session = self.session
        steps = round(seconds / session.dt)
        sup = self.supervisor
        if sup is None:
            session.advance(steps)
            return
        per_second = max(1, round(1.0 / session.dt))
        while steps > 0:
            to_boundary = per_second - session.step_count % per_second
            chunk = min(steps, to_boundary)
            session.advance(chunk)
            steps -= chunk
            if session.step_count % per_second == 0:
                sup.tick()

    def supervisor_summary(self) -> dict[str, Any] | None:
        return None if self.supervisor is None else self.supervisor.summary()


_sessions: OrderedDict[str, _Entry] = OrderedDict()
_registry_lock = threading.Lock()


class CreateSessionRequest(BaseModel):
    seed: int = Field(default=0, ge=0, le=2_147_483_647)
    ambient_temperature_c: float = Field(default=15.0, ge=-40.0, le=55.0)
    grid: str = Field(default="infinite_bus", pattern="^(infinite_bus|island)$")
    grid_frequency_hz: float = Field(default=50.0, ge=47.5, le=52.5)
    island_load_mw: float = Field(default=20.0, ge=0.0, le=60.0)
    measurement_noise: bool = True
    record_interval_s: float = Field(default=1.0, ge=0.1, le=60.0)
    #: Attach a WP5 supervisor in this mode; omitted or null means no supervisor.
    supervisor_mode: SupervisorMode | None = None


class SupervisorRequest(BaseModel):
    mode: SupervisorMode = "advisory"


class ModeRequest(BaseModel):
    mode: SupervisorMode


class DemandRequest(BaseModel):
    mw: float = Field(ge=0.0, le=60.0)
    #: Also move the plant's load setpoint to the demand (as the operator does when the
    #: dispatcher sends a new target); the supervisor then optimises inside the band.
    apply_setpoint: bool = False
    ramp_mw_per_min: float = Field(default=10.0, gt=0.0, le=120.0)


class CommandRequest(BaseModel):
    command: str = Field(max_length=40)
    params: dict[str, Any] = Field(default_factory=dict)


class AdvanceRequest(BaseModel):
    seconds: float = Field(gt=0.0, le=MAX_ADVANCE_SECONDS)


class ReplayRequest(BaseModel):
    log: dict[str, Any]


def _get(session_id: str) -> _Entry:
    with _registry_lock:
        entry = _sessions.get(session_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Unknown or expired session_id")
        entry.last_used = time.monotonic()
        _sessions.move_to_end(session_id)
        return entry


def _command_error(exc: CommandError) -> HTTPException:
    status = 422 if isinstance(exc, InvalidCommand) else 409
    return HTTPException(status_code=status, detail=str(exc))


@router.get("/commands")
def list_commands() -> dict[str, Any]:
    return {
        "commands": {
            name: {param: _type_name(types) for param, types in spec.items()}
            for name, spec in COMMANDS.items()
        },
        "model_note": MODEL_NOTE,
        "synthetic_simulation": True,
    }


def _type_name(types: type | tuple[type, ...]) -> str:
    items = types if isinstance(types, tuple) else (types,)
    names = sorted({"number" if t in (int, float) else t.__name__ for t in items})
    return " | ".join(n if n != "NoneType" else "null" for n in names)


@router.post("/sessions", status_code=201)
def create_session(request: CreateSessionRequest) -> dict[str, Any]:
    body = request.model_dump()
    mode = body.pop("supervisor_mode")
    try:
        config = SessionConfig(**body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session = Session(config)
    entry = _Entry(session)
    if mode is not None:
        entry.supervisor = _new_supervisor(session, mode)
    session_id = secrets.token_hex(8)
    with _registry_lock:
        while len(_sessions) >= MAX_SESSIONS:
            _sessions.popitem(last=False)  # evict the least recently used session
        _sessions[session_id] = entry
    response: dict[str, Any] = {
        "session_id": session_id,
        "config": config.to_dict(),
        "state": session.snapshot(),
        "model_note": MODEL_NOTE,
    }
    if entry.supervisor is not None:
        response["supervisor"] = entry.supervisor_summary()
    return response


def _new_supervisor(session: Session, mode: str) -> Supervisor:
    supervisor = Supervisor(session, SupervisorConfig(mode=Mode(mode)))
    supervisor.tick()  # a first look, so the summary has a status from the start
    return supervisor


@router.get("/sessions/{session_id}")
def get_state(session_id: str) -> dict[str, Any]:
    entry = _get(session_id)
    with entry.lock:
        return entry.session.snapshot()


@router.post("/sessions/{session_id}/commands")
def send_command(session_id: str, request: CommandRequest) -> dict[str, Any]:
    entry = _get(session_id)
    with entry.lock:
        try:
            event = entry.session.apply(request.command, request.params)
        except CommandError as exc:
            raise _command_error(exc) from exc
        return {"event": event, "state": entry.session.snapshot()}


@router.post("/sessions/{session_id}/advance")
def advance(session_id: str, request: AdvanceRequest) -> dict[str, Any]:
    entry = _get(session_id)
    with entry.lock:
        session = entry.session
        mark = session.step_count
        try:
            entry.advance(request.seconds)
        except CommandError as exc:
            raise _command_error(exc) from exc
        samples = [s for s in session.history if s["step"] > mark][-600:]
        response: dict[str, Any] = {"state": session.snapshot(), "samples": samples}
        if entry.supervisor is not None:
            response["supervisor"] = entry.supervisor_summary()
        return response


@router.get("/sessions/{session_id}/history")
def get_history(session_id: str, last: int = Query(default=300, ge=1, le=5000)) -> dict[str, Any]:
    entry = _get(session_id)
    with entry.lock:
        return {"samples": list(entry.session.history)[-last:]}


@router.get("/sessions/{session_id}/log")
def get_log(session_id: str) -> dict[str, Any]:
    entry = _get(session_id)
    with entry.lock:
        return entry.session.log()


@router.get("/sessions/{session_id}/stream")
def stream(
    session_id: str,
    seconds: float = Query(default=60.0, gt=0.0, le=MAX_ADVANCE_SECONDS),
    speed: float = Query(default=1.0, gt=0.0, le=500.0),
    interval_s: float = Query(default=0.1, ge=0.05, le=5.0),
) -> StreamingResponse:
    """Server-sent events with one state snapshot per ``interval_s`` of simulated time.

    ``speed`` is simulated seconds per wall-clock second. Commands can be posted to the
    same session while the stream runs; they apply between steps.
    """

    entry = _get(session_id)

    def events() -> Iterator[str]:
        remaining = seconds
        while remaining > 1e-9:
            chunk = min(interval_s, remaining)
            started = time.monotonic()
            with entry.lock:
                try:
                    entry.advance(chunk)
                except CommandError as exc:
                    yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
                    return
                payload = entry.session.snapshot()
                summary = entry.supervisor_summary()
            remaining -= chunk
            yield f"event: state\ndata: {json.dumps(payload)}\n\n"
            if summary is not None:
                yield f"event: supervisor\ndata: {json.dumps(summary)}\n\n"
            pause = chunk / speed - (time.monotonic() - started)
            if pause > 0:
                time.sleep(pause)
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------- supervisor (WP5)


def _supervised(session_id: str) -> _Entry:
    entry = _get(session_id)
    if entry.supervisor is None:
        raise HTTPException(status_code=404, detail="This session has no supervisor")
    return entry


@router.post("/sessions/{session_id}/supervisor")
def attach_supervisor(session_id: str, request: SupervisorRequest) -> dict[str, Any]:
    """Attach a supervisor in ``mode``, or switch the mode of the one already attached."""

    entry = _get(session_id)
    with entry.lock:
        if entry.supervisor is None:
            entry.supervisor = _new_supervisor(entry.session, request.mode)
        else:
            entry.supervisor.set_mode(request.mode)
        return entry.supervisor.summary()


@router.get("/sessions/{session_id}/supervisor")
def supervisor_summary(session_id: str) -> dict[str, Any]:
    entry = _supervised(session_id)
    with entry.lock:
        return entry.supervisor.summary()


@router.post("/sessions/{session_id}/supervisor/mode")
def supervisor_mode(session_id: str, request: ModeRequest) -> dict[str, Any]:
    entry = _supervised(session_id)
    with entry.lock:
        entry.supervisor.set_mode(request.mode)
        return entry.supervisor.summary()


@router.post("/sessions/{session_id}/supervisor/demand")
def supervisor_demand(session_id: str, request: DemandRequest) -> dict[str, Any]:
    entry = _supervised(session_id)
    with entry.lock:
        if request.apply_setpoint:
            try:
                entry.session.apply(
                    "set_load", {"mw": request.mw, "ramp_mw_per_min": request.ramp_mw_per_min}
                )
            except CommandError as exc:
                raise _command_error(exc) from exc
        try:
            entry.supervisor.set_demand(request.mw)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"supervisor": entry.supervisor.summary(), "state": entry.session.snapshot()}


def _resolve_decision(session_id: str, decision_id: int, accept: bool) -> dict[str, Any]:
    entry = _supervised(session_id)
    with entry.lock:
        sup = entry.supervisor
        try:
            decision = sup.accept(decision_id) if accept else sup.reject(decision_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown decision id") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except CommandError as exc:
            raise _command_error(exc) from exc
        return {
            "decision": decision.to_dict(),
            "supervisor": sup.summary(),
            "state": entry.session.snapshot(),
        }


@router.post("/sessions/{session_id}/supervisor/decisions/{decision_id}/accept")
def accept_decision(session_id: str, decision_id: int) -> dict[str, Any]:
    return _resolve_decision(session_id, decision_id, accept=True)


@router.post("/sessions/{session_id}/supervisor/decisions/{decision_id}/reject")
def reject_decision(session_id: str, decision_id: int) -> dict[str, Any]:
    return _resolve_decision(session_id, decision_id, accept=False)


@router.post("/sessions/{session_id}/supervisor/trust-thermocouple")
def trust_thermocouple(session_id: str) -> dict[str, Any]:
    entry = _supervised(session_id)
    with entry.lock:
        try:
            entry.supervisor.trust_thermocouple()
        except CommandError as exc:
            raise _command_error(exc) from exc
        return {"supervisor": entry.supervisor.summary(), "state": entry.session.snapshot()}


@router.get("/sessions/{session_id}/supervisor/decisions")
def decision_log(
    session_id: str, last: int = Query(default=200, ge=1, le=2000)
) -> dict[str, Any]:
    entry = _supervised(session_id)
    with entry.lock:
        decisions = entry.supervisor.decisions[-last:]
        return {
            "decisions": [d.to_dict() for d in decisions],
            "total": len(entry.supervisor.decisions),
        }


@router.post("/replay")
def replay_log(request: ReplayRequest) -> dict[str, Any]:
    log = request.log
    events = log.get("events", [])
    if not isinstance(events, list) or len(events) > MAX_REPLAY_EVENTS:
        raise HTTPException(status_code=422, detail="log.events must be a short list")
    steps = log.get("steps")
    if not isinstance(steps, int) or not 0 <= steps <= MAX_REPLAY_STEPS:
        raise HTTPException(
            status_code=422, detail=f"log.steps must be an integer up to {MAX_REPLAY_STEPS}"
        )
    try:
        session = replay(log)
    except (CommandError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=f"cannot replay log: {exc}") from exc
    digest = session.trace_digest()
    expected = log.get("trace_digest")
    return {
        "trace_digest": digest,
        "digest_matches": None if expected is None else digest == expected,
        "state": session.snapshot(),
    }
