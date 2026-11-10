"""The deterministic allow-list exposed to local and cloud orchestration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from turbineiq.analytics import assess_data_quality, detect_anomalies
from turbineiq.engineering import CycleInputs, simulate_cycle
from turbineiq.rag import DocumentChunk, search_documents
from turbineiq.synthetic import generate_scenario

CYCLE_FIELDS = {
    "ambient_temperature_c",
    "ambient_pressure_kpa",
    "pressure_ratio",
    "air_mass_flow_kg_s",
    "turbine_inlet_temperature_k",
    "compressor_efficiency",
    "turbine_efficiency",
    "combustor_pressure_loss_fraction",
    "mechanical_efficiency",
    "generator_efficiency",
}


def calculate_cycle_tool(arguments: dict[str, Any]) -> dict[str, object]:
    """Run the local deterministic cycle solver with supplied study inputs."""

    extra = set(arguments) - CYCLE_FIELDS
    if extra:
        raise ValueError(f"unsupported calculation field(s): {', '.join(sorted(extra))}")
    missing = CYCLE_FIELDS - set(arguments)
    if missing:
        raise ValueError(f"missing calculation field(s): {', '.join(sorted(missing))}")
    inputs = CycleInputs(**arguments)
    result = simulate_cycle(inputs)
    return {"inputs_used": asdict(inputs), "result": result.to_dict()}


def summarize_scenario_tool(arguments: dict[str, Any]) -> dict[str, object]:
    """Run a generated synthetic scenario and summarize local analytics."""

    scenario_id = arguments.get("scenario_id", "baseline")
    seed = arguments.get("seed", 42)
    if set(arguments) - {"scenario_id", "seed"}:
        raise ValueError("summarize_scenario accepts only scenario_id and seed")
    if set(arguments) != {"scenario_id", "seed"}:
        raise ValueError("summarize_scenario requires scenario_id and seed")
    if not isinstance(scenario_id, str):
        raise ValueError("scenario_id must be a string")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2_147_483_647:
        raise ValueError("seed must be an integer in the supported range")
    frame = generate_scenario(scenario_id, seed=seed, samples=96)
    report = assess_data_quality(frame)
    anomalies = detect_anomalies(frame)
    flagged = anomalies.loc[anomalies["anomaly_flag"]]
    return {
        "scenario_id": scenario_id,
        "scenario_name": frame.attrs["scenario_name"],
        "scenario_description": frame.attrs["scenario_description"],
        "synthetic_only": True,
        "seed": seed,
        "row_count": len(frame),
        "mean_ambient_temperature_c": float(frame["ambient_temperature_c"].mean()),
        "mean_model_electrical_power_kw": float(frame["model_electrical_power_kw"].mean()),
        "mean_observed_electrical_power_kw": float(frame["observed_electrical_power_kw"].mean()),
        "quality_report": report.to_dict(),
        "robust_outlier_count": int(len(flagged)),
        "labelled_sensor_fault_count": int(frame["sensor_fault_injected"].sum()),
        "flagged_timestamps_utc": [value.isoformat() for value in flagged["timestamp_utc"]],
    }


def search_documents_tool(
    arguments: dict[str, Any],
    documents: list[DocumentChunk],
) -> dict[str, object]:
    """Search only already-indexed local documents; return bounded excerpts."""

    if set(arguments) != {"query"}:
        raise ValueError("search_technical_documents requires only a query")
    query = arguments["query"]
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query must be a non-empty string")
    if len(query) > 300:
        raise ValueError("query must be at most 300 characters")
    hits = search_documents(query, documents, top_k=3)
    return {
        "query": query,
        "evidence": [
            {
                "text": hit.chunk.text[:900],
                "citation": hit.citation,
                "relevance_score": round(hit.score, 4),
            }
            for hit in hits
        ],
        "no_evidence": not hits,
    }


def inspect_synthetic_twin_tool(
    arguments: dict[str, Any],
    twin_context: dict[str, Any] | None,
) -> dict[str, object]:
    """Return the server-recomputed selected synthetic twin state."""

    if arguments:
        raise ValueError("inspect_synthetic_twin accepts no arguments")
    if twin_context is None:
        raise ValueError("no selected synthetic twin state was supplied")
    return twin_context
