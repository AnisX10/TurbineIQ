"""HTTP tests for the WP5 supervisor attached to simulated sessions."""

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


def _url(session_id: str, path: str = "") -> str:
    return f"/api/sim/sessions/{session_id}{path}"


def _create(**body) -> tuple[str, dict]:
    response = client.post("/api/sim/sessions", json=body)
    assert response.status_code == 201, response.text
    return response.json()["session_id"], response.json()


def _command(session_id: str, command: str, **params):
    return client.post(_url(session_id, "/commands"), json={"command": command, "params": params})


def _advance(session_id: str, seconds: float) -> dict:
    response = client.post(_url(session_id, "/advance"), json={"seconds": seconds})
    assert response.status_code == 200, response.text
    return response.json()


def test_sessions_without_a_supervisor_are_unchanged() -> None:
    session_id, body = _create(seed=1)
    assert "supervisor" not in body
    assert "supervisor" not in _advance(session_id, 2)
    assert client.get(_url(session_id, "/supervisor")).status_code == 404
    switched = client.post(_url(session_id, "/supervisor/mode"), json={"mode": "manual"})
    assert switched.status_code == 404


def test_create_with_a_mode_returns_a_summary() -> None:
    session_id, body = _create(seed=1, supervisor_mode="autonomous")
    summary = body["supervisor"]
    assert summary["mode"] == "autonomous"
    assert summary["status"]["t_s"] == 0.0
    assert summary["open_decisions"] == []
    assert client.get(_url(session_id, "/supervisor")).json()["mode"] == "autonomous"
    assert client.post("/api/sim/sessions", json={"supervisor_mode": "reckless"}).status_code == 422


def test_supervisor_ticks_once_per_simulated_second_however_time_is_chopped() -> None:
    session_id, _ = _create(seed=1, supervisor_mode="advisory")
    entry = sim_api._sessions[session_id]
    ticks = []
    original = entry.supervisor.tick
    entry.supervisor.tick = lambda: ticks.append(entry.session.step_count) or original()
    _advance(session_id, 0.5)
    assert ticks == []
    body = _advance(session_id, 0.7)  # crosses t = 1 s
    assert len(ticks) == 1
    _advance(session_id, 3.0)
    assert len(ticks) == 4
    per_second = round(1.0 / entry.session.dt)
    assert all(step % per_second == 0 for step in ticks)
    assert body["supervisor"]["status"]["t_s"] == pytest.approx(1.0)


def test_stream_ticks_the_supervisor_and_emits_its_summary() -> None:
    session_id, _ = _create(seed=2, supervisor_mode="manual")
    _command(session_id, "start")
    with client.stream(
        "GET", _url(session_id, "/stream"), params={"seconds": 2, "speed": 500, "interval_s": 0.5}
    ) as response:
        text = "".join(response.iter_text())
    blocks = [b for b in text.split("\n\n") if b.strip()]
    summaries = [
        json.loads(b.split("data: ", 1)[1]) for b in blocks if b.startswith("event: supervisor")
    ]
    assert len(summaries) == 4
    assert summaries[-1]["status"]["t_s"] == pytest.approx(2.0)
    assert summaries[0]["status"]["t_s"] == pytest.approx(0.0)  # no whole second crossed yet


def test_attach_mode_and_demand_endpoints() -> None:
    session_id, _ = _create(seed=3)
    attached = client.post(_url(session_id, "/supervisor"), json={"mode": "manual"})
    assert attached.status_code == 200 and attached.json()["mode"] == "manual"
    switched = client.post(_url(session_id, "/supervisor/mode"), json={"mode": "advisory"})
    assert switched.json()["mode"] == "advisory"
    again = client.post(_url(session_id, "/supervisor"), json={"mode": "autonomous"})
    assert again.json()["mode"] == "autonomous"

    demand = client.post(_url(session_id, "/supervisor/demand"), json={"mw": 30})
    assert demand.status_code == 200
    assert demand.json()["supervisor"]["demand_mw"] == 30
    assert demand.json()["supervisor"]["band_mw"] == [28.0, 32.0]
    assert demand.json()["state"]["load_setpoint_mw"] != 30  # setpoint left alone

    moved = client.post(
        _url(session_id, "/supervisor/demand"), json={"mw": 25, "apply_setpoint": True}
    )
    assert moved.status_code == 200
    assert moved.json()["state"]["load_setpoint_mw"] == 25
    assert client.post(_url(session_id, "/supervisor/demand"), json={"mw": -1}).status_code == 422


def test_decision_endpoints_reject_unknown_ids_and_log_is_listed() -> None:
    session_id, _ = _create(seed=4, supervisor_mode="advisory")
    assert client.post(_url(session_id, "/supervisor/decisions/99/accept")).status_code == 404
    assert client.post(_url(session_id, "/supervisor/decisions/99/reject")).status_code == 404
    log = client.get(_url(session_id, "/supervisor/decisions")).json()
    assert log == {"decisions": [], "total": 0}
    trusted = client.post(_url(session_id, "/supervisor/trust-thermocouple"))
    assert trusted.status_code == 200
    assert trusted.json()["supervisor"]["substitute_active"] is False


def test_advisory_recommendation_can_be_rejected_then_not_reopened() -> None:
    session_id, _ = _create(seed=1, supervisor_mode="advisory")
    _command(session_id, "start")
    _advance(session_id, 260)
    client.post(_url(session_id, "/supervisor/demand"), json={"mw": 35, "apply_setpoint": True})
    body = _advance(session_id, 420)
    assert body["state"]["state"] == "loaded"
    status = body["supervisor"]["status"]
    assert status["loaded"] and status["estimator_updates"] > 0
    assert set(status["health"]) == {
        "compressor_flow",
        "compressor_efficiency",
        "turbine_efficiency",
    }
    log = client.get(_url(session_id, "/supervisor/decisions")).json()
    assert log["total"] >= 1
    open_ids = [d["id"] for d in body["supervisor"]["open_decisions"]]
    assert open_ids, "the layer should have a recommendation waiting in advisory mode"
    rejected = client.post(_url(session_id, f"/supervisor/decisions/{open_ids[0]}/reject"))
    assert rejected.status_code == 200
    assert rejected.json()["decision"]["status"] == "rejected"
    assert rejected.json()["decision"]["resolved_by"] == "operator"
    again = client.post(_url(session_id, f"/supervisor/decisions/{open_ids[0]}/accept"))
    assert again.status_code == 409
