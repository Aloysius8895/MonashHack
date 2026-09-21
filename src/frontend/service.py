from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib

from contracts import DOCUMENT_FIELDS
from document_extraction.extract import DocumentExtraction, FieldExtraction, extract_from_bytes
from email_classification.features import build_email_text
from email_classification.modeling import score_mapping
from email_classification.routing import route_prediction
from verification.comparison import compare_documents


PUBLIC_CATEGORIES = {
    "bl_comparison": "BL_COMPARISON",
    "new_si_request": "SI_REQUEST",
    "invoice_query": "INVOICE_QUERY",
    "general_message": "GENERAL",
    "spam": "SPAM",
}


class DemoConfigurationError(RuntimeError):
    """Raised when committed runtime artifacts cannot be loaded."""


@dataclass(frozen=True)
class UploadedDocument:
    name: str
    data: bytes


@dataclass(frozen=True)
class DemoRuntime:
    model: Any
    review_margin_threshold: float


@dataclass(frozen=True)
class EvidenceView:
    document_role: str
    filename: str
    raw_label: str | None
    raw_value: object
    location: str | None
    ocr_used: bool
    llm_used: bool
    garbled: bool


@dataclass(frozen=True)
class FieldComparisonView:
    field: str
    si_value: object
    bl_value: object
    normalized_si: object
    normalized_bl: object
    status: str
    reason: str
    si_evidence: EvidenceView
    bl_evidence: EvidenceView


@dataclass(frozen=True)
class ComparisonView:
    status: str
    review_reason: str | None
    fields: tuple[FieldComparisonView, ...]


@dataclass(frozen=True)
class DemoResult:
    email_id: str
    category: str
    scores: dict[str, float]
    route: str
    routing_status: str
    routing_reason: str
    rules_fired: tuple[str, ...]
    comparison: ComparisonView | None
    submission: dict[str, object] | None


def load_demo_runtime(project_root: str | Path) -> DemoRuntime:
    root = Path(project_root)
    model_path = root / "artifacts/classification/selected_model.joblib"
    summary_path = root / "artifacts/classification/run_summary.json"
    try:
        model = joblib.load(model_path)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        threshold = float(summary["review_margin_threshold"])
    except Exception as error:
        raise DemoConfigurationError(
            "The classification model or its runtime summary could not be loaded."
        ) from error
    return DemoRuntime(model=model, review_margin_threshold=threshold)


def analyze_email(
    runtime: DemoRuntime,
    subject: str,
    body: str,
    si_document: UploadedDocument | None,
    bl_document: UploadedDocument | None,
    email_id: str = "demo_email",
) -> DemoResult:
    attachments = []
    if si_document is not None:
        attachments.append(_role_aware_name(si_document.name, "SI"))
    if bl_document is not None:
        attachments.append(_role_aware_name(bl_document.name, "BL"))
    record = {
        "email_id": email_id,
        "subject": str(subject),
        "body": str(body),
        "attachments": attachments,
    }
    text = build_email_text(record)
    predicted = str(runtime.model.predict([text])[0])
    scores = score_mapping(runtime.model, [text])[0]
    decision = route_prediction(
        record,
        predicted,
        scores,
        runtime.review_margin_threshold,
    )
    public_category = PUBLIC_CATEGORIES[decision.category]
    comparison = None
    submission = _submission(public_category)
    if public_category == "BL_COMPARISON":
        classification_needs_review = (
            decision.status == "human_review"
            and si_document is not None
            and bl_document is not None
        )
        if classification_needs_review:
            submission = None
        else:
            comparison, submission = _analyze_documents(
                public_category, si_document, bl_document
            )
    return DemoResult(
        email_id=email_id,
        category=public_category,
        scores={PUBLIC_CATEGORIES[name]: value for name, value in scores.items()},
        route=decision.route,
        routing_status=decision.status,
        routing_reason=decision.reason,
        rules_fired=decision.rules_fired,
        comparison=comparison,
        submission=submission,
    )


def _role_aware_name(original_name: str, role: str) -> str:
    suffix = Path(original_name).suffix
    return f"attachments/upload_{role}{suffix}"


def _submission(
    category: str,
    status: str = "OK",
    review_reason: str | None = None,
    defect_fields: list[str] | None = None,
) -> dict[str, object]:
    defects = defect_fields or []
    return {
        "category": category,
        "status": status,
        "review_reason": review_reason,
        "defect_fields": defects,
        "has_defect": status == "MISMATCH" and bool(defects),
    }


def _analyze_documents(
    category: str,
    si_document: UploadedDocument | None,
    bl_document: UploadedDocument | None,
) -> tuple[ComparisonView, dict[str, object]]:
    if si_document is None or bl_document is None:
        comparison = ComparisonView(
            status="NEEDS_REVIEW", review_reason="missing_attachment", fields=()
        )
        return comparison, _submission(
            category, status="NEEDS_REVIEW", review_reason="missing_attachment"
        )

    si_extraction = extract_from_bytes(
        si_document.data, si_document.name, use_llm_fallback=False
    )
    bl_extraction = extract_from_bytes(
        bl_document.data, bl_document.name, use_llm_fallback=False
    )
    si_values = _values(si_extraction)
    bl_values = _values(bl_extraction)
    raw_comparison = compare_documents(si_values, bl_values)
    fields = tuple(
        _field_view(
            field,
            raw_comparison["field_results"][field],
            si_extraction,
            bl_extraction,
            si_document.name,
            bl_document.name,
        )
        for field in DOCUMENT_FIELDS
    )

    review_reason = _review_reason(si_extraction, bl_extraction)
    mismatch_fields = [row.field for row in fields if row.status == "MISMATCH"]
    if review_reason is not None:
        status = "NEEDS_REVIEW"
        submission = _submission(
            category, status=status, review_reason=review_reason
        )
    elif mismatch_fields:
        status = "MISMATCH"
        submission = _submission(
            category, status=status, defect_fields=mismatch_fields
        )
    else:
        status = "OK"
        submission = _submission(category)

    return ComparisonView(status=status, review_reason=review_reason, fields=fields), submission


def _values(extraction: DocumentExtraction) -> dict[str, object]:
    return {
        field: extraction.fields[field].value if field in extraction.fields else None
        for field in DOCUMENT_FIELDS
    }


def _review_reason(
    si_extraction: DocumentExtraction, bl_extraction: DocumentExtraction
) -> str | None:
    extractions = (si_extraction, bl_extraction)
    if any(item.wrong_doc_type for item in extractions):
        return "wrong_doc_type"
    if any(item.unreadable or item.ocr_unavailable for item in extractions):
        return "unreadable"
    if any(item.missing_fields for item in extractions):
        return "missing_value"
    if any(field.garbled for item in extractions for field in item.fields.values()):
        return "unreadable"
    return None


def _field_view(
    field: str,
    comparison: dict[str, object],
    si_extraction: DocumentExtraction,
    bl_extraction: DocumentExtraction,
    si_filename: str,
    bl_filename: str,
) -> FieldComparisonView:
    return FieldComparisonView(
        field=field,
        si_value=comparison.get("si_value"),
        bl_value=comparison.get("bl_value"),
        normalized_si=comparison.get("normalized_si"),
        normalized_bl=comparison.get("normalized_bl"),
        status=str(comparison["status"]),
        reason=str(comparison["reason"]),
        si_evidence=_evidence("SI", si_filename, si_extraction, field),
        bl_evidence=_evidence("Draft BL", bl_filename, bl_extraction, field),
    )


def _evidence(
    role: str,
    filename: str,
    extraction: DocumentExtraction,
    field: str,
) -> EvidenceView:
    detail = extraction.fields.get(field, FieldExtraction())
    return EvidenceView(
        document_role=role,
        filename=filename,
        raw_label=detail.raw_label,
        raw_value=detail.raw_value,
        location=detail.evidence,
        ocr_used=extraction.ocr_used,
        llm_used=detail.llm_used,
        garbled=detail.garbled,
    )
