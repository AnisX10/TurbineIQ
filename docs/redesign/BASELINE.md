# Redesign baseline

Captured before visual implementation on 2026-11-03 from commit `eb41d2d` (`main`), at `http://127.0.0.1:8000/`. The redesign branch is `redesign/v2`.

## Screenshots

Taste inspector screenshots are in [`before/`](before/) at 375, 768, 1024, and 1440 CSS pixels. The inspected layouts had no horizontal overflow, no reported findings, and no browser console errors. The set includes a fold and full-page capture at each width. The machine-readable inspection output is [`before/report.json`](before/report.json).

## Build and bundle

`npm run build` passed with a Vite warning that the lazy-loaded 3D viewer chunk exceeds the 500 kB advisory limit.

| Asset | Minified | Gzip |
|---|---:|---:|
| Main JavaScript | 249.72 kB | 78.22 kB |
| Lazy 3D viewer JavaScript | 1,023.83 kB | 273.77 kB |
| CSS | 25.86 kB | 5.70 kB |
| HTML | 0.56 kB | 0.34 kB |
| **Total** | **1,299.97 kB** | **358.03 kB** |

## Lighthouse

Lighthouse CLI 13.6.0, headless Chrome, local production server, default desktop throttling:

| Category | Score |
|---|---:|
| Performance | 49 |
| Accessibility | 100 |
| Best practices | 96 |

| Metric | Result |
|---|---:|
| First Contentful Paint | 0.9 s |
| Largest Contentful Paint | 3.3 s |
| Total Blocking Time | 2,520 ms |
| Cumulative Layout Shift | 0.274 |
| Speed Index | 2.9 s |
| Time to Interactive | 14.8 s |

The full Lighthouse JSON is [`before/lighthouse.json`](before/lighthouse.json). The initial performance baseline is held back by main-thread JavaScript work, unused JavaScript, layout shifts, and the page's total payload (3,847 KiB). Treat these as local comparison values, not production guarantees.

## Regression gates

| Command | Result |
|---|---|
| `npm run build` | Passed; 3D chunk-size advisory above |
| `npm run lint` | Passed |
| `ruff check src tests` | Passed |
| `\.venv\Scripts\python.exe -m pytest -q` | **69 passed**, 5 dependency deprecation warnings |

The system Python did not have `pypdf`, so the first `python -m pytest -q` collection attempt failed. Running the suite in the repository's `.venv` passed. No application source was changed during Phase 0.
