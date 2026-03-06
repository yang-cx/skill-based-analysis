"""I/O abstraction for ROOT file access.

This module currently uses `uproot` and is intentionally isolated so a future
C++ ROOT backend can be introduced without changing higher-level modules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import awkward as ak
import uproot

from .exceptions import FileAccessError, ValidationError


def strip_cycle_suffix(key: str) -> str:
    """Return ROOT object key without cycle suffix (e.g. `Events;1` -> `Events`)."""
    return key.split(";")[0]


def validate_existing_file(path: str) -> Path:
    """Validate that path points to an existing file."""
    if not isinstance(path, str) or not path.strip():
        raise ValidationError(
            code="invalid_path",
            message="`path` must be a non-empty string.",
            details={"path": path},
        )

    file_path = Path(path).expanduser().resolve()
    if not file_path.exists() or not file_path.is_file():
        raise FileAccessError(
            code="file_not_found",
            message="ROOT file does not exist.",
            details={"path": str(file_path)},
        )
    return file_path


def open_root_file(path: str) -> Any:
    """Open a ROOT file using uproot."""
    file_path = validate_existing_file(path)
    try:
        return uproot.open(file_path)
    except Exception as exc:  # pragma: no cover - exact uproot errors vary
        raise FileAccessError(
            code="open_failed",
            message="Failed to open ROOT file with uproot.",
            details={"path": str(file_path), "error": str(exc)},
        ) from exc


def _resolve_tree_key(file_handle: Any, tree_name: str) -> str:
    """Resolve a user-provided tree name to a concrete ROOT key."""
    normalized = tree_name.strip()
    for key in file_handle.keys():
        if strip_cycle_suffix(key) == normalized:
            return key

    raise FileAccessError(
        code="tree_not_found",
        message="Requested tree is not present in ROOT file.",
        details={"tree": tree_name},
    )


def read_tree_arrays(
    path: str,
    tree: str,
    branches: list[str],
    entry_start: int | None = None,
    entry_stop: int | None = None,
) -> ak.Array:
    """Read selected branches from a ROOT tree into an awkward array record."""
    if not branches:
        raise ValidationError(
            code="empty_branches",
            message="At least one branch must be requested.",
            details={"branches": branches},
        )

    with open_root_file(path) as file_handle:
        tree_key = _resolve_tree_key(file_handle, tree)
        tree_obj = file_handle[tree_key]

        available = {str(name) for name in tree_obj.keys()}
        missing = sorted(set(branches) - available)
        if missing:
            raise ValidationError(
                code="missing_branches",
                message="Some requested branches are not available.",
                details={"missing": missing, "available_count": len(available)},
            )

        try:
            return tree_obj.arrays(
                branches,
                library="ak",
                entry_start=entry_start,
                entry_stop=entry_stop,
            )
        except Exception as exc:  # pragma: no cover - backend-specific failure
            raise FileAccessError(
                code="read_failed",
                message="Failed reading tree arrays from ROOT file.",
                details={"tree": tree, "error": str(exc)},
            ) from exc


# TODO: Add backend adapter interface for optional ROOT C++-based readers.
