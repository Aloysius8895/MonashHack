import json

from frontend.inbox import index_attachments, parse_inbox_uploads, resolve_record_documents
from frontend.service import UploadedDocument


def upload(name, value):
    data = json.dumps(value).encode() if name.endswith(".json") else value.encode()
    return UploadedDocument(name, data)


def record(email_id="a"):
    return {"email_id": email_id, "from": "ops@example.com", "subject": "Check", "body": "Please check", "attachments": ["attachments/a_SI.txt", "attachments/a_BL.txt"]}


def test_parses_single_and_list_while_reporting_invalid_record():
    records, issues = parse_inbox_uploads([upload("one.json", record("a")), upload("many.json", [record("b"), {"bad": True}])])
    assert [item.email_id for item in records] == ["a", "b"]
    assert len(issues) == 1 and "record 2" in issues[0].location


def test_matches_basename_and_rejects_duplicate_upload_names():
    files = [upload("a_SI.txt", "SI"), upload("a_BL.txt", "BL")]
    index, issues = index_attachments(files)
    parsed, _ = parse_inbox_uploads([upload("one.json", record())])
    pair = resolve_record_documents(parsed[0], index)
    assert pair.si_document.name == "a_SI.txt" and pair.bl_document.name == "a_BL.txt"
    assert issues == () and pair.missing_names == ()
    duplicate_index, duplicate_issues = index_attachments([upload("same.txt", "a"), upload("same.txt", "b")])
    assert "same.txt" not in duplicate_index
    assert "Duplicate attachment basename" in duplicate_issues[0].message
