"""Manual sanity check for the Document Intelligence extractors against the
real sample dataset. Not part of the pipeline - run directly:

    .venv\\Scripts\\python.exe src\\document_extraction\\demo.py
    .venv\\Scripts\\python.exe src\\document_extraction\\demo.py --all
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "download2"))
sys.path.insert(0, str(ROOT / "src"))

from loader import Inbox  # noqa: E402

from document_extraction import extract_from_bytes  # noqa: E402

# Hand-picked emails covering each attachment format plus the edge cases
# found while building this module.
SAMPLE_EMAIL_IDS = [
    "email_004",  # txt, clean mismatch on consignee
    "email_005",  # xlsx
    "email_055",  # docx (BL) + xlsx (SI), bilingual labels
    "email_059",  # pdf, per-container table + totals line
    "email_501",  # wrong_doc_type: commercial invoice attached as "_BL"
    "email_507",  # missing_attachment: SI only, no BL
    "email_512",  # scanned pdf (no text layer) - OCR fallback
    "email_516",  # missing_value: SI gross weight is "N/A"
]


def run_one(inbox, email_id):
    email = inbox.get(email_id)
    print(f"\n=== {email_id}: {email['subject']} ===")
    if not email["attachments"]:
        print("  (no attachments)")
        return
    for att_path in email["attachments"]:
        data = inbox.read_bytes(att_path)
        result = extract_from_bytes(data, att_path)
        print(
            f"  -- {att_path} ({result.doc_format}) "
            f"unreadable={result.unreadable} wrong_doc_type={result.wrong_doc_type}"
        )
        for name, fe in result.fields.items():
            flags = []
            if fe.missing_value:
                flags.append("MISSING")
            if fe.garbled:
                flags.append("GARBLED")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"     {name:18s} = {fe.value!r:35s} (raw {fe.raw_value!r}, {fe.evidence}){flag_str}")
        if result.missing_fields:
            print(f"     not found: {result.missing_fields}")


def run_all(inbox):
    summary = {"total_attachments": 0, "unreadable": 0, "wrong_doc_type": 0, "any_garbled": 0}
    missing_field_counts = {name: 0 for name in ("shipper", "consignee", "notify_party",
                                                   "port_of_loading", "port_of_discharge",
                                                   "container_count", "gross_weight_kg")}
    for email in inbox:
        for att_path in email["attachments"]:
            summary["total_attachments"] += 1
            data = inbox.read_bytes(att_path)
            result = extract_from_bytes(data, att_path)
            if result.unreadable:
                summary["unreadable"] += 1
            if result.wrong_doc_type:
                summary["wrong_doc_type"] += 1
            if any(fe.garbled for fe in result.fields.values()):
                summary["any_garbled"] += 1
            for name in result.missing_fields:
                missing_field_counts[name] += 1
    summary["missing_field_counts"] = missing_field_counts
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="run over every attachment, print a summary only")
    args = parser.parse_args()

    inbox = Inbox(str(ROOT / "download2"))
    if args.all:
        run_all(inbox)
    else:
        for eid in SAMPLE_EMAIL_IDS:
            run_one(inbox, eid)
