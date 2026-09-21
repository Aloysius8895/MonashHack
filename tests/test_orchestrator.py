import sys
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from contracts import (
    AttachmentPair,
    ClassificationResult,
    DocumentFields,
    ExtractionResult,
    ExtractionUnavailable,
    FieldMismatch,
    VerificationResult,
    VerificationUnavailable,
)
from pipeline import run_verification_pipeline


def classification(email_id="email_001", should_compare=True):
    return ClassificationResult(
        email_id=email_id,
        category="document_comparison" if should_compare else "spam",
        should_compare=should_compare,
        attachments=AttachmentPair(si="attachments/si.txt", bl="attachments/bl.txt")
        if should_compare
        else AttachmentPair(),
    )


class StubExtractor:
    def __init__(self, error=None, email_id=None):
        self._error = error
        self._email_id = email_id

    def extract(self, classification):
        if self._error is not None:
            raise self._error
        return ExtractionResult(
            email_id=self._email_id or classification.email_id,
            si=DocumentFields(shipper="ABC Trading", container_count=3),
            bl=DocumentFields(shipper="ABC Trading", container_count=4),
        )


class StubVerifier:
    def __init__(self, error=None, email_id=None):
        self._error = error
        self._email_id = email_id

    def verify(self, extraction):
        if self._error is not None:
            raise self._error
        return VerificationResult(
            email_id=self._email_id or extraction.email_id,
            status="mismatch_detected",
            mismatches=(FieldMismatch(field="container_count", si=3, bl=4),),
        )


class OrchestratorTests(unittest.TestCase):
    def test_runs_comparison_ready_emails_end_to_end(self):
        outcome = run_verification_pipeline(
            [classification("email_002"), classification("email_001")],
            StubExtractor(),
            StubVerifier(),
        )

        self.assertEqual([item.email_id for item in outcome.extractions], ["email_001", "email_002"])
        self.assertEqual(
            [item.status for item in outcome.verifications],
            ["mismatch_detected", "mismatch_detected"],
        )
        self.assertEqual(outcome.skipped, ())
        self.assertEqual(outcome.review_required, ())

    def test_skips_emails_that_are_not_comparison_ready(self):
        outcome = run_verification_pipeline(
            [classification("email_003", should_compare=False)],
            StubExtractor(),
            StubVerifier(),
        )

        self.assertEqual(outcome.skipped, ("email_003",))
        self.assertEqual(outcome.extractions, ())
        self.assertEqual(outcome.verifications, ())

    def test_extraction_failure_becomes_a_review_item(self):
        outcome = run_verification_pipeline(
            [classification()],
            StubExtractor(error=ExtractionUnavailable("unreadable PDF")),
            StubVerifier(),
        )

        self.assertEqual(outcome.extractions, ())
        self.assertEqual(outcome.review_required, ("email_001",))
        self.assertEqual(outcome.verifications[0].status, "not_verified")
        self.assertIn("unreadable PDF", outcome.verifications[0].review_reason)

    def test_verification_failure_keeps_the_extraction(self):
        outcome = run_verification_pipeline(
            [classification()],
            StubExtractor(),
            StubVerifier(error=VerificationUnavailable("comparator crashed")),
        )

        self.assertEqual(len(outcome.extractions), 1)
        self.assertEqual(outcome.verifications[0].status, "not_verified")
        self.assertIn("comparator crashed", outcome.verifications[0].review_reason)

    def test_rejects_extractor_answering_for_another_email(self):
        with self.assertRaises(ValueError):
            run_verification_pipeline(
                [classification("email_001")],
                StubExtractor(email_id="email_999"),
                StubVerifier(),
            )

    def test_rejects_verifier_answering_for_another_email(self):
        with self.assertRaises(ValueError):
            run_verification_pipeline(
                [classification("email_001")],
                StubExtractor(),
                StubVerifier(email_id="email_999"),
            )


class PlaceholderModuleTests(unittest.TestCase):
    def test_unimplemented_modules_surface_as_review_items(self):
        from document_extraction import AttachmentDocumentExtractor
        from verification import FieldComparisonVerifier

        outcome = run_verification_pipeline(
            [classification()],
            AttachmentDocumentExtractor("download2"),
            FieldComparisonVerifier(),
        )

        self.assertEqual(outcome.review_required, ("email_001",))
        self.assertEqual(outcome.verifications[0].status, "not_verified")


if __name__ == "__main__":
    unittest.main()
