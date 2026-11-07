# Phase 4 delivery report

**Date:** 2026-11-05
**Branch:** `redesign/v2`
**Scope:** Phase 3 finding closure, then Phase 4 Component detail, Evidence and Assistant. Phase 5 was not started.

## Delivered

### Phase 3 finding closure

- The Stage frame, heading, toolbar, reserved 4:3 viewport, schematic preview and interaction note render immediately. Only the Canvas and `TurbineViewer` are lazy; loading the GLB no longer gates the Stage text. The Canvas mounts after activation and a 700 ms delay while the preview remains visible.
- The compressor efficiency is formatted as a percentage. Temperatures are presented in kelvin, with original Celsius retained in provenance. Units use separate spans and missing references keep the unit with the em dash.
- Status labels wrap instead of truncating. Station rows use a fixed Synthetic / Reference model / Note grid. The Stage view switch is segmented; Reset, Explode, Isolate and Rotor controls are named icon buttons with keyboard access and 44 px targets.
- Timeline labels are separated, the residual strip has a zero line and scale, the playhead readout stays with the playhead, and the replay scrubber uses a neutral fill.
- Overview is split into `features/overview/` modules. Component detail is in `features/component-detail/`.
- Dark-stage lighting now uses theme-specific values: ambient 0.8 → 4, key 2.1 → 7, fill 9 → 32, rim 4 → 24. Light-stage values are unchanged. The original Phase 4 before/after capture pair was pruned with the old screenshot matrices; the later Stage review is preserved in [Phase 5](phase5/stage-after-dark.png).

### Phase 4 routes

- **Component detail:** breadcrumb and neutral synthetic label; Metrics, Over time and Evidence tabs with keyboard navigation; live metric ledger and provenance; two sample-window charts where the payload has a series; honest empty state where it does not; component-seeded Evidence search.
- **Evidence:** local lexical retrieval, URL-restored query and `top_k`, sorted relevance rows and plain-text excerpt reader. The no-result message states the exact query and retrieval mode.
- **Assistant:** Local is the default demo-safe mode; context chips reflect server-recomputed scenario, seed, sample and component. Answers retain expandable tool traces. Cloud is gated by a consent sheet that lists sent data; excerpts are opt-in. Browser tests mock cloud responses and never use a key. API warnings and local fallback are shown neutrally.
- The new screens preserve retry, offline, empty, invalid-input, loading and reduced-motion behavior. The offline state presents the exact local start command: `\.venv\Scripts\python.exe -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000`. Excerpts render as text, never HTML.
- Removed `LegacyWorkspace`, `PowerChart.tsx`, and migrated legacy CSS. Evidence and Assistant search state is represented in the URL. No backend, Python API, `frontend/src/types.ts`, component ID, GLB asset or GLB contract changed; no runtime dependency or external request was added.

## Gates and evidence

| Gate | Command / result | Evidence |
|---|---|---|
| Production build | `cd frontend; npm run build` — pass. Main JS 300.48 kB / 91.15 kB gzip; viewer 1,023.05 / 273.66; CSS 49.95 / 9.35; HTML 1.31 / 0.55. Vite's existing >500 kB viewer-chunk advisory remains. | [`build.txt`](phase4/build.txt) |
| Frontend lint | `cd frontend; npm run lint` — pass, exit 0. | [`npm-lint.txt`](phase4/npm-lint.txt) |
| Vitest | `cd frontend; npm test` — 3 files, 14 tests passed. | [`vitest.txt`](phase4/vitest.txt) |
| Playwright | `cd frontend; npm run test:e2e` builds production then runs 9 tests — all passed. Covers initial Stage paint, routes, interactions, URL restoration, mocked cloud/consent, retry, screenshot matrix, 320 px overflow and reduced motion. | [`e2e-command.log`](phase4/e2e-command.log) |
| Axe | 14 route/tab/consent states across light and dark; zero serious or critical violations. | [`axe-results.json`](phase4/axe-results.json), E2E log above |
| Keyboard | Tabs, Evidence list, consent sheet, composer, and replay keyboard map passed. Replay includes arrows, Shift+arrows, Home/End, Space and first-flagged behavior. | E2E log above |
| Network | Only the local app/API origin `http://127.0.0.1:8011`; zero other-origin requests. Cloud is intercepted and mocked. | [`network-origins.json`](phase4/network-origins.json) |
| Taste lint | `lint.mjs --json` on changed app files — 0 FAIL, 20 WARN across 55 files. Warnings: engineering mono (13 uses), real overlay shadows (6), required missing-data em dash (1). Mono justification is recorded once in DIRECTION.md. Raw lint output was pruned after its result was summarized here. |
| Taste inspect | `inspect.mjs --app --widths 1440,1024,768,375` on Overview, Component detail, Evidence and Assistant — zero FAIL. Colour share is 0–0.2% at every route/width. Six advisory warnings remain: compact labels, natural Stage/ledger height, and blank space when the Evidence result list is short. Raw inspector output and the screenshot matrix were pruned after this summary. |
| Contrast | `python docs/redesign/contrast_check.py` — all 44 measured token/state pairs pass, including control, chart, status text and stage edge in both themes. | [`contrast-check.txt`](phase4/contrast-check.txt) |
| Python checks | `ruff check src tests` passes; `python -m pytest -q` passes 69 tests, with 5 existing dependency deprecation warnings. | [`ruff.txt`](phase4/ruff.txt), [`pytest.txt`](phase4/pytest.txt) |
| Protected source | Python source/tests, frontend types and GLB compare byte-identical to `main`. | [`source-equivalence.txt`](phase4/source-equivalence.txt) |
| Responsive screenshots | Viewport captures at 375, 768, 1024 and 1440 px for all four routes in both themes (32 images). Captures are viewport-by-viewport, so the fixed mobile bar does not obscure a claimed full-page capture. No horizontal scroll at 320 px. | The intermediate image matrix was pruned; summary and recovery location are recorded in the [redesign index](README.md). |

### Lighthouse

Lighthouse 13.6.0, three production runs per preset. The mobile command used `--only-categories=performance --form-factor=mobile`; desktop used `--only-categories=performance --preset=desktop`. Both used headless Chrome against the local production preview with background networking and component updates disabled. The LCP element probe is separate from the throttled Lighthouse run and confirms that the largest first-paint candidates are outside the lazy Canvas.

| Preset | Run | Performance | LCP | CLS | TBT | Payload |
|---|---:|---:|---:|---:|---:|---:|
| Mobile | 1 | 68 | 1.075 s | 0.0373 | 3,601 ms | 3,969 KiB |
| Mobile | 2 | 69 | 1.078 s | 0.0373 | 3,260 ms | 3,969 KiB |
| Mobile | 3 | 70 | 1.084 s | 0.0373 | 3,234 ms | 3,969 KiB |
| **Mobile median** |  | **69** | **1.078 s** | **0.0373** | **3,260 ms** | **3,969 KiB** |
| Desktop | 1 | 76 | 0.330 s | 0.0132 | 573 ms | 3,969 KiB |
| Desktop | 2 | 76 | 0.301 s | 0.0133 | 602 ms | 3,969 KiB |
| Desktop | 3 | 75 | 0.310 s | 0.0132 | 643 ms | 3,969 KiB |
| **Desktop median** |  | **76** | **0.310 s** | **0.0132** | **602 ms** | **3,969 KiB** |

The mobile and desktop LCP targets (≤4 s / ≤1 s) and CLS target (≤0.1) pass. Desktop performance is 76 versus the Phase 0 median of 80, 4 points lower and inside the documented 5-point run-to-run allowance. Phase 3 medians were mobile 47 / 12.544 s LCP and desktop 74 / 2.171 s LCP. The three-run summary is preserved in the table above; raw Lighthouse JSON was pruned. The separate no-throttle probe observed `.viewer-note` at 0.260 s on mobile and `h2 Component ledger` at 0.144 s on desktop. Probe implementation and element record: [`lcp-probe.mjs`](../../frontend/e2e/lcp-probe.mjs), [`lcp-elements.json`](phase4/lcp-elements.json).

### Production bundle comparison

| Asset | Phase 2 minified / gzip | Phase 4 minified / gzip |
|---|---:|---:|
| Main JS | 276.98 / 85.22 kB | 300.48 / 91.15 kB |
| Viewer JS | 1,025.15 / 274.18 kB | 1,023.05 / 273.66 kB |
| CSS | 33.07 / 6.99 kB | 49.95 / 9.35 kB |
| HTML | 1.34 / 0.56 kB | 1.31 / 0.56 kB |
| **Total** | **1,336.54 / 366.95 kB** | **1,374.78 / 374.72 kB** |

Phase 4 adds 38.24 kB minified / 7.77 kB gzip (2.86% / 2.12%). Phase 2 figures were captured by building commit `9622e81` in a temporary worktree; the side-by-side totals are recorded here.

## Plan and DIRECTION decisions

No DIRECTION.md requirement was overridden. The 700 ms Stage activation delay is the progressive Canvas scheduling chosen to close the measured LCP regression; the static frame and schematic remain visible while it loads. The large Viewer chunk and GLB remain unchanged because full Viewer splitting is Phase 5 work and compression would add GLB extensions.

### TurbineViewer change log

- Lifted Stage view, explode, isolate, rotor and camera-reset state to `StageCard`; `TurbineViewer` now accepts those values and the model status callback as props. The controls live in the Stage toolbar.
- Lazy-loaded `TurbineViewer`/Canvas from `StageCard` after activation; the Stage frame and instruction note are main-bundle content. The viewer still progressively fetches and loads the same local GLB.
- Added a failure state when the local GLB request fails and retained the interactive schematic fallback. The status callback reports loading/failure to the Stage frame.
- Portalled the sub-mesh picker into the Component ledger and part-inspection details into the Stage info slot. Light-stage lighting is unchanged; dark-stage values are listed above and the material tokens continue to follow theme changes.
- No mesh names, component IDs, GLB contract, source asset, or public Viewer geometry metadata were changed.

## Offline GLB compression trial

The `meshopt` trial reduced the 1,910,712-byte source to 842,968 bytes (55.9% smaller). RGB mean absolute difference was 0.05158/255; only 0.06256% of pixels differed by more than 5 levels. The trial adds `EXT_meshopt_compression` and `KHR_mesh_quantization`. The GLB remains untouched; details and renders are in [`meshopt-evaluation.md`](phase4/meshopt-evaluation.md).

## Limitations and verification boundary

- The viewer remains a roughly 1 MB minified lazy chunk; mobile TBT median is 3.26 s. The LCP correction meets the requested limits, but further bundle and interaction-cost work remains valuable.
- Taste warnings are advisories, not hidden failures. Compact engineering sublines/axis ticks stay at 11–12 px; Evidence panels keep equal columns and can show spare space for short result lists.
- The cloud path was tested only through mocked provider responses. No credential or real cloud model was used. No OEM operating data or confidential FieldCore material was introduced.
- No Phase 5 work was started. The GLB compression trial was not adopted.

## Follow-up closure in Phase 5 Part A

The Phase 4 follow-up commit supersedes the initial Stage's fixed 700 ms Canvas activation, portable engine-offline guidance, component ledger formatting, and custom Cloud consent panel described above. Canvas activation is now gated by Stage visibility and browser idle time, and Boundary and Cloud consent share the native Sheet. The Assistant progress rule no longer renders while idle. The follow-up tests and requested state screenshots are documented in [`phase5/part-a-followups.md`](phase5/part-a-followups.md).
