"""Tests for deterministic pyhf fit wrapper with a fake pyhf backend."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from stattool.fit import fit_pyhf_model


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


def test_fit_with_free_parameters(tmp_path: Path, monkeypatch) -> None:
    workspace = _write_workspace(tmp_path / "workspace.json")
    monkeypatch.setattr("stattool.fit._import_pyhf", lambda: _FakePyhf())

    result = fit_pyhf_model(
        {
            "workspace_path": str(workspace),
            "poi_name": "mu",
            "initial_parameters": {},
            "parameter_bounds": {},
            "fixed_parameters": [],
            "fit_options": {"strategy": "default"},
        }
    )

    assert result.schema_version == "1.0"
    assert result.poi == "mu"
    assert result.parameters["mu"].value == 1.5
    assert result.parameters["norm_background"].value == 1.1
    assert result.parameters["mu"].error == 0.1


def test_fit_with_fixed_parameter(tmp_path: Path, monkeypatch) -> None:
    workspace = _write_workspace(tmp_path / "workspace_fixed.json")
    monkeypatch.setattr("stattool.fit._import_pyhf", lambda: _FakePyhf())

    result = fit_pyhf_model(
        {
            "workspace_path": str(workspace),
            "poi_name": "mu",
            "initial_parameters": {"mu": 2.5},
            "parameter_bounds": {},
            "fixed_parameters": ["mu"],
            "fit_options": {"strategy": "default"},
        }
    )

    assert result.parameters["mu"].value == 2.5
    assert result.parameters["norm_background"].value == 1.1


def test_fit_poi_change(tmp_path: Path, monkeypatch) -> None:
    workspace = _write_workspace(tmp_path / "workspace_poi.json")
    monkeypatch.setattr("stattool.fit._import_pyhf", lambda: _FakePyhf())

    result = fit_pyhf_model(
        {
            "workspace_path": str(workspace),
            "poi_name": "norm_background",
            "initial_parameters": {},
            "parameter_bounds": {},
            "fixed_parameters": [],
            "fit_options": {"strategy": "default"},
        }
    )

    assert result.poi == "norm_background"
    assert result.parameters["norm_background"].value == 1.5


def test_fit_bounds_respected(tmp_path: Path, monkeypatch) -> None:
    workspace = _write_workspace(tmp_path / "workspace_bounds.json")
    monkeypatch.setattr("stattool.fit._import_pyhf", lambda: _FakePyhf())

    result = fit_pyhf_model(
        {
            "workspace_path": str(workspace),
            "poi_name": "mu",
            "initial_parameters": {},
            "parameter_bounds": {"mu": [0.0, 0.4]},
            "fixed_parameters": [],
            "fit_options": {"strategy": "default"},
        }
    )

    assert result.parameters["mu"].value == 0.4
