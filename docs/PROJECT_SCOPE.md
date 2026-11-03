# TurbineIQ project scope

## Finalized configuration

- **Machine model:** simplified single-shaft, open-cycle industrial gas turbine (Brayton cycle).
- **LLM deployment:** hybrid. Local deterministic engineering, synthetic-data, analytics, and retrieval components; optional cloud LLM for natural-language planning and explanation.
- **Demonstration data:** synthetic only, generated reproducibly from explicit model assumptions.
- **Interface:** local Streamlit prototype.

## Included in the MVP

1. Validated compressor, combustor, turbine, shaft, and generator calculations with state-point outputs and stated assumptions.
2. Seeded baseline and perturbation scenarios derived from the deterministic model, plus labelled sensor faults.
3. Data completeness, timestamp, range, flat-line, and robust outlier checks.
4. An offline synthetic digital-twin demonstrator with a synthetic asset ID, time-selected state, model/observation comparison, and explicit provenance.
5. Local document ingestion and search that returns source and page/section citations.
6. One constrained assistant with allow-listed calculation, scenario, analytics, and retrieval tools.
7. Streamlit views for a three-minute end-to-end demonstration.

## Explicit exclusions

- A physical digital twin synchronized to a real turbine, real-time monitoring, live turbine connectivity, DCS/SCADA/PLC data or control.
- Autonomous maintenance decisions or commands.
- OEM-specific performance curves, fabricated OEM specifications, or unsourced operating thresholds.
- Real or confidential FieldCore data or documents.

## Modeling and safety boundaries

The cycle model is a transparent constant-property approximation. The twin represents a synthetic asset and is synchronized only to generated samples; it does not mirror or predict a real machine. Inputs and assumptions are illustrative and are not certified as safe for any real equipment. Synthetic anomalies demonstrate software behavior, not actual failure modes.

## Scope change

On 2 November 2026, the user changed the earlier no-digital-twin exclusion. TurbineIQ now includes a **synthetic, offline digital-twin demonstrator**. No real-time connection, industrial interface, or control capability was added.

