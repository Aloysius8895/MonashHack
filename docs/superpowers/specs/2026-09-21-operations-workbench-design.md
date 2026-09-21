# Shipping Operations Workbench Design

**Date:** 2026-09-21  
**Branch:** `feat/frontend-demo`  
**Status:** Proposed for implementation

## Purpose

Refactor the existing Streamlit prototype into a simple shipping-operations
workbench that a non-technical user can operate in roughly five clicks. The
application must process uploaded inbox records and attachments through the
repository's real classifier, extractors, normalizers, and seven-field
comparator. It must make the operational outcome and next action obvious while
keeping model details out of the main workflow.

This is an extension of the existing frontend and backend integration. It is
not a rewrite and does not introduce a separate API or persistent database.

## Scope

The refactor includes:

- batch JSON inbox parsing and in-memory attachment matching;
- five reproducible demo scenarios that use the real pipeline;
- a visible, per-email pipeline trace;
- confidence assessment from real pipeline signals;
- an in-session human-review queue and resolution controls;
- operational reports and downloads;
- a session dashboard;
- documentation and automated tests.

The refactor excludes authentication, persistent storage, email-provider
integration, collaboration, background jobs, and production workflow
orchestration.

## Architecture

The existing backend remains authoritative:

- the committed TF-IDF/scikit-learn artifact classifies email content;
- routing determines whether an email is a document-comparison request;
- existing multi-format extractors read TXT, PDF, DOCX, and XLSX data;
- existing normalization and comparison logic evaluates the seven canonical
  fields.

The frontend is divided into three responsibilities:

1. `streamlit_app.py` renders controls and four tabs, and stores the current
   session's workbench state in `st.session_state`.
2. `src/frontend/service.py` adapts inbox records and uploaded bytes to the
   existing backend and returns structured pipeline results.
3. Focused frontend modules hold report wording, human-review transitions, CSV
   generation, and dashboard aggregation so these behaviours can be tested
   without rendering Streamlit.

No uploaded file is written to the repository or local disk.

## Core Data Model

Each processed email has one session record containing:

- the validated source email record;
- matched SI and draft-BL upload references;
- the immutable automated result used for `submission.json`;
- the pipeline-stage trace;
- operational confidence percentage, level, and reasons;
- the current final result shown in the report/dashboard;
- optional human-review decisions and a `reviewed_by_human` flag.

The automated result and final result are intentionally separate. Human review
may change the report and dashboard, but never rewrites the official automated
submission payload.

## Input and Attachment Matching

The Input & Run tab accepts one or more JSON files. Each file may contain one
email object or a list of email objects. Required fields are `email_id`, `from`,
`subject`, `body`, and `attachments`; `attachments` must be a list of paths.
Invalid records are reported in plain English and do not prevent other valid
records from running.

Users upload multiple attachments separately. Files are held as bytes in
memory and indexed by basename. A JSON path such as
`attachments/email_001_SI.txt` therefore matches an uploaded file named
`email_001_SI.txt`. Duplicate uploaded basenames are rejected as ambiguous.
Any listed attachment without a matching upload is unavailable and follows the
missing-attachment branch.

Manual entry remains inside a collapsed expander and supports subject, body,
SI, and draft-BL inputs.

## Demo Scenarios

The selector can run one scenario, and **Run all demo scenarios** fills the
session report/dashboard. Every output is calculated by the real pipeline.

1. **All fields match:** real `email_001` plus its unmodified SI and draft BL.
2. **Mismatch:** real `email_001`; an in-memory copy of its draft BL changes
   consignee and container count before extraction.
3. **Missing BL:** real `email_001` without the draft-BL bytes.
4. **Needs human review:** real `email_001` with an unreadable attachment or a
   genuine missing value, producing low confidence.
5. **Classification only:** a real non-comparison email record, with no
   document comparison performed.

Scenario construction changes inputs only. Expected statuses and field results
are never injected into the result.

## Required Pipeline Flow

Every processed email follows and records this decision flow:

1. Inbox
2. Classifier
3. Document comparison request?
4. For No: Classify only
5. For Yes: Attachment check
6. SI + BL available?
7. For No: Human Review
8. For Yes: Extraction
9. Normalization
10. Comparison
11. Confidence check
12. For Low: Human Review
13. For High: Final result
14. Report
15. Dashboard

The Input & Run tab shows a compact highlighted path and a plain-English stage
list. Executed stages receive check marks and one-line outcomes. Skipped stages
are greyed out. The compact route and stage list are the complete workflow
visualization; no additional diagram is shown.

Classification-only emails still create report and dashboard entries reading
“Classified only, no action needed.”

## Confidence

The displayed percentage is an operational-confidence score, not a calibrated
probability of correctness or match. It is derived only from real signals:

- the classifier's winning-score margin relative to the trained review-margin
  threshold;
- completeness of the 14 required SI/BL field values;
- unreadable, wrong-document, missing-value, garbled, OCR, and LLM-fallback
  flags;
- whether the comparison produces a definite result for every field.

The score calculation is deterministic and returns both a percentage and
plain-English reasons. A comparison is always Low when any required field is
missing, unreadable, ambiguous, or unparsed, or when the classifier falls below
its trained threshold. Otherwise it is High. The UI default display threshold
is 80%; it can be adjusted only under Technical details.

A mismatch may have High confidence: confidence measures certainty of the
pipeline's evidence, not likelihood that documents match.

## Human Review

The **Human Review (n)** tab lists only pending cases. Each case shows the
review reason, missing or uncertain information, and side-by-side raw SI/BL
evidence for affected fields.

For field-level uncertainty, the reviewer selects one of:

- SI is correct;
- BL is correct;
- Enter value.

For a missing attachment, the reviewer uploads the required document and
clicks **Re-run**, which executes the real pipeline again. The reviewer may
also choose **Approve – no mismatch** or **Confirm mismatch**. Submitting a
decision updates the final result, tags it `Reviewed by human`, removes it from
the pending queue, and immediately refreshes the report and dashboard.

## Page Layout

The app uses wide layout, no sidebar, and four tabs.

### Input & Run

- inbox JSON uploader;
- multi-file attachment uploader;
- demo-scenario selector;
- Run selected and Run all controls;
- collapsed manual-entry expander;
- latest processed email's path strip, stage list, and collapsed full flow.

### Human Review (n)

- pending cases only;
- clear reason and required action;
- affected-field evidence and correction controls;
- missing-attachment upload and Re-run;
- approval/confirmation controls.

### Report

Every processed email starts with one badge:

- NO MISMATCH DETECTED;
- ACTION REQUIRED – n mismatch(es);
- HUMAN REVIEW;
- CLASSIFIED ONLY.

The badge is followed by a one-sentence verdict, concrete next step, and the
seven-row table for comparison requests. The table contains only Field, SI
value, BL value, and Result. Cleaned values and source evidence are placed in
per-field expanders. CSV and `submission.json` downloads are available.

### Dashboard

KPI cards show processed emails, comparison requests, no mismatch, mismatch,
waiting for review, and resolved by human. At most three charts show category,
outcome, and frequently mismatched fields. A filterable Needs action table is
sorted by urgency and includes each email's concrete next step.

## Official Submission Output

The downloadable JSON is keyed by `email_id`. Each value contains exactly:

- `category`;
- `status`;
- `review_reason`;
- `defect_fields`;
- `has_defect`.

Allowed categories are `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`,
`GENERAL`, and `SPAM`. Status is `OK`, `MISMATCH`, or `NEEDS_REVIEW`.
Review reason is null or one of `wrong_doc_type`, `missing_attachment`,
`unreadable`, and `missing_value`. Non-comparison results use `OK`, null review
reason, an empty defect list, and false `has_defect`.

## UI Language

Main-screen text uses operational language. “Cleaned value” replaces
“normalized value”; model names, raw model scores, thresholds, and rule names
do not appear in the primary workflow.

A collapsed **Technical details** section contains model identity and scores,
the confidence threshold, per-email automated submission JSON, and the explicit
statement that JEV is a future enhancement and is not used by this prototype.

## Error Handling

- Invalid JSON and schema errors identify the affected file/record.
- Duplicate email IDs and ambiguous attachment basenames are rejected clearly.
- One failed email does not discard other successfully processed emails.
- Extractor failures become human-review results, not page crashes.
- Runtime/model configuration failures display a safe configuration message.
- Downloads remain unavailable until at least one valid record is processed.

## Testing

Tests cover:

- parsing a single JSON object and a list;
- schema validation and duplicate detection;
- basename attachment matching and missing uploads;
- classify-only, missing-attachment, high-confidence, mismatch, and
  low-confidence branches;
- pipeline stage traces and confidence reasons;
- human-review decisions and re-run behaviour;
- separation of automated submission and human-adjusted final state;
- exact submission schema;
- report CSV rows and dashboard aggregation;
- Streamlit AppTest coverage of the four tabs and all demo controls;
- the existing repository suite.

## Documentation and Deployment

The README will retain pinned-dependency local setup and Streamlit Community
Cloud deployment instructions. It will describe the trained classifier and
document extraction as the AI components, the hosted Streamlit app as cloud
infrastructure, and provide a five-minute click order covering the five flow
branches. No deployment secret is required.

## Completion Conditions

The work is complete when:

- all specified inputs and four tabs function in a single Streamlit session;
- every flow stage is represented in code and visible in the UI;
- all five real-pipeline demo scenarios populate reports and the dashboard;
- human-review resolution updates final operational views but not the automated
  submission payload;
- the full test suite and headless Streamlit tests pass;
- the app starts locally and the final UI is visually checked;
- changes remain uncommitted and unpushed until the user explicitly confirms.
