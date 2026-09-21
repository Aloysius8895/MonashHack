from .adapter import AttachmentDocumentExtractor
from .fields import CANONICAL_FIELDS

__all__ = [
    "AttachmentDocumentExtractor",
    "CANONICAL_FIELDS",
    "DocumentExtraction",
    "FieldExtraction",
    "extract_from_bytes",
    "extract_pair",
    "to_contract_shape",
]

_LAZY = {
    "DocumentExtraction": ".extract",
    "FieldExtraction": ".extract",
    "extract_from_bytes": ".extract",
    "extract_pair": ".contract",
    "to_contract_shape": ".contract",
}


def __getattr__(name):
    # The format extractors import pdfplumber/python-docx/openpyxl at module
    # level. Resolving these on first use keeps `import document_extraction`
    # working when only the adapter is needed.
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    return getattr(import_module(module_name, __name__), name)


def __dir__():
    return sorted(__all__)
