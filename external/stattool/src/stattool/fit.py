"""Deterministic pyhf model fitting wrapper."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .schemas import (
    FitError,
    FitPyhfModelRequest,
    FitPyhfModelResult,
    ParameterEstimate,
    StatToolError,
    ValidationError,
)


def _import_pyhf() -> Any:
    """Import pyhf lazily so package import remains lightweight."""
    try:
        import pyhf  # type: ignore

        return pyhf
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise ValidationError(
            code="pyhf_not_available",
            message="pyhf is required for fit_pyhf_model action.",
            details={"error": str(exc)},
        ) from exc


def _load_workspace_spec(path: str) -> dict[str, Any]:
    """Load workspace JSON from disk."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise ValidationError(
            code="workspace_not_found",
            message="workspace_path does not point to an existing file.",
            details={"workspace_path": str(resolved)},
        )

    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        raise ValidationError(
            code="workspace_invalid_json",
            message="Failed to parse workspace JSON.",
            details={"workspace_path": str(resolved), "error": str(exc)},
        ) from exc

    if not isinstance(payload, dict):
        raise ValidationError(
            code="workspace_invalid_type",
            message="Workspace payload must be a JSON object.",
            details={"workspace_path": str(resolved)},
        )

    return payload


def _ensure_parameter_known(name: str, par_order: list[str], field_name: str) -> None:
    """Ensure user-provided parameter name exists in model parameter order."""
    if name not in par_order:
        raise ValidationError(
            code="unknown_parameter",
            message=f"Unknown parameter provided in `{field_name}`.",
            details={"parameter": name, "available_parameters": par_order},
        )


def _vector_to_float_list(values: Any) -> list[float]:
    """Convert backend vectors/tensors to a flat float list."""
    return [float(value) for value in np.asarray(values, dtype=float).reshape(-1).tolist()]


def _scalar_to_float(value: Any) -> float:
    """Convert backend scalar/tensor to Python float."""
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.size == 0:
        raise FitError(
            code="invalid_scalar",
            message="Unable to convert backend value to scalar.",
            details={"value": repr(value)},
        )
    return float(array[0])


def _build_model(workspace: Any, poi_name: str) -> Any:
    """Build model from workspace, requesting explicit POI when supported."""
    try:
        model = workspace.model(poi_name=poi_name)
    except TypeError:
        model = workspace.model()
    except Exception as exc:
        raise FitError(
            code="model_build_failed",
            message="Failed to build pyhf model from workspace.",
            details={"error": str(exc)},
        ) from exc

    model_poi = getattr(getattr(model, "config", None), "poi_name", None)
    if model_poi != poi_name:
        raise ValidationError(
            code="poi_name_unavailable",
            message="Requested poi_name is not available in model configuration.",
            details={"requested_poi": poi_name, "model_poi": model_poi},
        )

    return model


def _prepare_fit_inputs(model: Any, request: FitPyhfModelRequest) -> tuple[list[float], list[list[float]], list[bool], list[str]]:
    """Prepare init values, bounds, and fixed flags for pyhf fit."""
    config = model.config
    par_order = [str(name) for name in list(config.par_order)]
    par_index = {name: index for index, name in enumerate(par_order)}

    init_pars = [float(value) for value in list(config.suggested_init())]
    par_bounds = [[float(pair[0]), float(pair[1])] for pair in list(config.suggested_bounds())]

    if hasattr(config, "suggested_fixed"):
        fixed_params = [bool(value) for value in list(config.suggested_fixed())]
    else:  # pragma: no cover - defensive for backend differences
        fixed_params = [False] * len(par_order)

    for name, value in request.initial_parameters.items():
        _ensure_parameter_known(name, par_order, "initial_parameters")
        init_pars[par_index[name]] = float(value)

    for name, bounds in request.parameter_bounds.items():
        _ensure_parameter_known(name, par_order, "parameter_bounds")
        par_bounds[par_index[name]] = [float(bounds[0]), float(bounds[1])]

    for name in request.fixed_parameters:
        _ensure_parameter_known(name, par_order, "fixed_parameters")
        fixed_params[par_index[name]] = True

    return init_pars, par_bounds, fixed_params, par_order


def _run_fit(pyhf: Any, data: Any, model: Any, init_pars: list[float], par_bounds: list[list[float]], fixed_params: list[bool]) -> tuple[list[float], list[float]]:
    """Run MLE fit and return best-fit values and uncertainties if available."""
    fit_kwargs = {
        "data": data,
        "pdf": model,
        "init_pars": init_pars,
        "par_bounds": par_bounds,
        "fixed_params": fixed_params,
    }

    errors = [0.0] * len(init_pars)

    try:
        result = pyhf.infer.mle.fit(return_uncertainties=True, **fit_kwargs)
        if isinstance(result, tuple) and len(result) == 2:
            values = _vector_to_float_list(result[0])
            errors = _vector_to_float_list(result[1])
            if len(errors) != len(values):
                errors = [0.0] * len(values)
            return values, [abs(float(err)) for err in errors]

        values = _vector_to_float_list(result)
        return values, [0.0] * len(values)
    except TypeError:
        # Older pyhf versions may not support return_uncertainties.
        pass
    except Exception as exc:
        raise FitError(
            code="fit_failed",
            message="pyhf maximum-likelihood fit failed.",
            details={"error": str(exc)},
        ) from exc

    try:
        result = pyhf.infer.mle.fit(**fit_kwargs)
        values = _vector_to_float_list(result)
        return values, [0.0] * len(values)
    except Exception as exc:
        raise FitError(
            code="fit_failed",
            message="pyhf maximum-likelihood fit failed.",
            details={"error": str(exc)},
        ) from exc


def _compute_nll(pyhf: Any, values: list[float], data: Any, model: Any) -> float:
    """Compute NLL from fitted parameters."""
    if hasattr(pyhf.infer.mle, "twice_nll"):
        try:
            twice_nll = pyhf.infer.mle.twice_nll(pars=values, data=data, pdf=model)
            return 0.5 * _scalar_to_float(twice_nll)
        except TypeError:
            try:
                twice_nll = pyhf.infer.mle.twice_nll(values, data, model)
                return 0.5 * _scalar_to_float(twice_nll)
            except Exception:
                pass
        except Exception:
            pass

    if hasattr(model, "logpdf"):
        try:
            logpdf = model.logpdf(values, data)
            return -_scalar_to_float(logpdf)
        except Exception:
            pass

    raise FitError(
        code="nll_unavailable",
        message="Unable to compute NLL from fitted model.",
        details={},
    )


def fit_pyhf_model(request: FitPyhfModelRequest | dict[str, Any]) -> FitPyhfModelResult:
    """Fit a pyhf model and return JSON-serializable parameter estimates."""
    if isinstance(request, dict):
        request = FitPyhfModelRequest.model_validate(request)

    try:
        pyhf = _import_pyhf()
        workspace_spec = _load_workspace_spec(request.workspace_path)

        workspace = pyhf.Workspace(workspace_spec)
        model = _build_model(workspace, request.poi_name)
        data = workspace.data(model)

        init_pars, par_bounds, fixed_params, par_order = _prepare_fit_inputs(model, request)
        values, errors = _run_fit(
            pyhf=pyhf,
            data=data,
            model=model,
            init_pars=init_pars,
            par_bounds=par_bounds,
            fixed_params=fixed_params,
        )

        if len(values) != len(par_order):
            raise FitError(
                code="fit_result_length_mismatch",
                message="Fit output length does not match model parameter count.",
                details={
                    "n_values": len(values),
                    "n_parameters": len(par_order),
                    "parameters": par_order,
                },
            )

        nll = _compute_nll(pyhf, values, data, model)

        parameters = {
            name: ParameterEstimate(value=float(values[idx]), error=float(abs(errors[idx])))
            for idx, name in enumerate(par_order)
        }

        return FitPyhfModelResult(
            schema_version="1.0",
            poi=request.poi_name,
            nll=float(nll),
            parameters=parameters,
            metadata={
                "workspace_path": str(Path(request.workspace_path).expanduser().resolve()),
                "strategy": request.fit_options.strategy,
                "fixed_parameters": sorted(set(request.fixed_parameters)),
            },
        )
    except StatToolError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise FitError(
            code="fit_action_failed",
            message="Unexpected failure during pyhf fit action.",
            details={"error": str(exc)},
        ) from exc
