# Shipping Document Verification Frontend Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a Streamlit frontend that runs the repository's real five-class email classifier and SI-to-draft-BL verification flow with traceable evidence.

**Architecture:** Add a framework-independent `frontend.service` integration module that converts UI inputs into existing classifier, extractor, and comparator calls. Keep Streamlit limited to rendering and session state so all decision logic can be tested without a browser.

**Tech Stack:** Python 3.12, Streamlit, scikit-learn, existing document extraction modules, pytest

**Spec:** `docs/superpowers/specs/2026-09-21-frontend-demo-design.md`

## Global Constraints

- Use the existing committed model, extraction functions, normalization rules, and comparison logic.
- Public category names are exactly `BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`, `GENERAL`, and `SPAM`.
- Organizer statuses are exactly `OK`, `MISMATCH`, and `NEEDS_REVIEW`.
- Review reasons are limited to `wrong_doc_type`, `missing_attachment`, `unreadable`, and `missing_value`.
- Compare exactly the seven canonical fields defined in `contracts.DOCUMENT_FIELDS`.
- Keep JEV labelled as a future enhancement and never claim it runs in the prototype.
- Do not persist uploaded document content.
- Disable the optional Ollama fallback in the public demo path.

## Review Focus

- An uploaded comparison email with only one document must return `NEEDS_REVIEW / missing_attachment`, not crash or silently stop.
- A valid email in any non-comparison category must stop before extraction and retain an organizer-compatible `OK` summary.
- A pair with reliable mismatches and a separate missing field must keep the mismatch visible while the overall status is `NEEDS_REVIEW`.
- Unconventional uploaded filenames must still use the explicit SI and BL upload roles for routing and extraction.
- A missing or incompatible model artifact must produce a configuration error that Streamlit can display without exposing a traceback.

---

### Task 1: Framework-independent demo service

**Files:**
- Create: `src/frontend/__init__.py`
- Create: `src/frontend/service.py`
- Create: `tests/test_frontend_service.py`

**Interfaces:**
- Consumes: `build_email_text(record)`, `score_mapping(model, texts)`, `route_prediction(...)`, `extract_from_bytes(...)`, `compare_documents(si, bl)`, and `DOCUMENT_FIELDS`.
- Produces: `UploadedDocument`, `DemoResult`, `load_demo_runtime(project_root)`, and `analyze_email(runtime, subject, body, si_document, bl_document, email_id="demo_email")`.

- [ ] **Step 1: Write failing category and non-comparison tests**

```python
def test_maps_all_internal_categories_to_official_names():
    assert PUBLIC_CATEGORIES == {
        "bl_comparison": "BL_COMPARISON",
        "new_si_request": "SI_REQUEST",
        "invoice_query": "INVOICE_QUERY",
        "general_message": "GENERAL",
        "spam": "SPAM",
    }


def test_non_comparison_result_stops_before_document_extraction(fake_runtime):
    result = analyze_email(fake_runtime(category="spam"), "Prize", "Claim now", None, None)
    assert result.category == "SPAM"
    assert result.comparison is None
    assert result.submission == {
        "category": "SPAM", "status": "OK", "review_reason": None,
        "defect_fields": [], "has_defect": False,
    }
```

- [ ] **Step 2: Run the tests and verify they fail because `frontend.service` does not exist**

Run: `.venv/bin/python -m pytest tests/test_frontend_service.py -q`

Expected: collection fails with `ModuleNotFoundError: No module named 'frontend'`.

- [ ] **Step 3: Implement model loading, category mapping, and classification results**

Implement immutable result dataclasses, load `artifacts/classification/selected_model.joblib` plus `review_margin_threshold` from `run_summary.json`, build the existing feature text, calculate five scores, and call the existing router. Wrap missing or incompatible artifacts in `DemoConfigurationError`.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `.venv/bin/python -m pytest tests/test_frontend_service.py -q`

Expected: category mapping and non-comparison tests pass.

- [ ] **Step 5: Write failing document-result tests**

```python
def test_complete_pair_returns_seven_traceable_field_rows(comparison_runtime, txt_pair):
    result = analyze_email(comparison_runtime, "Please verify SI and BL", "Attached", *txt_pair)
    assert len(result.comparison.fields) == 7
    assert result.comparison.fields[0].si_evidence.raw_value is not None
    assert result.submission["status"] in {"OK", "MISMATCH", "NEEDS_REVIEW"}


def test_missing_bl_uses_official_review_reason(comparison_runtime, txt_pair):
    result = analyze_email(comparison_runtime, "Please verify SI and BL", "Attached", txt_pair[0], None)
    assert result.submission["status"] == "NEEDS_REVIEW"
    assert result.submission["review_reason"] == "missing_attachment"
```

- [ ] **Step 6: Run the new tests and verify the missing comparison behavior fails**

Run: `.venv/bin/python -m pytest tests/test_frontend_service.py -q`

Expected: failures show comparison/evidence results are not implemented.

- [ ] **Step 7: Implement extraction, detailed comparison, evidence, and organizer summary mapping**

Use explicit upload roles to build classifier attachment names, call `extract_from_bytes(..., use_llm_fallback=False)` for each document, retain `DocumentExtraction` and `FieldExtraction` details, and call `compare_documents`. Map extraction conditions in priority order: missing attachment, wrong document type, unreadable, then missing value. Preserve any reliable mismatch rows when the overall status requires review.

- [ ] **Step 8: Add and pass edge-case tests**

Add literal fixtures for normalized formatted weights, container mismatch, wrong document type, unreadable bytes, missing values, unconventional filenames, and a mismatch plus missing value. Run:

`.venv/bin/python -m pytest tests/test_frontend_service.py -q`

Expected: all frontend service tests pass.

- [ ] **Step 9: Commit the service task**

```bash
git add src/frontend tests/test_frontend_service.py
git commit -m "feat: add frontend demo service"
```

### Task 2: Streamlit interface and built-in demonstration

**Files:**
- Create: `streamlit_app.py`
- Create: `.streamlit/config.toml`
- Modify: `requirements.txt`
- Create: `tests/test_streamlit_app.py`

**Interfaces:**
- Consumes: `load_demo_runtime`, `analyze_email`, and the `DemoResult` dataclasses from Task 1.
- Produces: root Streamlit entry point with bundled-example and manual-input modes.

- [ ] **Step 1: Write a failing Streamlit AppTest for the initial screen**

```python
def test_app_shows_input_modes_and_jev_disclosure():
    app = AppTest.from_file("streamlit_app.py").run()
    assert not app.exception
    assert any("Bundled example" in item.value for item in app.radio)
    assert any("JEV is not used" in item.value for item in app.caption)
```

- [ ] **Step 2: Install the declared Streamlit dependency and verify the UI test fails for the missing app**

Run: `.venv/bin/python -m pip install -r requirements-dev.txt`

Run: `.venv/bin/python -m pytest tests/test_streamlit_app.py -q`

Expected: failure because `streamlit_app.py` does not exist.

- [ ] **Step 3: Implement the page shell and input panel**

Create a wide-layout application with a concise project header, pipeline progress indicator, bundled/manual mode control, subject/body inputs, explicit SI and draft BL upload controls, supported-format help, Analyze button, and current-AI/JEV disclosure. The bundled mode reads `download2/inbox/email_001.json` and its referenced attachments.

- [ ] **Step 4: Run the initial UI test and verify it passes**

Run: `.venv/bin/python -m pytest tests/test_streamlit_app.py -q`

Expected: initial screen loads without an exception and contains the two disclosures.

- [ ] **Step 5: Write failing UI tests for results**

```python
def test_bundled_example_renders_classification_and_seven_fields():
    app = AppTest.from_file("streamlit_app.py").run()
    app.button(key="analyze").click().run(timeout=30)
    assert any("BL Comparison" in item.value for item in app.metric)
    assert len(app.dataframe) >= 1
    assert app.dataframe[0].value.shape[0] == 7
```

- [ ] **Step 6: Run the result test and verify it fails because results are not rendered**

Run: `.venv/bin/python -m pytest tests/test_streamlit_app.py -q`

Expected: the seven-field dataframe assertion fails.

- [ ] **Step 7: Implement result rendering**

Render classification status, five scores, routing reason, overall verification status, match/mismatch/review counts, the seven-field comparison table, per-field evidence expanders, organizer-format JSON, error messages, and the explicit JEV future-enhancement note. Use accessible text labels in addition to color.

- [ ] **Step 8: Add Streamlit configuration and pass UI tests**

Configure headless-safe defaults and a conservative upload-size limit. Run:

`.venv/bin/python -m pytest tests/test_streamlit_app.py -q`

Expected: all UI tests pass.

- [ ] **Step 9: Commit the UI task**

```bash
git add streamlit_app.py .streamlit/config.toml requirements.txt tests/test_streamlit_app.py
git commit -m "feat: add Streamlit verification demo"
```

### Task 3: Documentation, deployment readiness, and final verification

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture.md`

**Interfaces:**
- Consumes: the completed Streamlit entry point and existing repository setup.
- Produces: local run instructions, Streamlit Community Cloud deployment steps, demo script, limitations, and preliminary-submission checklist.

- [ ] **Step 1: Update user and deployment documentation**

Document Python 3.12 environment creation for Windows and macOS/Linux, dependency installation, `.venv/bin/streamlit run streamlit_app.py` and Windows equivalent, supported files, bundled example, architecture, Community Cloud setup, secrets-free deployment, JEV status, OCR/Ollama limitations, and the organizer output schema.

- [ ] **Step 2: Add the five-minute demonstration sequence**

Record the exact clicks: select Bundled example, inspect subject/body and filenames, click Analyze, explain BL Comparison routing, inspect the seven canonical fields, expand one evidence item, show normalized equality/status, open organizer JSON, and finish on the JEV future-enhancement note.

- [ ] **Step 3: Add the preliminary-submission checklist**

Separate completed repository deliverables from team actions still required: deploy public URL, record maximum five-minute video, publish project description, provide slide deck/documentation link, and submit before the deadline.

- [ ] **Step 4: Run the full automated suite**

Run: `.venv/bin/python -m pytest -q`

Expected: all existing and new tests pass with zero failures.

- [ ] **Step 5: Run a headless application startup smoke test**

Run: `.venv/bin/streamlit run streamlit_app.py --server.headless true --server.port 8765`

Expected: Streamlit reports a local URL and no import/configuration exception; terminate after startup is confirmed.

- [ ] **Step 6: Run the real bundled end-to-end path and inspect output**

Use Streamlit AppTest or the service API with `email_001`; verify `BL_COMPARISON`, seven field rows, traceable evidence, and an organizer-format result containing exactly `category`, `status`, `review_reason`, `defect_fields`, and `has_defect`.

- [ ] **Step 7: Inspect repository changes and commit documentation**

Run: `git diff --check && git status --short`

```bash
git add README.md docs/architecture.md
git commit -m "docs: explain frontend demo and deployment"
```
