import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from contracts import (
    AttachmentPair,
    ClassificationResult,
    DocumentFields,
    ExtractionResult,
    ExtractionUnavailable,
)
from document_extraction import AttachmentDocumentExtractor
from pipeline import run_verification_pipeline
from verification import FieldComparisonVerifier

BUNDLE = PROJECT_ROOT / "download2"
SAMPLE = ClassificationResult(
    email_id="email_001",
    category="document_comparison",
    should_compare=True,
    attachments=AttachmentPair(
        si="attachments/email_001_SI.txt", bl="attachments/email_001_BL.txt"
    ),
)


def fields(**overrides):
    base = {
        "shipper": "ABC Trading",
        "consignee": "XYZ Logistics",
        "notify_party": "DEF Shipping",
        "port_of_loading": "Port Klang",
        "port_of_discharge": "Singapore",
        "container_count": 3,
        "gross_weight_kg": 22000,
    }
    base.update(overrides)
    return DocumentFields(**base)


def extraction(si=None, bl=None, email_id="email_001"):
    return ExtractionResult(
        email_id=email_id, si=si or fields(), bl=bl or fields()
    )


@unittest.skipUnless(BUNDLE.is_dir(), "participant bundle is not available")
class DocumentExtractorAdapterTests(unittest.TestCase):
    def test_extracts_contract_fields_from_a_real_pair(self):
        extractor = AttachmentDocumentExtractor(BUNDLE, use_llm_fallback=False)

        result = extractor.extract(SAMPLE)

        self.assertEqual(result.email_id, "email_001")
        self.assertEqual(result.si.missing_fields, ())
        self.assertEqual(result.bl.missing_fields, ())
        self.assertIsInstance(result.si.container_count, int)
        self.assertIsInstance(result.si.gross_weight_kg, int)

    def test_rejects_an_incomplete_attachment_pair(self):
        extractor = AttachmentDocumentExtractor(BUNDLE)
        classification = ClassificationResult(
            email_id="email_002", category="spam", should_compare=False
        )

        with self.assertRaises(ExtractionUnavailable):
            extractor.extract(classification)

    def test_reports_a_missing_attachment_file(self):
        extractor = AttachmentDocumentExtractor(BUNDLE)
        classification = ClassificationResult(
            email_id="email_999",
            category="document_comparison",
            should_compare=True,
            attachments=AttachmentPair(
                si="attachments/missing_SI.txt", bl="attachments/missing_BL.txt"
            ),
        )

        with self.assertRaises(ExtractionUnavailable):
            extractor.extract(classification)


class VerifierAdapterTests(unittest.TestCase):
    def test_identical_documents_map_to_match(self):
        result = FieldComparisonVerifier().verify(extraction())

        self.assertEqual(result.status, "match")
        self.assertEqual(result.mismatches, ())
        self.assertFalse(result.review_required)

    def test_differing_field_maps_to_mismatch_detected(self):
        result = FieldComparisonVerifier().verify(
            extraction(bl=fields(container_count=4))
        )

        self.assertEqual(result.status, "mismatch_detected")
        self.assertEqual([item.field for item in result.mismatches], ["container_count"])
        self.assertEqual(result.mismatches[0].si, 3)
        self.assertEqual(result.mismatches[0].bl, 4)
        self.assertFalse(result.review_required)

    def test_missing_value_maps_to_not_verified_with_a_reason(self):
        result = FieldComparisonVerifier().verify(extraction(si=fields(shipper=None)))

        self.assertEqual(result.status, "not_verified")
        self.assertTrue(result.review_required)
        self.assertTrue(result.review_reason)

    def test_preserves_the_email_id(self):
        result = FieldComparisonVerifier().verify(extraction(email_id="email_042"))

        self.assertEqual(result.email_id, "email_042")


@unittest.skipUnless(BUNDLE.is_dir(), "participant bundle is not available")
class EndToEndPipelineTests(unittest.TestCase):
    def test_classification_flows_through_extraction_into_verification(self):
        outcome = run_verification_pipeline(
            [SAMPLE],
            AttachmentDocumentExtractor(BUNDLE, use_llm_fallback=False),
            FieldComparisonVerifier(),
        )

        self.assertEqual(len(outcome.extractions), 1)
        self.assertEqual(len(outcome.verifications), 1)
        self.assertEqual(outcome.skipped, ())
        self.assertIn(
            outcome.verifications[0].status,
            {"match", "mismatch_detected", "not_verified"},
        )

    def test_non_comparison_email_never_reaches_extraction(self):
        outcome = run_verification_pipeline(
            [ClassificationResult(email_id="email_002", category="spam", should_compare=False)],
            AttachmentDocumentExtractor(BUNDLE, use_llm_fallback=False),
            FieldComparisonVerifier(),
        )

        self.assertEqual(outcome.skipped, ("email_002",))
        self.assertEqual(outcome.extractions, ())


if __name__ == "__main__":
    unittest.main()
