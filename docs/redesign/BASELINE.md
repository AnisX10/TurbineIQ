# Redesign baseline

Captured before visual implementation from commit `eb41d2d` (`main`) on 2026-11-03 at `http://127.0.0.1:8000/`. The redesign branch is `redesign/v2`. The documentation and asset corrections below were made after capture; no application source was changed.

## Screenshots

Taste inspector screenshots are in [`before/`](before/) at 375, 768, 1024, and 1440 CSS pixels. The inspected layouts had no horizontal overflow, no reported findings, and no browser console errors. Each `*-fold.jpg` is the initial viewport capture. Each `*-filmstrip.jpg` is a four-screen stitched filmstrip, not a single full-page screenshot. The machine-readable inspection output is [`before/report.json`](before/report.json); all image paths in its `images` entries are repository-relative. A scan of `docs/` found no local absolute paths or user-profile paths.

- 375 px: [`mobile-fold.jpg`](before/mobile-fold.jpg), [`mobile-filmstrip.jpg`](before/mobile-filmstrip.jpg)
- 768 px: [`tablet-768-fold.jpg`](before/tablet-768-fold.jpg), [`tablet-768-filmstrip.jpg`](before/tablet-768-filmstrip.jpg)
- 1024 px: [`tablet-1024-fold.jpg`](before/tablet-1024-fold.jpg), [`tablet-1024-filmstrip.jpg`](before/tablet-1024-filmstrip.jpg)
- 1440 px: [`desktop-fold.jpg`](before/desktop-fold.jpg), [`desktop-filmstrip.jpg`](before/desktop-filmstrip.jpg)

## Build and bundle

`npm run build` passed with a Vite warning that the lazy-loaded 3D viewer chunk exceeds the 500 kB advisory limit.

| Asset | Minified | Gzip |
|---|---:|---:|
| Main JavaScript | 249.72 kB | 78.22 kB |
| Lazy 3D viewer JavaScript | 1,023.83 kB | 273.77 kB |
| CSS | 25.86 kB | 5.70 kB |
| HTML | 0.56 kB | 0.34 kB |
| **Total** | **1,299.97 kB** | **358.03 kB** |

`frontend/public/models/turbine.glb` is 1,910,712 bytes (about 1.9 MB), roughly 48.5% of the 3,847 KiB total Lighthouse payload. Draco or meshopt compression is a Phase 5 decision and requires approval because it touches the GLB contract. No compression was applied.

## Lighthouse

The earlier `lighthouse.json` had been mislabeled as desktop: it records `formFactor: mobile` and used Lighthouse's mobile slow-CPU throttling. It has been replaced by the median mobile and desktop reports below. Lighthouse CLI 13.6.0 ran against the local production build in headless Chrome, with performance, accessibility, and best-practices categories enabled. Mobile runs used `--form-factor=mobile`; desktop runs used `--preset=desktop`.

| Preset | Run | Performance | Accessibility | Best practices | FCP | LCP | TBT | CLS | Speed Index | TTI | Total byte weight | `benchmarkIndex` |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Mobile | 1 | 51 | 100 | 96 | 0.9 s | 3.3 s | 1,650 ms | 0.274 | 2.4 s | 13.7 s | 3,847 KiB | 2982.5 |
| Mobile | 2 | 51 | 100 | 96 | 0.9 s | 3.3 s | 1,590 ms | 0.274 | 2.4 s | 13.9 s | 3,847 KiB | 2630.5 |
| Mobile | 3 | 50 | 100 | 96 | 0.9 s | 3.3 s | 2,010 ms | 0.275 | 2.5 s | 14.2 s | 3,847 KiB | 2079.5 |
| Desktop | 1 | 80 | 96 | 96 | 0.3 s | 0.7 s | 450 ms | 0.033 | 1.0 s | 2.9 s | 3,847 KiB | 1674 |
| Desktop | 2 | 85 | 96 | 96 | 0.3 s | 0.7 s | 340 ms | 0.034 | 0.8 s | 2.7 s | 3,847 KiB | 2289.5 |
| Desktop | 3 | 79 | 96 | 96 | 0.3 s | 0.7 s | 480 ms | 0.034 | 1.1 s | 2.9 s | 3,847 KiB | 2378 |

The median mobile performance score is 51 (run 1 selected from the tied median-score runs); the median desktop score is 80 (run 1). Their complete raw JSON reports are [`before/lighthouse-mobile.json`](before/lighthouse-mobile.json) and [`before/lighthouse-desktop.json`](before/lighthouse-desktop.json). `environment.benchmarkIndex` is Lighthouse's CPU calibration value; it varied from 2,079.5 to 2,982.5 on mobile and 1,674 to 2,378 on desktop, so these are local comparison results, not production guarantees.

The redesign target is CLS 0.1 or lower on both the mobile and desktop presets. The pre-redesign mobile median was 0.274 and desktop median was 0.034; those are recorded as historical baselines, not acceptance targets. Expect about 5 performance points of run-to-run Lighthouse noise on this machine, so compare repeated runs and supporting metrics rather than treating a small score change as a regression.

## Regression gates

| Command | Result |
|---|---|
| `npm run build` | Passed; Vite emitted the existing lazy 3D chunk-size advisory. Main JS 249.72 kB; viewer chunk 1,023.83 kB. |
| `npm run lint` | Passed (exit 0). |
| `ruff check src tests` | Passed: `All checks passed!` |
| `.venv\Scripts\python.exe -m pytest -q` | **69 passed**, 5 dependency deprecation warnings, in 4.86s. |

The build, lint, Ruff, and pytest gates were rerun after the Phase 0 documentation corrections. No application source, API schema, frontend types, component IDs, or GLB contents were changed.
