from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from contracts import DOCUMENT_FIELDS
from frontend.workbench import ProcessedEmail


@dataclass(frozen=True)
class FieldDecision:
    field: str
    choice: str
    entered_value: str | None


def apply_review(case: ProcessedEmail, outcome: str, decisions: Sequence[FieldDecision]):
    if outcome not in {"approve", "mismatch"}: raise ValueError("Unknown review outcome")
    for item in decisions:
        if item.field not in DOCUMENT_FIELDS: raise ValueError(f"Unknown field: {item.field}")
        if item.choice == "entered" and not item.entered_value: raise ValueError("Entered value is required")
    fields = tuple(item.field for item in decisions) if outcome == "mismatch" else ()
    notes = tuple(f"{item.field}: {item.choice}" for item in decisions)
    return replace(case, final_status="MISMATCH" if outcome == "mismatch" else "OK", final_defect_fields=fields, reviewed_by_human=True, review_notes=notes)


def pending_reviews(records):
    return tuple(item for item in records if item.final_status == "NEEDS_REVIEW" and not item.reviewed_by_human)


def replace_after_rerun(records, rerun):
    return tuple(rerun if item.email_id == rerun.email_id else item for item in records)
