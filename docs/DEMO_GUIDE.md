# Three-minute TurbineIQ demo

## Start the browser workspace

From the repository root, install once and run the local API and frontend in separate terminals:

```powershell
python -m pip install -e ".[dev,cloud]"
cd frontend
npm install
npm run dev
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000
```

Open the Vite URL, normally `http://localhost:5173`. The engineering model, scenario generator, analytics, and RAG stay local. Keep the assistant cloud option off for the meeting demo. The older Streamlit interface remains available with `streamlit run app.py`.

## Walkthrough

1. **Establish the boundary — 15 seconds.** Show the synthetic replay badge and identify the single-shaft open-cycle model as a simplified, non-OEM model. No physical turbine is connected.
2. **Show the model/data comparison — 45 seconds.** Point to reference model, synthetic plant truth, generated observation, residual, and the 96-sample timeline. Scrub to sample 73 at seed 42; the timeline, chart, and component inspector update together.
3. **Explain one component — 45 seconds.** Select the compressor. Show the 81.2% synthetic efficiency parameter against the fixed 85.0% reference, along with discharge temperature and compressor power. Explain that these values come from generated model states and do not establish a fault diagnosis.
4. **Show evidence — 35 seconds.** Open **Evidence & assistant**. Search the local notes for Brayton-cycle assumptions and point to the cited sections and explicit model limitations.
5. **Show the data-aware assistant — 40 seconds.** Ask “Explain the compressor-efficiency drift result.” Keep cloud mode off. The answer uses the server-recomputed scenario, seed, selected sample, and component; expand the tool trace to show the deterministic snapshot inspection call.

## Blender model

No turbine `.blend` or `.glb` asset was present in the project or workspace during this implementation. The 3D view is currently an interactive component geometry scaffold. When an export is ready, load it with **Load GLB**, or copy it to `frontend/public/models/turbine.glb` for local development auto-load. See [Blender model integration](BLENDER_INTEGRATION.md) for component IDs and export guidance. The model remains local to the browser/workspace.

## Expected result

With seed 42 and the compressor-performance drift scenario, sample 73 presents a generated efficiency value around 81.2% against an 85.0% reference. Output residuals are calculated from generated plant-model output plus seeded measurement noise compared with a fixed reference-model output. The local robust screen can remain unflagged at that sample; the scenario perturbation label and statistical screen are separate signals. The assistant repeats provenance and the no-diagnosis boundary.

## If time is short

Show the workbench values and compressor state, then open the assistant and expand its tool trace. That demonstrates the model comparison, component-linked context, deterministic orchestration, and synthetic-only boundary in under one minute.
