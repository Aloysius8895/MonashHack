from __future__ import annotations

import copy
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


_EMAIL_ID_PATTERN = re.compile(r"^email_\d{3}$")
_REQUIRED_TYPES = {
    "email_id": str,
    "from": str,
    "subject": str,
    "body": str,
    "attachments": list,
}


class InboxLike(Protocol):
    def emails(self) -> Iterable[Mapping[str, object]]:
        raise NotImplementedError


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    email_id: str | None = None
    field: str | None = None
    attachment: str | None = None


@dataclass(frozen=True)
class DatasetSummary:
    total_emails: int
    valid_emails: int
    invalid_emails: int
    with_attachments: int
    without_attachments: int
    attachment_references: int
    attachment_extensions: dict[str, int]
    empty_subjects: int
    empty_bodies: int
    validation_errors: int


@dataclass(frozen=True)
class ValidationResult:
    records: tuple[dict[str, object], ...]
    summary: DatasetSummary
    issues: tuple[ValidationIssue, ...]


class DatasetValidationError(ValueError):
    def __init__(self, issues: Sequence[ValidationIssue]):
        self.issues = tuple(issues)
        super().__init__(
            f"Dataset validation failed with {len(self.issues)} issue(s)"
        )


def load_and_validate(
    inbox: InboxLike,
    data_root: str | Path | None = None,
    strict: bool = True,
) -> ValidationResult:
    try:
        records = list(inbox.emails())
    except Exception as exc:
        issue = ValidationIssue(
            code="inbox_read_error",
            message=f"Could not read inbox: {exc}",
        )
        raise DatasetValidationError((issue,)) from exc

    return _validate_records(records, data_root=data_root, strict=strict)


def _validate_records(
    records: Sequence[object],
    data_root: str | Path | None,
    strict: bool,
) -> ValidationResult:
    del data_root  # Local attachment checks are added separately.

    valid_records: list[dict[str, object]] = []
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()

    for record in records:
        record_issues: list[ValidationIssue] = []
        if not isinstance(record, Mapping):
            issues.append(
                ValidationIssue(
                    code="invalid_record",
                    message="Email record must be a mapping",
                )
            )
            continue

        raw_email_id = record.get("email_id")
        email_id = raw_email_id if isinstance(raw_email_id, str) else None

        for field, expected_type in _REQUIRED_TYPES.items():
            if field not in record:
                record_issues.append(
                    ValidationIssue(
                        code="missing_field",
                        message=f"Required field is missing: {field}",
                        email_id=email_id,
                        field=field,
                    )
                )
            elif not isinstance(record[field], expected_type):
                record_issues.append(
                    ValidationIssue(
                        code="invalid_field_type",
                        message=(
                            f"Field {field} must be {expected_type.__name__}, "
                            f"not {type(record[field]).__name__}"
                        ),
                        email_id=email_id,
                        field=field,
                    )
                )

        if isinstance(raw_email_id, str):
            if not _EMAIL_ID_PATTERN.fullmatch(raw_email_id):
                record_issues.append(
                    ValidationIssue(
                        code="invalid_email_id",
                        message="email_id must match email_NNN",
                        email_id=raw_email_id,
                        field="email_id",
                    )
                )
            elif raw_email_id in seen_ids:
                record_issues.append(
                    ValidationIssue(
                        code="duplicate_email_id",
                        message=f"Duplicate email_id: {raw_email_id}",
                        email_id=raw_email_id,
                        field="email_id",
                    )
                )
            else:
                seen_ids.add(raw_email_id)

        attachments = record.get("attachments")
        if isinstance(attachments, list):
            for attachment in attachments:
                if not isinstance(attachment, str):
                    record_issues.append(
                        ValidationIssue(
                            code="invalid_field_type",
                            message="Every attachment path must be a string",
                            email_id=email_id,
                            field="attachments",
                        )
                    )

        if record_issues:
            issues.extend(record_issues)
            continue

        valid_records.append(copy.deepcopy(dict(record)))

    extension_counts: Counter[str] = Counter()
    with_attachments = 0
    empty_subjects = 0
    empty_bodies = 0
    attachment_references = 0

    for record in valid_records:
        attachments = record["attachments"]
        if not isinstance(attachments, list):
            raise AssertionError("Validated attachments must be a list")
        if attachments:
            with_attachments += 1
        attachment_references += len(attachments)
        for attachment in attachments:
            if not isinstance(attachment, str):
                raise AssertionError("Validated attachment paths must be strings")
            extension_counts[Path(attachment).suffix.lower() or "<none>"] += 1

        if not str(record["subject"]).strip():
            empty_subjects += 1
        if not str(record["body"]).strip():
            empty_bodies += 1

    summary = DatasetSummary(
        total_emails=len(records),
        valid_emails=len(valid_records),
        invalid_emails=len(records) - len(valid_records),
        with_attachments=with_attachments,
        without_attachments=len(valid_records) - with_attachments,
        attachment_references=attachment_references,
        attachment_extensions=dict(sorted(extension_counts.items())),
        empty_subjects=empty_subjects,
        empty_bodies=empty_bodies,
        validation_errors=len(issues),
    )
    result = ValidationResult(
        records=tuple(valid_records),
        summary=summary,
        issues=tuple(issues),
    )

    if strict and issues:
        raise DatasetValidationError(issues)

    return result
