# Grouped Cross-Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate deterministic, leakage-safe, stratified 5-fold assignments for all 520 human-labeled emails while preserving duplicate/template groups.

**Architecture:** Add category normalization and fold generation to a focused `cross_validation.py` module using scikit-learn's `StratifiedGroupKFold`. Extend the artifact layer for deterministic CSV/JSON output and add a `cross-validate` CLI command that validates the Inbox and the untouched annotation file before writing. Keep the earlier 120/400 artifacts for audit history but stop using them in the active workflow.

**Tech Stack:** Python 3.12, scikit-learn 1.9.1, Python standard library, `unittest`.

## Global Constraints

- Use all 520 human-labeled emails from `data/splits/annotations.csv`.
- Preserve `data/splits/annotations.csv` byte-for-byte during fold generation.
- Never read `download/`, `ground_truth*.json`, evaluator code, sample defaults, or submission feedback as labels.
- Normalize only the five explicitly mapped human-readable category names.
- Use `StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=20260921)`.
- Keep every exact/template duplicate group in one fold.
- Number persisted folds 1 through 5.
- Require all five categories in every validation fold.
- Pin scikit-learn exactly to version 1.9.1.
- Do not train or evaluate a classifier in this change.

---

### Task 1: Dependency and complete-label validation

**Files:**
- Create: `requirements.txt`
- Create: `src/email_classification/cross_validation.py`
- Modify: `src/email_classification/__init__.py`
- Create: `tests/test_cross_validation.py`

**Interfaces:**
- Consumes: validated inbox records and the label mapping returned by `read_annotations()`.
- Produces: `CATEGORY_LABEL_MAP`, `CrossValidationError`, and `normalize_complete_labels(records, labels)`.

- [ ] **Step 1: Record and install the exact dependency**

Create `requirements.txt` with:

```text
scikit-learn==1.9.1
```

Install only into the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Verify:

```powershell
.\.venv\Scripts\python.exe -c "import sklearn; print(sklearn.__version__)"
```

Expected: `1.9.1`.

- [ ] **Step 2: Write failing category-normalization tests**

Use records with the five human labels and assert exact internal mappings:

```python
CATEGORY_LABEL_MAP = {
    "Document Comparison": "bl_comparison",
    "New SI Request": "new_si_request",
    "Invoice Query": "invoice_query",
    "General Message": "general_message",
    "Spam": "spam",
}
```

Test duplicate annotation IDs through `read_annotations()`. Test missing IDs,
unknown IDs, empty labels, unknown category spellings, and duplicate inbox IDs.
Assert unknown values raise `CrossValidationError` rather than being guessed.

- [ ] **Step 3: Run normalization tests and verify failure**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_cross_validation -v`

Expected: FAIL because `email_classification.cross_validation` does not exist.

- [ ] **Step 4: Implement complete-label normalization**

Define:

```python
class CrossValidationError(ValueError):
    pass


def normalize_complete_labels(
    records: Sequence[Mapping[str, object]],
    labels: Mapping[str, str],
) -> dict[str, str]:
```

Require exact equality between inbox and annotation ID sets. Return a new mapping
sorted by email ID with internal category values. Do not mutate either input.

- [ ] **Step 5: Run Task 1 tests and commit**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_cross_validation -v`

Expected: all normalization tests PASS.

```powershell
git add -- requirements.txt src/email_classification tests/test_cross_validation.py
git commit -m "feat: validate complete cross-validation labels"
```

### Task 2: Deterministic grouped 5-fold generation

**Files:**
- Modify: `src/email_classification/cross_validation.py`
- Modify: `src/email_classification/__init__.py`
- Modify: `tests/test_cross_validation.py`

**Interfaces:**
- Consumes: raw validated email records, human labels, `n_splits=5`, and `seed=20260921`.
- Produces: `CVAssignment`, `CVFoldSummary`, `CrossValidationPlan`, and `build_cross_validation_plan(records, labels, n_splits, seed)`.

- [ ] **Step 1: Write failing deterministic-fold tests**

Create 520 synthetic labeled records with class counts 220/125/75/60/40 plus
several exact/template duplicate groups. Assert:

```python
plan = build_cross_validation_plan(records, labels, n_splits=5, seed=20260921)
self.assertEqual(len(plan.assignments), 520)
self.assertEqual({item.fold for item in plan.assignments}, {1, 2, 3, 4, 5})
self.assertEqual(plan, build_cross_validation_plan(records, labels, 5, 20260921))
```

Assert unique IDs, each ID assigned once, no group in multiple folds, every fold
contains all categories, and overall normalized counts remain exactly:

```python
{
    "bl_comparison": 220,
    "new_si_request": 125,
    "invoice_query": 75,
    "general_message": 60,
    "spam": 40,
}
```

- [ ] **Step 2: Run fold tests and verify failure**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_cross_validation -v`

Expected: FAIL because fold-generation interfaces do not exist.

- [ ] **Step 3: Implement fold dataclasses and generation**

Define immutable dataclasses:

```python
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
    training_category_counts: dict[str, int]
    validation_category_counts: dict[str, int]


@dataclass(frozen=True)
class CrossValidationPlan:
    assignments: tuple[CVAssignment, ...]
    folds: tuple[CVFoldSummary, ...]
    seed: int
    n_splits: int
    source_id_hash: str
    total_groups: int
    overall_category_counts: dict[str, int]
    sklearn_version: str
```

Call `build_split_records(records)` for group IDs. Pass sorted email IDs as X,
normalized categories as y, and group IDs as groups to
`StratifiedGroupKFold(...).split()`. Convert zero-based split indexes to folds
1-5. Verify every validation index is assigned exactly once.

Build training counts as overall counts minus validation counts. Raise
`CrossValidationError` if any validation fold lacks a category, any group spans
folds, or the assignment count differs from the source count.

- [ ] **Step 4: Run all cross-validation tests and commit**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_cross_validation -v`

Expected: all Tasks 1-2 tests PASS.

```powershell
git add -- src/email_classification tests/test_cross_validation.py
git commit -m "feat: generate grouped stratified folds"
```

### Task 3: Deterministic artifacts and CLI integration

**Files:**
- Modify: `src/email_classification/split_artifacts.py`
- Modify: `src/email_classification/__init__.py`
- Modify: `scripts/prepare_splits.py`
- Modify: `tests/test_split_artifacts.py`
- Modify: `tests/test_prepare_splits_cli.py`
- Modify: `README.md`
- Preserve without editing: `data/splits/annotations.csv`
- Create: `data/splits/cv_assignments.csv`
- Create: `data/splits/cv_folds.json`

**Interfaces:**
- Consumes: `CrossValidationPlan`, annotation SHA-256, participant bundle, annotation path, and output directory.
- Produces: `write_cross_validation(output_dir, plan, annotation_sha256)` and CLI subcommand `cross-validate`.

- [ ] **Step 1: Write failing artifact tests**

Assert `write_cross_validation()` writes CSV columns exactly:

```text
email_id,category,group_id,fold
```

Assert assignments are sorted by email ID. Assert `cv_folds.json` contains
schema version 1, strategy `StratifiedGroupKFold`, seed, n_splits,
scikit-learn version, source ID hash, annotation SHA-256, total record/group
counts, overall category counts, and all fold summaries.

Assert identical reruns are byte-for-byte stable and conflicting existing files
raise `ArtifactError` without overwrite.

- [ ] **Step 2: Implement artifact serialization**

Reuse `_write_atomic_set()` for atomic, conflict-safe output. Validate the
annotation hash against `^[0-9a-f]{64}$`. JSON uses UTF-8, sorted keys, two-space
indentation, and a trailing newline. CSV uses UTF-8 and `\n` line endings.

- [ ] **Step 3: Write failing cross-validate CLI tests**

Create a temporary 520-email bundle and complete five-category annotation CSV.
Assert the command returns 0, writes 520 assignments, leaves annotation bytes
unchanged, and reports:

```json
{
  "folds": 5,
  "groups": 520,
  "records": 520,
  "seed": 20260921
}
```

Test missing, duplicate, unknown, empty, and invalid annotations plus evaluator
paths. Assert no output is created on failure.

- [ ] **Step 4: Implement the cross-validate command**

Add:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_splits.py cross-validate download2 data\splits\annotations.csv data\splits
```

Validate the bundle boundary, output boundary, and annotation path. Hash the
annotation bytes before parsing, load and validate all 520 inbox records, call
`build_cross_validation_plan()`, write outputs, then confirm the annotation hash
is unchanged before returning success.

- [ ] **Step 5: Update documentation**

Mark the 120/400 workflow as superseded. Document fold semantics: for fold N,
validation is rows where `fold == N`; training is rows where `fold != N`.
State that all evaluation metrics must use out-of-fold predictions.

- [ ] **Step 6: Run the full automated suite**

Run: `\.venv\Scripts\python.exe -m unittest discover -s tests -v`

Expected: all existing and new tests PASS.

- [ ] **Step 7: Generate and verify real CV artifacts**

Record the annotation SHA-256, run the real cross-validation command twice, and
verify the annotation hash is unchanged and both generated output hashes are
identical between runs.

Assert exactly 520 unique assignments, folds 1-5, no group leakage, all five
categories in every fold, and overall 220/125/75/60/40 counts.

- [ ] **Step 8: Commit generated artifacts and the supplied labels**

Stage the already user-authored annotation file without modifying its bytes so
the folds remain reproducible:

```powershell
git add -- data/splits/annotations.csv data/splits/cv_assignments.csv data/splits/cv_folds.json
git add -- src/email_classification/split_artifacts.py src/email_classification/__init__.py
git add -- scripts/prepare_splits.py tests/test_split_artifacts.py tests/test_prepare_splits_cli.py README.md
git commit -m "feat: add grouped cross-validation workflow"
```
