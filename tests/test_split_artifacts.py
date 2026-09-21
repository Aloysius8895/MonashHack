import csv
import hashlib
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from email_classification.split_artifacts import (
    ArtifactError,
    read_annotations,
    read_manifest,
    write_stage_a,
    write_stage_b,
)
from email_classification.splitting import (
    SplitRecord,
    StageASelection,
    StageBSelection,
)


def id_hash(email_ids):
    payload = "\n".join(sorted(email_ids)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def split_record(number, group=None, pattern="none"):
    return SplitRecord(
        email_id=f"email_{number:03d}",
        group_id=group or f"group_{number:012x}",
        attachment_pattern=pattern,
    )


def stage_a_selection():
    annotation = (split_record(2), split_record(1))
    production = (split_record(4), split_record(3))
    return StageASelection(
        annotation_pool=annotation,
        production=production,
        seed=20260921,
        source_id_hash=id_hash(record.email_id for record in annotation + production),
    )


class SplitArtifactTests(unittest.TestCase):
    def test_stage_a_writes_deterministic_manifests_and_blank_annotations(self):
        selection = stage_a_selection()
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            write_stage_a(output_dir, selection)
            first_bytes = {
                path.name: path.read_bytes() for path in sorted(output_dir.iterdir())
            }
            write_stage_a(output_dir, selection)
            second_bytes = {
                path.name: path.read_bytes() for path in sorted(output_dir.iterdir())
            }

            self.assertEqual(first_bytes, second_bytes)
            annotation_json = json.loads(
                (output_dir / "annotation_pool.json").read_text(encoding="utf-8")
            )
            production_json = json.loads(
                (output_dir / "production.json").read_text(encoding="utf-8")
            )
            with (output_dir / "annotations.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                rows = list(csv.DictReader(stream))

        self.assertEqual(annotation_json["schema_version"], 1)
        self.assertEqual(annotation_json["seed"], 20260921)
        self.assertEqual(annotation_json["split"], "annotation_pool")
        self.assertEqual(annotation_json["source_id_hash"], selection.source_id_hash)
        self.assertEqual(
            list(annotation_json["records"][0]),
            ["attachment_pattern", "email_id", "group_id"],
        )
        self.assertEqual(
            [record["email_id"] for record in annotation_json["records"]],
            ["email_001", "email_002"],
        )
        self.assertEqual(production_json["split"], "production")
        self.assertEqual([row["category"] for row in rows], ["", ""])
        self.assertEqual([row["notes"] for row in rows], ["", ""])

    def test_stage_a_refuses_to_overwrite_human_annotations(self):
        selection = stage_a_selection()
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            write_stage_a(output_dir, selection)
            annotations_path = output_dir / "annotations.csv"
            annotations_path.write_text(
                "email_id,category,notes\nemail_001,spam,checked\n",
                encoding="utf-8",
            )
            human_bytes = annotations_path.read_bytes()

            with self.assertRaisesRegex(ArtifactError, "conflicting file"):
                write_stage_a(output_dir, selection)

            self.assertEqual(annotations_path.read_bytes(), human_bytes)

    def test_read_manifest_validates_and_round_trips(self):
        selection = stage_a_selection()
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            write_stage_a(output_dir, selection)

            manifest = read_manifest(output_dir / "annotation_pool.json")

        self.assertEqual(manifest.split, "annotation_pool")
        self.assertEqual(manifest.records, tuple(sorted(selection.annotation_pool, key=lambda r: r.email_id)))

    def test_read_annotations_rejects_duplicate_ids(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "annotations.csv"
            path.write_text(
                "email_id,category,notes\n"
                "email_001,spam,first\n"
                "email_001,general_message,second\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ArtifactError, "duplicate annotation ID"):
                read_annotations(path)

    def test_stage_b_writes_manifests_without_categories(self):
        stage_a = stage_a_selection()
        pool_ids = [record.email_id for record in stage_a.annotation_pool]
        stage_b = StageBSelection(
            development=(stage_a.annotation_pool[0],),
            final_test=(stage_a.annotation_pool[1],),
            seed=20260921,
            source_id_hash=id_hash(pool_ids),
        )
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            write_stage_a(output_dir, stage_a)
            annotations_path = output_dir / "annotations.csv"
            original_annotations = annotations_path.read_bytes()

            write_stage_b(output_dir, stage_b)

            development = json.loads(
                (output_dir / "development.json").read_text(encoding="utf-8")
            )
            final_test = json.loads(
                (output_dir / "final_test.json").read_text(encoding="utf-8")
            )
            self.assertEqual(annotations_path.read_bytes(), original_annotations)

        self.assertEqual(development["split"], "development")
        self.assertEqual(final_test["split"], "final_test")
        self.assertNotIn("category", development["records"][0])
        self.assertNotIn("category", final_test["records"][0])

    def test_stage_b_rejects_annotation_pool_hash_mismatch(self):
        stage_a = stage_a_selection()
        bad_stage_b = StageBSelection(
            development=(stage_a.annotation_pool[0],),
            final_test=(stage_a.annotation_pool[1],),
            seed=20260921,
            source_id_hash="0" * 64,
        )
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            write_stage_a(output_dir, stage_a)

            with self.assertRaisesRegex(ArtifactError, "source hash"):
                write_stage_b(output_dir, bad_stage_b)

            self.assertFalse((output_dir / "development.json").exists())
            self.assertFalse((output_dir / "final_test.json").exists())


if __name__ == "__main__":
    unittest.main()
