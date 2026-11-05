# Phase 5 Part A: Phase 4 follow-ups

## Changes

- The Assistant progress rule is rendered only during an in-flight request. Reduced-motion mode uses a static, full-width line. The server-provided scenario display name is shown in the context chip, including `Compressor-performance drift` for the compressor scenario.
- Engine-offline guidance is shared by Overview, Component detail, Evidence, and Assistant. It shows the portable `python -m uvicorn turbineiq.api.main:app --host 127.0.0.1 --port 8000` command, the PowerShell and POSIX virtual-environment activation lines, and a working copy button. The command is run after activating the project's environment.
- Component detail uses one decimal for percent and kelvin values, formats sample time as 24-hour UTC through `lib/format.ts`, and no longer repeats the reference value inside Provenance when Reference has its own column.
- Stage Canvas activation now waits until its viewport intersects the page and the browser is idle. `requestIdleCallback` is used where supported with a `setTimeout` fallback. The frame and schematic preview stay mounted before Canvas activation.
- Boundary and Cloud consent now use the same native `<dialog>` Sheet with `showModal`, initial focus, a shared Tab trap, Escape handling, and focus return.
- Captured nine requested states at 1440 and 375 pixels in light and dark themes: evidence with a selected reader, no evidence, Component Over time, Component Evidence, Assistant answer with expanded local tool trace, Cloud consent, local fallback, engine offline, and request failure with retry. The mobile fixed bar was hidden for full-page state captures. Thirty-two captures report `Local engine · connected`; the four offline captures report the intentionally simulated offline state. Fallback, offline, and request-failure states are explicitly marked as mocked in the manifest.

## Verification

| Check | Result | Evidence |
|---|---|---|
| `npm run build` | Passed; production build emits the existing large viewer-chunk advisory. | [`part-a-build.log`](part-a-build.log) |
| `npm run lint` | Passed. | [`part-a-lint.log`](part-a-lint.log) |
| `npm test` | 14 tests passed. | [`part-a-vitest.log`](part-a-vitest.log) |
| Targeted Playwright | 6 tests passed, including axe in both themes, keyboard focus/return, mocked consent, busy-rule behavior, offline command copy, and component formatting. | [`part-a-targeted-playwright-results.json`](part-a-targeted-playwright-results.json) |
| Axe | Zero serious or critical findings in the 16 light/dark route, tab, Boundary sheet, and Cloud consent states. | [`part-a-axe-results.json`](part-a-axe-results.json) |
| Local-origin check | No captured state requested a different origin. | [`part-a-network-origins.json`](part-a-network-origins.json), [`states/capture-manifest.json`](states/capture-manifest.json) |
| State screenshots | All 36 requested viewport/theme/state combinations were captured. | [`states/`](states/) |

The first capture-script attempt expected the desktop rail's engine button to be visible at phone width. The app correctly hides that control inside the mobile utilities menu; the capture harness was corrected to wait on the status attribute in the DOM. The successful captures are the authoritative evidence.
