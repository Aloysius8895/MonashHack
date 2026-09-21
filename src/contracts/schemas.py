from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


SCHEMA_VERSION = 1

DOCUMENT_FIELDS = (
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
)

PUBLISHED_CATEGORIES = frozenset(
    {
        "document_comparison",
        "new_si_request",
        "invoice_query",
        "general_message",
        "spam",
    }
)

VERIFICATION_STATUSES = frozenset(
    {"match", "mismatch_detected", "not_verified"}
)

_TEXT_FIELDS = (
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
)


class ContractError(ValueError):
    pass


@dataclass(frozen=True)
class AttachmentPair:
    si: str | None = None
    bl: str | None = None

    def __post_init__(self) -> None:
        for name in ("si", "bl"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ContractError(f"Attachment {name} must be a non-empty string")

    @property
    def is_complete(self) -> bool:
        return self.si is not None and self.bl is not None

    def to_dict(self) -> dict[str, str | None]:
        return {"si": self.si, "bl": self.bl}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> AttachmentPair:
        _require_mapping(payload, "attachments")
        return cls(si=_optional_str(payload.get("si")), bl=_optional_str(payload.get("bl")))


@dataclass(frozen=True)
class ClassificationResult:
    email_id: str
    category: str
    should_compare: bool
    attachments: AttachmentPair = AttachmentPair()

    def __post_init__(self) -> None:
        _require_email_id(self.email_id)
        if self.category not in PUBLISHED_CATEGORIES:
            raise ContractError(f"Unknown published category: {self.category!r}")
        if not isinstance(self.should_compare, bool):
            raise ContractError("Field should_compare must be a boolean")
        if not isinstance(self.attachments, AttachmentPair):
            raise ContractError("Field attachments must be an AttachmentPair")
        if self.should_compare and not self.attachments.is_complete:
            raise ContractError(
                f"{self.email_id} is marked should_compare without both SI and BL paths"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "email_id": self.email_id,
            "category": self.category,
            "should_compare": self.should_compare,
            "attachments": self.attachments.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ClassificationResult:
        _require_mapping(payload, "classification record")
        should_compare = payload.get("should_compare")
        if not isinstance(should_compare, bool):
            raise ContractError("Field should_compare must be a boolean")
        return cls(
            email_id=_required_str(payload.get("email_id"), "email_id"),
            category=_required_str(payload.get("category"), "category"),
            should_compare=should_compare,
            attachments=AttachmentPair.from_dict(payload.get("attachments") or {}),
        )


@dataclass(frozen=True)
class DocumentFields:
    shipper: str | None = None
    consignee: str | None = None
    notify_party: str | None = None
    port_of_loading: str | None = None
    port_of_discharge: str | None = None
    container_count: int | None = None
    gross_weight_kg: float | None = None

    def __post_init__(self) -> None:
        for name in _TEXT_FIELDS:
            value = getattr(self, name)
            if value is not None and not isinstance(value, str):
                raise ContractError(f"Document field {name} must be a string or null")
        if self.container_count is not None:
            if not isinstance(self.container_count, int) or isinstance(
                self.container_count, bool
            ):
                raise ContractError("Field container_count must be an integer or null")
            if self.container_count < 0:
                raise ContractError("Field container_count cannot be negative")
        if self.gross_weight_kg is not None:
            if not isinstance(self.gross_weight_kg, (int, float)) or isinstance(
                self.gross_weight_kg, bool
            ):
                raise ContractError("Field gross_weight_kg must be a number or null")
            if self.gross_weight_kg < 0:
                raise ContractError("Field gross_weight_kg cannot be negative")

    @property
    def missing_fields(self) -> tuple[str, ...]:
        return tuple(name for name in DOCUMENT_FIELDS if getattr(self, name) is None)

    def to_dict(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in DOCUMENT_FIELDS}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> DocumentFields:
        _require_mapping(payload, "document fields")
        unknown = sorted(set(payload) - set(DOCUMENT_FIELDS))
        if unknown:
            raise ContractError(f"Unknown document fields: {', '.join(unknown)}")
        return cls(**{name: payload.get(name) for name in DOCUMENT_FIELDS})


@dataclass(frozen=True)
class ExtractionResult:
    email_id: str
    si: DocumentFields
    bl: DocumentFields

    def __post_init__(self) -> None:
        _require_email_id(self.email_id)
        for name in ("si", "bl"):
            if not isinstance(getattr(self, name), DocumentFields):
                raise ContractError(f"Field {name} must be a DocumentFields instance")

    def to_dict(self) -> dict[str, object]:
        return {
            "email_id": self.email_id,
            "si": self.si.to_dict(),
            "bl": self.bl.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> ExtractionResult:
        _require_mapping(payload, "extraction record")
        return cls(
            email_id=_required_str(payload.get("email_id"), "email_id"),
            si=DocumentFields.from_dict(payload.get("si") or {}),
            bl=DocumentFields.from_dict(payload.get("bl") or {}),
        )


@dataclass(frozen=True)
class FieldMismatch:
    field: str
    si: object
    bl: object

    def __post_init__(self) -> None:
        if self.field not in DOCUMENT_FIELDS:
            raise ContractError(f"Unknown mismatch field: {self.field!r}")

    def to_dict(self) -> dict[str, object]:
        return {"field": self.field, "si": self.si, "bl": self.bl}

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> FieldMismatch:
        _require_mapping(payload, "mismatch record")
        return cls(
            field=_required_str(payload.get("field"), "field"),
            si=payload.get("si"),
            bl=payload.get("bl"),
        )


@dataclass(frozen=True)
class VerificationResult:
    email_id: str
    status: str
    mismatches: tuple[FieldMismatch, ...] = ()
    review_required: bool = False
    review_reason: str | None = None

    def __post_init__(self) -> None:
        _require_email_id(self.email_id)
        if self.status not in VERIFICATION_STATUSES:
            raise ContractError(f"Unknown verification status: {self.status!r}")
        if not isinstance(self.mismatches, tuple) or not all(
            isinstance(item, FieldMismatch) for item in self.mismatches
        ):
            raise ContractError("Field mismatches must be a tuple of FieldMismatch")
        if not isinstance(self.review_required, bool):
            raise ContractError("Field review_required must be a boolean")
        if self.review_reason is not None and not isinstance(self.review_reason, str):
            raise ContractError("Field review_reason must be a string or null")
        if self.review_required and not self.review_reason:
            raise ContractError(
                f"{self.email_id} requires review without a review_reason"
            )
        if self.status == "match" and self.mismatches:
            raise ContractError(f"{self.email_id} reports match with mismatches listed")
        if self.status == "mismatch_detected" and not self.mismatches:
            raise ContractError(
                f"{self.email_id} reports mismatch_detected with no mismatches listed"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "email_id": self.email_id,
            "status": self.status,
            "mismatches": [item.to_dict() for item in self.mismatches],
            "review_required": self.review_required,
            "review_reason": self.review_reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> VerificationResult:
        _require_mapping(payload, "verification record")
        raw_mismatches = payload.get("mismatches") or []
        if not isinstance(raw_mismatches, Sequence) or isinstance(raw_mismatches, str):
            raise ContractError("Field mismatches must be a list")
        review_required = payload.get("review_required", False)
        if not isinstance(review_required, bool):
            raise ContractError("Field review_required must be a boolean")
        return cls(
            email_id=_required_str(payload.get("email_id"), "email_id"),
            status=_required_str(payload.get("status"), "status"),
            mismatches=tuple(FieldMismatch.from_dict(item) for item in raw_mismatches),
            review_required=review_required,
            review_reason=_optional_str(payload.get("review_reason")),
        )


def _require_email_id(value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ContractError("Field email_id must be a non-empty string")


def _require_mapping(payload: object, label: str) -> None:
    if not isinstance(payload, Mapping):
        raise ContractError(f"Expected {label} to be an object")


def _required_str(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(f"Field {label} must be a non-empty string")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ContractError("Optional string fields must be non-empty or null")
    return value
