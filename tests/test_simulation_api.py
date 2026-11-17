"""HTTP tests for the simulated-operation API."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from turbineiq.api import simulation as sim_api
from turbineiq.api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_registry():
    sim_api._sessions.clear()
    yield
    sim_api._sessions.clear()


def _create(**body) -> str:
    response = client.post("/api/sim/sessions", json=body)
    assert response.status_code == 201, response.text
    return response.json()["session_id"]


def _command(session_id: str, command: str, **params):
    return client.post(
        f"/api/sim/sessions/{session_id}/commands", json={"command": command, "params": params}
    )


def test_command_catalog_states_it_is_simulation_only() -> None:
    body = client.get("/api/sim/commands").json()
    assert body["synthetic_simulation"] is True
    assert {"start", "stop", "trip", "set_load", "set_igv"} <= set(body["commands"])
    assert body["commands"]["set_load"]["mw"] == "number"
    assert "Simulated plant" in body["model_note"]


def test_create_session_starts_at_standstill_with_a_snapshot() -> None:
    response = client.post("/api/sim/sessions", json={"seed": 5, "ambient_temperature_c": 20})
    body = response.json()
    assert response.status_code == 201
    assert body["config"]["seed"] == 5
    assert body["state"]["state"] == "standstill"
    assert body["state"]["synthetic_simulation"] is True
    assert "start" in body["state"]["available_commands"]


def test_full_operating_flow_over_http() -> None:
    session_id = _create(seed=1)
    started = _command(session_id, "start")
    assert started.status_code == 200
    assert started.json()["event"] == {"step": 0, "command": "start", "params": {}}

    advanced = client.post(f"/api/sim/sessions/{session_id}/advance", json={"seconds": 260})
    assert advanced.status_code == 200
    state = advanced.json()["state"]
    assert state["state"] == "loaded" and state["breaker_closed"]
    assert 0 < len(advanced.json()["samples"]) <= 600

    load = _command(session_id, "set_load", mw=30.0, ramp_mw_per_min=60.0)
    assert load.status_code == 200
    client.post(f"/api/sim/sessions/{session_id}/advance", json={"seconds": 120})
    state = client.get(f"/api/sim/sessions/{session_id}").json()
    assert state["electrical_power_mw"] == pytest.approx(30.0, rel=5e-3)
    assert state["measured"]["electrical_power_mw"] != state["electrical_power_mw"]

    tripped = _command(session_id, "trip").json()["state"]
    assert tripped["state"] == "tripped" and tripped["trip_cause"] == "manual_emergency_trip"
    assert tripped["available_commands"] == ["reset", "set_load", "set_igv", "set_ambient"]


def test_state_conflicts_and_bad_input_use_distinct_status_codes() -> None:
    session_id = _create()
    assert _command(session_id, "stop").status_code == 409  # not running
    assert _command(session_id, "set_load", mw="lots").status_code == 422
    assert _command(session_id, "self_destruct").status_code == 422
    assert _command(session_id, "set_load", mw=9999).status_code == 409
    assert client.get("/api/sim/sessions/nope").status_code == 404
    assert client.post("/api/sim/sessions", json={"grid": "mains"}).status_code == 422
    assert (
        client.post(f"/api/sim/sessions/{session_id}/advance", json={"seconds": 1e9}).status_code
        == 422
    )
    log = client.get(f"/api/sim/sessions/{session_id}/log").json()
    assert log["events"] == []  # rejected commands are not logged


def test_log_replay_endpoint_reproduces_the_trace() -> None:
    session_id = _create(seed=9)
    _command(session_id, "start")
    client.post(f"/api/sim/sessions/{session_id}/advance", json={"seconds": 255})
    _command(session_id, "set_load", mw=25.0, ramp_mw_per_min=30.0)
    client.post(f"/api/sim/sessions/{session_id}/advance", json={"seconds": 90})
    log = client.get(f"/api/sim/sessions/{session_id}/log").json()

    replayed = client.post("/api/sim/replay", json={"log": log})
    assert replayed.status_code == 200
    assert replayed.json()["digest_matches"] is True
    assert replayed.json()["trace_digest"] == log["trace_digest"]

    log["events"][1]["params"]["mw"] = 26.0
    altered = client.post("/api/sim/replay", json={"log": log}).json()
    assert altered["digest_matches"] is False


def test_replay_endpoint_bounds_the_work() -> None:
    log = {"config": {}, "events": [], "steps": 10**9}
    assert client.post("/api/sim/replay", json={"log": log}).status_code == 422
    bad = {"config": {"nonsense": 1}, "events": [], "steps": 10}
    assert client.post("/api/sim/replay", json={"log": bad}).status_code == 422


def test_stream_emits_state_events_then_done() -> None:
    session_id = _create(seed=2)
    _command(session_id, "start")
    with client.stream(
        "GET", f"/api/sim/sessions/{session_id}/stream", params={"seconds": 2, "speed": 500}
    ) as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        text = "".join(response.iter_text())
    events = [block for block in text.split("\n\n") if block.strip()]
    assert events[-1].startswith("event: done")
    states = [json.loads(b.split("data: ", 1)[1]) for b in events if b.startswith("event: state")]
    assert len(states) == 20  # 2 s at one snapshot per 0.1 s
    assert states[-1]["t_s"] == pytest.approx(2.0)
    assert states[-1]["state"] == "crank" and states[-1]["speed_pu"] > states[0]["speed_pu"]


def test_session_registry_evicts_the_least_recently_used(monkeypatch) -> None:
    monkeypatch.setattr(sim_api, "MAX_SESSIONS", 2)
    first = _create()
    second = _create()
    client.get(f"/api/sim/sessions/{first}")  # touch: second is now the oldest
    _create()
    assert client.get(f"/api/sim/sessions/{first}").status_code == 200
    assert client.get(f"/api/sim/sessions/{second}").status_code == 404


def test_history_returns_recent_samples() -> None:
    session_id = _create()
    _command(session_id, "start")
    client.post(f"/api/sim/sessions/{session_id}/advance", json={"seconds": 30})
    samples = client.get(f"/api/sim/sessions/{session_id}/history", params={"last": 5}).json()
    assert len(samples["samples"]) == 5
    assert samples["samples"][-1]["t_s"] == pytest.approx(30.0)


def test_openapi_description_does_not_claim_there_are_no_control_endpoints() -> None:
    description = client.get("/openapi.json").json()["info"]["description"]
    assert "simulated plant only" in description
    assert "industrial connectivity" in description
