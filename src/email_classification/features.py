from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import PurePosixPath


_SI_PATTERN = re.compile(r"(?:^|[_\W])si(?:[_\W]|$)", re.I)
_BL_PATTERN = re.compile(r"(?:^|[_\W])bl(?:[_\W]|$)", re.I)
_INVOICE_PATTERN = re.compile(r"invoice", re.I)
_URL_PATTERN = re.compile(r"https?://", re.I)


def build_email_text(record: Mapping[str, object]) -> str:
    subject = _string_field(record, "subject")
    body = _string_field(record, "body")
    attachments = _attachment_names(record)
    attachment_text = " ".join(attachments) if attachments else "none"

    metadata = [
        "meta_has_attachment" if attachments else "meta_no_attachment",
        f"meta_attachment_count_{min(len(attachments), 5)}",
        "meta_empty_subject" if not subject.strip() else "meta_has_subject",
        "meta_empty_body" if not body.strip() else "meta_has_body",
        f"meta_body_length_{_length_band(len(body))}",
        f"meta_url_count_{min(len(_URL_PATTERN.findall(body)), 3)}",
    ]
    if any(_SI_PATTERN.search(name) for name in attachments):
        metadata.append("meta_has_si")
    if any(_BL_PATTERN.search(name) for name in attachments):
        metadata.append("meta_has_bl")
    if any(_INVOICE_PATTERN.search(name) for name in attachments):
        metadata.append("meta_has_invoice")
    metadata.extend(
        f"meta_ext_{PurePosixPath(name).suffix.casefold().lstrip('.') or 'none'}"
        for name in attachments
    )

    return "\n".join(
        (
            f"subject {subject}",
            f"body {body}",
            f"attachment_names {attachment_text}",
            "metadata " + " ".join(metadata),
        )
    )


def _string_field(record: Mapping[str, object], field: str) -> str:
    value = record.get(field)
    if not isinstance(value, str):
        raise ValueError(f"Email field {field} must be a string")
    return value


def _attachment_names(record: Mapping[str, object]) -> tuple[str, ...]:
    attachments = record.get("attachments")
    if not isinstance(attachments, list) or not all(
        isinstance(item, str) for item in attachments
    ):
        raise ValueError("Email field attachments must be a list of strings")
    return tuple(
        PurePosixPath(item.replace("\\", "/")).name for item in attachments
    )


def _length_band(length: int) -> str:
    if length == 0:
        return "empty"
    if length < 80:
        return "short"
    if length < 400:
        return "medium"
    return "long"
