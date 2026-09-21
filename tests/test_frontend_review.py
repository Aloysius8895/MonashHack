from dataclasses import replace
from pathlib import Path

from frontend.review import FieldDecision, apply_review, pending_reviews
from frontend.service import load_demo_runtime
from frontend.workbench import build_demo_scenarios, process_scenario


ROOT = Path(__file__).resolve().parents[1]


def test_review_changes_final_result_but_not_automated_submission():
    scenario = build_demo_scenarios(ROOT)[3]
    case = process_scenario(load_demo_runtime(ROOT), scenario)
    automated = dict(case.automated.submission)
    resolved = apply_review(case, "mismatch", [FieldDecision("consignee", "si", None)])
    assert resolved.final_status == "MISMATCH" and resolved.reviewed_by_human
    assert resolved.automated.submission == automated
    assert pending_reviews([resolved]) == ()
