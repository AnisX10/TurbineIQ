# TurbineIQ final audit and handoff

Audit date: 2026-11-07. Branch: `redesign/v2`. This report covers the final Phase 6-7 audit only. It does not start Phase 8.

## Outcome

The interaction, accessibility, contrast, browser, Python, and frontend test gates passed. The mobile Lighthouse accessibility score is 100, mobile LCP is 0.922 s, and CLS is 0.0464. The mobile TBT median is **2,746 ms**, above the 2,000 ms target. Lighthouse points to long work in the main application and viewer bundles; the run profile is preserved in [`lighthouse-summary.json`](phase6-7-part2/lighthouse-summary.json).

No backend/API, Python source or tests, frontend API types, component IDs, router IDs, model mesh names, or GLB asset changed. The GLB remains byte-identical to the starting commit. No runtime dependency or external application request was added. The `docs/redesign` tree is 11.1 MB (10.6 MiB), under the 12 MB budget.

## Lighthouse comparison

Each final preset used three Lighthouse 13.6.0 runs against the local production app with performance, accessibility, and best-practices categories enabled. Phase 4 and Phase 5 recorded performance-only Lighthouse runs, so their accessibility and best-practices values are not available.

| Preset | Phase | Performance | Accessibility | Best practices | LCP | CLS | TBT | Payload |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Mobile | Phase 0 | 51 | 100 | 96 | 3.3 s | 0.274 | 1,650 ms | 3,847 KiB |
| Mobile | Phase 4 | 69 | n/m | n/m | 1.078 s | 0.0373 | 3,260 ms | 3,969 KiB |
| Mobile | Phase 5 | 72 | n/m | n/m | 0.916 s | 0.0374 | 1,579 ms | 2,915 KiB |
| Mobile | Final | 69 | 100 | 96 | 0.922 s | 0.0464 | **2,746 ms** | 2,917 KiB |
| Desktop | Phase 0 | 80 | 96 | 96 | 0.7 s | 0.034 | 450 ms | 3,847 KiB |
| Desktop | Phase 4 | 76 | n/m | n/m | 0.310 s | 0.0132 | 602 ms | 3,969 KiB |
| Desktop | Phase 5 | 96 | n/m | n/m | 0.258 s | 0.0136 | 161 ms | 2,915 KiB |
| Desktop | Final | 81 | 100 | 96 | 0.262 s | 0.0136 | 424 ms | 2,917 KiB |

Here, n/m means the earlier phase did not measure that category. Final LCP element probes, run separately from Lighthouse throttling, identify `.viewer-note` at 252 ms on mobile and `h2#component-ledger-title` at 196 ms on desktop. Both Lighthouse LCP targets and both CLS targets pass. The final payload is 930 KiB below Phase 0 and 1,052 KiB below Phase 4.

The initial final sample missed the mobile TBT target in all three runs: 2,746, 3,441, and 2,360 ms (median 2,746 ms). Across those traces, the longest observed main-thread tasks were 1,034 ms from `index-*.js` and 653 ms from `TurbineViewer-*.js`; repeated 300-650 ms tasks also came from the viewer bundle. The run-by-run values and top tasks are in [`lighthouse-summary.json`](phase6-7-part2/lighthouse-summary.json). Desktop performance median was 81, 15 points below Phase 5's 96, while desktop LCP remained about 0.26 s. The controlled retest below found this apparent score drop was measurement drift; it did not reproduce a code regression.

### Controlled Phase 5-to-final A/B retest

To check whether that change came from the code, I built commit `08e5d1a` and `176a6b1` in separate worktrees, served them on local ports `8012` and `8013`, and alternated five Lighthouse 13.6.0 runs per build and preset. Each run enabled performance, accessibility, and best-practices categories. The runner records `environment.benchmarkIndex`, host CPU utilization during the run, free memory before and after, payload, and the boot-up cost attributed to each script. The full per-run records and summaries are in [`lighthouse-ab.json`](phase6-7-part2/lighthouse-ab.json).

| Preset | Build | Performance median [range] | Accessibility | Best practices | TBT median [range] | LCP median [range] | CLS median [range] | Payload | benchmarkIndex median [range] |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Mobile | `08e5d1a` | 67 [67–68] | 100 | 96 | 4,724 [4,365–6,065] ms | 930.3 [923.8–933.8] ms | 0.000123 [0.000123–0.037418] | 2,915 KiB | 1,549 [1,078.5–1,649.5] |
| Mobile | `176a6b1` | 67 [66–67] | 100 | 96 | 4,374 [4,025–5,003] ms | 934.5 [921.1–936.8] ms | 0.000123 [0.000123–0.046438] | 2,917 KiB | 1,590.5 [1,471.5–1,790.5] |
| Desktop | `08e5d1a` | 74 [72–75] | 100 | 96 | 671 [619–739] ms | 271.1 [265.6–275.0] ms | 0.013613 | 2,915 KiB | 1,683 [927.5–1,875] |
| Desktop | `176a6b1` | 74 [73–95] | 100 | 96 | 662 [172–700] ms | 265.6 [253.9–275.4] ms | 0.013613 | 2,917 KiB | 1,880.5 [1,612.5–2,620.5] |

The original Phase 5-to-final drop is not reproduced by the paired comparison. Performance medians are equal, desktop TBT is similar, mobile HEAD TBT is lower, and the run ranges overlap. The measured payload changed by only 2,469 bytes. I interpret the earlier score drop as measurement drift; the controlled runs do not show a code regression to bisect. The host was still noisy: CPU utilization ranged from 44.5% to 61.6%, free memory from 1,394 to 2,410 MiB, and benchmarkIndex varied substantially within the run set.

The 2,000 ms mobile TBT target was not met in this low-benchmark-index five-run set. For context, a separate three-pair diagnostic at benchmarkIndex 3,215–3,351 measured the original `176a6b1` at 1,132 ms median and a temporary optimization candidate at 1,122 ms; this diagnostic is recorded in [`lighthouse-candidate-check.json`](phase6-7-part2/lighthouse-candidate-check.json) and is not used to claim the formal five-run target passed. The profile points to startup cost rather than a Phase 5-to-final regression: in the five-run set, mobile boot-up work attributed to `TurbineViewer-*.js` had a 3,846 ms median and `index-*.js` a 3,106 ms median on HEAD. Their minified bundle sizes were 1,040.51 KiB and 275.47 KiB. The earlier trace's longest tasks were 653 ms and 1,034 ms respectively.

I tested narrower Drei subpath imports, a Rolldown vendor split, and a longer idle callback before Canvas activation. The candidate split the app into smaller named chunks but increased transfer by about 1 KiB and changed mobile TBT by only 10 ms in the high-benchmark diagnostic. I reverted those source changes to avoid extra chunks and delaying the 3D Canvas without a measurable gain. The Stage still shows its reserved frame and schematic while the existing idle/visibility activation loads the Canvas.

`npm run perf:lh -- --a <baseline-url> --b <head-url> --runs 5 --presets mobile,desktop` now provides the alternating method and writes UTF-8 JSON without a BOM. Lighthouse is pinned as a development dependency only; application runtime dependencies are unchanged.

## Accessibility, responsive behavior, and theme

- Playwright axe reported zero serious or critical findings across 16 states: all four routes, all three Component tabs, Boundary, and Cloud consent in both themes.
- Keyboard checks passed for tabs, Evidence result selection, both sheets, Assistant composer, replay shortcuts, and every viewer action. The top-level error boundary test confirms its fallback hides exception details and offers a reload action.
- There was no horizontal page overflow at 320 px or in the 720 CSS px / DPR 2 viewport used to represent 200% zoom, for all four routes, every Component tab, and both sheets in both themes.
- At 375 px the final target audit found no interactive target below 44x44 px in any route, tab, sheet, or theme. The initial audit found: skip link 144x43; Scenario selector 277x24; Seed input 45x24; mesh picker 317x34; Overview breadcrumb 52x15; Evidence query 298x40 and top_k 38x40; Assistant suggestion 343x40, composer 272x36, and Ask 64x36; consent checkbox 16x16, Cancel 78x40, and Continue 131x40. These targets were enlarged or given a 44x44 hit area. The initial dimensions are kept in [`hit-target-before.txt`](phase6-7-part2/hit-target-before.txt); the final zero-result audit is recorded in [`gate-summary.txt`](phase6-7-part2/gate-summary.txt).
- System, Light, and Dark theme changes worked live. The System preference followed an OS light-to-dark change and recoloured the 3D stage. A separate check confirmed saved Light and Dark preferences were applied by the head script before DOMContentLoaded.
- Forced-colours emulation kept route focus outlines, Stage borders, and segmented selections visible.
- Reduced motion disables the rotor, camera easing, OrbitControls damping, chart transitions, and the Assistant waiting animation. Skeletons are static. If replay is explicitly started, it continues stepping samples every 800 ms; replay is user-started and does not interpolate between samples. Pointer-driven orbit remains interactive.

The 200% check used a 720 CSS px viewport at DPR 2, equivalent to a 1440 px viewport at 200% browser zoom. Headless browser chrome zoom itself was unavailable, so actual Chrome zoom controls were not exercised.

## Contrast and design inspection

The contrast script passed all 52 light/dark pairs. Added pairs included focus ring on both `--ground` and `--surface`, the 3D callout label, and the selection outline against the Stage. Focus ratios were 16.72:1 / 18.42:1 in light and 17.26:1 / 16.43:1 in dark; callout text was 19.80:1 / 16.43:1; selection outline was 6.10:1 / 7.03:1. Full results are in [`contrast-check.txt`](phase6-7-part2/contrast-check.txt).

Taste lint scanned 68 frontend files with zero failures and 19 advisories. Taste inspect scanned all four routes at 1440, 1024, 768, and 375 px with zero FAIL findings. It reported small-type advisories on data-dense screens, unequal Overview panel heights, and blank space in the Results panel when one passage is returned; these were retained because the 12px engineering labels and equal-height panels follow the current direction. Accent-color share peaked at 0.4% in light and 0.32% in dark, below the 1% budget. See [`taste-summary.txt`](phase6-7-part2/taste-summary.txt).

## Browser and network checks

Chromium, Firefox, and WebKit passed Overview and Evidence smoke checks. Each loaded the local Meshopt GLB with WebGL2 available, had no runtime errors, and made requests only to `http://127.0.0.1:8011`. Playwright also confirmed:

- A failed GLB request leaves the interactive schematic visible with a note.
- Unavailable WebGL leaves the static schematic visible with a note.
- Demand rendering stops while idle, and resumes for camera interactions or opt-in rotor motion.

The browser output is in [`browser-smoke.json`](phase6-7-part2/browser-smoke.json). The local network assertion is included in the Playwright suite and summarized in [`gate-summary.txt`](phase6-7-part2/gate-summary.txt).

## Changes made in this audit

- Increased undersized mobile controls and consent targets to 44 px, including a 44x44 checkbox hit area.
- Matched the mobile Components link's accessible name to its visible “Parts” label after Lighthouse found a label/name mismatch; Lighthouse accessibility is now 100 on every final run.
- Added a top-level React error boundary with a calm reload fallback and a unit test.
- Added a visible static schematic state when WebGL is unavailable.
- Updated reduced-motion support so camera easing and OrbitControls damping stop under `prefers-reduced-motion`.
- Expanded the contrast checker for focus rings, the callout label, and the selected outline.
- Captured 32 final “after” screenshots as quality-85 WebP and 32 “before” screenshots as quality-85 JPEG. Screenshots are viewport captures, so the fixed mobile bar is shown once rather than repeated in a full-page image.

### TurbineViewer changes

This audit adds only the optional `reduceMotion` prop and sets `OrbitControls.enableDamping` to false when reduced motion is requested. No mesh mapping, selection, camera target, lighting, public API types, GLB, or asset contract changed. The Stage-level WebGL check and static fallback are implemented in `StageCard`, outside the viewer shell.

## Gate results

| Gate | Command and result | Evidence |
|---|---|---|
| Vitest | `cd frontend && npm test` — 24 tests passed. | [`gate-summary.txt`](phase6-7-part2/gate-summary.txt) |
| Playwright | `cd frontend && npm run test:e2e -- --workers=1` — 23 passed; separate saved-theme first-paint check — 1 passed. | [`gate-summary.txt`](phase6-7-part2/gate-summary.txt), [`browser-smoke.json`](phase6-7-part2/browser-smoke.json) |
| Frontend lint | `cd frontend && npm run lint` — passed. | [`gate-summary.txt`](phase6-7-part2/gate-summary.txt) |
| Build | `cd frontend && npm run build` — passed; Vite retains its large viewer-chunk advisory. | [`gate-summary.txt`](phase6-7-part2/gate-summary.txt) |
| Ruff | `ruff check src tests` — passed. | [`gate-summary.txt`](phase6-7-part2/gate-summary.txt) |
| Python | `cd <repo> && .venv/Scripts/python.exe -m pytest -q` — 69 passed, 5 dependency warnings. | [`gate-summary.txt`](phase6-7-part2/gate-summary.txt) |
| Taste lint and inspect | App rules on source and all four routes at 1440/1024/768/375 — zero failures. | [`taste-summary.txt`](phase6-7-part2/taste-summary.txt) |
| Axe and keyboard | Axe zero serious/critical across all 16 states; keyboard checks passed. | [`gate-summary.txt`](phase6-7-part2/gate-summary.txt) |
| Contrast | `python docs/redesign/contrast_check.py` — all 52 measured pairs passed. | [`contrast-check.txt`](phase6-7-part2/contrast-check.txt) |
| Responsive and touch targets | Playwright — no overflow at 320 px or the 200%-equivalent viewport; no sub-44 px targets at 375 px. | [`gate-summary.txt`](phase6-7-part2/gate-summary.txt) |
| Browsers and network | Chromium, Firefox, WebKit smoke checks passed; only local-origin requests. | [`browser-smoke.json`](phase6-7-part2/browser-smoke.json) |
| Lighthouse | Three runs per preset; accessibility, LCP, and CLS targets passed. **Mobile TBT median failed:** 2,746 ms vs 2,000 ms target. | [`lighthouse-summary.json`](phase6-7-part2/lighthouse-summary.json), [`lcp-elements.json`](phase6-7-part2/lcp-elements.json) |
| Documentation paths | `cd frontend && npm run check:paths` — passed after each evidence and report update. | [`gate-summary.txt`](phase6-7-part2/gate-summary.txt) |
| Protected files | Python `src` and `tests` byte-identical to `main`; types, router IDs, component IDs, and GLB unchanged from starting commit. | [`gate-summary.txt`](phase6-7-part2/gate-summary.txt) |

## Screenshots

Each row links to the pre-audit capture and final capture at the same viewport. The “after” files are WebP; the “before” files are JPEG. Captures are in [`phase6-7-part2/before/`](phase6-7-part2/before/) and [`phase6-7-part2/after/`](phase6-7-part2/after/).

### Overview

| Width | Light before | Light after | Dark before | Dark after |
|---:|---|---|---|---|
| 375 | [JPEG](phase6-7-part2/before/overview-375-light.jpg) | [WebP](phase6-7-part2/after/overview-375-light.webp) | [JPEG](phase6-7-part2/before/overview-375-dark.jpg) | [WebP](phase6-7-part2/after/overview-375-dark.webp) |
| 768 | [JPEG](phase6-7-part2/before/overview-768-light.jpg) | [WebP](phase6-7-part2/after/overview-768-light.webp) | [JPEG](phase6-7-part2/before/overview-768-dark.jpg) | [WebP](phase6-7-part2/after/overview-768-dark.webp) |
| 1024 | [JPEG](phase6-7-part2/before/overview-1024-light.jpg) | [WebP](phase6-7-part2/after/overview-1024-light.webp) | [JPEG](phase6-7-part2/before/overview-1024-dark.jpg) | [WebP](phase6-7-part2/after/overview-1024-dark.webp) |
| 1440 | [JPEG](phase6-7-part2/before/overview-1440-light.jpg) | [WebP](phase6-7-part2/after/overview-1440-light.webp) | [JPEG](phase6-7-part2/before/overview-1440-dark.jpg) | [WebP](phase6-7-part2/after/overview-1440-dark.webp) |

### Component detail

| Width | Light before | Light after | Dark before | Dark after |
|---:|---|---|---|---|
| 375 | [JPEG](phase6-7-part2/before/components-375-light.jpg) | [WebP](phase6-7-part2/after/components-375-light.webp) | [JPEG](phase6-7-part2/before/components-375-dark.jpg) | [WebP](phase6-7-part2/after/components-375-dark.webp) |
| 768 | [JPEG](phase6-7-part2/before/components-768-light.jpg) | [WebP](phase6-7-part2/after/components-768-light.webp) | [JPEG](phase6-7-part2/before/components-768-dark.jpg) | [WebP](phase6-7-part2/after/components-768-dark.webp) |
| 1024 | [JPEG](phase6-7-part2/before/components-1024-light.jpg) | [WebP](phase6-7-part2/after/components-1024-light.webp) | [JPEG](phase6-7-part2/before/components-1024-dark.jpg) | [WebP](phase6-7-part2/after/components-1024-dark.webp) |
| 1440 | [JPEG](phase6-7-part2/before/components-1440-light.jpg) | [WebP](phase6-7-part2/after/components-1440-light.webp) | [JPEG](phase6-7-part2/before/components-1440-dark.jpg) | [WebP](phase6-7-part2/after/components-1440-dark.webp) |

### Evidence

| Width | Light before | Light after | Dark before | Dark after |
|---:|---|---|---|---|
| 375 | [JPEG](phase6-7-part2/before/evidence-375-light.jpg) | [WebP](phase6-7-part2/after/evidence-375-light.webp) | [JPEG](phase6-7-part2/before/evidence-375-dark.jpg) | [WebP](phase6-7-part2/after/evidence-375-dark.webp) |
| 768 | [JPEG](phase6-7-part2/before/evidence-768-light.jpg) | [WebP](phase6-7-part2/after/evidence-768-light.webp) | [JPEG](phase6-7-part2/before/evidence-768-dark.jpg) | [WebP](phase6-7-part2/after/evidence-768-dark.webp) |
| 1024 | [JPEG](phase6-7-part2/before/evidence-1024-light.jpg) | [WebP](phase6-7-part2/after/evidence-1024-light.webp) | [JPEG](phase6-7-part2/before/evidence-1024-dark.jpg) | [WebP](phase6-7-part2/after/evidence-1024-dark.webp) |
| 1440 | [JPEG](phase6-7-part2/before/evidence-1440-light.jpg) | [WebP](phase6-7-part2/after/evidence-1440-light.webp) | [JPEG](phase6-7-part2/before/evidence-1440-dark.jpg) | [WebP](phase6-7-part2/after/evidence-1440-dark.webp) |

### Assistant

| Width | Light before | Light after | Dark before | Dark after |
|---:|---|---|---|---|
| 375 | [JPEG](phase6-7-part2/before/assistant-375-light.jpg) | [WebP](phase6-7-part2/after/assistant-375-light.webp) | [JPEG](phase6-7-part2/before/assistant-375-dark.jpg) | [WebP](phase6-7-part2/after/assistant-375-dark.webp) |
| 768 | [JPEG](phase6-7-part2/before/assistant-768-light.jpg) | [WebP](phase6-7-part2/after/assistant-768-light.webp) | [JPEG](phase6-7-part2/before/assistant-768-dark.jpg) | [WebP](phase6-7-part2/after/assistant-768-dark.webp) |
| 1024 | [JPEG](phase6-7-part2/before/assistant-1024-light.jpg) | [WebP](phase6-7-part2/after/assistant-1024-light.webp) | [JPEG](phase6-7-part2/before/assistant-1024-dark.jpg) | [WebP](phase6-7-part2/after/assistant-1024-dark.webp) |
| 1440 | [JPEG](phase6-7-part2/before/assistant-1440-light.jpg) | [WebP](phase6-7-part2/after/assistant-1440-light.webp) | [JPEG](phase6-7-part2/before/assistant-1440-dark.jpg) | [WebP](phase6-7-part2/after/assistant-1440-dark.webp) |

## Deviations from the audit conditions

The application direction and specified interactions were retained. Headless automation represented 200% zoom with a 720 CSS px viewport at DPR 2; it could not operate the browser chrome zoom control. The mobile TBT target was not met, so the measured main-thread profile is reported above. Taste inspect advisories were retained because the affected text sizes and equal-height panels follow the current design direction.

## Prioritized follow-up

1. Reduce mobile blocking work in `index-*.js` and `TurbineViewer-*.js`; add a repeatable trace to reach mobile TBT at or below 2,000 ms without delaying meaningful Stage access.
2. Re-run the desktop Lighthouse preset on a quiet machine and profile the 15-point performance drop from Phase 5; retain the 0.26 s LCP result while reducing viewer and app main-thread tasks.
3. Review the Taste small-type advisories against the engineering use case, especially status/provenance sublines, and review the Evidence empty-space treatment when only one result is returned.
4. Run the 200% layout check with browser chrome zoom on a headed desktop browser when available.
