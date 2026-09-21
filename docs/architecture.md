# Module Architecture

Three workstreams built in parallel on separate branches. They must not import
each other. The only shared dependency is `src/contracts/`.

```
                    +---------------------+
                    |    src/contracts    |   schemas, handoff files, ports
                    +---------------------+   (depends on nothing)
                       ^      ^      ^
        +--------------+      |      +--------------+
        |                     |                     |
+-------+---------+  +--------+----------+  +-------+--------+
| email_          |  | document_         |  | verification   |
| classification  |  | extraction        |  |                |
+-----------------+  +-------------------+  +----------------+

                    +---------------------+
                    |    src/pipeline     |   wires the ports together
                    +---------------------+   (depends on contracts only)

                    +---------------------+
                    |    src/frontend     |   interactive demo adapter
                    +---------------------+   calls public module APIs
                              ^
                              |
                    +---------------------+
                    | streamlit_app.py    |   presentation only
                    +---------------------+
```

## The rule

`tests/test_module_boundaries.py` enforces this by parsing every import in
`src/`. A module may import `contracts` and its own submodules. Nothing else.
If you add a package under `src/`, declare its allowed dependencies in that
test or the suite fails.

This is why `src/pipeline/orchestrator.py` receives an extractor and a verifier
as arguments instead of importing them: the orchestrator knows the ports, never
the implementations.

The interactive demo is intentionally a presentation adapter rather than a
fourth batch-processing stage. `src/frontend/service.py` accepts in-memory
email and attachment inputs, calls the existing classifier, extractor, and
comparator APIs, and returns immutable view records. `streamlit_app.py` renders
those records and contains no classification or comparison policy. This keeps
the existing handoff files and batch pipeline stable while allowing the UI to
retain raw extraction evidence that the flat stage contracts omit.

The public demo disables the optional Ollama fallback and does not use JEV.
JEV remains a future classification enhancement that can implement the same
category contract without changing document extraction or verification.

## Each module keeps its own shape

A module's internal representation is richer than what crosses the boundary,
and that is deliberate. Each module owns exactly one adapter that translates:

| Module | Internal | Adapter | Published |
| --- | --- | --- | --- |
| email_classification | `RoutingDecision`, internal categories (`bl_comparison`) | `contract_adapter.py` | `ClassificationResult`, published categories (`document_comparison`) |
| document_extraction | `DocumentExtraction` with evidence, OCR and garbled flags | `adapter.py` | `ExtractionResult` — the 7 plain field values |
| verification | `compare_documents` dict with `field_results`, normalized values | `adapter.py` | `VerificationResult`, status `match` / `mismatch_detected` / `not_verified` |

Callers that want the richer detail (a human-review UI, debugging) use the
module directly. Everything crossing a module boundary goes through the
contract. Changing an internal vocabulary only touches that module's adapter.

## Stage handoff

Stages communicate through JSON files, not function calls. A stage can be run,
re-run, or replaced without the others being present.

| Stage | Writes | Reads |
| --- | --- | --- |
| classification | `outputs/handoff/classification.json` | the inbox bundle |
| extraction | `outputs/handoff/extraction.json` | classification handoff |
| verification | `outputs/handoff/verification.json` | extraction handoff |

Every handoff file carries `schema_version` and `stage`, and `read_handoff`
rejects a file whose version or stage does not match what the caller expects.
Attachment paths in the classification handoff are relative to the inbox bundle
root (`download2/`), so they stay valid across machines.

## Failure handling

An extractor or verifier that cannot process a pair raises
`ExtractionUnavailable` / `VerificationUnavailable` rather than returning a
partial result. The orchestrator turns either into a `not_verified` result with
`review_required` and the reason, so one bad attachment never stops the run.

`document_extraction` imports pdfplumber, python-docx and openpyxl inside its
format extractors. `adapter.py` loads them late, so a missing optional parser
also degrades to a review item instead of breaking every import of the package.

## Category names

`email_classification` uses internal category names (`bl_comparison`, ...).
`contracts` uses the published names (`document_comparison`, ...).
`email_classification/contract_adapter.py` is the only place that translates.
