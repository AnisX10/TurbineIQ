from fastapi.testclient import TestClient

from turbineiq.api.main import app

client = TestClient(app)


def test_health_and_scenario_catalog_are_local_and_synthetic() -> None:
    health = client.get("/api/health")
    scenarios = client.get("/api/scenarios")

    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "synthetic_only": True,
        "industrial_connection": False,
    }
    assert scenarios.status_code == 200
    assert {item["scenario_id"] for item in scenarios.json()} == {
        "baseline",
        "warm_ambient",
        "compressor_fouling",
        "sensor_fault",
    }


def test_twin_run_api_returns_selected_component_state_and_timeline() -> None:
    response = client.get(
        "/api/twin/run",
        params={"scenario_id": "compressor_fouling", "seed": 42, "sample_index": 95},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["synthetic_only"] is True
    assert payload["run"]["seed"] == 42
    assert len(payload["timeline"]) == 96
    assert payload["snapshot"]["scenario_perturbation_label"] == (
        "synthetic_compressor_efficiency_drift"
    )
    assert payload["snapshot"]["power_residual_kw"] < 0
    assert any(
        component["component_id"] == "compressor"
        for component in payload["snapshot"]["components"]
    )


def test_twin_run_api_rejects_unknown_scenarios_and_out_of_range_samples() -> None:
    unknown = client.get("/api/twin/run", params={"scenario_id": "field_data"})
    invalid_index = client.get("/api/twin/run", params={"samples": 8, "sample_index": 8})

    assert unknown.status_code == 404
    assert invalid_index.status_code == 422


def test_evidence_search_returns_local_citations() -> None:
    response = client.get("/api/evidence/search", params={"q": "Brayton"})

    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "local lexical retrieval"
    assert result["evidence"]
    assert result["evidence"][0]["citation"].startswith("[")


def test_assistant_rejects_cloud_document_context_without_cloud_opt_in() -> None:
    response = client.post(
        "/api/assistant/ask",
        json={
            "question": "Summarize the notes",
            "enable_cloud": False,
            "allow_cloud_document_context": True,
        },
    )

    assert response.status_code == 422


def test_assistant_explains_server_recomputed_selected_twin_sample() -> None:
    response = client.post(
        "/api/assistant/ask",
        json={
            "question": "Explain the compressor-efficiency drift result.",
            "selected_twin": {
                "scenario_id": "compressor_fouling",
                "seed": 42,
                "sample_index": 72,
                "selected_component_id": "compressor",
            },
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["mode"] == "local"
    assert "compressor-efficiency drift" in result["answer"]
    assert "81.2%" in result["answer"]
    assert "85.0% reference" in result["answer"]
    assert "not a fault diagnosis" in result["answer"]
    assert result["tool_calls"][0]["name"] == "inspect_synthetic_twin_snapshot"
    assert result["tool_calls"][0]["result"]["snapshot"]["seed"] == 42


def test_assistant_rejects_invalid_synthetic_twin_selection() -> None:
    response = client.post(
        "/api/assistant/ask",
        json={
            "question": "Explain this sample.",
            "selected_twin": {
                "scenario_id": "field_data",
                "seed": 42,
                "sample_index": 12,
                "selected_component_id": "compressor",
            },
        },
    )

    assert response.status_code == 422


def test_assistant_stream_emits_tool_progress_tokens_and_final_response() -> None:
    response = client.post(
        "/api/assistant/stream",
        json={
            "question": "Explain this synthetic compressor sample.",
            "selected_twin": {
                "scenario_id": "compressor_fouling",
                "seed": 42,
                "sample_index": 72,
                "selected_component_id": "compressor",
            },
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: status" in response.text
    assert "event: tool_start" in response.text
    assert '"name": "inspect_synthetic_twin_snapshot"' in response.text
    assert "event: tool_result" in response.text
    assert "event: token" in response.text
    assert "event: done" in response.text
    assert "81.2%" in response.text
