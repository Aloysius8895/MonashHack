import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from email_classification.routing import route_prediction


def record(subject="Compare documents", body="Please check", attachments=None):
    return {
        "email_id": "email_001",
        "subject": subject,
        "body": body,
        "attachments": [] if attachments is None else attachments,
    }


class RoutingTests(unittest.TestCase):
    def test_complete_bl_comparison_is_usable(self):
        decision = route_prediction(
            record(
                attachments=[
                    "attachments/email_001_SI.txt",
                    "attachments/email_001_BL.txt",
                ]
            ),
            "bl_comparison",
            {"bl_comparison": 3.0, "invoice_query": 0.1},
            review_margin_threshold=0.5,
        )

        self.assertEqual(decision.route, "usable")
        self.assertEqual(decision.status, "ready_for_document_comparison")

    def test_missing_bl_is_unusable_human_review(self):
        decision = route_prediction(
            record(attachments=["attachments/email_001_SI.txt"]),
            "bl_comparison",
            {"bl_comparison": 3.0, "invoice_query": 0.1},
            review_margin_threshold=0.5,
        )

        self.assertEqual(decision.route, "unusable")
        self.assertEqual(decision.status, "human_review")
        self.assertIn("BL", decision.reason)

    def test_unreadable_attachment_is_unusable_human_review(self):
        decision = route_prediction(
            record(
                attachments=[
                    "attachments/email_001_SI.txt",
                    "attachments/email_001_BL.txt",
                ]
            ),
            "bl_comparison",
            {"bl_comparison": 3.0, "invoice_query": 0.1},
            review_margin_threshold=0.5,
            unavailable_attachments=("attachments/email_001_BL.txt",),
        )

        self.assertEqual(decision.route, "unusable")
        self.assertEqual(decision.status, "human_review")
        self.assertIn("cannot be opened", decision.reason)

    def test_low_margin_strong_invoice_rule_can_override(self):
        decision = route_prediction(
            record(subject="Invoice payment query", body="Please check this invoice"),
            "general_message",
            {"general_message": 1.1, "invoice_query": 1.0},
            review_margin_threshold=0.5,
        )

        self.assertEqual(decision.category, "invoice_query")
        self.assertEqual(decision.route, "unusable")
        self.assertIn("invoice_evidence", decision.rules_fired)

    def test_high_margin_rule_conflict_routes_to_human_review(self):
        decision = route_prediction(
            record(subject="Invoice payment query", body="Please check this invoice"),
            "general_message",
            {"general_message": 4.0, "invoice_query": 0.2},
            review_margin_threshold=0.5,
        )

        self.assertEqual(decision.category, "general_message")
        self.assertEqual(decision.status, "human_review")
        self.assertEqual(decision.route, "unusable")

    def test_incidental_invoice_in_shipping_body_is_not_strong_evidence(self):
        decision = route_prediction(
            record(
                subject="REQUEST SI for booking",
                body="Documents required: original invoice and packing list.",
            ),
            "new_si_request",
            {"new_si_request": 4.0, "invoice_query": 0.2},
            review_margin_threshold=0.5,
        )

        self.assertEqual(decision.status, "classified")
        self.assertNotIn("invoice_evidence", decision.rules_fired)

    def test_low_margin_without_rule_routes_to_human_review(self):
        decision = route_prediction(
            record(subject="Hello", body="Checking in"),
            "general_message",
            {"general_message": 1.0, "new_si_request": 0.9},
            review_margin_threshold=0.5,
        )

        self.assertEqual(decision.status, "human_review")
        self.assertIn("margin", decision.reason.casefold())


if __name__ == "__main__":
    unittest.main()
