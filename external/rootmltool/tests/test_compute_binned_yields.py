"""Tests for deterministic per-region binned yield computation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError

from rootmltool.binned_yields import compute_binned_yields
from rootmltool.schemas import ComputeBinnedYieldsRequest
from rootmltool.tool_entrypoint import run_tool


def _write_convert_output(
    path: Path,
    *,
    process: str = "ttbar",
    data: dict | None = None,
    weights: list[float] | None = None,
) -> Path:
    payload = {
        "process": process,
        "n_events": 4,
        "data": data
        or {
            "pt": [10.0, 20.0, 30.0, 40.0],
            "eta": [0.1, 1.0, -1.3, 2.0],
        },
        "weights": weights,
        "metadata": {
            "source_files": ["/tmp/mock.root"],
            "tree_name": "Events",
            "preselection": None,
            "backend": "uproot",
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_compute_binned_yields_single_region_unweighted(tmp_path: Path) -> None:
    input_array = _write_convert_output(tmp_path / "arrays.json", weights=None)

    result = compute_binned_yields(
        {
            "analysis_version": "ana-v1",
            "process": "ttbar",
            "is_data": False,
            "input_array_path": str(input_array),
            "regions": {
                "SR": {
                    "cut": "abs(eta) < 1.5",
                    "observable": "pt",
                    "bin_edges": [0.0, 20.0, 40.0, 60.0],
                }
            },
        }
    )

    assert result.schema_version == "1.0"
    assert result.analysis_version == "ana-v1"
    assert result.metadata["n_events_processed"] == 4
    assert result.regions["SR"].yields == [1.0, 2.0, 0.0]


def test_compute_binned_yields_single_region_weighted(tmp_path: Path) -> None:
    input_array = _write_convert_output(
        tmp_path / "arrays_weighted.json",
        weights=[1.0, 0.5, 2.0, 3.0],
    )

    result = compute_binned_yields(
        {
            "analysis_version": "ana-v2",
            "process": "ttbar",
            "is_data": False,
            "input_array_path": str(input_array),
            "regions": {
                "SR": {
                    "cut": "pt >= 20",
                    "observable": "pt",
                    "bin_edges": [0.0, 25.0, 50.0],
                }
            },
        }
    )

    assert result.regions["SR"].yields == [0.5, 5.0]


def test_compute_binned_yields_multiple_regions(tmp_path: Path) -> None:
    input_array = _write_convert_output(tmp_path / "arrays_multi.json", weights=None)

    result = compute_binned_yields(
        {
            "analysis_version": "ana-v3",
            "process": "ttbar",
            "is_data": False,
            "input_array_path": str(input_array),
            "regions": {
                "Central": {
                    "cut": "abs(eta) < 1.5",
                    "observable": "pt",
                    "bin_edges": [0.0, 25.0, 50.0],
                },
                "Forward": {
                    "cut": "abs(eta) >= 1.5",
                    "observable": "pt",
                    "bin_edges": [0.0, 25.0, 50.0],
                },
            },
        }
    )

    assert result.regions["Central"].yields == [2.0, 1.0]
    assert result.regions["Forward"].yields == [0.0, 1.0]


def test_compute_binned_yields_is_data_true(tmp_path: Path) -> None:
    input_array = _write_convert_output(tmp_path / "arrays_data.json", process="data")

    result = compute_binned_yields(
        {
            "analysis_version": "ana-v4",
            "process": "data",
            "is_data": True,
            "input_array_path": str(input_array),
            "regions": {
                "DataRegion": {
                    "cut": "pt > 0",
                    "observable": "pt",
                    "bin_edges": [0.0, 50.0],
                }
            },
        }
    )

    assert result.is_data is True
    assert result.process == "data"
    assert result.regions["DataRegion"].yields == [4.0]


def test_compute_binned_yields_missing_analysis_version_validation_error() -> None:
    with pytest.raises(PydanticValidationError):
        ComputeBinnedYieldsRequest.model_validate(
            {
                "process": "ttbar",
                "is_data": False,
                "input_array_path": "/tmp/nonexistent.json",
                "regions": {
                    "SR": {
                        "cut": "pt > 0",
                        "observable": "pt",
                        "bin_edges": [0.0, 1.0],
                    }
                },
            }
        )


def test_run_tool_dispatch_compute_binned_yields(tmp_path: Path) -> None:
    input_array = _write_convert_output(tmp_path / "arrays_dispatch.json", weights=None)

    response = run_tool(
        {
            "action": "compute_binned_yields",
            "input": {
                "analysis_version": "ana-v5",
                "process": "ttbar",
                "is_data": False,
                "input_array_path": str(input_array),
                "regions": {
                    "SR": {
                        "cut": "pt > 15",
                        "observable": "pt",
                        "bin_edges": [0.0, 25.0, 50.0],
                    }
                },
            },
        }
    )

    assert response["ok"] is True
    assert response["action"] == "compute_binned_yields"
    assert response["result"]["schema_version"] == "1.0"
    assert response["result"]["regions"]["SR"]["yields"] == [1.0, 2.0]
