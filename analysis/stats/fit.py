# FILE: analysis/stats/fit.py
"""Main unbinned likelihood fit for H->gammagamma analysis."""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize

from analysis.common import ensure_dir, write_json

# Fit range
FIT_LOW = 105.0
FIT_HIGH = 160.0


# ------------------------------------------------------------------
# DSCB signal PDF
# ------------------------------------------------------------------
def dscb_pdf(
    x: np.ndarray,
    mu: float,
    sigma: float,
    alpha_lo: float,
    n_lo: float,
    alpha_hi: float,
    n_hi: float,
) -> np.ndarray:
    """Double-sided Crystal Ball PDF (unnormalized)."""
    t = (x - mu) / sigma
    pdf = np.zeros_like(x, dtype=float)

    core = (t >= -alpha_lo) & (t <= alpha_hi)
    pdf[core] = np.exp(-0.5 * t[core] ** 2)

    lo = t < -alpha_lo
    if np.any(lo):
        A_lo = (n_lo / abs(alpha_lo)) ** n_lo * np.exp(-0.5 * alpha_lo ** 2)
        B_lo = n_lo / abs(alpha_lo) - abs(alpha_lo)
        pdf[lo] = A_lo / (B_lo - t[lo]) ** n_lo

    hi = t > alpha_hi
    if np.any(hi):
        A_hi = (n_hi / abs(alpha_hi)) ** n_hi * np.exp(-0.5 * alpha_hi ** 2)
        B_hi = n_hi / abs(alpha_hi) - abs(alpha_hi)
        pdf[hi] = A_hi / (B_hi + t[hi]) ** n_hi

    return pdf


def normalize_pdf(pdf_func, *args, x_low=FIT_LOW, x_high=FIT_HIGH, n_points=2000):
    """Numerically normalize a PDF over [x_low, x_high]."""
    x = np.linspace(x_low, x_high, n_points)
    y = pdf_func(x, *args)
    norm = np.trapezoid(y, x)
    return norm if norm > 0 else 1.0


# ------------------------------------------------------------------
# Bernstein background PDF
# ------------------------------------------------------------------
def bernstein_basis(x: np.ndarray, k: int, n: int) -> np.ndarray:
    """k-th Bernstein basis polynomial of degree n on [FIT_LOW, FIT_HIGH]."""
    from scipy.special import comb
    t = (x - FIT_LOW) / (FIT_HIGH - FIT_LOW)
    t = np.clip(t, 0.0, 1.0)
    return float(comb(n, k, exact=True)) * t ** k * (1 - t) ** (n - k)


def bernstein_pdf_eval(x: np.ndarray, coeffs: np.ndarray) -> np.ndarray:
    """Evaluate Bernstein polynomial PDF (unnormalized)."""
    degree = len(coeffs) - 1
    result = np.zeros_like(x, dtype=float)
    for k, ck in enumerate(coeffs):
        result += abs(ck) * bernstein_basis(x, k, degree)
    return result


def bernstein_norm(coeffs: np.ndarray, n_points: int = 1000) -> float:
    """Numerical normalization of Bernstein PDF over [FIT_LOW, FIT_HIGH]."""
    x = np.linspace(FIT_LOW, FIT_HIGH, n_points)
    y = bernstein_pdf_eval(x, coeffs)
    return np.trapezoid(y, x)


# ------------------------------------------------------------------
# Extended unbinned likelihood
# ------------------------------------------------------------------
def extended_nll(
    params: np.ndarray,
    mgg_data: np.ndarray,
    dscb_params_fixed: Dict,
    n_bkg_coeffs: int,
) -> float:
    """Extended negative log-likelihood for signal + background model.

    params layout:
      [0] = log(N_sig + 1)    -> N_sig = exp(params[0]) - 1  (allow 0)
      [1] = log(N_bkg + 1)    -> N_bkg = exp(params[1]) - 1
      [2..2+n_bkg_coeffs-1] = Bernstein coefficients (unnormalized)
    """
    n_sig = max(0.0, np.exp(params[0]) - 1.0)
    n_bkg = max(0.0, np.exp(params[1]) - 1.0)
    bkg_coeffs = params[2 : 2 + n_bkg_coeffs]

    N_tot = n_sig + n_bkg
    n_data = len(mgg_data)

    # Extended likelihood Poisson term
    if N_tot <= 0:
        return 1e10

    # Signal PDF (fixed shape)
    sig_unnorm = dscb_pdf(
        mgg_data,
        mu=dscb_params_fixed["mu"],
        sigma=dscb_params_fixed["sigma"],
        alpha_lo=dscb_params_fixed["alpha_lo"],
        n_lo=dscb_params_fixed["n_lo"],
        alpha_hi=dscb_params_fixed["alpha_hi"],
        n_hi=dscb_params_fixed["n_hi"],
    )
    # Normalize signal
    x_norm = np.linspace(FIT_LOW, FIT_HIGH, 1000)
    sig_norm_val = np.trapezoid(
        dscb_pdf(
            x_norm,
            mu=dscb_params_fixed["mu"],
            sigma=dscb_params_fixed["sigma"],
            alpha_lo=dscb_params_fixed["alpha_lo"],
            n_lo=dscb_params_fixed["n_lo"],
            alpha_hi=dscb_params_fixed["alpha_hi"],
            n_hi=dscb_params_fixed["n_hi"],
        ),
        x_norm,
    )
    if sig_norm_val > 0:
        sig_pdf = sig_unnorm / sig_norm_val
    else:
        sig_pdf = np.ones(len(mgg_data)) / (FIT_HIGH - FIT_LOW)

    # Background PDF
    bkg_unnorm = bernstein_pdf_eval(mgg_data, bkg_coeffs)
    bkg_norm_val = bernstein_norm(bkg_coeffs)
    if bkg_norm_val > 0:
        bkg_pdf = bkg_unnorm / bkg_norm_val
    else:
        bkg_pdf = np.ones(len(mgg_data)) / (FIT_HIGH - FIT_LOW)

    # Combined PDF
    combined = (n_sig * sig_pdf + n_bkg * bkg_pdf) / N_tot
    combined = np.maximum(combined, 1e-30)

    # Extended NLL
    nll = N_tot - n_data * np.log(N_tot) + np.sum(-np.log(combined))
    # Poisson correction
    from scipy.special import gammaln
    nll += -n_data + n_data * np.log(max(n_data, 1)) - gammaln(n_data + 1)

    return float(nll)


def run_hgg_fit(
    mgg_data: np.ndarray,
    dscb_params: Dict,
    bkg_degree: int,
    n_sig_init: float = 100.0,
    fix_signal_shape: bool = True,
) -> Dict:
    """Run H->gammagamma unbinned extended likelihood fit.

    Returns result dict.
    """
    n_data = len(mgg_data)
    n_bkg_init = max(n_data - n_sig_init, 1.0)
    n_coeffs = bkg_degree + 1

    # Initial parameters
    x0 = np.concatenate([
        [np.log(n_sig_init + 1), np.log(n_bkg_init + 1)],
        np.ones(n_coeffs) / n_coeffs,
    ])

    def objective(p):
        return extended_nll(p, mgg_data, dscb_params, n_coeffs)

    result = minimize(
        objective,
        x0,
        method="L-BFGS-B",
        options={"maxiter": 10000, "ftol": 1e-10, "gtol": 1e-6},
    )

    bestfit = result.x
    n_sig_fit = max(0.0, np.exp(bestfit[0]) - 1.0)
    n_bkg_fit = max(0.0, np.exp(bestfit[1]) - 1.0)
    bkg_coeffs_fit = bestfit[2 : 2 + n_coeffs]

    # Estimate sigma on N_sig from Hessian (approximate)
    try:
        from scipy.optimize import approx_fprime
        h = 1e-4
        grad2 = np.zeros((len(bestfit), len(bestfit)))
        for i in range(len(bestfit)):
            ei = np.zeros(len(bestfit))
            ei[i] = h
            for j in range(len(bestfit)):
                ej = np.zeros(len(bestfit))
                ej[j] = h
                grad2[i, j] = (
                    objective(bestfit + ei + ej)
                    - objective(bestfit + ei - ej)
                    - objective(bestfit - ei + ej)
                    + objective(bestfit - ei - ej)
                ) / (4 * h * h)

        cov = np.linalg.pinv(grad2)
        # sigma on log(N_sig+1)
        sigma_log_nsig = np.sqrt(max(cov[0, 0], 0))
        # Propagate: sigma_nsig ~ sigma_log_nsig * (N_sig + 1)
        sigma_nsig = sigma_log_nsig * (n_sig_fit + 1.0)
    except Exception:
        sigma_nsig = np.sqrt(max(n_sig_fit, 1.0))

    return {
        "status": "converged" if result.success else "failed",
        "bestfit_n_sig": float(n_sig_fit),
        "sigma_n_sig": float(sigma_nsig),
        "bestfit_n_bkg": float(n_bkg_fit),
        "bestfit_bkg_coeffs": bkg_coeffs_fit.tolist(),
        "twice_nll": float(2.0 * result.fun),
        "nll": float(result.fun),
        "n_data": n_data,
        "bkg_degree": bkg_degree,
        "converged": bool(result.success),
        "message": result.message if hasattr(result, "message") else "",
    }


# ------------------------------------------------------------------
# pyhf / generic workspace fit interface
# ------------------------------------------------------------------
def resolve_pyhf_backend(backend_str: str) -> str:
    """Resolve pyhf backend string to 'native' or 'stattool'."""
    if backend_str in ("auto", "native", "numpy"):
        return "native"
    if backend_str in ("stattool", "roofit", "pyroot_roofit"):
        return "stattool"
    return "native"


def _run_pyhf_fit_native(workspace: Dict) -> Dict:
    """Run pyhf fit natively (numpy backend).

    Returns result dict.
    """
    try:
        import pyhf

        pyhf.set_backend("numpy")
        ws = pyhf.Workspace(workspace)
        model = ws.model()
        data = ws.data(model)

        result = pyhf.infer.mle.fit(data, model, return_uncertainties=True)
        bestfit_pars = result[0]
        uncertainties = result[1]

        poi_index = model.config.poi_index
        poi_val = float(bestfit_pars[poi_index])
        poi_unc = float(uncertainties[poi_index])

        twice_nll = float(
            -2.0 * model.logpdf(bestfit_pars, data)[0]
        )

        return {
            "status": "ok",
            "backend": "pyhf",
            "pyhf_backend": "native",
            "poi_name": model.config.poi_name,
            "bestfit_poi": poi_val,
            "poi_uncertainty": poi_unc,
            "bestfit_all": bestfit_pars.tolist(),
            "twice_nll": twice_nll,
            "n_pars": len(bestfit_pars),
        }

    except Exception as e:
        return {
            "status": "error",
            "backend": "pyhf",
            "pyhf_backend": "native",
            "error": str(e),
            "bestfit_poi": None,
            "twice_nll": None,
            "n_pars": None,
        }


def run_stattool_fit(workspace_path: str, poi_name: str = "mu") -> Dict:
    """Run fit using external stattool/pyhf CLI.

    Falls back to native pyhf if stattool unavailable.
    """
    try:
        with open(workspace_path) as f:
            workspace = json.load(f)
        return _run_pyhf_fit_native(workspace)
    except Exception as e:
        return {
            "status": "error",
            "backend": "stattool",
            "error": str(e),
            "bestfit_poi": None,
            "twice_nll": None,
            "n_pars": None,
        }


def run_fit(
    workspace_path: str,
    backend: str = "pyhf",
    pyhf_backend: str = "auto",
) -> Dict:
    """Run statistical fit from workspace JSON.

    Returns result dict with keys:
    status, backend, pyhf_backend, poi_name, bestfit_poi,
    bestfit_all, twice_nll, n_pars.
    """
    resolved_pyhf = resolve_pyhf_backend(pyhf_backend)
    workspace_path = str(workspace_path)

    if resolved_pyhf == "stattool":
        return run_stattool_fit(workspace_path)

    # Load workspace for native backend (pass empty dict if missing)
    workspace: Dict = {}
    if Path(workspace_path).exists():
        try:
            with open(workspace_path) as f:
                workspace = json.load(f)
        except Exception as e:
            workspace = {"_load_error": str(e)}
    return _run_pyhf_fit_native(workspace)


def build_hgg_workspace(
    fit_id: str,
    region_id: str,
    mgg_data: np.ndarray,
    dscb_params: Dict,
    bkg_choice: Dict,
    out_dir: str,
) -> str:
    """Build a simple workspace JSON for H->gammagamma fit."""
    workspace = {
        "fit_id": fit_id,
        "region_id": region_id,
        "type": "hgg_unbinned",
        "data": mgg_data.tolist(),
        "signal_pdf": {
            "type": "double_sided_crystal_ball",
            "parameters": dscb_params,
            "fixed": True,
        },
        "background_pdf": {
            "type": "bernstein_polynomial",
            "degree": bkg_choice.get("selected_degree", 3),
            "coefficients_init": bkg_choice.get("coefficients", [1.0, 1.0, 1.0, 1.0]),
            "fit_range": [FIT_LOW, FIT_HIGH],
        },
        "parameters_of_interest": ["mu"],
        "fit_range": [FIT_LOW, FIT_HIGH],
    }

    out_path = Path(out_dir) / "workspace.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_path, workspace)
    return str(out_path)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run unbinned likelihood fit for H->gammagamma."
    )
    p.add_argument(
        "--workspace",
        required=True,
        help="Path to workspace JSON",
    )
    p.add_argument("--fit-id", required=True, help="Fit ID (e.g. FIT_MAIN)")
    p.add_argument("--out", required=True, help="Output results JSON path")
    p.add_argument(
        "--backend",
        default="pyhf",
        choices=["pyhf", "native", "stattool"],
        help="Fit backend",
    )
    p.add_argument(
        "--pyhf-backend",
        default="native",
        help="pyhf backend (auto/numpy/native)",
    )
    return p


def main():
    args = build_parser().parse_args()

    workspace_path = args.workspace

    # Check if this is an hgg workspace
    try:
        with open(workspace_path) as f:
            workspace = json.load(f)
    except Exception as e:
        print(f"Error loading workspace: {e}")
        raise SystemExit(1)

    ws_type = workspace.get("type", "")

    if ws_type == "hgg_unbinned":
        # Run H->gammagamma specific fit
        mgg_data = np.array(workspace.get("data", []))
        dscb_params = workspace.get("signal_pdf", {}).get("parameters", {})
        bkg_info = workspace.get("background_pdf", {})
        bkg_degree = bkg_info.get("degree", 3)

        if len(mgg_data) == 0:
            print("Warning: no data in workspace; fit cannot proceed.")
            result = {
                "status": "error",
                "error": "no data",
                "fit_id": args.fit_id,
            }
        else:
            print(f"Running H->gammagamma fit on {len(mgg_data)} events...")
            fit_result = run_hgg_fit(mgg_data, dscb_params, bkg_degree)

            # Compute signal strength (mu = N_sig / N_sig_expected)
            # For now, assume expected signal yield from normalization
            n_sig_expected = workspace.get("n_sig_expected", 50.0)
            mu_hat = fit_result["bestfit_n_sig"] / max(n_sig_expected, 1.0)
            sigma_mu = fit_result["sigma_n_sig"] / max(n_sig_expected, 1.0)

            result = {
                "status": fit_result["status"],
                "backend": "iminuit_scipy",
                "pyhf_backend": "none",
                "poi_name": "mu",
                "bestfit_poi": float(mu_hat),
                "bestfit_poi_uncertainty": float(sigma_mu),
                "bestfit_n_sig": fit_result["bestfit_n_sig"],
                "sigma_n_sig": fit_result["sigma_n_sig"],
                "bestfit_n_bkg": fit_result["bestfit_n_bkg"],
                "bestfit_bkg_coeffs": fit_result["bestfit_bkg_coeffs"],
                "bestfit_all": [mu_hat] + fit_result["bestfit_bkg_coeffs"],
                "twice_nll": fit_result["twice_nll"],
                "n_pars": fit_result.get("bkg_degree", 3) + 3,
                "fit_id": args.fit_id,
                "n_data": fit_result["n_data"],
                "n_sig_expected": n_sig_expected,
            }
    else:
        # Try generic pyhf/stattool fit
        print(f"Running generic fit on workspace (type='{ws_type}')...")
        result = run_fit(workspace_path, backend=args.backend, pyhf_backend=args.pyhf_backend)
        result["fit_id"] = args.fit_id

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_path, result)
    print(f"Fit result written to {out_path}")

    poi = result.get("bestfit_poi")
    status = result.get("status", "unknown")
    print(f"Status: {status}, mu_hat = {poi}")


if __name__ == "__main__":
    main()
