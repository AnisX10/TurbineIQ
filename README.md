# TurbineIQ

TurbineIQ is a local-first prototype for exploring a simplified, single-shaft, open-cycle industrial gas turbine. Its primary interface is a React and Three.js engineering workspace backed by a local FastAPI service and deterministic Python modules. The workspace brings together a simplified Brayton-cycle reference, reproducible synthetic scenarios, data-quality screening, cited local document search, and a bounded assistant.

The project includes an interactive synthetic-twin demonstrator. It is not synchronized to a physical turbine and is not an OEM performance model, maintenance authorization system, or control system. No real turbine data, fabricated OEM specifications, live industrial connectivity, DCS/SCADA/PLC control, or confidential FieldCore material is included.

## The workspace

The Overview connects the sample replay, engineering readouts, interactive stage, component ledger, and timeline. Components provides component metrics, trends, and linked evidence. Evidence searches local technical notes. Assistant defaults to deterministic local mode; using a cloud model requires an explicit choice, and sending retrieved excerpts has a separate consent control.

![Overview with the interactive turbine stage](docs/redesign/phase5/stage-after-light.webp)

![Assistant answer with its expanded tool trace](docs/redesign/phase5/states/assistant-answer-tool-trace-expanded-1440-light.webp)

The stage loads the project-authored `frontend/public/models/turbine.glb`. This conceptual Blender visualization is Meshopt-compressed for delivery; an uncompressed glTF export also loads. See [Blender model integration](docs/BLENDER_INTEGRATION.md) for the name-mapping and export contract.

## Run the browser workspace

Requirements: Python 3.11 or newer, Node.js 22 or newer, and npm. Run the API and frontend in separate terminals from the repository root.

### PowerShell

Terminal 1:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
npm ci --prefix frontend
npm run dev --prefix frontend
```

Open the local URL printed by Vite, normally `http://localhost:5173`.

### POSIX shell

Terminal 1:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```sh
npm ci --prefix frontend
npm run dev --prefix frontend
```

Open the local URL printed by Vite, normally `http://localhost:5173`.

For a single-process preview, run `npm run build --prefix frontend`, then start the API; FastAPI serves `frontend/dist` when that directory exists. The frontend uses the local API at `127.0.0.1:8000` during Vite development.

## Optional interfaces

The earlier Streamlit interface is optional. Install it only when you want to run it:

```sh
python -m pip install -e '.[streamlit]'
streamlit run app.py
```

## Assistant providers

The assistant runs deterministic local tools by default. To enable Cloud mode, install the optional OpenAI client with `python -m pip install -e '.[cloud]'`, configure `.env`, and restart the API. The provider key stays in the API process. The consent sheet names the provider, model, and host before sharing. Questions, assistant instructions, selected synthetic context, and local tool results go to that provider. Document excerpts are a separate opt-in. Free plans and hosted endpoints can log or retain prompts; read the provider's current terms and retention controls before use. Open-weight model weights can be free to download, while hosted inference can still cost money or have changing limits. TurbineIQ does not hardcode provider quota assumptions.

`TURBINEIQ_LLM_PROVIDER` selects `groq`, `cerebras`, `openrouter`, `ollama`, `openai`, or `custom`. The supplied `.env.example` starts with Groq's GPT-OSS 120B preset. Provider-specific keys are accepted (`GROQ_API_KEY`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY`, and `OPENAI_API_KEY`); `TURBINEIQ_LLM_API_KEY` takes precedence. Local Ollama does not require a key. Existing `OPENAI_API_KEY`, `TURBINEIQ_OPENAI_MODEL`, and `TURBINEIQ_OPENAI_BASE_URL` settings continue to work when the new provider selector is unset.

Examples for `.env`:

```dotenv
# Groq
TURBINEIQ_LLM_PROVIDER=groq
GROQ_API_KEY=your-key
TURBINEIQ_LLM_MODEL=openai/gpt-oss-120b
TURBINEIQ_LLM_BASE_URL=https://api.groq.com/openai/v1

# Cerebras: gpt-oss-120b is the documented preset.
# TURBINEIQ_LLM_PROVIDER=cerebras
# CEREBRAS_API_KEY=your-key
# TURBINEIQ_LLM_MODEL=gpt-oss-120b
# TURBINEIQ_LLM_BASE_URL=https://api.cerebras.ai/v1

# OpenRouter: use openai/gpt-oss-120b or openai/gpt-oss-20b.
# TURBINEIQ_LLM_PROVIDER=openrouter
# OPENROUTER_API_KEY=your-key
# TURBINEIQ_LLM_MODEL=openai/gpt-oss-20b
# TURBINEIQ_LLM_BASE_URL=https://openrouter.ai/api/v1

# Local Ollama: pull gpt-oss:20b before selecting Cloud mode.
# TURBINEIQ_LLM_PROVIDER=ollama
# TURBINEIQ_LLM_MODEL=gpt-oss:20b
# TURBINEIQ_LLM_BASE_URL=http://localhost:11434/v1

# OpenAI Responses API. This is a hosted OpenAI model, not GPT-OSS.
# TURBINEIQ_LLM_PROVIDER=openai
# OPENAI_API_KEY=your-key
# TURBINEIQ_LLM_MODEL=gpt-5.5

# Hugging Face Router/custom compatible endpoint.
# TURBINEIQ_LLM_PROVIDER=custom
# HF_TOKEN=your-token
# TURBINEIQ_LLM_MODEL=openai/gpt-oss-120b
# TURBINEIQ_LLM_BASE_URL=https://router.huggingface.co/v1
```

Timeout, answer size, and tool rounds can be adjusted with `TURBINEIQ_LLM_TIMEOUT_SECONDS`, `TURBINEIQ_LLM_MAX_TOKENS`, and `TURBINEIQ_LLM_MAX_TOOL_ROUNDS`. The tool-round value is capped at three. See [verified provider presets and caveats](docs/ASSISTANT_PROVIDERS.md) for current source links and model support notes.

Run a local fake evaluation with `python scripts/eval_assistant.py` or `python scripts/eval_assistant.py --fake`; this never contacts a provider and is suitable for CI. To intentionally evaluate the configured live provider, run `python scripts/eval_assistant.py --live`. This sends the synthetic evaluation questions and tool outputs to that provider and writes its report to `docs/evidence/`. Do not run the live evaluation with confidential data.

## Verify

Install the Streamlit extra as well as development tools because the Python suite includes tests for the optional Streamlit interface.

PowerShell:

```powershell
python -m pip install -e '.[dev,streamlit]'
ruff check src tests
python -m pytest -q
npm run lint --prefix frontend
npm run build --prefix frontend
npm run test --prefix frontend
npm run check:paths --prefix frontend
npm run test:e2e --prefix frontend
```

POSIX shell:

```sh
python -m pip install -e '.[dev,streamlit]'
ruff check src tests
python -m pytest -q
npm run lint --prefix frontend
npm run build --prefix frontend
npm run test --prefix frontend
npm run check:paths --prefix frontend
npm run test:e2e --prefix frontend
```

Install Chromium with `npx playwright install chromium`. The production E2E run starts a local API automatically. The cloud path is mocked in tests; tests do not need credentials. CI on Linux also installs system packages with `npx playwright install --with-deps chromium`.

## Blender asset

Rebuild the native Blender scene and GLB with Blender installed:

```sh
blender --background --python models/build_ge_6b03_reference.py
```

The exported geometry is a conceptual visualization, not a dimensionally accurate OEM assembly. Publicly sourced reference metadata and its limits are documented in [the public-data review](docs/GE_6B03_PUBLIC_DATA_REVIEW.md). The GLB compression pipeline and required extensions are described in [Blender model integration](docs/BLENDER_INTEGRATION.md).

## Project map

```text
src/turbineiq/engineering/   Simplified cycle calculations and validation
src/turbineiq/synthetic/     Seeded synthetic scenario generation
src/turbineiq/analytics/     Data-quality checks and residual screening
src/turbineiq/twin/          Synthetic-only state and replay data
src/turbineiq/rag/           Local document extraction and retrieval
src/turbineiq/agent/         Single-agent tools and optional cloud adapter
src/turbineiq/api/           Local FastAPI endpoints
src/turbineiq/ui/            Optional earlier Streamlit pages
frontend/src/app/            Hash router and shared reducer/context store
frontend/src/features/       Overview, component, evidence, assistant, and viewer
frontend/src/components/ui/  Shared Sheet and offline banner
frontend/src/lib/            Formatting, API helpers, and shared references
frontend/src/index.css       Design tokens, fonts, and global accessibility styles
docs/                        Scope, architecture, demo, integration, and design guidance
tests/                       Python unit and integration tests
```

For a guided walkthrough, see the [three-minute demo guide](docs/DEMO_GUIDE.md). The [architecture note](docs/ARCHITECTURE.md) describes data flow and frontend module boundaries. The [redesign index](docs/redesign/README.md) collects the direction, phase reports, contrast results, and final visual evidence.
