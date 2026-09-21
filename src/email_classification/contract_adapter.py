from __future__ import annotations

from collections.abc import Mapping

from contracts import AttachmentPair, ClassificationResult

from .routing import RoutingDecision, resolve_attachment_pair


PUBLISHED_CATEGORY_MAP = {
    "bl_comparison": "document_comparison",
    "new_si_request": "new_si_request",
    "invoice_query": "invoice_query",
    "general_message": "general_message",
    "spam": "spam",
}

COMPARISON_READY_STATUS = "ready_for_document_comparison"


class AdapterError(ValueError):
    pass


def to_contract(
    decision: RoutingDecision,
    record: Mapping[str, object],
) -> ClassificationResult:
    if str(record.get("email_id")) != decision.email_id:
        raise AdapterError(
            f"Routing decision {decision.email_id} does not match the supplied record"
        )
    published = PUBLISHED_CATEGORY_MAP.get(decision.category)
    if published is None:
        raise AdapterError(f"Internal category has no published name: {decision.category!r}")

    si_path, bl_path = resolve_attachment_pair(record)
    should_compare = (
        decision.route == "usable" and decision.status == COMPARISON_READY_STATUS
    )
    if should_compare and (si_path is None or bl_path is None):
        raise AdapterError(
            f"{decision.email_id} routed for comparison without both SI and BL paths"
        )

    return ClassificationResult(
        email_id=decision.email_id,
        category=published,
        should_compare=should_compare,
        attachments=AttachmentPair(si=si_path, bl=bl_path),
    )
