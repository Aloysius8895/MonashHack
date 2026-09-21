# Shipping Document Verification Frontend Demo Design

## Purpose

Build a publicly deployable semi-working prototype for the Averis x Monash Hackathon preliminary round. The interface must demonstrate the repository's real email-classification, document-extraction, normalization, and SI-to-draft-BL comparison logic. It must not present JEV as part of the current implementation.

The primary audience is a judging panel watching a short live demonstration. The default path must therefore be reliable, understandable without technical setup, and traceable from the email input to the extracted source evidence.

## Scope

The prototype will provide one Streamlit application with two input modes:

1. A bundled `email_001` example that loads the real participant email and attachments from `download2`.
2. Manual entry of an email subject and body plus optional SI and draft BL uploads.

Both modes use the same application service and existing repository modules. There will be no separate web API, JavaScript frontend, database, authentication system, or JEV integration in this preliminary prototype.

## Organizer Contract

The organizer material defines exactly five public categories:

- `BL_COMPARISON`
- `SI_REQUEST`
- `INVOICE_QUERY`
- `GENERAL`
- `SPAM`

Only `BL_COMPARISON` proceeds to document verification. Verification output uses `OK`, `MISMATCH`, or `NEEDS_REVIEW`. A `NEEDS_REVIEW` result uses one of `wrong_doc_type`, `missing_attachment`, `unreadable`, or `missing_value`. A `MISMATCH` reports `has_defect: true` and the canonical names of all differing fields in `defect_fields`.

The seven canonical fields are `shipper`, `consignee`, `notify_party`, `port_of_loading`, `port_of_discharge`, `container_count`, and `gross_weight_kg`. The SI is the reference document.

The richer frontend view is an internal diagnostic representation. It will preserve raw values, normalized values, evidence, and review details without adding those fields to an organizer-format submission record.

## Architecture

Streamlit is the presentation layer. A small frontend service module is the only new integration boundary. It will:

- validate email text and upload metadata;
- load the committed classification model and review threshold;
- build the existing classifier features and call the existing routing logic;
- map internal category names to the organizer's five display names;
- identify SI and BL attachments from filenames;
- call `document_extraction.extract_from_bytes` directly so the UI retains `FieldExtraction` evidence;
- call `verification.compare_documents` to obtain normalized values, per-field statuses, reasons, and the overall result;
- produce a separate organizer-format summary with only the required five properties.

The service will accept in-memory attachment objects so uploaded files do not need to be persisted. The existing batch pipeline and handoff contracts remain unchanged.

## Classification Experience

The input panel will show editable subject and body fields and two explicit upload controls labelled Shipping Instruction and Draft Bill of Lading. Supported formats are TXT, PDF, DOCX, and XLSX.

On analysis, the application displays:

- the predicted public category;
- all five model scores in a compact chart or table;
- whether the email proceeds to document verification;
- the routing status and plain-language reason;
- any rule evidence used by the existing router.

For the manual form, the upload filenames are included in the classifier record. The two upload controls establish the SI/BL roles even if their names are unconventional; attachment-presence rules use generated role-aware names internally while the original filename remains visible as evidence.

If the result is not `BL_COMPARISON`, the UI ends the workflow with a clear message that document comparison is not applicable. It does not fabricate verification output.

## Document Verification Experience

When the classification route is ready for comparison and both files are present, the service extracts both documents and compares all seven fields. The main result area displays:

- overall status: Match, Mismatch detected, or Pending human review;
- review reason when applicable;
- count of matching, mismatching, and unresolved fields;
- a seven-row table containing the SI value, BL value, normalized SI, normalized BL, field status, and reason.

Each row has traceable evidence available in an expanded detail view. Evidence includes the document role, original filename, raw label, raw value, extractor evidence location, and whether OCR or the existing optional LLM fallback was used. The application will default to deterministic extraction with the optional Ollama fallback disabled so the public deployment is reproducible and does not claim an unavailable cloud or local model.

Wrong-document markers, parsing failures, missing uploads, missing field values, garbled extraction, and unavailable OCR route to human review. Reliable field differences remain visible as mismatches even if another field requires review.

## AI and JEV Disclosure

The application will state that the current classification layer uses the repository's trained TF-IDF text features with its selected scikit-learn classifier plus deterministic routing rules. Document parsing and comparison are deterministic in the public demo configuration.

JEV will appear only in a Future enhancement note: it could act as a fallback or second opinion for unfamiliar or low-confidence emails. The interface and README will explicitly say that JEV is not used by the current prototype.

## Error Handling

The UI must keep the user's inputs visible after an error and show a concise actionable message. Expected failures are converted into result states rather than uncaught tracebacks:

- no SI or BL upload for a comparison email becomes `NEEDS_REVIEW / missing_attachment`;
- an unsupported or failed parser becomes `NEEDS_REVIEW / unreadable`;
- a detected non-SI/BL document becomes `NEEDS_REVIEW / wrong_doc_type`;
- any absent canonical value becomes `NEEDS_REVIEW / missing_value`;
- a missing or incompatible model artifact becomes a visible application configuration error.

Uploaded content and extracted document text are treated as data, never as application instructions.

## Testing

Tests will exercise the integration service rather than Streamlit internals. They will cover:

- all five internal-to-public category mappings;
- a non-comparison email stopping after classification;
- a complete TXT SI/BL pair producing seven per-field results and evidence;
- normalized equality such as formatted weight values;
- a genuine mismatch appearing in both the detailed view and organizer summary;
- missing attachments, unreadable content, wrong document type, and missing values producing the required organizer review reasons;
- the bundled `email_001` path running against the committed model and real attachments.

The full existing test suite must remain green. A Streamlit headless startup smoke test will verify that the application imports and starts without an immediate exception.

## Deployment and Documentation

The repository will include Streamlit in its runtime requirements, a root application entry point compatible with Streamlit Community Cloud, and configuration that avoids local-only assumptions. The README will provide macOS/Linux and Windows setup commands, the local launch command, Community Cloud deployment steps, supported upload formats, architecture summary, and known limitations.

The README will also provide a concise live-demo sequence: load the bundled example, run classification, open document verification, inspect the seven-field table, expand evidence, and point out the JEV future-enhancement disclosure.

Deployment configuration makes the project deployable but does not create or claim a public URL. Publishing requires the repository owner to connect the GitHub repository to a hosting account.

## Preliminary Submission Boundary

This work supplies the frontend prototype, a real end-to-end demo path, repository setup instructions, and a deployment recipe. The team still owns the final public deployment action, a maximum five-minute demo video, the final project-description link, the slide deck or documentation link, and any submission-form entry required by the organizers.
