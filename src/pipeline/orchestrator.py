from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from contracts import (
    ClassificationResult,
    DocumentExtractor,
    ExtractionResult,
    ExtractionUnavailable,
    VerificationResult,
    VerificationUnavailable,
    Verifier,
)


@dataclass(frozen=True)
class PipelineOutcome:
    extractions: tuple[ExtractionResult, ...]
    verifications: tuple[VerificationResult, ...]
    skipped: tuple[str, ...]

    @property
    def review_required(self) -> tuple[str, ...]:
        return tuple(
            result.email_id for result in self.verifications if result.review_required
        )


def run_verification_pipeline(
    classifications: Sequence[ClassificationResult],
    extractor: DocumentExtractor,
    verifier: Verifier,
) -> PipelineOutcome:
    extractions: list[ExtractionResult] = []
    verifications: list[VerificationResult] = []
    skipped: list[str] = []

    for classification in sorted(classifications, key=lambda item: item.email_id):
        if not classification.should_compare:
            skipped.append(classification.email_id)
            continue

        try:
            extraction = extractor.extract(classification)
        except ExtractionUnavailable as error:
            verifications.append(
                _not_verified(classification.email_id, f"Extraction failed: {error}")
            )
            continue

        if extraction.email_id != classification.email_id:
            raise ValueError(
                f"Extractor returned {extraction.email_id} for {classification.email_id}"
            )
        extractions.append(extraction)

        try:
            verification = verifier.verify(extraction)
        except VerificationUnavailable as error:
            verifications.append(
                _not_verified(classification.email_id, f"Verification failed: {error}")
            )
            continue

        if verification.email_id != classification.email_id:
            raise ValueError(
                f"Verifier returned {verification.email_id} for {classification.email_id}"
            )
        verifications.append(verification)

    return PipelineOutcome(
        extractions=tuple(extractions),
        verifications=tuple(verifications),
        skipped=tuple(skipped),
    )


def _not_verified(email_id: str, reason: str) -> VerificationResult:
    return VerificationResult(
        email_id=email_id,
        status="not_verified",
        mismatches=(),
        review_required=True,
        review_reason=reason,
    )
