from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

from frontend.inbox import InboxRecord, ResolvedDocuments
from frontend.service import DemoResult, DemoRuntime, UploadedDocument, analyze_email


@dataclass(frozen=True)
class DemoScenario:
    name: str
    record: InboxRecord
    documents: ResolvedDocuments


@dataclass(frozen=True)
class ProcessedEmail:
    email_id: str
    source: InboxRecord
    automated: DemoResult
    documents: ResolvedDocuments
    final_status: str
    final_defect_fields: tuple[str, ...]
    reviewed_by_human: bool = False
    review_notes: tuple[str, ...] = ()


def _load_record(root, email_id, new_id):
    raw = json.loads((root / "download2/inbox" / f"{email_id}.json").read_text())
    return InboxRecord(new_id, raw["from"], raw["subject"], raw["body"], tuple(raw["attachments"]))


def _upload(root, path):
    full = root / "download2" / path
    return UploadedDocument(full.name, full.read_bytes())


def build_demo_scenarios(project_root: Path):
    base = _load_record(project_root, "email_001", "demo_match")
    si = _upload(project_root, base.attachments[0]); bl = _upload(project_root, base.attachments[1])
    mismatch_bl = UploadedDocument(bl.name, bl.data.replace(b"CONSIGNEE: MOORIM SP CO., LTD", b"CONSIGNEE: OCEAN TRADE PTE LTD").replace(b"Container Count: 1 x 40'HC", b"Container Count: 2 x 40'HC"))
    classify = _load_record(project_root, "email_002", "demo_classify_only")
    return (
        DemoScenario("All fields match", base, ResolvedDocuments(si, bl, ())),
        DemoScenario("Mismatch detected", replace(base, email_id="demo_mismatch"), ResolvedDocuments(si, mismatch_bl, ())),
        DemoScenario("Missing BL attachment", replace(base, email_id="demo_missing_bl"), ResolvedDocuments(si, None, (base.attachments[1],))),
        DemoScenario("Needs human review", replace(base, email_id="demo_human_review"), ResolvedDocuments(si, UploadedDocument("unreadable_BL.pdf", b"not pdf"), ())),
        DemoScenario("Classification only", classify, ResolvedDocuments(None, None, ())),
    )


def process_scenario(runtime: DemoRuntime, scenario: DemoScenario):
    return process_record(runtime, scenario.record, scenario.documents)


def process_record(runtime, record, documents):
    result = analyze_email(runtime, record.subject, record.body, documents.si_document, documents.bl_document, record.email_id)
    submission = result.submission or {"status": "NEEDS_REVIEW", "defect_fields": []}
    return ProcessedEmail(record.email_id, record, result, documents, submission["status"], tuple(submission["defect_fields"]))


def upsert_records(existing: Sequence[ProcessedEmail], incoming: Sequence[ProcessedEmail]):
    merged = {item.email_id: item for item in existing}
    merged.update({item.email_id: item for item in incoming})
    return tuple(merged.values())
