# Data Loader and Validation Design

## Scope

Step 2 adds a participant-data loading and validation layer around the existing
`download2/loader.py` interface. It does not classify emails, train a model,
read evaluator-only files, or write routed output.

## Data Boundary

- `download2/inbox/` and `download2/attachments/` are immutable application
  inputs.
- `download2/loader.py` remains unchanged and compatible with local folders and
  HTTP sources.
- `download/`, `ground_truth*.json`, submission feedback, and evaluator code are
  forbidden inputs.
- Generated data will eventually live under `outputs/`, never inside
  `download2/`.

## Architecture

Create a focused `email_classification` package under `src/`. Its Step 2 loader
will consume records returned by the provided `Inbox` interface and produce
validated email records plus a dataset summary. Validation errors will identify
the affected email or attachment without exposing unrelated file contents.

The validation layer will:

1. Require `email_id`, `from`, `subject`, `body`, and `attachments`.
2. Require string values for the first four fields and a list of strings for
   `attachments`.
3. Reject duplicate or malformed email IDs.
4. Validate local attachment paths against the configured participant-data root
   and reject absolute paths or traversal outside that root.
5. Report missing attachment files and malformed records with clear exceptions.
6. Produce counts for emails, attachment presence, attachment extensions,
   missing text fields, and validation failures.
7. Avoid reading attachment contents during basic inbox validation.

The module will use Python's standard library so Step 2 does not introduce a
package-install requirement.

## Interfaces

The package will expose a loader that accepts an Inbox-compatible object rather
than depending on a concrete local-only implementation. This preserves both
static and HTTP operation from `download2/loader.py` and makes tests independent
of the organizer service.

Validated records retain the original five participant fields. Classification
metadata is deliberately absent in Step 2 because no classifier has run yet.

## Future Routing Contract

After classification is implemented in later authorized steps:

- `outputs/usable/` will contain document-comparison records that are ready for
  the comparison pipeline.
- `outputs/unusable/` will contain all other classified records.
- The internal `category` values will be `bl_comparison`, `spam`,
  `general_message`, `invoice_query`, and `new_si_request`.
- The official submission adapter in Step 9 will map those internal values to
  `BL_COMPARISON`, `SPAM`, `GENERAL`, `INVOICE_QUERY`, and `SI_REQUEST`.

Original inbox JSON files will never be moved or edited.

## Error Handling

Validation will fail visibly for malformed JSON-compatible records, invalid
field types, duplicate IDs, unsafe attachment paths, and missing local files.
The raised error will include a stable reason and record context. A caller may
choose strict mode for fail-fast behavior or collect all validation issues for
a complete audit.

HTTP attachment existence cannot be checked without downloading every file, so
record-level validation remains available for HTTP sources while local path and
existence checks apply only when a local data root is supplied.

## Testing

Use `unittest` with temporary directories and fake Inbox-compatible objects.
Tests will cover:

- valid records and dataset summaries;
- missing and malformed fields;
- duplicate and malformed IDs;
- missing local attachments;
- absolute paths and directory traversal;
- compatibility with an Inbox-compatible object;
- assurance that basic validation does not read attachment contents.

The real participant dataset will also receive a read-only smoke validation.

## Acceptance Criteria

- All 520 participant records validate successfully.
- The summary reports 520 emails and 250 attachment references.
- Existing `download2/loader.py` remains unchanged.
- No evaluator-only file is accessed by production code or tests.
- Automated tests pass using only the project Python standard library.
