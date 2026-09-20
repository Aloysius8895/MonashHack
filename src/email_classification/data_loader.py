from __future__ import annotations

import copy
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
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
    valid_records: list[dict[str, object]] = []
    issues: list[ValidationIssue] = []
    seen_ids: set[str] = set()
    resolved_root = Path(data_root).resolve() if data_root is not None else None

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
            seen_attachments: set[str] = set()
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
                    continue

                normalized_attachment = attachment.replace("\\", "/")
                duplicate_key = normalized_attachment.casefold()
                if duplicate_key in seen_attachments:
                    record_issues.append(
                        ValidationIssue(
                            code="duplicate_attachment",
                            message=f"Duplicate attachment reference: {attachment}",
                            email_id=email_id,
                            field="attachments",
                            attachment=attachment,
                        )
                    )
                    continue
                seen_attachments.add(duplicate_key)

                attachment_issue = _validate_attachment_path(
                    attachment,
                    email_id=email_id,
                    data_root=resolved_root,
                )
                if attachment_issue is not None:
                    record_issues.append(attachment_issue)

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


def _validate_attachment_path(
    attachment: str,
    email_id: str | None,
    data_root: Path | None,
) -> ValidationIssue | None:
    normalized = attachment.replace("\\", "/")
    path = PurePosixPath(normalized)
    has_windows_drive = bool(re.match(r"^[A-Za-z]:/", normalized))
    is_allowed_relative_path = (
        bool(normalized)
        and not path.is_absolute()
        and not has_windows_drive
        and ".." not in path.parts
        and len(path.parts) >= 2
        and path.parts[0] == "attachments"
    )
    if not is_allowed_relative_path:
        return ValidationIssue(
            code="invalid_attachment_path",
            message="Attachment path must remain inside the attachments directory",
            email_id=email_id,
            field="attachments",
            attachment=attachment,
        )

    if data_root is None:
        return None

    attachment_root = (data_root / "attachments").resolve()
    candidate = (data_root / Path(*path.parts)).resolve()
    if not candidate.is_relative_to(attachment_root):
        return ValidationIssue(
            code="invalid_attachment_path",
            message="Resolved attachment path is outside the attachments directory",
            email_id=email_id,
            field="attachments",
            attachment=attachment,
        )
    if not candidate.is_file():
        return ValidationIssue(
            code="missing_attachment",
            message=f"Attachment file does not exist: {attachment}",
            email_id=email_id,
            field="attachments",
            attachment=attachment,
        )

    return None
