"""Dispatch tests for stattool tool_entrypoint envelope contract."""

from __future__ import annotations

import json
from pathlib import Path

from stattool.tool_entrypoint import run_tool


def _write_process_file(path: Path, process: str, is_data: bool) -> Path:
    payload = {
        "schema_version": "1.0",
        "analysis_version": "ana-v1",
        "process": process,
        "is_data": is_data,
        "regions": {
            "SR": {
                "observable": "met",
                "bin_edges": [0.0, 50.0],
                "yields": [1.0],
            }
        },
        "metadata": {"source_array": "/tmp/mock.json", "n_events_processed": 10},
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_run_tool_dispatch_build_workspace(tmp_path: Path) -> None:
    signal = _write_process_file(tmp_path / "signal.json", process="signal", is_data=False)
    data = _write_process_file(tmp_path / "data.json", process="data", is_data=True)
    workspace_path = tmp_path / "workspace.json"

    response = run_tool(
        {
            "action": "build_pyhf_workspace",
            "input": {
                "analysis_version": "ana-v1",
                "process_files": [str(signal), str(data)],
                "signal_process": "signal",
                "norm_config": {"signal": {"free": True, "shared_group": None}},
                "output_workspace_path": str(workspace_path),
            },
        }
    )

    assert response["ok"] is True
    assert response["action"] == "build_pyhf_workspace"
    assert response["result"]["schema_version"] == "1.0"


def test_run_tool_invalid_payload_returns_error() -> None:
    response = run_tool({"action": "build_pyhf_workspace", "input": {}})

    assert response["ok"] is False
    assert "error" in response
