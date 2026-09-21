# Labeling and Splits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select a deterministic, leakage-safe 120-email annotation pool, retain 400 production emails, and create an exact group-aware 80/40 development/final-test split after human labels are complete.

**Architecture:** Add pure split algorithms in `src/email_classification/splitting.py` and artifact serialization in `src/email_classification/split_artifacts.py`. A standard-library CLI reads the validated participant Inbox for Stage A and reads only generated manifests plus human annotations for Stage B. Dynamic-programming selection keeps duplicate/template groups intact while minimizing observable-stratum or category-distribution differences.

**Tech Stack:** Python 3.12 standard library, `csv`, `dataclasses`, `hashlib`, `json`, `pathlib`, `random`, `re`, `unittest`.

## Global Constraints

- Read application inputs only from `download2/inbox/` and attachment metadata.
- Never read `download/`, `ground_truth*.json`, evaluator code, or submission feedback.
- Keep original inbox JSON and attachments unchanged.
- Use seed `20260921` and stable SHA-256 identifiers; never use process-randomized `hash()`.
- Keep exact and conservative template duplicates in one group across every boundary.
- Human labels are exactly `bl_comparison`, `new_si_request`, `invoice_query`, `general_message`, and `spam`.
- Do not train a model or assign inferred labels in Step 3.
- Stage A must contain exactly 120 annotation IDs and 400 production IDs.
- Stage B must contain exactly 80 development IDs and 40 locked final-test IDs.
- Final-test labels must not be imported by production classification modules.

---

### Task 1: Stable duplicate groups and Stage A selection

**Files:**
- Create: `src/email_classification/splitting.py`
- Modify: `src/email_classification/__init__.py`
- Create: `tests/test_splitting.py`

**Interfaces:**
- Consumes: validated email dictionaries with `email_id`, `subject`, `body`, and `attachments`.
- Produces: `SplitRecord`, `StageASelection`, `build_split_records(records)`, and `select_annotation_pool(records, pool_size, seed)`.

- [ ] **Step 1: Write failing grouping tests**

Create helpers that generate unique records and records differing only by email
addresses, URLs, or numbers. Assert exact and template variants receive the same
group ID, unrelated records receive different IDs, and repeated calls produce
identical IDs.

```python
def test_template_variants_share_a_stable_group(self):
    records = [
        make_email("email_001", "Reminder 100", "Visit https://a.example/100"),
        make_email("email_002", "Reminder 200", "Visit https://b.example/200"),
        make_email("email_003", "Unrelated", "Different body"),
    ]

    first = build_split_records(records)
    second = build_split_records(records)

    self.assertEqual(first, second)
    self.assertEqual(first[0].group_id, first[1].group_id)
    self.assertNotEqual(first[0].group_id, first[2].group_id)
```

Also test attachment patterns `none`, `si`, `bl`, `si_bl`, and `other` from
filenames only. The code must not open attachments.

- [ ] **Step 2: Run grouping tests and verify failure**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_splitting -v`

Expected: FAIL because `email_classification.splitting` does not exist.

- [ ] **Step 3: Implement normalization and connected grouping**

Define these public dataclasses and constants:

```python
DEFAULT_SPLIT_SEED = 20260921


@dataclass(frozen=True)
class SplitRecord:
    email_id: str
    group_id: str
    attachment_pattern: str


@dataclass(frozen=True)
class StageASelection:
    annotation_pool: tuple[SplitRecord, ...]
    production: tuple[SplitRecord, ...]
    seed: int
    source_id_hash: str
```

Normalize exact text with Unicode-safe lowercase and collapsed whitespace.
Create the template signature by replacing email addresses, HTTP(S) URLs, and
numeric tokens with `<email>`, `<url>`, and `<n>`. Use a union-find structure:
union records sharing an exact signature, then union records sharing a template
signature. Derive each `group_id` as `group_` plus the first 12 hexadecimal
characters of SHA-256 over sorted member IDs joined by newline.

- [ ] **Step 4: Write failing Stage A tests**

Generate 520 records containing duplicate groups and all attachment patterns.
Assert:

```python
selection = select_annotation_pool(records, pool_size=120, seed=20260921)
self.assertEqual(len(selection.annotation_pool), 120)
self.assertEqual(len(selection.production), 400)
self.assertEqual(
    {r.email_id for r in selection.annotation_pool}
    & {r.email_id for r in selection.production},
    set(),
)
self.assertEqual(selection, select_annotation_pool(records, 120, 20260921))
```

Build a map from `group_id` to assigned split and assert every group has exactly
one assignment. Assert every attachment pattern present in at least two source
records appears in the annotation pool when the pool is large enough.

- [ ] **Step 5: Implement exact pattern-stratified selection**

Group `SplitRecord` instances by `group_id`. Represent each group as a count
vector over sorted attachment patterns. Order groups by SHA-256 of
`f"{seed}:{group_id}"`.

Use dynamic programming from the zero vector. For each group, retain one stable
group-ID tuple for every reachable count vector whose total does not exceed
`pool_size`. First restrict vectors totaling `pool_size` to those containing at
least one record from every observed attachment pattern. Raise `SplitError` if
the requested pool is too small to provide that coverage without breaking a
group. Choose the remaining vector minimizing:

```python
sum(
    (selected_count - source_count * pool_size / len(records)) ** 2
    for selected_count, source_count in zip(vector, source_vector)
)
```

Use the selected group-ID tuple as the tie breaker. Raise `SplitError` if no
exact group-preserving selection exists. Sort both output record tuples by
`email_id`. Compute `source_id_hash` from all sorted source IDs.

- [ ] **Step 6: Run Task 1 tests**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_splitting -v`

Expected: all grouping and Stage A tests PASS.

- [ ] **Step 7: Export Stage A interfaces and commit**

Export the Task 1 public names from `src/email_classification/__init__.py`, then:

```powershell
git add -- src/email_classification tests/test_splitting.py
git commit -m "feat: add leakage-safe annotation pool selection"
```

### Task 2: Human-label validation and Stage B split

**Files:**
- Modify: `src/email_classification/splitting.py`
- Modify: `src/email_classification/__init__.py`
- Modify: `tests/test_splitting.py`

**Interfaces:**
- Consumes: the 120 `SplitRecord` entries from Stage A and a mapping from email ID to human category.
- Produces: `ALLOWED_CATEGORIES`, `StageBSelection`, and `finalize_labeled_split(annotation_pool, labels, development_size, test_size, seed)`.

- [ ] **Step 1: Write failing label-validation tests**

Test missing labels, extra IDs, invalid categories, duplicate IDs supplied by the
CSV parser, and an incorrect total size. Every failure must raise `SplitError`
with a message naming the problem but not printing email bodies.

```python
with self.assertRaisesRegex(SplitError, "missing labels"):
    finalize_labeled_split(pool, incomplete_labels, 80, 40, 20260921)

with self.assertRaisesRegex(SplitError, "invalid category"):
    finalize_labeled_split(pool, invalid_labels, 80, 40, 20260921)
```

- [ ] **Step 2: Write failing exact 80/40 tests**

Create 120 labeled records across all five categories and several multi-record
groups. Assert exact sizes, full coverage, no overlap, group isolation, category
coverage where reachable, and deterministic output.

- [ ] **Step 3: Run Stage B tests and verify failure**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_splitting -v`

Expected: FAIL because Stage B interfaces do not exist.

- [ ] **Step 4: Implement category-aware dynamic programming**

Define:

```python
ALLOWED_CATEGORIES = frozenset(
    {
        "bl_comparison",
        "new_si_request",
        "invoice_query",
        "general_message",
        "spam",
    }
)


@dataclass(frozen=True)
class StageBSelection:
    development: tuple[SplitRecord, ...]
    final_test: tuple[SplitRecord, ...]
    seed: int
    source_id_hash: str
```

Validate that labels contain exactly the annotation-pool IDs and only allowed
categories. Build each group's vector over categories, then use the same stable
dynamic-programming method with target `test_size`. When at least one reachable
vector places every category having two or more records in both development and
final test, restrict candidates to those vectors. Select the remaining vector
minimizing squared distance from the proportional category target. The final
test contains selected groups; development contains the remainder.

Verify `development_size + test_size == len(annotation_pool)` and raise
`SplitError` if an exact group-preserving target is impossible.

- [ ] **Step 5: Run all split tests**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_splitting -v`

Expected: all Tasks 1-2 tests PASS.

- [ ] **Step 6: Export Stage B interfaces and commit**

```powershell
git add -- src/email_classification tests/test_splitting.py
git commit -m "feat: add group-aware development and test split"
```

### Task 3: Atomic manifests and annotation CSV

**Files:**
- Create: `src/email_classification/split_artifacts.py`
- Modify: `src/email_classification/__init__.py`
- Create: `tests/test_split_artifacts.py`

**Interfaces:**
- Consumes: `StageASelection`, `StageBSelection`, manifests, and annotation CSV rows.
- Produces: `write_stage_a(output_dir, selection)`, `read_manifest(path)`, `read_annotations(path)`, and `write_stage_b(output_dir, selection)`.

- [ ] **Step 1: Write failing Stage A artifact tests**

In a temporary directory, write a small Stage A selection and assert:

- manifest metadata contains schema version 1, seed, split, and source ID hash;
- records contain only `email_id`, `group_id`, and `attachment_pattern`;
- records are sorted by ID;
- `annotations.csv` has `email_id,category,notes` and blank categories;
- rerunning identical output succeeds without changing bytes;
- a conflicting existing file raises `ArtifactError` without overwriting it.

- [ ] **Step 2: Run artifact tests and verify failure**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_split_artifacts -v`

Expected: FAIL because `split_artifacts` does not exist.

- [ ] **Step 3: Implement deterministic serialization and atomic writes**

Serialize JSON with UTF-8, `indent=2`, `sort_keys=True`, and a trailing newline.
Serialize CSV with `lineterminator="\n"`. Precompute all Stage A byte payloads,
preflight every existing target, write temporary files in the destination, then
replace final targets with `Path.replace()` only after every temporary write
succeeds. Always remove remaining temporary files in `finally`.

`read_manifest()` must validate schema version, metadata types, record fields,
sorted unique IDs, unique split name, and source hash. `read_annotations()` must
reject duplicate IDs and return both the label mapping and notes mapping.

- [ ] **Step 4: Write and implement Stage B artifact tests**

Assert `write_stage_b()` creates `development.json` and `final_test.json`, never
modifies `annotations.csv`, and emits no category in either manifest. Assert a
source hash mismatch raises `ArtifactError` before writing.

- [ ] **Step 5: Run artifact tests**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_split_artifacts -v`

Expected: all artifact tests PASS.

- [ ] **Step 6: Export artifact interfaces and commit**

```powershell
git add -- src/email_classification tests/test_split_artifacts.py
git commit -m "feat: persist split manifests safely"
```

### Task 4: Split command and real Stage A generation

**Files:**
- Create: `scripts/prepare_splits.py`
- Create: `tests/test_prepare_splits_cli.py`
- Modify: `README.md`
- Create: `data/splits/annotation_pool.json`
- Create: `data/splits/production.json`
- Create: `data/splits/annotations.csv`

**Interfaces:**
- Consumes: `select <bundle> <output_dir>` or `finalize <output_dir>`.
- Produces: exit code 0 with a JSON summary, or exit code 1 with a safe diagnostic.

- [ ] **Step 1: Write failing CLI tests**

Build a temporary 520-record participant bundle with a minimal compatible
`loader.py`. Assert `select` creates exact 120/400 outputs and prints:

```json
{
  "annotation_pool": 120,
  "production": 400,
  "seed": 20260921
}
```

Assert `select` rejects a missing bundle, an evaluator-like bundle containing
`ground_truth.json`, and a bundle that fails Step 2 validation.

- [ ] **Step 2: Run select CLI tests and verify failure**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_prepare_splits_cli -v`

Expected: FAIL because `scripts.prepare_splits` does not exist.

- [ ] **Step 3: Implement the select command**

Reuse the participant-loader isolation pattern from `scripts/validate_inbox.py`.
Call `load_and_validate(Inbox(bundle), data_root=bundle)`, then
`select_annotation_pool(records, 120, 20260921)` and `write_stage_a()`.

Before loading, reject a path named `download`, any recursively discovered
`ground_truth*.json`, a missing `inbox/`, or a missing `loader.py`.

- [ ] **Step 4: Write failing finalize CLI tests**

Assert incomplete annotations return 1 and create no Stage B manifests. Fill all
120 categories with valid synthetic labels, run `finalize`, and assert exact
80/40 output and this summary:

```json
{
  "development": 80,
  "final_test": 40,
  "seed": 20260921
}
```

- [ ] **Step 5: Implement the finalize command**

Read `annotation_pool.json` and `annotations.csv`, validate their ID sets and
source hash, call `finalize_labeled_split()`, and write Stage B manifests. Do not
open `production.json`, inbox files, attachments, or evaluator files while
computing category stratification.

- [ ] **Step 6: Document the workflow**

Add the exact commands and boundaries to `README.md`. State that users fill only
the `category` and optional `notes` columns, all 120 labels must be complete, and
`final_test.json` IDs must not be used for rule or prompt tuning.

- [ ] **Step 7: Run all automated tests**

Run: `\.venv\Scripts\python.exe -m unittest discover -s tests -v`

Expected: all Step 2 and Step 3 tests PASS.

- [ ] **Step 8: Generate real Stage A artifacts**

Run:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_splits.py select download2 data\splits
```

Expected: 120 annotation records, 400 production records, and 120 blank
annotation rows.

- [ ] **Step 9: Verify leakage and reproducibility**

Run the select command again and verify generated files are byte-identical.
Programmatically assert complete 520-ID coverage, zero split overlap, zero group
crossing, and blank categories. Confirm protected participant files have no Git
diff and `finalize` currently fails because human labels are intentionally empty.

- [ ] **Step 10: Commit Task 4**

```powershell
git add -- scripts/prepare_splits.py tests/test_prepare_splits_cli.py README.md data/splits
git commit -m "feat: prepare human annotation splits"
```
