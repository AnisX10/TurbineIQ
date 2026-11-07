# Pull request description

## Title

Complete the TurbineIQ redesign and final audit handoff

## Summary

This branch builds a local-first engineering workspace for a simplified, single-shaft open-cycle gas turbine. The React interface connects a seeded synthetic operating sample to deterministic engineering calculations, a local Meshopt-compressed Blender GLB, component metrics, local lexical document search, and a demo-safe local assistant.

The redesigned workspace contains Overview, Component detail, Evidence, and Assistant routes. It includes light/dark/system themes, a keyboard-accessible icon rail and mobile navigation, shared sheets, an interactive 3D Stage with schematic fallbacks, replay charts, accessible touch targets, and a top-level error boundary.

## Validation

- Python: Ruff passed; 69 tests passed in the repository virtual environment.
- Frontend: lint, build, 24 Vitest tests, and 23 production Playwright tests passed. A separate saved-theme first-paint test passed.
- Accessibility: zero serious or critical axe findings across all four routes, Component tabs, Boundary, and Cloud consent in light and dark.
- Browser smoke: Chromium, Firefox, and WebKit loaded Overview, Evidence, and the local GLB without runtime errors or off-origin requests.
- Contrast: all 52 measured light/dark pairs passed; the final accent-color share stayed below 1%.
- Lighthouse: final accessibility 100 and CLS below 0.1 on both presets. LCP medians were 0.922 s mobile and 0.262 s desktop.
- Mobile Lighthouse TBT median is 2,746 ms against a 2,000 ms target. The report includes the per-run measurements and long-task profile.

## Limits

The product uses synthetic demonstration values only. It is not a physical digital twin, OEM model, maintenance authorization system, or control product. No live industrial connection or confidential FieldCore material is included. The final 200% check used a 720 CSS px viewport at DPR 2 rather than browser chrome zoom.

No `LICENSE` file is present; the owner must choose a license. No pull request was opened as part of this handoff.

## Review artifacts

- Final audit, screenshots, gate results, performance table, and backlog: [`FINAL_REPORT.md`](FINAL_REPORT.md)
- Compact output summaries and browser evidence: [`phase6-7-part2/`](phase6-7-part2/)
