import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from email_classification.splitting import (
    ALLOWED_CATEGORIES,
    SplitError,
    build_split_records,
    finalize_labeled_split,
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


class FinalizeLabeledSplitTests(unittest.TestCase):
    def setUp(self):
        stage_a = select_annotation_pool(
            make_stage_a_records(), pool_size=120, seed=20260921
        )
        self.pool = stage_a.annotation_pool
        categories = sorted(ALLOWED_CATEGORIES)
        self.labels = {
            record.email_id: categories[index % len(categories)]
            for index, record in enumerate(self.pool)
        }

    def test_missing_labels_are_rejected(self):
        incomplete = dict(self.labels)
        incomplete.pop(next(iter(incomplete)))

        with self.assertRaisesRegex(SplitError, "missing labels"):
            finalize_labeled_split(self.pool, incomplete, 80, 40, 20260921)

    def test_unknown_label_ids_are_rejected(self):
        labels = dict(self.labels)
        labels["email_999"] = "spam"

        with self.assertRaisesRegex(SplitError, "unknown label IDs"):
            finalize_labeled_split(self.pool, labels, 80, 40, 20260921)

    def test_invalid_categories_are_rejected(self):
        labels = dict(self.labels)
        labels[next(iter(labels))] = "not_a_category"

        with self.assertRaisesRegex(SplitError, "invalid category"):
            finalize_labeled_split(self.pool, labels, 80, 40, 20260921)

    def test_sizes_must_cover_the_annotation_pool(self):
        with self.assertRaisesRegex(SplitError, "must equal annotation pool size"):
            finalize_labeled_split(self.pool, self.labels, 70, 40, 20260921)

    def test_stage_b_is_exact_deterministic_stratified_and_group_safe(self):
        first = finalize_labeled_split(
            self.pool, self.labels, 80, 40, 20260921
        )
        second = finalize_labeled_split(
            self.pool, self.labels, 80, 40, 20260921
        )

        self.assertEqual(first, second)
        self.assertEqual(len(first.development), 80)
        self.assertEqual(len(first.final_test), 40)
        development_ids = {record.email_id for record in first.development}
        test_ids = {record.email_id for record in first.final_test}
        self.assertFalse(development_ids & test_ids)
        self.assertEqual(len(development_ids | test_ids), 120)

        assignments = {}
        for split_name, split_records in (
            ("development", first.development),
            ("final_test", first.final_test),
        ):
            for record in split_records:
                assignments.setdefault(record.group_id, set()).add(split_name)
        self.assertTrue(all(len(splits) == 1 for splits in assignments.values()))

        development_categories = {self.labels[email_id] for email_id in development_ids}
        test_categories = {self.labels[email_id] for email_id in test_ids}
        self.assertEqual(development_categories, ALLOWED_CATEGORIES)
        self.assertEqual(test_categories, ALLOWED_CATEGORIES)
        self.assertRegex(first.source_id_hash, r"^[0-9a-f]{64}$")

    def test_stage_b_rejects_impossible_group_preserving_size(self):
        records = build_split_records(
            [
                make_email("email_001", "Same", "Same"),
                make_email("email_002", "Same", "Same"),
                make_email("email_003", "Other", "Other"),
                make_email("email_004", "Other", "Other"),
            ]
        )
        labels = {record.email_id: "spam" for record in records}

        with self.assertRaisesRegex(SplitError, "exact final test"):
            finalize_labeled_split(records, labels, 3, 1, 20260921)


if __name__ == "__main__":
    unittest.main()
