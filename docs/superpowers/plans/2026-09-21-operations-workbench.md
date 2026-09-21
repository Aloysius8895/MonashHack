# Shipping Operations Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing Streamlit demo into an in-memory shipping operations workbench with batch input, visible pipeline routing, human review, reports, and a session dashboard.

**Architecture:** Keep the trained classifier, extractors, normalization, and comparator unchanged. Extend the frontend adapter with structured workbench results, isolate parsing/review/report aggregation in focused modules, and keep `streamlit_app.py` as a rendering layer backed by `st.session_state`.

**Tech Stack:** Python 3.12, Streamlit 1.64, pandas, scikit-learn/joblib, pytest, and Streamlit AppTest.

**Spec:** `docs/superpowers/specs/2026-09-21-operations-workbench-design.md`

## Global Constraints

- Reuse the existing classifier, extractors, normalization, comparator, model artifact, and public category mapping.
- Do not write uploaded inbox data or attachments to disk.
- Main screens use plain operational English; model names, scores, thresholds, rule names, and JEV stay under collapsed Technical details.
- The app has wide layout, no sidebar, and exactly four tabs: Input & Run, Human Review (n), Report, Dashboard.
- `submission.json` preserves the automated decision before human edits and contains exactly `category`, `status`, `review_reason`, `defect_fields`, and `has_defect` per email.
- JEV is explicitly a future enhancement and is not used by this prototype.
- Keep Streamlit Community Cloud compatibility, pinned requirements, and no required secrets.
- Do not commit, push, or update PR #1 until the user explicitly confirms the finished local prototype.

## Review Focus

- A JSON file containing a valid list beside an invalid record processes the valid record and reports the invalid one without crashing; pinned in Task 1.
- Two uploaded attachments with the same basename are rejected as ambiguous rather than silently choosing one; pinned in Task 1.
- A high-confidence mismatch stays a final result and is not incorrectly routed to human review; pinned in Task 2.
- Resolving a human-review case changes the report/dashboard but leaves the automated submission payload byte-for-byte equivalent; pinned in Task 4.
- Running all demo scenarios twice replaces records by stable demo email ID instead of doubling dashboard counts; pinned in Task 5.

---

### Task 1: Inbox Parsing and In-Memory Attachment Matching

**Files:**
- Create: `src/frontend/inbox.py`
- Create: `tests/test_frontend_inbox.py`

**Interfaces:**
- Consumes: `UploadedDocument(name: str, data: bytes)` from `src/frontend/service.py`.
- Produces: `InboxRecord`, `ParseIssue`, `ResolvedDocuments`, `parse_inbox_uploads(files)`, `index_attachments(files)`, and `resolve_record_documents(record, index)`.

- [ ] **Step 1: Write failing parsing tests**

```python
def test_parses_one_object_and_a_list_without_dropping_valid_records():
    files = [
        UploadedDocument("one.json", json.dumps(valid_record("a")).encode()),
        UploadedDocument("many.json", json.dumps([valid_record("b"), {"bad": True}]).encode()),
    ]
    records, issues = parse_inbox_uploads(files)
    assert [record.email_id for record in records] == ["a", "b"]
    assert len(issues) == 1
    assert "many.json record 2" in issues[0].location

def test_rejects_duplicate_email_ids_across_files():
    records, issues = parse_inbox_uploads([
        json_upload("one.json", valid_record("same")),
        json_upload("two.json", valid_record("same")),
    ])
    assert [record.email_id for record in records] == ["same"]
    assert "Duplicate email ID" in issues[0].message
```

- [ ] **Step 2: Run the parsing tests and confirm the missing-module failure**

Run: `.venv/bin/python -m pytest tests/test_frontend_inbox.py -q`  
Expected: FAIL because `frontend.inbox` does not exist.

- [ ] **Step 3: Implement validated parsing types and functions**

```python
@dataclass(frozen=True)
class InboxRecord:
    email_id: str
    sender: str
    subject: str
    body: str
    attachments: tuple[str, ...]

@dataclass(frozen=True)
class ParseIssue:
    location: str
    message: str

@dataclass(frozen=True)
class ResolvedDocuments:
    si_document: UploadedDocument | None
    bl_document: UploadedDocument | None
    missing_names: tuple[str, ...]

def parse_inbox_uploads(
    files: Sequence[UploadedDocument],
) -> tuple[tuple[InboxRecord, ...], tuple[ParseIssue, ...]]:
    records: list[InboxRecord] = []
    issues: list[ParseIssue] = []
    seen: set[str] = set()
    for upload in files:
        try:
            payload = json.loads(upload.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            issues.append(ParseIssue(upload.name, f"Invalid JSON: {error}"))
            continue
        values = payload if isinstance(payload, list) else [payload]
        for index, value in enumerate(values, start=1):
            location = f"{upload.name} record {index}"
            record, issue = _validate_record(value, location)
            if issue is not None:
                issues.append(issue)
            elif record.email_id in seen:
                issues.append(ParseIssue(location, f"Duplicate email ID: {record.email_id}"))
            else:
                seen.add(record.email_id)
                records.append(record)
    return tuple(records), tuple(issues)
```

Validate all five required keys and preserve valid records when siblings are invalid. Treat malformed JSON and non-object/non-list roots as file-scoped issues.

- [ ] **Step 4: Write failing basename-matching tests**

```python
def test_matches_json_attachment_paths_by_basename():
    index, issues = index_attachments([text_upload("email_001_SI.txt"), text_upload("email_001_BL.txt")])
    pair = resolve_record_documents(record_with_paths(), index)
    assert pair.si_document.name == "email_001_SI.txt"
    assert pair.bl_document.name == "email_001_BL.txt"
    assert pair.missing_names == ()
    assert issues == ()

def test_duplicate_uploaded_basenames_are_ambiguous():
    index, issues = index_attachments([text_upload("same.txt"), text_upload("same.txt")])
    assert "same.txt" not in index
    assert issues[0].message == "Duplicate attachment basename: same.txt"
```

- [ ] **Step 5: Implement basename indexing and SI/BL resolution**

Use `PurePosixPath(path.replace("\\", "/")).name` for JSON paths and the existing `resolve_attachment_pair()` to identify document roles. Return missing listed names explicitly.

- [ ] **Step 6: Run Task 1 tests**

Run: `.venv/bin/python -m pytest tests/test_frontend_inbox.py -q`  
Expected: PASS. Leave changes uncommitted.

---

### Task 2: Pipeline Trace and Operational Confidence

**Files:**
- Modify: `src/frontend/service.py`
- Modify: `tests/test_frontend_service.py`

**Interfaces:**
- Consumes: existing `analyze_email()`, `DemoResult`, extraction evidence, model score map, and trained `review_margin_threshold`.
- Produces: `PipelineStep`, `ConfidenceView`, new `DemoResult.pipeline_steps`, `DemoResult.confidence`, and `classifier_margin(scores)`.

- [ ] **Step 1: Write failing trace tests for every branch**

```python
def test_classify_only_trace_skips_document_stages():
    result = analyze_email(fake_runtime("invoice_query"), "Invoice query", "Please explain charge", None, None)
    assert step(result, "Classify only").state == "complete"
    assert step(result, "Extraction").state == "skipped"
    assert step(result, "Report").state == "complete"

def test_missing_attachment_trace_routes_to_review():
    result = analyze_email(fake_runtime("bl_comparison"), comparison_subject(), "Attached", text_document("SI.txt"), None)
    assert step(result, "Attachment check").state == "attention"
    assert step(result, "Human review").state == "complete"

def test_complete_pair_executes_extraction_normalization_comparison_and_confidence():
    result = complete_pair_result()
    assert [step.state for step in result.pipeline_steps if step.name in DOCUMENT_STAGES] == ["complete"] * 4
```

- [ ] **Step 2: Run the trace tests and confirm attribute failures**

Run: `.venv/bin/python -m pytest tests/test_frontend_service.py -q`  
Expected: FAIL because `pipeline_steps` and `confidence` do not exist.

- [ ] **Step 3: Add trace and confidence dataclasses**

```python
@dataclass(frozen=True)
class PipelineStep:
    name: str
    state: Literal["complete", "attention", "skipped"]
    summary: str

@dataclass(frozen=True)
class ConfidenceView:
    percent: int
    level: Literal["High", "Low"]
    reasons: tuple[str, ...]
```

Build every named flow step for every result, including Report and Dashboard. Use plain-English summaries and preserve skipped stages.

- [ ] **Step 4: Write failing confidence tests**

```python
def test_high_confidence_mismatch_remains_final_result():
    result = mismatch_result()
    assert result.confidence.level == "High"
    assert result.comparison.status == "MISMATCH"
    assert step(result, "Final result").state == "complete"

def test_missing_or_unreadable_field_forces_low_confidence_with_reason():
    result = unreadable_result()
    assert result.confidence.level == "Low"
    assert result.confidence.percent < 80
    assert any("could not be read" in reason for reason in result.confidence.reasons)
```

- [ ] **Step 5: Implement deterministic operational confidence**

Compute classification quality from the top-two score margin relative to the trained review threshold, then combine it with extraction completeness and certainty flags. Cap any incomplete, unreadable, wrong-document, garbled, OCR/LLM-fallback, or below-trained-threshold result below 80. A fully extracted definite comparison is at least 80 even when mismatched. Return reasons describing every cap or deduction.

- [ ] **Step 6: Run Task 2 and existing service tests**

Run: `.venv/bin/python -m pytest tests/test_frontend_service.py -q`  
Expected: PASS. Leave changes uncommitted.

---

### Task 3: Batch Processing and Real Demo Scenarios

**Files:**
- Create: `src/frontend/workbench.py`
- Create: `tests/test_frontend_workbench.py`

**Interfaces:**
- Consumes: `InboxRecord`, resolved documents, `DemoRuntime`, and `analyze_email()`.
- Produces: `DemoScenario`, `ProcessIssue`, `ProcessedEmail`, `build_demo_scenarios(project_root: Path) -> tuple[DemoScenario, ...]`, `process_record(runtime: DemoRuntime, record: InboxRecord, documents: ResolvedDocuments) -> ProcessedEmail`, and `process_batch(runtime: DemoRuntime, records: Sequence[InboxRecord], attachment_index: Mapping[str, UploadedDocument]) -> tuple[tuple[ProcessedEmail, ...], tuple[ProcessIssue, ...]]`.

- [ ] **Step 1: Write failing demo-construction tests**

```python
def test_five_demo_scenarios_use_real_pipeline_inputs(tmp_project):
    scenarios = build_demo_scenarios(PROJECT_ROOT)
    assert [item.name for item in scenarios] == [
        "All fields match", "Mismatch detected", "Missing BL attachment",
        "Needs human review", "Classification only",
    ]
    assert all(item.record.email_id.startswith("demo_") for item in scenarios)

def test_demo_outputs_are_calculated_not_injected():
    results = [process_scenario(runtime, item) for item in build_demo_scenarios(PROJECT_ROOT)]
    assert [item.automated.submission["status"] for item in results] == [
        "OK", "MISMATCH", "NEEDS_REVIEW", "NEEDS_REVIEW", "OK",
    ]
```

- [ ] **Step 2: Run demo tests and confirm missing-function failures**

Run: `.venv/bin/python -m pytest tests/test_frontend_workbench.py -q`  
Expected: FAIL because `frontend.workbench` does not exist.

- [ ] **Step 3: Implement stable scenarios from real bundle data**

Load `email_001` and real attachments for the first four scenarios. For mismatch, replace the draft-BL consignee and container-count source text in memory before calling the extractor. For low confidence, pass unreadable bytes. Use real `email_002` for classification only. Give scenarios stable IDs `demo_match`, `demo_mismatch`, `demo_missing_bl`, `demo_human_review`, and `demo_classify_only`.

- [ ] **Step 4: Write failing batch-isolation test**

```python
def test_batch_keeps_successful_records_when_one_record_fails():
    processed, issues = process_batch(runtime, [valid_record, invalid_runtime_record], attachments)
    assert [item.email_id for item in processed] == [valid_record.email_id]
    assert issues[0].email_id == invalid_runtime_record.email_id
```

- [ ] **Step 5: Implement `ProcessedEmail` and batch isolation**

```python
@dataclass(frozen=True)
class ProcessedEmail:
    email_id: str
    source: InboxRecord
    automated: DemoResult
    final_status: str
    final_defect_fields: tuple[str, ...]
    reviewed_by_human: bool = False
    review_notes: tuple[str, ...] = ()

@dataclass(frozen=True)
class DemoScenario:
    name: str
    record: InboxRecord
    documents: ResolvedDocuments

@dataclass(frozen=True)
class ProcessIssue:
    email_id: str
    message: str
```

Catch record-scoped validation/extraction errors, return issues beside successful results, and never persist bytes.

- [ ] **Step 6: Run Task 3 tests**

Run: `.venv/bin/python -m pytest tests/test_frontend_workbench.py -q`  
Expected: PASS. Leave changes uncommitted.

---

### Task 4: Human Review State Transitions

**Files:**
- Create: `src/frontend/review.py`
- Create: `tests/test_frontend_review.py`

**Interfaces:**
- Consumes: `ProcessedEmail` and immutable `DemoResult.submission`.
- Produces: `FieldDecision`, `apply_review(processed, outcome, decisions)`, `pending_reviews(records)`, and `replace_after_rerun(records, rerun)`.

- [ ] **Step 1: Write failing decision tests**

```python
def test_human_approval_removes_case_from_queue_and_preserves_submission():
    original = review_case()
    automated_json = json.dumps(original.automated.submission, sort_keys=True)
    resolved = apply_review(original, "approve", ())
    assert resolved.final_status == "OK"
    assert resolved.reviewed_by_human is True
    assert pending_reviews([resolved]) == ()
    assert json.dumps(resolved.automated.submission, sort_keys=True) == automated_json

def test_confirm_mismatch_records_field_decisions():
    resolved = apply_review(review_case(), "mismatch", [FieldDecision("consignee", "si", None)])
    assert resolved.final_status == "MISMATCH"
    assert resolved.final_defect_fields == ("consignee",)
```

- [ ] **Step 2: Run decision tests and confirm missing-module failure**

Run: `.venv/bin/python -m pytest tests/test_frontend_review.py -q`  
Expected: FAIL because `frontend.review` does not exist.

- [ ] **Step 3: Implement immutable review transitions**

Validate `outcome` as `approve` or `mismatch`; validate field names against the seven canonical fields; require an entered value when choice is `entered`; use `dataclasses.replace()` to create the reviewed record without mutating `automated`.

- [ ] **Step 4: Write failing re-run replacement test**

```python
def test_rerun_replaces_same_email_and_can_clear_pending_state():
    records = (missing_attachment_case(),)
    rerun = complete_pair_case(email_id=records[0].email_id)
    updated = replace_after_rerun(records, rerun)
    assert len(updated) == 1
    assert updated[0].final_status == "OK"
```

- [ ] **Step 5: Implement stable-ID re-run replacement and pending selection**

Replace records by `email_id`, preserve insertion order, and define pending as automated/final `NEEDS_REVIEW` with `reviewed_by_human == False`.

- [ ] **Step 6: Run Task 4 tests**

Run: `.venv/bin/python -m pytest tests/test_frontend_review.py -q`  
Expected: PASS. Leave changes uncommitted.

---

### Task 5: Report, Downloads, and Dashboard Aggregation

**Files:**
- Create: `src/frontend/reporting.py`
- Create: `tests/test_frontend_reporting.py`

**Interfaces:**
- Consumes: sequence of `ProcessedEmail` values.
- Produces: `ReportView`, `report_view(record)`, `report_csv(records)`, `submission_json(records)`, `dashboard_summary(records)`, and `needs_action_rows(records, status_filter)`.

- [ ] **Step 1: Write failing report wording and export tests**

```python
def test_mismatch_report_names_field_values_and_concrete_action():
    view = report_view(mismatch_case())
    assert view.badge == "ACTION REQUIRED – 2 mismatches"
    assert "Ask the carrier to correct" in view.next_step
    assert "SI:" in view.next_step and "BL:" in view.next_step

def test_submission_json_has_exact_automated_schema_after_human_review():
    payload = json.loads(submission_json([human_resolved_case()]))
    assert set(payload["demo_review"]) == {
        "category", "status", "review_reason", "defect_fields", "has_defect"
    }
    assert payload["demo_review"]["status"] == "NEEDS_REVIEW"
```

- [ ] **Step 2: Run report tests and confirm missing-module failure**

Run: `.venv/bin/python -m pytest tests/test_frontend_reporting.py -q`  
Expected: FAIL because `frontend.reporting` does not exist.

- [ ] **Step 3: Implement badges, next steps, CSV, and JSON**

Generate the four exact badge families from final state. Create one CSV row per email/field with email ID, category, final status, field, SI value, BL value, field result, next step, and reviewed flag. Build submission JSON exclusively from each immutable automated payload.

- [ ] **Step 4: Write failing dashboard aggregation tests**

```python
def test_dashboard_counts_and_mismatch_frequency():
    summary = dashboard_summary(all_outcome_cases())
    assert summary.emails_processed == 5
    assert summary.comparison_requests == 4
    assert summary.waiting_for_human_review == 2
    assert summary.mismatched_fields["container_count"] == 1

def test_repeated_demo_batch_replaces_ids_instead_of_double_counting():
    session = upsert_records(first_run(), second_run_same_ids())
    assert dashboard_summary(session).emails_processed == 5
```

- [ ] **Step 5: Implement aggregation, urgency sorting, and stable upsert**

Provide category counts, outcome counts, mismatched-field counts, all six KPIs, and Needs action rows ordered Human Review, Mismatch, then remaining actionable statuses. Apply the optional status filter after sorting.

- [ ] **Step 6: Run Task 5 tests**

Run: `.venv/bin/python -m pytest tests/test_frontend_reporting.py -q`  
Expected: PASS. Leave changes uncommitted.

---

### Task 6: Four-Tab Streamlit Workbench

**Files:**
- Modify: `streamlit_app.py`
- Modify: `tests/test_streamlit_app.py`

**Interfaces:**
- Consumes: all public interfaces from Tasks 1–5.
- Produces: session keys `processed_emails`, `processing_issues`, `latest_email_id`, and `confidence_threshold`; renders the specified four-tab UI.

- [ ] **Step 1: Replace current AppTest expectations with failing four-tab tests**

```python
def test_app_has_four_workbench_tabs_and_no_sidebar_controls():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    assert [tab.label for tab in app.tabs] == [
        "Input & Run", "Human Review (0)", "Report", "Dashboard"
    ]
    assert app.selectbox(key="demo_scenario").options[:2] == ["All fields match", "Mismatch detected"]
    assert app.button(key="run_all_demos").label == "Run all demo scenarios"

def test_run_all_populates_report_dashboard_and_review_count():
    app = AppTest.from_file(str(APP_PATH), default_timeout=30).run()
    app.button(key="run_all_demos").click().run()
    assert any(tab.label == "Human Review (2)" for tab in app.tabs)
    assert metric(app, "Emails processed") == "5"
    assert any("ACTION REQUIRED" in item.value for item in app.markdown)
```

- [ ] **Step 2: Run AppTest and confirm layout failures**

Run: `.venv/bin/python -m pytest tests/test_streamlit_app.py -q`  
Expected: FAIL because the current app is a single-page scenario result.

- [ ] **Step 3: Implement session setup and Input & Run tab**

Initialize state with `setdefault`. Add multi-file JSON and attachment uploaders, selected-demo and run-all buttons, and collapsed manual entry. On run, upsert results and set `latest_email_id`. Render the compact route strip and all pipeline stages, including grey skipped steps. Do not render a separate workflow diagram.

- [ ] **Step 4: Add failing Human Review interaction AppTest**

```python
def test_human_review_approval_updates_queue_and_dashboard():
    app = run_all_demos()
    app.button(key="approve_demo_human_review").click().run()
    assert any(tab.label == "Human Review (1)" for tab in app.tabs)
    assert metric(app, "Resolved by human") == "1"
```

- [ ] **Step 5: Implement Human Review tab**

Render only pending cases. Show reason, uncertain-field source evidence, per-field choice and entered value, missing-attachment uploader/re-run, and the two final decision buttons. Apply immutable transitions from Task 4 and rerun immediately.

- [ ] **Step 6: Implement Report tab and downloads**

Render each report badge, verdict, next step, seven-field table, and per-field cleaned-value/evidence expander. Add `st.download_button` for `shipping_report.csv` and `submission.json`.

- [ ] **Step 7: Implement Dashboard tab**

Render six KPI cards, category/outcome/mismatched-field charts, status filter, and urgency-sorted Needs action dataframe. Do not exceed three charts.

- [ ] **Step 8: Implement collapsed Technical details**

Place the 80% threshold control, model identity, raw class scores, automated submission JSON, and exact JEV future-enhancement disclosure at the bottom. Threshold changes recompute only displayed High/Low classification from existing real-signal scores; they do not rewrite automated submission.

- [ ] **Step 9: Run Task 6 AppTests**

Run: `.venv/bin/python -m pytest tests/test_streamlit_app.py -q`  
Expected: PASS. Leave changes uncommitted.

---

### Task 7: Documentation and End-to-End Verification

**Files:**
- Modify: `README.md`
- Modify if required by imports only: `src/frontend/__init__.py`
- Test: all files under `tests/`

**Interfaces:**
- Consumes: completed workbench UI and verified commands.
- Produces: final local run/deployment/demo instructions and verification evidence.

- [ ] **Step 1: Update README usage and deployment sections**

Document:

```text
Local: create Python 3.12 venv, install requirements, run streamlit_app.py.
Cloud: connect Aloysius8895/MonashHack, choose feat/frontend-demo (or main after merge), entry point streamlit_app.py, no secrets.
AI: trained TF-IDF/scikit-learn classifier plus real document extraction and deterministic comparison.
Cloud infrastructure: Streamlit Community Cloud hosts the public prototype.
```

- [ ] **Step 2: Add the five-minute click order**

The order is Run all demo scenarios → inspect highlighted paths → resolve one Human Review case → inspect Report → inspect Dashboard → download CSV/JSON → open Technical details and state that JEV is future work.

- [ ] **Step 3: Run focused frontend tests**

Run: `.venv/bin/python -m pytest tests/test_frontend_inbox.py tests/test_frontend_service.py tests/test_frontend_workbench.py tests/test_frontend_review.py tests/test_frontend_reporting.py tests/test_streamlit_app.py -q`  
Expected: all pass.

- [ ] **Step 4: Run the complete repository suite**

Run: `.venv/bin/python -m pytest -q`  
Expected: all pass with zero failures.

- [ ] **Step 5: Start the app headlessly**

Run: `.venv/bin/streamlit run streamlit_app.py --server.headless true --server.port 8765`  
Expected: Streamlit prints `Local URL: http://localhost:8765` and remains running without traceback.

- [ ] **Step 6: Visually verify every flow**

In a browser, run all scenarios and confirm four tabs, the two pending review cases, report badges/tables, six dashboard KPIs, no more than three charts, downloads, collapsed technical details, and no horizontal overflow at desktop width.

- [ ] **Step 7: Check diff integrity and preserve local-only state**

Run: `git diff --check && git status --short && git rev-list --left-right --count origin/feat/frontend-demo...HEAD`  
Expected: no whitespace errors; intended files are modified/untracked; branch commit count remains `0 0` because nothing was committed or pushed.

- [ ] **Step 8: Present the local URL and click path for user approval**

Do not commit or push. Wait for explicit user confirmation. After confirmation, run fresh tests, commit the complete approved change, push `feat/frontend-demo`, and verify PR #1 reflects the new commit.
