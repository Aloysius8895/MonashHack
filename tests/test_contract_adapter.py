import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from email_classification.contract_adapter import AdapterError, to_contract
from email_classification.routing import RoutingDecision


def record(email_id="email_001", attachments=None):
    return {
        "email_id": email_id,
        "subject": "Please compare SI and BL",
        "body": "Attached are the documents.",
        "attachments": [
            "attachments/email_001_SI.txt",
            "attachments/email_001_BL.txt",
        ]
        if attachments is None
        else attachments,
    }


def decision(
    email_id="email_001",
    category="bl_comparison",
    route="usable",
    status="ready_for_document_comparison",
):
    return RoutingDecision(
        email_id=email_id,
        category=category,
        route=route,
        status=status,
        reason="test",
        rules_fired=(),
    )


class ContractAdapterTests(unittest.TestCase):
    def test_maps_comparison_ready_decision(self):
        result = to_contract(decision(), record())

        self.assertEqual(result.email_id, "email_001")
        self.assertEqual(result.category, "document_comparison")
        self.assertTrue(result.should_compare)
        self.assertEqual(result.attachments.si, "attachments/email_001_SI.txt")
        self.assertEqual(result.attachments.bl, "attachments/email_001_BL.txt")

    def test_resolves_attachments_regardless_of_order(self):
        result = to_contract(
            decision(),
            record(
                attachments=[
                    "attachments/email_001_BL.txt",
                    "attachments/email_001_SI.txt",
                ]
            ),
        )

        self.assertEqual(result.attachments.si, "attachments/email_001_SI.txt")
        self.assertEqual(result.attachments.bl, "attachments/email_001_BL.txt")

    def test_human_review_is_not_comparison_ready(self):
        result = to_contract(
            decision(route="unusable", status="human_review"), record()
        )

        self.assertEqual(result.category, "document_comparison")
        self.assertFalse(result.should_compare)
        self.assertTrue(result.attachments.is_complete)

    def test_maps_non_comparison_categories(self):
        result = to_contract(
            decision(category="spam", route="unusable", status="classified"),
            record(attachments=[]),
        )

        self.assertEqual(result.category, "spam")
        self.assertFalse(result.should_compare)
        self.assertIsNone(result.attachments.si)

    def test_rejects_decision_for_a_different_record(self):
        with self.assertRaises(AdapterError):
            to_contract(decision(email_id="email_002"), record("email_001"))

    def test_rejects_comparison_ready_without_attachment_pair(self):
        with self.assertRaises(AdapterError):
            to_contract(
                decision(), record(attachments=["attachments/email_001_SI.txt"])
            )


if __name__ == "__main__":
    unittest.main()
