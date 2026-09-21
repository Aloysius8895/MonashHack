"""Extractor for Excel SI/BL attachments.

Format: a single sheet, 2-column key/value grid (label in column A, value
in column B). Weight is sometimes a numeric cell, sometimes text - both are
handled here and normalize.parse_gross_weight_kg() downstream.
"""
import io

import openpyxl

from ..fields import classify_label
from ..normalize import normalize_label


def extract(data):
    workbook = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    hits = {}
    text_parts = []
    for sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
        for row_idx, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            if not row or row[0] is None:
                continue
            label = str(row[0]).strip()
            value = row[1] if len(row) > 1 else None
            text_parts.append(f"{label} {value}")
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            field_name = classify_label(normalize_label(label))
            if field_name and field_name not in hits:
                hits[field_name] = (label, value, f"sheet '{sheet_name}' row {row_idx}")
    return hits, "\n".join(text_parts), {}
