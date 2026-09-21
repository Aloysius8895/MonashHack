"""Adapter between this module's internal DocumentExtraction/FieldExtraction
(raw values, evidence, missing/garbled/OCR/LLM flags - useful for debugging
and human review) and the flat shape docs/data_contract.md specifies for
handoff to the rest of the pipeline:

    {
      "email_id": "...",
      "si": {"shipper": "...", ..., "container_count": 3, "gross_weight_kg": 22000},
      "bl": {"shipper": "...", ..., "container_count": 4, "gross_weight_kg": 22000}
    }

The richer DocumentExtraction objects aren't discarded - callers that want
evidence/confidence detail (e.g. a human-review UI) should keep using
extract_from_bytes() directly and only reach for this adapter at the point
where a plain value needs to cross into another module's contract.
"""
from .extract import extract_from_bytes
from .fields import CANONICAL_FIELDS


def _field_values(document_extraction):
    values = {}
    for field_name in CANONICAL_FIELDS:
        field_extraction = document_extraction.fields.get(field_name)
        values[field_name] = field_extraction.value if field_extraction is not None else None
    return values


def to_contract_shape(email_id, si_extraction, bl_extraction):
    """Build the docs/data_contract.md extraction-output shape from two
    already-computed DocumentExtraction objects (SI and BL)."""
    return {
        "email_id": email_id,
        "si": _field_values(si_extraction),
        "bl": _field_values(bl_extraction),
    }


def extract_pair(email_id, si_data, si_path, bl_data, bl_path, use_llm_fallback=True):
    """Convenience one-shot call: extract both attachments and return the
    contract-shaped dict, plus the two full DocumentExtraction objects
    (for review-UI/debugging use, not part of the contract itself).

    Returns (contract_dict, si_extraction, bl_extraction).
    """
    si_extraction = extract_from_bytes(si_data, si_path, use_llm_fallback=use_llm_fallback)
    bl_extraction = extract_from_bytes(bl_data, bl_path, use_llm_fallback=use_llm_fallback)
    contract_dict = to_contract_shape(email_id, si_extraction, bl_extraction)
    return contract_dict, si_extraction, bl_extraction
