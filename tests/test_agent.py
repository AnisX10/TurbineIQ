import json
from types import SimpleNamespace

import pytest

from turbineiq.agent import CloudLLMSettings, TurbineAssistant
from turbineiq.rag import load_document_bytes


class FakeResponses:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.outputs.pop(0)


class FakeClient:
    def __init__(self, outputs):
        self.responses = FakeResponses(outputs)


def text_response(answer: str):
    return SimpleNamespace(output=[], output_text=answer)


def tool_call(name: str, arguments: dict, call_id: str = "call-1"):
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments=json.dumps(arguments),
        call_id=call_id,
    )


def test_local_assistant_runs_calculation_tool() -> None:
    assistant = TurbineAssistant()

    response = assistant.run("Calculate the turbine electrical power.")

    assert response.mode == "local"
    assert response.tool_calls[0].name == "calculate_cycle"
    assert "illustrative cycle case" in response.answer
    assert response.tool_calls[0].result["result"]["electrical_power_kw"] > 0


def test_local_assistant_runs_synthetic_scenario_tool() -> None:
    assistant = TurbineAssistant()

    response = assistant.run("Review the sensor fault scenario for anomalies.")

    assert response.tool_calls[0].name == "summarize_synthetic_scenario"
    assert response.tool_calls[0].result["synthetic_only"] is True
    assert response.tool_calls[0].result["labelled_sensor_fault_count"] == 1


def test_local_assistant_retrieves_and_cites_demo_document() -> None:
    documents = load_document_bytes(
        "demo.md", b"## Compressor\nCompressor work is cp multiplied by temperature rise."
    )
    assistant = TurbineAssistant(documents)

    response = assistant.run("According to the notes, how is compressor work calculated?")

    assert response.tool_calls[0].name == "search_technical_documents"
    assert '[demo.md, section "Compressor"]' in response.answer
    assert response.mode == "local"


def test_cloud_tool_loop_executes_local_calculation_and_returns_answer() -> None:
    inputs = {
        "ambient_temperature_c": 15,
        "ambient_pressure_kpa": 101.325,
        "pressure_ratio": 12,
        "air_mass_flow_kg_s": 100,
        "turbine_inlet_temperature_k": 1300,
        "compressor_efficiency": 0.85,
        "turbine_efficiency": 0.9,
        "combustor_pressure_loss_fraction": 0.04,
        "mechanical_efficiency": 0.98,
        "generator_efficiency": 0.97,
    }
    client = FakeClient(
        [
            SimpleNamespace(output=[tool_call("calculate_cycle", inputs)], output_text=""),
            text_response("The local model estimates 26 MW for this illustrative case."),
        ]
    )
    assistant = TurbineAssistant(
        cloud_settings=CloudLLMSettings(api_key="fake", model="test-model"),
        client=client,
    )

    response = assistant.run("Calculate the power.", enable_cloud=True)

    assert response.mode == "cloud"
    assert response.answer.startswith("The local model")
    assert response.tool_calls[0].name == "calculate_cycle"
    assert len(client.responses.calls) == 2
    assert client.responses.calls[0]["store"] is False
    tool_output = client.responses.calls[1]["input"][-1]
    assert tool_output["type"] == "function_call_output"
    assert json.loads(tool_output["output"])["result"]["electrical_power_kw"] > 0


def test_cloud_document_tool_is_hidden_unless_user_opted_in() -> None:
    docs = load_document_bytes("private.txt", b"The secret demo note describes a compressor.")
    client = FakeClient([text_response("No document context was sent.")])
    assistant = TurbineAssistant(
        docs,
        cloud_settings=CloudLLMSettings(api_key="fake", model="test-model"),
        client=client,
    )

    response = assistant.run("Explain the cycle.", enable_cloud=True)

    tool_names = [tool["name"] for tool in client.responses.calls[0]["tools"]]
    serialized_input = json.dumps(client.responses.calls[0]["input"][:2])
    assert "search_technical_documents" not in tool_names
    assert "secret demo note" not in serialized_input
    assert response.mode == "cloud"


def test_cloud_document_tool_returns_citations_only_after_opt_in() -> None:
    docs = load_document_bytes("demo.txt", b"The compressor raises air pressure and temperature.")
    client = FakeClient(
        [
            SimpleNamespace(
                output=[tool_call("search_technical_documents", {"query": "compressor pressure"})],
                output_text="",
            ),
            text_response("The note says the compressor raises pressure [demo.txt]."),
        ]
    )
    assistant = TurbineAssistant(
        docs,
        cloud_settings=CloudLLMSettings(api_key="fake", model="test-model"),
        client=client,
    )

    response = assistant.run(
        "What does the note say about the compressor?",
        enable_cloud=True,
        allow_cloud_document_context=True,
    )

    assert response.tool_calls[0].result["evidence"][0]["citation"] == "[demo.txt]"
    assert "The note says" in response.answer
    assert "search_technical_documents" in [
        tool["name"] for tool in client.responses.calls[0]["tools"]
    ]


def test_cloud_inspects_selected_synthetic_twin_context() -> None:
    context = {
        "run": {"scenario_name": "Compressor-performance drift", "seed": 42},
        "snapshot": {"sample_index": 72, "synthetic_only": True},
        "selected_component": {"component_id": "compressor", "label": "Compressor"},
    }
    client = FakeClient(
        [
            SimpleNamespace(
                output=[tool_call("inspect_synthetic_twin_snapshot", {})], output_text=""
            ),
            text_response("The selected synthetic compressor sample is shown."),
        ]
    )
    assistant = TurbineAssistant(
        cloud_settings=CloudLLMSettings(api_key="fake", model="test-model"),
        client=client,
    )

    response = assistant.run(
        "Explain the current compressor result.",
        enable_cloud=True,
        twin_context=context,
    )

    tool_names = [tool["name"] for tool in client.responses.calls[0]["tools"]]
    serialized_input = json.dumps(client.responses.calls[0]["input"][:2])
    assert "inspect_synthetic_twin_snapshot" in tool_names
    assert "Compressor-performance drift" in serialized_input
    assert response.tool_calls[0].result == context


def test_disallowed_document_tool_call_cannot_send_excerpts_without_opt_in() -> None:
    docs = load_document_bytes("demo.txt", b"Local-only excerpt with a unique phrase.")
    client = FakeClient(
        [
            SimpleNamespace(
                output=[tool_call("search_technical_documents", {"query": "unique phrase"})],
                output_text="",
            ),
            text_response("The document tool was rejected."),
        ]
    )
    assistant = TurbineAssistant(
        docs,
        cloud_settings=CloudLLMSettings(api_key="fake"),
        client=client,
    )

    response = assistant.run("Question without document sharing.", enable_cloud=True)

    assert response.tool_calls[0].result == {
        "error": "document excerpts were not approved for cloud use"
    }
    second_input = client.responses.calls[1]["input"][-1]
    assert "unique phrase" not in second_input["output"]


def test_unknown_cloud_tool_is_rejected_by_local_allow_list() -> None:
    client = FakeClient(
        [
            SimpleNamespace(
                output=[tool_call("run_shell", {})],
                output_text="",
            ),
            text_response("I cannot run that tool."),
        ]
    )
    assistant = TurbineAssistant(
        cloud_settings=CloudLLMSettings(api_key="fake"),
        client=client,
    )

    response = assistant.run("Do something risky.", enable_cloud=True)

    assert response.tool_calls[0].result["error"].startswith("tool 'run_shell' is not in")


def test_cloud_failure_falls_back_to_local_answer_without_exposing_secret() -> None:
    class FailingClient:
        class responses:
            @staticmethod
            def create(**kwargs):
                raise RuntimeError("request failed with a secret token")

    assistant = TurbineAssistant(
        cloud_settings=CloudLLMSettings(api_key="secret"),
        client=FailingClient(),
    )

    response = assistant.run("Calculate the turbine output.", enable_cloud=True)

    assert response.mode == "local_fallback"
    assert "RuntimeError" in response.warning
    assert "secret token" not in response.warning
    assert response.tool_calls[0].name == "calculate_cycle"


def _twin_context(
    scenario_id="compressor_fouling", seed=42, sample_index=60, component="compressor"
):
    from turbineiq.twin import create_synthetic_twin

    twin = create_synthetic_twin(scenario_id, seed=seed)
    snapshot = twin.snapshot_at(sample_index).to_dict()
    selected = next(c for c in snapshot["components"] if c["component_id"] == component)
    return {
        "run": {
            "scenario_id": scenario_id,
            "scenario_name": twin.scenario_name,
            "seed": seed,
            "sample_count": twin.sample_count,
            "model_name": twin.model_name,
            "synthetic_only": True,
        },
        "snapshot": snapshot,
        "selected_component": selected,
    }


def test_local_assistant_reruns_cycle_for_a_stated_pressure_ratio_even_with_selection() -> None:
    response = TurbineAssistant().run(
        "What is the efficiency at pressure ratio 18?", twin_context=_twin_context()
    )

    assert [call.name for call in response.tool_calls] == ["calculate_cycle", "calculate_cycle"]
    default_call, changed_call = response.tool_calls
    assert default_call.arguments["pressure_ratio"] == 12
    assert changed_call.arguments["pressure_ratio"] == 18
    assert changed_call.result["result"]["electrical_efficiency"] > (
        default_call.result["result"]["electrical_efficiency"]
    )
    assert "pressure ratio 18 (default 12)" in response.answer
    assert "Selected synthetic replay" not in response.answer
    efficiency = changed_call.result["result"]["electrical_efficiency"]
    assert f"{efficiency:.1%}" in response.answer


def test_local_assistant_converts_units_in_what_if_questions() -> None:
    response = TurbineAssistant().run(
        "What if ambient is 95 F and turbine inlet temperature is 1500 C with 120 kg/s air flow?"
    )

    changed = response.tool_calls[-1].arguments
    assert changed["ambient_temperature_c"] == pytest.approx(35.0)
    assert changed["turbine_inlet_temperature_k"] == pytest.approx(1773.15)
    assert changed["air_mass_flow_kg_s"] == 120
    assert changed["pressure_ratio"] == 12


def test_local_assistant_reports_invalid_what_if_inputs_instead_of_crashing() -> None:
    response = TurbineAssistant().run("What about pressure ratio 0.5?")

    assert response.mode == "local"
    assert response.tool_calls == ()
    assert "pressure_ratio must be greater than 1" in response.answer


def test_local_assistant_compares_named_scenarios() -> None:
    response = TurbineAssistant().run("Compare warm ambient against baseline with seed 7.")

    assert [call.name for call in response.tool_calls] == ["summarize_synthetic_scenario"] * 2
    assert [call.arguments["scenario_id"] for call in response.tool_calls] == [
        "warm_ambient",
        "baseline",
    ]
    assert all(call.arguments["seed"] == 7 for call in response.tool_calls)
    assert "Compared with Warmer ambient, Baseline changes mean modeled output" in response.answer


def test_local_assistant_answers_about_a_named_scenario_even_when_another_is_selected() -> None:
    response = TurbineAssistant().run(
        "Tell me about the sensor fault scenario.",
        twin_context=_twin_context(),
    )

    assert response.tool_calls[0].arguments["scenario_id"] == "sensor_fault"
    assert "Selected synthetic replay" not in response.answer


def test_local_assistant_summarises_the_whole_run_for_run_level_questions() -> None:
    response = TurbineAssistant().run(
        "How many samples are flagged in this run?", twin_context=_twin_context(seed=7)
    )

    call = response.tool_calls[0]
    assert call.name == "summarize_synthetic_scenario"
    assert call.arguments == {"scenario_id": "compressor_fouling", "seed": 7}
    assert call.result["drift_flag_count"] > 50
    assert "sustained drift" in response.answer


def test_local_assistant_explains_selected_sample_when_asked_about_it() -> None:
    response = TurbineAssistant().run(
        "Explain the Compressor metrics at sample 61.", twin_context=_twin_context()
    )

    assert response.tool_calls[0].name == "inspect_synthetic_twin_snapshot"
    assert response.answer.startswith("Selected synthetic replay")
    assert "flagged for sustained drift" in response.answer


def test_local_assistant_says_when_it_could_not_match_the_question() -> None:
    response = TurbineAssistant().run("hello there", twin_context=_twin_context())

    assert response.answer.startswith("I could not tie this question")
    assert "pressure ratio 18" in response.answer
    assert "Selected synthetic replay" in response.answer
