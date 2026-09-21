"""Presentation-facing integration for the interactive prototype."""

from .service import (
    DemoConfigurationError,
    DemoResult,
    DemoRuntime,
    UploadedDocument,
    analyze_email,
    load_demo_runtime,
)

__all__ = [
    "DemoConfigurationError",
    "DemoResult",
    "DemoRuntime",
    "UploadedDocument",
    "analyze_email",
    "load_demo_runtime",
]
