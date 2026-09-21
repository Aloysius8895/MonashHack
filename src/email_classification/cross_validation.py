from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import sklearn
from sklearn.model_selection import StratifiedGroupKFold

from .splitting import DEFAULT_SPLIT_SEED, SplitError, build_split_records


CATEGORY_LABEL_MAP = {
    "Document Comparison": "bl_comparison",
    "New SI Request": "new_si_request",
    "Invoice Query": "invoice_query",
    "General Message": "general_message",
    "Spam": "spam",
}
DEFAULT_CV_FOLDS = 5


class CrossValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CVAssignment:
    email_id: str
    category: str
    group_id: str
    fold: int


@dataclass(frozen=True)
class CVFoldSummary:
    fold: int
    training_size: int
    validation_size: int
    training_category_counts: tuple[tuple[str, int], ...]
    validation_category_counts: tuple[tuple[str, int], ...]
    validation_proportion_deviations: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class CrossValidationPlan:
    assignments: tuple[CVAssignment, ...]
    folds: tuple[CVFoldSummary, ...]
    n_splits: int
    seed: int
    source_id_hash: str
    sklearn_version: str
    total_groups: int
    overall_category_counts: tuple[tuple[str, int], ...]


def build_cross_validation_plan(
    records: Sequence[Mapping[str, object]],
    labels: Mapping[str, str],
    n_splits: int = DEFAULT_CV_FOLDS,
    seed: int = DEFAULT_SPLIT_SEED,
) -> CrossValidationPlan:
    if n_splits < 2:
        raise CrossValidationError("Cross-validation requires at least 2 folds")

    try:
        split_records = build_split_records(records)
    except SplitError as error:
        raise CrossValidationError(str(error)) from error

    source_ids = {record.email_id for record in split_records}
    label_ids = set(labels)
    missing_ids = sorted(source_ids - label_ids)
    if missing_ids:
        raise CrossValidationError(
            f"Annotation file has missing labels for {len(missing_ids)} IDs"
        )
    unknown_ids = sorted(label_ids - source_ids)
    if unknown_ids:
        raise CrossValidationError(
            f"Annotation file has unknown label IDs: {unknown_ids[0]}"
        )

    normalized_labels = {}
    for email_id in sorted(source_ids):
        human_label = labels[email_id]
        if not isinstance(human_label, str) or human_label not in CATEGORY_LABEL_MAP:
            raise CrossValidationError(
                f"Annotation file has invalid category for {email_id}: {human_label!r}"
            )
        normalized_labels[email_id] = CATEGORY_LABEL_MAP[human_label]

    group_categories: dict[str, set[str]] = defaultdict(set)
    for record in split_records:
        group_categories[record.group_id].add(normalized_labels[record.email_id])
    categories = tuple(sorted(CATEGORY_LABEL_MAP.values()))
    category_counts = Counter(normalized_labels.values())
    for category in categories:
        if category_counts[category] < n_splits:
            raise CrossValidationError(
                f"Category {category} must have at least {n_splits} records"
            )
        category_group_count = sum(
            category in group_category
            for group_category in group_categories.values()
        )
        if category_group_count < n_splits:
            raise CrossValidationError(
                f"Category {category} must have at least {n_splits} groups"
            )

    ordered_records = tuple(sorted(split_records, key=lambda item: item.email_id))
    y = [normalized_labels[record.email_id] for record in ordered_records]
    groups = [record.group_id for record in ordered_records]
    splitter = StratifiedGroupKFold(
        n_splits=n_splits,
        shuffle=True,
        random_state=seed,
    )

    folds_by_index: dict[int, int] = {}
    try:
        split_iterator = splitter.split(range(len(ordered_records)), y, groups)
        for fold, (_, validation_indexes) in enumerate(split_iterator, start=1):
            for index in validation_indexes:
                if int(index) in folds_by_index:
                    raise CrossValidationError(
                        "A record was assigned to more than one validation fold"
                    )
                folds_by_index[int(index)] = fold
    except ValueError as error:
        raise CrossValidationError(f"Cannot build cross-validation folds: {error}") from error

    if len(folds_by_index) != len(ordered_records):
        raise CrossValidationError("Not every record was assigned to a validation fold")

    assignments = tuple(
        CVAssignment(
            email_id=record.email_id,
            category=normalized_labels[record.email_id],
            group_id=record.group_id,
            fold=folds_by_index[index],
        )
        for index, record in enumerate(ordered_records)
    )

    folds_by_group: dict[str, set[int]] = defaultdict(set)
    for assignment in assignments:
        folds_by_group[assignment.group_id].add(assignment.fold)
    if any(len(folds) != 1 for folds in folds_by_group.values()):
        raise CrossValidationError("A duplicate/template group crosses validation folds")

    overall_counts = tuple((category, category_counts[category]) for category in categories)
    total_size = len(assignments)
    fold_summaries = []
    for fold in range(1, n_splits + 1):
        validation_counts = Counter(
            assignment.category
            for assignment in assignments
            if assignment.fold == fold
        )
        missing_categories = [
            category for category in categories if validation_counts[category] == 0
        ]
        if missing_categories:
            raise CrossValidationError(
                f"Fold {fold} is missing category: {missing_categories[0]}"
            )
        validation_size = sum(validation_counts.values())
        training_counts = {
            category: category_counts[category] - validation_counts[category]
            for category in categories
        }
        deviations = tuple(
            (
                category,
                round(
                    validation_counts[category] / validation_size
                    - category_counts[category] / total_size,
                    12,
                ),
            )
            for category in categories
        )
        fold_summaries.append(
            CVFoldSummary(
                fold=fold,
                training_size=total_size - validation_size,
                validation_size=validation_size,
                training_category_counts=tuple(training_counts.items()),
                validation_category_counts=tuple(
                    (category, validation_counts[category])
                    for category in categories
                ),
                validation_proportion_deviations=deviations,
            )
        )

    return CrossValidationPlan(
        assignments=assignments,
        folds=tuple(fold_summaries),
        n_splits=n_splits,
        seed=seed,
        source_id_hash=_source_id_hash(assignment.email_id for assignment in assignments),
        sklearn_version=sklearn.__version__,
        total_groups=len(folds_by_group),
        overall_category_counts=overall_counts,
    )


def _source_id_hash(email_ids: Iterable[str]) -> str:
    import hashlib

    ordered_ids = sorted(str(email_id) for email_id in email_ids)
    return hashlib.sha256("\n".join(ordered_ids).encode("utf-8")).hexdigest()
