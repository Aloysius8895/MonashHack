"""Extractor for PDF SI/BL attachments.

Unlike the txt/xlsx/docx formats, these PDFs put the label and value on the
same line with no separator ("Shipper APRIL FINE PAPER TRADING", "POL
BUATAN, INDONESIA") and wrap multi-line addresses across following lines.
There's no clean delimiter to split on, so instead we check, per line,
whether it *starts with* one of the known field aliases (longest alias
first, so "Port of Discharge (POD)" wins over the shorter "Port of
Discharge" when both would match) - this only uses the fixed alias list
from fields.py, never an open-ended keyword rule, because an open-ended
rule can keep matching past the label into the value on these
label+value-on-one-line layouts.

The container/weight totals ("No. of Containers: 6 x 40'HC", "TOTAL Gross
Wt (kgs): 131,322 KG") are themselves colon-separated summary lines above a
per-container table, so the same line-prefix match handles them directly -
no need to sum the table rows ourselves. A couple of sample PDFs render
these two labels with overlapping text boxes that corrupt the label text
(e.g. "TOTAL Gross Weightnn(KGS)"); _WEIGHT_FALLBACK/_CONTAINER_FALLBACK
recover the value from its unambiguous "<number> KG" / "<number> x ..."
shape when the label match fails.

Scanned pages: if a page's text layer is empty or near-empty (no sample PDF
in this dataset is scanned, but the brief calls this out as an advanced
case), the page is rendered to an image via pdfplumber's built-in pdfium
renderer (no poppler/pdftoppm needed) and run through Tesseract OCR
(ocr.py). The OCR'd text is fed through the exact same line-prefix matching
as a normal text layer, so scanned pages don't need separate parsing logic
- just a different source of text. If no OCR engine is installed, the page
is left blank rather than raising, and that's surfaced via the `ocr_unavailable`
flag in the returned meta dict so the caller can route it to human review.
"""
import io
import re

import pdfplumber

from ..fields import ALIASES
from ..ocr import is_available as ocr_available
from ..ocr import ocr_image

_MIN_TEXT_LAYER_CHARS = 20

def _alias_pattern(alias):
    # \s* (not \s+) between words so an OCR'd "Portof Loading" (missing
    # space) still matches the "PORT OF LOADING" alias - the fixed alias
    # list keeps this safe from open-ended over-matching.
    return re.compile(r"^" + r"\s*".join(re.escape(tok) for tok in alias.split()))


_SORTED_ALIASES = sorted(
    (
        (_alias_pattern(alias), field_name, alias)
        for field_name, aliases in ALIASES.items()
        for alias in aliases
    ),
    key=lambda triple: -len(triple[2]),
)

_WEIGHT_FALLBACK = re.compile(r"GROSS.*?([\d,]+)\s*KG", re.IGNORECASE)
_CONTAINER_FALLBACK = re.compile(r"CONTAINER.*?:?\s*(\d+)\s*x", re.IGNORECASE)


def _match_line_prefix(line):
    upper = line.upper()
    for pattern, field_name, _alias in _SORTED_ALIASES:
        match = pattern.match(upper)
        if not match:
            continue
        end = match.end()
        # "." is included because Tesseract sometimes reads a label's colon
        # as a period ("Shipper. APRIL..." instead of "Shipper: APRIL...")
        if end == len(upper) or upper[end] in " :.\t":
            value = line[end:].lstrip(": .").strip()
            return field_name, line[:end], value
    return None


def extract(data):
    hits = {}
    text_parts = []
    any_ocr_used = False
    any_ocr_unavailable = False

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_idx, page in enumerate(pdf.pages, start=1):
            page_text = page.extract_text() or ""
            page_ocr_used = False

            if len(page_text.strip()) < _MIN_TEXT_LAYER_CHARS:
                if ocr_available():
                    try:
                        image = page.to_image(resolution=300).original
                        ocr_text = ocr_image(image)
                    except Exception:
                        ocr_text = ""
                    if ocr_text.strip():
                        page_text = ocr_text
                        page_ocr_used = True
                        any_ocr_used = True
                else:
                    any_ocr_unavailable = True

            text_parts.append(page_text)
            evidence_suffix = " (OCR)" if page_ocr_used else ""
            for line_idx, line in enumerate(page_text.splitlines(), start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                match = _match_line_prefix(stripped)
                if not match:
                    continue
                field_name, label, value = match
                if field_name not in hits and value:
                    hits[field_name] = (label, value, f"page {page_idx} line {line_idx}{evidence_suffix}")

    full_text = "\n".join(text_parts)

    if "gross_weight_kg" not in hits:
        match = _WEIGHT_FALLBACK.search(full_text)
        if match:
            hits["gross_weight_kg"] = ("(regex fallback)", f"{match.group(1)} KG", "regex fallback")
    if "container_count" not in hits:
        match = _CONTAINER_FALLBACK.search(full_text)
        if match:
            hits["container_count"] = ("(regex fallback)", match.group(1), "regex fallback")

    meta = {"ocr_used": any_ocr_used, "ocr_unavailable": any_ocr_unavailable}
    return hits, full_text, meta
