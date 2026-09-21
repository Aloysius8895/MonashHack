import sys
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from frontend.service import (
    PUBLIC_CATEGORIES,
    DemoConfigurationError,
    DemoRuntime,
    UploadedDocument,
    analyze_email,
    load_demo_runtime,
)


class FakeModel:
    classes_ = np.array(
        ["bl_comparison", "general_message", "invoice_query", "new_si_request", "spam"]
    )

    def __init__(self, category: str):
        self.category = category

    def predict(self, texts):
        return np.array([self.category for _ in texts])

    def decision_function(self, texts):
        row = [-4.0 for _ in self.classes_]
        row[list(self.classes_).index(self.category)] = 4.0
        return np.array([row for _ in texts])


class LowMarginComparisonModel(FakeModel):
    def __init__(self):
        super().__init__("bl_comparison")

    def decision_function(self, texts):
        row = [0.11, 0.10, 0.0, -0.1, -0.2]
        return np.array([row for _ in texts])


def fake_runtime(category: str) -> DemoRuntime:
    return DemoRuntime(model=FakeModel(category), review_margin_threshold=0.2)


def text_document(name: str, *, container_count="3", gross_weight="22,000 KG"):
    content = f"""SHIPPER: ABC Trading
CONSIGNEE: XYZ Logistics
NOTIFY PARTY: DEF Shipping
PORT OF LOADING: Port Klang
PORT OF DISCHARGE: Singapore
CONTAINER COUNT: {container_count}
GROSS WEIGHT (KG): {gross_weight}
"""
    return UploadedDocument(name=name, data=content.encode())


def test_maps_all_internal_categories_to_official_names():
    assert PUBLIC_CATEGORIES == {
        "bl_comparison": "BL_COMPARISON",
        "new_si_request": "SI_REQUEST",
        "invoice_query": "INVOICE_QUERY",
        "general_message": "GENERAL",
        "spam": "SPAM",
    }


def test_non_comparison_result_stops_before_document_extraction():
    result = analyze_email(
        fake_runtime("spam"), "Account update", "Routine account message", None, None
    )

    assert result.category == "SPAM"
    assert result.comparison is None
    assert result.submission == {
        "category": "SPAM",
        "status": "OK",
        "review_reason": None,
        "defect_fields": [],
        "has_defect": False,
    }


def test_complete_pair_returns_seven_traceable_field_rows():
    result = analyze_email(
        fake_runtime("bl_comparison"),
        "Please verify SI and BL",
        "Attached for comparison",
        text_document("customer-instructions.txt"),
        text_document("carrier-draft.txt", gross_weight="22000"),
    )

    assert result.comparison is not None
    assert len(result.comparison.fields) == 7
    assert result.comparison.fields[0].si_evidence.raw_value is not None
    assert result.submission["status"] == "OK"


def test_missing_bl_uses_official_review_reason():
    result = analyze_email(
        fake_runtime("bl_comparison"),
        "Please verify SI and BL",
        "Attached for comparison",
        text_document("instructions.txt"),
        None,
    )

    assert result.submission["status"] == "NEEDS_REVIEW"
    assert result.submission["review_reason"] == "missing_attachment"


def test_container_mismatch_is_reported_in_detail_and_submission():
    result = analyze_email(
        fake_runtime("bl_comparison"),
        "Please verify SI and BL",
        "Attached for comparison",
        text_document("si-source.txt", container_count="3"),
        text_document("bl-source.txt", container_count="4"),
    )

    mismatch = next(row for row in result.comparison.fields if row.field == "container_count")
    assert mismatch.status == "MISMATCH"
    assert mismatch.normalized_si == 3
    assert mismatch.normalized_bl == 4
    assert result.submission == {
        "category": "BL_COMPARISON",
        "status": "MISMATCH",
        "review_reason": None,
        "defect_fields": ["container_count"],
        "has_defect": True,
    }


def test_wrong_document_type_uses_official_review_reason():
    wrong = UploadedDocument(
        name="mystery.txt",
        data=b"COMMERCIAL INVOICE\nINVOICE NUMBER: 42\n",
    )
    result = analyze_email(
        fake_runtime("bl_comparison"),
        "Please verify SI and BL",
        "Attached for comparison",
        wrong,
        text_document("draft.txt"),
    )

    assert result.submission["status"] == "NEEDS_REVIEW"
    assert result.submission["review_reason"] == "wrong_doc_type"


def test_unreadable_document_uses_official_review_reason():
    broken = UploadedDocument(name="broken.pdf", data=b"not a pdf")
    result = analyze_email(
        fake_runtime("bl_comparison"),
        "Please verify SI and BL",
        "Attached for comparison",
        broken,
        text_document("draft.txt"),
    )

    assert result.submission["status"] == "NEEDS_REVIEW"
    assert result.submission["review_reason"] == "unreadable"


def test_missing_value_keeps_reliable_mismatch_visible():
    si = text_document("si.txt")
    bl_text = """SHIPPER: ABC Trading
CONSIGNEE:
NOTIFY PARTY: DEF Shipping
PORT OF LOADING: Port Klang
PORT OF DISCHARGE: Singapore
CONTAINER COUNT: 4
GROSS WEIGHT (KG): 22000
"""
    result = analyze_email(
        fake_runtime("bl_comparison"),
        "Please verify SI and BL",
        "Attached for comparison",
        si,
        UploadedDocument(name="bl.txt", data=bl_text.encode()),
    )

    assert result.submission["status"] == "NEEDS_REVIEW"
    assert result.submission["review_reason"] == "missing_value"
    container_row = next(
        row for row in result.comparison.fields if row.field == "container_count"
    )
    assert container_row.status == "MISMATCH"


def test_incompatible_model_artifact_is_a_configuration_error(tmp_path):
    artifacts = tmp_path / "artifacts" / "classification"
    artifacts.mkdir(parents=True)
    (artifacts / "selected_model.joblib").write_bytes(b"not a joblib artifact")
    (artifacts / "run_summary.json").write_text(
        '{"review_margin_threshold": 0.2}', encoding="utf-8"
    )

    try:
        load_demo_runtime(tmp_path)
    except DemoConfigurationError:
        pass
    else:
        raise AssertionError("incompatible model must raise DemoConfigurationError")


def test_any_model_deserialization_failure_is_a_configuration_error(tmp_path):
    artifacts = tmp_path / "artifacts" / "classification"
    artifacts.mkdir(parents=True)
    (artifacts / "selected_model.joblib").write_bytes(b"placeholder")
    (artifacts / "run_summary.json").write_text(
        '{"review_margin_threshold": 0.2}', encoding="utf-8"
    )

    with patch("frontend.service.joblib.load", side_effect=RuntimeError("version mismatch")):
        try:
            load_demo_runtime(tmp_path)
        except DemoConfigurationError:
            pass
        else:
            raise AssertionError("all model load failures must be safe configuration errors")


def test_uncertain_bl_classification_does_not_claim_document_result():
    runtime = DemoRuntime(
        model=LowMarginComparisonModel(), review_margin_threshold=0.2
    )

    result = analyze_email(
        runtime,
        "Documents attached",
        "Please review the attached files",
        text_document("instructions.txt"),
        text_document("draft.txt"),
    )

    assert result.routing_status == "human_review"
    assert result.comparison is None
    assert result.submission is None


def test_bundled_email_001_runs_real_model_extraction_and_comparison():
    record = json.loads(
        (PROJECT_ROOT / "download2/inbox/email_001.json").read_text(encoding="utf-8")
    )
    si_path = PROJECT_ROOT / "download2" / record["attachments"][0]
    bl_path = PROJECT_ROOT / "download2" / record["attachments"][1]

    result = analyze_email(
        load_demo_runtime(PROJECT_ROOT),
        record["subject"],
        record["body"],
        UploadedDocument(si_path.name, si_path.read_bytes()),
        UploadedDocument(bl_path.name, bl_path.read_bytes()),
        email_id=record["email_id"],
    )

    assert result.category == "BL_COMPARISON"
    assert result.comparison is not None
    assert len(result.comparison.fields) == 7
    assert set(result.submission) == {
        "category", "status", "review_reason", "defect_fields", "has_defect"
    }
