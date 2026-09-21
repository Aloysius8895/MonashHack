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

## Prepare cross-validation folds

The earlier 120/400 annotation split and 80/40 development/test split are kept
only as audit history. They are superseded by deterministic, group-aware,
stratified five-fold cross-validation over all 520 human-labeled emails.

`data/splits/annotations.csv` must contain exactly one complete row for every
inbox email. Human category values are:

- `Document Comparison`
- `New SI Request`
- `Invoice Query`
- `General Message`
- `Spam`

Install the reproducible project dependency and generate fold assignments:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\prepare_splits.py cross-validate download2 data\splits\annotations.csv data\splits
```

The command writes `data/splits/cv_assignments.csv` and
`data/splits/cv_folds.json`. It preserves duplicate/template groups within a
single validation fold and never rewrites `annotations.csv`.
