# Assistant tools and cloud-data boundaries

## Local tools

The single assistant can call only these local functions:

- `calculate_cycle` — validates inputs and runs the deterministic engineering model.
- `summarize_synthetic_scenario` — generates one seeded scenario and returns quality/anomaly summaries.
- `inspect_synthetic_twin_snapshot` — returns the server-recomputed selected sample and component metrics.
- `search_technical_documents` — searches already-indexed local text and returns short cited excerpts.

There is no shell, file-writing, network, DCS/SCADA/PLC, or maintenance-action tool. Cloud tool calls are limited to three rounds and unknown tool names are rejected locally.

## Cloud mode

The optional OpenAI Responses API integration uses strict function schemas and is disabled unless the user selects the cloud option in the UI. It sends the user's question, current synthetic sample/component context, and outputs of tools selected for that answer to the configured provider. Requests are made without persisted conversation state (`store=False`).

Uploaded files are parsed and searched locally in memory. The document-search tool is not exposed to the cloud model unless the user separately approves sending retrieved excerpts for that answer. A local evidence-only answer remains available without cloud access.

### Server-side consent

Cloud consent is enforced by the API, not only by the browser. The consent sheet calls `POST /api/assistant/consent`, which returns a short-lived token (30 minutes, in memory only). A Cloud request without a valid token is refused with HTTP 403 before any provider call. The grant is bound to the provider, model and base-URL host that were shown to the user, and to whether document excerpts were approved. Changing any of these invalidates it (`consent_scope_changed`), and sending document excerpts without that approval is refused (`document_consent_required`). `POST /api/assistant/consent/revoke` ends a grant.

The API also rejects requests whose `Host` header is not `localhost` or `127.0.0.1` (set `TURBINEIQ_ALLOWED_HOSTS` to a comma-separated list to allow others) and rejects state-changing requests from non-local `Origin` values. This protects against DNS rebinding and against other web pages calling the local API. `GET /api/assistant/audit` lists recent Cloud requests (time, provider, model, host, document scope, tools used, question length, never the text), and each is also logged under `turbineiq.audit`.

Limit: any program already running on this computer can call the consent endpoint. That is the same trust level as reading the local `.env` file, so this is a guard against web pages and stale clients, not against local malware.

The API key and model can be configured through `.env` or environment variables. Never commit secrets. The cloud model cannot execute code and is instructed to use tool results for numeric claims, cite retrieved passages, and avoid inventing OEM values or operating limits.

