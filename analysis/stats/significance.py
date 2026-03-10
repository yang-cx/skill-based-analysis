# FILE: analysis/stats/significance.py
"""Compute profile-likelihood discovery significance for H->gammagamma."""

import argparse
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
from scipy.optimize import minimize

from analysis.common import ensure_dir, write_json
from analysis.stats.fit import (
    FIT_LOW,
    FIT_HIGH,
    bernstein_pdf_eval,
    bernstein_norm,
    dscb_pdf,
    extended_nll,
    run_hgg_fit,
)


def run_hgg_fit_fixed_mu(
    mgg_data: np.ndarray,
    dscb_params: Dict,
    bkg_degree: int,
    mu_fixed: float = 0.0,
    n_sig_expected: float = 50.0,
) -> float:
    """Run fit with signal strength mu fixed.

    Returns NLL at fixed mu.
    """
    n_data = len(mgg_data)
    n_coeffs = bkg_degree + 1

    # With fixed mu, N_sig = mu * n_sig_expected (fixed)
    n_sig_fixed = mu_fixed * n_sig_expected
    n_bkg_init = max(n_data - n_sig_fixed, 1.0)

    # Only optimize background params (N_bkg + coefficients)
    # params: [log(N_bkg+1), c0, c1, ..., c_degree]
    x0 = np.concatenate([
        [np.log(n_bkg_init + 1)],
        np.ones(n_coeffs) / n_coeffs,
    ])

    def objective_fixed(p):
        n_bkg = max(0.0, np.exp(p[0]) - 1.0)
        bkg_coeffs = p[1 : 1 + n_coeffs]

        N_tot = n_sig_fixed + n_bkg
        if N_tot <= 0:
            return 1e10

        sig_unnorm = dscb_pdf(mgg_data, **dscb_params)
        x_norm = np.linspace(FIT_LOW, FIT_HIGH, 1000)
        sig_norm_val = np.trapezoid(dscb_pdf(x_norm, **dscb_params), x_norm)
        sig_pdf = sig_unnorm / max(sig_norm_val, 1e-30)

        bkg_unnorm = bernstein_pdf_eval(mgg_data, bkg_coeffs)
        bkg_norm_val = bernstein_norm(bkg_coeffs)
        bkg_pdf = bkg_unnorm / max(bkg_norm_val, 1e-30)

        combined = (n_sig_fixed * sig_pdf + n_bkg * bkg_pdf) / N_tot
        combined = np.maximum(combined, 1e-30)

        nll = N_tot - len(mgg_data) * np.log(N_tot) + np.sum(-np.log(combined))
        return float(nll)

    result = minimize(
        objective_fixed,
        x0,
        method="L-BFGS-B",
        options={"maxiter": 5000, "ftol": 1e-10},
    )

    return float(result.fun)


def compute_q0(
    mgg_data: np.ndarray,
    dscb_params: Dict,
    bkg_degree: int,
    n_sig_expected: float = 50.0,
) -> Tuple[float, float, Dict, Dict]:
    """Compute q0 test statistic and discovery significance.

    q0 = max(0, 2 * (NLL_mu0 - NLL_muhat))
    Z = sqrt(q0)

    Returns (q0, Z, fit_result_muhat, fit_result_mu0).
    """
    # Fit with mu free (find mu_hat)
    fit_free = run_hgg_fit(
        mgg_data, dscb_params, bkg_degree,
        n_sig_init=max(n_sig_expected * 0.1, 1.0),
    )

    nll_muhat = fit_free["nll"]

    # Fit with mu=0 (background only)
    nll_mu0 = run_hgg_fit_fixed_mu(
        mgg_data, dscb_params, bkg_degree,
        mu_fixed=0.0,
        n_sig_expected=n_sig_expected,
    )

    mu_hat = fit_free["bestfit_n_sig"] / max(n_sig_expected, 1.0)

    # q0 only valid when mu_hat >= 0
    if mu_hat < 0:
        q0 = 0.0
    else:
        q0 = max(0.0, 2.0 * (nll_mu0 - nll_muhat))

    z = float(np.sqrt(q0))

    return q0, z, fit_free, {"nll": nll_mu0, "mu_fixed": 0.0}


def generate_asimov_data(
    dscb_params: Dict,
    bkg_coeffs: np.ndarray,
    n_bkg: float,
    n_sig: float = 0.0,
    n_points: int = 10000,
    seed: int = 42,
) -> np.ndarray:
    """Generate Asimov pseudo-data from background-only model.

    Returns array of mgg values sampled from the background PDF.
    """
    rng = np.random.default_rng(seed)

    x = np.linspace(FIT_LOW, FIT_HIGH, 10000)

    # Background PDF
    bkg_pdf = bernstein_pdf_eval(x, bkg_coeffs)
    bkg_norm = np.trapezoid(bkg_pdf, x)
    if bkg_norm > 0:
        bkg_pdf = bkg_pdf / bkg_norm

    # Signal PDF
    if n_sig > 0:
        sig_pdf = dscb_pdf(x, **dscb_params)
        sig_norm = np.trapezoid(sig_pdf, x)
        if sig_norm > 0:
            sig_pdf = sig_pdf / sig_norm
        total_pdf = (n_bkg * bkg_pdf + n_sig * sig_pdf) / (n_bkg + n_sig)
    else:
        total_pdf = bkg_pdf

    # Sample using inverse CDF method
    total_pdf = np.maximum(total_pdf, 0.0)
    cdf = np.cumsum(total_pdf)
    cdf = cdf / cdf[-1]

    u = rng.uniform(0, 1, int(n_bkg + n_sig))
    asimov = np.interp(u, cdf, x)
    return asimov


def compute_significance(
    workspace_path: str,
    fit_results_path: Optional[str] = None,
    out_path: Optional[str] = None,
) -> Dict:
    """Compute observed and Asimov significance.

    Returns significance dict.
    """
    with open(workspace_path) as f:
        workspace = json.load(f)

    ws_type = workspace.get("type", "")

    if ws_type != "hgg_unbinned":
        return {
            "status": "error",
            "error": f"Unsupported workspace type: {ws_type}",
            "observed_q0": None,
            "observed_Z": None,
            "asimov_q0": None,
            "asimov_Z": None,
        }

    mgg_data = np.array(workspace.get("data", []))
    dscb_params = workspace.get("signal_pdf", {}).get("parameters", {})
    bkg_info = workspace.get("background_pdf", {})
    bkg_degree = bkg_info.get("degree", 3)
    n_sig_expected = workspace.get("n_sig_expected", 50.0)
    bkg_coeffs_init = np.array(bkg_info.get("coefficients_init", [1.0] * (bkg_degree + 1)))

    if len(mgg_data) == 0:
        print("Warning: no data; generating synthetic background-only data.")
        mgg_data = generate_asimov_data(
            dscb_params, bkg_coeffs_init, n_bkg=1000.0, n_sig=0.0
        )

    print(f"Computing observed significance on {len(mgg_data)} events...")
    obs_q0, obs_Z, fit_free, fit_mu0 = compute_q0(
        mgg_data, dscb_params, bkg_degree, n_sig_expected=n_sig_expected
    )

    mu_hat = fit_free["bestfit_n_sig"] / max(n_sig_expected, 1.0)
    sigma_mu = fit_free["sigma_n_sig"] / max(n_sig_expected, 1.0)

    print(f"  Observed: q0={obs_q0:.3f}, Z={obs_Z:.3f} sigma, mu_hat={mu_hat:.2f}")

    # Asimov significance: generate bkg-only data, test significance
    print("Computing Asimov significance...")
    bkg_coeffs_fit = np.array(fit_free.get("bestfit_bkg_coeffs", bkg_coeffs_init))
    n_bkg_fit = fit_free.get("bestfit_n_bkg", len(mgg_data))

    asimov_data = generate_asimov_data(
        dscb_params,
        bkg_coeffs_fit,
        n_bkg=n_bkg_fit,
        n_sig=0.0,
    )

    asimov_q0, asimov_Z, _, _ = compute_q0(
        asimov_data, dscb_params, bkg_degree, n_sig_expected=n_sig_expected
    )

    print(f"  Asimov: q0={asimov_q0:.3f}, Z={asimov_Z:.3f} sigma")

    result = {
        "status": "ok",
        "n_data": len(mgg_data),
        "n_sig_expected": n_sig_expected,
        "bestfit_mu": float(mu_hat),
        "sigma_mu": float(sigma_mu),
        "observed": {
            "q0": float(obs_q0),
            "Z": float(obs_Z),
            "nll_muhat": float(fit_free["nll"]),
            "nll_mu0": float(fit_mu0["nll"]),
        },
        "asimov": {
            "q0": float(asimov_q0),
            "Z": float(asimov_Z),
            "n_asimov": len(asimov_data),
        },
        "dscb_parameters": dscb_params,
        "bkg_degree": bkg_degree,
    }

    if out_path is not None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(out_path, result)
        print(f"Significance written to {out_path}")

    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compute profile-likelihood discovery significance."
    )
    p.add_argument("--workspace", required=True, help="Path to workspace JSON")
    p.add_argument("--fit-id", required=True, help="Fit ID (e.g. FIT_MAIN)")
    p.add_argument("--out", required=True, help="Output significance JSON path")
    p.add_argument("--backend", default="pyhf", help="Fit backend")
    p.add_argument("--pyhf-backend", default="native", help="pyhf backend")
    p.add_argument(
        "--fit-results",
        default=None,
        help="Path to existing fit results JSON (optional)",
    )
    return p


def main():
    args = build_parser().parse_args()

    result = compute_significance(
        workspace_path=args.workspace,
        fit_results_path=args.fit_results,
        out_path=args.out,
    )

    obs_Z = result.get("observed", {}).get("Z")
    asimov_Z = result.get("asimov", {}).get("Z")
    print(f"Observed significance: {obs_Z:.3f} sigma")
    print(f"Asimov significance:   {asimov_Z:.3f} sigma")


if __name__ == "__main__":
    main()
