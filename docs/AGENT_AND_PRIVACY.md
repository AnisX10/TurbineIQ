# Assistant tools and cloud-data boundaries

## Local mode

With no cloud model, a small rule-based parser (`agent/local_intent.py`) maps the question onto the tools below: numbers named next to a cycle input (pressure ratio, ambient temperature, turbine inlet temperature, air flow, efficiencies) rerun the cycle and report the change against the default case; scenario names select or compare scenario summaries; wording about "this sample" or the selected component explains the replay snapshot. A question it cannot map says so and lists what local mode can answer.

## Local tools

The single assistant can call only these local functions:

- `calculate_cycle` — validates inputs and runs the deterministic engineering model.
- `summarize_synthetic_scenario` — generates one seeded scenario and returns quality/anomaly summaries.
- `inspect_synthetic_twin_snapshot` — returns the server-recomputed selected sample and component metrics.
- `search_technical_documents` — searches already-indexed local text and returns short cited excerpts.

There is no shell, file-writing, network, DCS/SCADA/PLC, or maintenance-action tool. Cloud tool calls are limited to three rounds and unknown tool names are rejected locally.

## Number grounding

After every answer, the API checks the numbers it states against the data the assistant actually had: the question, the server-recomputed context, and the results of the tools that ran (`agent/grounding.py`). The response carries `grounding` with the counts and any numbers it could not find, and the interface shows either "Numbers traced to tool results" or a note listing the unverified numbers.

The check is conservative about what it skips (citations, list numbering, small whole numbers, "sample N" labels, the fixed help footer) and tolerant about presentation: rounding, kW to MW, kelvin to Celsius and fraction to percent all match, and sign is ignored so "1,000.9 kW below" matches a residual of -1,000.9. A number is **unverified**, not wrong, when it cannot be found: a model may state a sum or ratio no tool returned. Local answers record their own derived differences (for example the change against the default case) in the tool result so they trace too.

Limits: this verifies that a number appears in the inputs, not that the sentence around it is true, and a coincidental match with an unrelated value is possible. It is a first guardrail, not a proof of correctness.

## Cloud mode

The optional OpenAI Responses API integration uses strict function schemas and is disabled unless the user selects the cloud option in the UI. It sends the user's question, current synthetic sample/component context, and outputs of tools selected for that answer to the configured provider. Requests are made without persisted conversation state (`store=False`).

Uploaded files are parsed and searched locally in memory. The document-search tool is not exposed to the cloud model unless the user separately approves sending retrieved excerpts for that answer. A local evidence-only answer remains available without cloud access.

The API key and model can be configured through `.env` or environment variables. Never commit secrets. The cloud model cannot execute code and is instructed to use tool results for numeric claims, cite retrieved passages, and avoid inventing OEM values or operating limits.

