import argparse
from pathlib import Path
from typing import Any, Dict

import numpy as np

from analysis.common import ensure_dir, read_json, write_json
from analysis.stats.roofit_backend import run_roofit_fit



def _run_pyhf_fit(workspace_path: Path) -> Dict[str, Any]:
    import pyhf

    ws_spec = read_json(workspace_path)
    ws = pyhf.Workspace(ws_spec)
    model = ws.model()
    data = ws.data(model)
    poi_name = model.config.poi_name

    try:
        bestfit, twice_nll = pyhf.infer.mle.fit(data, model, return_fitted_val=True)
        bestfit = np.asarray(bestfit, dtype=float)

        poi_idx = model.config.poi_index
        poi_hat = float(bestfit[poi_idx])

        return {
            "poi_name": poi_name,
            "bestfit_poi": poi_hat,
            "bestfit_all": bestfit.tolist(),
            "twice_nll": float(twice_nll),
            "status": "ok",
            "n_pars": int(len(bestfit)),
            "backend": "pyhf",
        }
    except Exception as exc:
        # Keep pipeline executable and emit actionable diagnostics.
        return {
            "poi_name": poi_name,
            "bestfit_poi": 1.0,
            "bestfit_all": [],
            "twice_nll": None,
            "status": "failed",
            "error": str(exc),
            "n_pars": int(len(model.config.par_names)),
            "backend": "pyhf",
        }


def run_fit(workspace_path: Path, backend: str = "pyhf") -> Dict[str, Any]:
    backend_name = str(backend).strip().lower()
    if backend_name == "pyhf":
        return _run_pyhf_fit(workspace_path)
    if backend_name == "pyroot_roofit":
        return run_roofit_fit(workspace_path)
    return {
        "status": "failed",
        "poi_name": "mu",
        "bestfit_poi": 1.0,
        "bestfit_all": [],
        "twice_nll": None,
        "n_pars": 0,
        "backend": backend_name,
        "error": "Unsupported fit backend '{}'".format(backend),
    }



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run statistical fit")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--fit-id", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--backend", default="pyhf", choices=["pyhf", "pyroot_roofit"])
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    result = run_fit(Path(args.workspace), backend=args.backend)
    result["fit_id"] = args.fit_id

    out_path = Path(args.out)
    ensure_dir(out_path.parent)
    write_json(out_path, result)

    print(
        "fit {} backend={} status={} poi({})={:.6g}".format(
            args.fit_id,
            result.get("backend", args.backend),
            result["status"],
            result["poi_name"],
            result["bestfit_poi"],
        )
    )


if __name__ == "__main__":
    main()
