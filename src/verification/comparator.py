from __future__ import annotations

from contracts import ExtractionResult, VerificationResult, VerificationUnavailable


class FieldComparisonVerifier:
    """Owned by feature/verification. Implement verify() there."""

    def verify(self, extraction: ExtractionResult) -> VerificationResult:
        raise VerificationUnavailable(
            "Document verification is not implemented; "
            "feature/verification owns src/verification"
        )
