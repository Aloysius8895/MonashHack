# Quick Email Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build, compare, select, train, and run a leakage-safe email classifier that routes all 520 inbox records into usable or unusable JSON outputs.

**Architecture:** A focused feature builder combines subject, body, attachment filenames, and compact metadata tokens. An evaluation module follows the committed group-aware folds for out-of-fold comparison of Logistic Regression and Linear SVM, then fits the selected pipeline on all legitimate labels. A routing module applies attachment and high-precision business guardrails without silently overriding strong predictions, and an orchestration CLI persists reports, the model, and per-email outputs.

**Tech Stack:** Python 3.12, scikit-learn 1.9.1, joblib, standard-library JSON/CSV, unittest.

## Global Constraints

- Read only `download2`, `data/splits/annotations.csv`, and `data/splits/cv_assignments.csv` as classification inputs.
- Never read `download`, ground truth, scoring code, evaluator-only material, or attachment contents.
- Use the existing folds and `random_state=20260921`; fit vectorizers only on each training fold.
- Normalize output categories to `bl_comparison`, `new_si_request`, `invoice_query`, `general_message`, and `spam`.
- Preserve source inbox data, annotations, and split artifacts byte-for-byte.
- Produce exactly one final route for every one of the 520 emails.
- Stop after classification; do not implement document comparison, backend submission, or external LLM calls.

---

### Task 1: Feature Construction and OOF Model Evaluation

**Files:**
- Create: `src/email_classification/features.py`
- Create: `src/email_classification/modeling.py`
- Create: `tests/test_modeling.py`
- Modify: `src/email_classification/__init__.py`

**Interfaces:**
- Consumes: validated record mappings, normalized labels, and fold assignments.
- Produces: `build_email_text(record)`, `evaluate_candidates(records, labels, folds, seed)`, `fit_final_model(records, labels, candidate_name, seed)`, serializable metrics, and OOF predictions.

- [ ] Write failing tests proving subject/body/attachment filenames and structured tokens are included, every record receives one OOF prediction, fold training excludes validation records, metrics include required class and aggregate values, and repeated runs are deterministic.
- [ ] Run `python -m unittest tests.test_modeling -v` and confirm failure from missing modules.
- [ ] Implement word unigram/bigram TF-IDF pipelines for Logistic Regression and Linear SVM with small fixed candidate variants, `class_weight` candidates, fixed seed, fold-by-fold fitting, timing, and required metrics.
- [ ] Run focused tests and commit the passing model/evaluation slice.

### Task 2: Explainable Guardrails and Routing

**Files:**
- Create: `src/email_classification/routing.py`
- Create: `tests/test_routing.py`
- Modify: `src/email_classification/__init__.py`

**Interfaces:**
- Consumes: model category, decision scores, subject/body/attachment metadata.
- Produces: `RoutingDecision(email_id, category, route, status, reason, rules_fired)` and `route_prediction(record, prediction, scores)`.

- [ ] Write failing tests for usable BL comparison with SI+BL, unusable BL comparison with missing attachment, obvious high-precision invoice/new-SI/spam evidence, ambiguous score conflict, and exactly one route per input.
- [ ] Run `python -m unittest tests.test_routing -v` and confirm missing implementation failure.
- [ ] Implement attachment metadata validation, conservative evidence rules, score-margin conflict detection derived from OOF score distributions where available, and explicit human-review reasons without inventing a probability threshold.
- [ ] Run focused tests and commit the passing routing slice.

### Task 3: Training CLI, Artifacts, and Real-Data Run

**Files:**
- Create: `scripts/run_classification.py`
- Create: `tests/test_run_classification_cli.py`
- Create: generated `artifacts/classification/*`
- Create: generated `outputs/usable/*.json`
- Create: generated `outputs/unusable/*.json`
- Modify: `README.md`

**Interfaces:**
- Consumes: `download2`, complete annotations, committed CV assignments, output root, artifact root.
- Produces: `model_comparison.json`, `oof_predictions.csv`, `confusion_matrix.json`, `selected_model.joblib`, `run_summary.json`, and one routed JSON per inbox email.

- [ ] Write failing CLI tests for source/fold/label alignment, evaluator path rejection, deterministic reports, complete exclusive routing, output schema, and source-file hash preservation.
- [ ] Run `python -m unittest tests.test_run_classification_cli -v` and confirm missing CLI failure.
- [ ] Implement orchestration, select the candidate by Macro F1 then Macro Recall then `bl_comparison` recall, fit all 520 labels, persist atomically, clear only stale generated JSON owned by this command, and print a concise summary.
- [ ] Run focused tests, all tests, and the real-data command.
- [ ] Verify 520 outputs, exact route partition, required metrics, artifact hashes on a repeated run, and unchanged annotation/inbox metadata hashes.
- [ ] Update README with install/run commands, generated paths, model-selection rule, and known limitation that OOF scores are a development estimate.
- [ ] Commit the complete quick-classification implementation and generated reproducible artifacts.

## Self-Review

- The plan covers both requested models, existing group folds, leakage-safe OOF evaluation, all required metrics, attachment guardrails, human-review handling, final training, route outputs, deterministic artifacts, and tests.
- No external LLM, backend submission, OCR, document comparison, or evaluator data is in scope.
- Every interface consumed by a later task is defined in an earlier task; no placeholder work remains.
