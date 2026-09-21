from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src")) if str(ROOT / "src") not in sys.path else None

from frontend.inbox import InboxRecord, ResolvedDocuments, index_attachments, parse_inbox_uploads, resolve_record_documents  # noqa: E402
from frontend.reporting import dashboard_summary, report_csv, submission_json  # noqa: E402
from frontend.review import FieldDecision, apply_review, pending_reviews, replace_after_rerun  # noqa: E402
from frontend.service import UploadedDocument, load_demo_runtime  # noqa: E402
from frontend.workbench import process_record, upsert_records  # noqa: E402


st.set_page_config(page_title="Shipping Operations Workbench", page_icon="🚢", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""
<style>
.block-container{max-width:1200px;padding-top:1.6rem}.stMetric{background:#f7f9fc;border:1px solid #e1e7ef;border-radius:12px;padding:12px}
.step-done{border-left:4px solid #16835b;padding:.35rem .8rem;margin:.25rem 0}.step-skip{border-left:4px solid #c7ced8;color:#7b8491;padding:.35rem .8rem;margin:.25rem 0}.step-warn{border-left:4px solid #d58a00;padding:.35rem .8rem;margin:.25rem 0}
</style>""", unsafe_allow_html=True)


@st.cache_resource
def runtime(): return load_demo_runtime(ROOT)


def init_state():
    st.session_state.setdefault("processed_emails", ())
    st.session_state.setdefault("processing_issues", ())
    st.session_state.setdefault("latest_email_id", None)
    st.session_state.setdefault("confidence_threshold", 80)


def store(items):
    st.session_state.processed_emails = upsert_records(st.session_state.processed_emails, items)
    if items: st.session_state.latest_email_id = items[-1].email_id


def badge(item):
    if item.automated.category != "BL_COMPARISON":
        st.info("**CLASSIFIED ONLY**  \nClassified only, no action needed."); return
    if item.final_status == "NEEDS_REVIEW":
        reason = item.automated.comparison.review_reason if item.automated.comparison else "uncertain classification"
        st.warning(f"**HUMAN REVIEW**  \n{next_step(item)} ({reason})"); return
    if item.final_status == "MISMATCH":
        st.error(f"**ACTION REQUIRED – {len(item.final_defect_fields)} mismatch(es)**  \n{next_step(item)}"); return
    st.success("**NO MISMATCH DETECTED**  \nDraft BL matches the SI. Safe to finalise.")


def next_step(item):
    if item.automated.category != "BL_COMPARISON": return "No action needed."
    reason = item.automated.comparison.review_reason if item.automated.comparison else None
    if reason == "missing_attachment": return "BL attachment is missing. Ask the sender to resend it."
    if reason == "unreadable": return "An attachment cannot be read. Check the file manually or request a new copy."
    if reason == "missing_value": return "Required shipping information is missing. Complete it before approval."
    if reason == "wrong_doc_type": return "Replace the incorrect attachment with the SI or draft BL."
    if item.final_status == "MISMATCH":
        rows = item.automated.comparison.fields if item.automated.comparison else ()
        details = []
        for field in item.final_defect_fields:
            row = next((value for value in rows if value.field == field), None)
            label = field.replace("_", " ").title()
            details.append(f"{label} (SI: {row.si_value}, BL: {row.bl_value})" if row else label)
        return "Ask the carrier to correct " + "; ".join(details) + "."
    return "Draft BL matches the SI. Safe to finalise."


def field_rows(item):
    comparison = item.automated.comparison
    if comparison is None: return []
    labels = {"OK": "Match", "MISMATCH": "Mismatch", "NEEDS_REVIEW": "Review"}
    return [{"Field": row.field.replace("_", " ").title(), "SI value": str(row.si_value) if row.si_value is not None else "—", "BL value": str(row.bl_value) if row.bl_value is not None else "—", "Result": labels[row.status]} for row in comparison.fields]


def render_pipeline(item):
    st.markdown("**Route taken**")
    route = "Inbox → Classifier → " + ("Classify only → Report → Dashboard" if item.automated.category != "BL_COMPARISON" else "Attachment check → Extraction → Clean values → Comparison → Confidence → " + ("Human review" if item.final_status == "NEEDS_REVIEW" else "Final result") + " → Report → Dashboard")
    st.caption(route)
    st.markdown("#### Pipeline steps")
    for step in item.automated.pipeline_steps:
        css = "step-done" if step.state == "complete" else "step-warn" if step.state == "attention" else "step-skip"
        icon = "✓" if step.state == "complete" else "!" if step.state == "attention" else "–"
        st.markdown(f'<div class="{css}"><b>{icon} {step.name}</b> — {step.summary}</div>', unsafe_allow_html=True)


init_state()
records = st.session_state.processed_emails
pending = pending_reviews(records)
st.title("Shipping Operations Workbench")
st.write("Process shipping emails, review exceptions, and see the next action at a glance.")
input_tab, review_tab, report_tab, dashboard_tab = st.tabs(["Input & Run", f"Human Review ({len(pending)})", "Report", "Dashboard"])

with input_tab:
    st.subheader("Process your inbox")
    left, right = st.columns(2)
    inbox_files = left.file_uploader("Inbox JSON files", type="json", accept_multiple_files=True, key="inbox_uploads")
    attachment_files = right.file_uploader("SI and draft BL attachments", type=("txt", "pdf", "docx", "xlsx"), accept_multiple_files=True, key="attachment_uploads")
    if st.button("Run uploaded inbox", type="primary", key="run_uploaded", disabled=not inbox_files):
        json_uploads = [UploadedDocument(file.name, file.getvalue()) for file in inbox_files]
        uploads = [UploadedDocument(file.name, file.getvalue()) for file in attachment_files]
        inbox_records, parse_issues = parse_inbox_uploads(json_uploads)
        attachment_index, attachment_issues = index_attachments(uploads)
        completed = [process_record(runtime(), record, resolve_record_documents(record, attachment_index)) for record in inbox_records]
        store(completed); st.session_state.processing_issues = parse_issues + attachment_issues; st.rerun()

    with st.expander("Manual email entry"):
        subject = st.text_input("Email subject", key="manual_subject")
        body = st.text_area("Email body", key="manual_body")
        manual_cols = st.columns(2)
        manual_si = manual_cols[0].file_uploader("Shipping Instruction", type=("txt", "pdf", "docx", "xlsx"), key="manual_si")
        manual_bl = manual_cols[1].file_uploader("Draft Bill of Lading", type=("txt", "pdf", "docx", "xlsx"), key="manual_bl")
        if st.button("Run manual email", key="run_manual"):
            source = InboxRecord("manual_email", "", subject, body, tuple(filter(None, [manual_si.name if manual_si else None, manual_bl.name if manual_bl else None])))
            documents = ResolvedDocuments(UploadedDocument(manual_si.name, manual_si.getvalue()) if manual_si else None, UploadedDocument(manual_bl.name, manual_bl.getvalue()) if manual_bl else None, ())
            store((process_record(runtime(), source, documents),)); st.rerun()
    if st.session_state.processing_issues:
        for issue in st.session_state.processing_issues: st.error(f"{issue.location}: {issue.message}")
    latest = next((item for item in st.session_state.processed_emails if item.email_id == st.session_state.latest_email_id), None)
    if latest: st.divider(); badge(latest); render_pipeline(latest)

with review_tab:
    st.subheader("Cases waiting for a person")
    if not pending: st.success("No cases are waiting for review.")
    for item in pending:
        with st.container(border=True):
            st.markdown(f"### {item.email_id}"); st.warning(next_step(item))
            rows = field_rows(item)
            if rows: st.dataframe([row for row in rows if row["Result"] == "Review"] or rows, hide_index=True, width="stretch")
            decisions = []
            if item.automated.comparison and item.automated.comparison.fields:
                for row in item.automated.comparison.fields:
                    if row.status == "OK": continue
                    with st.expander(f"Review {row.field.replace('_', ' ').title()}"):
                        evidence = st.columns(2)
                        evidence[0].write(f"**SI raw text**  \n{row.si_evidence.raw_value or 'Not available'}")
                        evidence[1].write(f"**BL raw text**  \n{row.bl_evidence.raw_value or 'Not available'}")
                        choice = st.radio("Choose the trusted value", ("SI is correct", "BL is correct", "Enter value"), key=f"choice_{item.email_id}_{row.field}", horizontal=True)
                        entered = st.text_input("Correct value", key=f"entered_{item.email_id}_{row.field}", disabled=choice != "Enter value")
                        decisions.append(FieldDecision(row.field, {"SI is correct": "si", "BL is correct": "bl", "Enter value": "entered"}[choice], entered or None))
            reason = item.automated.comparison.review_reason if item.automated.comparison else None
            if reason == "missing_attachment":
                replacement = st.file_uploader("Upload the missing attachment", type=("txt", "pdf", "docx", "xlsx"), key=f"replacement_{item.email_id}")
                if st.button("Re-run", key=f"rerun_{item.email_id}", disabled=replacement is None):
                    uploaded = UploadedDocument(replacement.name, replacement.getvalue())
                    documents = ResolvedDocuments(item.documents.si_document or uploaded, item.documents.bl_document or uploaded, ())
                    rerun = process_record(runtime(), item.source, documents)
                    st.session_state.processed_emails = replace_after_rerun(records, rerun); st.rerun()
            buttons = st.columns(2)
            if buttons[0].button("Approve – no mismatch", key=f"approve_{item.email_id}"):
                updated = apply_review(item, "approve", ())
                st.session_state.processed_emails = upsert_records(records, (updated,)); st.rerun()
            if buttons[1].button("Confirm mismatch", key=f"mismatch_{item.email_id}"):
                if not decisions: decisions = [FieldDecision("consignee", "si", None)]
                updated = apply_review(item, "mismatch", decisions)
                st.session_state.processed_emails = upsert_records(records, (updated,)); st.rerun()

with report_tab:
    st.subheader("Operations report")
    if not records: st.info("Upload and run an inbox, or enter an email manually, to create a report.")
    else:
        download_cols = st.columns(2)
        download_cols[0].download_button("Download report (CSV)", report_csv(records), "shipping_report.csv", "text/csv")
        download_cols[1].download_button("Download submission.json", submission_json(records), "submission.json", "application/json")
        for item in records:
            with st.container(border=True):
                st.markdown(f"### {item.email_id} · {item.automated.category.replace('_', ' ').title()}")
                badge(item); st.write(f"**Next step:** {next_step(item)}")
                if item.reviewed_by_human: st.caption("Reviewed by human")
                rows = field_rows(item)
                if rows: st.dataframe(rows, hide_index=True, width="stretch")
                if item.automated.comparison and item.automated.comparison.fields:
                    with st.expander("Cleaned values and source evidence"):
                        for row in item.automated.comparison.fields:
                            st.markdown(f"**{row.field.replace('_', ' ').title()}** — Cleaned SI: `{row.normalized_si}` · Cleaned BL: `{row.normalized_bl}`")
                            st.caption(f"SI source: {row.si_evidence.raw_value} ({row.si_evidence.location}) | BL source: {row.bl_evidence.raw_value} ({row.bl_evidence.location})")

with dashboard_tab:
    st.subheader("Session dashboard")
    summary = dashboard_summary(records)
    labels = [("Emails processed", summary.emails_processed), ("Comparison requests", summary.comparison_requests), ("No mismatch", summary.no_mismatch), ("Mismatch found", summary.mismatch_found), ("Waiting for human review", summary.waiting_for_human_review), ("Resolved by human", summary.resolved_by_human)]
    for column, (label, value) in zip(st.columns(6), labels): column.metric(label, value)
    if records:
        charts = st.columns(3)
        charts[0].write("**Emails by category**"); charts[0].bar_chart(summary.categories)
        charts[1].write("**Outcomes**"); charts[1].bar_chart(summary.outcomes)
        charts[2].write("**Frequently mismatched fields**"); charts[2].bar_chart(summary.mismatched_fields or {"None": 0})
        st.write("**Needs action**")
        action_rows = [{"Email": item.email_id, "Status": item.final_status, "Next step": next_step(item)} for item in records if item.final_status != "OK"]
        status_filter = st.selectbox("Status filter", ["All", "NEEDS_REVIEW", "MISMATCH"], key="status_filter")
        if status_filter != "All": action_rows = [row for row in action_rows if row["Status"] == status_filter]
        st.dataframe(action_rows, hide_index=True, width="stretch")

with st.expander("Technical details"):
    st.slider("High-confidence display threshold", 50, 95, key="confidence_threshold")
    st.caption("Model: committed TF-IDF + scikit-learn classifier. Scores and the automated organizer output are shown below.")
    if records:
        selected_id = st.selectbox("Email", [item.email_id for item in records], key="technical_email")
        selected_record = next(item for item in records if item.email_id == selected_id)
        st.json({"scores": selected_record.automated.scores, "confidence": selected_record.automated.confidence.percent, "submission": selected_record.automated.submission})
    st.caption("JEV is not used in this prototype. It is a future enhancement for unfamiliar or low-confidence emails.")
