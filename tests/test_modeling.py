import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from email_classification.features import build_email_text
from email_classification.modeling import (
    evaluate_candidates,
    fit_final_model,
    select_best_candidate,
)


CATEGORIES = (
    "bl_comparison",
    "new_si_request",
    "invoice_query",
    "general_message",
    "spam",
)


def sample_data():
    records = []
    labels = {}
    folds = {}
    words = {
        "bl_comparison": "compare draft bill lading",
        "new_si_request": "new shipping instruction booking",
        "invoice_query": "invoice payment billing",
        "general_message": "meeting update hello",
        "spam": "winner lottery unsubscribe",
    }
    for category_index, category in enumerate(CATEGORIES):
        for offset in range(10):
            number = category_index * 10 + offset + 1
            email_id = f"email_{number:03d}"
            records.append(
                {
                    "email_id": email_id,
                    "from": "sender@example.com",
                    "subject": words[category],
                    "body": f"{words[category]} token{chr(97 + offset)}",
                    "attachments": (
                        [f"attachments/{email_id}_SI.txt", f"attachments/{email_id}_BL.txt"]
                        if category == "bl_comparison"
                        else []
                    ),
                }
            )
            labels[email_id] = category
            folds[email_id] = offset % 5 + 1
    return records, labels, folds


class FeatureTests(unittest.TestCase):
    def test_email_text_contains_content_filenames_and_metadata_tokens(self):
        text = build_email_text(
            {
                "email_id": "email_001",
                "subject": "Please compare",
                "body": "Attached documents",
                "attachments": [
                    "attachments/email_001_SI.txt",
                    "attachments/email_001_BL.pdf",
                ],
            }
        )

        self.assertIn("Please compare", text)
        self.assertIn("Attached documents", text)
        self.assertIn("email_001_SI.txt", text)
        self.assertIn("meta_has_si", text)
        self.assertIn("meta_has_bl", text)
        self.assertIn("meta_ext_txt", text)
        self.assertIn("meta_ext_pdf", text)
        self.assertIn("meta_attachment_count_2", text)


class ModelingTests(unittest.TestCase):
    def test_candidates_produce_complete_deterministic_oof_metrics(self):
        records, labels, folds = sample_data()

        first = evaluate_candidates(records, labels, folds, seed=20260921)
        second = evaluate_candidates(records, labels, folds, seed=20260921)

        self.assertEqual([item.name for item in first], [
            "logistic_regression",
            "linear_svm",
        ])
        for left, right in zip(first, second, strict=True):
            self.assertEqual(left.oof_predictions, right.oof_predictions)
            self.assertEqual(left.metrics, right.metrics)
            self.assertEqual(len(left.oof_predictions), 50)
            self.assertEqual(
                {prediction.fold for prediction in left.oof_predictions},
                {1, 2, 3, 4, 5},
            )
            self.assertEqual(set(left.metrics["per_class"]), set(CATEGORIES))
            self.assertIn("macro_f1", left.metrics)
            self.assertIn("macro_recall", left.metrics)
            self.assertIn("bl_comparison_false_negatives", left.metrics)
            self.assertIn("bl_comparison_false_positives", left.metrics)
            self.assertGreaterEqual(left.review_margin_threshold, 0.0)

    def test_best_candidate_can_fit_and_predict_all_records(self):
        records, labels, folds = sample_data()
        results = evaluate_candidates(records, labels, folds, seed=20260921)
        selected = select_best_candidate(results)

        model = fit_final_model(records, labels, selected.name, seed=20260921)
        predictions = model.predict([build_email_text(record) for record in records])

        self.assertEqual(len(predictions), 50)
        self.assertEqual(set(predictions), set(CATEGORIES))


if __name__ == "__main__":
    unittest.main()
