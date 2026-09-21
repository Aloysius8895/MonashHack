"""Tesseract OCR backend, used only for scanned (image-only) PDF pages.

extractors/pdf_extractor.py falls back to this when a page has no usable
text layer. The tesseract binary is resolved explicitly rather than relying
on PATH, because installing it (e.g. via winget) doesn't take effect in an
already-open shell - a teammate's session might not see it on PATH yet even
right after installing.
"""
import shutil
from pathlib import Path

import pytesseract

_CANDIDATE_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]


def _resolve_tesseract_cmd():
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in _CANDIDATE_PATHS:
        if Path(candidate).exists():
            return candidate
    return None


_TESSERACT_CMD = _resolve_tesseract_cmd()
if _TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = _TESSERACT_CMD


def is_available():
    return _TESSERACT_CMD is not None


def ocr_image(image):
    """image: a PIL.Image (e.g. from pdfplumber's page.to_image().original).
    Returns extracted text, or '' if OCR isn't available or fails."""
    if not is_available():
        return ""
    try:
        return pytesseract.image_to_string(image)
    except Exception:
        return ""
