"""ROOT file inspection helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .exceptions import InspectionError, RootMLToolError
from .io import open_root_file, strip_cycle_suffix
from .schemas import BranchSummary, RootFileSummary, TreeSummary
from .semantics import infer_physics_meaning


def _is_tree_object(obj: Any) -> bool:
    """Return True if the object behaves like a TTree in uproot."""
    return hasattr(obj, "num_entries") and hasattr(obj, "keys")


def inspect_root_file(path: str) -> RootFileSummary:
    """Inspect a ROOT file and summarize trees/branches.

    Parameters
    ----------
    path:
        Filesystem path to a ROOT file.

    Returns
    -------
    RootFileSummary
        Structured summary of ROOT contents.
    """
    try:
        with open_root_file(path) as file_handle:
            tree_summaries: list[TreeSummary] = []
            warnings: list[str] = []

            for raw_key in file_handle.keys():
                obj = file_handle[raw_key]
                if not _is_tree_object(obj):
                    continue

                branches: list[BranchSummary] = []
                for branch_name in obj.keys():
                    branch_obj = obj[branch_name]
                    interpretation = getattr(branch_obj, "interpretation", None)
                    dtype = str(getattr(branch_obj, "typename", "unknown"))
                    inferred = infer_physics_meaning(str(branch_name), dtype)
                    branches.append(
                        BranchSummary(
                            name=str(branch_name),
                            dtype=dtype,
                            interpretation=str(interpretation) if interpretation else None,
                            title=getattr(branch_obj, "title", None),
                            physics_meaning=inferred["physics_meaning"],
                            physics_category=inferred["physics_category"],
                            physics_units=inferred["physics_units"],
                            physics_confidence=inferred["physics_confidence"],
                            inference_source=inferred["inference_source"],
                        )
                    )

                tree_summaries.append(
                    TreeSummary(
                        name=strip_cycle_suffix(str(raw_key)),
                        num_entries=int(obj.num_entries),
                        branches=branches,
                        metadata={
                            "num_branches": len(branches),
                            "classname": str(getattr(obj, "classname", "")),
                        },
                    )
                )

            if not tree_summaries:
                warnings.append("no_ttrees_found")

            return RootFileSummary(
                path=str(Path(path).expanduser().resolve()),
                trees=tree_summaries,
                metadata={
                    "num_trees": len(tree_summaries),
                    "backend": "uproot",
                    "warnings": warnings,
                },
            )
    except RootMLToolError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise InspectionError(
            code="inspection_failed",
            message="Unexpected failure during ROOT inspection.",
            details={"path": path, "error": str(exc)},
        ) from exc


# TODO: Add histogram/object summary support beyond TTree metadata.
