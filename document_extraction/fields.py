"""Canonical SI/BL fields, and the label variants that map to each one.

The alias lists were compiled by scanning every txt/xlsx/docx/pdf attachment
in download2/attachments/ (not guessed), so they reflect labels that
actually appear across the sample SI and BL documents, e.g. the same field
shows up as "Port of Loading (POL)" in one document and "Load Port" in
another. Matching runs against the normalized (normalize_label) form.
"""

CANONICAL_FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]

ALIASES = {
    "shipper": [
        "SHIPPER (PRINCIPAL OR SELLER)",
        "SHIPPER/EXPORTER",
        "SHIPPER",
    ],
    "consignee": [
        "CONSIGNEE (NON-NEGOTIABLE)",
        "TO THE ORDER OF",
        "CONSIGNEE",
    ],
    "notify_party": [
        "NOTIFY PARTY/INTERMEDIATE CONSIGNEE",
        "NOTIFY PARTY",
        "NOTIFY",
    ],
    "port_of_loading": [
        "PORT OF LOADING (POL)",
        "PORT OF LOADING",
        "LOAD PORT",
        "POL",
    ],
    "port_of_discharge": [
        "PORT OF DISCHARGE (POD)",
        "PORT OF DISCHARGE",
        "DISCHARGE PORT",
        "POD",
    ],
    "container_count": [
        "NO. OF CONTAINERS OR PACKAGES",
        "NO. OF CONTAINERS",
        "TOTAL CONTAINERS",
        "CONTAINER COUNT",
    ],
    "gross_weight_kg": [
        "TOTAL GROSS WEIGHT (KG)",
        "TOTAL GROSS WT (KGS)",
        "GROSS WEIGHT (KG)",
        "GROSS WT (KGS)",
        "GROSS WEIGHT",
    ],
}

# Labels observed in the data that look related but must NEVER be treated as
# one of the 7 canonical fields - e.g. some SIs also print a NET WEIGHT line
# alongside GROSS WEIGHT; aliasing them together would silently hide real
# gross-weight discrepancies.
DISTRACTOR_LABELS = {
    "NET WEIGHT",
}

ALIAS_TO_FIELD = {
    alias: field_name for field_name, aliases in ALIASES.items() for alias in aliases
}

# Fallback keyword rules for label variants not in ALIASES (e.g. future/
# messier sample data). Only used for whole-cell labels (txt/xlsx/docx),
# never for PDF line-prefix scanning - there, an open-ended substring rule
# can swallow the start of the value into the label.
_FIELD_KEYWORD_RULES = [
    ("shipper", lambda l: "SHIPPER" in l and "CONSIGNEE" not in l),
    ("consignee", lambda l: "NOTIFY" not in l and ("CONSIGNEE" in l or l == "TO THE ORDER OF")),
    ("notify_party", lambda l: "NOTIFY" in l),
    ("port_of_loading", lambda l: l in ("POL", "LOAD PORT") or ("LOADING" in l and "PORT" in l)),
    ("port_of_discharge", lambda l: l in ("POD", "DISCHARGE PORT") or ("DISCHARGE" in l and "PORT" in l)),
    ("container_count", lambda l: "CONTAINER" in l),
    ("gross_weight_kg", lambda l: "NET" not in l and "GROSS" in l and ("WEIGHT" in l or "WT" in l)),
]


def classify_label(normalized_label):
    """Map a normalized label string to a canonical field, or None."""
    if normalized_label in DISTRACTOR_LABELS:
        return None
    field_name = ALIAS_TO_FIELD.get(normalized_label)
    if field_name:
        return field_name
    for field_name, rule in _FIELD_KEYWORD_RULES:
        if rule(normalized_label):
            return field_name
    return None


# Document-type header keywords that indicate an attachment is NOT an SI/BL
# at all (e.g. a commercial invoice attached by mistake, as in email_501).
# Checked against the whole extracted text, not per-line.
WRONG_DOC_TYPE_MARKERS = [
    "COMMERCIAL INVOICE",
    "CERTIFICATE OF ORIGIN",
    "PACKING LIST",
]
