"""Deterministic profile NLL scan generation for pyhf models."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .fit import (
    _build_model,
    _compute_nll,
    _ensure_parameter_known,
    _import_pyhf,
    _load_workspace_spec,
    _prepare_fit_inputs,
    _run_fit,
)
from .schemas import (
    FitPyhfModelRequest,
    FitError,
    ScanNLLCurveRequest,
    ScanNLLCurveResult,
    StatToolError,
    ValidationError,
)


def _import_plotter() -> Any:
    """Import matplotlib lazily for headless figure rendering."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        return plt
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise ValidationError(
            code="matplotlib_not_available",
            message="matplotlib is required to render NLL scan PNG output.",
            details={"error": str(exc)},
        ) from exc


def _resolve_scan_range(
    request: ScanNLLCurveRequest,
    best_value: float,
    best_error: float,
    bounds: list[float],
) -> tuple[float, float]:
    """Resolve scan interval from explicit inputs or default best ± 3 sigma."""
    low_bound, high_bound = float(bounds[0]), float(bounds[1])

    if request.scan_min is not None:
        if request.scan_min < low_bound:
            raise ValidationError(
                code="scan_min_out_of_bounds",
                message="scan_min is below allowed parameter bounds.",
                details={
                    "scan_min": float(request.scan_min),
                    "lower_bound": low_bound,
                    "parameter": request.parameter_name,
                },
            )
        scan_min = float(request.scan_min)
    else:
        sigma = max(float(best_error), 1e-6)
        scan_min = max(low_bound, float(best_value - 3.0 * sigma))

    if request.scan_max is not None:
        if request.scan_max > high_bound:
            raise ValidationError(
                code="scan_max_out_of_bounds",
                message="scan_max is above allowed parameter bounds.",
                details={
                    "scan_max": float(request.scan_max),
                    "upper_bound": high_bound,
                    "parameter": request.parameter_name,
                },
            )
        scan_max = float(request.scan_max)
    else:
        sigma = max(float(best_error), 1e-6)
        scan_max = min(high_bound, float(best_value + 3.0 * sigma))

    if scan_max <= scan_min:
        raise ValidationError(
            code="invalid_scan_range",
            message="Resolved scan range is invalid (scan_max <= scan_min).",
            details={
                "scan_min": scan_min,
                "scan_max": scan_max,
                "parameter": request.parameter_name,
            },
        )

    return scan_min, scan_max


def _resolve_output_paths(request: ScanNLLCurveRequest) -> tuple[Path, Path]:
    """Resolve PNG/TXT output paths and ensure parent directories exist."""
    png_path = Path(request.output_png_path).expanduser().resolve()
    txt_path = (
        Path(request.output_txt_path).expanduser().resolve()
        if request.output_txt_path
        else png_path.with_suffix(".txt")
    )

    png_path.parent.mkdir(parents=True, exist_ok=True)
    txt_path.parent.mkdir(parents=True, exist_ok=True)
    return png_path, txt_path


def _write_scan_txt(points: list[dict[str, float]], parameter_name: str, path: Path) -> None:
    """Write scan points as deterministic text table."""
    lines = [f"# {parameter_name}\tnll\tdelta_nll"]
    for point in points:
        lines.append(
            f"{point['value']:.12g}\t{point['nll']:.12g}\t{point['delta_nll']:.12g}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _render_scan_plot(
    points: list[dict[str, float]],
    parameter_name: str,
    best_value: float,
    path: Path,
) -> None:
    """Render profile NLL curve to PNG."""
    plt = _import_plotter()

    x_values = [point["value"] for point in points]
    y_values = [point["delta_nll"] for point in points]

    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    ax.plot(x_values, y_values, marker="o", linewidth=1.5)
    ax.axvline(best_value, linestyle="--", linewidth=1.0, label="best fit")
    ax.axhline(0.5, linestyle=":", linewidth=1.0, label="ΔNLL=0.5")
    ax.set_xlabel(parameter_name)
    ax.set_ylabel("Delta NLL")
    ax.set_title(f"Profile scan for {parameter_name}")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")

    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def scan_nll_curve(request: ScanNLLCurveRequest | dict[str, Any]) -> ScanNLLCurveResult:
    """Profile NLL as a function of one fixed parameter."""
    if isinstance(request, dict):
        request = ScanNLLCurveRequest.model_validate(request)

    try:
        pyhf = _import_pyhf()
        workspace_spec = _load_workspace_spec(request.workspace_path)

        workspace = pyhf.Workspace(workspace_spec)
        model = _build_model(workspace, request.poi_name)
        data = workspace.data(model)

        base_fit_request = FitPyhfModelRequest(
            workspace_path=request.workspace_path,
            poi_name=request.poi_name,
            initial_parameters=request.initial_parameters,
            parameter_bounds=request.parameter_bounds,
            fixed_parameters=request.fixed_parameters,
            fit_options=request.fit_options,
        )

        init_pars, par_bounds, fixed_params, par_order = _prepare_fit_inputs(model, base_fit_request)
        _ensure_parameter_known(request.parameter_name, par_order, "parameter_name")

        scan_idx = par_order.index(request.parameter_name)
        if fixed_params[scan_idx]:
            raise ValidationError(
                code="scan_parameter_already_fixed",
                message="Requested scan parameter is already fixed in fixed_parameters.",
                details={"parameter": request.parameter_name},
            )

        free_fit_values, free_fit_errors = _run_fit(
            pyhf=pyhf,
            data=data,
            model=model,
            init_pars=init_pars,
            par_bounds=par_bounds,
            fixed_params=fixed_params,
        )

        if len(free_fit_values) != len(par_order):
            raise FitError(
                code="fit_result_length_mismatch",
                message="Free-fit output length does not match model parameter count.",
                details={
                    "n_values": len(free_fit_values),
                    "n_parameters": len(par_order),
                    "parameters": par_order,
                },
            )

        best_value = float(free_fit_values[scan_idx])
        best_error = float(abs(free_fit_errors[scan_idx]))

        scan_min, scan_max = _resolve_scan_range(
            request=request,
            best_value=best_value,
            best_error=best_error,
            bounds=par_bounds[scan_idx],
        )

        scan_values = np.linspace(scan_min, scan_max, int(request.n_steps))
        points: list[dict[str, float]] = []

        for scan_value in scan_values.tolist():
            prof_init = [float(value) for value in free_fit_values]
            prof_fixed = [bool(flag) for flag in fixed_params]
            prof_init[scan_idx] = float(scan_value)
            prof_fixed[scan_idx] = True

            prof_values, _ = _run_fit(
                pyhf=pyhf,
                data=data,
                model=model,
                init_pars=prof_init,
                par_bounds=par_bounds,
                fixed_params=prof_fixed,
            )
            nll = _compute_nll(pyhf, prof_values, data, model)
            points.append({"value": float(scan_value), "nll": float(nll), "delta_nll": 0.0})

        min_nll = min(point["nll"] for point in points)
        for point in points:
            point["delta_nll"] = float(point["nll"] - min_nll)

        output_png_path, output_txt_path = _resolve_output_paths(request)
        _write_scan_txt(points=points, parameter_name=request.parameter_name, path=output_txt_path)
        _render_scan_plot(
            points=points,
            parameter_name=request.parameter_name,
            best_value=best_value,
            path=output_png_path,
        )

        return ScanNLLCurveResult(
            schema_version="1.0",
            parameter_name=request.parameter_name,
            poi_name=request.poi_name,
            best_fit_value=best_value,
            best_fit_error=best_error,
            scan_min=float(scan_min),
            scan_max=float(scan_max),
            n_steps=int(request.n_steps),
            output_png_path=str(output_png_path),
            output_txt_path=str(output_txt_path),
            points=points,
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
            code="scan_nll_curve_failed",
            message="Unexpected failure during NLL scan computation.",
            details={"error": str(exc)},
        ) from exc
