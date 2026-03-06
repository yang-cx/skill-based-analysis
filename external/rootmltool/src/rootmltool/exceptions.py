"""Structured exception types used throughout rootmltool."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RootMLToolError(Exception):
    """Base exception with machine-readable error details."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable error payload."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ValidationError(RootMLToolError):
    """Raised when input contracts are violated."""


class FileAccessError(RootMLToolError):
    """Raised when ROOT files cannot be opened or read."""


class InspectionError(RootMLToolError):
    """Raised when file inspection fails unexpectedly."""


class ExtractionError(RootMLToolError):
    """Raised when branch extraction fails unexpectedly."""


class ConversionError(RootMLToolError):
    """Raised when conversion/export operations fail."""
