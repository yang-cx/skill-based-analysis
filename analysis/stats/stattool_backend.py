from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def vendored_stattool_src_path() -> Path:
    return _repo_root() / "external" / "stattool" / "src"


def _ensure_vendored_stattool_importable() -> None:
    src = vendored_stattool_src_path()
    if not src.exists():
        raise RuntimeError("Vendored stattool source not found: {}".format(src))
    src_s = str(src)
    if src_s not in sys.path:
        sys.path.insert(0, src_s)


def stattool_is_available() -> Tuple[bool, str]:
    src = vendored_stattool_src_path()
    if not src.exists():
        return False, "vendored source missing"
    try:
        _ensure_vendored_stattool_importable()
        import stattool  # noqa: F401

        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def resolve_pyhf_backend(requested_backend: str) -> str:
    backend = str(requested_backend).strip().lower()
    if backend == "native":
        return "native"
    if backend == "stattool":
        available, reason = stattool_is_available()
        if not available:
            raise RuntimeError(
                "Requested --pyhf-backend stattool but it is unavailable: {}".format(reason)
            )
        return "stattool"
    if backend != "auto":
        raise RuntimeError("Unsupported pyhf backend: {}".format(requested_backend))

    available, _reason = stattool_is_available()
    if available:
        return "stattool"
    return "native"


def run_stattool_fit(
    workspace_path: Path,
    *,
    poi_name: str = "mu",
    initial_parameters: Dict[str, float] | None = None,
    parameter_bounds: Dict[str, list[float]] | None = None,
    fixed_parameters: list[str] | None = None,
) -> Dict[str, Any]:
    _ensure_vendored_stattool_importable()
    from stattool.tool_entrypoint import run_tool

    response = run_tool(
        {
            "action": "fit_pyhf_model",
            "input": {
                "workspace_path": str(Path(workspace_path).expanduser().resolve()),
                "poi_name": str(poi_name),
                "initial_parameters": dict(initial_parameters or {}),
                "parameter_bounds": dict(parameter_bounds or {}),
                "fixed_parameters": list(fixed_parameters or []),
                "fit_options": {"strategy": "default"},
            },
        }
    )

    if not response.get("ok"):
        error = response.get("error", {})
        return {
            "poi_name": str(poi_name),
            "bestfit_poi": 1.0,
            "bestfit_all": [],
            "bestfit_labels": [],
            "bestfit_errors": [],
            "twice_nll": None,
            "status": "failed",
            "error": "{}: {}".format(
                error.get("code", "unknown_error"),
                error.get("message", "no message"),
            ),
            "n_pars": 0,
            "backend": "pyhf",
            "pyhf_backend": "stattool",
        }

    result = response.get("result", {})
    params = result.get("parameters", {})
    labels = list(params.keys())
    values = [float(params[name].get("value", 0.0)) for name in labels]
    errors = [float(abs(params[name].get("error", 0.0))) for name in labels]

    poi = str(result.get("poi", poi_name))
    poi_idx = labels.index(poi) if poi in labels else -1
    poi_hat = float(values[poi_idx]) if poi_idx >= 0 else 0.0
    nll = result.get("nll")
    twice_nll = (2.0 * float(nll)) if isinstance(nll, (int, float)) else None

    return {
        "poi_name": poi,
        "bestfit_poi": poi_hat,
        "bestfit_all": values,
        "bestfit_labels": labels,
        "bestfit_errors": errors,
        "twice_nll": twice_nll,
        "status": "ok",
        "n_pars": int(len(values)),
        "backend": "pyhf",
        "pyhf_backend": "stattool",
        "metadata": {
            "workspace_path": result.get("metadata", {}).get("workspace_path"),
            "strategy": result.get("metadata", {}).get("strategy"),
        },
    }

