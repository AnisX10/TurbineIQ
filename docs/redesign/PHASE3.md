# Phase 3 Overview report

## Delivered Overview

The Overview route is driven by the existing API response and one reducer/context store. The filter row groups Scenario, Seed, Sample and Interval; invalid seed input stays inline and preserves the last successful run. Four ledger-style KPIs show live reference, observation, residual and flagged-sample values. Residual sign and direction are explicit.

The Stage card uses the local Blender GLB and interactive schematic, with camera reset, explode, isolate and opt-in rotor motion. Reduced-motion preference disables rotor motion. The Station ledger reads existing temperature and ambient-pressure fields. Component selection synchronizes the station pair, component row, GLB highlight, inspector and URL. The mesh picker is portalled into the Component ledger while retaining its existing Viewer state.

The Component ledger shows the six existing component IDs, live metrics and provenance, selected-component metrics, and the published 6B.03 block with its caveat. The SVG TimelineChart uses ResizeObserver, a unit-bearing y-axis, direct series labels, reference/observation/truth lines, residual strip, playhead/readout, table view and a factual trend sentence. Playback and scrubbing update the KPIs, Stage, ledgers, chart and URL from one state.

Loading/error states reserve dimensions; the offline banner contains the API start command; failed requests expose retry; and GLB failure falls back to a visible interactive schematic. The 320px page has no horizontal scroll and the mobile bar reserves the safe area.

## Phase 3 gates

| Gate | Command or evidence | Result |
|---|---|---|
| Production build | cd frontend; npm run build and the build within npm run test:e2e | Pass. Main JS 276.98 kB/85.22 kB gzip; Viewer 1,025.15/274.18 kB; CSS 33.07/6.99 kB; HTML 1.31/0.55 kB. Vite retains its >500 kB Viewer advisory. [Log](phase3/logs/build.txt) |
| Unit tests | cd frontend; npm test | 3 files, 11 passed. [Log](phase2/logs/vitest.txt) |
| Browser tests | cd frontend; npm run test:e2e | 7 passed on production build. Includes axe, keyboard, interactions, network log, screenshots, 320px reflow, reduced motion and 44px touch targets. [Log](phase2/logs/playwright.txt) |
| Axe | Overview light and dark; full suite covers all four routes/themes | Zero serious/critical issues. [Results](phase2/axe-results.json) |
| Contrast | python docs/redesign/contrast_check.py | All 40 light/dark pairs pass, including strong controls, chart-2, status text and stage edge. [Output](phase3/contrast-check.txt) |
| Taste lint | lint.mjs --app --json over 23 changed frontend files | Zero FAIL; 18 WARN for engineering monospace and actual overlay shadows. Mono justification is recorded once in DIRECTION.md. Raw lint output was pruned after its result was summarized here. |
| Taste inspect | inspect.mjs --app --widths 1440,1024,768,375 on all routes | Zero FAIL on Overview, Components, Evidence and Assistant. Overview colour share: 0.1%, 0.2%, 0.2%, 0.2%, within the <1% budget. Raw inspector output and screenshot matrices were pruned after their results were summarized here. |
| Keyboard-only replay | Playwright replay keyboard map | Left/Right, Shift+Left/Right, Home/End, Space, F, no-flag disabled behavior, accessible sample value and URL sync pass. |
| Network | Playwright request-origin collection | Only http://127.0.0.1:8011; no CDN or other origin. |
| Viewports | Both-theme screenshots at 375/768/1024/1440 and separate 320px overflow assertion | Pass. Screenshot test waits for GLB mesh catalog so the loaded model is consistent at each size. The old screenshot matrix was pruned; the viewport results remain summarized here and the captures can be recovered from the archive commit in the [redesign index](README.md). |
| Python regression | ruff check src tests; .venv\Scripts\python.exe -m pytest -q | Ruff passes; 69 passed, 5 dependency deprecation warnings. Logs are in phase2/logs/. |
| Lighthouse | Lighthouse 13.6.0, three sequential production runs per preset | CLS passes: 0.023 mobile, 0.056 desktop. Mobile performance median 47 vs baseline 51 (inside the stated five-point noise). Desktop median 74 vs baseline 80 (six points lower, one beyond noise); **desktop performance gate is not passed**. Run summaries are preserved in the tables above; raw JSON was pruned and can be recovered from the archive commit in the [redesign index](README.md). |
| Total payload | Lighthouse total byte weight | 4,026,243 bytes vs 3,939,199 baseline, +87,044 bytes (2.2%). |

### Production bundle comparison with Phase 0

| Asset | Phase 0 minified / gzip | Phase 3 minified / gzip |
|---|---:|---:|
| Main JavaScript | 249.72 / 78.22 kB | 276.98 / 85.22 kB |
| Lazy Viewer JavaScript | 1,023.83 / 273.77 kB | 1,025.15 / 274.18 kB |
| CSS | 25.86 / 5.70 kB | 33.07 / 6.99 kB |
| HTML | 0.56 / 0.34 kB | 1.31 / 0.55 kB |
| Total | 1,299.97 / 358.03 kB | 1,336.51 / 366.94 kB |

Desktop performance ranged 67-75 across the three runs, a wider spread than the approximately five-point Phase 0 noise. The desktop median remains a gate miss. Mobile LCP is also substantially slower than Phase 0: median 12.544 s vs 3.3 s. The large Viewer module and first API-backed render are visible contributors. The full Viewer split remains deferred to Phase 5; remeasure on a quieter machine and address initial-render cost before signing off desktop performance.

## UI/UX Pro Max pre-delivery checklist

- **Accessibility and contrast:** axe covers four routes in light and dark with zero serious/critical findings. The contrast script measures 40 token/state pairs. Icon controls have names/state; BoundarySheet focus entry, trap, Escape and focus return pass. Evidence: phase2/axe-results.json, phase3/contrast-check.txt and phase2/logs/playwright.txt.
- **Touch and interaction:** Playwright measures navigation, filters, Stage controls, replay, chart controls and icon actions at 44px or larger. Scenario, invalid seed, replay, part selection, Evidence search, local Assistant and keyboard map pass.
- **Responsive and safe areas:** both-theme screenshots at 375, 768, 1024 and 1440px; no overflow at 320px; 812x375 landscape passes; mobile bar uses safe-area-inset-bottom.
- **Motion:** reduced-motion emulation disables rotor motion; rotor is opt-in and visual only.
- **Visual system:** no emoji icons; Lucide outline icons, local Geist fonts and semantic theme tokens; neutral active rail and flat surfaces; stable selected-row border; Overview colour share below 1%. Geist Mono is justified once in DIRECTION.md.
- **Data/charts:** live API values and units; missing values use a dash; zero remains zero; residual sign and direction accompany color; series have direct labels and a table alternative.
- **Native checks:** Dynamic Type and authentication are native-app-only and do not apply. Browser reflow is tested at 320px and the planned widths; a separate browser zoom-control test was not run.

## Deviations and TurbineViewer change log

- Selected component is serialized as component= on Overview in addition to scenario, seed and i; no API change.
- Published 6B.03 catalogue values are not in the API payload. A shared cited local constant serves the Boundary sheet and inspector; synthetic outputs are not presented as OEM operating data.
- The initial 768px color-share measurement was 1.4%. To meet the <1% budget, selected-mesh emissive intensity changed from 0.48 to 0.22 and selected-component intensity from 0.16 to 0.08. Final measured share is 0.2%. No CSS saturation filter was retained.
- Added a stage-token context and MutationObserver/matchMedia listeners; schematic and GLB materials reread background, part, edge and selected tones when theme preference changes.
- Moved GLB/Schematic, reset camera, explode, isolate and rotor actions into the Stage toolbar within the card. Rotor remains opt-in and disabled under reduced motion.
- Moved the mesh picker into the Component ledger through the partPickerHost portal. The existing Viewer public props, component IDs and model IDs remain.
- Added an accessible Canvas name/interaction description and a visible status note on GLB failure. Did not change ambient, directional or point-light intensity; screenshots showed the light-stage metal detail was not washed out.
- Did not split the Viewer module, change the GLB asset/contract, add runtime packages, change API/types, or start Phase 4/5.

The app remains synthetic-only and local: no real-time industrial connectivity, DCS/SCADA/PLC control, or confidential FieldCore material.

## Phase 3 performance finding closure

The Phase 3 mobile and desktop LCP regressions and desktop performance miss recorded above were rechecked after Phase 4's Stage-frame correction. The Stage heading, toolbar, reserved 4:3 viewport, preview and interaction note now render in the main bundle. Only the Canvas and `TurbineViewer` are lazy-loaded; the Canvas starts after the Stage is active and a 700 ms delay, with the schematic preview visible meanwhile.

Three final Lighthouse runs per preset report mobile performance 68/69/70 (median 69), LCP 1.075/1.078/1.084 s (median 1.078 s), CLS 0.0373, and desktop performance 76/76/75 (median 76), LCP 0.330/0.301/0.310 s (median 0.310 s), CLS 0.0132. The desktop performance median is 4 points below the Phase 0 median of 80, within the 5-point noise allowance. Both LCP limits and the CLS limit pass. The independent LCP probe identifies the static Stage interaction note on mobile and the Component ledger heading on desktop; neither is inside the lazy Canvas. Run tables remain in [PHASE4.md](PHASE4.md); the raw Lighthouse JSON was pruned and is recoverable from the archive commit listed in the [redesign index](README.md).

The 3D chunk remains large and mobile total-blocking time is still high. This closes the requested Phase 3 finding without splitting the full viewer, changing the GLB, or changing the API.
