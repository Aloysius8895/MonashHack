from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .splitting import SplitRecord, StageASelection, StageBSelection


SCHEMA_VERSION = 1
_ALLOWED_SPLITS = frozenset(
    {"annotation_pool", "production", "development", "final_test"}
)
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ArtifactError(ValueError):
    pass


@dataclass(frozen=True)
class SplitManifest:
    schema_version: int
    seed: int
    split: str
    source_id_hash: str
    records: tuple[SplitRecord, ...]


@dataclass(frozen=True)
class AnnotationSet:
    labels: dict[str, str]
    notes: dict[str, str]


def write_stage_a(output_dir: str | Path, selection: StageASelection) -> None:
    annotation_ids = {record.email_id for record in selection.annotation_pool}
    production_ids = {record.email_id for record in selection.production}
    if annotation_ids & production_ids:
        raise ArtifactError("Stage A selections contain overlapping email IDs")
    if _id_hash(annotation_ids | production_ids) != selection.source_id_hash:
        raise ArtifactError("Stage A source hash does not match selected IDs")

    annotation_groups = {record.group_id for record in selection.annotation_pool}
    production_groups = {record.group_id for record in selection.production}
    if annotation_groups & production_groups:
        raise ArtifactError("A duplicate group crosses the Stage A boundary")

    payloads = {
        "annotation_pool.json": _manifest_bytes(
            split="annotation_pool",
            records=selection.annotation_pool,
            seed=selection.seed,
            source_id_hash=selection.source_id_hash,
        ),
        "production.json": _manifest_bytes(
            split="production",
            records=selection.production,
            seed=selection.seed,
            source_id_hash=selection.source_id_hash,
        ),
        "annotations.csv": _blank_annotations_bytes(selection.annotation_pool),
    }
    _write_atomic_set(Path(output_dir), payloads)


def write_stage_b(output_dir: str | Path, selection: StageBSelection) -> None:
    output_path = Path(output_dir)
    annotation_manifest = read_manifest(output_path / "annotation_pool.json")
    annotation_ids = {record.email_id for record in annotation_manifest.records}
    if _id_hash(annotation_ids) != selection.source_id_hash:
        raise ArtifactError("Stage B source hash does not match annotation pool")
    if selection.seed != annotation_manifest.seed:
        raise ArtifactError("Stage B seed does not match annotation pool")

    development_ids = {record.email_id for record in selection.development}
    test_ids = {record.email_id for record in selection.final_test}
    if development_ids & test_ids:
        raise ArtifactError("Stage B selections contain overlapping email IDs")
    if development_ids | test_ids != annotation_ids:
        raise ArtifactError("Stage B IDs do not cover the annotation pool")

    development_groups = {record.group_id for record in selection.development}
    test_groups = {record.group_id for record in selection.final_test}
    if development_groups & test_groups:
        raise ArtifactError("A duplicate group crosses the Stage B boundary")

    payloads = {
        "development.json": _manifest_bytes(
            split="development",
            records=selection.development,
            seed=selection.seed,
            source_id_hash=selection.source_id_hash,
        ),
        "final_test.json": _manifest_bytes(
            split="final_test",
            records=selection.final_test,
            seed=selection.seed,
            source_id_hash=selection.source_id_hash,
        ),
    }
    _write_atomic_set(output_path, payloads)


def read_manifest(path: str | Path) -> SplitManifest:
    manifest_path = Path(path)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError(f"Could not read manifest {manifest_path.name}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ArtifactError("Manifest root must be an object")
    schema_version = raw.get("schema_version")
    seed = raw.get("seed")
    split = raw.get("split")
    source_id_hash = raw.get("source_id_hash")
    raw_records = raw.get("records")
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        raise ArtifactError("Manifest has an unsupported schema version")
    if type(seed) is not int:
        raise ArtifactError("Manifest seed must be an integer")
    if not isinstance(split, str) or split not in _ALLOWED_SPLITS:
        raise ArtifactError("Manifest has an invalid split name")
    if not isinstance(source_id_hash, str) or not _HASH_PATTERN.fullmatch(
        source_id_hash
    ):
        raise ArtifactError("Manifest has an invalid source hash")
    if not isinstance(raw_records, list):
        raise ArtifactError("Manifest records must be a list")

    records = []
    for raw_record in raw_records:
        if not isinstance(raw_record, dict) or set(raw_record) != {
            "email_id",
            "group_id",
            "attachment_pattern",
        }:
            raise ArtifactError("Manifest record fields are invalid")
        if not all(isinstance(value, str) for value in raw_record.values()):
            raise ArtifactError("Manifest record values must be strings")
        records.append(
            SplitRecord(
                email_id=raw_record["email_id"],
                group_id=raw_record["group_id"],
                attachment_pattern=raw_record["attachment_pattern"],
            )
        )

    email_ids = [record.email_id for record in records]
    if email_ids != sorted(email_ids):
        raise ArtifactError("Manifest records must be sorted by email ID")
    if len(email_ids) != len(set(email_ids)):
        raise ArtifactError("Manifest contains duplicate email IDs")
    return SplitManifest(
        schema_version=schema_version,
        seed=seed,
        split=split,
        source_id_hash=source_id_hash,
        records=tuple(records),
    )


def read_annotations(path: str | Path) -> AnnotationSet:
    annotation_path = Path(path)
    try:
        with annotation_path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ["email_id", "category", "notes"]:
                raise ArtifactError(
                    "Annotation CSV header must be email_id,category,notes"
                )
            rows = list(reader)
    except OSError as exc:
        raise ArtifactError(
            f"Could not read annotations {annotation_path.name}: {exc}"
        ) from exc

    labels: dict[str, str] = {}
    notes: dict[str, str] = {}
    for row in rows:
        email_id = row.get("email_id", "")
        if not email_id:
            raise ArtifactError("Annotation row has an empty email ID")
        if email_id in labels:
            raise ArtifactError(f"Annotation CSV has duplicate annotation ID: {email_id}")
        labels[email_id] = row.get("category", "").strip()
        notes[email_id] = row.get("notes", "")
    return AnnotationSet(labels=labels, notes=notes)


def _manifest_bytes(
    split: str,
    records: Sequence[SplitRecord],
    seed: int,
    source_id_hash: str,
) -> bytes:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "seed": seed,
        "source_id_hash": source_id_hash,
        "split": split,
        "records": [
            {
                "email_id": record.email_id,
                "group_id": record.group_id,
                "attachment_pattern": record.attachment_pattern,
            }
            for record in sorted(records, key=lambda item: item.email_id)
        ],
    }
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _blank_annotations_bytes(records: Sequence[SplitRecord]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=["email_id", "category", "notes"],
        lineterminator="\n",
    )
    writer.writeheader()
    for record in sorted(records, key=lambda item: item.email_id):
        writer.writerow({"email_id": record.email_id, "category": "", "notes": ""})
    return stream.getvalue().encode("utf-8")


def _write_atomic_set(output_dir: Path, payloads: Mapping[str, bytes]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in payloads.items():
        target = output_dir / filename
        if target.exists() and target.read_bytes() != payload:
            raise ArtifactError(f"Refusing to overwrite conflicting file: {target}")

    temporary_paths: list[tuple[Path, Path]] = []
    try:
        for filename, payload in payloads.items():
            target = output_dir / filename
            if target.exists():
                continue
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{filename}.",
                suffix=".tmp",
                dir=output_dir,
            )
            temporary_path = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary_paths.append((temporary_path, target))

        for temporary_path, target in temporary_paths:
            temporary_path.replace(target)
    finally:
        for temporary_path, _target in temporary_paths:
            temporary_path.unlink(missing_ok=True)


def _id_hash(email_ids: Sequence[str] | set[str]) -> str:
    payload = "\n".join(sorted(email_ids)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
