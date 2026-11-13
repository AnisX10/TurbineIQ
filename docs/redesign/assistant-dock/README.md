# Assistant dock on Overview

This evidence records the shared assistant dock added to the Overview dashboard on `mvp/llm-assistant`. The dock overlays the dashboard, becomes a bottom sheet on narrow screens, and shares the same conversation state as the full Assistant route. Context chips follow scenario, seed, sample, and selected component changes. Streaming exposes tool progress, stop and retry actions, citations, and the expandable tool trace. Cloud mode reuses the session-only consent sheet.

## Screenshots

Captures are viewport screenshots at four widths in both themes. They were converted from the browser PNG captures to WebP (quality 82) for the documentation size budget. File pattern: `<state>-<width>-<theme>.webp`.

| State | 375 light / dark | 768 light / dark | 1024 light / dark | 1440 light / dark |
|---|---|---|---|---|
| Dock closed | [light](screenshots/dock-closed-375-light.webp) / [dark](screenshots/dock-closed-375-dark.webp) | [light](screenshots/dock-closed-768-light.webp) / [dark](screenshots/dock-closed-768-dark.webp) | [light](screenshots/dock-closed-1024-light.webp) / [dark](screenshots/dock-closed-1024-dark.webp) | [light](screenshots/dock-closed-1440-light.webp) / [dark](screenshots/dock-closed-1440-dark.webp) |
| Answer with tool trace | [light](screenshots/answer-tool-trace-375-light.webp) / [dark](screenshots/answer-tool-trace-375-dark.webp) | [light](screenshots/answer-tool-trace-768-light.webp) / [dark](screenshots/answer-tool-trace-768-dark.webp) | [light](screenshots/answer-tool-trace-1024-light.webp) / [dark](screenshots/answer-tool-trace-1024-dark.webp) | [light](screenshots/answer-tool-trace-1440-light.webp) / [dark](screenshots/answer-tool-trace-1440-dark.webp) |
| Cloud consent | [light](screenshots/cloud-consent-375-light.webp) / [dark](screenshots/cloud-consent-375-dark.webp) | [light](screenshots/cloud-consent-768-light.webp) / [dark](screenshots/cloud-consent-768-dark.webp) | [light](screenshots/cloud-consent-1024-light.webp) / [dark](screenshots/cloud-consent-1024-dark.webp) | [light](screenshots/cloud-consent-1440-light.webp) / [dark](screenshots/cloud-consent-1440-dark.webp) |
| Local fallback | [light](screenshots/local-fallback-375-light.webp) / [dark](screenshots/local-fallback-375-dark.webp) | [light](screenshots/local-fallback-768-light.webp) / [dark](screenshots/local-fallback-768-dark.webp) | [light](screenshots/local-fallback-1024-light.webp) / [dark](screenshots/local-fallback-1024-dark.webp) | [light](screenshots/local-fallback-1440-light.webp) / [dark](screenshots/local-fallback-1440-dark.webp) |
| Streaming | [light](screenshots/streaming-375-light.webp) / [dark](screenshots/streaming-375-dark.webp) | [light](screenshots/streaming-768-light.webp) / [dark](screenshots/streaming-768-dark.webp) | [light](screenshots/streaming-1024-light.webp) / [dark](screenshots/streaming-1024-dark.webp) | [light](screenshots/streaming-1440-light.webp) / [dark](screenshots/streaming-1440-dark.webp) |

## Verification

The fresh-clone frontend checks were run from a clone of the pushed `c7af346` commit. The retained logs are under [`evidence/`](evidence/).

| Gate | Command | Result |
|---|---|---|
| Install | `cd frontend && npm ci` | Passed without flags; 272 packages installed, no vulnerabilities. |
| Lint / build / unit tests | `npm run lint`; `npm run build`; `npm test` | Passed; 30 Vitest tests. The closed Overview does not fetch the assistant chunks; compressed entry growth from the parent dashboard is about 1.25 kB, below 8 kB. |
| Browser tests | `npm run test:e2e` | Passed: 29 tests, 1 opt-in capture test skipped in the normal suite. Axe had zero serious or critical findings in checked routes and sheets in both themes. |
| Screenshot capture | `CAPTURE_DOCK=1 npx playwright test e2e/assistant-dock-captures.spec.ts` | Passed separately; captured all 40 combinations in the table above. |
| Python | `ruff check src tests`; `pytest -q` | Passed; 90 tests. |
| Contrast | `python docs/redesign/contrast_check.py` | All 52 measured pairs passed. See [`contrast.txt`](evidence/contrast.txt). |
| Documentation paths | `npm run check:paths` | Passed after evidence and report updates. |
| CI | GitHub Actions workflow `CI` | The run ID and result for the final pushed commit are included in the handoff report. |

The accessible dock is opened by the header Ask control or `A`, closes with Escape, and returns focus to the opener. At 375 px it is a bottom sheet. The fake provider supports stream, stop, retry, tool trace, citation, fallback, and cloud consent coverage; browser tests make no provider or other off-origin requests.

## Lighthouse note

The previously recorded Phase 6-7 medians predate this dock and did not record `benchmarkIndex`; they cannot be compared against the now-required 2,500 floor. The controlled Lighthouse attempt for this addition and its raw measurements are documented in [`lighthouse-note.md`](lighthouse-note.md). Only runs with `benchmarkIndex >= 2,500` are comparable for TBT.

## Scope

No Python API types, component IDs, GLB asset, runtime dependencies, or external requests were added by the dashboard dock work. The SSE endpoint and provider work are described separately in [Assistant providers](../../ASSISTANT_PROVIDERS.md).
