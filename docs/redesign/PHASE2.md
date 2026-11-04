# Phase 2 completion report

## Scope

Phase 2 closes the local frontend foundation and accessible shell on redesign/v2. It preserves the simplified single-shaft open-cycle reference model, synthetic-only demo data, local deterministic engineering/data/RAG behavior, and existing API. No industrial connectivity or control path was added.

The restored disclaimer wording in src/turbineiq/synthetic/scenarios.py and its assertion in tests/test_synthetic_scenarios.py are byte-identical to main. Hash comparison evidence is in phase2/logs/source-equivalence.txt. No backend implementation or Python API changed.

## Foundation

- frontend/index.html reads the saved light/dark preference before first paint in a guarded inline script, uses separate media-scoped theme-color tags, and preloads local Geist 400/500/600 and Geist Mono 500 fonts.
- frontend/src/app/router.ts validates the four routes and six existing component IDs, parses the shared scenario/seed/sample query, falls back on invalid routes and indexes, and serializes selected component state as component= on Overview.
- frontend/src/app/store.tsx owns the existing API payload, scenario, seed, sample, component, theme, engine status, and request state. Route/scenario/seed changes push history; sample scrubbing uses a debounced replace.
- frontend/src/lib/format.ts centralizes units, explicit signs, true minus, missing-value dashes, and grey zero values. Units use a separate span or U+00A0. Unsupported thin-space and triangle characters are absent.
- frontend/src/lib/publishedReference.ts is the shared 6B.03 constant for the Boundary sheet and inspector. The existing API returns run/reference measurements but not the published catalogue block; the constant cites GE Vernova and carries the ISO-condition and conceptual-geometry caveat.
- App.tsx is the shell and route outlet. IconRail, MobileBottomBar, PageHeader, theme menu, engine popover, BoundarySheet, skip link, landmarks, and accessible states are implemented. Components is a small transition detail screen; Evidence and Assistant remain legacy until Phase 4.

## Gates and retained evidence

| Gate | Command or evidence | Result |
|---|---|---|
| Frontend lint | cd frontend; npm run lint | Pass, exit 0. [Log](phase2/logs/npm-lint.txt) |
| Unit tests | cd frontend; npm test | 3 files, 11 passed. [Log](phase2/logs/vitest.txt) |
| Build | cd frontend; npm run build | Pass. Existing lazy Viewer size advisory remains. [Log](phase3/logs/build.txt) |
| Production Playwright | cd frontend; npm run test:e2e (build then playwright test) | 7 passed. [Console log](phase2/logs/playwright.txt), [machine results](phase2/playwright-results.json). |
| Axe | Four destinations, light and dark | Zero serious/critical findings in new code and zero serious/critical legacy nodes in all eight route/theme checks. [Results](phase2/axe-results.json) |
| Keyboard | Skip link; shell menus; BoundarySheet focus, trap, Escape, return; replay keys | Pass. Includes Left/Right, Shift+Left/Right, Home/End, Space, F and disabled no-flag behavior. |
| Legacy interaction regression | Scenario change, valid/invalid seed, replay, mesh picker, 3D part selection, Evidence search, local Assistant | Pass. |
| Network isolation | Playwright records request origins during API/app interaction | Only http://127.0.0.1:8011. [Result](phase2/network-origins.json) |
| Responsive screenshots | 375/768/1024/1440, light and dark | Pass, no horizontal overflow. Overview screenshots are in phase2/. |
| Unsupported glyph scan | U+2009, U+202F, U+25B2, U+25BE in frontend source/index | Pass, zero matches. |
| Python source equality | SHA-256 and byte comparison with git show main:<path> | Pass for both restored files. [Evidence](phase2/logs/source-equivalence.txt) |
| Ruff | .venv\Scripts\python.exe -m ruff check src tests | Pass. [Log](phase2/logs/ruff.txt) |
| Pytest | .venv\Scripts\python.exe -m pytest -q | 69 passed, 5 dependency deprecation warnings. [Log](phase2/logs/pytest.txt) |
| Taste lint | design-taste-frontend lint.mjs on 23 changed frontend files, --app --json | Exit 0, zero FAIL, 18 WARN (engineering mono and overlay shadows). [Output](phase3/taste-lint.json) |
| Taste inspect | inspect.mjs --app --widths 1440,1024,768,375 on all four routes | Exit 0, zero FAIL. Reports: [Overview](phase3/taste-inspect/overview-final/report.json), [Components](phase3/taste-inspect/components/report.json), [Evidence](phase2/taste-inspect/evidence/report.json), [Assistant](phase2/taste-inspect/assistant/report.json). |

The palette and type decisions are in DIRECTION.md; performance baseline/noise are in BASELINE.md. Playwright uses the local production build and API on port 8011. The offline banner retains the user-facing API startup command on port 8000.

## Findings and limits

Overview has one Taste inspector warning: compact 11-12px sublines and chart axis labels; no text is below 11px. Evidence and Assistant have legacy density/edge-text warnings; Components has a sparse detail warning. Those screens are not redesigned in this phase. The UI/UX Pro Max applicable checklist and evidence are recorded in PHASE3.md. Native Dynamic Type and authentication checks do not apply to this browser-only prototype.

Overview uses component= to retain selected component state alongside scenario, seed, and i. Published 6B.03 catalogue data is absent from the existing payload, so one shared cited constant is used; run observations and component/station metrics remain live API values. The Viewer stays a single lazy module until Phase 5.
