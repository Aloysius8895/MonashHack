import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from email_classification.cross_validation import (
    CATEGORY_LABEL_MAP,
    CrossValidationError,
    build_cross_validation_plan,
)


def make_records():
    labels = (
        [("Document Comparison", "comparison")] * 220
        + [("New SI Request", "new-si")] * 125
        + [("Invoice Query", "invoice")] * 75
        + [("General Message", "general")] * 60
        + [("Spam", "spam")] * 40
    )
    records = []
    annotations = {}
    for index, (label, token) in enumerate(labels, start=1):
        email_id = f"email_{index:03d}"
        unique_token = f"token{chr(97 + index % 26)}{chr(97 + (index // 26) % 26)}{chr(97 + (index // 676) % 26)}"
        records.append(
            {
                "email_id": email_id,
                "subject": f"{token} subject {unique_token}",
                "body": f"{token} body {unique_token}",
                "attachments": [],
            }
        )
        annotations[email_id] = label

    # Two same-category template variants must stay in one fold.
    records[0]["subject"] = "Comparison shipment 100"
    records[0]["body"] = "Compare ops1@example.com reference 100"
    records[1]["subject"] = "Comparison shipment 200"
    records[1]["body"] = "Compare ops2@example.com reference 200"
    return records, annotations


class CrossValidationTests(unittest.TestCase):
    def test_builds_deterministic_stratified_grouped_folds(self):
        records, labels = make_records()

        first = build_cross_validation_plan(records, labels)
        second = build_cross_validation_plan(list(reversed(records)), labels)

        self.assertEqual(first, second)
        self.assertEqual(first.n_splits, 5)
        self.assertEqual(first.seed, 20260921)
        self.assertEqual(len(first.assignments), 520)
        self.assertEqual(len({item.email_id for item in first.assignments}), 520)
        self.assertEqual({item.fold for item in first.assignments}, {1, 2, 3, 4, 5})
        self.assertEqual(
            Counter(item.category for item in first.assignments),
            Counter(
                {
                    "bl_comparison": 220,
                    "new_si_request": 125,
                    "invoice_query": 75,
                    "general_message": 60,
                    "spam": 40,
                }
            ),
        )

        folds_by_group = defaultdict(set)
        for item in first.assignments:
            folds_by_group[item.group_id].add(item.fold)
        self.assertTrue(all(len(folds) == 1 for folds in folds_by_group.values()))
        self.assertEqual(first.assignments[0].fold, first.assignments[1].fold)

        expected_categories = set(CATEGORY_LABEL_MAP.values())
        self.assertEqual(len(first.folds), 5)
        for summary in first.folds:
            self.assertEqual(set(dict(summary.validation_category_counts)), expected_categories)
            self.assertEqual(summary.training_size + summary.validation_size, 520)
            self.assertEqual(
                sum(dict(summary.validation_category_counts).values()),
                summary.validation_size,
            )

    def test_rejects_missing_unknown_and_invalid_labels(self):
        records, labels = make_records()
        missing = dict(labels)
        missing.pop("email_001")
        with self.assertRaisesRegex(CrossValidationError, "missing labels"):
            build_cross_validation_plan(records, missing)

        unknown = dict(labels)
        unknown["email_999"] = "Spam"
        with self.assertRaisesRegex(CrossValidationError, "unknown label IDs"):
            build_cross_validation_plan(records, unknown)

        invalid = dict(labels)
        invalid["email_001"] = "Comparison"
        with self.assertRaisesRegex(CrossValidationError, "invalid category"):
            build_cross_validation_plan(records, invalid)

    def test_keeps_a_mixed_category_group_together(self):
        records, labels = make_records()
        labels["email_002"] = "Spam"

        plan = build_cross_validation_plan(records, labels)

        self.assertEqual(plan.assignments[0].fold, plan.assignments[1].fold)

    def test_rejects_too_few_members_of_a_category(self):
        records = [
            {
                "email_id": f"email_{index:03d}",
                "subject": f"subject token{chr(97 + index)}",
                "body": f"body token{chr(97 + index)}",
                "attachments": [],
            }
            for index in range(1, 10)
        ]
        labels = {
            record["email_id"]: (
                "Spam" if index < 4 else "General Message"
            )
            for index, record in enumerate(records)
        }

        with self.assertRaisesRegex(CrossValidationError, "at least 5"):
            build_cross_validation_plan(records, labels)


if __name__ == "__main__":
    unittest.main()
