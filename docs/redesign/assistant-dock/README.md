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

The dock's frontend checks were run from a clean clone of the pushed `c7af346` application commit. The retained logs are under [`evidence/`](evidence/). Clean-clone verification was rerun at commit `21cd21c`, which contains the final application and path-scanner source; the follow-up `1958a42` commit only adds those clean-clone logs.

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

### Clean clone of final application commit (`21cd21c`)

This clone was made after pushing the final evidence/path-scanner commit. Python dependencies were installed from the repository extras with `pip install -e ".[dev,streamlit]"`.

| Gate | Command | Result and retained output |
|---|---|---|
| Install | `cd frontend && npm ci` | Passed without flags; [`npm-ci.txt`](evidence/fresh-clone/npm-ci.txt). |
| Frontend | `npm run lint`; `npm run build`; `npm test` | Passed; build and 30 unit tests are recorded in [`lint.txt`](evidence/fresh-clone/lint.txt), [`build.txt`](evidence/fresh-clone/build.txt), and [`vitest.txt`](evidence/fresh-clone/vitest.txt). |
| Browser | `CI=1 npm run test:e2e` | Passed: 29 tests, one opt-in screenshot test skipped; [`playwright.txt`](evidence/fresh-clone/playwright.txt). CI mode uses one worker and does not reuse an already-running API server. |
| Python install and tests | `pip install -e ".[dev,streamlit]"`; `ruff check src tests`; `pytest -q` | Passed; 90 pytest tests, with one upstream Starlette/httpx deprecation warning. Logs: [`python-install.txt`](evidence/fresh-clone/python-install.txt), [`ruff.txt`](evidence/fresh-clone/ruff.txt), [`pytest.txt`](evidence/fresh-clone/pytest.txt). |
| Paths | `cd frontend && npm run check:paths` | Passed; [`check-paths.txt`](evidence/fresh-clone/check-paths.txt). The scanner also rejected a UTF-16 absolute-path fixture; [`path-check-selftest.txt`](evidence/path-check-selftest.txt). |

One initial browser run reused an A/B Lighthouse API server still bound to port 8021, so two cases failed against the wrong server. After stopping those servers, the clean `CI=1 npm run test:e2e` run above passed end to end.

The accessible dock is opened by the header Ask control or `A`, closes with Escape, and returns focus to the opener. At 375 px it is a bottom sheet. The fake provider supports stream, stop, retry, tool trace, citation, fallback, and cloud consent coverage; browser tests make no provider or other off-origin requests.

## Lighthouse note

The previously recorded Phase 6-7 medians predate this dock and did not record `benchmarkIndex`; they cannot be compared against the now-required 2,500 floor. The controlled Lighthouse attempt for this addition and its raw measurements are documented in [`lighthouse-note.md`](lighthouse-note.md). Only runs with `benchmarkIndex >= 2,500` are comparable for TBT.

## Scope

No Python API types, component IDs, GLB asset, runtime dependencies, or external requests were added by the dashboard dock work. The SSE endpoint and provider work are described separately in [Assistant providers](../../ASSISTANT_PROVIDERS.md).
