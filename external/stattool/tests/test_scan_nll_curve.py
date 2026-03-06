"""Tests for deterministic profile NLL scan generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from stattool.scan import scan_nll_curve
from stattool.tool_entrypoint import run_tool


class _FakeConfig:
    def __init__(self, par_order: list[str], poi_name: str) -> None:
        self.par_order = par_order
        self.poi_name = poi_name

    def suggested_init(self) -> list[float]:
        return [1.0 for _ in self.par_order]

    def suggested_bounds(self) -> list[list[float]]:
        return [[0.0, 10.0] for _ in self.par_order]

    def suggested_fixed(self) -> list[bool]:
        return [False for _ in self.par_order]


class _FakeModel:
    def __init__(self, par_order: list[str], poi_name: str) -> None:
        self.config = _FakeConfig(par_order=par_order, poi_name=poi_name)

    def logpdf(self, pars: list[float], data: Any) -> np.ndarray:
        values = np.asarray(pars, dtype=float)
        return np.array([-float(np.sum((values - 1.0) ** 2))])


class _FakeWorkspace:
    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec
        measurement = spec["measurements"][0]
        self.default_poi = measurement["config"]["poi"]

        parameters: list[str] = []
        for channel in spec.get("channels", []):
            for sample in channel.get("samples", []):
                for modifier in sample.get("modifiers", []):
                    if modifier.get("type") == "normfactor":
                        name = str(modifier.get("name"))
                        if name not in parameters:
                            parameters.append(name)
        self.parameters = parameters

    def model(self, poi_name: str | None = None) -> _FakeModel:
        chosen_poi = self.default_poi if poi_name is None else poi_name
        if chosen_poi not in self.parameters:
            raise KeyError(f"Unknown POI: {chosen_poi}")
        return _FakeModel(par_order=self.parameters, poi_name=chosen_poi)

    def data(self, model: _FakeModel) -> list[float]:
        values: list[float] = []
        for observation in self.spec.get("observations", []):
            values.extend(float(item) for item in observation.get("data", []))
        return values


class _FakeMLE:
    def fit(
        self,
        *,
        data: Any,
        pdf: _FakeModel,
        init_pars: list[float],
        par_bounds: list[list[float]],
        fixed_params: list[bool],
        return_uncertainties: bool = False,
    ) -> Any:
        fitted = np.asarray(init_pars, dtype=float)

        for idx, name in enumerate(pdf.config.par_order):
            if fixed_params[idx]:
                candidate = fitted[idx]
            elif name == pdf.config.poi_name:
                candidate = 1.5
            else:
                candidate = 1.1

            low, high = par_bounds[idx]
            fitted[idx] = min(max(candidate, low), high)

        if return_uncertainties:
            return fitted, np.full_like(fitted, 0.1)
        return fitted

    def twice_nll(self, pars: list[float], data: Any, pdf: _FakeModel) -> float:
        values = np.asarray(pars, dtype=float)
        return float(2.0 * np.sum((values - 1.0) ** 2))


class _FakeInfer:
    def __init__(self) -> None:
        self.mle = _FakeMLE()


class _FakePyhf:
    Workspace = _FakeWorkspace

    def __init__(self) -> None:
        self.infer = _FakeInfer()


def _write_workspace(path: Path) -> Path:
    workspace = {
        "version": "1.0.0",
        "channels": [
            {
                "name": "SR",
                "samples": [
                    {
                        "name": "signal",
                        "data": [2.0, 1.0],
                        "modifiers": [{"name": "mu", "type": "normfactor", "data": None}],
                    },
                    {
                        "name": "background",
                        "data": [10.0, 7.0],
                        "modifiers": [
                            {"name": "norm_background", "type": "normfactor", "data": None}
                        ],
                    },
                ],
            }
        ],
        "observations": [{"name": "SR", "data": [12.0, 8.0]}],
        "measurements": [
            {
                "name": "measurement",
                "config": {
                    "poi": "mu",
                    "parameters": [
                        {
                            "name": "mu",
                            "inits": [1.0],
                            "bounds": [[0.0, 10.0]],
                            "fixed": False,
                        },
                        {
                            "name": "norm_background",
                            "inits": [1.0],
                            "bounds": [[0.0, 10.0]],
                            "fixed": False,
                        },
                    ],
                },
            }
        ],
    }
    path.write_text(json.dumps(workspace, indent=2), encoding="utf-8")
    return path


def _fake_plot(points: list[dict[str, float]], parameter_name: str, best_value: float, path: Path) -> None:
    path.write_text(
        f"fake plot for {parameter_name} with {len(points)} points and best={best_value}\n",
        encoding="utf-8",
    )


def test_scan_nll_curve_default_range_and_steps(tmp_path: Path, monkeypatch) -> None:
    workspace = _write_workspace(tmp_path / "workspace.json")
    output_png = tmp_path / "nll_scan.png"

    monkeypatch.setattr("stattool.scan._import_pyhf", lambda: _FakePyhf())
    monkeypatch.setattr("stattool.scan._render_scan_plot", _fake_plot)

    result = scan_nll_curve(
        {
            "workspace_path": str(workspace),
            "parameter_name": "mu",
            "poi_name": "mu",
            "initial_parameters": {},
            "parameter_bounds": {},
            "fixed_parameters": [],
            "output_png_path": str(output_png),
        }
    )

    assert result.schema_version == "1.0"
    assert result.parameter_name == "mu"
    assert result.n_steps == 10
    assert pytest.approx(result.best_fit_value, rel=0.0, abs=1e-12) == 1.5
    assert pytest.approx(result.best_fit_error, rel=0.0, abs=1e-12) == 0.1
    assert pytest.approx(result.scan_min, rel=0.0, abs=1e-12) == 1.2
    assert pytest.approx(result.scan_max, rel=0.0, abs=1e-12) == 1.8
    assert len(result.points) == 10

    txt_path = output_png.with_suffix(".txt")
    assert output_png.exists()
    assert txt_path.exists()

    lines = txt_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 11
    assert lines[0].startswith("# mu")


def test_scan_nll_curve_custom_range_and_steps(tmp_path: Path, monkeypatch) -> None:
    workspace = _write_workspace(tmp_path / "workspace_custom.json")
    output_png = tmp_path / "custom_scan.png"
    output_txt = tmp_path / "custom_scan_points.txt"

    monkeypatch.setattr("stattool.scan._import_pyhf", lambda: _FakePyhf())
    monkeypatch.setattr("stattool.scan._render_scan_plot", _fake_plot)

    result = scan_nll_curve(
        {
            "workspace_path": str(workspace),
            "parameter_name": "mu",
            "poi_name": "mu",
            "scan_min": 0.5,
            "scan_max": 2.5,
            "n_steps": 5,
            "output_png_path": str(output_png),
            "output_txt_path": str(output_txt),
        }
    )

    assert result.n_steps == 5
    assert pytest.approx(result.scan_min, rel=0.0, abs=1e-12) == 0.5
    assert pytest.approx(result.scan_max, rel=0.0, abs=1e-12) == 2.5
    assert len(result.points) == 5
    assert result.output_txt_path == str(output_txt.resolve())
    assert output_png.exists()
    assert output_txt.exists()


def test_scan_nll_curve_parameter_already_fixed(tmp_path: Path, monkeypatch) -> None:
    workspace = _write_workspace(tmp_path / "workspace_fixed_scan.json")

    monkeypatch.setattr("stattool.scan._import_pyhf", lambda: _FakePyhf())
    monkeypatch.setattr("stattool.scan._render_scan_plot", _fake_plot)

    with pytest.raises(Exception) as exc_info:
        scan_nll_curve(
            {
                "workspace_path": str(workspace),
                "parameter_name": "mu",
                "poi_name": "mu",
                "fixed_parameters": ["mu"],
                "output_png_path": str(tmp_path / "bad.png"),
            }
        )

    assert getattr(exc_info.value, "code", "") == "scan_parameter_already_fixed"
    assert "already fixed" in getattr(exc_info.value, "message", "")


def test_run_tool_dispatch_scan_nll_curve(tmp_path: Path, monkeypatch) -> None:
    workspace = _write_workspace(tmp_path / "workspace_dispatch.json")
    output_png = tmp_path / "dispatch_scan.png"

    monkeypatch.setattr("stattool.scan._import_pyhf", lambda: _FakePyhf())
    monkeypatch.setattr("stattool.scan._render_scan_plot", _fake_plot)

    response = run_tool(
        {
            "action": "scan_nll_curve",
            "input": {
                "workspace_path": str(workspace),
                "parameter_name": "mu",
                "poi_name": "mu",
                "n_steps": 4,
                "output_png_path": str(output_png),
            },
        }
    )

    assert response["ok"] is True
    assert response["action"] == "scan_nll_curve"
    assert response["result"]["schema_version"] == "1.0"
    assert response["result"]["n_steps"] == 4
    assert Path(response["result"]["output_png_path"]).exists()
    assert Path(response["result"]["output_txt_path"]).exists()
