"""Tests for deterministic pyhf workspace construction."""

from __future__ import annotations

import json
from pathlib import Path

from stattool.workspace import build_pyhf_workspace


def _write_process_file(
    path: Path,
    *,
    analysis_version: str,
    process: str,
    is_data: bool,
    yields: list[float],
) -> Path:
    payload = {
        "schema_version": "1.0",
        "analysis_version": analysis_version,
        "process": process,
        "is_data": is_data,
        "regions": {
            "SR": {
                "observable": "met",
                "bin_edges": [0.0, 50.0, 100.0],
                "yields": yields,
            }
        },
        "metadata": {
            "source_array": f"/{process}.json",
            "n_events_processed": 100,
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_build_workspace_single_region_signal_and_background(tmp_path: Path) -> None:
    signal = _write_process_file(
        tmp_path / "signal.json",
        analysis_version="ana-v1",
        process="signal",
        is_data=False,
        yields=[2.0, 1.0],
    )
    background = _write_process_file(
        tmp_path / "background.json",
        analysis_version="ana-v1",
        process="background",
        is_data=False,
        yields=[12.0, 8.0],
    )
    data = _write_process_file(
        tmp_path / "data.json",
        analysis_version="ana-v1",
        process="data",
        is_data=True,
        yields=[14.0, 9.0],
    )

    workspace_path = tmp_path / "workspace.json"
    result = build_pyhf_workspace(
        {
            "analysis_version": "ana-v1",
            "process_files": [str(signal), str(background), str(data)],
            "signal_process": "signal",
            "norm_config": {
                "signal": {"free": True, "shared_group": None},
                "background": {"free": True, "shared_group": None},
            },
            "output_workspace_path": str(workspace_path),
        }
    )

    assert result.schema_version == "1.0"
    assert result.poi_name == "mu"
    assert result.samples == ["background", "signal"]
    assert len(result.channels) == 1
    assert result.channels[0].name == "SR"

    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    assert workspace["version"] == "1.0.0"
    assert workspace["measurements"][0]["config"]["poi"] == "mu"

    samples = workspace["channels"][0]["samples"]
    sample_names = [sample["name"] for sample in samples]
    assert sample_names == ["background", "signal"]


def test_build_workspace_shared_normalization_group(tmp_path: Path) -> None:
    signal = _write_process_file(
        tmp_path / "signal.json",
        analysis_version="ana-v2",
        process="signal",
        is_data=False,
        yields=[1.0, 1.0],
    )
    bkg_a = _write_process_file(
        tmp_path / "bkg_a.json",
        analysis_version="ana-v2",
        process="bkg_a",
        is_data=False,
        yields=[3.0, 2.0],
    )
    bkg_b = _write_process_file(
        tmp_path / "bkg_b.json",
        analysis_version="ana-v2",
        process="bkg_b",
        is_data=False,
        yields=[5.0, 4.0],
    )
    data = _write_process_file(
        tmp_path / "data.json",
        analysis_version="ana-v2",
        process="data",
        is_data=True,
        yields=[9.0, 7.0],
    )

    workspace_path = tmp_path / "workspace_group.json"
    build_pyhf_workspace(
        {
            "analysis_version": "ana-v2",
            "process_files": [str(signal), str(bkg_a), str(bkg_b), str(data)],
            "signal_process": "signal",
            "norm_config": {
                "bkg_a": {"free": True, "shared_group": "bkg_group"},
                "bkg_b": {"free": True, "shared_group": "bkg_group"},
            },
            "output_workspace_path": str(workspace_path),
        }
    )

    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    samples = workspace["channels"][0]["samples"]
    modifiers = {
        sample["name"]: sample["modifiers"][0]["name"]
        for sample in samples
    }

    assert modifiers["bkg_a"] == "norm_bkg_group"
    assert modifiers["bkg_b"] == "norm_bkg_group"
    assert modifiers["signal"] == "mu"

    parameter_names = [
        entry["name"]
        for entry in workspace["measurements"][0]["config"]["parameters"]
    ]
    assert parameter_names == ["mu", "norm_bkg_group"]
