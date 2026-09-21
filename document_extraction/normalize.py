"""Normalization helpers for extracted SI/BL field values.

Kept deliberately separate from label classification (fields.py): this
module only turns a raw label/value string into a clean, comparable form -
it doesn't decide *which* canonical field something belongs to.
"""
import re

_CJK_RE = re.compile(r"[一-鿿]+")
_WS_RE = re.compile(r"\s+")
_EMPTY_PARENS_RE = re.compile(r"\(\s*\)")
_MISSING_RE = re.compile(r"^(N/?A\.?|TBD|NONE|-{2,}|_+|\?+)$", re.IGNORECASE)


def normalize_label(label):
    """Uppercase, whitespace-collapsed label used for alias/keyword matching."""
    label = _CJK_RE.sub("", label)
    label = _EMPTY_PARENS_RE.sub("", label)
    label = _WS_RE.sub(" ", label).strip()
    return label.upper().rstrip(" :")


def clean_text(value):
    if value is None:
        return ""
    text = _WS_RE.sub(" ", str(value)).strip()
    return text


def is_missing_placeholder(value):
    """True for blank values and placeholder text like 'N/A' or '______'."""
    if value is None:
        return True
    text = clean_text(value)
    if not text:
        return True
    return bool(_MISSING_RE.match(text))


def looks_garbled(value):
    """Heuristic flag for PDF text-extraction corruption.

    Observed in this dataset: overlapping text boxes in source PDFs make
    pdfplumber interleave two strings, e.g. "Notify Party/Intermediate
    ConsCigEnReIEeX" instead of "...Consignee CERIEX". Real company/place
    names don't switch from lowercase to uppercase mid-word repeatedly;
    corrupted extractions do.
    """
    if not value:
        return False
    transitions = len(re.findall(r"[a-z][A-Z]", value))
    return transitions >= 3


def parse_container_count(raw):
    if isinstance(raw, (int, float)):
        return int(raw)
    text = clean_text(raw)
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else None


_THOUSANDS_DOT_RE = re.compile(r"^\d{1,3}\.\d{3}$")


def parse_gross_weight_kg(raw):
    if isinstance(raw, (int, float)):
        return int(round(raw))
    text = clean_text(raw)
    match = re.search(r"([\d,]+(?:\.\d+)?)", text)
    if not match:
        return None
    number_text = match.group(1)
    # Gross weight in this dataset is always a whole number of kg. OCR
    # sometimes misreads a "," thousands separator as ".", e.g. "22,625" ->
    # "22.625" - a lone "NNN.NNN"-shaped group is that separator, not a
    # fraction of a kg.
    if _THOUSANDS_DOT_RE.match(number_text):
        number_text = number_text.replace(".", "")
    number_text = number_text.replace(",", "")
    return int(round(float(number_text)))


def parse_value(field_name, raw):
    """Dispatch to the right normalizer for a canonical field's raw value."""
    if field_name == "container_count":
        return parse_container_count(raw)
    if field_name == "gross_weight_kg":
        return parse_gross_weight_kg(raw)
    return clean_text(raw)
