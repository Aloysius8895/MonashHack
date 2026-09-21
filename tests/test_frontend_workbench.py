from pathlib import Path

from frontend.service import load_demo_runtime
from frontend.workbench import build_demo_scenarios, process_scenario, upsert_records


ROOT = Path(__file__).resolve().parents[1]


def test_all_demo_scenarios_use_pipeline_and_stable_ids():
    scenarios = build_demo_scenarios(ROOT)
    results = [process_scenario(load_demo_runtime(ROOT), item) for item in scenarios]
    assert [item.email_id for item in results] == ["demo_match", "demo_mismatch", "demo_missing_bl", "demo_human_review", "demo_classify_only"]
    assert [item.automated.submission["status"] for item in results] == ["OK", "MISMATCH", "NEEDS_REVIEW", "NEEDS_REVIEW", "OK"]
    assert len(upsert_records(results, results)) == 5
