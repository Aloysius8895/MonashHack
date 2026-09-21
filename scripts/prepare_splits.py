#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_path in (PROJECT_ROOT, SRC_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from email_classification import (
    ArtifactError,
    DatasetValidationError,
    SplitError,
    finalize_labeled_split,
    load_and_validate,
    read_annotations,
    read_manifest,
    select_annotation_pool,
    write_stage_a,
    write_stage_b,
)


EXPECTED_EMAIL_COUNT = 520
ANNOTATION_POOL_SIZE = 120
DEVELOPMENT_SIZE = 80
FINAL_TEST_SIZE = 40
SPLIT_SEED = 20260921
CV_FOLDS = 5
EVALUATOR_ROOT = (PROJECT_ROOT / "download").resolve()


def _parse_arguments(arguments: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare leakage-safe human annotation and evaluation splits."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    select_parser = commands.add_parser(
        "select", help="Create the annotation pool and production manifests"
    )
    select_parser.add_argument("bundle", help="Validated participant bundle")
    select_parser.add_argument("output_dir", help="Generated split directory")

    finalize_parser = commands.add_parser(
        "finalize", help="Create development and final-test manifests"
    )
    finalize_parser.add_argument("output_dir", help="Generated split directory")

    cross_validate_parser = commands.add_parser(
        "cross-validate",
        help="Create grouped five-fold assignments for all labeled emails",
    )
    cross_validate_parser.add_argument("bundle", help="Validated participant bundle")
    cross_validate_parser.add_argument(
        "annotations", help="Complete human annotation CSV"
    )
    cross_validate_parser.add_argument("output_dir", help="Generated split directory")
    return parser.parse_args(arguments)


def _validate_bundle_boundary(bundle: Path) -> str | None:
    if not bundle.exists():
        return f"Bundle does not exist: {bundle}"
    if not bundle.is_dir():
        return f"Bundle is not a directory: {bundle}"
    if bundle.name.casefold() == "download":
        return "Refusing evaluator-only bundle named download"
    if not (bundle / "inbox").is_dir():
        return f"Bundle is missing its inbox directory: {bundle}"
    if not (bundle / "loader.py").is_file():
        return f"Bundle is missing loader.py: {bundle}"
    try:
        if next(bundle.rglob("ground_truth*.json"), None) is not None:
            return "Refusing bundle containing evaluator-only ground truth"
    except OSError as exc:
        return f"Could not inspect bundle boundary: {exc}"
    return None


def _validate_output_boundary(output_dir: Path, bundle: Path | None = None) -> str | None:
    if bundle is not None and output_dir.is_relative_to(bundle):
        return "Output directory must be outside the participant bundle"
    if output_dir == EVALUATOR_ROOT or output_dir.is_relative_to(EVALUATOR_ROOT):
        return "Refusing output inside the evaluator-only download directory"
    if output_dir.exists():
        try:
            if next(output_dir.rglob("ground_truth*.json"), None) is not None:
                return "Refusing output directory containing evaluator-only ground truth"
        except OSError as exc:
            return f"Could not inspect output boundary: {exc}"
    return None


def _validate_annotation_boundary(annotation_path: Path, bundle: Path) -> str | None:
    if not annotation_path.exists():
        return f"Annotation file does not exist: {annotation_path}"
    if not annotation_path.is_file():
        return f"Annotation path is not a file: {annotation_path}"
    if annotation_path.is_relative_to(bundle):
        return "Annotation file must be outside the participant bundle"
    if (
        annotation_path == EVALUATOR_ROOT
        or annotation_path.is_relative_to(EVALUATOR_ROOT)
        or any(part.casefold() == "download" for part in annotation_path.parts)
        or annotation_path.name.casefold().startswith("ground_truth")
    ):
        return "Refusing evaluator-only annotation path"
    return None


def _load_participant_module(loader_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_email_classification_split_loader",
        loader_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not create a module specification for loader.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "Inbox"):
        raise RuntimeError("loader.py does not expose Inbox")
    return module


def _load_cross_validation_api():
    from email_classification import (
        build_cross_validation_plan,
        write_cross_validation,
    )

    return build_cross_validation_plan, write_cross_validation


def _select(bundle: Path, output_dir: Path) -> dict[str, int]:
    bundle_error = _validate_bundle_boundary(bundle)
    if bundle_error is not None:
        raise SplitError(bundle_error)
    output_error = _validate_output_boundary(output_dir, bundle)
    if output_error is not None:
        raise SplitError(output_error)

    participant_loader = _load_participant_module(bundle / "loader.py")
    inbox = participant_loader.Inbox(str(bundle))
    validation = load_and_validate(inbox, data_root=bundle)
    if len(validation.records) != EXPECTED_EMAIL_COUNT:
        raise SplitError(
            f"Expected {EXPECTED_EMAIL_COUNT} emails, found {len(validation.records)}"
        )

    selection = select_annotation_pool(
        validation.records,
        pool_size=ANNOTATION_POOL_SIZE,
        seed=SPLIT_SEED,
    )
    write_stage_a(output_dir, selection)
    return {
        "annotation_pool": len(selection.annotation_pool),
        "production": len(selection.production),
        "seed": selection.seed,
    }


def _finalize(output_dir: Path) -> dict[str, int]:
    output_error = _validate_output_boundary(output_dir)
    if output_error is not None:
        raise SplitError(output_error)

    annotation_manifest = read_manifest(output_dir / "annotation_pool.json")
    if annotation_manifest.split != "annotation_pool":
        raise ArtifactError("Expected the annotation_pool manifest")
    annotations = read_annotations(output_dir / "annotations.csv")
    selection = finalize_labeled_split(
        annotation_manifest.records,
        annotations.labels,
        development_size=DEVELOPMENT_SIZE,
        test_size=FINAL_TEST_SIZE,
        seed=annotation_manifest.seed,
    )
    write_stage_b(output_dir, selection)
    return {
        "development": len(selection.development),
        "final_test": len(selection.final_test),
        "seed": selection.seed,
    }


def _cross_validate(
    bundle: Path,
    annotation_path: Path,
    output_dir: Path,
) -> dict[str, int]:
    bundle_error = _validate_bundle_boundary(bundle)
    if bundle_error is not None:
        raise SplitError(bundle_error)
    annotation_error = _validate_annotation_boundary(annotation_path, bundle)
    if annotation_error is not None:
        raise SplitError(annotation_error)
    output_error = _validate_output_boundary(output_dir, bundle)
    if output_error is not None:
        raise SplitError(output_error)

    annotation_bytes = annotation_path.read_bytes()
    annotation_sha256 = hashlib.sha256(annotation_bytes).hexdigest()

    participant_loader = _load_participant_module(bundle / "loader.py")
    inbox = participant_loader.Inbox(str(bundle))
    validation = load_and_validate(inbox, data_root=bundle)
    if len(validation.records) != EXPECTED_EMAIL_COUNT:
        raise SplitError(
            f"Expected {EXPECTED_EMAIL_COUNT} emails, found {len(validation.records)}"
        )

    annotations = read_annotations(annotation_path)
    if len(annotations.labels) != EXPECTED_EMAIL_COUNT:
        raise SplitError(
            "Annotation file must contain exactly "
            f"{EXPECTED_EMAIL_COUNT} unique labeled records"
        )
    empty_labels = sorted(
        email_id for email_id, category in annotations.labels.items() if not category
    )
    if empty_labels:
        raise SplitError(
            f"Annotation file has empty labels for {len(empty_labels)} records"
        )

    build_cross_validation_plan, write_cross_validation = (
        _load_cross_validation_api()
    )
    plan = build_cross_validation_plan(
        validation.records,
        annotations.labels,
        n_splits=CV_FOLDS,
        seed=SPLIT_SEED,
    )
    if annotation_path.read_bytes() != annotation_bytes:
        raise SplitError("Annotation file changed during cross-validation generation")
    write_cross_validation(output_dir, plan, annotation_sha256)

    if annotation_path.read_bytes() != annotation_bytes:
        raise SplitError("Annotation file changed during cross-validation generation")

    return {
        "folds": plan.n_splits,
        "groups": plan.total_groups,
        "records": len(plan.assignments),
        "seed": plan.seed,
    }


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parse_arguments(arguments)
    try:
        if args.command == "select":
            summary = _select(
                Path(args.bundle).expanduser().resolve(),
                Path(args.output_dir).expanduser().resolve(),
            )
        elif args.command == "finalize":
            summary = _finalize(Path(args.output_dir).expanduser().resolve())
        else:
            summary = _cross_validate(
                Path(args.bundle).expanduser().resolve(),
                Path(args.annotations).expanduser().resolve(),
                Path(args.output_dir).expanduser().resolve(),
            )
    except DatasetValidationError as exc:
        for issue in exc.issues:
            context = f" [{issue.email_id}]" if issue.email_id else ""
            print(
                f"Split error{context}: {issue.code}: {issue.message}",
                file=sys.stderr,
            )
        return 1
    except (ArtifactError, ImportError, SplitError, OSError, RuntimeError, ValueError) as exc:
        print(f"Split error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
