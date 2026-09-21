import csv
import hashlib
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from scripts.run_classification import main


LOADER_SOURCE = """\
import json
from pathlib import Path

class Inbox:
    def __init__(self, source):
        self.source = Path(source)

    def emails(self):
        return [json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((self.source / "inbox").glob("email_*.json"))]
"""

HUMAN_LABELS = {
    "bl_comparison": "Document Comparison",
    "new_si_request": "New SI Request",
    "invoice_query": "Invoice Query",
    "general_message": "General Message",
    "spam": "Spam",
}

WORDS = {
    "bl_comparison": "compare draft bill lading",
    "new_si_request": "create new shipping instruction",
    "invoice_query": "invoice billing payment",
    "general_message": "general meeting update",
    "spam": "lottery winner unsubscribe",
}


def create_inputs(root):
    bundle = root / "participant"
    inbox = bundle / "inbox"
    attachments = bundle / "attachments"
    inbox.mkdir(parents=True)
    attachments.mkdir()
    (bundle / "loader.py").write_text(LOADER_SOURCE, encoding="utf-8")
    rows = []
    fold_rows = []
    number = 0
    for category in HUMAN_LABELS:
        for offset in range(5):
            number += 1
            email_id = f"email_{number:03d}"
            attachment_paths = []
            if category == "bl_comparison":
                for suffix in ("SI", "BL"):
                    relative = f"attachments/{email_id}_{suffix}.txt"
                    (bundle / relative).write_text("fixture", encoding="utf-8")
                    attachment_paths.append(relative)
            record = {
                "email_id": email_id,
                "from": "sender@example.com",
                "subject": WORDS[category],
                "body": f"{WORDS[category]} token{chr(97 + offset)}",
                "attachments": attachment_paths,
            }
            (inbox / f"{email_id}.json").write_text(
                json.dumps(record), encoding="utf-8"
            )
            rows.append(
                {"email_id": email_id, "category": HUMAN_LABELS[category], "notes": ""}
            )
            fold_rows.append(
                {
                    "email_id": email_id,
                    "category": category,
                    "group_id": f"group_{number:012x}",
                    "fold": offset + 1,
                }
            )

    annotations = root / "annotations.csv"
    with annotations.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["email_id", "category", "notes"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    folds = root / "cv_assignments.csv"
    with folds.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["email_id", "category", "group_id", "fold"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(fold_rows)
    return bundle, annotations, folds


def run_main(arguments):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = main(arguments)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class RunClassificationCliTests(unittest.TestCase):
    def test_runs_complete_classification_and_preserves_inputs(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle, annotations, folds = create_inputs(root)
            output_root = root / "outputs"
            artifact_root = root / "artifacts" / "classification"
            annotation_hash = hashlib.sha256(annotations.read_bytes()).hexdigest()
            inbox_hashes = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted((bundle / "inbox").glob("*.json"))
            }

            exit_code, stdout, stderr = run_main(
                [str(bundle), str(annotations), str(folds), str(output_root), str(artifact_root)]
            )

            usable = sorted((output_root / "usable").glob("email_*.json"))
            unusable = sorted((output_root / "unusable").glob("email_*.json"))
            summary = json.loads((artifact_root / "run_summary.json").read_text(encoding="utf-8"))
            comparison = json.loads((artifact_root / "model_comparison.json").read_text(encoding="utf-8"))
            sample = json.loads(usable[0].read_text(encoding="utf-8"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(json.loads(stdout)["total_records"], 25)
            self.assertEqual(len(usable) + len(unusable), 25)
            self.assertEqual(
                {path.stem for path in usable}.intersection(path.stem for path in unusable),
                set(),
            )
            self.assertEqual(summary["total_records"], 25)
            self.assertEqual(set(comparison["candidates"]), {"logistic_regression", "linear_svm"})
            self.assertEqual(
                set(sample),
                {"category", "email_id", "model_category", "reason", "route", "rules_fired", "scores", "status"},
            )
            self.assertTrue((artifact_root / "selected_model.joblib").is_file())
            self.assertTrue((artifact_root / "oof_predictions.csv").is_file())
            self.assertEqual(hashlib.sha256(annotations.read_bytes()).hexdigest(), annotation_hash)
            self.assertEqual(
                {
                    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted((bundle / "inbox").glob("*.json"))
                },
                inbox_hashes,
            )

    def test_rejects_category_mismatch_without_outputs(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle, annotations, folds = create_inputs(root)
            with folds.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            rows[0]["category"] = "spam"
            with folds.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=["email_id", "category", "group_id", "fold"], lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)

            exit_code, stdout, stderr = run_main(
                [str(bundle), str(annotations), str(folds), str(root / "outputs"), str(root / "artifacts")]
            )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("category", stderr.casefold())
            self.assertFalse((root / "outputs").exists())

    def test_rejects_evaluator_only_bundle(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle, annotations, folds = create_inputs(root)
            evaluator_bundle = root / "download"
            bundle.rename(evaluator_bundle)

            exit_code, stdout, stderr = run_main(
                [str(evaluator_bundle), str(annotations), str(folds), str(root / "outputs"), str(root / "artifacts")]
            )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("evaluator-only", stderr)
            self.assertFalse((root / "outputs").exists())


if __name__ == "__main__":
    unittest.main()
