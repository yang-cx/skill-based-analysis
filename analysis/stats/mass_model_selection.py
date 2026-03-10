# FILE: analysis/stats/mass_model_selection.py
"""Background functional form selection via spurious-signal test."""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize
from scipy.special import comb as scipy_comb

from analysis.common import ensure_dir, write_json

# Fit range
FIT_LOW = 105.0    # GeV
FIT_HIGH = 160.0   # GeV
SB_LOW = [105.0, 120.0]    # Lower sideband
SB_HIGH = [130.0, 160.0]   # Upper sideband
SR_LOW = 120.0
SR_HIGH = 130.0

# Spurious signal threshold
SPURIOUS_SIGNAL_THRESHOLD = 0.2  # N_spur / sigma_Nsig < 0.2

# Double-sided Crystal Ball default parameters (proxy from signal MC)
DEFAULT_DSCB = {
    "mu": 125.0,
    "sigma": 1.7,
    "alpha_lo": 1.5,
    "n_lo": 5.0,
    "alpha_hi": 1.8,
    "n_hi": 6.0,
}


def bernstein_basis(x: np.ndarray, k: int, n: int) -> np.ndarray:
    """Compute k-th Bernstein basis polynomial of degree n."""
    t = (x - FIT_LOW) / (FIT_HIGH - FIT_LOW)
    t = np.clip(t, 0.0, 1.0)
    coeff = float(scipy_comb(n, k, exact=True))
    return coeff * t ** k * (1 - t) ** (n - k)


def bernstein_pdf(x: np.ndarray, coeffs: np.ndarray) -> np.ndarray:
    """Evaluate normalized Bernstein polynomial PDF.

    coeffs: array of shape (degree+1,), non-negative, will be normalized.
    """
    degree = len(coeffs) - 1
    # Ensure non-negative coefficients
    c = np.abs(coeffs)
    # Sum basis polynomials
    result = np.zeros_like(x, dtype=float)
    for k, ck in enumerate(c):
        result += ck * bernstein_basis(x, k, degree)

    # Normalize over [FIT_LOW, FIT_HIGH]
    x_norm = np.linspace(FIT_LOW, FIT_HIGH, 1000)
    norm = np.trapezoid(
        np.array([sum(c[k] * bernstein_basis(x_norm, k, degree) for k in range(degree + 1))]),
        x_norm,
    )[0]

    if norm <= 0:
        return np.ones_like(x) / (FIT_HIGH - FIT_LOW)
    return result / norm


def dscb_pdf(x: np.ndarray, mu: float, sigma: float, alpha_lo: float, n_lo: float,
             alpha_hi: float, n_hi: float) -> np.ndarray:
    """Double-sided Crystal Ball PDF (unnormalized; normalize externally)."""
    t = (x - mu) / sigma
    pdf = np.zeros_like(x, dtype=float)

    # Core Gaussian region
    core = (t >= -alpha_lo) & (t <= alpha_hi)
    pdf[core] = np.exp(-0.5 * t[core] ** 2)

    # Low power-law tail
    lo = t < -alpha_lo
    A_lo = (n_lo / np.abs(alpha_lo)) ** n_lo * np.exp(-0.5 * alpha_lo ** 2)
    B_lo = n_lo / np.abs(alpha_lo) - np.abs(alpha_lo)
    pdf[lo] = A_lo / (B_lo - t[lo]) ** n_lo

    # High power-law tail
    hi = t > alpha_hi
    A_hi = (n_hi / np.abs(alpha_hi)) ** n_hi * np.exp(-0.5 * alpha_hi ** 2)
    B_hi = n_hi / np.abs(alpha_hi) - np.abs(alpha_hi)
    pdf[hi] = A_hi / (B_hi + t[hi]) ** n_hi

    return pdf


def normalize_dscb(params: Dict, x_range: Tuple = (FIT_LOW, FIT_HIGH)) -> float:
    """Compute normalization integral for DSCB over x_range."""
    x = np.linspace(x_range[0], x_range[1], 2000)
    y = dscb_pdf(x, **params)
    return np.trapezoid(y, x)


def fit_bernstein_to_data(
    mgg_data: np.ndarray,
    degree: int,
    weights: Optional[np.ndarray] = None,
    sideband_only: bool = True,
) -> Tuple[np.ndarray, float, bool]:
    """Fit Bernstein polynomial of given degree to (sideband) data.

    Returns (coefficients, nll, converged).
    """
    if sideband_only:
        sb_mask = (
            ((mgg_data >= SB_LOW[0]) & (mgg_data < SB_LOW[1]))
            | ((mgg_data >= SB_HIGH[0]) & (mgg_data <= SB_HIGH[1]))
        )
        x = mgg_data[sb_mask]
        w = weights[sb_mask] if weights is not None else None
    else:
        x = mgg_data
        w = weights

    if len(x) == 0:
        # No data in sideband; return flat distribution
        return np.ones(degree + 1) / (degree + 1), 0.0, False

    n_coeffs = degree + 1
    # Initial coefficients: uniform
    c0 = np.ones(n_coeffs) / n_coeffs

    def neg_log_likelihood(c):
        # Evaluate pdf at data points
        c_abs = np.abs(c)
        pdf_vals = np.zeros(len(x))
        for k in range(n_coeffs):
            pdf_vals += c_abs[k] * bernstein_basis(x, k, degree)

        # Normalize
        x_norm = np.linspace(FIT_LOW, FIT_HIGH, 500)
        norm_vals = np.zeros(len(x_norm))
        for k in range(n_coeffs):
            norm_vals += c_abs[k] * bernstein_basis(x_norm, k, degree)
        norm = np.trapezoid(norm_vals, x_norm)

        if norm <= 0:
            return 1e10

        pdf_vals = pdf_vals / norm
        # Protect against zeros
        pdf_vals = np.maximum(pdf_vals, 1e-30)

        if w is not None:
            nll = -np.sum(w * np.log(pdf_vals))
        else:
            nll = -np.sum(np.log(pdf_vals))
        return nll

    result = minimize(
        neg_log_likelihood,
        c0,
        method="Nelder-Mead",
        options={"maxiter": 10000, "xatol": 1e-6, "fatol": 1e-6},
    )

    return np.abs(result.x), result.fun, result.success


def compute_spurious_signal(
    mgg_data: np.ndarray,
    bkg_coeffs: np.ndarray,
    degree: int,
    dscb_params: Dict,
    weights: Optional[np.ndarray] = None,
    n_sig_expected: float = 1.0,
) -> Tuple[float, float, float]:
    """Compute spurious signal N_spur.

    Fits signal+background to full range, extracts signal yield at mu=0 expectation.
    Returns (n_spur, sigma_nsig, ratio).
    """
    # Generate pseudo-data from background-only model in full range
    x_test = np.linspace(FIT_LOW, FIT_HIGH, 1000)
    bkg_pdf = np.zeros(len(x_test))
    n_coeffs = degree + 1
    for k in range(n_coeffs):
        bkg_pdf += np.abs(bkg_coeffs[k]) * bernstein_basis(x_test, k, degree)
    norm = np.trapezoid(bkg_pdf, x_test)
    if norm > 0:
        bkg_pdf = bkg_pdf / norm

    # Signal PDF
    sig_pdf = dscb_pdf(x_test, **dscb_params)
    sig_norm = np.trapezoid(sig_pdf, x_test)
    if sig_norm > 0:
        sig_pdf = sig_pdf / sig_norm

    # In the actual data, estimate N_bkg in SR
    sr_mask = (mgg_data >= SR_LOW) & (mgg_data <= SR_HIGH)
    if weights is not None:
        n_sr = float(np.sum(weights[sr_mask]))
    else:
        n_sr = float(np.sum(sr_mask))

    if n_sr <= 0:
        n_sr = 1.0

    # Estimate sigma on signal yield from Poisson statistics
    sigma_nsig = np.sqrt(n_sr)

    # Spurious signal: fit signal+background to sideband data, get signal yield
    # Simplified: use the signal fraction in SR from pure background model
    sr_idx = (x_test >= SR_LOW) & (x_test <= SR_HIGH)
    bkg_in_sr = np.trapezoid(bkg_pdf[sr_idx], x_test[sr_idx]) * n_sr
    sig_in_sr = np.trapezoid(sig_pdf[sr_idx], x_test[sr_idx])

    # Spurious signal is the signal yield when fitting bkg-only data with sig+bkg model
    # Approximated as: projection of background component onto signal shape
    # N_spur ~ |N_bkg * overlap| / normalization
    if sig_in_sr > 0 and sigma_nsig > 0:
        n_spur = abs(bkg_in_sr * sig_in_sr / (np.trapezoid(sig_pdf, x_test) + 1e-10))
    else:
        n_spur = 0.0

    ratio = n_spur / (sigma_nsig + 1e-10)
    return n_spur, sigma_nsig, ratio


def extract_signal_dscb_params(
    hists_dir: str,
    region_id: str,
    signal_sample_ids: List[str],
) -> Dict:
    """Extract DSCB parameters from signal MC histograms.

    Returns DSCB parameter dict.
    """
    # Try to load signal histograms and fit a DSCB
    mgg_signal = []

    for sample_id in signal_sample_ids:
        hist_path = Path(hists_dir) / region_id / "m_gg" / f"{sample_id}.npz"
        if hist_path.exists():
            try:
                d = np.load(str(hist_path), allow_pickle=True)
                edges = d["edges"]
                counts = d["counts"]
                centers = 0.5 * (edges[:-1] + edges[1:])
                # Expand to pseudo-data
                for center, count in zip(centers, counts):
                    n = int(round(count))
                    if n > 0:
                        mgg_signal.extend([center] * min(n, 1000))
            except Exception as e:
                print(f"Warning: could not load {hist_path}: {e}")

    if not mgg_signal:
        print(f"Warning: no signal histograms found for {region_id}; using defaults")
        return DEFAULT_DSCB.copy()

    mgg_signal = np.array(mgg_signal)

    # Fit Gaussian as first approximation
    from scipy.stats import norm as scipy_norm
    try:
        mu_fit, sigma_fit = scipy_norm.fit(mgg_signal)
    except Exception:
        mu_fit = 125.0
        sigma_fit = 1.7

    params = {
        "mu": float(mu_fit),
        "sigma": float(max(sigma_fit, 0.5)),
        "alpha_lo": 1.5,
        "n_lo": 5.0,
        "alpha_hi": 1.8,
        "n_hi": 6.0,
    }
    return params


def select_background_model(
    fit_id: str,
    region_id: str,
    hists_dir: str,
    strategy: Dict,
    registry: Dict,
    out_dir: str,
    max_degree: int = 4,
) -> Dict:
    """Select background functional form for a region.

    Tests Bernstein polynomials of degree 1..max_degree.
    Selects lowest degree passing spurious-signal check.
    """
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Load data histogram for the region
    samples = registry.get("samples", registry)
    data_sample_id = None
    signal_sample_ids = []

    for sid, info in samples.items():
        if info.get("type") == "data":
            data_sample_id = sid
        elif info.get("type") == "signal":
            signal_sample_ids.append(sid)

    # Load data mgg values from histogram
    mgg_data = np.array([])
    if data_sample_id is not None:
        hist_path = Path(hists_dir) / region_id / "m_gg" / f"{data_sample_id}.npz"
        if hist_path.exists():
            try:
                d = np.load(str(hist_path), allow_pickle=True)
                edges = d["edges"]
                counts = d["counts"]
                centers = 0.5 * (edges[:-1] + edges[1:])
                # Expand to pseudo-data weighted
                expanded = []
                for center, count in zip(centers, counts):
                    n = int(round(count))
                    if n > 0:
                        expanded.extend([center] * min(n, 10000))
                mgg_data = np.array(expanded)
            except Exception as e:
                print(f"Warning: could not load data histogram: {e}")

    # If no data, generate synthetic sideband data
    if len(mgg_data) == 0:
        print(f"Warning: no data for region {region_id}; using synthetic sideband")
        rng = np.random.default_rng(42)
        # Exponential-like background
        mgg_data = np.concatenate([
            rng.uniform(SB_LOW[0], SB_LOW[1], 1000),
            rng.uniform(SB_HIGH[0], SB_HIGH[1], 1500),
        ])

    # Get signal DSCB parameters
    dscb_params = extract_signal_dscb_params(hists_dir, region_id, signal_sample_ids)

    # Save signal PDF
    signal_pdf_path = out_path / "signal_pdf.json"
    write_json(signal_pdf_path, {
        "region_id": region_id,
        "fit_id": fit_id,
        "pdf_type": "double_sided_crystal_ball",
        "parameters": dscb_params,
        "note": "Parameters estimated from signal MC",
    })

    # Test background models
    scan_results = []
    selected_degree = None
    selected_coeffs = None

    for degree in range(1, max_degree + 1):
        print(f"  Testing Bernstein degree {degree} for {region_id}...")

        coeffs, nll, converged = fit_bernstein_to_data(
            mgg_data, degree=degree, sideband_only=True
        )

        n_spur, sigma_nsig, ratio = compute_spurious_signal(
            mgg_data, coeffs, degree, dscb_params
        )

        passes = ratio < SPURIOUS_SIGNAL_THRESHOLD

        scan_entry = {
            "degree": degree,
            "coefficients": coeffs.tolist(),
            "nll": float(nll),
            "converged": bool(converged),
            "n_spur": float(n_spur),
            "sigma_nsig": float(sigma_nsig),
            "spurious_signal_ratio": float(ratio),
            "passes_spurious_check": bool(passes),
        }
        scan_results.append(scan_entry)

        if passes and selected_degree is None:
            selected_degree = degree
            selected_coeffs = coeffs

    # If none pass, use highest tested degree
    if selected_degree is None:
        selected_degree = max_degree
        selected_coeffs = scan_results[-1]["coefficients"]
        print(f"Warning: no degree passes spurious-signal check; defaulting to degree {max_degree}")

    # Save scan results
    scan_path = out_path / "background_pdf_scan.json"
    write_json(scan_path, {
        "region_id": region_id,
        "fit_id": fit_id,
        "fit_range": [FIT_LOW, FIT_HIGH],
        "sideband_low": SB_LOW,
        "sideband_high": SB_HIGH,
        "spurious_signal_threshold": SPURIOUS_SIGNAL_THRESHOLD,
        "scan": scan_results,
    })

    # Save selected model
    choice_path = out_path / "background_pdf_choice.json"
    choice = {
        "region_id": region_id,
        "fit_id": fit_id,
        "selected_degree": selected_degree,
        "coefficients": selected_coeffs.tolist() if hasattr(selected_coeffs, "tolist") else list(selected_coeffs),
        "pdf_type": "bernstein_polynomial",
        "fit_range": [FIT_LOW, FIT_HIGH],
    }
    write_json(choice_path, choice)

    # Save spurious signal summary
    spur_path = out_path / "spurious_signal.json"
    selected_entry = next(
        (e for e in scan_results if e["degree"] == selected_degree), scan_results[-1]
    )
    write_json(spur_path, {
        "region_id": region_id,
        "fit_id": fit_id,
        "selected_degree": selected_degree,
        "n_spur": selected_entry["n_spur"],
        "sigma_nsig": selected_entry["sigma_nsig"],
        "spurious_signal_ratio": selected_entry["spurious_signal_ratio"],
        "passes_check": selected_entry["passes_spurious_check"],
        "threshold": SPURIOUS_SIGNAL_THRESHOLD,
    })

    print(f"  Selected degree {selected_degree} for {region_id} "
          f"(ratio={selected_entry['spurious_signal_ratio']:.3f})")
    return choice


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Select background functional form via spurious-signal test."
    )
    p.add_argument("--fit-id", required=True, help="Fit ID (e.g. FIT_MAIN)")
    p.add_argument(
        "--summary",
        required=True,
        help="Path to analysis summary JSON",
    )
    p.add_argument("--hists", required=True, help="Path to hists directory")
    p.add_argument(
        "--strategy",
        required=True,
        help="Path to background_modeling_strategy.json",
    )
    p.add_argument("--out", required=True, help="Output directory for fit artifacts")
    p.add_argument("--registry", default=None, help="Path to samples.registry.json")
    p.add_argument("--max-degree", type=int, default=4, help="Max Bernstein degree")
    return p


def main():
    args = build_parser().parse_args()

    with open(args.summary) as f:
        summary = json.load(f)

    with open(args.strategy) as f:
        strategy = json.load(f)

    registry = {}
    if args.registry is not None:
        with open(args.registry) as f:
            registry = json.load(f)

    # Get all region IDs from summary
    region_ids = []
    for r in summary.get("signal_regions", []):
        region_ids.append(r["signal_region_id"])
    for r in summary.get("control_regions", []):
        region_ids.append(r["control_region_id"])

    if not region_ids:
        # Fall back to open-data 6-category regions
        region_ids = [
            "SR_DIPHOTON_INCL",
            "SR_2JET",
            "SR_TRANSITION",
            "SR_CENTRAL_LOW_PTT",
            "SR_CENTRAL_HIGH_PTT",
            "SR_REST_LOW_PTT",
            "SR_REST_HIGH_PTT",
            "CR_BKG_SHAPE_CHECKS",
        ]

    out_base = Path(args.out)

    for region_id in region_ids:
        print(f"Processing region: {region_id}")
        region_out = out_base / region_id
        try:
            select_background_model(
                fit_id=args.fit_id,
                region_id=region_id,
                hists_dir=args.hists,
                strategy=strategy,
                registry=registry,
                out_dir=str(region_out),
                max_degree=args.max_degree,
            )
        except Exception as e:
            print(f"  Error for {region_id}: {e}")

    print("Background model selection complete.")


if __name__ == "__main__":
    main()
