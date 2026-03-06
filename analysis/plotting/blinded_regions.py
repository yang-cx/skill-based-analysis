import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml
from scipy.optimize import minimize

from analysis.common import ensure_dir, read_json, write_json



def _load_kind_map(registry_path: Path) -> Dict[str, str]:
    if not registry_path.exists():
        return {}
    reg = read_json(registry_path)
    out = {}
    for sample in reg.get("samples", []):
        out[str(sample.get("sample_id"))] = sample.get("kind", "background")
        out[str(sample.get("sample_name"))] = sample.get("kind", "background")
    return out



def _load_regions(regions_path: Path) -> Dict[str, List[str]]:
    with regions_path.open() as f:
        payload = yaml.safe_load(f)

    all_regions = []
    control = []
    signal = []
    validation = []
    for reg in payload.get("regions", []):
        rid = str(reg.get("region_id", "")).strip()
        if not rid:
            continue
        all_regions.append(rid)
        kind = str(reg.get("kind", "validation")).lower()
        if kind == "control":
            control.append(rid)
        elif kind == "signal":
            signal.append(rid)
        else:
            validation.append(rid)

    return {
        "all": all_regions,
        "control": control,
        "signal": signal,
        "validation": validation,
    }



def _load_region_hists(hists_dir: Path, kind_map: Dict[str, str]) -> Dict[str, Dict[str, np.ndarray]]:
    out: Dict[str, Dict[str, np.ndarray]] = {}

    for region_dir in sorted([p for p in hists_dir.iterdir() if p.is_dir()]):
        obs_dirs = [p for p in region_dir.iterdir() if p.is_dir()]
        if not obs_dirs:
            continue
        obs_dir = sorted(obs_dirs)[0]

        edges = None
        data = None
        bkg = None
        sig = None
        for npz_path in sorted(obs_dir.glob("*.npz")):
            arr = np.load(npz_path, allow_pickle=True)
            e = arr["edges"].astype(float)
            c = arr["counts"].astype(float)
            if edges is None:
                edges = e
                data = np.zeros_like(c)
                bkg = np.zeros_like(c)
                sig = np.zeros_like(c)

            sid = npz_path.stem
            kind = kind_map.get(sid, "background")
            if kind == "data":
                data += c
            elif kind == "signal":
                sig += c
            else:
                bkg += c

        if edges is None:
            continue

        out[region_dir.name] = {
            "edges": edges,
            "data": np.clip(data, 0.0, None),
            "background": np.clip(bkg, 0.0, None),
            "signal": np.clip(sig, 0.0, None),
            "observable": obs_dir.name,
        }

    return out



def _fit_cr_normalizations(
    region_hists: Dict[str, Dict[str, np.ndarray]],
    control_regions: List[str],
    mu_init: float = 1.0,
) -> Dict[str, float]:
    data_bins = []
    bkg_bins = []
    sig_bins = []

    for rid in control_regions:
        h = region_hists.get(rid)
        if h is None:
            continue
        data_bins.append(h["data"])
        bkg_bins.append(h["background"])
        sig_bins.append(h["signal"])

    if not data_bins:
        return {
            "status": "fallback_no_control_data",
            "alpha_bkg": 1.0,
            "alpha_sig": float(mu_init),
            "nll": None,
        }

    data = np.concatenate(data_bins)
    bkg = np.concatenate(bkg_bins)
    sig = np.concatenate(sig_bins)

    def nll(params: np.ndarray) -> float:
        alpha_bkg = max(float(params[0]), 0.0)
        alpha_sig = max(float(params[1]), 0.0)
        model = alpha_bkg * bkg + alpha_sig * sig
        model = np.clip(model, 1e-9, None)
        return float(np.sum(model - data * np.log(model)))

    x0 = np.array([1.0, max(0.0, float(mu_init))], dtype=float)
    result = minimize(nll, x0=x0, bounds=[(0.0, None), (0.0, None)], method="L-BFGS-B")

    if not result.success:
        return {
            "status": "fallback_fit_failed",
            "alpha_bkg": 1.0,
            "alpha_sig": float(mu_init),
            "nll": None,
            "error": str(result.message),
        }

    return {
        "status": "ok",
        "alpha_bkg": float(result.x[0]),
        "alpha_sig": float(result.x[1]),
        "nll": float(result.fun),
    }



def _plot_region(
    region_id: str,
    hist: Dict[str, np.ndarray],
    out_path: Path,
    alpha_bkg: float,
    alpha_sig: float,
    show_data: bool,
    title_suffix: str = "",
) -> None:
    edges = hist["edges"]
    bkg = np.clip(alpha_bkg * hist["background"], 0.0, None)
    sig = np.clip(alpha_sig * hist["signal"], 0.0, None)
    data = np.clip(hist["data"], 0.0, None)

    width = np.diff(edges)
    centers = 0.5 * (edges[:-1] + edges[1:])

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(
        edges[:-1],
        bkg,
        width=width,
        align="edge",
        color="#4c72b0",
        alpha=0.8,
        label="Background",
    )
    ax.bar(
        edges[:-1],
        sig,
        width=width,
        align="edge",
        bottom=bkg,
        color="#dd8452",
        alpha=0.85,
        label="Signal (stacked)",
    )

    if show_data:
        yerr = np.sqrt(np.clip(data, 0.0, None))
        ax.errorbar(
            centers,
            data,
            yerr=yerr,
            fmt="o",
            color="black",
            ms=3,
            label="Data",
        )
    else:
        ax.text(
            0.03,
            0.93,
            "Data blinded in signal region",
            transform=ax.transAxes,
            fontsize=10,
            bbox={"facecolor": "white", "alpha": 0.8, "edgecolor": "gray"},
        )

    total = bkg + sig
    ax.step(edges[:-1], total, where="post", color="#2f2f2f", lw=1.5, label="S+B expectation")

    ax.set_xlabel("m(gammagamma) [GeV]")
    ax.set_ylabel("Events / bin")
    ax.set_title("{}{}".format(region_id, title_suffix))
    ax.grid(alpha=0.2)
    if np.max(total) > 0 and np.max(total) / max(np.min(total[total > 0]), 1e-9) > 30:
        ax.set_yscale("log")
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)



def _plot_placeholder(region_id: str, out_path: Path, text: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.axis("off")
    ax.text(
        0.5,
        0.5,
        text,
        ha="center",
        va="center",
        fontsize=11,
        bbox={"facecolor": "white", "alpha": 0.9, "edgecolor": "gray"},
    )
    ax.set_title(region_id)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    plt.close(fig)


def _build_overlap_audit(region_cfg: Dict[str, List[str]]) -> Dict[str, Any]:
    signal = set(region_cfg.get("signal", []))
    control = set(region_cfg.get("control", []))
    intersection = sorted(signal.intersection(control))
    return {
        "signal_region_ids": sorted(signal),
        "control_region_ids": sorted(control),
        "region_id_overlap": intersection,
        "has_region_id_overlap": bool(intersection),
        "event_level_overlap_checked": False,
        "note": (
            "This artifact audits declared region-ID overlap only. "
            "Event-level overlap checks require event-level mask intersection artifacts."
        ),
    }


def run_blinded_region_visualization(
    outputs: Path,
    registry_path: Path,
    regions_path: Path,
    fit_id: str,
    blind_sr: bool = True,
) -> Dict[str, Any]:
    kind_map = _load_kind_map(registry_path)
    region_cfg = _load_regions(regions_path)
    region_hists = _load_region_hists(outputs / "hists", kind_map)

    mu_init = 1.0
    fit_result_path = outputs / "fit" / fit_id / "results.json"
    if fit_result_path.exists():
        fit_payload = read_json(fit_result_path)
        if isinstance(fit_payload.get("bestfit_poi"), (int, float)):
            mu_init = float(fit_payload["bestfit_poi"])

    fit_info = _fit_cr_normalizations(region_hists, region_cfg["control"], mu_init=mu_init)
    alpha_bkg = float(fit_info.get("alpha_bkg", 1.0))
    alpha_sig = float(fit_info.get("alpha_sig", mu_init))

    plots_dir = ensure_dir(outputs / "report" / "plots")
    per_region = {}
    overlap_audit = _build_overlap_audit(region_cfg)
    overlap_audit_path = outputs / "report" / "blinding_overlap_audit.json"

    for rid in region_cfg["all"]:
        in_sr = rid in region_cfg["signal"]
        show_data = not (blind_sr and in_sr)
        kind = "signal" if in_sr else ("control" if rid in region_cfg["control"] else "validation")
        plot_path = plots_dir / ("blinded_region_{}.png".format(rid))
        prefit_plot_path = plots_dir / ("prefit_region_{}.png".format(rid))
        postfit_plot_path = plots_dir / ("postfit_region_{}.png".format(rid))

        hist = region_hists.get(rid)
        if hist is None:
            _plot_placeholder(
                region_id=rid,
                out_path=plot_path,
                text="No histogram template available for this region",
            )
            if not in_sr:
                _plot_placeholder(
                    region_id=rid,
                    out_path=prefit_plot_path,
                    text="No histogram template available for this region",
                )
                _plot_placeholder(
                    region_id=rid,
                    out_path=postfit_plot_path,
                    text="No histogram template available for this region",
                )
            per_region[rid] = {
                "kind": kind,
                "data_shown": bool(show_data),
                "plot": str(plot_path),
                "prefit_plot": str(prefit_plot_path) if not in_sr else None,
                "postfit_plot": str(postfit_plot_path) if not in_sr else None,
                "observable": None,
                "missing_histogram": True,
            }
            continue

        _plot_region(
            region_id=rid,
            hist=hist,
            out_path=plot_path,
            alpha_bkg=alpha_bkg,
            alpha_sig=alpha_sig,
            show_data=show_data,
            title_suffix=" (primary)",
        )

        prefit_out = None
        postfit_out = None
        if not in_sr:
            _plot_region(
                region_id=rid,
                hist=hist,
                out_path=prefit_plot_path,
                alpha_bkg=1.0,
                alpha_sig=1.0,
                show_data=True,
                title_suffix=" (pre-fit)",
            )
            _plot_region(
                region_id=rid,
                hist=hist,
                out_path=postfit_plot_path,
                alpha_bkg=alpha_bkg,
                alpha_sig=alpha_sig,
                show_data=True,
                title_suffix=" (post-fit)",
            )
            prefit_out = str(prefit_plot_path)
            postfit_out = str(postfit_plot_path)

        per_region[rid] = {
            "kind": kind,
            "data_shown": bool(show_data),
            "plot": str(plot_path),
            "prefit_plot": prefit_out,
            "postfit_plot": postfit_out,
            "observable": hist["observable"],
            "missing_histogram": False,
        }

    fit_payload = {
        "fit_id": fit_id,
        "status": fit_info.get("status", "unknown"),
        "alpha_bkg": alpha_bkg,
        "alpha_sig": alpha_sig,
        "nll": fit_info.get("nll"),
        "mu_init_from_fit": mu_init,
        "control_regions": region_cfg["control"],
        "blind_sr": bool(blind_sr),
    }
    if "error" in fit_info:
        fit_payload["error"] = fit_info["error"]

    summary = {
        "fit_id": fit_id,
        "blind_sr": bool(blind_sr),
        "control_regions": region_cfg["control"],
        "signal_regions": region_cfg["signal"],
        "normalization_fit": fit_payload,
        "overlap_audit_path": str(overlap_audit_path),
        "regions": per_region,
    }

    ensure_dir(outputs / "fit" / fit_id)
    write_json(outputs / "fit" / fit_id / "blinded_cr_fit.json", fit_payload)
    write_json(overlap_audit_path, overlap_audit)
    write_json(outputs / "report" / "blinding_summary.json", summary)
    return summary



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create CR/SR region plots with SR data blinding and CR-only normalization fit"
    )
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--registry", default="outputs/samples.registry.json")
    parser.add_argument("--regions", default="analysis/regions.yaml")
    parser.add_argument("--fit-id", default="FIT_MAIN")
    parser.add_argument("--unblind-sr", action="store_true")
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    summary = run_blinded_region_visualization(
        outputs=Path(args.outputs),
        registry_path=Path(args.registry),
        regions_path=Path(args.regions),
        fit_id=args.fit_id,
        blind_sr=not args.unblind_sr,
    )
    print(
        "blinded region visualization written: fit_id={} blind_sr={} regions={}".format(
            args.fit_id,
            not args.unblind_sr,
            len(summary.get("regions", {})),
        )
    )


if __name__ == "__main__":
    main()
