# MonashHack

Email classification and shipping-document verification project.

## Interactive frontend demo

The Streamlit frontend is a semi-working prototype, not a static mockup. It
uses the committed classifier, the real multi-format document extractors, and
the deterministic seven-field SI-to-draft-BL comparator. It supports editable
email content, explicit SI and draft BL uploads, all five official categories,
normalized comparison, human-review routing, traceable evidence, and a strict
organizer-format JSON result. Supported uploads are TXT, PDF, DOCX, and XLSX.

The default bundled example uses the real `email_001` record and attachments
from `download2`, so a complete path can be demonstrated without preparing
files.

### Run locally on macOS or Linux

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/streamlit run streamlit_app.py
```

### Run locally on Windows PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\streamlit.exe run streamlit_app.py
```

Open the local URL printed by Streamlit. Choose **Bundled example** and click
**Analyze email** for the shortest verified path.

### Deploy on Streamlit Community Cloud

1. Push this repository and the `feat/frontend-demo` branch to GitHub, or merge
   the branch into `main` through a pull request.
2. Sign in to [Streamlit Community Cloud](https://share.streamlit.io/) with the
   GitHub account that can read the repository.
3. Create an app, select this repository and branch, and set the entry point to
   `streamlit_app.py`.
4. Deploy. The committed `requirements.txt`, model artifact, participant demo
   data, and `.streamlit/config.toml` are sufficient; no secret is required.
5. Open the generated public URL and run the bundled example once before
   recording or submitting it.

The repository makes the app deployable but does not create a public URL by
itself. The repository owner must complete the Community Cloud connection.

### Five-minute demonstration sequence

1. Open the app with **Bundled example** selected.
2. Point out the editable subject/body and the real SI and draft BL filenames.
3. Click **Analyze email**.
4. Explain that the trained classifier selected **BL Comparison**, then show
   the routing reason and the five model scores.
5. Show the overall verification status and scan the seven-field table.
6. Use gross weight to explain normalized equality, or use a mismatched row to
   explain deterministic defect detection.
7. Expand one item under **Traceable evidence** and show its raw label, raw
   value, and source location.
8. Show the organizer-format JSON and its five exact properties.
9. Finish at the disclosure explaining that JEV is a future enhancement and is
   not used by this prototype.

### Current AI and known limitations

The email classifier uses TF-IDF text features with the selected committed
scikit-learn model and deterministic routing rules. JEV is **not** used in the
current prototype; it is a future fallback or second-opinion enhancement for
unfamiliar or low-confidence emails.

The public demo disables the optional local Ollama extraction fallback for
reproducibility. Text-based PDF, DOCX, XLSX, and TXT extraction works through
the declared Python dependencies. Scanned image-only PDFs require a working
Tesseract OCR installation on the host; if OCR is unavailable or evidence is
unreadable, the result is routed to human review rather than treated as a
match. Uploaded files are processed in memory and are not persisted by the
frontend.

### Organizer result shape

The frontend's organizer view contains exactly these five properties:

```json
{
  "category": "BL_COMPARISON",
  "status": "MISMATCH",
  "review_reason": null,
  "defect_fields": ["container_count"],
  "has_defect": true
}
```

`NEEDS_REVIEW` uses only `wrong_doc_type`, `missing_attachment`, `unreadable`,
or `missing_value`. Rich evidence remains in the interface and is not added to
the official payload.

### Preliminary submission checklist

Completed in this repository:

- working frontend source code and real end-to-end bundled demo;
- local setup and public deployment instructions;
- architecture, implementation details, limitations, and future roadmap;
- tests for classifier integration, extraction, comparison, review routing,
  and Streamlit rendering.

Team actions still required:

- deploy and submit the publicly accessible prototype URL;
- record and submit the demo video, maximum five minutes;
- submit the final project-description document or link;
- submit the slide deck/documentation link;
- include impact, metrics, results, or user feedback in the video/deck;
- complete the organizer submission before 22 September 2026 at 12:00 PM.

## Architecture

Three independent modules under `src/`, sharing one dependency:

- `email_classification` — routes inbox emails to comparison or human review
- `document_extraction` — reads the 7 SI/BL fields from txt/xlsx/docx/pdf
- `verification` — normalizes and compares SI against BL
- `contracts` — schemas, handoff files, and ports that the three share
- `pipeline` — wires the ports together
- `frontend` — adapts interactive inputs to the existing modules and preserves
  detailed evidence for Streamlit

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
