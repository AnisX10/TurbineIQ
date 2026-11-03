from pathlib import Path

from streamlit.testing.v1 import AppTest

APP_FILE = Path(__file__).resolve().parents[1] / "app.py"


def test_overview_page_renders() -> None:
    app = AppTest.from_file(str(APP_FILE)).run()

    assert not app.exception
    assert any(element.value == "TurbineIQ" for element in app.title)
    assert any("Synthetic demonstration only" in element.value for element in app.info)


def test_cycle_analysis_page_renders_editable_inputs_and_state_table() -> None:
    app = AppTest.from_file(str(APP_FILE)).run()
    app.sidebar.radio[0].set_value("Cycle analysis").run()

    assert not app.exception
    assert any(element.value == "Cycle analysis" for element in app.title)
    assert any(element.label == "Compressor pressure ratio (–)" for element in app.number_input)
    assert len(app.dataframe) >= 1


def test_scenario_page_shows_synthetic_data_and_quality_metrics() -> None:
    app = AppTest.from_file(str(APP_FILE)).run()
    app.sidebar.radio[0].set_value("Scenarios & data").run()

    assert not app.exception
    assert any(element.value == "Scenarios & data" for element in app.title)
    assert any(element.label == "Random seed" for element in app.number_input)
    assert any(element.label == "Robust residual flags" for element in app.metric)


def test_synthetic_digital_twin_page_shows_state_and_provenance() -> None:
    app = AppTest.from_file(str(APP_FILE)).run()
    app.sidebar.radio[0].set_value("Synthetic digital twin").run()

    assert not app.exception
    assert any(element.value == "Synthetic digital twin" for element in app.title)
    assert any("Twin demonstrator only" in element.value for element in app.info)
    assert any("TIQ-SYNTH-GT-001" in element.value for element in app.caption)
    assert any("Synthetic residual flagged" in element.value for element in app.metric)


def test_local_document_page_returns_a_citation() -> None:
    app = AppTest.from_file(str(APP_FILE)).run()
    app.sidebar.radio[0].set_value("Technical documents").run()
    app.text_input[0].set_value("How is net cycle work estimated?").run()
    app.button[0].click().run()

    assert not app.exception
    assert any("demo_cycle_notes.md" in element.value for element in app.markdown)


def test_assistant_page_runs_local_scenario_tool() -> None:
    app = AppTest.from_file(str(APP_FILE)).run()
    app.sidebar.radio[0].set_value("Engineering assistant").run()
    app.text_area[0].set_value("Review the sensor fault scenario for anomalies.").run()
    app.button[0].click().run()

    assert not app.exception
    assert any("seeded synthetic scenario" in element.value for element in app.markdown)
