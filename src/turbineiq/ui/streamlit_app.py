"""Streamlit screens for the TurbineIQ three-minute prototype demo."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from turbineiq.agent import CloudLLMSettings, TurbineAssistant
from turbineiq.analytics import assess_data_quality, detect_anomalies
from turbineiq.engineering import CycleInputs, CycleResult, simulate_cycle
from turbineiq.rag import DocumentChunk, build_local_answer, load_document_bytes, load_document_path
from turbineiq.synthetic import SCENARIOS, generate_scenario
from turbineiq.twin import create_synthetic_twin

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEMO_DOCUMENT = PROJECT_ROOT / "data" / "documents" / "demo_cycle_notes.md"
MAX_DOCUMENT_BYTES = 20_000_000
NAVIGATION = [
    "Overview",
    "Cycle analysis",
    "Scenarios & data",
    "Synthetic digital twin",
    "Technical documents",
    "Engineering assistant",
]


def _initialize_session() -> None:
    if "cycle_result" not in st.session_state:
        st.session_state.cycle_result = simulate_cycle()
    if "demo_documents" not in st.session_state:
        try:
            st.session_state.demo_documents = load_document_path(DEMO_DOCUMENT)
        except Exception as exc:
            st.session_state.demo_documents = []
            st.session_state.demo_document_error = str(exc)
    if "uploaded_documents" not in st.session_state:
        st.session_state.uploaded_documents = {}


def _documents() -> list[DocumentChunk]:
    chunks = list(st.session_state.demo_documents)
    for document in st.session_state.uploaded_documents.values():
        chunks.extend(document["chunks"])
    return chunks


def _render_header(title: str, subtitle: str) -> None:
    st.title(title)
    st.caption(subtitle)


def _render_scope_notice() -> None:
    st.info(
        "**Synthetic demonstration only.** Model values are transparent study assumptions, "
        "not OEM specifications or operating limits. "
        "No live turbine connection or control is available."
    )


def _format_mw(power_kw: float) -> str:
    return f"{power_kw / 1000:.2f} MW"


def _overview_page() -> None:
    result: CycleResult = st.session_state.cycle_result
    _render_header(
        "TurbineIQ",
        "A local-first gas-turbine engineering prototype · simplified single-shaft open cycle",
    )
    _render_scope_notice()

    columns = st.columns(4)
    columns[0].metric("Illustrative electrical output", _format_mw(result.electrical_power_kw))
    columns[1].metric("Electrical efficiency", f"{result.electrical_efficiency:.1%}")
    columns[2].metric("Fuel flow estimate", f"{result.fuel_mass_flow_kg_s:.2f} kg/s")
    columns[3].metric("Demo evidence sources", str(len(_documents())))

    st.subheader("Three-minute walkthrough")
    step_columns = st.columns(3)
    step_columns[0].markdown(
        "**1 · Explore a scenario**\n\n"
        "Open **Scenarios & data** and choose the labelled power-sensor spike."
    )
    step_columns[1].markdown(
        "**2 · Check the evidence**\n\n"
        "Review the model and measured traces, then inspect the quality report "
        "and flagged sample."
    )
    step_columns[2].markdown(
        "**3 · Ask a grounded question**\n\n"
        "Use **Technical documents** for local citations or the assistant for "
        "calculations and scenario summaries."
    )

    with st.expander("What the prototype includes"):
        st.markdown(
            "- A four-state constant-property Brayton calculation with explicit assumptions.\n"
            "- Seeded synthetic operating scenarios and explainable anomaly flags.\n"
            "- An offline digital-twin view synchronized to generated scenario samples.\n"
            "- Local PDF, Markdown, and text retrieval with source citations.\n"
            "- One bounded assistant that can use deterministic engineering and analytics tools.\n"
            "- Optional cloud language help; local calculations and document "
            "search work without it."
        )


def _cycle_inputs_form() -> CycleInputs | None:
    defaults = CycleInputs()
    st.subheader("Illustrative study inputs")
    st.caption(
        "These are editable model assumptions, not machine ratings or safe-operation settings."
    )
    with st.form("cycle_inputs"):
        left, right = st.columns(2)
        with left:
            ambient_temperature = st.number_input(
                "Ambient temperature (°C)", value=defaults.ambient_temperature_c, step=1.0
            )
            ambient_pressure = st.number_input(
                "Ambient absolute pressure (kPa)", value=defaults.ambient_pressure_kpa, step=1.0
            )
            pressure_ratio = st.number_input(
                "Compressor pressure ratio (–)", value=defaults.pressure_ratio, step=0.5
            )
            air_mass_flow = st.number_input(
                "Air mass flow assumption (kg/s)", value=defaults.air_mass_flow_kg_s, step=5.0
            )
            turbine_inlet_temperature = st.number_input(
                "Turbine inlet temperature (K)",
                value=defaults.turbine_inlet_temperature_k,
                step=10.0,
            )
        with right:
            compressor_efficiency = st.number_input(
                "Compressor isentropic efficiency (–)",
                value=defaults.compressor_efficiency,
                step=0.01,
            )
            turbine_efficiency = st.number_input(
                "Turbine isentropic efficiency (–)",
                value=defaults.turbine_efficiency,
                step=0.01,
            )
            pressure_loss = st.number_input(
                "Combustor pressure-loss fraction (–)",
                value=defaults.combustor_pressure_loss_fraction,
                step=0.01,
            )
            mechanical_efficiency = st.number_input(
                "Mechanical efficiency assumption (–)",
                value=defaults.mechanical_efficiency,
                step=0.01,
            )
            generator_efficiency = st.number_input(
                "Generator efficiency assumption (–)",
                value=defaults.generator_efficiency,
                step=0.01,
            )
        submitted = st.form_submit_button("Run deterministic calculation", type="primary")

    if not submitted:
        return None
    try:
        return CycleInputs(
            ambient_temperature_c=ambient_temperature,
            ambient_pressure_kpa=ambient_pressure,
            pressure_ratio=pressure_ratio,
            air_mass_flow_kg_s=air_mass_flow,
            turbine_inlet_temperature_k=turbine_inlet_temperature,
            compressor_efficiency=compressor_efficiency,
            turbine_efficiency=turbine_efficiency,
            combustor_pressure_loss_fraction=pressure_loss,
            mechanical_efficiency=mechanical_efficiency,
            generator_efficiency=generator_efficiency,
        )
    except ValueError as exc:
        st.error(f"Input validation: {exc}")
        return None


def _show_cycle_result(result: CycleResult) -> None:
    columns = st.columns(4)
    columns[0].metric("Electrical output", _format_mw(result.electrical_power_kw))
    columns[1].metric("Net cycle power", _format_mw(result.net_cycle_power_kw))
    columns[2].metric("Fuel flow estimate", f"{result.fuel_mass_flow_kg_s:.2f} kg/s")
    columns[3].metric("Electrical efficiency", f"{result.electrical_efficiency:.1%}")
    st.caption(f"Estimated heat rate: {result.heat_rate_kj_per_kwh:,.0f} kJ/kWh")

    state_frame = pd.DataFrame(
        [
            {
                "State": f"{state.name} · {state.description}",
                "Temperature (K)": state.temperature_k,
                "Absolute pressure (kPa)": state.pressure_kpa,
            }
            for state in result.states
        ]
    )
    chart_columns = st.columns(2)
    with chart_columns[0]:
        st.markdown("**Cycle temperature by state**")
        st.line_chart(state_frame.set_index("State")[["Temperature (K)"]])
    with chart_columns[1]:
        st.markdown("**Cycle pressure by state**")
        st.line_chart(state_frame.set_index("State")[["Absolute pressure (kPa)"]])
    st.dataframe(state_frame, hide_index=True, width="stretch")
    with st.expander("Model assumptions and boundaries"):
        for assumption in result.assumptions:
            st.write(f"• {assumption}")


def _cycle_page() -> None:
    _render_header(
        "Cycle analysis",
        "A deterministic four-state calculation with visible inputs and assumptions.",
    )
    _render_scope_notice()
    entered_inputs = _cycle_inputs_form()
    if entered_inputs is not None:
        try:
            st.session_state.cycle_result = simulate_cycle(entered_inputs)
        except ValueError as exc:
            st.error(f"Calculation could not run: {exc}")
    _show_cycle_result(st.session_state.cycle_result)


def _scenario_page() -> None:
    _render_header(
        "Scenarios & data",
        "Reproducible model-derived series · no real operating measurements are loaded.",
    )
    spec_labels = {spec.name: key for key, spec in SCENARIOS.items()}
    selected_name = st.selectbox("Synthetic scenario", list(spec_labels))
    scenario_id = spec_labels[selected_name]
    seed = st.number_input("Random seed", min_value=0, value=42, step=1)
    frame = generate_scenario(scenario_id, seed=int(seed), samples=96)
    report = assess_data_quality(frame)
    analyzed = detect_anomalies(frame)
    st.info(f"**{frame.attrs['scenario_name']}** — {frame.attrs['scenario_description']}")
    st.caption(
        f"Synthetic only · seed {seed} · 96 samples at 15-minute intervals · "
        "values are model perturbations and illustrative measurement noise."
    )

    metric_columns = st.columns(4)
    metric_columns[0].metric(
        "Mean modeled output", _format_mw(frame["model_electrical_power_kw"].mean())
    )
    metric_columns[1].metric(
        "Mean measured output", _format_mw(frame["observed_electrical_power_kw"].mean())
    )
    metric_columns[2].metric("Robust residual flags", str(int(analyzed["anomaly_flag"].sum())))
    metric_columns[3].metric(
        "Injected sensor faults", str(int(frame["sensor_fault_injected"].sum()))
    )

    st.subheader("Power trace")
    chart = frame.set_index("timestamp_utc")[
        ["model_electrical_power_kw", "observed_electrical_power_kw"]
    ]
    st.line_chart(chart)
    st.caption(
        "Electrical power (kW) by synthetic UTC timestamp. Model estimate and "
        "noisy observation are separate series."
    )

    quality_columns = st.columns([1, 2])
    with quality_columns[0]:
        st.subheader("Data quality")
        st.metric("Missing cells", report.missing_cells)
        st.metric("Duplicate timestamps", report.duplicate_timestamps)
        st.metric("Out-of-order timestamps", report.out_of_order_timestamps)
        st.metric("Rows not marked synthetic", report.non_synthetic_rows)
        if report.findings:
            for finding in report.findings:
                st.warning(finding)
        else:
            st.success("No configured data-quality issues found.")
    with quality_columns[1]:
        st.subheader("Screening table")
        st.caption(
            "Robust residual flags are statistical screening signals, not fault "
            "diagnoses or alarm limits."
        )
        columns = [
            "timestamp_utc",
            "ambient_temperature_c",
            "model_electrical_power_kw",
            "observed_electrical_power_kw",
            "power_residual_kw",
            "robust_z_score",
            "anomaly_flag",
            "sensor_fault_label",
        ]
        st.dataframe(analyzed[columns], hide_index=True, width="stretch")

    st.download_button(
        "Download this synthetic scenario as CSV",
        data=frame.to_csv(index=False).encode("utf-8"),
        file_name=f"turbineiq_{scenario_id}_seed_{seed}.csv",
        mime="text/csv",
    )


def _digital_twin_page() -> None:
    _render_header(
        "Synthetic digital twin",
        "An offline asset-state view synchronized to a seeded model and synthetic feed.",
    )
    st.info(
        "**Twin demonstrator only.** This virtual asset is synchronized to generated samples; "
        "it is not connected to a physical turbine. It has no live telemetry, control, or "
        "maintenance-action interface."
    )

    spec_labels = {spec.name: key for key, spec in SCENARIOS.items()}
    scenario_names = list(spec_labels)
    fault_scenario_index = scenario_names.index(SCENARIOS["sensor_fault"].name)
    selected_name = st.selectbox("Twin scenario feed", scenario_names, index=fault_scenario_index)
    scenario_id = spec_labels[selected_name]
    seed = st.number_input("Twin random seed", min_value=0, value=42, step=1)
    twin = create_synthetic_twin(scenario_id, seed=int(seed), samples=96)
    sample_number = st.slider(
        "Twin timeline sample",
        min_value=1,
        max_value=twin.sample_count,
        value=min(49, twin.sample_count),
    )
    snapshot = twin.snapshot_at(int(sample_number) - 1)

    st.caption(
        f"Asset {snapshot.asset_id} · source: {snapshot.data_provenance} · "
        f"state timestamp: {snapshot.timestamp_utc} · sample {snapshot.sample_index + 1} "
        f"of {twin.sample_count}"
    )
    if snapshot.residual_screen_flag:
        st.warning(
            "The selected synthetic sample is flagged by residual screening. "
            "This is not a fault diagnosis."
        )
    else:
        st.success("No residual flag at this synthetic sample.")

    st.subheader("Mirrored asset state")
    state_columns = st.columns(4)
    state_columns[0].metric(
        "Ambient inlet",
        f"{snapshot.ambient_temperature_c:.1f} °C",
        f"{snapshot.ambient_pressure_kpa:.1f} kPa abs",
    )
    state_columns[1].metric(
        "Compressor",
        f"η {snapshot.compressor_efficiency_assumption:.2f}",
        f"discharge {snapshot.compressor_discharge_temperature_k:.1f} K",
    )
    state_columns[2].metric(
        "Turbine gas path",
        f"inlet {snapshot.turbine_inlet_temperature_k:.1f} K",
        f"exhaust {snapshot.exhaust_temperature_k:.1f} K",
    )
    state_columns[3].metric("Scenario label", snapshot.sensor_fault_label)

    st.subheader("Model state compared with synthetic observation")
    comparison_columns = st.columns(4)
    comparison_columns[0].metric(
        "Model electrical output", _format_mw(snapshot.model_electrical_power_kw)
    )
    comparison_columns[1].metric(
        "Synthetic observed output", _format_mw(snapshot.synthetic_observed_power_kw)
    )
    comparison_columns[2].metric("Power residual", f"{snapshot.power_residual_kw:+.1f} kW")
    comparison_columns[3].metric("Residual screen", snapshot.screen_status)

    timeline = twin.analyzed_history.set_index("timestamp_utc")[
        ["model_electrical_power_kw", "observed_electrical_power_kw"]
    ]
    st.line_chart(timeline)
    st.caption(
        "The timeline shows model output beside generated observations. The twin state "
        "updates when the selected synthetic sample changes."
    )
    st.dataframe(pd.DataFrame([snapshot.to_dict()]), hide_index=True, width="stretch")
    st.download_button(
        "Download synthetic twin timeline as CSV",
        data=twin.history.to_csv(index=False).encode("utf-8"),
        file_name=f"turbineiq_twin_{scenario_id}_seed_{seed}.csv",
        mime="text/csv",
    )


def _document_page() -> None:
    _render_header(
        "Technical documents",
        "Local retrieval with source and page/section citations. Files stay in session memory.",
    )
    st.info(
        "Only upload material you are authorized to use. "
        "Do not upload confidential FieldCore or OEM documents. "
        "Document text is processed locally and is not sent to a cloud model on this screen."
    )
    if getattr(st.session_state, "demo_document_error", None):
        st.error(f"Could not load the built-in demo note: {st.session_state.demo_document_error}")

    uploads = st.file_uploader(
        "Add a PDF, Markdown, or text document",
        type=["pdf", "md", "markdown", "txt"],
        accept_multiple_files=True,
        help="Uploads are parsed in memory and discarded when the session ends.",
    )
    if uploads:
        for uploaded in uploads:
            content = uploaded.getvalue()
            digest = hashlib.sha256(content).hexdigest()
            if digest in st.session_state.uploaded_documents:
                continue
            if len(content) > MAX_DOCUMENT_BYTES:
                st.error(f"{uploaded.name} exceeds the 20 MB prototype upload size.")
                continue
            try:
                chunks = load_document_bytes(uploaded.name, content)
                st.session_state.uploaded_documents[digest] = {
                    "name": uploaded.name,
                    "chunks": chunks,
                }
                st.success(f"Indexed {uploaded.name}: {len(chunks)} local chunk(s).")
            except ValueError as exc:
                st.error(f"Could not index {uploaded.name}: {exc}")

    if st.session_state.uploaded_documents and st.button(
        "Clear uploaded documents from this session"
    ):
        st.session_state.uploaded_documents = {}
        st.rerun()

    documents = _documents()
    st.caption(
        f"{len(documents)} local evidence chunk(s) available, including the "
        "built-in synthetic demo note."
    )
    question = st.text_input(
        "Question for local document search",
        placeholder="How does the simplified model estimate net power?",
    )
    top_k = st.selectbox("Maximum passages", [1, 2, 3, 4], index=2)
    if st.button("Search locally", type="primary", disabled=not question.strip()):
        from turbineiq.rag import search_documents

        hits = search_documents(question, documents, top_k=int(top_k))
        st.session_state.document_search = {
            "question": question,
            "answer": build_local_answer(question, hits),
            "hits": hits,
        }

    search_result: dict[str, Any] | None = st.session_state.get("document_search")
    if search_result:
        st.subheader("Evidence-backed result")
        st.write(search_result["answer"])
        if search_result["hits"]:
            with st.expander("Retrieved passages and relevance scores"):
                for hit in search_result["hits"]:
                    st.markdown(f"**{hit.citation}** · relevance {hit.score:.3f}")
                    st.write(hit.chunk.text)


def _assistant_page() -> None:
    _render_header(
        "Engineering assistant",
        "One bounded assistant with local calculation, scenario, and document tools.",
    )
    documents = _documents()
    settings = CloudLLMSettings.from_environment()
    cloud_enabled = st.checkbox(
        "Use the cloud language model for this answer",
        value=False,
        disabled=not bool(settings.api_key),
        help=(
            "The selected question and results from any tools used for it will "
            "be sent to the configured provider."
        ),
    )
    if not settings.api_key:
        st.caption(
            "No API key found. The deterministic local assistant is ready without cloud access."
        )
    allow_document_context = False
    if cloud_enabled:
        st.warning("This sends your question and tool results to the cloud provider.")
        allow_document_context = st.checkbox(
            "Also allow retrieved document excerpts to be sent for this answer",
            value=False,
            help=(
                "Leave unchecked to keep document text local. "
                "This choice applies only to the next answer."
            ),
        )

    question = st.text_area(
        "Ask a question",
        placeholder=(
            "Try: Calculate illustrative electrical output.\n"
            "Or: Review the sensor fault scenario for anomalies.\n"
            "Or: According to the demo notes, how is compressor work estimated?"
        ),
        height=120,
    )
    if st.button("Run assistant", type="primary", disabled=not question.strip()):
        assistant = TurbineAssistant(documents, cloud_settings=settings)
        with st.spinner(
            "Running local tools…"
            if not cloud_enabled
            else "Calling the selected model and local tools…"
        ):
            response = assistant.run(
                question,
                enable_cloud=cloud_enabled,
                allow_cloud_document_context=allow_document_context,
            )
        st.session_state.assistant_response = response

    response = st.session_state.get("assistant_response")
    if response:
        st.subheader("Answer")
        st.write(response.answer)
        st.caption(f"Execution mode: {response.mode.replace('_', ' ')}")
        if response.warning:
            st.warning(response.warning)
        with st.expander("Tool trace"):
            if response.tool_calls:
                for invocation in response.tool_calls:
                    st.markdown(f"**{invocation.name}**")
                    st.json(invocation.to_dict())
            else:
                st.write("No tool was needed for this answer.")
        st.caption(
            "The assistant is a prototype. It cannot provide OEM ratings, safe "
            "limits, fault diagnoses, "
            "or maintenance authorization."
        )


def run() -> None:
    """Render the Streamlit application."""

    st.set_page_config(page_title="TurbineIQ", page_icon="T", layout="wide")
    st.markdown(
        """
        <style>
          .block-container { max-width: 1320px; padding-top: 1.8rem; padding-bottom: 3rem; }
          [data-testid="stMetric"] {
            border: 1px solid rgba(128, 128, 128, 0.24);
            padding: 0.8rem;
            border-radius: 0.55rem;
          }
          [data-testid="stSidebar"] { border-right: 1px solid rgba(128, 128, 128, 0.18); }
        </style>
        """,
        unsafe_allow_html=True,
    )
    _initialize_session()

    st.sidebar.title("TurbineIQ")
    st.sidebar.caption("Engineering prototype · synthetic data only")
    page = st.sidebar.radio("Navigate", NAVIGATION, label_visibility="collapsed")
    st.sidebar.divider()
    st.sidebar.caption(
        "Local calculations and document search. No industrial connection or control."
    )

    page_functions = {
        "Overview": _overview_page,
        "Cycle analysis": _cycle_page,
        "Scenarios & data": _scenario_page,
        "Synthetic digital twin": _digital_twin_page,
        "Technical documents": _document_page,
        "Engineering assistant": _assistant_page,
    }
    page_functions[page]()
