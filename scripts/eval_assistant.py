"""Run deterministic fake or explicitly configured live assistant evaluations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from turbineiq.agent import CloudLLMSettings, TurbineAssistant  # noqa: E402
from turbineiq.agent.llm import LLMMessage, LLMReply, LLMSettings, LLMToolCall  # noqa: E402
from turbineiq.rag import load_document_bytes  # noqa: E402
from turbineiq.twin import create_synthetic_twin  # noqa: E402

NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?")
GROUNDED_TOLERANCE = 0.001


def _golden_cases() -> list[dict[str, Any]]:
    base = {
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
    cases: list[dict[str, Any]] = []
    for index, pressure_ratio in enumerate((8, 9, 10, 11, 12, 14, 16, 18), start=1):
        arguments = {**base, "pressure_ratio": pressure_ratio, "air_mass_flow_kg_s": 80 + index * 5}
        cases.append(
            {
                "id": f"cycle-{index:02d}",
                "question": (
                    "For this illustrative cycle case, what electrical output does the model "
                    f"calculate at pressure ratio {pressure_ratio}?"
                ),
                "expected_tool": "calculate_cycle",
                "arguments": arguments,
                "fact_path": "result.electrical_power_kw",
            }
        )
    scenario_cases = (
        ("baseline", 42),
        ("baseline", 7),
        ("warm_ambient", 42),
        ("warm_ambient", 123),
        ("compressor_fouling", 42),
        ("compressor_fouling", 19),
        ("sensor_fault", 42),
    )
    for index, (scenario_id, seed) in enumerate(scenario_cases, start=1):
        cases.append(
            {
                "id": f"scenario-{index:02d}",
                "question": (
                    "What is the mean modeled electrical output for the "
                    f"{scenario_id} synthetic scenario with seed {seed}?"
                ),
                "expected_tool": "summarize_synthetic_scenario",
                "arguments": {"scenario_id": scenario_id, "seed": seed},
                "fact_path": "mean_model_electrical_power_kw",
            }
        )
    document_questions = (
        "What pressure ratio is listed in the synthetic cycle note?",
        "Which compressor efficiency is named in the synthetic evaluation note?",
        "What air mass flow is used in the synthetic cycle example?",
        "Find the cited synthetic evaluation note about cycle inputs.",
    )
    for index, question in enumerate(document_questions, start=1):
        cases.append(
            {
                "id": f"evidence-{index:02d}",
                "question": question,
                "expected_tool": "search_technical_documents",
                "arguments": {"query": "synthetic cycle note inputs"},
                "fact_path": "evidence.0.text",
                "allow_documents": True,
            }
        )
    twin_cases = (
        ("compressor_fouling", 42, 72, "compressor"),
        ("baseline", 7, 12, "turbine"),
        ("warm_ambient", 123, 35, "generator"),
        ("sensor_fault", 42, 48, "compressor"),
        ("compressor_fouling", 19, 95, "turbine"),
        ("baseline", 123, 0, "inlet"),
    )
    for index, (scenario_id, seed, sample_index, component_id) in enumerate(twin_cases, start=1):
        cases.append(
            {
                "id": f"snapshot-{index:02d}",
                "question": (
                    "What is the reference electrical output at sample "
                    f"{sample_index + 1} for this selected synthetic component?"
                ),
                "expected_tool": "inspect_synthetic_twin_snapshot",
                "arguments": {},
                "fact_path": "snapshot.model_electrical_power_kw",
                "context": {
                    "scenario_id": scenario_id,
                    "seed": seed,
                    "sample_index": sample_index,
                    "selected_component_id": component_id,
                },
            }
        )
    assert len(cases) == 25
    return cases


class ScriptedFakeProvider:
    def __init__(self, case: dict[str, Any]) -> None:
        self.case = case

    def complete(self, *, messages: list[LLMMessage], **_kwargs: Any) -> LLMReply:
        tool_messages = [message for message in messages if message.role == "tool"]
        if not tool_messages:
            return LLMReply(
                text="",
                tool_calls=(
                    LLMToolCall(
                        call_id=f"fake-{self.case['id']}",
                        name=self.case["expected_tool"],
                        arguments=json.dumps(self.case["arguments"]),
                    ),
                ),
            )
        result = _parse_tool_output(tool_messages[-1].content)
        fact = _get_path(result, self.case["fact_path"])
        candidates = _numbers(fact)
        if not candidates:
            return LLMReply(text="The tool result did not contain a numeric fact.")
        return LLMReply(text=f"The retrieved deterministic tool result includes {candidates[0]:g}.")


def _parse_tool_output(value: str) -> Any:
    start = value.find("{")
    if start < 0:
        return {}
    parsed, _end = json.JSONDecoder().raw_decode(value[start:])
    return parsed


def _get_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def _numbers(value: Any) -> list[float]:
    if isinstance(value, bool) or value is None:
        return []
    if isinstance(value, (float, int)):
        return [float(value)]
    if isinstance(value, str):
        return [float(item) for item in NUMBER_RE.findall(value)]
    if isinstance(value, dict):
        return [number for item in value.values() for number in _numbers(item)]
    if isinstance(value, (list, tuple)):
        return [number for item in value for number in _numbers(item)]
    return []


def _case_context(case: dict[str, Any]) -> dict[str, Any] | None:
    selection = case.get("context")
    if not selection:
        return None
    run = create_synthetic_twin(selection["scenario_id"], seed=selection["seed"], samples=96)
    payload = run.to_payload(selection["sample_index"])
    selected_component = next(
        item
        for item in payload["snapshot"]["components"]
        if item["component_id"] == selection["selected_component_id"]
    )
    return {
        "run": payload["run"],
        "snapshot": payload["snapshot"],
        "selected_component": selected_component,
    }


def _evaluation_documents():
    return load_document_bytes(
        "synthetic-evaluation-note.txt",
        (
            b"Synthetic evaluation note: pressure ratio 12.0, compressor efficiency 0.85, "
            b"and air mass flow 100.0 kg/s are illustrative local example inputs; "
            b"they are not OEM specifications."
        ),
    )


def _grounded(answer: str, result: Any, context: Any) -> bool:
    answer_numbers = _numbers(answer)
    source_numbers = _numbers(result) + _numbers(context)
    return bool(answer_numbers) and all(
        any(
            abs(value - source) <= max(0.01, abs(source) * GROUNDED_TOLERANCE)
            for source in source_numbers
        )
        for value in answer_numbers
    )


def run_evaluation(live: bool = False) -> dict[str, Any]:
    documents = _evaluation_documents()
    live_settings = CloudLLMSettings.from_environment() if live else None
    if live_settings is not None and not live_settings.configured:
        raise RuntimeError("Live evaluation needs a configured provider; no request was sent.")
    rows: list[dict[str, Any]] = []
    tool_correct = 0
    grounded_count = 0
    numeric_fact_correct = 0
    passing = 0
    cases = _golden_cases()
    for case in cases:
        context = _case_context(case)
        if live:
            assert live_settings is not None
            assistant = TurbineAssistant(documents, cloud_settings=live_settings)
        else:
            assistant = TurbineAssistant(
                documents,
                cloud_settings=LLMSettings(
                    provider="custom",
                    api_key="fake-eval",
                    model="scripted-fake",
                    base_url="http://127.0.0.1/fake/v1",
                ),
                adapter=ScriptedFakeProvider(case),
            )
        response = assistant.run(
            case["question"],
            enable_cloud=True,
            allow_cloud_document_context=case.get("allow_documents", False),
            twin_context=context,
        )
        names = [call.name for call in response.tool_calls]
        matched = response.mode == "cloud" and case["expected_tool"] in names
        if matched:
            tool_correct += 1
        result_values = [call.result for call in response.tool_calls]
        context_for_check = context or {}
        grounded = _grounded(response.answer, result_values, context_for_check)
        if grounded:
            grounded_count += 1
        expected_result = next(
            (call.result for call in response.tool_calls if call.name == case["expected_tool"]),
            {},
        )
        try:
            expected_fact_values = _numbers(_get_path(expected_result, case["fact_path"]))
        except (KeyError, IndexError, TypeError, ValueError):
            expected_fact_values = []
        answer_values = _numbers(response.answer)
        expected_fact = expected_fact_values[0] if expected_fact_values else None
        numeric_fact_matched = expected_fact is not None and any(
            abs(value - expected_fact) <= max(0.01, abs(expected_fact) * GROUNDED_TOLERANCE)
            for value in answer_values
        )
        if numeric_fact_matched:
            numeric_fact_correct += 1
        passed = matched and grounded and numeric_fact_matched
        if passed:
            passing += 1
        rows.append(
            {
                "id": case["id"],
                "expected_tool": case["expected_tool"],
                "observed_tools": names,
                "numeric_fact_path": case["fact_path"],
                "expected_numeric_fact": expected_fact,
                "mode": response.mode,
                "tool_correct": matched,
                "grounded": grounded,
                "numeric_fact_matched": numeric_fact_matched,
                "passed": passed,
            }
        )
    total = len(cases)
    settings = live_settings or LLMSettings(
        provider="custom", model="scripted-fake", base_url="http://127.0.0.1/fake/v1"
    )
    return {
        "date": date.today().isoformat(),
        "mode": "live" if live else "fake",
        "provider": settings.provider,
        "model": settings.model,
        "case_count": total,
        "pass_count": passing,
        "pass_rate": round(passing / total, 4),
        "tool_accuracy": round(tool_correct / total, 4),
        "groundedness_rate": round(grounded_count / total, 4),
        "numeric_fact_accuracy": round(numeric_fact_correct / total, 4),
        "groundedness_tolerance": GROUNDED_TOLERANCE,
        "cases": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--fake", action="store_true", help="Use the scripted provider (default).")
    group.add_argument(
        "--live",
        action="store_true",
        help="Send synthetic evaluation prompts to the configured provider.",
    )
    args = parser.parse_args()
    try:
        report = run_evaluation(live=args.live)
    except Exception as exc:
        print(f"Assistant evaluation could not run ({type(exc).__name__}).", file=sys.stderr)
        return 2
    rendered = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)
    if args.live:
        evidence_dir = ROOT / "docs" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        output = evidence_dir / f"assistant-eval-{report['date']}.json"
        output.write_text(rendered + "\n", encoding="utf-8")
        print(f"Live evaluation report: {output.relative_to(ROOT).as_posix()}")
    print(rendered)
    return 0 if report["pass_count"] == report["case_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
