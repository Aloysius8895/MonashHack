from __future__ import annotations

from pathlib import Path

from contracts import (
    ClassificationResult,
    DocumentFields,
    ExtractionResult,
    ExtractionUnavailable,
)


class AttachmentDocumentExtractor:
    def __init__(self, bundle_root: str | Path, use_llm_fallback: bool = True) -> None:
        self._bundle_root = Path(bundle_root)
        self._use_llm_fallback = use_llm_fallback

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
        si_path, bl_path = self.resolve(classification)
        extract_pair = _load_extract_pair()

        try:
            si_bytes = si_path.read_bytes()
            bl_bytes = bl_path.read_bytes()
        except OSError as error:
            raise ExtractionUnavailable(
                f"{classification.email_id} attachment could not be read: {error}"
            ) from error

        payload, _si_detail, _bl_detail = extract_pair(
            classification.email_id,
            si_bytes,
            str(si_path),
            bl_bytes,
            str(bl_path),
            use_llm_fallback=self._use_llm_fallback,
        )
        return ExtractionResult(
            email_id=classification.email_id,
            si=DocumentFields.from_dict(payload["si"]),
            bl=DocumentFields.from_dict(payload["bl"]),
        )


def _load_extract_pair():
    # pdfplumber/python-docx/openpyxl are imported by the format extractors at
    # module level. Import late so a missing optional parser degrades to a
    # review item instead of breaking every import of this package.
    try:
        from .contract import extract_pair
    except ImportError as error:
        raise ExtractionUnavailable(
            f"Document extraction dependencies are not installed: {error}"
        ) from error
    return extract_pair
