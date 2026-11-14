import json
from types import SimpleNamespace

import pytest

from turbineiq.agent import CloudLLMSettings, TurbineAssistant
from turbineiq.agent.grounding import check_numbers, extract_numbers
from turbineiq.twin import create_synthetic_twin


def test_extraction_skips_citations_list_markers_small_counts_and_sample_labels() -> None:
    text = (
        "1. Power is 25.46 MW at 1,300 K at sample 49 [demo_cycle_notes.md, page 12]. "
        "Three of 7 checks passed; ratio 12.8:1 and -1,000.9 kW."
    )
    found = [mention.text for mention in extract_numbers(text)]
    assert found == ["25.46", "1,300", "12.8", "-1,000.9"]


def test_common_unit_conversions_and_rounding_are_recognised() -> None:
    source = {"electrical_power_kw": 25460.4, "exhaust_k": 768.2, "efficiency": 0.3751}
    grounding = check_numbers("25.46 MW, 25,460 kW, 495 °C, 768.2 K and 37.5% efficiency", source)
    assert grounding.unverified == ()
    assert grounding.verified == grounding.checked == 5


def test_sign_is_ignored_for_residuals_described_as_below() -> None:
    grounding = check_numbers("It sits 1,000.9 kW below the model.", {"power_residual_kw": -1000.9})
    assert grounding.all_verified


def test_a_number_no_source_contains_is_reported() -> None:
    grounding = check_numbers("The model gives 31.7 MW and 25.5 MW.", {"mw": 25.46})
    assert grounding.unverified == ("31.7",)
    assert grounding.verified == 1


def test_numbers_from_the_question_count_as_given() -> None:
    grounding = check_numbers("At 18 bar the result changes.", "What if the pressure is 18 bar?")
    assert grounding.all_verified


def test_a_number_that_rounds_the_wrong_way_is_not_verified() -> None:
    # 25.46 MW is "about 25", not "26"; the check should not wave it through.
    assert check_numbers("About 26 MW.", {"electrical_power_kw": 25460.0}).unverified == ("26",)


def _context() -> dict:
    twin = create_synthetic_twin("compressor_fouling", seed=42)
    snapshot = twin.snapshot_at(60).to_dict()
    return {
        "run": {
            "scenario_id": "compressor_fouling",
            "scenario_name": twin.scenario_name,
            "seed": 42,
            "sample_count": twin.sample_count,
            "model_name": twin.model_name,
            "synthetic_only": True,
        },
        "snapshot": snapshot,
        "selected_component": snapshot["components"][1],
    }


@pytest.mark.parametrize(
    ("question", "with_context"),
    [
        ("Calculate the turbine electrical power.", False),
        ("What is the efficiency at pressure ratio 18?", True),
        ("What if ambient is 95 F and turbine inlet temperature is 1500 C?", False),
        ("Compare baseline and warm_ambient.", False),
        ("Explain the selected sample.", True),
        ("Summarise the whole run.", True),
    ],
)
def test_local_answers_trace_every_number_to_a_tool_result(
    question: str, with_context: bool
) -> None:
    response = TurbineAssistant().run(question, twin_context=_context() if with_context else None)

    assert response.grounding is not None
    assert response.grounding.unverified == (), response.answer


def test_a_cloud_answer_with_an_invented_number_is_flagged() -> None:
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

    def reply(answer: str):
        class Client:
            def __init__(self) -> None:
                outputs = [
                    SimpleNamespace(
                        output=[
                            SimpleNamespace(
                                type="function_call",
                                name="calculate_cycle",
                                arguments=json.dumps(inputs),
                                call_id="c1",
                            )
                        ],
                        output_text="",
                    ),
                    SimpleNamespace(output=[], output_text=answer),
                ]
                self.responses = SimpleNamespace(create=lambda **_: outputs.pop(0))

        return TurbineAssistant(
            cloud_settings=CloudLLMSettings(api_key="fake", model="test-model"), client=Client()
        )

    honest = reply("The model gives 25.5 MW at 37.5% efficiency.").run(
        "Power?", enable_cloud=True
    )
    invented = reply("The model gives 25.5 MW and a 41.8% efficiency.").run(
        "Power?", enable_cloud=True
    )

    assert honest.mode == invented.mode == "cloud"
    assert honest.grounding is not None and honest.grounding.unverified == ()
    assert invented.grounding is not None and invented.grounding.unverified == ("41.8",)
