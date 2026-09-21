# Grouped Cross-Validation Design

## Scope

Replace the earlier 120/400 and 80/40 evaluation workflow with deterministic,
group-aware, stratified 5-fold cross-validation over all 520 human-labeled
emails.

This step creates fold assignments only. Model training and evaluation remain
separate later steps.

## Source Data and Labels

- Email inputs remain `download2/inbox/` plus attachment metadata.
- Human labels come only from `data/splits/annotations.csv`.
- The annotation file must contain exactly 520 unique IDs matching the inbox.
- Preserve the human annotation file byte-for-byte; fold generation must never
  rewrite it.
- Never read `download/`, `ground_truth*.json`, evaluator code, sample defaults,
  or submission feedback as labels.

The observed human-label distribution is:

- Document Comparison: 220
- New SI Request: 125
- Invoice Query: 75
- General Message: 60
- Spam: 40

## Category Normalization

Normalize human-readable labels only in generated fold artifacts:

| Human label | Internal category |
|---|---|
| Document Comparison | `bl_comparison` |
| New SI Request | `new_si_request` |
| Invoice Query | `invoice_query` |
| General Message | `general_message` |
| Spam | `spam` |

Reject empty labels, unknown spellings, duplicate IDs, missing inbox IDs, and
annotation IDs that are not present in the inbox. Do not silently guess or
rewrite an unknown category.

## Fold Strategy

Use scikit-learn's `StratifiedGroupKFold` with:

```python
n_splits=5
shuffle=True
random_state=20260921
```

The class label is the normalized internal category. The group value comes from
the existing exact/template duplicate grouping in
`email_classification.splitting.build_split_records()`.

Each email must be assigned to exactly one validation fold numbered 1 through
5. For fold N, validation consists of records assigned to N and training is the
complement. No `group_id` may occur in more than one validation fold.

Fold sizes may differ slightly because preserving duplicate groups takes
priority over exactly equal record counts. Every fold must contain all five
categories. Report per-fold category counts and deviations from the overall
distribution.

## Dependency

Install scikit-learn into the project virtual environment after the
implementation plan is approved. Record the exact resolved version in
`requirements.txt` so teammate environments can reproduce the same assignments.
Do not install packages into the system or Anaconda Python.

## Outputs

Create, without modifying `annotations.csv`:

- `data/splits/cv_assignments.csv`
- `data/splits/cv_folds.json`

`cv_assignments.csv` contains sorted records with these columns:

```text
email_id,category,group_id,fold
```

`cv_folds.json` contains:

- schema version;
- split strategy and fixed seed;
- scikit-learn version;
- source ID hash;
- annotation file SHA-256;
- total record and group counts;
- overall category distribution;
- each fold's training/validation sizes and category distributions.

Training IDs are inferred as all assignments whose fold differs from the active
fold. The JSON does not duplicate complete email bodies or private labels.

## Existing Split Files

Keep `annotation_pool.json` and `production.json` unchanged for audit history,
but mark the 120/400 workflow as superseded in documentation. Do not use
`development.json` or `final_test.json` for the cross-validation workflow.

## Command

Extend the split command with:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_splits.py cross-validate download2 data\splits\annotations.csv data\splits
```

The command validates inbox data and annotations before generating either
output. Existing outputs may be reused only when their bytes exactly match the
new deterministic result; conflicting files must not be overwritten silently.

## Verification

Automated and real-data checks must prove:

- exactly 520 assignment rows and 520 unique IDs;
- all inbox IDs and annotation IDs match;
- each record has one fold in the range 1-5;
- each record acts as validation data exactly once;
- no duplicate/template group crosses folds;
- all five categories appear in every validation fold;
- overall normalized counts remain 220/125/75/60/40;
- repeated generation is byte-for-byte identical;
- `annotations.csv` and all `download2` inputs remain unchanged;
- no evaluator-only file is accessed.

## Evaluation Use

Rules, prompts, thresholds, and later classifiers must be evaluated by producing
out-of-fold predictions: fit or configure on four folds and score on the held-out
fold, repeated five times. Aggregate Macro F1, Macro Recall, per-class metrics,
confusion matrix, and `bl_comparison` false negatives across all 520 out-of-fold
predictions.

Because there is no untouched final holdout, cross-validation results are a
development estimate. Lock the final configuration before reporting the final
out-of-fold score, then fit or configure the production system using all 520
labels.
