import re
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
    "gross_weight_kg"
]


# ============================================================
# 2. NORMALIZATION
# ============================================================

def normalize_text(value: Any) -> Optional[str]:
    """
    General text normalization.

    Example:
        "  ABC   Trading Sdn Bhd  "
        ->
        "abc trading sdn bhd"
    """

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    value = value.lower()

    # Normalize multiple spaces
    value = re.sub(r"\s+", " ", value)

    # Remove unnecessary punctuation at the edges
    value = value.strip(" ,.;:")

    return value


# ============================================================
# 3. NAME NORMALIZATION
# ============================================================

def normalize_name(value: Any) -> Optional[str]:
    """
    Conservative normalization for company/person names.

    We do not remove words such as Ltd, LLC, Sdn Bhd, etc.
    because they may be meaningful parts of the name.
    """

    value = normalize_text(value)

    if value is None:
        return None

    # Treat & and "and" consistently
    value = value.replace("&", "and")

    # Normalize punctuation
    value = re.sub(r"[.,]+", " ", value)

    # Normalize spaces again
    value = re.sub(r"\s+", " ", value)

    return value.strip()


# ============================================================
# 4. PORT NORMALIZATION
# ============================================================

def normalize_port(value: Any) -> Optional[str]:
    """
    Normalize port names.

    Example:
        "NANTONG, CHINA (CNNTG)"
        ->
        "nantong, china"
    """

    value = normalize_text(value)

    if value is None:
        return None

    # Remove "port of" at the beginning
    value = re.sub(
        r"^port of\s+",
        "",
        value
    )

    # Remove port/location codes in brackets
    value = re.sub(
        r"\s*\([a-z0-9]{4,6}\)\s*$",
        "",
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
# 5. CONTAINER COUNT NORMALIZATION
# ============================================================

def normalize_container_count(
    value: Any
) -> Optional[int]:
    """
    Convert container count into an integer.

    Examples:
        "6"            -> 6
        "6 containers" -> 6
        "6 x 40'HC"   -> 6
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

        count = int(match.group())

        if count < 0:
            return None

        return count

    except ValueError:

        return None


# ============================================================
# 6. GROSS WEIGHT NORMALIZATION
# ============================================================

def normalize_weight(
    value: Any
) -> Optional[float]:
    """
    Normalize gross weight into kilograms.

    Examples:
        "131,058 KG"       -> 131058.0
        "131058 kilograms" -> 131058.0
        "131058"           -> 131058.0
    """

    if value is None:
        return None

    value = str(value).strip().lower()

    if not value:
        return None

    # Remove commas
    value = value.replace(",", "")

    # Remove common units
    value = value.replace("kilograms", "")
    value = value.replace("kilogram", "")
    value = value.replace("kgs", "")
    value = value.replace("kg", "")

    # Remove spaces
    value = value.replace(" ", "")

    # Extract numeric value
    match = re.search(
        r"\d+(?:\.\d+)?",
        value
    )

    if not match:
        return None

    try:

        return float(match.group())

    except ValueError:

        return None


# ============================================================
# 7. FIELD NORMALIZATION
# ============================================================

def normalize_value(
    field: str,
    value: Any
) -> Any:
    """
    Apply the appropriate normalization based on field type.
    """

    if value is None:
        return None

    if field == "gross_weight_kg":

        return normalize_weight(value)

    elif field == "container_count":

        return normalize_container_count(value)

    elif field in [
        "port_of_loading",
        "port_of_discharge"
    ]:

        return normalize_port(value)

    elif field in [
        "shipper",
        "consignee",
        "notify_party"
    ]:

        return normalize_name(value)

    return normalize_text(value)


# ============================================================
# 8. COMPARE ONE FIELD
# ============================================================

def compare_field(
    field: str,
    si_value: Any,
    bl_value: Any
) -> Dict[str, Any]:
    """
    Compare one field between SI and BL.
    """

    normalized_si = normalize_value(
        field,
        si_value
    )

    normalized_bl = normalize_value(
        field,
        bl_value
    )

    # --------------------------------------------------------
    # Missing value
    # --------------------------------------------------------

    if (
        normalized_si is None
        or normalized_bl is None
    ):

        missing_side = []

        if normalized_si is None:
            missing_side.append("SI")

        if normalized_bl is None:
            missing_side.append("BL")

        return {
            "status": "NEEDS_REVIEW",
            "review_reason": "missing_value",

            "field": field,

            "si_value": si_value,
            "bl_value": bl_value,

            "normalized_si": normalized_si,
            "normalized_bl": normalized_bl,

            "reason":
                "Missing or unreadable value in: "
                + ", ".join(missing_side)
        }

    # --------------------------------------------------------
    # Values match
    # --------------------------------------------------------

    if normalized_si == normalized_bl:

        return {
            "status": "OK",
            "review_reason": None,

            "field": field,

            "si_value": si_value,
            "bl_value": bl_value,

            "normalized_si": normalized_si,
            "normalized_bl": normalized_bl,

            "reason": "SI and BL values match."
        }

    # --------------------------------------------------------
    # Values mismatch
    # --------------------------------------------------------

    return {
        "status": "MISMATCH",
        "review_reason": None,

        "field": field,

        "si_value": si_value,
        "bl_value": bl_value,

        "normalized_si": normalized_si,
        "normalized_bl": normalized_bl,

        "reason": "SI and BL values are different."
    }


# ============================================================
# 9. COMPARE SI AGAINST BL
# ============================================================

def compare_documents(
    si: Dict[str, Any],
    bl: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Compare the seven required fields.

    IMPORTANT:
    This function assumes extraction/OCR has already happened.

    Input example:

        si = {
            "shipper": "...",
            "consignee": "...",
            ...
            "gross_weight_kg": "22000 KG"
        }

    No document extraction is performed here.
    """

    mismatches = []
    review_fields = []
    field_results = {}

    # --------------------------------------------------------
    # Compare all seven fields
    # --------------------------------------------------------

    for field in FIELDS:

        si_value = si.get(field)

        bl_value = bl.get(field)

        result = compare_field(
            field=field,
            si_value=si_value,
            bl_value=bl_value
        )

        field_results[field] = result

        # Store mismatches
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

        # Store review fields
        elif result["status"] == "NEEDS_REVIEW":

            review_fields.append({
                "field": field,

                "reason":
                    result["review_reason"]
            })

    # ========================================================
    # FINAL STATUS
    # ========================================================

    # Human review takes priority
    if review_fields:

        status = "NEEDS_REVIEW"

        reason = review_fields[0]["reason"]

    # Mismatch exists
    elif mismatches:

        status = "MISMATCH"

        reason = None

    # Everything matches
    else:

        status = "OK"

        reason = None

    # ========================================================
    # FINAL RESULT
    # ========================================================

    return {
        "status": status,

        "review_reason": reason,

        "mismatch": len(mismatches) > 0,

        "mismatches": mismatches,

        "review_fields": review_fields,

        "field_results": field_results
    }


# ============================================================
# 10. PRINT RESULT
# ============================================================

def print_result(
    result: Dict[str, Any]
):

    print("\n")
    print(
        "============================================================"
    )

    print(
        "VERIFICATION RESULT"
    )

    print(
        "============================================================"
    )

    print(
        f"\nStatus: {result['status']}"
    )

    if result["review_reason"]:

        print(
            f"Review reason: "
            f"{result['review_reason']}"
        )

    # --------------------------------------------------------
    # Mismatches
    # --------------------------------------------------------

    print("\nMismatches:")

    if result["mismatches"]:

        for mismatch in result["mismatches"]:

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

        print("- None")

    # --------------------------------------------------------
    # Review fields
    # --------------------------------------------------------

    print("\nReview fields:")

    if result["review_fields"]:

        for review in result["review_fields"]:

            print(
                f"- {review['field']}: "
                f"{review['reason']}"
            )

    else:

        print("- None")


# ============================================================
# 11. TESTING
# ============================================================
# This is only for testing your verification module.
# Your teammate's extraction/OCR module will eventually
# provide the SI and BL dictionaries instead.

def run_test():

    si = {
        "shipper":
            "APRIL FAR EAST (M) SDN BHD",

        "consignee":
            "EAST BRIGHT FZ-LLC",

        "notify_party":
            "EAST BRIGHT FZ-LLC",

        "port_of_loading":
            "NANTONG, CHINA (CNNTG)",

        "port_of_discharge":
            "KARACHI, PAKISTAN (PKKHI)",

        "container_count":
            "6 x 40'HC",

        "gross_weight_kg":
            "131,058 KG"
    }

    bl = {
        "shipper":
            "APRIL FAR EAST (M) SDN BHD",

        "consignee":
            "UAB NOVAKOPA",

        "notify_party":
            "UAB NOVAKOPA",

        "port_of_loading":
            "NANTONG, CHINA (CNNTG)",

        "port_of_discharge":
            "KARACHI, PAKISTAN (PKKHI)",

        "container_count":
            "6 x 40'HC",

        "gross_weight_kg":
            "131058 KG"
    }

    result = compare_documents(
        si,
        bl
    )

    print_result(
        result
    )


# ============================================================
# 12. RUN
# ============================================================

if __name__ == "__main__":

    run_test()