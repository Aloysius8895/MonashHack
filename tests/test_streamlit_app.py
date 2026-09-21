from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).resolve().parents[1] / "streamlit_app.py"


def test_app_uses_real_inputs_without_prepared_demo_controls():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    assert not app.exception
    assert [item.label for item in app.tabs] == ["Input & Run", "Human Review (0)", "Report", "Dashboard"]
    assert app.file_uploader(key="inbox_uploads").multiple_files
    assert app.text_input(key="manual_subject").label == "Email subject"
    assert app.text_area(key="manual_body").label == "Email body"
    assert all(button.key not in {"run_selected_demo", "run_all_demos"} for button in app.button)
    assert all(selectbox.key != "demo_scenario" for selectbox in app.selectbox)
    assert any("JEV is not used" in item.value for item in app.caption)
