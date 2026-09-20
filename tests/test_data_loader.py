import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from email_classification.data_loader import (
    DatasetValidationError,
    load_and_validate,
)


class FakeInbox:
    def __init__(self, records):
        self._records = records
        self.read_bytes_calls = 0

    def emails(self):
        return self._records

    def read_bytes(self, _path):
        self.read_bytes_calls += 1
        raise AssertionError("Basic validation must not read attachment contents")


class BrokenInbox:
    def emails(self):
        raise OSError("inbox unavailable")


def make_email(email_id="email_001", attachments=None, **overrides):
    record = {
        "email_id": email_id,
        "from": "sender@example.com",
        "subject": "Please check attached documents",
        "body": "Attached are the SI and draft BL.",
        "attachments": [] if attachments is None else attachments,
    }
    record.update(overrides)
    return record


class DataLoaderTests(unittest.TestCase):
    def test_valid_records_are_detached_and_summarized(self):
        records = [make_email(), make_email("email_002", subject="", body="")]

        result = load_and_validate(FakeInbox(records))

        self.assertEqual(result.records, tuple(records))
        self.assertIsNot(result.records[0], records[0])
        self.assertEqual(result.summary.total_emails, 2)
        self.assertEqual(result.summary.valid_emails, 2)
        self.assertEqual(result.summary.invalid_emails, 0)
        self.assertEqual(result.summary.with_attachments, 0)
        self.assertEqual(result.summary.without_attachments, 2)
        self.assertEqual(result.summary.attachment_references, 0)
        self.assertEqual(result.summary.attachment_extensions, {})
        self.assertEqual(result.summary.empty_subjects, 1)
        self.assertEqual(result.summary.empty_bodies, 1)
        self.assertEqual(result.summary.validation_errors, 0)
        self.assertEqual(result.issues, ())

    def test_validated_record_is_not_changed_by_caller_mutation(self):
        record = make_email(attachments=["attachments/email_001_SI.txt"])
        result = load_and_validate(FakeInbox([record]))

        record["subject"] = "changed"
        record["attachments"].append("attachments/email_001_BL.txt")

        self.assertEqual(result.records[0]["subject"], "Please check attached documents")
        self.assertEqual(
            result.records[0]["attachments"],
            ["attachments/email_001_SI.txt"],
        )

    def test_collect_mode_reports_malformed_records(self):
        records = [
            make_email(),
            make_email("001"),
            {"email_id": "email_003"},
            make_email("email_004", subject=42),
            make_email("email_005", attachments="attachments/a.txt"),
            "not a record",
        ]

        result = load_and_validate(FakeInbox(records), strict=False)

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.summary.total_emails, 6)
        self.assertEqual(result.summary.valid_emails, 1)
        self.assertEqual(result.summary.invalid_emails, 5)
        self.assertEqual(result.summary.validation_errors, len(result.issues))
        codes = {issue.code for issue in result.issues}
        self.assertEqual(
            codes,
            {"invalid_record", "invalid_email_id", "missing_field", "invalid_field_type"},
        )

    def test_strict_mode_raises_with_all_record_issues(self):
        records = [make_email("bad"), make_email("email_002", body=17)]

        with self.assertRaises(DatasetValidationError) as raised:
            load_and_validate(FakeInbox(records))

        self.assertEqual(len(raised.exception.issues), 2)
        self.assertIn("2 issue(s)", str(raised.exception))

    def test_duplicate_email_ids_are_rejected(self):
        records = [make_email(), make_email()]

        result = load_and_validate(FakeInbox(records), strict=False)

        self.assertEqual(result.summary.valid_emails, 1)
        self.assertEqual(result.summary.invalid_emails, 1)
        self.assertEqual(result.issues[0].code, "duplicate_email_id")
        self.assertEqual(result.issues[0].email_id, "email_001")

    def test_inbox_read_failure_is_wrapped(self):
        with self.assertRaises(DatasetValidationError) as raised:
            load_and_validate(BrokenInbox())

        self.assertEqual(raised.exception.issues[0].code, "inbox_read_error")
        self.assertIn("inbox unavailable", raised.exception.issues[0].message)

    def test_existing_local_attachment_is_validated_without_being_read(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attachment_dir = root / "attachments"
            attachment_dir.mkdir()
            (attachment_dir / "email_001_SI.TXT").write_text(
                "test attachment", encoding="utf-8"
            )
            inbox = FakeInbox(
                [make_email(attachments=["attachments/email_001_SI.TXT"])]
            )

            result = load_and_validate(inbox, data_root=root)

        self.assertEqual(result.summary.attachment_references, 1)
        self.assertEqual(result.summary.attachment_extensions, {".txt": 1})
        self.assertEqual(inbox.read_bytes_calls, 0)

    def test_missing_local_attachment_is_reported(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "attachments").mkdir()

            result = load_and_validate(
                FakeInbox(
                    [make_email(attachments=["attachments/email_001_SI.txt"])]
                ),
                data_root=root,
                strict=False,
            )

        self.assertEqual(result.summary.valid_emails, 0)
        self.assertEqual(result.issues[0].code, "missing_attachment")
        self.assertEqual(
            result.issues[0].attachment,
            "attachments/email_001_SI.txt",
        )

    def test_unsafe_attachment_paths_are_rejected(self):
        unsafe_paths = [
            "../download/data_v2/ground_truth.json",
            "attachments/../../outside.txt",
            "C:/absolute/file.txt",
            "/absolute/file.txt",
            "inbox/email_001.json",
        ]

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "attachments").mkdir()
            for index, unsafe_path in enumerate(unsafe_paths, start=1):
                with self.subTest(path=unsafe_path):
                    result = load_and_validate(
                        FakeInbox(
                            [
                                make_email(
                                    f"email_{index:03d}",
                                    attachments=[unsafe_path],
                                )
                            ]
                        ),
                        data_root=root,
                        strict=False,
                    )

                    self.assertEqual(result.summary.valid_emails, 0)
                    self.assertEqual(result.issues[0].code, "invalid_attachment_path")

    def test_duplicate_attachment_references_are_rejected(self):
        path = "attachments/email_001_SI.txt"

        result = load_and_validate(
            FakeInbox([make_email(attachments=[path, path])]),
            strict=False,
        )

        self.assertEqual(result.summary.valid_emails, 0)
        self.assertEqual(result.issues[0].code, "duplicate_attachment")


if __name__ == "__main__":
    unittest.main()
