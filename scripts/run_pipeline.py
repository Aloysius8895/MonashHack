#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_path in (PROJECT_ROOT, SRC_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from contracts import (
    CLASSIFICATION_STAGE,
    EXTRACTION_STAGE,
    VERIFICATION_STAGE,
    ContractError,
    read_handoff,
    write_handoff,
)
from document_extraction import AttachmentDocumentExtractor
from pipeline import run_verification_pipeline
from verification import FieldComparisonVerifier


class PipelineRunError(ValueError):
    pass


def _parse_arguments(arguments: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract and verify the SI/BL pairs that classification marked "
            "should_compare."
        )
    )
    parser.add_argument("bundle", help="Participant data bundle, e.g. download2")
    parser.add_argument("handoff_dir", help="Directory holding the stage handoff files")
    parser.add_argument(
        "--no-llm-fallback",
        action="store_true",
        help="Skip the local Ollama fallback for fields no alias matched",
    )
    return parser.parse_args(arguments)


def run_pipeline(
    bundle: Path,
    handoff_dir: Path,
    use_llm_fallback: bool = True,
) -> dict[str, object]:
    if not bundle.is_dir():
        raise PipelineRunError(f"Bundle directory does not exist: {bundle}")

    classifications = read_handoff(handoff_dir, CLASSIFICATION_STAGE)
    outcome = run_verification_pipeline(
        classifications,
        AttachmentDocumentExtractor(bundle, use_llm_fallback=use_llm_fallback),
        FieldComparisonVerifier(),
    )
    write_handoff(handoff_dir, EXTRACTION_STAGE, outcome.extractions)
    write_handoff(handoff_dir, VERIFICATION_STAGE, outcome.verifications)

    return {
        "classified": len(classifications),
        "skipped": len(outcome.skipped),
        "extracted": len(outcome.extractions),
        "verified": len(outcome.verifications),
        "status_counts": dict(
            sorted(Counter(item.status for item in outcome.verifications).items())
        ),
        "mismatch_field_counts": dict(
            sorted(
                Counter(
                    mismatch.field
                    for item in outcome.verifications
                    for mismatch in item.mismatches
                ).items()
            )
        ),
        "review_required": len(outcome.review_required),
    }


def main(arguments: Sequence[str] | None = None) -> int:
    args = _parse_arguments(arguments)
    try:
        summary = run_pipeline(
            Path(args.bundle).expanduser().resolve(),
            Path(args.handoff_dir).expanduser().resolve(),
            use_llm_fallback=not args.no_llm_fallback,
        )
    except (PipelineRunError, ContractError, OSError, ValueError) as error:
        print(f"Pipeline error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
