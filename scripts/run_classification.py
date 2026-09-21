#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import ModuleType

import joblib


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_path in (PROJECT_ROOT, SRC_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from contracts import CLASSIFICATION_STAGE, HANDOFF_FILENAMES, write_handoff
from email_classification import (
    CATEGORY_LABEL_MAP,
    DatasetValidationError,
    ModelingError,
    build_email_text,
    evaluate_candidates,
    fit_final_model,
    load_and_validate,
    read_annotations,
    route_prediction,
    score_mapping,
    select_best_candidate,
)
from email_classification.contract_adapter import to_contract


SEED = 20260921
SCHEMA_VERSION = 1
EVALUATOR_ROOT = (PROJECT_ROOT / "download").resolve()


class ClassificationRunError(ValueError):
    pass


def _parse_arguments(arguments: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate, train, and run the email classification pipeline."
    )
    parser.add_argument("bundle", help="Participant data bundle")
    parser.add_argument("annotations", help="Complete human annotation CSV")
    parser.add_argument("folds", help="Committed cross-validation assignments CSV")
    parser.add_argument("output_root", help="Root containing usable and unusable")
    parser.add_argument("artifact_root", help="Classification model and report directory")
    return parser.parse_args(arguments)


def run_classification(
    bundle: Path,
    annotation_path: Path,
    fold_path: Path,
    output_root: Path,
    artifact_root: Path,
) -> dict[str, object]:
    _validate_paths(bundle, annotation_path, fold_path, output_root, artifact_root)
    initial_hashes = _source_hashes(bundle, annotation_path, fold_path)

    participant_loader = _load_participant_module(bundle / "loader.py")
    validation = load_and_validate(
        participant_loader.Inbox(str(bundle)),
        data_root=bundle,
    )
    records = validation.records
    annotation_set = read_annotations(annotation_path)
    labels = _normalize_labels(annotation_set.labels)
    folds = _read_folds(fold_path, labels)
    record_ids = {str(record["email_id"]) for record in records}
    if record_ids != set(labels):
        raise ClassificationRunError("Inbox and annotation IDs do not match")
    if record_ids != set(folds):
        raise ClassificationRunError("Inbox and cross-validation fold IDs do not match")

    run_started = time.perf_counter()
    candidate_results = evaluate_candidates(records, labels, folds, seed=SEED)
    selected = select_best_candidate(candidate_results)
    model = fit_final_model(records, labels, selected.name, seed=SEED)

    ordered_records = tuple(sorted(records, key=lambda record: str(record["email_id"])))
    texts = [build_email_text(record) for record in ordered_records]
    model_predictions = [str(value) for value in model.predict(texts)]
    score_rows = score_mapping(model, texts)
    decisions = []
    contract_results = []
    output_payloads: dict[str, dict[str, object]] = {}
    for record, model_category, scores in zip(
        ordered_records, model_predictions, score_rows, strict=True
    ):
        decision = route_prediction(
            record,
            model_category,
            scores,
            selected.review_margin_threshold,
            unavailable_attachments=_unavailable_attachments(record, bundle),
        )
        decisions.append(decision)
        contract_results.append(to_contract(decision, record))
        output_payloads[decision.email_id] = {
            "email_id": decision.email_id,
            "category": decision.category,
            "route": decision.route,
            "status": decision.status,
            "reason": decision.reason,
            "model_category": model_category,
            "scores": dict(sorted(scores.items())),
            "rules_fired": list(decision.rules_fired),
        }

    if len(output_payloads) != len(records):
        raise ClassificationRunError("Not every inbox record received exactly one output")
    if _source_hashes(bundle, annotation_path, fold_path) != initial_hashes:
        raise ClassificationRunError("A classification input changed during processing")

    route_counts = Counter(decision.route for decision in decisions)
    status_counts = Counter(decision.status for decision in decisions)
    category_counts = Counter(decision.category for decision in decisions)
    review_reasons = Counter(
        _review_reason(decision)
        for decision in decisions
        if decision.status == "human_review"
    )
    summary = {
        "schema_version": SCHEMA_VERSION,
        "seed": SEED,
        "total_records": len(records),
        "selected_model": selected.name,
        "review_margin_threshold": selected.review_margin_threshold,
        "route_counts": dict(sorted(route_counts.items())),
        "status_counts": dict(sorted(status_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "human_review_reasons": dict(sorted(review_reasons.items())),
        "comparison_ready": sum(
            1 for result in contract_results if result.should_compare
        ),
        "handoff_file": f"handoff/{HANDOFF_FILENAMES[CLASSIFICATION_STAGE]}",
        "source_hashes": initial_hashes,
    }
    runtime = {
        "candidate_seconds": {
            result.name: result.elapsed_seconds for result in candidate_results
        },
        "total_seconds": round(time.perf_counter() - run_started, 6),
    }

    with tempfile.TemporaryDirectory(prefix="classification-stage-") as temp_dir:
        stage = Path(temp_dir)
        artifact_stage = stage / "artifacts"
        output_stage = stage / "outputs"
        _stage_artifacts(
            artifact_stage,
            candidate_results,
            selected,
            model,
            summary,
            runtime,
        )
        generated_paths = _stage_outputs(output_stage, output_payloads)
        _publish_artifacts(artifact_stage, artifact_root)
        _publish_outputs(output_stage, output_root, generated_paths)
        _verify_published_outputs(output_root, set(output_payloads))
        write_handoff(output_root / "handoff", CLASSIFICATION_STAGE, contract_results)

    if _source_hashes(bundle, annotation_path, fold_path) != initial_hashes:
        raise ClassificationRunError("A classification input changed during output writing")
    return summary


def _normalize_labels(labels: Mapping[str, str]) -> dict[str, str]:
    normalized = {}
    for email_id, label in labels.items():
        if label not in CATEGORY_LABEL_MAP:
            raise ClassificationRunError(
                f"Annotation has invalid category for {email_id}: {label!r}"
            )
        normalized[email_id] = CATEGORY_LABEL_MAP[label]
    if not normalized:
        raise ClassificationRunError("Annotation file is empty")
    return normalized


def _read_folds(path: Path, labels: Mapping[str, str]) -> dict[str, int]:
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ["email_id", "category", "group_id", "fold"]:
                raise ClassificationRunError(
                    "Fold CSV header must be email_id,category,group_id,fold"
                )
            rows = list(reader)
    except OSError as error:
        raise ClassificationRunError(f"Could not read fold assignments: {error}") from error

    folds = {}
    groups: dict[str, set[int]] = {}
    for row in rows:
        email_id = row.get("email_id", "")
        if not email_id or email_id in folds:
            raise ClassificationRunError(f"Fold CSV has invalid or duplicate ID: {email_id}")
        if email_id not in labels:
            raise ClassificationRunError(f"Fold CSV has unknown email ID: {email_id}")
        if row.get("category") != labels[email_id]:
            raise ClassificationRunError(f"Fold category does not match annotation: {email_id}")
        try:
            fold = int(row.get("fold", ""))
        except ValueError as error:
            raise ClassificationRunError(f"Invalid fold for {email_id}") from error
        if fold not in {1, 2, 3, 4, 5}:
            raise ClassificationRunError(f"Fold must be in 1-5 for {email_id}")
        group_id = row.get("group_id", "")
        if not group_id:
            raise ClassificationRunError(f"Fold group is empty for {email_id}")
        folds[email_id] = fold
        groups.setdefault(group_id, set()).add(fold)
    if set(folds) != set(labels):
        raise ClassificationRunError("Fold IDs and annotation IDs do not match")
    if set(folds.values()) != {1, 2, 3, 4, 5}:
        raise ClassificationRunError("Fold CSV must contain folds 1 through 5")
    if any(len(group_folds) != 1 for group_folds in groups.values()):
        raise ClassificationRunError("A duplicate/template group crosses folds")
    return folds


def _stage_artifacts(
    stage: Path,
    candidate_results,
    selected,
    model,
    summary: Mapping[str, object],
    runtime: Mapping[str, object],
) -> None:
    stage.mkdir(parents=True)
    comparison = {
        "schema_version": SCHEMA_VERSION,
        "seed": SEED,
        "selection_order": ["macro_f1", "macro_recall", "bl_comparison_recall"],
        "selected_model": selected.name,
        "candidates": {
            result.name: {
                "metrics": result.metrics,
                "review_margin_threshold": result.review_margin_threshold,
            }
            for result in candidate_results
        },
    }
    _write_json(stage / "model_comparison.json", comparison)
    _write_json(
        stage / "confusion_matrix.json",
        {
            "model": selected.name,
            **selected.metrics["confusion_matrix"],
        },
    )
    _write_json(stage / "run_summary.json", summary)
    _write_json(stage / "runtime.json", runtime)
    (stage / "oof_predictions.csv").write_bytes(
        _oof_csv_bytes(candidate_results)
    )
    joblib.dump(model, stage / "selected_model.joblib", compress=0)


def _stage_outputs(
    stage: Path,
    payloads: Mapping[str, Mapping[str, object]],
) -> list[str]:
    generated = []
    for email_id, payload in sorted(payloads.items()):
        route = str(payload["route"])
        target = stage / route / f"{email_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_json(target, payload)
        generated.append(f"{route}/{email_id}.json")
    return generated


def _publish_artifacts(stage: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for staged_file in stage.iterdir():
        staged_file.replace(target / staged_file.name)


def _publish_outputs(stage: Path, target: Path, generated: Sequence[str]) -> None:
    manifest_path = target / "classification_manifest.json"
    stale_paths = []
    if manifest_path.is_file():
        try:
            raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            stale_paths = raw_manifest.get("generated_files", [])
        except (OSError, json.JSONDecodeError):
            stale_paths = []

    target.mkdir(parents=True, exist_ok=True)
    for relative in stale_paths:
        if not isinstance(relative, str):
            continue
        candidate = (target / relative).resolve()
        if candidate.is_relative_to(target.resolve()) and candidate.parent.name in {
            "usable",
            "unusable",
        }:
            candidate.unlink(missing_ok=True)

    for route in ("usable", "unusable"):
        (target / route).mkdir(exist_ok=True)
        staged_route = stage / route
        if staged_route.is_dir():
            for staged_file in staged_route.iterdir():
                staged_file.replace(target / route / staged_file.name)

    temporary_manifest = target / ".classification_manifest.tmp"
    _write_json(
        temporary_manifest,
        {"schema_version": SCHEMA_VERSION, "generated_files": list(generated)},
    )
    os.replace(temporary_manifest, manifest_path)


def _verify_published_outputs(target: Path, expected_ids: set[str]) -> None:
    usable_ids = {path.stem for path in (target / "usable").glob("email_*.json")}
    unusable_ids = {
        path.stem for path in (target / "unusable").glob("email_*.json")
    }
    if usable_ids & unusable_ids:
        raise ClassificationRunError("An email appears in both output routes")
    if usable_ids | unusable_ids != expected_ids:
        raise ClassificationRunError(
            "Published outputs do not exactly match the inbox email IDs"
        )


def _oof_csv_bytes(candidate_results) -> bytes:
    stream = io.StringIO(newline="")
    fields = [
        "model",
        "email_id",
        "fold",
        "true_category",
        "predicted_category",
        "margin",
        "scores",
    ]
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for result in candidate_results:
        for prediction in result.oof_predictions:
            writer.writerow(
                {
                    "model": result.name,
                    "email_id": prediction.email_id,
                    "fold": prediction.fold,
                    "true_category": prediction.true_category,
                    "predicted_category": prediction.predicted_category,
                    "margin": prediction.margin,
                    "scores": json.dumps(dict(prediction.scores), sort_keys=True),
                }
            )
    return stream.getvalue().encode("utf-8")


def _review_reason(decision) -> str:
    rules = set(decision.rules_fired)
    if "unavailable_attachment" in rules:
        return "unavailable_attachment"
    if "missing_required_attachment" in rules:
        return "missing_required_attachment"
    if "low_score_margin" in rules:
        return "low_score_margin"
    return "model_rule_conflict"


def _unavailable_attachments(
    record: Mapping[str, object],
    bundle: Path,
) -> tuple[str, ...]:
    unavailable = []
    for attachment in record.get("attachments", []):
        try:
            with (bundle / str(attachment)).open("rb"):
                pass
        except OSError:
            unavailable.append(str(attachment))
    return tuple(unavailable)


def _source_hashes(bundle: Path, annotation_path: Path, fold_path: Path) -> dict[str, str]:
    digest = hashlib.sha256()
    for path in sorted((bundle / "inbox").glob("email_*.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return {
        "inbox_sha256": digest.hexdigest(),
        "annotations_sha256": hashlib.sha256(annotation_path.read_bytes()).hexdigest(),
        "folds_sha256": hashlib.sha256(fold_path.read_bytes()).hexdigest(),
    }


def _validate_paths(
    bundle: Path,
    annotation_path: Path,
    fold_path: Path,
    output_root: Path,
    artifact_root: Path,
) -> None:
    if not bundle.is_dir() or not (bundle / "inbox").is_dir() or not (bundle / "loader.py").is_file():
        raise ClassificationRunError("Bundle must contain inbox and loader.py")
    if bundle.name.casefold() == "download" or bundle == EVALUATOR_ROOT:
        raise ClassificationRunError("Refusing evaluator-only bundle")
    if next(bundle.rglob("ground_truth*.json"), None) is not None:
        raise ClassificationRunError("Refusing bundle containing evaluator-only ground truth")
    for path, label in ((annotation_path, "Annotation"), (fold_path, "Fold")):
        if not path.is_file():
            raise ClassificationRunError(f"{label} file does not exist: {path}")
        if any(part.casefold() == "download" for part in path.parts) or path.name.casefold().startswith("ground_truth"):
            raise ClassificationRunError(f"Refusing evaluator-only {label.casefold()} path")
    for path, label in ((output_root, "Output"), (artifact_root, "Artifact")):
        if path.is_relative_to(bundle):
            raise ClassificationRunError(f"{label} directory must be outside the bundle")
        if path == EVALUATOR_ROOT or path.is_relative_to(EVALUATOR_ROOT):
            raise ClassificationRunError(f"Refusing {label.casefold()} inside evaluator-only data")
    if output_root == artifact_root or output_root.is_relative_to(artifact_root) or artifact_root.is_relative_to(output_root):
        raise ClassificationRunError("Output and artifact directories must not overlap")


def _load_participant_module(loader_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("_classification_loader", loader_path)
    if spec is None or spec.loader is None:
        raise ClassificationRunError("Could not load participant loader.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "Inbox"):
        raise ClassificationRunError("loader.py does not expose Inbox")
    return module


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parse_arguments(arguments)
    try:
        summary = run_classification(
            Path(args.bundle).expanduser().resolve(),
            Path(args.annotations).expanduser().resolve(),
            Path(args.folds).expanduser().resolve(),
            Path(args.output_root).expanduser().resolve(),
            Path(args.artifact_root).expanduser().resolve(),
        )
    except DatasetValidationError as error:
        for issue in error.issues:
            context = f" [{issue.email_id}]" if issue.email_id else ""
            print(f"Classification error{context}: {issue.code}: {issue.message}", file=sys.stderr)
        return 1
    except (ClassificationRunError, ModelingError, OSError, RuntimeError, ValueError) as error:
        print(f"Classification error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
