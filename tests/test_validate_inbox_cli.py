import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.validate_inbox import main


LOADER_SOURCE = """\
import json
from pathlib import Path


class Inbox:
    def __init__(self, source):
        self.source = Path(source)

    def emails(self):
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((self.source / "inbox").glob("email_*.json"))
        ]
"""


def create_bundle(root: Path) -> Path:
    bundle = root / "participant"
    inbox_dir = bundle / "inbox"
    inbox_dir.mkdir(parents=True)
    (bundle / "attachments").mkdir()
    (bundle / "loader.py").write_text(LOADER_SOURCE, encoding="utf-8")
    record = {
        "email_id": "email_001",
        "from": "sender@example.com",
        "subject": "Hello",
        "body": "A valid message",
        "attachments": [],
    }
    (inbox_dir / "email_001.json").write_text(
        json.dumps(record), encoding="utf-8"
    )
    return bundle


def run_main(arguments):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = main(arguments)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class ValidateInboxCliTests(unittest.TestCase):
    def test_valid_bundle_prints_json_summary(self):
        with TemporaryDirectory() as temp_dir:
            bundle = create_bundle(Path(temp_dir))

            exit_code, stdout, stderr = run_main([str(bundle)])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            json.loads(stdout),
            {
                "attachment_extensions": {},
                "attachment_references": 0,
                "empty_bodies": 0,
                "empty_subjects": 0,
                "invalid_emails": 0,
                "total_emails": 1,
                "valid_emails": 1,
                "validation_errors": 0,
                "with_attachments": 0,
                "without_attachments": 1,
            },
        )

    def test_missing_bundle_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing"

            exit_code, stdout, stderr = run_main([str(missing)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("does not exist", stderr)

    def test_bundle_without_inbox_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir) / "participant"
            bundle.mkdir()
            (bundle / "loader.py").write_text(LOADER_SOURCE, encoding="utf-8")

            exit_code, stdout, stderr = run_main([str(bundle)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("inbox directory", stderr)

    def test_bundle_without_loader_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            bundle = Path(temp_dir) / "participant"
            (bundle / "inbox").mkdir(parents=True)

            exit_code, stdout, stderr = run_main([str(bundle)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("loader.py", stderr)

    def test_evaluator_bundle_is_rejected_before_loading(self):
        with TemporaryDirectory() as temp_dir:
            bundle = create_bundle(Path(temp_dir))
            evaluator_dir = bundle / "private"
            evaluator_dir.mkdir()
            (evaluator_dir / "ground_truth.json").write_text("{}", encoding="utf-8")

            exit_code, stdout, stderr = run_main([str(bundle)])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("evaluator-only", stderr)


if __name__ == "__main__":
    unittest.main()
