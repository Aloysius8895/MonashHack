from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    recall_score,
)
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from .features import build_email_text
from .splitting import ALLOWED_CATEGORIES, DEFAULT_SPLIT_SEED


CANDIDATE_NAMES = ("logistic_regression", "linear_svm")


class ModelingError(ValueError):
    pass


@dataclass(frozen=True)
class OOFPrediction:
    email_id: str
    fold: int
    true_category: str
    predicted_category: str
    scores: tuple[tuple[str, float], ...]
    margin: float


@dataclass(frozen=True)
class CandidateResult:
    name: str
    metrics: dict[str, object]
    oof_predictions: tuple[OOFPrediction, ...]
    review_margin_threshold: float
    elapsed_seconds: float


def evaluate_candidates(
    records: Sequence[Mapping[str, object]],
    labels: Mapping[str, str],
    folds: Mapping[str, int],
    seed: int = DEFAULT_SPLIT_SEED,
) -> tuple[CandidateResult, ...]:
    ordered_records = _validate_inputs(records, labels, folds)
    texts = [build_email_text(record) for record in ordered_records]
    y = [labels[_email_id(record)] for record in ordered_records]
    fold_values = [folds[_email_id(record)] for record in ordered_records]

    results = []
    for candidate_name in CANDIDATE_NAMES:
        started = time.perf_counter()
        predictions: list[OOFPrediction] = []
        for fold in sorted(set(fold_values)):
            train_indexes = [
                index for index, value in enumerate(fold_values) if value != fold
            ]
            validation_indexes = [
                index for index, value in enumerate(fold_values) if value == fold
            ]
            if not train_indexes or not validation_indexes:
                raise ModelingError(f"Fold {fold} has an empty train or validation set")

            model = _build_pipeline(candidate_name, seed)
            model.fit(
                [texts[index] for index in train_indexes],
                [y[index] for index in train_indexes],
            )
            validation_texts = [texts[index] for index in validation_indexes]
            predicted = model.predict(validation_texts)
            score_rows = model.decision_function(validation_texts)
            classes = tuple(str(value) for value in model.classes_)

            for index, predicted_category, raw_scores in zip(
                validation_indexes, predicted, score_rows, strict=True
            ):
                scores = tuple(
                    (category, round(float(score), 12))
                    for category, score in zip(classes, raw_scores, strict=True)
                )
                predictions.append(
                    OOFPrediction(
                        email_id=_email_id(ordered_records[index]),
                        fold=fold,
                        true_category=y[index],
                        predicted_category=str(predicted_category),
                        scores=scores,
                        margin=_score_margin(scores),
                    )
                )

        ordered_predictions = tuple(
            sorted(predictions, key=lambda item: item.email_id)
        )
        metrics = _classification_metrics(ordered_predictions)
        review_threshold = _review_margin_threshold(ordered_predictions)
        results.append(
            CandidateResult(
                name=candidate_name,
                metrics=metrics,
                oof_predictions=ordered_predictions,
                review_margin_threshold=review_threshold,
                elapsed_seconds=round(time.perf_counter() - started, 6),
            )
        )
    return tuple(results)


def select_best_candidate(
    results: Sequence[CandidateResult],
) -> CandidateResult:
    if not results:
        raise ModelingError("No candidate results were provided")
    return max(
        results,
        key=lambda result: (
            float(result.metrics["macro_f1"]),
            float(result.metrics["macro_recall"]),
            float(result.metrics["per_class"]["bl_comparison"]["recall"]),
            -CANDIDATE_NAMES.index(result.name),
        ),
    )


def fit_final_model(
    records: Sequence[Mapping[str, object]],
    labels: Mapping[str, str],
    candidate_name: str,
    seed: int = DEFAULT_SPLIT_SEED,
) -> Pipeline:
    folds = {str(record.get("email_id")): 1 for record in records}
    ordered_records = _validate_inputs(records, labels, folds, require_multiple_folds=False)
    model = _build_pipeline(candidate_name, seed)
    model.fit(
        [build_email_text(record) for record in ordered_records],
        [labels[_email_id(record)] for record in ordered_records],
    )
    return model


def score_mapping(model: Pipeline, texts: Sequence[str]) -> tuple[dict[str, float], ...]:
    raw_rows = model.decision_function(texts)
    classes = tuple(str(value) for value in model.classes_)
    return tuple(
        {
            category: round(float(score), 12)
            for category, score in zip(classes, raw_scores, strict=True)
        }
        for raw_scores in raw_rows
    )


def _build_pipeline(candidate_name: str, seed: int) -> Pipeline:
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
        strip_accents="unicode",
    )
    if candidate_name == "logistic_regression":
        classifier = LogisticRegression(
            class_weight="balanced",
            max_iter=2000,
            random_state=seed,
        )
    elif candidate_name == "linear_svm":
        classifier = LinearSVC(class_weight="balanced", random_state=seed)
    else:
        raise ModelingError(f"Unknown model candidate: {candidate_name}")
    return Pipeline((("tfidf", vectorizer), ("classifier", classifier)))


def _validate_inputs(
    records: Sequence[Mapping[str, object]],
    labels: Mapping[str, str],
    folds: Mapping[str, int],
    require_multiple_folds: bool = True,
) -> tuple[Mapping[str, object], ...]:
    ordered_records = tuple(sorted(records, key=_email_id))
    email_ids = [_email_id(record) for record in ordered_records]
    if len(email_ids) != len(set(email_ids)):
        raise ModelingError("Records contain duplicate email IDs")
    if set(email_ids) != set(labels):
        raise ModelingError("Record IDs and label IDs do not match")
    if set(email_ids) != set(folds):
        raise ModelingError("Record IDs and fold IDs do not match")
    invalid_labels = sorted(set(labels.values()) - ALLOWED_CATEGORIES)
    if invalid_labels:
        raise ModelingError(f"Invalid category: {invalid_labels[0]}")
    fold_values = set(folds.values())
    if not all(type(value) is int and value > 0 for value in fold_values):
        raise ModelingError("Fold values must be positive integers")
    if require_multiple_folds and len(fold_values) < 2:
        raise ModelingError("OOF evaluation requires at least two folds")
    return ordered_records


def _classification_metrics(
    predictions: Sequence[OOFPrediction],
) -> dict[str, object]:
    categories = sorted(ALLOWED_CATEGORIES)
    y_true = [item.true_category for item in predictions]
    y_pred = [item.predicted_category for item in predictions]
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=categories,
        zero_division=0,
    )
    per_class = {
        category: {
            "precision": round(float(precision[index]), 12),
            "recall": round(float(recall[index]), 12),
            "f1": round(float(f1[index]), 12),
            "support": int(support[index]),
        }
        for index, category in enumerate(categories)
    }
    false_negatives = sum(
        truth == "bl_comparison" and predicted != "bl_comparison"
        for truth, predicted in zip(y_true, y_pred, strict=True)
    )
    false_positives = sum(
        truth != "bl_comparison" and predicted == "bl_comparison"
        for truth, predicted in zip(y_true, y_pred, strict=True)
    )
    return {
        "macro_f1": round(float(f1_score(y_true, y_pred, average="macro")), 12),
        "macro_recall": round(
            float(recall_score(y_true, y_pred, average="macro")), 12
        ),
        "per_class": per_class,
        "confusion_matrix": {
            "labels": categories,
            "values": confusion_matrix(y_true, y_pred, labels=categories).tolist(),
        },
        "bl_comparison_false_negatives": int(false_negatives),
        "bl_comparison_false_positives": int(false_positives),
    }


def _review_margin_threshold(predictions: Sequence[OOFPrediction]) -> float:
    correct_margins = sorted(
        item.margin
        for item in predictions
        if item.predicted_category == item.true_category
    )
    if not correct_margins:
        return 0.0
    index = max(0, int((len(correct_margins) - 1) * 0.10))
    return round(correct_margins[index], 12)


def _score_margin(scores: Sequence[tuple[str, float]]) -> float:
    ordered = sorted((score for _category, score in scores), reverse=True)
    if len(ordered) < 2:
        return 0.0
    return round(float(ordered[0] - ordered[1]), 12)


def _email_id(record: Mapping[str, object]) -> str:
    value = record.get("email_id")
    if not isinstance(value, str):
        raise ModelingError("Record email_id must be a string")
    return value
