"""Top-level entry point for the Document Intelligence module.

extract_from_bytes(data, attachment_path) is the interface the rest of the
pipeline calls: give it the raw attachment bytes (e.g. from
download2.loader.Inbox.read_bytes) and the attachment's path/filename, get
back a DocumentExtraction with the 7 canonical fields (where found),
evidence locations, and flags for anything that needs a human - a missing
value, a garbled extraction, an unreadable file, or a wrong document type.
Extraction never raises: any parse failure is captured as `unreadable`
instead of crashing the caller's loop.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from . import llm_fallback
from .extractors import docx_extractor, pdf_extractor, txt_extractor, xlsx_extractor
from .fields import CANONICAL_FIELDS, WRONG_DOC_TYPE_MARKERS
from .normalize import is_missing_placeholder, looks_garbled, parse_value

_EXTRACTORS = {
    ".txt": lambda data: txt_extractor.extract(data.decode("utf-8", errors="replace")),
    ".xlsx": xlsx_extractor.extract,
    ".docx": docx_extractor.extract,
    ".pdf": pdf_extractor.extract,
}


@dataclass
class FieldExtraction:
    raw_label: Optional[str] = None
    raw_value: Optional[object] = None
    value: Optional[object] = None
    evidence: Optional[str] = None
    missing_value: bool = False
    garbled: bool = False
    llm_used: bool = False


@dataclass
class DocumentExtraction:
    attachment_path: str
    doc_format: str
    fields: dict = field(default_factory=dict)
    missing_fields: list = field(default_factory=list)
    unreadable: bool = False
    unreadable_reason: Optional[str] = None
    wrong_doc_type: bool = False
    ocr_used: bool = False
    ocr_unavailable: bool = False

    def to_dict(self):
        return {
            "attachment_path": self.attachment_path,
            "doc_format": self.doc_format,
            "fields": {name: asdict(fe) for name, fe in self.fields.items()},
            "missing_fields": self.missing_fields,
            "unreadable": self.unreadable,
            "unreadable_reason": self.unreadable_reason,
            "wrong_doc_type": self.wrong_doc_type,
            "ocr_used": self.ocr_used,
            "ocr_unavailable": self.ocr_unavailable,
        }


def extract_from_bytes(
    data: bytes, attachment_path: str, use_llm_fallback: bool = True
) -> DocumentExtraction:
    suffix = Path(attachment_path).suffix.lower()
    extractor = _EXTRACTORS.get(suffix)
    result = DocumentExtraction(attachment_path=attachment_path, doc_format=suffix.lstrip("."))

    if extractor is None:
        result.unreadable = True
        result.unreadable_reason = f"unsupported attachment type: {suffix or 'unknown'}"
        result.missing_fields = list(CANONICAL_FIELDS)
        return result

    try:
        hits, full_text, meta = extractor(data)
    except Exception as exc:  # extraction must never crash the pipeline
        result.unreadable = True
        result.unreadable_reason = f"failed to parse {suffix} attachment: {exc}"
        result.missing_fields = list(CANONICAL_FIELDS)
        return result

    result.ocr_used = meta.get("ocr_used", False)
    result.ocr_unavailable = meta.get("ocr_unavailable", False)

    if any(marker in full_text.upper() for marker in WRONG_DOC_TYPE_MARKERS):
        result.wrong_doc_type = True

    # LLM fallback only runs for fields no alias/keyword rule matched at
    # all (not for fields already found but flagged missing_value/garbled)
    # and never for documents already known not to be an SI/BL.
    llm_recovered_fields = set()
    if use_llm_fallback and not result.wrong_doc_type:
        not_found = [name for name in CANONICAL_FIELDS if name not in hits]
        if not_found and llm_fallback.is_available():
            recovered = llm_fallback.find_missing_fields(full_text, not_found)
            for field_name, value in recovered.items():
                hits[field_name] = (
                    f"(LLM: {field_name})",
                    value,
                    f"LLM fallback ({llm_fallback.MODEL_NAME})",
                )
                llm_recovered_fields.add(field_name)

    for field_name in CANONICAL_FIELDS:
        if field_name not in hits:
            result.missing_fields.append(field_name)
            continue

        raw_label, raw_value, evidence = hits[field_name]
        missing_value = is_missing_placeholder(raw_value)
        raw_text = "" if raw_value is None else str(raw_value)
        result.fields[field_name] = FieldExtraction(
            raw_label=raw_label,
            raw_value=raw_value,
            value=None if missing_value else parse_value(field_name, raw_value),
            evidence=evidence,
            missing_value=missing_value,
            garbled=looks_garbled(raw_text),
            llm_used=field_name in llm_recovered_fields,
        )
        if missing_value:
            result.missing_fields.append(field_name)

    return result
