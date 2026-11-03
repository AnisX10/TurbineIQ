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

The API key and model can be configured through `.env` or environment variables. Never commit secrets. The cloud model cannot execute code and is instructed to use tool results for numeric claims, cite retrieved passages, and avoid inventing OEM values or operating limits.

