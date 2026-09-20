import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from email_classification.splitting import (
    SplitError,
    build_split_records,
    select_annotation_pool,
)


def alpha_token(number):
    value = number
    letters = []
    while True:
        value, remainder = divmod(value, 26)
        letters.append(chr(ord("a") + remainder))
        if value == 0:
            return "".join(reversed(letters))
        value -= 1


def make_email(email_id, subject=None, body=None, attachments=None):
    token = alpha_token(int(email_id.removeprefix("email_")))
    return {
        "email_id": email_id,
        "from": f"sender-{token}@example.com",
        "subject": subject if subject is not None else f"Unique subject {token}",
        "body": body if body is not None else f"Unique message body {token}",
        "attachments": [] if attachments is None else attachments,
    }


def make_stage_a_records():
    records = []
    for number in range(1, 521):
        email_id = f"email_{number:03d}"
        if number <= 390:
            attachments = []
        elif number <= 516:
            attachments = [
                f"attachments/{email_id}_SI.txt",
                f"attachments/{email_id}_BL.txt",
            ]
        elif number == 517:
            attachments = [f"attachments/{email_id}_SI.txt"]
        elif number == 518:
            attachments = [f"attachments/{email_id}_BL.txt"]
        else:
            attachments = [f"attachments/{email_id}_invoice.pdf"]
        records.append(make_email(email_id, attachments=attachments))

    records[1]["subject"] = records[0]["subject"]
    records[1]["body"] = records[0]["body"]
    return records


class SplitGroupingTests(unittest.TestCase):
    def test_template_variants_share_a_stable_group(self):
        records = [
            make_email(
                "email_001",
                "Reminder 100",
                "Email ops1@example.com and visit https://a.example/100",
            ),
            make_email(
                "email_002",
                "Reminder 200",
                "Email ops2@example.com and visit https://b.example/200",
            ),
            make_email("email_003", "Unrelated", "Different body"),
        ]

        first = build_split_records(records)
        second = build_split_records(records)

        self.assertEqual(first, second)
        self.assertEqual(first[0].group_id, first[1].group_id)
        self.assertNotEqual(first[0].group_id, first[2].group_id)
        self.assertRegex(first[0].group_id, r"^group_[0-9a-f]{12}$")

    def test_attachment_patterns_use_metadata_only(self):
        records = [
            make_email("email_001"),
            make_email("email_002", attachments=["attachments/a_SI.txt"]),
            make_email("email_003", attachments=["attachments/a_BL.txt"]),
            make_email(
                "email_004",
                attachments=["attachments/a_SI.txt", "attachments/a_BL.txt"],
            ),
            make_email("email_005", attachments=["attachments/invoice.pdf"]),
        ]

        result = build_split_records(records)

        self.assertEqual(
            [record.attachment_pattern for record in result],
            ["none", "si", "bl", "si_bl", "other"],
        )

    def test_stage_a_selection_is_exact_deterministic_and_group_safe(self):
        records = make_stage_a_records()

        first = select_annotation_pool(records, pool_size=120, seed=20260921)
        second = select_annotation_pool(records, pool_size=120, seed=20260921)

        self.assertEqual(first, second)
        self.assertEqual(len(first.annotation_pool), 120)
        self.assertEqual(len(first.production), 400)
        annotation_ids = {record.email_id for record in first.annotation_pool}
        production_ids = {record.email_id for record in first.production}
        self.assertFalse(annotation_ids & production_ids)
        self.assertEqual(len(annotation_ids | production_ids), 520)

        assignments = {}
        for split_name, split_records in (
            ("annotation", first.annotation_pool),
            ("production", first.production),
        ):
            for record in split_records:
                assignments.setdefault(record.group_id, set()).add(split_name)
        self.assertTrue(all(len(splits) == 1 for splits in assignments.values()))

        source_patterns = {
            record.attachment_pattern for record in build_split_records(records)
        }
        selected_patterns = {
            record.attachment_pattern for record in first.annotation_pool
        }
        self.assertEqual(selected_patterns, source_patterns)
        self.assertRegex(first.source_id_hash, r"^[0-9a-f]{64}$")

    def test_stage_a_rejects_impossible_group_preserving_size(self):
        records = [
            make_email("email_001", "Same", "Same"),
            make_email("email_002", "Same", "Same"),
            make_email("email_003", "Other", "Other"),
            make_email("email_004", "Other", "Other"),
        ]

        with self.assertRaisesRegex(SplitError, "exact annotation pool"):
            select_annotation_pool(records, pool_size=1, seed=20260921)


if __name__ == "__main__":
    unittest.main()
