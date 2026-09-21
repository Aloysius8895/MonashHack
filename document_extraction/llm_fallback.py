"""Local LLM fallback for fields the deterministic extractor couldn't find
at all (i.e. no known alias/keyword matched any label in the document).

This is deliberately narrow: it's not a replacement for fields.py's
alias/keyword matching, and it's never asked to re-check a field that was
already found (even if flagged missing_value or garbled) - only fields
that classify_label() had nothing to say about. That matters if the
organizers introduce label wording we haven't seen, e.g. "Origin Port"
instead of any of the "Port of Loading" variants already in ALIASES - a
keyword rule can't recognize that as the same field, but an LLM can align
it by meaning.

Talks to a local Ollama server over plain HTTP (stdlib urllib, same style
as download2/loader.py) so this stays free and works offline - no extra
Python package, no API key. If Ollama isn't running, is_available() says
so and the caller just leaves those fields missing, same as any other
extraction gap.
"""
import json
import urllib.error
import urllib.request

MODEL_NAME = "qwen2.5:7b"

_OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
_OLLAMA_GENERATE_URL = "http://localhost:11434/api/generate"
_AVAILABILITY_TIMEOUT = 3
_GENERATE_TIMEOUT = 60

FIELD_DESCRIPTIONS = {
    "shipper": "the exporter/seller sending the goods (may be labeled Shipper, "
    "Shipper/Exporter, or Shipper (Principal or Seller))",
    "consignee": "the party receiving the goods (may be labeled Consignee, "
    "Consignee (Non-Negotiable), or To the Order of)",
    "notify_party": "the party to notify on arrival (may be labeled Notify, "
    "Notify Party, or Notify Party/Intermediate Consignee)",
    "port_of_loading": "the port where the cargo is loaded (may be labeled "
    "Port of Loading, POL, or Load Port)",
    "port_of_discharge": "the port where the cargo is unloaded (may be labeled "
    "Port of Discharge, POD, or Discharge Port)",
    "container_count": "the number of containers, usually written like "
    "\"6 x 40'HC\" (may be labeled No. of Containers, Total Containers, or "
    "Container Count)",
    "gross_weight_kg": "the total GROSS weight in kilograms - NOT net weight "
    "(may be labeled Gross Weight or Gross Wt (kgs))",
}


def is_available():
    try:
        with urllib.request.urlopen(_OLLAMA_TAGS_URL, timeout=_AVAILABILITY_TIMEOUT) as resp:
            return resp.status == 200
    except Exception:
        return False


def find_missing_fields(document_text, missing_field_names):
    """Ask the LLM to find only the given fields in document_text.

    Returns {field_name: raw_value} for whatever it found - fields it
    couldn't find, or any failure (Ollama down, timeout, bad JSON), are
    just absent from the result. Never raises.
    """
    if not missing_field_names:
        return {}

    field_list = "\n".join(
        f'- "{name}": {FIELD_DESCRIPTIONS[name]}' for name in missing_field_names
    )
    prompt = (
        "You are extracting fields from a shipping document (a Shipping "
        "Instruction or a Bill of Lading). Below is the document text, "
        "followed by a list of fields to find. For each field, return the "
        "value EXACTLY as written in the document - do not paraphrase, "
        "translate, or reformat it. If a field genuinely does not appear "
        "anywhere in the document, return null for it. Never guess or "
        "invent a value that isn't in the text.\n\n"
        f"Fields to find:\n{field_list}\n\n"
        "Document text:\n-----\n"
        f"{document_text}\n"
        "-----\n\n"
        "Respond with a JSON object mapping each field name above to its "
        "value (a string) or null."
    )

    payload = json.dumps(
        {
            "model": MODEL_NAME,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0},
        }
    ).encode("utf-8")

    try:
        request = urllib.request.Request(
            _OLLAMA_GENERATE_URL, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=_GENERATE_TIMEOUT) as response:
            body = json.loads(response.read())
        result = json.loads(body["response"])
    except Exception:
        return {}

    if not isinstance(result, dict):
        return {}
    return {
        name: result[name]
        for name in missing_field_names
        if result.get(name)
    }
