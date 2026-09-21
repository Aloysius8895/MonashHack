# MonashHack

Email classification and shipping-document verification project.

## Participant data

Use `download2/` as the application input. The original inbox and attachment
files are immutable. The ignored `download/` directory contains evaluator-only
material and must never be used by the production pipeline.

## Validate the inbox

Run the Step 2 read-only validator with the project Python environment:

```powershell
.\.venv\Scripts\python.exe scripts\validate_inbox.py download2
```

The command validates email fields, IDs, attachment paths, and local attachment
existence, then prints a JSON dataset summary. It does not classify messages or
read attachment contents.

## Classification output contract

Later classification steps will write generated records under
`outputs/usable/` and `outputs/unusable/`; source records will not be moved.
The internal categories will be `bl_comparison`, `spam`, `general_message`,
`invoice_query`, and `new_si_request`. The official submission adapter will map
these values to the competition's required category names.

## Prepare human annotation splits

Create the deterministic 120-email annotation pool and retain the other 400
emails for production processing:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_splits.py select download2 data\splits
```

Fill only the `category` and optional `notes` columns in
`data/splits/annotations.csv`. Every category must be one of:

- `bl_comparison`
- `new_si_request`
- `invoice_query`
- `general_message`
- `spam`

After all 120 rows have been reviewed by a human, create the 80-email
development set and locked 40-email final test set:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_splits.py finalize data\splits
```

Do not use IDs or labels from `final_test.json` to adjust classification rules,
LLM prompts, confidence thresholds, or review logic. Keep the original inbox
and generated split manifests unchanged while annotation is in progress.
