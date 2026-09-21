from __future__ import annotations

import json
import sys
from pathlib import Path

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from frontend.service import (
    DemoConfigurationError,
    UploadedDocument,
    analyze_email,
    load_demo_runtime,
)


st.set_page_config(
    page_title="Shipping Document Verification",
    page_icon="🚢",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {max-width: 1180px; padding-top: 2rem;}
    [data-testid="stMetric"] {border: 1px solid #dbe4ed; border-radius: 12px; padding: 14px;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def runtime():
    return load_demo_runtime(PROJECT_ROOT)


def bundled_inputs():
    record = json.loads(
        (PROJECT_ROOT / "download2/inbox/email_001.json").read_text(encoding="utf-8")
    )
    si_path = PROJECT_ROOT / "download2" / record["attachments"][0]
    bl_path = PROJECT_ROOT / "download2" / record["attachments"][1]
    return (
        record,
        UploadedDocument(si_path.name, si_path.read_bytes()),
        UploadedDocument(bl_path.name, bl_path.read_bytes()),
    )


st.title("Shipping Document Verification")
st.write(
    "Classify an incoming shipping email, extract seven canonical SI and draft BL "
    "fields, and route uncertain evidence to human review."
)
st.caption("AI pipeline  ·  Document extraction  ·  Deterministic verification  ·  Human review")

with st.container(border=True):
    st.subheader("1 · Email and attachments")
    mode = st.radio(
        "Input mode",
        ("Bundled example", "Manual input"),
        horizontal=True,
        help="The bundled example runs email_001 and its real participant documents.",
    )

    if mode == "Bundled example":
        record, si_document, bl_document = bundled_inputs()
        subject = st.text_input("Email subject", value=record["subject"])
        body = st.text_area("Email body", value=record["body"], height=210)
        cols = st.columns(2)
        cols[0].text_input("Shipping Instruction", value=si_document.name, disabled=True)
        cols[1].text_input("Draft Bill of Lading", value=bl_document.name, disabled=True)
        email_id = record["email_id"]
    else:
        email_id = "demo_email"
        subject = st.text_input("Email subject", placeholder="e.g. Please verify SI and draft BL")
        body = st.text_area("Email body", height=210, placeholder="Paste the incoming email body")
        cols = st.columns(2)
        si_upload = cols[0].file_uploader(
            "Shipping Instruction",
            type=("txt", "pdf", "docx", "xlsx"),
            key="si_upload",
        )
        bl_upload = cols[1].file_uploader(
            "Draft Bill of Lading",
            type=("txt", "pdf", "docx", "xlsx"),
            key="bl_upload",
        )
        si_document = (
            UploadedDocument(si_upload.name, si_upload.getvalue()) if si_upload else None
        )
        bl_document = (
            UploadedDocument(bl_upload.name, bl_upload.getvalue()) if bl_upload else None
        )
        st.caption("Supported attachments: TXT, PDF, DOCX and XLSX. Files are processed in memory.")

    analyze = st.button("Analyze email", type="primary", key="analyze", width="stretch")

st.subheader("How the current prototype uses AI")
st.write(
    "The email category comes from the repository's trained TF-IDF and scikit-learn "
    "classifier, followed by deterministic routing rules. Extraction and SI/BL comparison "
    "are deterministic in this public demo configuration."
)
st.caption(
    "JEV is not used in the current prototype. It is a future enhancement for unfamiliar "
    "wording or low-confidence classifications."
)

if analyze:
    try:
        result = analyze_email(
            runtime(),
            subject,
            body,
            si_document,
            bl_document,
            email_id=email_id,
        )
    except DemoConfigurationError as error:
        st.error(str(error))
    else:
        st.divider()
        st.subheader("2 · Classification")
        category_labels = {
            "BL_COMPARISON": "BL Comparison",
            "SI_REQUEST": "SI Request",
            "INVOICE_QUERY": "Invoice Query",
            "GENERAL": "General",
            "SPAM": "Spam",
        }
        classification_cols = st.columns((1, 1, 2))
        classification_cols[0].metric(
            "Email category", category_labels[result.category]
        )
        classification_cols[1].metric(
            "Route",
            (
                "Verify documents"
                if result.comparison is not None
                else "Human review"
                if result.routing_status == "human_review"
                else "No comparison"
            ),
        )
        classification_cols[2].write("**Routing decision**")
        classification_cols[2].write(result.routing_reason)
        if result.rules_fired:
            classification_cols[2].caption(
                "Rules: " + ", ".join(result.rules_fired)
            )

        score_rows = [
            {"Category": category_labels[name], "Model score": score}
            for name, score in sorted(
                result.scores.items(), key=lambda item: item[1], reverse=True
            )
        ]
        with st.expander("View all five model scores"):
            st.bar_chart(
                {row["Category"]: row["Model score"] for row in score_rows},
                horizontal=True,
            )

        if result.comparison is None:
            st.info(
                "This category does not enter SI / draft BL verification. "
                "The workflow ends after classification."
            )
        elif not result.comparison.fields:
            st.subheader("3 · Document verification")
            st.warning(
                "Pending human review: both an SI and a draft BL are required."
            )
        else:
            st.subheader("3 · Document verification")
            status_labels = {
                "OK": "Match",
                "MISMATCH": "Mismatch detected",
                "NEEDS_REVIEW": "Pending human review",
            }
            fields = result.comparison.fields
            counts = {
                "OK": sum(row.status == "OK" for row in fields),
                "MISMATCH": sum(row.status == "MISMATCH" for row in fields),
                "NEEDS_REVIEW": sum(row.status == "NEEDS_REVIEW" for row in fields),
            }
            result_cols = st.columns(4)
            result_cols[0].metric(
                "Verification status", status_labels[result.comparison.status]
            )
            result_cols[1].metric("Matched fields", counts["OK"])
            result_cols[2].metric("Mismatched fields", counts["MISMATCH"])
            result_cols[3].metric("Review fields", counts["NEEDS_REVIEW"])
            if result.comparison.review_reason:
                st.warning(
                    "Human review reason: " + result.comparison.review_reason
                )

            comparison_rows = [
                {
                    "Field": row.field.replace("_", " ").title(),
                    "SI value": "—" if row.si_value is None else str(row.si_value),
                    "Draft BL value": "—" if row.bl_value is None else str(row.bl_value),
                    "Normalized SI": "—" if row.normalized_si is None else str(row.normalized_si),
                    "Normalized BL": "—" if row.normalized_bl is None else str(row.normalized_bl),
                    "Status": status_labels[row.status],
                    "Reason": row.reason,
                }
                for row in fields
            ]
            st.dataframe(
                comparison_rows,
                hide_index=True,
                width="stretch",
                column_config={
                    "Status": st.column_config.TextColumn("Status", width="medium"),
                    "Reason": st.column_config.TextColumn("Reason", width="large"),
                },
            )

            st.markdown("#### Traceable evidence")
            st.caption(
                "Raw labels, values and source locations are preserved separately from normalized comparison values."
            )
            for row in fields:
                with st.expander(
                    f"{row.field.replace('_', ' ').title()} · {status_labels[row.status]}"
                ):
                    evidence_cols = st.columns(2)
                    for column, evidence in zip(
                        evidence_cols,
                        (row.si_evidence, row.bl_evidence),
                        strict=True,
                    ):
                        column.write(f"**{evidence.document_role} · {evidence.filename}**")
                        column.json(
                            {
                                "raw_label": evidence.raw_label,
                                "raw_value": evidence.raw_value,
                                "evidence_location": evidence.location,
                                "ocr_used": evidence.ocr_used,
                                "llm_fallback_used": evidence.llm_used,
                                "garbled": evidence.garbled,
                            }
                        )

        st.subheader("4 · Organizer-format result")
        if result.submission is None:
            st.warning(
                "No organizer result is claimed until a person confirms this uncertain email category."
            )
        else:
            st.caption(
                "This JSON contains only the five properties accepted by the organizer submission contract."
            )
            st.json(result.submission)
