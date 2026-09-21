from __future__ import annotations

import csv
import io
import json
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class DashboardSummary:
    emails_processed: int
    comparison_requests: int
    no_mismatch: int
    mismatch_found: int
    waiting_for_human_review: int
    resolved_by_human: int
    categories: dict[str, int]
    outcomes: dict[str, int]
    mismatched_fields: dict[str, int]


def dashboard_summary(records):
    categories = Counter(item.automated.category for item in records)
    outcomes = Counter(item.final_status for item in records)
    mismatches = Counter(field for item in records for field in item.final_defect_fields)
    return DashboardSummary(len(records), sum(item.automated.category == "BL_COMPARISON" for item in records), outcomes["OK"], outcomes["MISMATCH"], sum(item.final_status == "NEEDS_REVIEW" and not item.reviewed_by_human for item in records), sum(item.reviewed_by_human for item in records), dict(categories), dict(outcomes), dict(mismatches))


def submission_json(records):
    return json.dumps({item.email_id: item.automated.submission for item in records}, indent=2)


def report_csv(records):
    target = io.StringIO(); writer = csv.writer(target)
    writer.writerow(["email_id", "category", "status", "field", "si_value", "bl_value", "result", "reviewed_by_human"])
    for item in records:
        fields = item.automated.comparison.fields if item.automated.comparison else ()
        if not fields: writer.writerow([item.email_id, item.automated.category, item.final_status, "", "", "", "", item.reviewed_by_human])
        for row in fields: writer.writerow([item.email_id, item.automated.category, item.final_status, row.field, row.si_value, row.bl_value, row.status, item.reviewed_by_human])
    return target.getvalue()
