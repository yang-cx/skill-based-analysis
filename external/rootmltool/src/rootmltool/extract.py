"""Branch extraction and deterministic transformation pipeline."""

from __future__ import annotations

from typing import Any

import awkward as ak

from .converters import awkward_to_numpy_dict, awkward_to_pandas, awkward_to_parquet
from .exceptions import ExtractionError, RootMLToolError, ValidationError
from .filters import apply_filter_conditions
from .io import read_tree_arrays
from .schemas import ExtractionRequest, ExtractionResult


def _compute_shapes(arrays: ak.Array, branches: list[str]) -> dict[str, list[int]]:
    """Compute simple shape metadata for selected branches."""
    shapes: dict[str, list[int]] = {}
    for branch in branches:
        branch_array = awkward_to_numpy_dict(arrays, [branch])[branch]
        shapes[branch] = [int(dim) for dim in branch_array.shape]
    return shapes


def extract_branches(request: ExtractionRequest | dict[str, Any]) -> ExtractionResult:
    """Extract selected branches from a ROOT tree and convert output format."""
    if isinstance(request, dict):
        request = ExtractionRequest.model_validate(request)

    try:
        arrays = read_tree_arrays(
            path=request.path,
            tree=request.tree,
            branches=request.branches,
            entry_start=request.entry_start,
            entry_stop=request.entry_stop,
        )

        filtered = apply_filter_conditions(arrays, request.filters)

        output_path = request.output_path
        data: dict[str, Any] | None = None

        if request.output_format == "dict":
            if request.include_data:
                data = {branch: ak.to_list(filtered[branch]) for branch in request.branches}

        elif request.output_format == "numpy":
            numpy_data = awkward_to_numpy_dict(filtered, request.branches)
            if request.include_data:
                data = {name: values.tolist() for name, values in numpy_data.items()}

        elif request.output_format == "pandas":
            df = awkward_to_pandas(filtered, request.branches)
            if request.include_data:
                data = df.to_dict(orient="list")

        elif request.output_format == "parquet":
            if not request.output_path:
                raise ValidationError(
                    code="missing_output_path",
                    message="`output_path` is required when output_format is `parquet`.",
                )
            output_path = awkward_to_parquet(filtered, request.output_path)
            if request.include_data:
                data = {"parquet_path": output_path}

        shapes = _compute_shapes(filtered, request.branches)

        return ExtractionResult(
            path=request.path,
            tree=request.tree,
            selected_branches=list(request.branches),
            num_events=int(len(filtered)),
            output_format=request.output_format,
            output_path=output_path,
            shapes=shapes,
            data=data,
            metadata={
                "filters_applied": len(request.filters),
                "entry_start": request.entry_start,
                "entry_stop": request.entry_stop,
            },
        )
    except RootMLToolError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise ExtractionError(
            code="extraction_failed",
            message="Unexpected failure during branch extraction.",
            details={"error": str(exc)},
        ) from exc


# TODO: Add chunked extraction mode for very large TTrees.
