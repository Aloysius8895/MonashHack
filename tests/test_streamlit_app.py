from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def test_app_has_workbench_tabs_inputs_and_jev_disclosure():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    assert not app.exception
    assert [item.label for item in app.tabs] == ["Input & Run", "Human Review (0)", "Report", "Dashboard"]
    assert app.button(key="run_all_demos").label == "Run all demo scenarios"
    assert app.file_uploader(key="inbox_uploads").multiple_files
    assert any("JEV is not used" in item.value for item in app.caption)


def test_run_all_populates_report_dashboard_and_review_queue():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    app.button(key="run_all_demos").click().run()
    assert not app.exception
    assert [item.label for item in app.tabs][1] == "Human Review (2)"
    assert any(item.label == "Emails processed" and item.value == "5" for item in app.metric)
    assert any("ACTION REQUIRED" in item.value for item in app.error)
    assert any(frame.value.shape[0] == 7 for frame in app.dataframe)
    comparison = next(frame.value for frame in app.dataframe if frame.value.shape[0] == 7)
    assert all(isinstance(value, str) for value in comparison["SI value"])
    assert all(isinstance(value, str) for value in comparison["BL value"])
    assert all(item.label != "View full workflow diagram" for item in app.expander)


def test_selected_classification_only_scenario_records_no_action_result():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    app.selectbox(key="demo_scenario").select("Classification only").run()
    app.button(key="run_selected_demo").click().run()
    assert any("CLASSIFIED ONLY" in item.value for item in app.info)
    assert any(item.label == "Emails processed" and item.value == "1" for item in app.metric)
