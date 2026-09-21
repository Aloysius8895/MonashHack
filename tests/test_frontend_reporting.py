import json
from pathlib import Path

from frontend.reporting import dashboard_summary, report_csv, submission_json
from frontend.service import load_demo_runtime
from frontend.workbench import build_demo_scenarios, process_scenario


ROOT = Path(__file__).resolve().parents[1]


def cases():
    runtime = load_demo_runtime(ROOT)
    return [process_scenario(runtime, item) for item in build_demo_scenarios(ROOT)]


def test_dashboard_and_exports_use_all_processed_cases():
    values = cases()
    summary = dashboard_summary(values)
    assert summary.emails_processed == 5
    assert summary.comparison_requests == 4
    assert summary.waiting_for_human_review == 2
    assert summary.mismatched_fields["container_count"] == 1
    assert "demo_match" in report_csv(values)
    payload = json.loads(submission_json(values))
    assert set(payload["demo_match"]) == {"category", "status", "review_reason", "defect_fields", "has_defect"}
