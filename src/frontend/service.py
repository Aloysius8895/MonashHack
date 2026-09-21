from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

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
class PipelineStep:
    name: str
    state: Literal["complete", "attention", "skipped"]
    summary: str


@dataclass(frozen=True)
class ConfidenceView:
    percent: int
    level: Literal["High", "Low"]
    reasons: tuple[str, ...]


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
    pipeline_steps: tuple[PipelineStep, ...]
    confidence: ConfidenceView


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
    confidence = _confidence(scores, runtime.review_margin_threshold, decision.status, comparison)
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
        pipeline_steps=_pipeline_steps(public_category, comparison, confidence),
        confidence=confidence,
    )


def _score_margin(scores: dict[str, float]) -> float:
    values = sorted(scores.values(), reverse=True)
    return values[0] - values[1] if len(values) > 1 else 0.0


def _confidence(scores, trained_threshold, routing_status, comparison):
    margin = _score_margin(scores)
    if routing_status == "human_review" and comparison is None:
        return ConfidenceView(45, "Low", ("The email category is not clear enough for automatic processing.",))
    if comparison is not None and comparison.status == "NEEDS_REVIEW":
        reason = comparison.review_reason
        wording = {
            "missing_attachment": "A required SI or draft BL attachment is missing.",
            "wrong_doc_type": "An attachment is not an SI or draft BL.",
            "unreadable": "A required attachment could not be read reliably.",
            "missing_value": "One or more required shipping values could not be read.",
        }.get(reason, "The available evidence is incomplete.")
        completeness = len(comparison.fields) / 7 if comparison.fields else 0
        return ConfidenceView(min(79, round(40 + completeness * 30)), "Low", (wording,))
    ratio = margin / max(trained_threshold, 0.000001)
    return ConfidenceView(min(99, round(80 + min(ratio, 4) * 4.75)), "High", ("The classification and available evidence are complete.",))


def _pipeline_steps(category, comparison, confidence):
    comparison_request = category == "BL_COMPARISON"
    has_documents = comparison is not None and bool(comparison.fields)
    needs_review = comparison_request and (comparison is None or comparison.status == "NEEDS_REVIEW" or confidence.level == "Low")
    definite = comparison_request and has_documents and not needs_review
    state = lambda condition: "complete" if condition else "skipped"
    return (
        PipelineStep("Inbox", "complete", "Email received and validated."),
        PipelineStep("Classifier", "complete", "Document comparison request." if comparison_request else "No document comparison requested."),
        PipelineStep("Document comparison request?", "complete", "Yes" if comparison_request else "No"),
        PipelineStep("Classify only", state(not comparison_request), "Category recorded; no comparison needed." if not comparison_request else "Not used."),
        PipelineStep("Attachment check", "attention" if comparison_request and not has_documents else state(comparison_request), "SI and draft BL found." if has_documents else "Required attachment unavailable."),
        PipelineStep("Extraction", state(has_documents), "Required values read from both documents." if has_documents else "Skipped."),
        PipelineStep("Normalization", state(has_documents), "Values cleaned into comparable formats." if has_documents else "Skipped."),
        PipelineStep("Comparison", state(has_documents), "Seven fields compared." if has_documents else "Skipped."),
        PipelineStep("Confidence check", state(has_documents), f"{confidence.level}, {confidence.percent}%." if has_documents else "Skipped."),
        PipelineStep("Human review", state(needs_review), confidence.reasons[0] if needs_review else "Not required."),
        PipelineStep("Final result", state(definite), "Automatic result is ready." if definite else "Not available."),
        PipelineStep("Report", "complete", "Added to the report."),
        PipelineStep("Dashboard", "complete", "Included in the session dashboard."),
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
