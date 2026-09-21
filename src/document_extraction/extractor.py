from __future__ import annotations

from pathlib import Path

from contracts import ClassificationResult, ExtractionResult, ExtractionUnavailable


class AttachmentDocumentExtractor:
    """Owned by feature/document-extraction. Implement extract() there."""

    def __init__(self, bundle_root: str | Path) -> None:
        self._bundle_root = Path(bundle_root)

    def resolve(self, classification: ClassificationResult) -> tuple[Path, Path]:
        if not classification.attachments.is_complete:
            raise ExtractionUnavailable(
                f"{classification.email_id} has no SI/BL attachment pair"
            )
        si = self._bundle_root / str(classification.attachments.si)
        bl = self._bundle_root / str(classification.attachments.bl)
        missing = [str(path) for path in (si, bl) if not path.is_file()]
        if missing:
            raise ExtractionUnavailable(
                f"{classification.email_id} attachment is missing: {', '.join(missing)}"
            )
        return si, bl

    def extract(self, classification: ClassificationResult) -> ExtractionResult:
        self.resolve(classification)
        raise ExtractionUnavailable(
            "Document extraction is not implemented; "
            "feature/document-extraction owns src/document_extraction"
        )
