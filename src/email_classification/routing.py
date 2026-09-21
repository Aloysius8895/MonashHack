from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from .splitting import ALLOWED_CATEGORIES


_SI_PATTERN = re.compile(r"(?:^|[_\W])si(?:[_\W]|$)", re.I)
_BL_PATTERN = re.compile(r"(?:^|[_\W])bl(?:[_\W]|$)", re.I)
_INVOICE_PATTERN = re.compile(r"\b(invoice|billing|payment due)\b", re.I)
_NEW_SI_PATTERN = re.compile(
    r"\b(new|create|prepare|submit|send)\b.{0,30}\b(si|shipping instruction)s?\b",
    re.I | re.S,
)
_SPAM_PATTERN = re.compile(
    r"\b(lottery|prize winner|claim your prize|unsubscribe|limited offer)\b",
    re.I,
)
_COMPARISON_PATTERN = re.compile(
    r"\b(compare|comparison|check|verify|match)\b.{0,50}\b(si|bl|draft|bill of lading)\b",
    re.I | re.S,
)


@dataclass(frozen=True)
class RoutingDecision:
    email_id: str
    category: str
    route: str
    status: str
    reason: str
    rules_fired: tuple[str, ...]


def route_prediction(
    record: Mapping[str, object],
    predicted_category: str,
    scores: Mapping[str, float],
    review_margin_threshold: float,
    unavailable_attachments: Sequence[str] = (),
) -> RoutingDecision:
    email_id = record.get("email_id")
    if not isinstance(email_id, str):
        raise ValueError("Record email_id must be a string")
    if predicted_category not in ALLOWED_CATEGORIES:
        raise ValueError(f"Invalid predicted category: {predicted_category}")
    if review_margin_threshold < 0:
        raise ValueError("Review margin threshold cannot be negative")
    if unavailable_attachments:
        return RoutingDecision(
            email_id=email_id,
            category=predicted_category,
            route="unusable",
            status="human_review",
            reason=(
                "Attachment cannot be opened: "
                + ", ".join(sorted(unavailable_attachments))
            ),
            rules_fired=("unavailable_attachment",),
        )

    names = _attachment_names(record)
    has_si = any(_SI_PATTERN.search(name) for name in names)
    has_bl = any(_BL_PATTERN.search(name) for name in names)
    evidence_category, rules_fired = _strong_evidence(record, names, has_si, has_bl)
    margin = _score_margin(scores)
    category = predicted_category
    adjusted = False

    if evidence_category is not None and evidence_category != predicted_category:
        if margin <= review_margin_threshold:
            category = evidence_category
            adjusted = True
        else:
            return RoutingDecision(
                email_id=email_id,
                category=predicted_category,
                route="unusable",
                status="human_review",
                reason=(
                    f"Model prediction conflicts with strong {evidence_category} "
                    "evidence."
                ),
                rules_fired=rules_fired,
            )

    if category == "bl_comparison":
        missing = []
        if not has_si:
            missing.append("SI")
        if not has_bl:
            missing.append("BL")
        if missing:
            return RoutingDecision(
                email_id=email_id,
                category=category,
                route="unusable",
                status="human_review",
                reason=f"Document comparison is missing required {' and '.join(missing)} attachment.",
                rules_fired=rules_fired + ("missing_required_attachment",),
            )

    if not adjusted and margin < review_margin_threshold:
        return RoutingDecision(
            email_id=email_id,
            category=category,
            route="unusable",
            status="human_review",
            reason=(
                f"Model score margin {margin:.6f} is below the OOF-derived "
                f"review margin {review_margin_threshold:.6f}."
            ),
            rules_fired=rules_fired + ("low_score_margin",),
        )

    if category == "bl_comparison":
        return RoutingDecision(
            email_id=email_id,
            category=category,
            route="usable",
            status="ready_for_document_comparison",
            reason=(
                "Classified as bl_comparison with usable SI and BL attachment metadata."
                if not adjusted
                else "Strong comparison evidence adjusted an uncertain prediction; SI and BL are present."
            ),
            rules_fired=rules_fired,
        )

    return RoutingDecision(
        email_id=email_id,
        category=category,
        route="unusable",
        status="rule_adjusted" if adjusted else "classified",
        reason=(
            f"Strong {category} evidence adjusted an uncertain model prediction."
            if adjusted
            else f"Category {category} does not enter document comparison."
        ),
        rules_fired=rules_fired,
    )


def _strong_evidence(
    record: Mapping[str, object],
    names: tuple[str, ...],
    has_si: bool,
    has_bl: bool,
) -> tuple[str | None, tuple[str, ...]]:
    subject = str(record.get("subject", ""))
    body = str(record.get("body", ""))
    text = f"{subject}\n{body}\n{' '.join(names)}"
    subject_and_names = f"{subject}\n{' '.join(names)}"
    matches = []
    if _SPAM_PATTERN.search(text):
        matches.append(("spam", "spam_evidence"))
    if _INVOICE_PATTERN.search(subject_and_names):
        matches.append(("invoice_query", "invoice_evidence"))
    if _NEW_SI_PATTERN.search(subject) and not has_bl:
        matches.append(("new_si_request", "new_si_evidence"))
    if has_si and has_bl and _COMPARISON_PATTERN.search(text):
        matches.append(("bl_comparison", "comparison_evidence"))

    categories = {category for category, _rule in matches}
    rules = tuple(rule for _category, rule in matches)
    if len(categories) == 1:
        return matches[0][0], rules
    return None, rules + (("conflicting_rule_evidence",) if len(categories) > 1 else ())


def resolve_attachment_pair(
    record: Mapping[str, object],
) -> tuple[str | None, str | None]:
    si_path: str | None = None
    bl_path: str | None = None
    for attachment in _attachment_paths(record):
        name = PurePosixPath(attachment.replace("\\", "/")).name
        if _SI_PATTERN.search(name):
            if si_path is None:
                si_path = attachment
        elif _BL_PATTERN.search(name):
            if bl_path is None:
                bl_path = attachment
    return si_path, bl_path


def _attachment_paths(record: Mapping[str, object]) -> tuple[str, ...]:
    attachments = record.get("attachments")
    if not isinstance(attachments, list) or not all(
        isinstance(item, str) for item in attachments
    ):
        raise ValueError("Email field attachments must be a list of strings")
    return tuple(attachments)


def _attachment_names(record: Mapping[str, object]) -> tuple[str, ...]:
    return tuple(
        PurePosixPath(item.replace("\\", "/")).name
        for item in _attachment_paths(record)
    )


def _score_margin(scores: Mapping[str, float]) -> float:
    values = sorted((float(value) for value in scores.values()), reverse=True)
    if len(values) < 2:
        return 0.0
    return values[0] - values[1]
