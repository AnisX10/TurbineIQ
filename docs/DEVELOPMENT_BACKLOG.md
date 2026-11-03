# Prioritized MVP backlog

The original MVP milestones, synthetic twin, and local React/API workspace are implemented. The counts below are focused checks recorded during development; the final combined suite is recorded below.

1. **Complete — repository audit and project foundation** — new local Git repository, package, scope boundaries, test runner, research record, and reproducible setup. Focused check: 1 passed.
2. **Complete — engineering core** — validated single-shaft open-cycle solver; state points, component work, heat input, fuel flow, shaft/electrical power, and efficiency. Focused check: 11 passed.
3. **Complete — synthetic scenarios** — fixed-seed baseline, warmer-ambient, compressor-performance perturbation, and sensor-fault cases; all generated rows labeled synthetic. Focused check: 19 passed.
4. **Complete — data quality and analytics** — schema/completeness, duplicate/time-order, physical-value, flat-line checks, and explainable robust residual flags. Focused check: 25 passed.
5. **Complete — technical-document retrieval** — local Markdown/TXT/PDF ingestion, chunk metadata, retrieval, and source/page/section citations. Focused check: 36 passed.
6. **Complete — single-agent orchestration** — allow-listed tools around deterministic functions; optional cloud tool-calling with bounded rounds and validated arguments. Focused check: 45 passed.
7. **Complete — offline synthetic digital twin** — time-selected synthetic asset state, model/observation comparison, residual screen, provenance, and export; no physical asset connection. Focused check: 5 passed.
8. **Complete — Streamlit UI** — cycle explorer, scenario and quality explorer, synthetic twin, local document Q&A, and assistant.
9. **Complete — integration, tests, and documentation** — setup guide, scope, architecture, supplemental digital-twin research, privacy boundaries, and demo guide. Original MVP checkpoint: 56 passed.
10. **Complete — interactive browser workspace** — local FastAPI endpoints, React/TypeScript workbench, Three.js component selection, time-aligned output chart, local cited evidence, and selected-snapshot assistant context. Browser lint/build pass; final Python suite: 66 passed. A Blender GLB can be loaded locally when available; the workspace currently uses an interactive geometry scaffold.

## Acceptance target

From a clean install, the browser app and local API start, run deterministic engineering calculations, display a synthetic asset state aligned to a reproducible scenario, show reference/plant/observed output and an explainable residual result, retrieve cited document passages, and explain the selected sample without cloud access. Cloud mode is optional and was not exercised against a live provider during local verification.

