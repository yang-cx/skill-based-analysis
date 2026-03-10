import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from analysis.common import ensure_dir, read_json, write_json



def _load_npz(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    arr = np.load(path, allow_pickle=True)
    edges = arr["edges"].astype(float)
    counts = arr["counts"].astype(float)
    return edges, counts



def _fit_regions_from_summary(summary: Dict[str, Any], fit_id: str) -> List[str]:
    first_fit_regions: List[str] = []
    for fit in summary.get("fit_setup", []):
        regs = fit.get("regions_included", [])
        if isinstance(regs, list) and regs and not first_fit_regions:
            first_fit_regions = [str(r) for r in regs]
        if str(fit.get("fit_id", "")) == fit_id and isinstance(regs, list):
            return [str(r) for r in regs]
    if first_fit_regions:
        return first_fit_regions
    # Final fallback for legacy outputs.
    return ["SR_DIPHOTON_INCL"]



def _collect_hist_sum(hists_dir: Path, region: str, sample_ids: List[str]) -> Tuple[np.ndarray, np.ndarray]:
    region_dir = hists_dir / region
    if not region_dir.exists():
        return np.array([]), np.array([])

    obs_dirs = [d for d in region_dir.iterdir() if d.is_dir()]
    if not obs_dirs:
        return np.array([]), np.array([])
    obs_dir = sorted(obs_dirs)[0]

    edges = None
    total = None
    for sid in sample_ids:
        f = obs_dir / (sid + ".npz")
        if not f.exists():
            continue
        e, c = _load_npz(f)
        if edges is None:
            edges = e
            total = np.zeros_like(c)
        total += c

    if edges is None or total is None:
        return np.array([]), np.array([])
    return edges, total



def _signal_shape(signal_counts: np.ndarray) -> np.ndarray:
    s = np.clip(signal_counts.astype(float), 0.0, None)
    norm = float(np.sum(s))
    if norm <= 0:
        return np.ones_like(s) / max(len(s), 1)
    return s / norm



def _model_counts(family: str, degree: int, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    y = np.clip(y, 1e-9, None)
    if family == "exp_poly":
        coeff = np.polyfit(x, np.log(y), deg=degree)
        pred = np.exp(np.polyval(coeff, x))
    else:  # bernstein-style proxy with ordinary polynomial in [0,1]
        xu = (x - x.min()) / max(x.max() - x.min(), 1e-9)
        coeff = np.polyfit(xu, y, deg=degree)
        pred = np.polyval(coeff, xu)
    return np.clip(pred, 1e-9, None)



def _spurious_metrics(
    bkg_counts: np.ndarray,
    model_counts: np.ndarray,
    sshape: np.ndarray,
) -> Tuple[float, float, float]:
    residual = bkg_counts - model_counts
    n_spur = float(np.sum(residual * sshape))
    sigma = float(np.sqrt(np.sum(np.clip(model_counts, 0.0, None) * (sshape**2))))
    sigma = max(sigma, 1e-9)
    r = abs(n_spur) / sigma
    return n_spur, sigma, r



def run_mass_model_selection(
    fit_id: str,
    summary_path: Path,
    hists_dir: Path,
    strategy_path: Path,
    out_path: Path,
) -> Dict[str, Any]:
    summary = read_json(summary_path) if summary_path.exists() else {}
    strategy = read_json(strategy_path) if strategy_path.exists() else {}
    cls = strategy.get("classification", {})

    signal_ids = [str(x) for x in cls.get("signal", [])]
    bkg_ids = [str(x) for x in cls.get("background", [])]

    regions = _fit_regions_from_summary(summary, fit_id)
    if not regions:
        regions = ["SR_DIPHOTON_INCL"]
    region = regions[0]

    edges_s, signal_counts = _collect_hist_sum(hists_dir, region, signal_ids)
    edges_b, bkg_counts = _collect_hist_sum(hists_dir, region, bkg_ids)

    if len(signal_counts) == 0 or len(bkg_counts) == 0:
        payload = {
            "fit_id": fit_id,
            "status": "failed",
            "error": "Missing signal or background templates for mass-model selection",
            "region": region,
        }
        ensure_dir(out_path.parent)
        write_json(out_path, payload)
        return payload

    if not np.allclose(edges_s, edges_b):
        payload = {
            "fit_id": fit_id,
            "status": "failed",
            "error": "Signal/background binning mismatch",
            "region": region,
        }
        ensure_dir(out_path.parent)
        write_json(out_path, payload)
        return payload

    edges = edges_s
    x = 0.5 * (edges[:-1] + edges[1:])

    sshape = _signal_shape(signal_counts)
    mean = float(np.sum(x * sshape))
    width = float(np.sqrt(np.sum(((x - mean) ** 2) * sshape)))

    signal_pdf = {
        "fit_id": fit_id,
        "status": "ok",
        "pdf": "DSCB_proxy",
        "region": region,
        "mean": mean,
        "width": width,
        "alpha_low": 1.5,
        "alpha_high": 1.5,
        "n_low": 5.0,
        "n_high": 5.0,
        "note": "Proxy parameterization from histogram moments; replace with true DSCB fit for production.",
    }

    candidates = []
    for degree in [1, 2, 3]:
        for family in ["bernstein", "exp_poly"]:
            model = _model_counts(family, degree, x, bkg_counts)
            n_spur, sigma, r = _spurious_metrics(bkg_counts, model, sshape)
            candidates.append(
                {
                    "family": family,
                    "degree": degree,
                    "n_spur": n_spur,
                    "sigma_nsig": sigma,
                    "r_spur": r,
                    "passed": bool(r < 0.2),
                }
            )

    # Choose model: minimal degree with pass, then smallest |N_spur|.
    choice = None
    for degree in [1, 2, 3]:
        passing = [c for c in candidates if c["degree"] == degree and c["passed"]]
        if passing:
            choice = sorted(passing, key=lambda c: abs(c["n_spur"]))[0]
            break
    if choice is None:
        choice = sorted(candidates, key=lambda c: c["r_spur"])[0]

    scan = {
        "fit_id": fit_id,
        "status": "ok",
        "region": region,
        "candidates": candidates,
        "criterion": "r_spur = |N_spur|/sigma_nsig < 0.2",
    }

    choice_payload = {
        "fit_id": fit_id,
        "status": "ok",
        "region": region,
        "chosen_family": choice["family"],
        "chosen_degree": int(choice["degree"]),
        "passed_target": bool(choice["passed"]),
        "selection_rule": "lowest degree passing target; else smallest r_spur",
    }

    spurious = {
        "fit_id": fit_id,
        "status": "ok",
        "region": region,
        "n_spur": float(choice["n_spur"]),
        "sigma_nsig": float(choice["sigma_nsig"]),
        "r_spur": float(choice["r_spur"]),
        "criterion_threshold": 0.2,
        "passed": bool(choice["passed"]),
        "chosen_family": choice["family"],
        "chosen_degree": int(choice["degree"]),
    }

    ensure_dir(out_path.parent)
    write_json(out_path, choice_payload)
    write_json(out_path.parent / "signal_pdf.json", signal_pdf)
    write_json(out_path.parent / "background_pdf_scan.json", scan)
    write_json(out_path.parent / "spurious_signal.json", spurious)

    return choice_payload



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Select analytic background mass model with spurious-signal scan"
    )
    parser.add_argument("--fit-id", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--hists", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--out", required=True)
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    out = run_mass_model_selection(
        fit_id=args.fit_id,
        summary_path=Path(args.summary),
        hists_dir=Path(args.hists),
        strategy_path=Path(args.strategy),
        out_path=Path(args.out),
    )

    print(
        "mass-model selection {}: family={} degree={} passed_target={}".format(
            args.fit_id,
            out.get("chosen_family", "n/a"),
            out.get("chosen_degree", "n/a"),
            out.get("passed_target", False),
        )
    )


if __name__ == "__main__":
    main()
