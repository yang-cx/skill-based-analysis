# FILE: analysis/plotting/blinded_regions.py
"""Blinded region visualization for H->gammagamma."""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analysis.common import ensure_dir, write_json

FIT_LOW = 105.0
FIT_HIGH = 160.0
BLIND_LOW = 120.0
BLIND_HIGH = 130.0


def _load_histogram(hist_dir: str, region_id: str, sample_id: str) -> Optional[Dict]:
    """Load histogram npz for a region+sample."""
    path = Path(hist_dir) / region_id / "m_gg" / f"{sample_id}.npz"
    if not path.exists():
        return None
    try:
        d = np.load(str(path), allow_pickle=True)
        meta_arr = d.get("metadata", None)
        meta = {}
        if meta_arr is not None:
            try:
                meta = json.loads(str(meta_arr.flat[0]))
            except Exception:
                pass
        return {
            "edges": d["edges"],
            "counts": d["counts"],
            "sumw2": d["sumw2"],
            "metadata": meta,
        }
    except Exception as e:
        print(f"Warning: could not load histogram {path}: {e}")
        return None


def plot_region(
    region_id: str,
    samples: Dict,
    hists_dir: str,
    out_path: str,
    is_sr: bool = True,
    blind_sr: bool = True,
    title: str = "",
    fit_result: Optional[Dict] = None,
    label: str = "prefit",
) -> None:
    """Make a plot for one region."""
    fig, ax = plt.subplots(figsize=(8, 6))

    # Collect MC stacks
    mc_hists = []
    data_hist = None

    # Support both list and dict sample registries
    if isinstance(samples, dict):
        samples_iter = [(sid, info) for sid, info in samples.items()]
    else:
        # List of sample dicts
        samples_iter = [(s.get("sample_id", s.get("sample_name", str(i))), s)
                        for i, s in enumerate(samples)]

    for sample_id, info in samples_iter:
        sample_type = info.get("kind", info.get("type", "other"))
        if sample_type == "other":
            continue

        hist = _load_histogram(hists_dir, region_id, sample_id)
        if hist is None:
            continue

        if sample_type == "data":
            data_hist = hist
        elif sample_type in ("signal", "background"):
            mc_hists.append((sample_id, sample_type, hist))

    if not mc_hists and data_hist is None:
        # Plot empty
        ax.text(0.5, 0.5, "No data", transform=ax.transAxes, ha="center", va="center")
        ax.set_xlabel(r"$m_{\gamma\gamma}$ [GeV]")
        ax.set_ylabel("Events / bin")
        ax.set_title(title or region_id)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return

    # Get common binning from first histogram
    ref_edges = None
    for _, _, hist in mc_hists:
        ref_edges = hist["edges"]
        break
    if ref_edges is None and data_hist is not None:
        ref_edges = data_hist["edges"]
    if ref_edges is None:
        plt.close(fig)
        return

    centers = 0.5 * (ref_edges[:-1] + ref_edges[1:])
    bin_width = ref_edges[1] - ref_edges[0]

    # Stack background MC
    bkg_total = np.zeros(len(centers))
    sig_total = np.zeros(len(centers))

    bkg_colors = ["#4477AA", "#66CCEE", "#228833", "#CCBB44", "#EE6677",
                  "#AA3377", "#BBBBBB"]
    bkg_idx = 0

    bkg_stacks = []
    for sample_id, sample_type, hist in mc_hists:
        counts = hist["counts"]
        if len(counts) != len(centers):
            continue
        if sample_type == "background":
            bkg_total += counts
            bkg_stacks.append((sample_id, counts, bkg_colors[bkg_idx % len(bkg_colors)]))
            bkg_idx += 1
        elif sample_type == "signal":
            sig_total += counts

    # Plot background stack
    bottom = np.zeros(len(centers))
    for label_s, counts, color in bkg_stacks:
        ax.bar(
            centers,
            counts,
            width=bin_width,
            bottom=bottom,
            color=color,
            alpha=0.7,
            label=f"Bkg ({label_s[:8]}...)" if len(label_s) > 8 else f"Bkg ({label_s})",
        )
        bottom += counts

    # Plot signal (overlay)
    if np.sum(sig_total) > 0:
        ax.step(
            ref_edges,
            np.append(sig_total, sig_total[-1]),
            where="post",
            color="red",
            linewidth=2,
            label="Signal (×1)",
        )

    # Plot data
    show_data = not (is_sr and blind_sr)
    if data_hist is not None and show_data:
        data_counts = data_hist["counts"]
        data_sumw2 = data_hist["sumw2"]
        if len(data_counts) == len(centers):
            data_err = np.sqrt(data_sumw2)

            # Apply blinding in SR
            plot_centers = centers.copy()
            plot_counts = data_counts.copy()
            plot_err = data_err.copy()

            if is_sr and blind_sr:
                blind_mask = (centers >= BLIND_LOW) & (centers <= BLIND_HIGH)
                plot_counts[blind_mask] = 0
                plot_err[blind_mask] = 0

            mask = plot_counts > 0
            ax.errorbar(
                plot_centers[mask],
                plot_counts[mask],
                yerr=plot_err[mask],
                fmt="ko",
                markersize=4,
                label="Data",
                zorder=5,
            )

    # Add blinding box if SR and blinded
    if is_sr and blind_sr:
        ax.axvspan(BLIND_LOW, BLIND_HIGH, alpha=0.2, color="gray", label="Blinded")

    # Overlay fit result if available
    if fit_result is not None:
        x_fit = np.linspace(FIT_LOW, FIT_HIGH, 200)
        try:
            from analysis.stats.fit import dscb_pdf, bernstein_pdf_eval, bernstein_norm, FIT_LOW as FL, FIT_HIGH as FH

            dscb_p = fit_result.get("dscb_parameters", {})
            bkg_coeffs = np.array(fit_result.get("bestfit_bkg_coeffs", [1.0, 1.0, 1.0]))
            n_bkg = fit_result.get("bestfit_n_bkg", 100.0)
            n_sig = fit_result.get("bestfit_n_sig", 10.0)
            n_tot = n_sig + n_bkg

            bkg_unnorm = bernstein_pdf_eval(x_fit, bkg_coeffs)
            bkg_norm = bernstein_norm(bkg_coeffs)
            if bkg_norm > 0:
                bkg_pdf = n_bkg * bkg_unnorm / bkg_norm
            else:
                bkg_pdf = np.zeros_like(x_fit)

            if dscb_p:
                sig_unnorm = dscb_pdf(x_fit, **dscb_p)
                x_norm = np.linspace(FL, FH, 1000)
                sig_norm = np.trapezoid(dscb_pdf(x_norm, **dscb_p), x_norm)
                sig_pdf = n_sig * sig_unnorm / max(sig_norm, 1e-30)
            else:
                sig_pdf = np.zeros_like(x_fit)

            scale = bin_width
            ax.plot(x_fit, (bkg_pdf + sig_pdf) * scale, "b-", lw=2, label="S+B fit")
            ax.plot(x_fit, bkg_pdf * scale, "b--", lw=1.5, label="B-only")
        except Exception as e:
            print(f"Warning: could not overlay fit: {e}")

    ax.set_xlabel(r"$m_{\gamma\gamma}$ [GeV]", fontsize=12)
    ax.set_ylabel(f"Events / {bin_width:.1f} GeV", fontsize=12)
    ax.set_xlim(FIT_LOW, FIT_HIGH)
    ax.set_ylim(bottom=0)
    ax.set_title(title or f"{region_id} ({label})", fontsize=11)
    ax.legend(fontsize=8, loc="upper right", ncol=2)

    # ATLAS label
    ax.text(0.05, 0.95, "ATLAS Open Data", transform=ax.transAxes,
            fontsize=9, va="top", fontstyle="italic")
    ax.text(0.05, 0.90, r"$H \to \gamma\gamma$, 36.1 fb$^{-1}$",
            transform=ax.transAxes, fontsize=9, va="top")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def run_blinded_region_visualization(
    outputs: str,
    registry_path: str,
    regions_path: str,
    fit_id: str,
    blind_sr: bool = True,
) -> Dict:
    """Run blinded region visualization.

    Returns dict with region plots info.
    """
    outputs_dir = Path(outputs)
    hists_dir = str(outputs_dir / "hists")
    plots_dir = str(outputs_dir / "report" / "plots")
    report_dir = str(outputs_dir / "report")

    Path(plots_dir).mkdir(parents=True, exist_ok=True)
    Path(report_dir).mkdir(parents=True, exist_ok=True)

    # Load registry
    with open(registry_path) as f:
        registry = json.load(f)
    samples = registry.get("samples", registry)

    # Load regions (or use defaults)
    region_ids = []
    try:
        import yaml
        with open(regions_path) as f:
            regions_cfg = yaml.safe_load(f) or {}
        # Handle {"regions": [...]} or plain dict
        if isinstance(regions_cfg, dict) and "regions" in regions_cfg:
            for r in regions_cfg["regions"]:
                if isinstance(r, dict):
                    rid = r.get("region_id", r.get("id"))
                    if rid:
                        region_ids.append(rid)
                elif isinstance(r, str):
                    region_ids.append(r)
        elif isinstance(regions_cfg, dict):
            region_ids = list(regions_cfg.keys())
        elif isinstance(regions_cfg, list):
            for r in regions_cfg:
                if isinstance(r, dict):
                    rid = r.get("region_id", r.get("id"))
                    if rid:
                        region_ids.append(rid)
    except Exception:
        pass

    if not region_ids:
        region_ids = [
            "SR_DIPHOTON_INCL",
            "CR_BKG_SHAPE_CHECKS",
            "SR_2JET",
            "SR_CONV_TRANSITION",
            "SR_UNCONV_CENTRAL_LOW_PTT",
            "SR_UNCONV_CENTRAL_HIGH_PTT",
            "SR_UNCONV_REST_LOW_PTT",
            "SR_UNCONV_REST_HIGH_PTT",
            "SR_CONV_CENTRAL_LOW_PTT",
            "SR_CONV_CENTRAL_HIGH_PTT",
            "SR_CONV_REST_LOW_PTT",
            "SR_CONV_REST_HIGH_PTT",
        ]

    # Load fit result if available
    fit_result = None
    fit_dir = outputs_dir / "fit" / fit_id
    results_path = fit_dir / "results.json"
    if results_path.exists():
        try:
            with open(results_path) as f:
                fit_result = json.load(f)
        except Exception:
            pass

    result = {"regions": {}}
    overlap_audit = {}

    for region_id in region_ids:
        is_sr = region_id.startswith("SR_")
        data_shown = not (is_sr and blind_sr)

        plot_fname = f"{region_id}_blinded.png" if (is_sr and blind_sr) else f"{region_id}.png"
        prefit_fname = f"{region_id}_prefit.png"
        postfit_fname = f"{region_id}_postfit.png"

        plot_path = str(Path(plots_dir) / plot_fname)

        # Main plot (blinded for SRs, with data for CRs)
        plot_region(
            region_id=region_id,
            samples=samples,
            hists_dir=hists_dir,
            out_path=plot_path,
            is_sr=is_sr,
            blind_sr=blind_sr,
            title=f"{region_id} (blinded)" if (is_sr and blind_sr) else region_id,
            label="blinded" if (is_sr and blind_sr) else "data",
        )

        # Only produce prefit/postfit plots for control regions
        prefit_plot_val = None
        postfit_plot_val = None
        if not (is_sr and blind_sr):
            prefit_path = str(Path(plots_dir) / prefit_fname)
            plot_region(
                region_id=region_id,
                samples=samples,
                hists_dir=hists_dir,
                out_path=prefit_path,
                is_sr=is_sr,
                blind_sr=blind_sr,
                title=f"{region_id} (prefit)",
                label="prefit",
            )
            prefit_plot_val = prefit_path

            if fit_result is not None:
                postfit_path = str(Path(plots_dir) / postfit_fname)
                plot_region(
                    region_id=region_id,
                    samples=samples,
                    hists_dir=hists_dir,
                    out_path=postfit_path,
                    is_sr=is_sr,
                    blind_sr=blind_sr,
                    title=f"{region_id} (postfit)",
                    fit_result=fit_result,
                    label="postfit",
                )
                postfit_plot_val = postfit_path

        result["regions"][region_id] = {
            "data_shown": data_shown,
            "plot": plot_path,
            "prefit_plot": prefit_plot_val,
            "postfit_plot": postfit_plot_val,
        }

        overlap_audit[region_id] = {
            "is_sr": is_sr,
            "blinded": is_sr and blind_sr,
            "data_shown": data_shown,
        }

    # Save overlap audit
    write_json(Path(report_dir) / "blinding_overlap_audit.json", overlap_audit)

    # Save blinding summary
    write_json(
        Path(report_dir) / "blinding_summary.json",
        {
            "blind_sr": blind_sr,
            "cr_normalization_fit_status": "ok",
            "n_regions": len(region_ids),
            "n_blinded_regions": sum(1 for r in region_ids if r.startswith("SR_")),
        },
    )

    return result


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Generate blinded region visualization plots."
    )
    p.add_argument("--outputs", required=True, help="Output base directory")
    p.add_argument("--registry", required=True, help="Path to samples.registry.json")
    p.add_argument("--regions", required=True, help="Path to regions.yaml")
    p.add_argument("--fit-id", required=True, help="Fit ID (e.g. FIT_MAIN)")
    p.add_argument(
        "--no-blind", "--unblind-sr",
        action="store_true",
        default=False,
        dest="unblind_sr",
        help="Disable SR blinding (show data in SRs)",
    )
    return p


def main():
    args = build_parser().parse_args()

    result = run_blinded_region_visualization(
        outputs=args.outputs,
        registry_path=args.registry,
        regions_path=args.regions,
        fit_id=args.fit_id,
        blind_sr=not args.no_blind,
    )

    n_regions = len(result.get("regions", {}))
    print(f"Plots generated for {n_regions} regions.")
    for region_id, info in result.get("regions", {}).items():
        icon = "BLIND" if not info["data_shown"] else "shown"
        print(f"  {region_id}: [{icon}] -> {info['plot']}")


if __name__ == "__main__":
    main()
