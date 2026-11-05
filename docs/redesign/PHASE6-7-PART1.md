# Phase 6–7, Part 1: Stage refinements and repository cleanup

This part fixes the Phase 5 Stage findings, prunes historical raw evidence, refreshes the project documentation, and adds CI checks. No Part 2 work was started.

## Changes

- The Stage toolbar is left-aligned with a fixed 6 px gap. Its GLB/Schematic segmented control sizes to its content, including the full “Schematic” label. The controls keep 44 px targets, accessible names, and hover/focus tooltips.
- Stage tooltips on the last controls align toward the toolbar so they do not create page overflow at 320 px. The final Playwright suite verified all four routes at 320 px without horizontal page scroll.
- The selection callout uses a selected mesh's local geometry bounds, projects the transformed edge through the active camera, and positions the HTML label outside that edge. It points away from the part center where the viewport allows, with a visible 1 px `--text` leader line. The anchor and placement logic has focused Vitest coverage.
- The callout ink pair is `--text` on `--stage-bg`, which aliases `--surface`: the measured contrast is 19.80:1 in light and 16.43:1 in dark. No new color token was introduced.
- Stage before/after captures were refreshed at 1440 px in light and dark themes. The final label and leader line are visible in both themes.
- README, Blender integration, demo, architecture, and design system documentation now describe the current workspace and Meshopt asset pipeline. `docs/redesign/README.md` indexes the kept direction, baseline, reports, contrast results, and final screenshots.
- Raw Phase 2–4 screenshot matrices, Lighthouse JSON, and taste inspector output were removed from the working tree. The Phase 5 raw Lighthouse JSON was also removed to keep `docs/redesign/` under 8 MB; its run tables, CLI logs, and final screenshots remain. Removed files are recoverable from archive commit `08e5d1ae1bc4e9541f4cf45a8ee6d4b17e902464`.
- Local machine paths in docs and reports were replaced with `<repo>` or `<home>`. The new `npm run check:paths` guard checks README and text artifacts under `docs/`.
- CI runs Python Ruff and pytest plus frontend install, lint, build, Vitest, path scanning, and Playwright on pushes and pull requests for `main` and `redesign/*`. Playwright reports and generated screenshots now go to the ignored `frontend/test-results/` folder.
- Streamlit is an optional `streamlit` extra. The full Python suite, including the optional Streamlit tests, passed.

## Gates and evidence

| Gate | Command and result | Evidence |
| --- | --- | --- |
| Ruff | `.venv\Scripts\python.exe -m ruff check src tests` — passed. | [`ruff.txt`](phase6-7-part1/ruff.txt) |
| Python tests | `.venv\Scripts\python.exe -m pytest -q` — **69 passed**, with five existing dependency deprecation warnings. | [`pytest.txt`](phase6-7-part1/pytest.txt) |
| Frontend lint | `npm run lint --prefix frontend` — passed. | [`frontend-lint.txt`](phase6-7-part1/frontend-lint.txt) |
| Vitest | `npm run test --prefix frontend` — **22 tests passed in 5 files**, including the callout anchor tests. | [`vitest.txt`](phase6-7-part1/vitest.txt) |
| Production build | `npm run build --prefix frontend` — passed. Vite reports the existing 1,039.64 kB 3D viewer chunk advisory. | [`build.txt`](phase6-7-part1/build.txt) |
| Playwright | `npm run test:e2e --prefix frontend` — **16 passed**. Covers route interactions, keyboard access, viewer actions, reduced motion, offline/retry behavior, responsive screenshots, and 320 px overflow. | [`playwright.txt`](phase6-7-part1/playwright.txt) |
| Axe | Sixteen route/theme/tab/consent states have no findings. | [`axe-results.json`](phase6-7-part1/axe-results.json) and the Playwright log |
| Network | The test recorded only `http://127.0.0.1:8011`; cloud behavior is mocked. | [`network-origins.json`](phase6-7-part1/network-origins.json) |
| Documentation paths | `npm run check:paths --prefix frontend` — passed for `README.md` and text files under `docs/`. | [`check-paths.txt`](phase6-7-part1/check-paths.txt) |
| Contrast | `.venv\Scripts\python.exe docs\redesign\contrast_check.py` — all 44 measured light/dark checks passed. No new color token was added. | [`contrast-check.txt`](phase6-7-part1/contrast-check.txt), with prior phase results in [`phase3/contrast-check.txt`](phase3/contrast-check.txt) and [`phase4/contrast-check.txt`](phase4/contrast-check.txt) |
| Protected files | `git diff --quiet main -- src tests`; `git diff --quiet main -- frontend/src/types.ts`; `git diff --quiet HEAD -- frontend/public/models/turbine.glb` — all exited 0. | [`source-invariants.txt`](phase6-7-part1/source-invariants.txt) |
| Stage screenshots | Before/after captures at 1440 px, light and dark. | [`stage-toolbar-before-light.png`](phase6-7-part1/stage-toolbar-before-light.png), [`stage-toolbar-after-light.png`](phase6-7-part1/stage-toolbar-after-light.png), [`stage-toolbar-before-dark.png`](phase6-7-part1/stage-toolbar-before-dark.png), [`stage-toolbar-after-dark.png`](phase6-7-part1/stage-toolbar-after-dark.png) |
| Markdown links | All relative Markdown links in the root README and docs resolve. | [`markdown-links.txt`](phase6-7-part1/markdown-links.txt) |
| Docs size | The final `docs/redesign/` tree is below the 8,000,000 byte target. | [`docs-size.txt`](phase6-7-part1/docs-size.txt) |

The first Playwright run caught a 5 px 320-width overflow caused by Stage tooltip geometry. The toolbar tooltip alignment was corrected and the final full run passed; the initial failure output is retained in [`playwright-initial-failure.txt`](phase6-7-part1/playwright-initial-failure.txt).

## Notes and limits

- The GLB, Python source/tests, API types, component IDs, and mesh-name contract were not changed in this part.
- No new runtime dependencies or external application requests were added.
- The repository has no tracked `LICENSE`; the owner must choose a license. [`license-check.txt`](phase6-7-part1/license-check.txt) records the check.
- The GitHub Actions workflow was added but its remote run was not inspected in this local verification.
