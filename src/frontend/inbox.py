from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Mapping, Sequence

from email_classification.routing import resolve_attachment_pair
from frontend.service import UploadedDocument


@dataclass(frozen=True)
class InboxRecord:
    email_id: str
    sender: str
    subject: str
    body: str
    attachments: tuple[str, ...]

    def as_mapping(self) -> dict[str, object]:
        return {"email_id": self.email_id, "from": self.sender, "subject": self.subject, "body": self.body, "attachments": list(self.attachments)}


@dataclass(frozen=True)
class ParseIssue:
    location: str
    message: str


@dataclass(frozen=True)
class ResolvedDocuments:
    si_document: UploadedDocument | None
    bl_document: UploadedDocument | None
    missing_names: tuple[str, ...]


def parse_inbox_uploads(files: Sequence[UploadedDocument]):
    records, issues, seen = [], [], set()
    for upload in files:
        try:
            payload = json.loads(upload.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            issues.append(ParseIssue(upload.name, f"Invalid JSON: {error}")); continue
        values = payload if isinstance(payload, list) else [payload]
        if not isinstance(payload, (dict, list)):
            issues.append(ParseIssue(upload.name, "JSON must contain an email object or list.")); continue
        for number, value in enumerate(values, 1):
            location = f"{upload.name} record {number}"
            record, issue = _validate(value, location)
            if issue: issues.append(issue)
            elif record.email_id in seen: issues.append(ParseIssue(location, f"Duplicate email ID: {record.email_id}"))
            else: seen.add(record.email_id); records.append(record)
    return tuple(records), tuple(issues)


def _validate(value, location):
    if not isinstance(value, dict): return None, ParseIssue(location, "Email record must be an object.")
    missing = [key for key in ("email_id", "from", "subject", "body", "attachments") if key not in value]
    if missing: return None, ParseIssue(location, "Missing fields: " + ", ".join(missing))
    if not all(isinstance(value[key], str) for key in ("email_id", "from", "subject", "body")):
        return None, ParseIssue(location, "Email ID, from, subject and body must be text.")
    if not isinstance(value["attachments"], list) or not all(isinstance(item, str) for item in value["attachments"]):
        return None, ParseIssue(location, "Attachments must be a list of paths.")
    return InboxRecord(value["email_id"], value["from"], value["subject"], value["body"], tuple(value["attachments"])), None


def index_attachments(files: Sequence[UploadedDocument]):
    index, issues = {}, []
    duplicates = set()
    for upload in files:
        name = PurePosixPath(upload.name.replace("\\", "/")).name
        if name in index:
            duplicates.add(name); index.pop(name, None)
        elif name not in duplicates: index[name] = upload
    for name in sorted(duplicates): issues.append(ParseIssue(name, f"Duplicate attachment basename: {name}"))
    return index, tuple(issues)


def resolve_record_documents(record: InboxRecord, index: Mapping[str, UploadedDocument]):
    si_path, bl_path = resolve_attachment_pair(record.as_mapping())
    def lookup(path):
        return None if path is None else index.get(PurePosixPath(path.replace("\\", "/")).name)
    si, bl = lookup(si_path), lookup(bl_path)
    missing = tuple(path for path, item in ((si_path, si), (bl_path, bl)) if path and item is None)
    return ResolvedDocuments(si, bl, missing)
