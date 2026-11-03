"""Local-only API for reproducible synthetic turbine runs and evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from turbineiq.agent import TurbineAssistant
from turbineiq.rag import DocumentChunk, load_document_path, search_documents
from turbineiq.synthetic import SCENARIOS
from turbineiq.twin import create_synthetic_twin

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEMO_DOCUMENTS_PATH = PROJECT_ROOT / "data" / "documents"
FRONTEND_DIST_PATH = PROJECT_ROOT / "frontend" / "dist"


def _load_demo_documents() -> list[DocumentChunk]:
    documents: list[DocumentChunk] = []
    for path in sorted(DEMO_DOCUMENTS_PATH.glob("*")):
        if path.is_file() and path.suffix.lower() in {".md", ".markdown", ".txt", ".pdf"}:
            documents.extend(load_document_path(path))
    return documents


DEMO_DOCUMENTS = _load_demo_documents()
assistant = TurbineAssistant(documents=DEMO_DOCUMENTS)

app = FastAPI(
    title="TurbineIQ local API",
    description=(
        "Local deterministic engineering services for a synthetic, offline gas-turbine "
        "demonstrator. No industrial connectivity or control endpoints are provided."
    ),
    version="0.2.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class SelectedTwinContext(BaseModel):
    scenario_id: str = Field(min_length=1, max_length=80)
    seed: int = Field(ge=0, le=2_147_483_647)
    sample_index: int = Field(ge=0, le=95)
    selected_component_id: Literal[
        "inlet", "compressor", "combustor", "turbine", "shaft", "generator"
    ]


class AssistantRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    enable_cloud: bool = False
    allow_cloud_document_context: bool = False
    selected_twin: SelectedTwinContext | None = None


@app.get("/api/health")
def health() -> dict[str, str | bool]:
    return {"status": "ok", "synthetic_only": True, "industrial_connection": False}


@app.get("/api/scenarios")
def list_scenarios() -> list[dict[str, str | bool | int]]:
    return [
        {
            "scenario_id": scenario_id,
            "name": spec.name,
            "description": spec.description,
            "synthetic_only": True,
            "sample_interval_minutes": 15,
        }
        for scenario_id, spec in SCENARIOS.items()
    ]


@app.get("/api/twin/run")
def get_twin_run(
    scenario_id: str = Query(default="compressor_fouling"),
    seed: int = Query(default=42, ge=0, le=2_147_483_647),
    samples: int = Query(default=96, ge=8, le=288),
    sample_index: int = Query(default=48, ge=0),
) -> dict[str, Any]:
    if scenario_id not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Unknown scenario_id: {scenario_id}")
    if sample_index >= samples:
        raise HTTPException(status_code=422, detail="sample_index must be less than samples")

    run = create_synthetic_twin(scenario_id, seed=seed, samples=samples)
    return run.to_payload(sample_index)


@app.get("/api/evidence/search")
def search_evidence(
    q: str = Query(min_length=2, max_length=300),
    top_k: int = Query(default=4, ge=1, le=8),
) -> dict[str, object]:
    hits = search_documents(q, DEMO_DOCUMENTS, top_k=top_k)
    return {
        "query": q,
        "mode": "local lexical retrieval",
        "evidence": [
            {
                "text": hit.chunk.text,
                "citation": hit.citation,
                "source": hit.chunk.source,
                "page_number": hit.chunk.page_number,
                "section": hit.chunk.section,
                "score": round(hit.score, 4),
            }
            for hit in hits
        ],
        "no_evidence": not hits,
    }


@app.post("/api/assistant/ask")
def ask_assistant(request: AssistantRequest) -> dict[str, object]:
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=422, detail="question must not be blank")
    if request.allow_cloud_document_context and not request.enable_cloud:
        raise HTTPException(
            status_code=422,
            detail="cloud document context requires explicit cloud mode",
        )

    twin_context = None
    if request.selected_twin is not None:
        selection = request.selected_twin
        if selection.scenario_id not in SCENARIOS:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown synthetic scenario: {selection.scenario_id}",
            )
        twin_run = create_synthetic_twin(selection.scenario_id, seed=selection.seed, samples=96)
        twin_snapshot = twin_run.snapshot_at(selection.sample_index).to_dict()
        component = next(
            (
                item
                for item in twin_snapshot["components"]
                if item["component_id"] == selection.selected_component_id
            ),
            None,
        )
        if component is None:
            raise HTTPException(status_code=422, detail="Selected component is not in the snapshot")
        twin_context = {
            "run": {
                "scenario_id": twin_run.scenario_id,
                "scenario_name": twin_run.scenario_name,
                "scenario_description": twin_run.scenario_description,
                "seed": twin_run.seed,
                "sample_count": twin_run.sample_count,
                "model_name": twin_run.model_name,
                "synthetic_only": True,
            },
            "snapshot": twin_snapshot,
            "selected_component": component,
        }

    response = assistant.run(
        question,
        enable_cloud=request.enable_cloud,
        allow_cloud_document_context=request.allow_cloud_document_context,
        twin_context=twin_context,
    )
    return {
        "answer": response.answer,
        "mode": response.mode,
        "warning": response.warning,
        "tool_calls": [call.to_dict() for call in response.tool_calls],
        "synthetic_only": True,
    }


if FRONTEND_DIST_PATH.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_PATH, html=True), name="web")
