# Assistant provider branch gate evidence

Clean-clone validation for `mvp/llm-assistant` at commit `5c1749477ad527ab82a98c0f16cc79e49cf22319` (2026-11-10). The individual outputs are in [`llm-assistant-evidence/`](llm-assistant-evidence/). Local filesystem paths were replaced with placeholders before committing the logs.

| Command | Result | Evidence |
|---|---|---|
| `python -m pip install -e ".[dev,streamlit]"` | Passed in the clean clone | [`python-install.txt`](llm-assistant-evidence/python-install.txt) |
| `ruff check src tests scripts/eval_assistant.py` | Passed | [`ruff.txt`](llm-assistant-evidence/ruff.txt) |
| `pytest -q` | 88 passed; one upstream Starlette/httpx deprecation warning | [`pytest.txt`](llm-assistant-evidence/pytest.txt) |
| `python scripts/eval_assistant.py --fake` | 25/25 cases; 100% pass, tool, numeric-fact and groundedness accuracy | [`fake-eval.json`](llm-assistant-evidence/fake-eval.json) |
| `npm ci` (from `frontend/`, no flags) | Passed; 272 packages installed, zero reported vulnerabilities | [`npm-ci.txt`](llm-assistant-evidence/npm-ci.txt) |
| `npm run lint` | Passed | [`lint.txt`](llm-assistant-evidence/lint.txt) |
| `npm run build` | Passed; Vite reports the existing 1,040.51 kB viewer chunk warning | [`build.txt`](llm-assistant-evidence/build.txt) |
| `npm test` | 24 tests passed across 6 files | [`vitest.txt`](llm-assistant-evidence/vitest.txt) |
| `npm run check:paths` | Passed | [`check-paths.txt`](llm-assistant-evidence/check-paths.txt) |
| `npm run test:e2e` | 24 Playwright tests passed, including axe, keyboard, responsive, theme, forced-colors and WebGL fallback checks | [`playwright.txt`](llm-assistant-evidence/playwright.txt) |
| GitHub Actions `CI` | Passed for this commit; run [42905065699](https://github.com/AnisX10/TurbineIQ/actions/runs/42905065699) | Run summary is on GitHub |

The tests and fake evaluation make no provider requests. The live evaluation was not run. Provider/model defaults and source links, checked on 2026-11-10, are recorded in [`ASSISTANT_PROVIDERS.md`](../ASSISTANT_PROVIDERS.md).

Build warnings are informational: the viewer output chunk exceeds Vite's 500 kB advisory threshold. The Python test warning comes from the installed Starlette/httpx combination; all tests passed.
