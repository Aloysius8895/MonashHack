from __future__ import annotations

from typing import Protocol, runtime_checkable

from .schemas import ClassificationResult, ExtractionResult, VerificationResult


class ExtractionUnavailable(RuntimeError):
    pass


class VerificationUnavailable(RuntimeError):
    pass


@runtime_checkable
class DocumentExtractor(Protocol):
    def extract(self, classification: ClassificationResult) -> ExtractionResult:
        ...


@runtime_checkable
class Verifier(Protocol):
    def verify(self, extraction: ExtractionResult) -> VerificationResult:
        ...
