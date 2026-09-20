#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from email_classification import DatasetValidationError, load_and_validate


def _parse_arguments(arguments: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a participant inbox without classifying emails."
    )
    parser.add_argument(
        "bundle",
        nargs="?",
        default=str(PROJECT_ROOT / "download2"),
        help="Folder containing loader.py, inbox/, and attachments/",
    )
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
        contains_ground_truth = next(bundle.rglob("ground_truth*.json"), None)
    except OSError as exc:
        return f"Could not inspect bundle boundary: {exc}"
    if contains_ground_truth is not None:
        return "Refusing bundle containing evaluator-only ground truth"
    return None


def _load_participant_module(loader_path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "_email_classification_participant_loader",
        loader_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not create a module specification for loader.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "Inbox"):
        raise RuntimeError("loader.py does not expose Inbox")
    return module


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parse_arguments(arguments)
    bundle = Path(args.bundle).expanduser().resolve()

    boundary_error = _validate_bundle_boundary(bundle)
    if boundary_error is not None:
        print(f"Validation error: {boundary_error}", file=sys.stderr)
        return 1

    try:
        participant_loader = _load_participant_module(bundle / "loader.py")
        inbox = participant_loader.Inbox(str(bundle))
        result = load_and_validate(inbox, data_root=bundle)
    except DatasetValidationError as exc:
        for issue in exc.issues:
            context = f" [{issue.email_id}]" if issue.email_id else ""
            print(
                f"Validation error{context}: {issue.code}: {issue.message}",
                file=sys.stderr,
            )
        return 1
    except Exception as exc:
        print(
            f"Validation error: could not load participant bundle: {exc}",
            file=sys.stderr,
        )
        return 1

    print(json.dumps(asdict(result.summary), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
