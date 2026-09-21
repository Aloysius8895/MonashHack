import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from contracts import (
    CLASSIFICATION_STAGE,
    EXTRACTION_STAGE,
    SCHEMA_VERSION,
    VERIFICATION_STAGE,
    AttachmentPair,
    ClassificationResult,
    ContractError,
    DocumentFields,
    ExtractionResult,
    FieldMismatch,
    VerificationResult,
    handoff_path,
    read_handoff,
    write_handoff,
)


def comparison_result(email_id="email_001"):
    return ClassificationResult(
        email_id=email_id,
        category="document_comparison",
        should_compare=True,
        attachments=AttachmentPair(si="attachments/si.txt", bl="attachments/bl.txt"),
    )


class ClassificationResultTests(unittest.TestCase):
    def test_round_trips_through_a_mapping(self):
        result = comparison_result()
        self.assertEqual(ClassificationResult.from_dict(result.to_dict()), result)

    def test_rejects_unknown_published_category(self):
        with self.assertRaises(ContractError):
            ClassificationResult(
                email_id="email_001", category="bl_comparison", should_compare=False
            )

    def test_rejects_comparison_without_both_attachments(self):
        with self.assertRaises(ContractError):
            ClassificationResult(
                email_id="email_001",
                category="document_comparison",
                should_compare=True,
                attachments=AttachmentPair(si="attachments/si.txt"),
            )

    def test_allows_non_comparison_without_attachments(self):
        result = ClassificationResult(
            email_id="email_002", category="spam", should_compare=False
        )
        self.assertFalse(result.attachments.is_complete)


class DocumentFieldsTests(unittest.TestCase):
    def test_reports_missing_fields(self):
        fields = DocumentFields(shipper="ABC Trading", container_count=3)
        self.assertEqual(
            fields.missing_fields,
            (
                "consignee",
                "notify_party",
                "port_of_loading",
                "port_of_discharge",
                "gross_weight_kg",
            ),
        )

    def test_rejects_unknown_field_names(self):
        with self.assertRaises(ContractError):
            DocumentFields.from_dict({"shipper": "ABC", "vessel_name": "Ever Given"})

    def test_rejects_negative_quantities(self):
        with self.assertRaises(ContractError):
            DocumentFields(container_count=-1)
        with self.assertRaises(ContractError):
            DocumentFields(gross_weight_kg=-0.5)

    def test_rejects_boolean_container_count(self):
        with self.assertRaises(ContractError):
            DocumentFields(container_count=True)


class VerificationResultTests(unittest.TestCase):
    def test_round_trips_with_mismatches(self):
        result = VerificationResult(
            email_id="email_001",
            status="mismatch_detected",
            mismatches=(FieldMismatch(field="container_count", si=3, bl=4),),
        )
        self.assertEqual(VerificationResult.from_dict(result.to_dict()), result)

    def test_rejects_match_carrying_mismatches(self):
        with self.assertRaises(ContractError):
            VerificationResult(
                email_id="email_001",
                status="match",
                mismatches=(FieldMismatch(field="shipper", si="A", bl="B"),),
            )

    def test_rejects_mismatch_status_without_mismatches(self):
        with self.assertRaises(ContractError):
            VerificationResult(email_id="email_001", status="mismatch_detected")

    def test_rejects_review_without_reason(self):
        with self.assertRaises(ContractError):
            VerificationResult(
                email_id="email_001", status="not_verified", review_required=True
            )

    def test_rejects_unknown_mismatch_field(self):
        with self.assertRaises(ContractError):
            FieldMismatch(field="vessel_name", si="A", bl="B")


class HandoffTests(unittest.TestCase):
    def test_classification_round_trip(self):
        with TemporaryDirectory() as temp_dir:
            records = (comparison_result("email_002"), comparison_result("email_001"))
            written = write_handoff(temp_dir, CLASSIFICATION_STAGE, records)

            self.assertEqual(written, handoff_path(temp_dir, CLASSIFICATION_STAGE))
            loaded = read_handoff(temp_dir, CLASSIFICATION_STAGE)
            self.assertEqual([item.email_id for item in loaded], ["email_001", "email_002"])

    def test_extraction_and_verification_round_trip(self):
        with TemporaryDirectory() as temp_dir:
            extraction = ExtractionResult(
                email_id="email_001",
                si=DocumentFields(shipper="ABC Trading", container_count=3),
                bl=DocumentFields(shipper="ABC Trading", container_count=4),
            )
            verification = VerificationResult(
                email_id="email_001",
                status="mismatch_detected",
                mismatches=(FieldMismatch(field="container_count", si=3, bl=4),),
            )
            write_handoff(temp_dir, EXTRACTION_STAGE, [extraction])
            write_handoff(temp_dir, VERIFICATION_STAGE, [verification])

            self.assertEqual(read_handoff(temp_dir, EXTRACTION_STAGE), (extraction,))
            self.assertEqual(read_handoff(temp_dir, VERIFICATION_STAGE), (verification,))

    def test_rejects_duplicate_email_ids(self):
        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(ContractError):
                write_handoff(
                    temp_dir,
                    CLASSIFICATION_STAGE,
                    [comparison_result("email_001"), comparison_result("email_001")],
                )

    def test_rejects_wrong_stage_in_file(self):
        with TemporaryDirectory() as temp_dir:
            write_handoff(temp_dir, CLASSIFICATION_STAGE, [comparison_result()])
            target = handoff_path(temp_dir, CLASSIFICATION_STAGE)
            document = json.loads(target.read_text(encoding="utf-8"))
            document["stage"] = EXTRACTION_STAGE
            target.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaises(ContractError):
                read_handoff(temp_dir, CLASSIFICATION_STAGE)

    def test_rejects_unsupported_schema_version(self):
        with TemporaryDirectory() as temp_dir:
            write_handoff(temp_dir, CLASSIFICATION_STAGE, [comparison_result()])
            target = handoff_path(temp_dir, CLASSIFICATION_STAGE)
            document = json.loads(target.read_text(encoding="utf-8"))
            document["schema_version"] = SCHEMA_VERSION + 1
            target.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaises(ContractError):
                read_handoff(temp_dir, CLASSIFICATION_STAGE)

    def test_rejects_missing_file(self):
        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(ContractError):
                read_handoff(temp_dir, CLASSIFICATION_STAGE)

    def test_rejects_unknown_stage(self):
        with TemporaryDirectory() as temp_dir:
            with self.assertRaises(ContractError):
                write_handoff(temp_dir, "triage", [comparison_result()])


if __name__ == "__main__":
    unittest.main()
