# TurbineIQ

TurbineIQ is a local-first prototype for exploring a **simplified, single-shaft, open-cycle industrial gas turbine**. It combines deterministic engineering calculations, reproducible synthetic operating scenarios, an offline synthetic digital-twin demonstrator, data checks, cited technical-document search, and a single tool-using assistant. A cloud language model is optional; engineering and data processing stay local.

This is an educational and analytical prototype. Its synthetic twin is not synchronized to a physical asset. It is not an OEM performance model, maintenance authorization system, or control system.

## Scope boundaries

- Demonstration operating data is generated locally from documented assumptions and a fixed random seed.
- The offline twin mirrors selected states from that generated scenario and compares model output with a synthetic observation.
- No real turbine data, OEM specifications, operating limits, or confidential FieldCore material is included.
- No physical-turbine synchronization, live industrial connectivity, DCS/SCADA/PLC interface, remote control, or autonomous maintenance action is included.
- The cloud model can only request an allow-listed local tool. It cannot run code or write files.
- Sending a question or retrieved document excerpts to a cloud LLM requires an explicit UI choice.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,cloud]"
streamlit run app.py
```

## Run the interactive engineering workspace

Install the Python package and frontend dependencies once, then run the local API and Vite development server in separate terminals:

```powershell
python -m pip install -e ".[dev,cloud]"
cd frontend
npm install
npm run dev
```

In a second terminal from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000
```

Open the local URL printed by Vite (normally `http://localhost:5173`). The frontend uses the API at `127.0.0.1:8000`. For a single-process preview, run `npm run build` in `frontend`, then launch the API; FastAPI serves `frontend/dist` when it exists. Streamlit remains available as the earlier prototype.

The 3D panel auto-loads the project-authored, source-noted GE 6B.03 reference model from `frontend/public/models/turbine.glb`. Its geometry is a conceptual visualization, not a dimensionally accurate OEM assembly. The editable Blender scene and reproducible generator are in `models/`; the public-data review explains the evidence and limits. For the semantic mapping and export contract, see [Blender model integration](docs/BLENDER_INTEGRATION.md).

Rebuild the native Blender scene, app GLB, and preview render with Blender installed:

```powershell
blender --background --python models/build_ge_6b03_reference.py
```

Cloud LLM support is optional. If no API key is configured, the deterministic local assistant remains available. Install the `cloud` extra and copy `.env.example` to `.env` only if you want to configure the provider; never commit credentials. The app asks before sending a question and tool results to the cloud. Document excerpts require a separate opt-in.

## Verify

```powershell
python -m pytest -q
ruff check src tests
```

## Project map

```text
app.py                       Streamlit entry point
src/turbineiq/engineering/   Brayton-cycle model and validation
src/turbineiq/synthetic/     Seeded scenario generator
src/turbineiq/analytics/     Data-quality checks and anomaly flags
src/turbineiq/twin/         Synthetic-only digital-twin state views
src/turbineiq/rag/           Local document ingestion and retrieval
src/turbineiq/agent/         Single-agent tool routing and optional cloud adapter
src/turbineiq/ui/            Streamlit pages
src/turbineiq/api/           Local FastAPI endpoints for the browser workspace
frontend/                    React, TypeScript, Three.js / React Three Fiber workspace
tests/                       Unit and integration tests
data/documents/              Public-domain or clearly synthetic demo notes only
docs/                        Scope, research notes, backlog, and demo guide
```

The local prototype includes an interactive synthetic replay, a local API, cited retrieval, and a bounded assistant. See the [backlog](docs/DEVELOPMENT_BACKLOG.md), [scope](docs/PROJECT_SCOPE.md), and [GitHub reuse review](docs/OPEN_SOURCE_REVIEW.md).

For a guided meeting walkthrough, see the [three-minute demo guide](docs/DEMO_GUIDE.md). The [architecture note](docs/ARCHITECTURE.md) describes module boundaries and data flow.

