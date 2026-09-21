# MonashHack

Email classification and shipping-document verification project.

## Architecture

Three independent modules under `src/`, sharing one dependency:

- `email_classification` — routes inbox emails to comparison or human review
- `document_extraction` — reads the 7 SI/BL fields from txt/xlsx/docx/pdf
- `verification` — normalizes and compares SI against BL
- `contracts` — schemas, handoff files, and ports that the three share
- `pipeline` — wires the ports together

Modules never import each other; they exchange versioned JSON handoff files
through `contracts`. `tests/test_module_boundaries.py` enforces that rule.
See [docs/architecture.md](docs/architecture.md) before adding a module.

## Run the whole pipeline

Classify the inbox, then extract and verify every comparison-ready pair:

```powershell
.\.venv\Scripts\python.exe scripts\run_classification.py download2 data\splits\annotations.csv data\splits\cv_assignments.csv outputs artifacts\classification
.\.venv\Scripts\python.exe scripts\run_pipeline.py download2 outputs\handoff
```

The second command reads `outputs/handoff/classification.json` and writes
`extraction.json` and `verification.json` beside it. Pass `--no-llm-fallback`
to skip the local Ollama lookup for fields no alias matched.

## Development setup

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

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

## Train and run email classification

Evaluate Logistic Regression and Linear SVM on the committed folds, select the
best model, fit it on all legitimate labels, and classify the inbox:

```powershell
.\.venv\Scripts\python.exe scripts\run_classification.py download2 data\splits\annotations.csv data\splits\cv_assignments.csv outputs artifacts\classification
```

The selected model and evaluation reports are written under
`artifacts/classification/`. Every inbox record is written exactly once under
`outputs/usable/` or `outputs/unusable/`. Only `bl_comparison` records with
readable SI and BL attachment paths enter `usable`; uncertain, conflicting, or
incomplete cases carry an explicit `human_review` reason.

The same run publishes `outputs/handoff/classification.json`, the contract-shaped
input for document extraction. It carries published category names and the
resolved SI/BL paths for every `should_compare` email. Read it with
`contracts.read_handoff`, never by globbing `outputs/usable/` — those records are
the classification module's own diagnostics and are not a stable interface.

The reported five-fold out-of-fold metrics are a development estimate, not an
independent final-test score. The production model is fitted on all 520 labels
only after candidate selection.
