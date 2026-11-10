# Three-minute TurbineIQ demo

## Start the workspace

Install the Python development extra and frontend dependencies once. Start the API and frontend in separate terminals from the repository root.

PowerShell, terminal 1:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000
```

PowerShell, terminal 2:

```powershell
npm ci --prefix frontend
npm run dev --prefix frontend
```

POSIX shell, terminal 1:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000
```

POSIX shell, terminal 2:

```sh
npm ci --prefix frontend
npm run dev --prefix frontend
```

Open the Vite URL, normally `http://localhost:5173`. Keep Assistant in Local mode for the demo. The model, replay, analytics, and evidence retrieval run locally. No real plant is connected.

## Walkthrough

1. **Set the boundary — 15 seconds.** Point out the Synthetic label and explain that the simplified open-cycle model and generated records are illustrative; the workspace is not connected to a turbine.
2. **Show the replay and stage — 45 seconds.** On Overview, set the compressor-performance scenario and seed `42`, then scrub to sample 73. Show how the model reference, synthetic observation, residual, chart, station ledger, component ledger, and selected part update together. Use Reset, Explode, or Isolate to demonstrate the 3D stage.
3. **Explain a component — 40 seconds.** Select Compressor and review its live metrics, reference column, and provenance. Explain that the displayed residual and scenario label are generated comparison signals, not a fault diagnosis.
4. **Show cited evidence — 35 seconds.** Open Evidence, search for Brayton-cycle assumptions, and select a result to show its citation, source, section, and excerpt. The retrieval mode is local lexical search.
5. **Show the assistant — 45 seconds.** Open Assistant in Local mode and ask, “Explain the compressor-efficiency drift result.” Expand the tool trace to show the deterministic snapshot inspection. Cloud mode is optional and requires a separate consent action.

## Blender stage

The workspace already includes the project-authored Blender GLB at `frontend/public/models/turbine.glb`. The conceptual model is Meshopt-compressed and is loaded with the local decoder bundled in the existing viewer dependencies. The stage also offers an interactive schematic fallback. See [Blender model integration](BLENDER_INTEGRATION.md) for component mapping, compression, and export review.

## If time is short

Show Overview with the sample scrubber and compressor selection, then open Assistant and expand its tool trace. This demonstrates the live synthetic comparison, linked 3D selection, and local deterministic orchestration in under one minute.
