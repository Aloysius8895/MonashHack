from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from .schemas import (
    SCHEMA_VERSION,
    ClassificationResult,
    ContractError,
    ExtractionResult,
    VerificationResult,
)


CLASSIFICATION_STAGE = "classification"
EXTRACTION_STAGE = "extraction"
VERIFICATION_STAGE = "verification"

HANDOFF_FILENAMES = {
    CLASSIFICATION_STAGE: "classification.json",
    EXTRACTION_STAGE: "extraction.json",
    VERIFICATION_STAGE: "verification.json",
}

_PARSERS = {
    CLASSIFICATION_STAGE: ClassificationResult.from_dict,
    EXTRACTION_STAGE: ExtractionResult.from_dict,
    VERIFICATION_STAGE: VerificationResult.from_dict,
}


def handoff_path(handoff_dir: str | Path, stage: str) -> Path:
    if stage not in HANDOFF_FILENAMES:
        raise ContractError(f"Unknown handoff stage: {stage!r}")
    return Path(handoff_dir) / HANDOFF_FILENAMES[stage]


def write_handoff(handoff_dir: str | Path, stage: str, records: Sequence[object]) -> Path:
    target = handoff_path(handoff_dir, stage)
    payloads = [_as_payload(record) for record in records]
    email_ids = [str(payload["email_id"]) for payload in payloads]
    duplicates = sorted({value for value in email_ids if email_ids.count(value) > 1})
    if duplicates:
        raise ContractError(
            f"Handoff stage {stage} has duplicate email IDs: {', '.join(duplicates)}"
        )

    document = {
        "schema_version": SCHEMA_VERSION,
        "stage": stage,
        "records": sorted(payloads, key=lambda payload: str(payload["email_id"])),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, target)
    return target


def read_handoff(handoff_dir: str | Path, stage: str) -> tuple[object, ...]:
    if stage not in _PARSERS:
        raise ContractError(f"Unknown handoff stage: {stage!r}")
    target = handoff_path(handoff_dir, stage)
    if not target.is_file():
        raise ContractError(f"Handoff file is missing: {target}")

    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ContractError(f"Handoff file {target} is not valid JSON") from error
    if not isinstance(document, Mapping):
        raise ContractError(f"Handoff file {target} must contain an object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ContractError(
            f"Handoff file {target} has unsupported schema_version "
            f"{document.get('schema_version')!r}; expected {SCHEMA_VERSION}"
        )
    if document.get("stage") != stage:
        raise ContractError(
            f"Handoff file {target} declares stage {document.get('stage')!r}, "
            f"expected {stage!r}"
        )

    records = document.get("records")
    if not isinstance(records, list):
        raise ContractError(f"Handoff file {target} must contain a records list")
    parse = _PARSERS[stage]
    return tuple(parse(record) for record in records)


def _as_payload(record: object) -> Mapping[str, object]:
    to_dict = getattr(record, "to_dict", None)
    if not callable(to_dict):
        raise ContractError("Handoff records must expose a to_dict method")
    payload = to_dict()
    if not isinstance(payload, Mapping) or "email_id" not in payload:
        raise ContractError("Handoff records must serialise to an object with email_id")
    return payload
