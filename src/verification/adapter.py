from __future__ import annotations

from contracts import (
    ExtractionResult,
    FieldMismatch,
    VerificationResult,
    VerificationUnavailable,
)

from .comparison import compare_documents


STATUS_MAP = {
    "OK": "match",
    "MISMATCH": "mismatch_detected",
    "NEEDS_REVIEW": "not_verified",
}


class FieldComparisonVerifier:
    def verify(self, extraction: ExtractionResult) -> VerificationResult:
        try:
            raw = compare_documents(extraction.si.to_dict(), extraction.bl.to_dict())
        except Exception as error:  # the comparator is not expected to raise
            raise VerificationUnavailable(
                f"Comparator failed for {extraction.email_id}: {error}"
            ) from error

        status = STATUS_MAP.get(str(raw.get("status")))
        if status is None:
            raise VerificationUnavailable(
                f"Comparator returned unknown status {raw.get('status')!r}"
            )

        mismatches = tuple(
            FieldMismatch(
                field=str(item["field"]),
                si=item.get("si_value"),
                bl=item.get("bl_value"),
            )
            for item in raw.get("mismatches", [])
        )
        if status == "match" and mismatches:
            raise VerificationUnavailable(
                f"Comparator reported OK for {extraction.email_id} with mismatches listed"
            )

        review_required = status == "not_verified"
        review_reason = raw.get("review_reason") if review_required else None
        if review_required and not review_reason:
            review_reason = _fallback_reason(raw)

        return VerificationResult(
            email_id=extraction.email_id,
            status=status,
            mismatches=mismatches,
            review_required=review_required,
            review_reason=review_reason,
        )


def _fallback_reason(raw: dict) -> str:
    fields = [str(item.get("field")) for item in raw.get("review_fields", [])]
    if fields:
        return f"Comparator flagged for review: {', '.join(fields)}"
    return "Comparator flagged the document pair for review"
