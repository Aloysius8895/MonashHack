import csv
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

from scripts.prepare_splits import main


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


def alpha_token(number):
    value = number
    letters = []
    while True:
        value, remainder = divmod(value, 26)
        letters.append(chr(ord("a") + remainder))
        if value == 0:
            return "".join(reversed(letters))
        value -= 1


def create_bundle(root, count=520, malformed=False):
    bundle = root / "participant"
    inbox_dir = bundle / "inbox"
    inbox_dir.mkdir(parents=True)
    (bundle / "attachments").mkdir()
    (bundle / "loader.py").write_text(LOADER_SOURCE, encoding="utf-8")
    for number in range(1, count + 1):
        token = alpha_token(number)
        record = {
            "email_id": f"email_{number:03d}",
            "from": f"sender-{token}@example.com",
            "subject": f"Unique subject {token}",
            "body": f"Unique body {token}",
            "attachments": [],
        }
        if malformed and number == 1:
            record.pop("body")
        (inbox_dir / f"email_{number:03d}.json").write_text(
            json.dumps(record), encoding="utf-8"
        )
    return bundle


def run_main(arguments):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        exit_code = main(arguments)
    return exit_code, stdout.getvalue(), stderr.getvalue()


class PrepareSplitsCliTests(unittest.TestCase):
    def test_select_creates_exact_stage_a_outputs(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle = create_bundle(root)
            output_dir = root / "splits"

            exit_code, stdout, stderr = run_main(
                ["select", str(bundle), str(output_dir)]
            )

            annotation = json.loads(
                (output_dir / "annotation_pool.json").read_text(encoding="utf-8")
            )
            production = json.loads(
                (output_dir / "production.json").read_text(encoding="utf-8")
            )
            with (output_dir / "annotations.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                rows = list(csv.DictReader(stream))

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            json.loads(stdout),
            {"annotation_pool": 120, "production": 400, "seed": 20260921},
        )
        self.assertEqual(len(annotation["records"]), 120)
        self.assertEqual(len(production["records"]), 400)
        self.assertEqual(len(rows), 120)
        self.assertTrue(all(not row["category"] for row in rows))

    def test_select_rejects_evaluator_material(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle = create_bundle(root)
            (bundle / "ground_truth.json").write_text("{}", encoding="utf-8")

            exit_code, stdout, stderr = run_main(
                ["select", str(bundle), str(root / "splits")]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("evaluator-only", stderr)

    def test_select_rejects_invalid_inbox(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle = create_bundle(root, count=520, malformed=True)

            exit_code, stdout, stderr = run_main(
                ["select", str(bundle), str(root / "splits")]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("missing_field", stderr)

    def test_select_rejects_output_inside_participant_bundle(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle = create_bundle(root)

            exit_code, stdout, stderr = run_main(
                ["select", str(bundle), str(bundle / "generated")]
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("outside the participant bundle", stderr)

    def test_finalize_requires_complete_labels_then_creates_exact_outputs(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle = create_bundle(root)
            output_dir = root / "splits"
            select_exit, _stdout, _stderr = run_main(
                ["select", str(bundle), str(output_dir)]
            )
            self.assertEqual(select_exit, 0)

            incomplete_exit, incomplete_stdout, incomplete_stderr = run_main(
                ["finalize", str(output_dir)]
            )
            self.assertEqual(incomplete_exit, 1)
            self.assertEqual(incomplete_stdout, "")
            self.assertIn("invalid category", incomplete_stderr)
            self.assertFalse((output_dir / "development.json").exists())
            self.assertFalse((output_dir / "final_test.json").exists())

            annotations_path = output_dir / "annotations.csv"
            with annotations_path.open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            categories = [
                "bl_comparison",
                "new_si_request",
                "invoice_query",
                "general_message",
                "spam",
            ]
            with annotations_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=["email_id", "category", "notes"],
                    lineterminator="\n",
                )
                writer.writeheader()
                for index, row in enumerate(rows):
                    row["category"] = categories[index % len(categories)]
                    writer.writerow(row)

            exit_code, stdout, stderr = run_main(
                ["finalize", str(output_dir)]
            )
            development = json.loads(
                (output_dir / "development.json").read_text(encoding="utf-8")
            )
            final_test = json.loads(
                (output_dir / "final_test.json").read_text(encoding="utf-8")
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(
            json.loads(stdout),
            {"development": 80, "final_test": 40, "seed": 20260921},
        )
        self.assertEqual(len(development["records"]), 80)
        self.assertEqual(len(final_test["records"]), 40)


if __name__ == "__main__":
    unittest.main()
