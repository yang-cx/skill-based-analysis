"""Tests for process-aware ROOT-to-array conversion."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import uproot

from rootmltool.convert import convert_root_to_array
from rootmltool.tool_entrypoint import run_tool


def _create_synthetic_root(path: Path, pt: np.ndarray, eta: np.ndarray, weight: np.ndarray) -> None:
    with uproot.recreate(path) as root_file:
        root_file["Events"] = {
            "pt": pt.astype(np.float32),
            "eta": eta.astype(np.float32),
            "event_weight": weight.astype(np.float32),
        }


def test_convert_root_to_array_single_file_with_weight(tmp_path: Path) -> None:
    root_path = tmp_path / "sample.root"
    out_path = tmp_path / "arrays.json"
    _create_synthetic_root(
        root_path,
        pt=np.array([10.0, 20.0, 30.0]),
        eta=np.array([0.1, -0.2, 1.3]),
        weight=np.array([1.0, 0.8, 1.2]),
    )

    result = convert_root_to_array(
        {
            "process": "ttbar",
            "input_paths": [str(root_path)],
            "tree": "Events",
            "branches": ["pt", "eta"],
            "weight_branch": "event_weight",
            "output_path": str(out_path),
        }
    )

    assert result.process == "ttbar"
    assert result.n_events == 3
    assert list(result.data.keys()) == ["pt", "eta"]
    assert result.data["pt"] == [10.0, 20.0, 30.0]
    assert result.weights == [1.0, 0.800000011920929, 1.2000000476837158]
    assert result.metadata["tree_name"] == "Events"
    assert result.metadata["preselection"] is None
    assert len(result.metadata["source_files"]) == 1

    dumped = json.loads(out_path.read_text(encoding="utf-8"))
    assert dumped["process"] == "ttbar"
    assert dumped["n_events"] == 3
    assert dumped["weights"] is not None
    assert dumped["metadata"]["backend"] == "uproot"


def test_convert_root_to_array_concatenates_multiple_files(tmp_path: Path) -> None:
    root_a = tmp_path / "a.root"
    root_b = tmp_path / "b.root"
    _create_synthetic_root(
        root_a,
        pt=np.array([1.0, 2.0]),
        eta=np.array([0.1, 0.2]),
        weight=np.array([1.0, 1.0]),
    )
    _create_synthetic_root(
        root_b,
        pt=np.array([3.0]),
        eta=np.array([0.3]),
        weight=np.array([0.5]),
    )

    result = convert_root_to_array(
        {
            "process": "zjets",
            "input_paths": [str(root_a), str(root_b)],
            "tree": "Events",
            "branches": ["pt", "eta"],
            "weight_branch": "event_weight",
        }
    )

    assert result.process == "zjets"
    assert result.n_events == 3
    assert result.data["pt"] == [1.0, 2.0, 3.0]
    assert result.data["eta"] == [0.10000000149011612, 0.20000000298023224, 0.30000001192092896]
    assert result.weights == [1.0, 1.0, 0.5]
    assert len(result.metadata["source_files"]) == 2


def test_tool_entrypoint_supports_convert_root_to_array(tmp_path: Path) -> None:
    root_path = tmp_path / "entrypoint.root"
    _create_synthetic_root(
        root_path,
        pt=np.array([5.0, 6.0]),
        eta=np.array([0.0, 1.0]),
        weight=np.array([1.0, 1.0]),
    )

    response = run_tool(
        {
            "action": "convert_root_to_array",
            "input": {
                "process": "signal",
                "input_paths": [str(root_path)],
                "tree": "Events",
                "branches": ["pt", "eta"],
                "weight_branch": "event_weight",
            },
        }
    )

    assert response["ok"] is True
    assert response["action"] == "convert_root_to_array"
    assert response["result"]["process"] == "signal"
    assert response["result"]["n_events"] == 2
    assert response["result"]["weights"] is not None


def test_convert_root_to_array_without_weight_branch(tmp_path: Path) -> None:
    root_path = tmp_path / "no_weight.root"
    _create_synthetic_root(
        root_path,
        pt=np.array([11.0, 22.0]),
        eta=np.array([0.5, -0.4]),
        weight=np.array([1.2, 0.7]),
    )

    result = convert_root_to_array(
        {
            "process": "qcd",
            "input_paths": [str(root_path)],
            "tree": "Events",
            "branches": ["pt", "eta"],
        }
    )

    assert result.n_events == 2
    assert list(result.data.keys()) == ["pt", "eta"]
    assert result.weights is None
    assert result.metadata["preselection"] is None


def test_convert_root_to_array_with_preselection_reduces_events(tmp_path: Path) -> None:
    root_path = tmp_path / "preselection.root"
    _create_synthetic_root(
        root_path,
        pt=np.array([10.0, 25.0, 40.0, 15.0]),
        eta=np.array([0.1, 2.8, 0.2, -3.0]),
        weight=np.array([1.0, 0.9, 1.1, 0.8]),
    )

    result = convert_root_to_array(
        {
            "process": "signal",
            "input_paths": [str(root_path)],
            "tree": "Events",
            "branches": ["pt", "eta"],
            "weight_branch": "event_weight",
            "preselection": "pt > 20 & abs(eta) < 2.5",
        }
    )

    assert result.n_events == 1
    assert result.data["pt"] == [40.0]
    assert result.data["eta"] == [0.20000000298023224]
    assert result.weights == [1.100000023841858]
    assert result.metadata["preselection"] == "pt > 20 & abs(eta) < 2.5"
