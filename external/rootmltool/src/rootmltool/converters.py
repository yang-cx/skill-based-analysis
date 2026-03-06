"""Conversion helpers from awkward records to ML-friendly outputs."""

from __future__ import annotations

from pathlib import Path

import awkward as ak
import numpy as np
import pandas as pd

from .exceptions import ConversionError


def awkward_to_numpy_dict(arrays: ak.Array, branches: list[str]) -> dict[str, np.ndarray]:
    """Convert selected awkward fields into numpy arrays."""
    converted: dict[str, np.ndarray] = {}
    for branch in branches:
        try:
            converted[branch] = np.asarray(ak.to_numpy(arrays[branch]))
        except Exception as exc:
            raise ConversionError(
                code="numpy_conversion_failed",
                message="Failed converting awkward branch to numpy.",
                details={"branch": branch, "error": str(exc)},
            ) from exc
    return converted


def awkward_to_pandas(arrays: ak.Array, branches: list[str]) -> pd.DataFrame:
    """Convert selected awkward fields into a pandas DataFrame."""
    try:
        data = {
            branch: np.asarray(ak.to_numpy(arrays[branch]))
            for branch in branches
        }
        return pd.DataFrame(data)
    except Exception as exc:
        raise ConversionError(
            code="pandas_conversion_failed",
            message="Failed converting awkward arrays to pandas DataFrame.",
            details={"branches": branches, "error": str(exc)},
        ) from exc


# TODO: Add configurable jagged-array flattening strategy for dataframe export.


def awkward_to_parquet(arrays: ak.Array, output_path: str) -> str:
    """Write awkward records to parquet using pyarrow."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - dependency-specific
        raise ConversionError(
            code="missing_pyarrow",
            message="Parquet export requires optional dependency `pyarrow`.",
            details={"output_path": output_path},
        ) from exc

    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        serializable = {field: ak.to_list(arrays[field]) for field in arrays.fields}
        table = pa.table(serializable)
        pq.write_table(table, path)
    except Exception as exc:
        raise ConversionError(
            code="parquet_conversion_failed",
            message="Failed writing arrays to parquet.",
            details={"output_path": str(path), "error": str(exc)},
        ) from exc

    return str(path)
