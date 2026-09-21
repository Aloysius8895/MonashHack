import os
import re
from pathlib import Path
from typing import Any, Dict, Optional


# ============================================================
# 1. REQUIRED FIELDS
# ============================================================

FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight"
]


# ============================================================
# 2. FIELD ALIASES
# ============================================================
# These are the different labels that may appear in the
# shipping documents for the same required field.
#
# Based on the actual hackathon documents.

FIELD_ALIASES = {

    "shipper": [
        "shipper",
        "shipper name",
        "exporter",
        "exporter name",
        "seller"
    ],

    "consignee": [
        "consignee",
        "consignee name",
        "consignee non negotiable",
        "consignee non-negotiable",
        "receiver",
        "importer",
        "buyer",

        # BL may use this instead of "Consignee"
        "to the order of"
    ],

    "notify_party": [
        "notify",
        "notify party",
        "notify_party",
        "notify person",
        "notify party name"
    ],

    "port_of_loading": [
        "port of loading",
        "port of loading pol",
        "loading port",
        "load port",
        "pol",
        "place of loading",
        "port of load"
    ],

    "port_of_discharge": [
        "port of discharge",
        "port of discharge pod",
        "discharge port",
        "pod",
        "place of discharge",
        "final destination"
    ],

    "container_count": [
        "container count",
        "container_count",
        "containers",
        "container quantity",
        "container qty",
        "number of containers",
        "number of container",
        "no of containers",
        "no of container",
        "no containers",
        "total containers"
    ],

    "gross_weight": [
        "gross weight",
        "gross_weight",
        "gross mass",
        "gross wt",
        "gross wt kgs",
        "gross weight kg",
        "gross weight kgs",
        "total weight",
        "total_weight",
        "weight"
    ]
}


# ============================================================
# 3. NORMALIZE FIELD LABEL
# ============================================================

def normalize_label(label: str) -> str:
    """
    Normalize document labels so that slightly different
    formatting can still be recognized.

    Example:

        "Port of Loading (POL)"
        ->
        "port of loading pol"

        "Gross Wt (kgs)"
        ->
        "gross wt kgs"
    """

    if label is None:
        return ""

    label = str(label).strip().lower()

    # Replace underscores with spaces
    label = label.replace("_", " ")

    # Replace brackets with spaces
    label = label.replace("(", " ")
    label = label.replace(")", " ")

    # Replace slash with spaces
    label = label.replace("/", " ")

    # Replace punctuation with spaces
    label = re.sub(r"[-:.,]", " ", label)

    # Remove extra spaces
    label = re.sub(r"\s+", " ", label)

    return label.strip()


# ============================================================
# 4. IDENTIFY FIELD
# ============================================================

def identify_field(label: str) -> Optional[str]:
    """
    Convert a document label into one of the seven standard
    fields.
    """

    normalized_label = normalize_label(label)

    for field, aliases in FIELD_ALIASES.items():

        for alias in aliases:

            normalized_alias = normalize_label(alias)

            if normalized_label == normalized_alias:
                return field

    return None


# ============================================================
# 5. EXTRACT FIELDS FROM TEXT
# ============================================================

def extract_fields_from_text(text: str) -> Dict[str, Any]:
    """
    Extract required fields from a text document.

    Main format supported:

        Shipper: ABC Company
        Consignee: XYZ Company
        Notify Party: XYZ Company

    Also supports labels such as:

        Consignee (Non-Negotiable): XYZ Company
        Port of Loading (POL): NANTONG, CHINA
        POD: KARACHI, PAKISTAN
        Total Containers: 6 x 40'HC
        Gross Wt (kgs): 131,058 KG
    """

    extracted = {}

    lines = text.splitlines()

    for line in lines:

        line = line.strip()

        if not line:
            continue

        # ----------------------------------------------------
        # Look for:
        #
        # LABEL: VALUE
        # ----------------------------------------------------

        match = re.match(
            r"^\s*([^:]+?)\s*:\s*(.*?)\s*$",
            line
        )

        if not match:
            continue

        label = match.group(1).strip()
        value = match.group(2).strip()

        if not value:
            continue

        field = identify_field(label)

        if field is not None:

            extracted[field] = value

    return extracted


# ============================================================
# 6. READ TEXT FILE
# ============================================================

def read_text_file(file_path: str) -> Optional[str]:
    """
    Read a text document.
    """

    try:

        with open(
            file_path,
            "r",
            encoding="utf-8",
            errors="replace"
        ) as file:

            return file.read()

    except FileNotFoundError:

        print(
            f"ERROR: File not found: {file_path}"
        )

        return None

    except Exception as error:

        print(
            f"ERROR reading {file_path}: {error}"
        )

        return None


# ============================================================
# 7. GENERAL TEXT NORMALIZATION
# ============================================================

def normalize_text(value: Any) -> Optional[str]:
    """
    General text normalization.
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    # Lowercase
    value = value.lower()

    # Normalize spaces
    value = re.sub(
        r"\s+",
        " ",
        value
    )

    # Remove unnecessary punctuation at edges
    value = value.strip(
        " ,.;:"
    )

    return value


# ============================================================
# 8. NAME NORMALIZATION
# ============================================================

def normalize_name(value: Any) -> Optional[str]:
    """
    Conservative normalization for shipper, consignee and
    notify party.

    We intentionally do NOT remove words such as:
        Ltd
        Sdn Bhd
        LLC

    because these can be important parts of company names.
    """

    value = normalize_text(value)

    if value is None:
        return None

    # Convert & to and
    value = value.replace(
        "&",
        "and"
    )

    # Normalize punctuation
    value = re.sub(
        r"[.,]+",
        " ",
        value
    )

    # Normalize spaces
    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


# ============================================================
# 9. PORT NORMALIZATION
# ============================================================

def normalize_port(value: Any) -> Optional[str]:
    """
    Normalize port names.

    Example:

        NANTONG, CHINA (CNNTG)
        ->
        nantong, china

    This prevents a location code such as (CNNTG) from
    causing a false mismatch.
    """

    value = normalize_text(value)

    if value is None:
        return None

    # Remove "port of"
    value = re.sub(
        r"^port of\s+",
        "",
        value
    )

    # Remove location codes in brackets
    value = re.sub(
        r"\s*\([a-z0-9]{4,6}\)\s*$",
        "",
        value
    )

    # Remove extra spaces
    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


# ============================================================
# 10. CONTAINER COUNT NORMALIZATION
# ============================================================

def normalize_container_count(
    value: Any
) -> Optional[int]:
    """
    Extract the number of containers.

    Examples:

        "6"
        -> 6

        "6 containers"
        -> 6

        "6 x 40'HC"
        -> 6

        "No. of containers: 4"
        -> 4
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    # Find the first integer
    match = re.search(
        r"\b\d+\b",
        value
    )

    if not match:
        return None

    try:

        count = int(
            match.group()
        )

        if count < 0:
            return None

        return count

    except ValueError:

        return None


# ============================================================
# 11. GROSS WEIGHT NORMALIZATION
# ============================================================

def normalize_weight(
    value: Any
) -> Optional[float]:
    """
    Convert gross weight into kilograms.

    Examples:

        "131,058 KG"
        -> 131058.0

        "131058 kilograms"
        -> 131058.0

        "131058"
        -> 131058.0
    """

    if value is None:
        return None

    value = str(value).strip().lower()

    if not value:
        return None

    # Remove commas
    value = value.replace(
        ",",
        ""
    )

    # Remove units
    value = value.replace(
        "kilograms",
        ""
    )

    value = value.replace(
        "kilogram",
        ""
    )

    value = value.replace(
        "kgs",
        ""
    )

    value = value.replace(
        "kg",
        ""
    )

    # Remove spaces
    value = value.replace(
        " ",
        ""
    )

    # Find numeric value
    match = re.search(
        r"\d+(?:\.\d+)?",
        value
    )

    if not match:
        return None

    try:

        return float(
            match.group()
        )

    except ValueError:

        return None


# ============================================================
# 12. NORMALIZE VALUE BASED ON FIELD
# ============================================================

def normalize_value(
    field: str,
    value: Any
) -> Any:

    if value is None:
        return None

    if field == "gross_weight":

        return normalize_weight(
            value
        )

    elif field == "container_count":

        return normalize_container_count(
            value
        )

    elif field in [
        "port_of_loading",
        "port_of_discharge"
    ]:

        return normalize_port(
            value
        )

    elif field in [
        "shipper",
        "consignee",
        "notify_party"
    ]:

        return normalize_name(
            value
        )

    return normalize_text(
        value
    )


# ============================================================
# 13. GET FIELD VALUE
# ============================================================

def get_field_value(
    document: Dict[str, Any],
    field: str
) -> Any:
    """
    Find a field using its standard name or aliases.
    """

    if field in document:
        return document[field]

    aliases = FIELD_ALIASES.get(
        field,
        []
    )

    normalized_document = {}

    for key, value in document.items():

        normalized_key = normalize_label(
            key
        )

        normalized_document[
            normalized_key
        ] = value

    for alias in aliases:

        normalized_alias = normalize_label(
            alias
        )

        if normalized_alias in normalized_document:

            return normalized_document[
                normalized_alias
            ]

    return None


# ============================================================
# 14. EXTRACTION VALUE + CONFIDENCE
# ============================================================

def extract_value_and_confidence(
    document: Dict[str, Any],
    field: str
):
    """
    Supports:

        "shipper": "ABC Company"

    and:

        "shipper": {
            "value": "ABC Company",
            "confidence": 0.95
        }
    """

    raw_value = get_field_value(
        document,
        field
    )

    if raw_value is None:
        return None, None

    # Advanced format
    if isinstance(
        raw_value,
        dict
    ):

        value = raw_value.get(
            "value"
        )

        confidence = raw_value.get(
            "confidence"
        )

        return value, confidence

    # Simple format
    return raw_value, None


# ============================================================
# 15. CONFIDENCE CHECK
# ============================================================

CONFIDENCE_THRESHOLD = 0.80


def is_low_confidence(
    confidence: Any
) -> bool:

    if confidence is None:
        return False

    try:

        confidence = float(
            confidence
        )

        return (
            confidence
            < CONFIDENCE_THRESHOLD
        )

    except (
        ValueError,
        TypeError
    ):

        return True


# ============================================================
# 16. COMPARE ONE FIELD
# ============================================================

def compare_field(
    field: str,
    si_value: Any,
    bl_value: Any,
    si_confidence: Optional[float] = None,
    bl_confidence: Optional[float] = None
) -> Dict[str, Any]:

    normalized_si = normalize_value(
        field,
        si_value
    )

    normalized_bl = normalize_value(
        field,
        bl_value
    )

    # --------------------------------------------------------
    # Missing / unreadable
    # --------------------------------------------------------

    if (
        normalized_si is None
        or normalized_bl is None
    ):

        missing_side = []

        if normalized_si is None:
            missing_side.append(
                "SI"
            )

        if normalized_bl is None:
            missing_side.append(
                "BL"
            )

        return {

            "status": "REVIEW",

            "field": field,

            "si_value": si_value,

            "bl_value": bl_value,

            "normalized_si": normalized_si,

            "normalized_bl": normalized_bl,

            "si_confidence": si_confidence,

            "bl_confidence": bl_confidence,

            "reason":
                "Missing or unreadable value in: "
                + ", ".join(
                    missing_side
                )
        }

    # --------------------------------------------------------
    # Low extraction confidence
    # --------------------------------------------------------

    if (
        is_low_confidence(
            si_confidence
        )
        or
        is_low_confidence(
            bl_confidence
        )
    ):

        return {

            "status": "REVIEW",

            "field": field,

            "si_value": si_value,

            "bl_value": bl_value,

            "normalized_si": normalized_si,

            "normalized_bl": normalized_bl,

            "si_confidence": si_confidence,

            "bl_confidence": bl_confidence,

            "reason":
                "Extraction confidence is below threshold."
        }

    # --------------------------------------------------------
    # MATCH
    # --------------------------------------------------------

    if normalized_si == normalized_bl:

        return {

            "status": "MATCH",

            "field": field,

            "si_value": si_value,

            "bl_value": bl_value,

            "normalized_si": normalized_si,

            "normalized_bl": normalized_bl,

            "si_confidence": si_confidence,

            "bl_confidence": bl_confidence,

            "reason":
                "SI and BL values match."
        }

    # --------------------------------------------------------
    # MISMATCH
    # --------------------------------------------------------

    return {

        "status": "MISMATCH",

        "field": field,

        "si_value": si_value,

        "bl_value": bl_value,

        "normalized_si": normalized_si,

        "normalized_bl": normalized_bl,

        "si_confidence": si_confidence,

        "bl_confidence": bl_confidence,

        "reason":
            "SI and BL values are different."
    }


# ============================================================
# 17. COMPARE ALL 7 FIELDS
# ============================================================

def compare_documents(
    si: Dict[str, Any],
    bl: Dict[str, Any]
) -> Dict[str, Any]:

    mismatches = []

    review_fields = []

    field_results = {}

    for field in FIELDS:

        si_value, si_confidence = (
            extract_value_and_confidence(
                si,
                field
            )
        )

        bl_value, bl_confidence = (
            extract_value_and_confidence(
                bl,
                field
            )
        )

        result = compare_field(
            field=field,
            si_value=si_value,
            bl_value=bl_value,
            si_confidence=si_confidence,
            bl_confidence=bl_confidence
        )

        field_results[
            field
        ] = result

        # ----------------------------------------------------
        # Mismatch
        # ----------------------------------------------------

        if result["status"] == "MISMATCH":

            mismatches.append({

                "field": field,

                "si_value": si_value,

                "bl_value": bl_value,

                "normalized_si":
                    result["normalized_si"],

                "normalized_bl":
                    result["normalized_bl"]
            })

        # ----------------------------------------------------
        # Review
        # ----------------------------------------------------

        elif result["status"] == "REVIEW":

            review_fields.append({

                "field": field,

                "reason":
                    result["reason"]
            })

    # ========================================================
    # FINAL DECISION
    # ========================================================

    # Human review has priority
    if review_fields:

        decision = "HUMAN_REVIEW"

        confidence = "LOW"

        reason = (
            "One or more required fields are "
            "missing, unreadable, or uncertain."
        )

    elif mismatches:

        decision = "MISMATCH"

        confidence = "HIGH"

        reason = (
            f"{len(mismatches)} required field(s) "
            "differ between the SI and BL."
        )

    else:

        decision = "MATCH"

        confidence = "HIGH"

        reason = "No mismatch detected."

    return {

        "decision": decision,

        "confidence": confidence,

        "mismatch":
            len(mismatches) > 0,

        "mismatches":
            mismatches,

        "review_fields":
            review_fields,

        "reason":
            reason,

        "field_results":
            field_results
    }


# ============================================================
# 18. PRINT RESULT
# ============================================================

def print_result(
    result: Dict[str, Any]
):

    print("\n")
    print(
        "============================================================"
    )

    print(
        "FINAL VERIFICATION RESULT"
    )

    print(
        "============================================================"
    )

    print(
        f"\nDecision: "
        f"{result['decision']}"
    )

    print(
        f"Confidence: "
        f"{result['confidence']}"
    )

    print(
        f"Reason: "
        f"{result['reason']}"
    )

    print(
        f"\nMismatch: "
        f"{result['mismatch']}"
    )

    # --------------------------------------------------------
    # Mismatches
    # --------------------------------------------------------

    print("\nMismatches:")

    if result["mismatches"]:

        for mismatch in result[
            "mismatches"
        ]:

            print(
                f"\n- {mismatch['field']}"
            )

            print(
                f"  SI = "
                f"{mismatch['si_value']}"
            )

            print(
                f"  BL = "
                f"{mismatch['bl_value']}"
            )

    else:

        print(
            "- None"
        )

    # --------------------------------------------------------
    # Review fields
    # --------------------------------------------------------

    print(
        "\nReview fields:"
    )

    if result["review_fields"]:

        for review in result[
            "review_fields"
        ]:

            print(
                f"- {review['field']}: "
                f"{review['reason']}"
            )

    else:

        print(
            "- None"
        )


# ============================================================
# 19. TEST REAL HACKATHON DOCUMENTS
# ============================================================

def test_real_documents(
    si_file: str,
    bl_file: str
):

    print("\n")
    print(
        "============================================================"
    )

    print(
        "REAL HACKATHON DOCUMENT TEST"
    )

    print(
        "============================================================"
    )

    print(
        f"\nSI file:\n{si_file}"
    )

    print(
        f"\nBL file:\n{bl_file}"
    )

    # --------------------------------------------------------
    # Read SI
    # --------------------------------------------------------

    si_text = read_text_file(
        si_file
    )

    # --------------------------------------------------------
    # Read BL
    # --------------------------------------------------------

    bl_text = read_text_file(
        bl_file
    )

    if (
        si_text is None
        or bl_text is None
    ):

        return

    # --------------------------------------------------------
    # Extract SI
    # --------------------------------------------------------

    si = extract_fields_from_text(
        si_text
    )

    # --------------------------------------------------------
    # Extract BL
    # --------------------------------------------------------

    bl = extract_fields_from_text(
        bl_text
    )

    # --------------------------------------------------------
    # Display SI extraction
    # --------------------------------------------------------

    print(
        "\n-------------------- EXTRACTED SI --------------------"
    )

    for field in FIELDS:

        value = si.get(
            field,
            None
        )

        if value is None:
            value = "[NOT FOUND]"

        print(
            f"{field}: {value}"
        )

    # --------------------------------------------------------
    # Display BL extraction
    # --------------------------------------------------------

    print(
        "\n-------------------- EXTRACTED BL --------------------"
    )

    for field in FIELDS:

        value = bl.get(
            field,
            None
        )

        if value is None:
            value = "[NOT FOUND]"

        print(
            f"{field}: {value}"
        )

    # --------------------------------------------------------
    # Compare
    # --------------------------------------------------------

    result = compare_documents(
        si,
        bl
    )

    # --------------------------------------------------------
    # Print final result
    # --------------------------------------------------------

    print_result(
        result
    )


# ============================================================
# 20. RUN
# ============================================================

if __name__ == "__main__":

    # Your current VS Code working directory is:
    #
    # C:\Users\User\Documents\MonashHack
    #
    # Therefore we include "download2" in the path.

    si_file = os.path.join(
        "download2",
        "attachments",
        "email_004_SI.txt"
    )

    bl_file = os.path.join(
        "download2",
        "attachments",
        "email_004_BL.txt"
    )

    test_real_documents(
        si_file,
        bl_file
    )