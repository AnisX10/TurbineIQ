# Phase 5: 3D Stage

Phase 5 is complete on `redesign/v2`. Part A was committed before the Phase 5 viewer work. The approved high-level Meshopt conversion was applied in B6; the original asset remains recoverable from Git history. No Python source or test, backend API, frontend API type, component ID, or mesh-name contract changed.

## Changes

- Part A: fixed the Assistant busy rule and scenario display name; standardized offline startup guidance; corrected component metric formatting; delayed Canvas activation until the Stage is visible and the browser is idle; shared a native dialog Sheet; captured the requested nine UI states at 1440 and 375 px in both themes. Evidence is in [`phase5/part-a-followups.md`](phase5/part-a-followups.md) and [`phase5/states/`](phase5/states/).
- B1: split the viewer into `TurbineViewer`, `GLBModel`, `SchematicTurbine`, `selection`, `camera`, `stageTokens`, `lights`, and `ModelBoundary` modules. The public viewer props, mesh names, six component IDs, and selection behavior remain the same.
- B2–B4: added selected-mesh outlines and callouts, 240 ms reduced-motion-aware camera easing, the 2× DPR cap, demand rendering, and invalidation for user interactions and rotor motion. The camera does not auto-rotate; rotor motion is opt-in.
- Runtime correction: the Drei callout now mounts into a stable Stage-owned HTML overlay. The prior Canvas event target produced a React `removeChild` exception during viewer initialization. The responsive runtime probe now has no page errors, and the selected label remains visible in light and dark.
- B5: split Component detail, Evidence, and Assistant into lazy route chunks with a dimensioned loading state. This reduces the initial route work while preserving the shell and Overview first paint.
- B6: applied the approved Meshopt high-level compression to `turbine.glb`. The existing local Meshopt decoder is used, and Draco loading is explicitly disabled for this asset.

## Lighthouse

Lighthouse 13.6.0 ran three times per preset against the local production build. The mobile and desktop run values and medians are preserved in the tables below; raw JSON reports were pruned during the documentation cleanup to keep the docs folder within its size budget. The medians compare with the Phase 0 baseline in [`BASELINE.md`](BASELINE.md) and the Phase 4 results in [`PHASE4.md`](PHASE4.md). The CLI command logs remain in [`phase5/lighthouse/`](phase5/lighthouse/).

| Preset | Runs: Performance | Median Performance | Runs: LCP | Median LCP | Median CLS | Runs: TBT | Median TBT | Median payload |
|---|---|---:|---|---:|---:|---|---:|---:|
| Mobile | 72, 71, 72 | 72 | 916, 922, 915 ms | 916 ms | 0.0374 | 1,448, 2,039, 1,579 ms | 1,579 ms | 2,915 KiB |
| Desktop | 96, 95, 96 | 96 | 258, 258, 262 ms | 258 ms | 0.0136 | 161, 182, 161 ms | 161 ms | 2,915 KiB |

| Preset | Measure | Phase 0 | Phase 4 | Phase 5 |
|---|---|---:|---:|---:|
| Mobile | Performance | 51 | 69 | 72 |
| Mobile | LCP | 3.3 s | 1.078 s | 0.916 s |
| Mobile | CLS | 0.274 | 0.0373 | 0.0374 |
| Mobile | TBT | 1,650 ms | 3,260 ms | 1,579 ms |
| Mobile | Payload | 3,847 KiB | 3,969 KiB | 2,915 KiB |
| Desktop | Performance | 80 | 76 | 96 |
| Desktop | LCP | 0.7 s | 0.310 s | 0.258 s |
| Desktop | CLS | 0.034 | 0.0132 | 0.0136 |
| Desktop | TBT | 450 ms | 602 ms | 161 ms |
| Desktop | Payload | 3,847 KiB | 3,969 KiB | 2,915 KiB |

Mobile TBT meets the 2,000 ms median target. One run measured 2,039 ms; the observed run range was 1,448–2,039 ms. The median mobile main-thread breakdown was 2,862 ms script evaluation, 347 ms other work, and 193 ms style/layout. The five longest tasks were 561, 369, 302, 298, and 229 ms. Performance medians are 21 points above Phase 0 on mobile and 16 points above Phase 0 on desktop; both differences exceed the roughly five-point run-to-run variation noted in the baseline.

The three mobile commands used `npx --yes lighthouse@13.6.0 http://127.0.0.1:8011/#/overview?scenario=compressor_fouling&seed=42&i=72 --only-categories=performance --form-factor=mobile --chrome-flags="--headless --disable-background-networking --disable-component-update --no-sandbox" --output=json --output-path=<run>.json --quiet`. Desktop used the same command with `--preset=desktop` in place of `--form-factor=mobile`. The six CLI invocations are retained as `final-mobile-{1,2,3}-cli.log` and `final-desktop-{1,2,3}-cli.log` in [`phase5/lighthouse/`](phase5/lighthouse/); the JSON artifacts were removed.

The mobile LCP element probe reported `.viewer-note` at 476 ms; desktop reported `h2 Component ledger` at 192 ms. These unthrottled element observations are recorded in [`phase5/lcp-elements.json`](phase5/lcp-elements.json); the Lighthouse LCP medians above are measured under their respective preset throttling. Both LCP targets and both CLS targets pass.

Total Lighthouse payload is 1,054 KiB lower than Phase 4 (3,969 KiB) and 932 KiB lower than Phase 0 (3,847 KiB). The production bundle still reports Vite's advisory for the 1,039.67 kB minified viewer chunk. The Overview entry chunk is 274.73 kB minified (84.72 kB gzip); route screens are separate lazy chunks. The minified build details and warning are in [`phase5/final-build.log`](phase5/final-build.log).

## Meshopt result

The approved conversion reduced `frontend/public/models/turbine.glb` from 1,910,712 to 842,968 bytes (55.9%). Before and after node, mesh, material, and animation names and counts match: 328 nodes, 320 meshes, 8 materials, and 0 animations. The ordered dumps and contract diff are [`glb-structure-before.json`](phase5/glb-structure-before.json), [`glb-structure-after.json`](phase5/glb-structure-after.json), and [`glb-structure-diff.txt`](phase5/glb-structure-diff.txt). At the paired view, the mean absolute RGB difference was 0.051845/255 in light and 0.047056/255 in dark; fewer than 0.16% of pixels differed by more than 5 levels in either theme.

`gltf-transform validate` reported no errors. It warned that it cannot validate `EXT_meshopt_compression` and that a buffer may be unused. The production viewer loaded the compressed model using Drei's existing `three-stdlib` Meshopt decoder. The unchanged Blender asset test passed 3/3. The screenshot comparison is documented in [`glb-pipeline.md`](glb-pipeline.md); light/dark renders and difference images are in [`phase5/`](phase5/).

## Gates and evidence

| Gate | Command and result | Evidence |
|---|---|---|
| Taste-skill lint | `node <home>/.codex/skills/design-taste-frontend/scripts/lint.mjs --app <changed files>` — 0 failures, 6 advisory warnings. Four shadow warnings are for actual overlays/sheets/menus; the two mono warnings are reference values in the Boundary sheet. | [`phase5/final-taste-lint.log`](phase5/final-taste-lint.log) |
| Taste-skill inspect | Ran `node <home>/.codex/skills/design-taste-frontend/scripts/inspect.mjs <route> --app --out <dir> --widths 1440,1024,768,375 --json` for Overview and Components — no horizontal overflow, browser errors, or broken images at any width. Maximum measured colour share is 0.4%. | [`phase5/taste-inspect/overview-report.json`](phase5/taste-inspect/overview-report.json), [`phase5/taste-inspect/components-report.json`](phase5/taste-inspect/components-report.json), and route screenshots below `phase5/taste-inspect/` |
| Build | `npm run build --prefix frontend` — passed. Vite retains its >500 kB viewer-chunk advisory. | [`phase5/final-build.log`](phase5/final-build.log) |
| Frontend lint | `npm run lint --prefix frontend` — passed. | [`phase5/final-lint.log`](phase5/final-lint.log) |
| Vitest | `npm run test --prefix frontend` — 18 tests passed across 4 files. | [`phase5/final-vitest.log`](phase5/final-vitest.log) |
| Playwright, axe, and keyboard | `npm run test:e2e --prefix frontend` — 16 tests passed. Axe found zero serious or critical findings on all four routes, Component tabs, Boundary sheet, and Cloud consent in both themes. Keyboard coverage includes each viewer action, mesh selection, menus, dialogs, tabs, replay keys, and composer. Cloud behavior is mocked and tests do not use keys. | [`phase5/final-playwright.log`](phase5/final-playwright.log), [`phase5/final-playwright-results.json`](phase5/final-playwright-results.json), [`phase5/final-axe-results.json`](phase5/final-axe-results.json) |
| Network origins | Playwright records only `http://127.0.0.1:8011`; the application made no other-origin request. | [`phase5/viewer-network-origins.json`](phase5/viewer-network-origins.json), [`phase5/final-network-origins.json`](phase5/final-network-origins.json) |
| Demand-render probe | Playwright observed no draws while idle, draws during camera easing and opt-in rotor motion, then no draws after motion settled or stopped. Reduced-motion coverage passed. | [`phase5/final-playwright.log`](phase5/final-playwright.log), test `demand rendering stops while idle...` in [`phase5/final-playwright-results.json`](phase5/final-playwright-results.json) |
| Responsive runtime probe | Playwright loaded the real GLB and resized through 1024, 768, 375, and 1440 px with no page or console errors (the browser's `/favicon.ico` 404 is excluded from the runtime assertion). | [`phase5/responsive-runtime-errors.json`](phase5/responsive-runtime-errors.json), [`phase5/final-playwright.log`](phase5/final-playwright.log) |
| LCP element | `node e2e/lcp-probe.mjs` — mobile `.viewer-note`, desktop `h2 Component ledger`. Lighthouse medians are listed above. | [`phase5/lcp-elements.json`](phase5/lcp-elements.json), [`phase5/lcp-probe-final.log`](phase5/lcp-probe-final.log), and the six invocation logs in [`phase5/lighthouse/`](phase5/lighthouse/) |
| Python quality | `.venv\Scripts\python.exe -m ruff check src tests` — passed. `.venv\Scripts\python.exe -m pytest -q` — 69 passed, 5 dependency warnings. | [`phase5/final-ruff.log`](phase5/final-ruff.log), [`phase5/final-pytest.log`](phase5/final-pytest.log) |
| Source invariants | `git diff --quiet main -- src tests` and `git diff --quiet main -- frontend/src/types.ts` — both exit 0. | [`phase5/python-byte-identical.log`](phase5/python-byte-identical.log) |
| Blender asset contract | Unchanged `tests/test_blender_asset.py` — 3 passed. Mesh-name/count comparison is identical. | [`phase5/glb-blender-test.log`](phase5/glb-blender-test.log), [`phase5/glb-structure-diff.txt`](phase5/glb-structure-diff.txt) |
| Stage screenshots | Before/after light and dark at the same 1440 px viewport; selection outline and callout remain visible. | [`stage-before-light.webp`](phase5/stage-before-light.webp), [`stage-after-light.webp`](phase5/stage-after-light.webp), [`stage-before-dark.webp`](phase5/stage-before-dark.webp), [`stage-after-dark.webp`](phase5/stage-after-dark.webp) |

Taste inspection commands were run for the two required routes:

```powershell
node <home>/.codex/skills/design-taste-frontend/scripts/inspect.mjs 'http://127.0.0.1:8011/#/overview?scenario=compressor_fouling&seed=42&i=72' --app --out <repo>/docs/redesign/phase5/taste-inspect/overview --widths 1440,1024,768,375 --json
node <home>/.codex/skills/design-taste-frontend/scripts/inspect.mjs 'http://127.0.0.1:8011/#/components/compressor?scenario=compressor_fouling&seed=42&i=72' --app --out <repo>/docs/redesign/phase5/taste-inspect/components --widths 1440,1024,768,375 --json
```

The matching lint invocation used `node <home>/.codex/skills/design-taste-frontend/scripts/lint.mjs --app` on the changed app shell, Stage CSS, viewer modules, and `frontend/e2e/phase5-viewer.spec.ts`; its output is retained in [`phase5/final-taste-lint.log`](phase5/final-taste-lint.log).

## Viewer change log and limitations

`TurbineViewer.tsx` was split into the modules listed above; its public props did not change. The Canvas now uses `frameloop="demand"` and `dpr={[1, 2]}`. Scene, theme, selection, camera, controls, and rotor updates invalidate frames as needed. Camera reset/focus eases over 240 ms unless reduced motion is enabled. Selected mesh outlines use `--stage-selected`, and labels use a stable stage-owned overlay. Auto-rotation remains off. The mesh loader call is `useGLTF(url, false, true)` to select the local Meshopt decoder and disable Drei's default Draco decoder path. No lighting intensity change was needed in this phase; the dark-stage after capture shows visible model detail.

No Phase 6 work was started. Lighthouse variability remains measurable on mobile: two runs were below 2,000 ms TBT, while one exceeded it by 39 ms; the required median passed. The glTF validator does not support the new Meshopt extension, so viewer loading plus the unchanged Blender contract test provide the runtime and repository-level validation for the compressed asset.
