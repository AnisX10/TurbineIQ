# TurbineIQ browser workspace

This React/TypeScript app is the interactive presentation layer for the local TurbineIQ Python engine. It uses React Three Fiber for the turbine scene and proxies `/api` requests to FastAPI during development.

From the repository root, install dependencies and launch both processes in separate terminals:

```powershell
python -m pip install -e ".[dev,cloud]"
cd frontend
npm install
npm run dev
```

```powershell
.\.venv\Scripts\python.exe -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000
```

Run `npm run lint` and `npm run build` before handing off UI changes. For the optional Blender export path, component IDs, and GLB details, see [`../docs/BLENDER_INTEGRATION.md`](../docs/BLENDER_INTEGRATION.md).
