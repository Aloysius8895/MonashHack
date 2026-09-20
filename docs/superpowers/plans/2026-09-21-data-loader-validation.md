# Data Loader and Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standard-library data loader that validates Inbox-compatible email records and produces a reproducible dataset summary without accessing evaluator-only data.

**Architecture:** Keep the organizer-provided `download2/loader.py` unchanged. Add an `email_classification` package under `src/` that accepts any object exposing `emails()`, performs record and local attachment validation, and returns detached validation results. Add a small command-line adapter for read-only validation of `download2`.

**Tech Stack:** Python 3.12 standard library, `dataclasses`, `pathlib`, `unittest`.

## Global Constraints

- Do not read from `download/`, `ground_truth*.json`, evaluator code, or submission feedback.
- Do not modify files under `download2/inbox/` or `download2/attachments/`.
- Keep `download2/loader.py` compatible and unchanged.
- Do not classify emails or train a model in Step 2.
- Use internal category `bl_comparison` in later routing; Step 2 does not assign categories.
- Use only Python's standard library.

---

### Task 1: Validation types and record checks

**Files:**
- Create: `src/email_classification/__init__.py`
- Create: `src/email_classification/data_loader.py`
- Create: `tests/__init__.py`
- Create: `tests/test_data_loader.py`

**Interfaces:**
- Consumes: dictionaries returned by an Inbox-compatible object's `emails()` method.
- Produces: `ValidationIssue`, `DatasetSummary`, `ValidationResult`, `DatasetValidationError`, and `load_and_validate(inbox, data_root=None, strict=True)`.

- [ ] **Step 1: Write failing tests for valid records and summary fields**

```python
class FakeInbox:
    def __init__(self, records):
        self._records = records

    def emails(self):
        return self._records


def make_email(email_id="email_001", attachments=None, **overrides):
    record = {
        "email_id": email_id,
        "from": "sender@example.com",
        "subject": "Please check attached documents",
        "body": "Attached are the SI and draft BL.",
        "attachments": [] if attachments is None else attachments,
    }
    record.update(overrides)
    return record


class DataLoaderTests(unittest.TestCase):
    def test_valid_records_are_preserved_and_summarized(self):
        records = [make_email(), make_email("email_002", subject="", body="")]
        result = load_and_validate(FakeInbox(records))

        self.assertEqual(result.records, tuple(records))
        self.assertEqual(result.summary.total_emails, 2)
        self.assertEqual(result.summary.valid_emails, 2)
        self.assertEqual(result.summary.empty_subjects, 1)
        self.assertEqual(result.summary.empty_bodies, 1)
        self.assertEqual(result.issues, ())
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_data_loader.DataLoaderTests.test_valid_records_are_preserved_and_summarized -v`

Expected: FAIL because `email_classification.data_loader` does not exist.

- [ ] **Step 3: Implement immutable result types and basic record validation**

Implement these public shapes in `data_loader.py`:

```python
class InboxLike(Protocol):
    def emails(self) -> Iterable[Mapping[str, object]]:
        raise NotImplementedError


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    email_id: str | None = None
    field: str | None = None
    attachment: str | None = None


@dataclass(frozen=True)
class DatasetSummary:
    total_emails: int
    valid_emails: int
    invalid_emails: int
    with_attachments: int
    without_attachments: int
    attachment_references: int
    attachment_extensions: dict[str, int]
    empty_subjects: int
    empty_bodies: int
    validation_errors: int


@dataclass(frozen=True)
class ValidationResult:
    records: tuple[dict[str, object], ...]
    summary: DatasetSummary
    issues: tuple[ValidationIssue, ...]


class DatasetValidationError(ValueError):
    def __init__(self, issues: Sequence[ValidationIssue]):
        self.issues = tuple(issues)
        super().__init__(f"Dataset validation failed with {len(self.issues)} issue(s)")


def load_and_validate(
    inbox: InboxLike,
    data_root: str | Path | None = None,
    strict: bool = True,
) -> ValidationResult:
    try:
        records = list(inbox.emails())
    except Exception as exc:
        issue = ValidationIssue("inbox_read_error", f"Could not read inbox: {exc}")
        raise DatasetValidationError((issue,)) from exc
    return _validate_records(records, data_root=data_root, strict=strict)
```

Define the private helper with the exact signature
`_validate_records(records: Sequence[object], data_root: str | Path | None,
strict: bool) -> ValidationResult`. It owns all per-record checks, issue
collection, detached copies, and summary construction.

Require `email_id`, `from`, `subject`, `body`, and `attachments`. Require
strings for the first four fields and a list of strings for attachments. Treat
an absent field or wrong type as invalid. Accept empty subject/body strings and
count them in the summary. Match IDs against `^email_\d{3}$` and reject duplicate
IDs. Copy each accepted record with `copy.deepcopy(record)` so later caller
changes cannot mutate the validated result. Build `DatasetSummary` from all read
records and set `validation_errors` to the number of collected issues.

In `tests/__init__.py`, add the repository `src/` directory to `sys.path` so the
documented `python -m unittest` commands work without installing the package:

```python
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
```

- [ ] **Step 4: Add failing malformed-record tests**

Add tests asserting stable issue codes for:

```python
cases = [
    (make_email(email_id="001"), "invalid_email_id"),
    ({"email_id": "email_001"}, "missing_field"),
    (make_email(subject=42), "invalid_field_type"),
    (make_email(attachments="attachments/a.txt"), "invalid_field_type"),
]
```

Also test duplicate `email_001` records. In `strict=False`, assert issues are
collected and only valid records appear in `result.records`. In `strict=True`,
assert `DatasetValidationError` exposes the complete `issues` tuple.

- [ ] **Step 5: Run all record-validation tests**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_data_loader -v`

Expected: all Task 1 tests PASS.

- [ ] **Step 6: Export the public API**

In `src/email_classification/__init__.py`, export exactly:

```python
from .data_loader import (
    DatasetSummary,
    DatasetValidationError,
    ValidationIssue,
    ValidationResult,
    load_and_validate,
)

__all__ = [
    "DatasetSummary",
    "DatasetValidationError",
    "ValidationIssue",
    "ValidationResult",
    "load_and_validate",
]
```

- [ ] **Step 7: Commit Task 1**

```powershell
git add -- src/email_classification tests
git commit -m "feat: validate inbox email records"
```

### Task 2: Safe local attachment validation

**Files:**
- Modify: `src/email_classification/data_loader.py`
- Modify: `tests/test_data_loader.py`

**Interfaces:**
- Consumes: `data_root` and attachment strings such as `attachments/email_001_SI.txt`.
- Produces: issue codes `invalid_attachment_path` and `missing_attachment` plus extension counts.

- [ ] **Step 1: Write failing attachment tests**

Use `tempfile.TemporaryDirectory()` to create a temporary participant root with
an `attachments/` directory. Test:

```python
valid_paths = ["attachments/email_001_SI.txt"]
unsafe_paths = [
    "../download/data_v2/ground_truth.json",
    "attachments/../../outside.txt",
    "C:/absolute/file.txt",
    "/absolute/file.txt",
    "inbox/email_001.json",
]
```

Assert a valid existing file passes, a missing file yields
`missing_attachment`, and every unsafe path yields `invalid_attachment_path`.
Also assert repeated attachment paths within one record are rejected as
`duplicate_attachment`.

- [ ] **Step 2: Run attachment tests and verify they fail**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_data_loader -v`

Expected: FAIL because local attachment checks are not implemented.

- [ ] **Step 3: Implement lexical and resolved-path checks**

Normalize separators for validation only. Require every path to be relative,
contain no `..`, and begin with `attachments/`. If `data_root` is supplied,
resolve both the root and candidate path, require the candidate to remain below
`data_root/attachments`, and require `candidate.is_file()`.

Do not open attachment contents. Count extensions using lowercase suffixes such
as `.txt`; use `<none>` when a safe attachment has no suffix.

- [ ] **Step 4: Test that validation never reads attachment contents**

Give `FakeInbox` a `read_bytes()` method that raises `AssertionError`. Validate
a record whose local attachment exists and assert validation succeeds without
calling `read_bytes()`.

- [ ] **Step 5: Run the complete test module**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_data_loader -v`

Expected: all Tasks 1-2 tests PASS.

- [ ] **Step 6: Commit Task 2**

```powershell
git add -- src/email_classification/data_loader.py tests/test_data_loader.py
git commit -m "feat: validate local attachment references"
```

### Task 3: Read-only validation command and participant-data smoke test

**Files:**
- Create: `scripts/validate_inbox.py`
- Create: `tests/test_validate_inbox_cli.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: a local participant bundle path, defaulting to `download2`.
- Produces: a JSON summary on stdout and process exit code `0` for success or `1` for validation failure.

- [ ] **Step 1: Write a failing CLI test**

Patch `sys.argv` and capture stdout. Run the command's `main()` against a
temporary bundle containing one valid JSON email and no attachments. Assert it
returns `0` and prints parseable JSON with:

```json
{
  "total_emails": 1,
  "valid_emails": 1,
  "invalid_emails": 0,
  "with_attachments": 0,
  "without_attachments": 1,
  "attachment_references": 0,
  "attachment_extensions": {},
  "empty_subjects": 0,
  "empty_bodies": 0,
  "validation_errors": 0
}
```

- [ ] **Step 2: Run the CLI test and verify it fails**

Run: `\.venv\Scripts\python.exe -m unittest tests.test_validate_inbox_cli -v`

Expected: FAIL because `scripts.validate_inbox` does not exist.

- [ ] **Step 3: Implement the CLI adapter**

In `scripts/validate_inbox.py`, resolve the repository root from `__file__`, add
`src/` to `sys.path`, and load `<bundle>/loader.py` with
`importlib.util.spec_from_file_location`. Call
`load_and_validate(Inbox(bundle), data_root=bundle)` and serialize
`dataclasses.asdict(result.summary)` with sorted keys and indentation. Fail with
a clear message if the loader module cannot be created or does not expose
`Inbox`.

Accept one optional positional path argument. Reject a path named `download` or
a root containing `ground_truth*.json` with a clear stderr message before Inbox
loading, preventing accidental evaluator ingestion.

- [ ] **Step 4: Add CLI rejection tests**

Assert the CLI returns `1` for a missing bundle, a bundle without `inbox/`, and
an evaluator-like bundle containing `ground_truth.json`. Assert stderr names the
reason without printing file contents.

- [ ] **Step 5: Document the validation command**

Expand the root `README.md` with:

```powershell
.\.venv\Scripts\python.exe scripts\validate_inbox.py download2
```

State that it is read-only, does not classify messages, and must never be
pointed at `download/`.

- [ ] **Step 6: Run all automated tests**

Run: `\.venv\Scripts\python.exe -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 7: Validate the real participant dataset**

Run: `\.venv\Scripts\python.exe scripts\validate_inbox.py download2`

Expected key values:

```text
total_emails: 520
valid_emails: 520
invalid_emails: 0
attachment_references: 250
with_attachments: 126
without_attachments: 394
```

- [ ] **Step 8: Confirm protected inputs and organizer loader are unchanged**

Run:

```powershell
git diff --exit-code -- download2/loader.py download2/inbox download2/attachments
git status --short
```

Expected: no diff for protected participant files; status shows only intended
Step 2 implementation and documentation files.

- [ ] **Step 9: Commit Task 3**

```powershell
git add -- scripts/validate_inbox.py tests/test_validate_inbox_cli.py README.md
git commit -m "feat: add inbox validation command"
```
