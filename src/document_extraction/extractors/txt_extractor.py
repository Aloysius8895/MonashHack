"""Extractor for plain-text SI/BL attachments.

Format: one "Label: value" pair per line (see download2/attachments/*.txt).
"""
import re

from ..fields import classify_label
from ..normalize import normalize_label

_LINE_RE = re.compile(r"^([^\r\n:]{1,60}):\s*(.*)$")


def extract(text):
    """Returns (hits, full_text, meta) where hits maps canonical field name
    to (raw_label, raw_value, evidence). meta is empty for this format -
    only the PDF extractor's OCR fallback needs it."""
    hits = {}
    for lineno, line in enumerate(text.splitlines(), start=1):
        match = _LINE_RE.match(line)
        if not match:
            continue
        label, value = match.group(1).strip(), match.group(2).strip()
        field_name = classify_label(normalize_label(label))
        if field_name and field_name not in hits:
            hits[field_name] = (label, value, f"line {lineno}")
    return hits, text, {}
