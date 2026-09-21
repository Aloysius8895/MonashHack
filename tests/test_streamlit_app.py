from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "streamlit_app.py"


def test_app_shows_input_modes_and_jev_disclosure():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()

    assert not app.exception
    assert any("Bundled example" in option for item in app.radio for option in item.options)
    assert any("JEV is not used" in item.value for item in app.caption)


def test_bundled_example_renders_classification_and_seven_fields():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()

    app.button(key="analyze").click().run()

    assert any(item.value == "BL Comparison" for item in app.metric)
    assert len(app.dataframe) >= 1
    assert app.dataframe[0].value.shape[0] == 7
