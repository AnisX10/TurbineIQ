"""HTTP API for simulated operating sessions (commands, state, event log, replay).

Everything here drives a simulated plant held in memory. There is no connection to any
real machine or control system, and no persistence beyond the running process.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

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


class _Entry:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.lock = threading.Lock()
        self.last_used = time.monotonic()


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
    try:
        config = SessionConfig(**request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session = Session(config)
    session_id = secrets.token_hex(8)
    with _registry_lock:
        while len(_sessions) >= MAX_SESSIONS:
            _sessions.popitem(last=False)  # evict the least recently used session
        _sessions[session_id] = _Entry(session)
    return {
        "session_id": session_id,
        "config": config.to_dict(),
        "state": session.snapshot(),
        "model_note": MODEL_NOTE,
    }


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
            session.advance_seconds(request.seconds)
        except CommandError as exc:
            raise _command_error(exc) from exc
        samples = [s for s in session.history if s["step"] > mark][-600:]
        return {"state": session.snapshot(), "samples": samples}


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
                    entry.session.advance_seconds(chunk)
                except CommandError as exc:
                    yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
                    return
                payload = entry.session.snapshot()
            remaining -= chunk
            yield f"event: state\ndata: {json.dumps(payload)}\n\n"
            pause = chunk / speed - (time.monotonic() - started)
            if pause > 0:
                time.sleep(pause)
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
