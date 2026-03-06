import argparse
from pathlib import Path
from typing import Any, Dict

import numpy as np

from analysis.common import ensure_dir, read_json, write_json
from analysis.stats.roofit_backend import run_roofit_significance



def _compute_discovery_significance_pyhf(workspace_path: Path) -> Dict[str, Any]:
    """Compute asymptotic discovery significance using profile likelihood ratio.

    Performs two fits:
    1) conditional fit with mu fixed to 0 (background-only hypothesis)
    2) unconditional fit with mu floating

    Returns q0 = 2*(NLL_mu0 - NLL_muhat) and Z = sqrt(max(q0, 0)).
    """

    import pyhf

    ws_spec = read_json(workspace_path)
    ws = pyhf.Workspace(ws_spec)
    model = ws.model()
    data = ws.data(model)
    poi_name = model.config.poi_name

    try:
        par_hat, twice_nll_free = pyhf.infer.mle.fit(
            data, model, return_fitted_val=True
        )
        par_hat = np.asarray(par_hat, dtype=float)
        mu_hat = float(par_hat[model.config.poi_index])

        par_mu0, twice_nll_mu0 = pyhf.infer.mle.fixed_poi_fit(
            0.0, data, model, return_fitted_val=True
        )
        par_mu0 = np.asarray(par_mu0, dtype=float)

        q0_raw = float(twice_nll_mu0 - twice_nll_free)
        # One-sided discovery test statistic.
        q0 = max(q0_raw, 0.0)
        z = float(np.sqrt(q0))

        return {
            "status": "ok",
            "poi_name": poi_name,
            "mu_hat": mu_hat,
            "twice_nll_free": float(twice_nll_free),
            "twice_nll_mu0": float(twice_nll_mu0),
            "q0": q0,
            "z_discovery": z,
            "fit_params_free": par_hat.tolist(),
            "fit_params_mu0": par_mu0.tolist(),
            "note": "Asymptotic profile-likelihood approximation (one-sided).",
            "backend": "pyhf",
        }
    except Exception as exc:
        return {
            "status": "failed",
            "poi_name": poi_name,
            "error": str(exc),
            "mu_hat": None,
            "twice_nll_free": None,
            "twice_nll_mu0": None,
            "q0": None,
            "z_discovery": None,
            "backend": "pyhf",
        }


def compute_discovery_significance(workspace_path: Path, backend: str = "pyhf") -> Dict[str, Any]:
    backend_name = str(backend).strip().lower()
    if backend_name == "pyhf":
        return _compute_discovery_significance_pyhf(workspace_path)
    if backend_name == "pyroot_roofit":
        return run_roofit_significance(workspace_path)
    return {
        "status": "failed",
        "poi_name": "mu",
        "error": "Unsupported significance backend '{}'".format(backend),
        "mu_hat": None,
        "twice_nll_free": None,
        "twice_nll_mu0": None,
        "q0": None,
        "z_discovery": None,
        "backend": backend_name,
    }



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute discovery significance from profile likelihood ratio"
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--fit-id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--backend", default="pyhf", choices=["pyhf", "pyroot_roofit"])
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    payload = compute_discovery_significance(Path(args.workspace), backend=args.backend)
    payload["fit_id"] = args.fit_id

    out_path = Path(args.out)
    ensure_dir(out_path.parent)
    write_json(out_path, payload)

    if payload.get("status") == "ok":
        print(
            "significance {} backend={}: q0={:.6g}, Z={:.6g}".format(
                args.fit_id,
                payload.get("backend", args.backend),
                float(payload["q0"]),
                float(payload["z_discovery"]),
            )
        )
    else:
        print(
            "significance {} backend={}: failed ({})".format(
                args.fit_id,
                payload.get("backend", args.backend),
                payload.get("error", "unknown"),
            )
        )


if __name__ == "__main__":
    main()
