"""Tests for branch extraction."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import uproot

from rootmltool.extract import extract_branches
from rootmltool.schemas import ExtractionRequest, FilterCondition


def _create_synthetic_root(path: Path) -> None:
    with uproot.recreate(path) as root_file:
        root_file["Events"] = {
            "pt": np.array([10.0, 25.0, 45.0], dtype=np.float32),
            "eta": np.array([0.1, -1.2, 0.4], dtype=np.float32),
            "charge": np.array([1, -1, 1], dtype=np.int32),
        }


def test_extract_branches_with_filter_returns_expected_shapes(tmp_path: Path) -> None:
    root_path = tmp_path / "synthetic.root"
    _create_synthetic_root(root_path)

    request = ExtractionRequest(
        path=str(root_path),
        tree="Events",
        branches=["pt", "eta"],
        filters=[FilterCondition(branch="pt", op="gt", value=20)],
        output_format="dict",
    )

    result = extract_branches(request)

    assert result.num_events == 2
    assert result.shapes["pt"] == [2]
    assert result.shapes["eta"] == [2]
    assert result.data is not None
    assert result.data["pt"] == [25.0, 45.0]


def test_extract_branches_numpy_format_serializes_lists(tmp_path: Path) -> None:
    root_path = tmp_path / "synthetic.root"
    _create_synthetic_root(root_path)

    request = ExtractionRequest(
        path=str(root_path),
        tree="Events",
        branches=["pt", "charge"],
        output_format="numpy",
    )

    result = extract_branches(request)

    assert result.output_format == "numpy"
    assert result.data is not None
    assert result.data["charge"] == [1, -1, 1]
