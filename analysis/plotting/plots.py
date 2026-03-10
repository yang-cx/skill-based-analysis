# FILE: analysis/plotting/plots.py
"""Generate validation and analysis plots for H->gammagamma."""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from analysis.common import ensure_dir, write_json
from analysis.io.readers import load_events
from analysis.selections.regions import (
    extract_event_weights,
    apply_baseline_diphoton_selection,
    extract_tight_leading_photons,
    compute_diphoton_kinematics,
    _get_photon_branch,
    MGG_LOW,
    MGG_HIGH,
    LEAD_PT_MIN,
    SUBLEAD_PT_MIN,
)

FIT_LOW = 105.0
FIT_HIGH = 160.0
BLIND_LOW = 120.0
BLIND_HIGH = 130.0


def _setup_atlas_style(ax, title: str = "", xlabel: str = "", ylabel: str = "Events"):
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    if title:
        ax.set_title(title, fontsize=11)
    ax.text(0.05, 0.97, "ATLAS Open Data", transform=ax.transAxes,
            fontsize=9, va="top", fontstyle="italic")
    ax.text(0.05, 0.92, r"$H \to \gamma\gamma$, 36.1 fb$^{-1}$",
            transform=ax.transAxes, fontsize=9, va="top")


def _load_sample_kinematics(
    registry: Dict,
    sample_ids: Optional[List[str]] = None,
    max_events_per_sample: int = 200000,
) -> Tuple[Dict, np.ndarray]:
    """Load kinematics for plotting from registry samples."""
    samples = registry.get("samples", registry)

    all_pt1 = []
    all_pt2 = []
    all_eta1 = []
    all_eta2 = []
    all_n_photon = []
    all_mgg = []
    all_pt_gg = []
    all_deltaR = []
    all_weights = []
    all_types = []

    if sample_ids is None:
        sample_ids = list(samples.keys())

    for sample_id in sample_ids:
        if sample_id not in samples:
            continue
        info = samples[sample_id]
        sample_type = info.get("type", "other")
        if sample_type == "other":
            continue

        files = info.get("files", [])
        norm_factor = info.get("norm_factor") or 1.0
        is_data = sample_type == "data"

        branches = [
            "photon_pt", "photon_eta", "photon_phi", "photon_e",
            "photon_n", "photon_isTightID",
            "mcWeight", "ScaleFactor_PILEUP", "ScaleFactor_PHOTON",
        ]

        try:
            data = load_events(files, branches=branches, max_events=max_events_per_sample)
        except Exception as e:
            print(f"Warning: could not load {sample_id}: {e}")
            continue

        if not data:
            continue

        weights = extract_event_weights(data, norm_factor, is_data)
        n_events = len(weights)

        # Photon multiplicity
        pt_arr = _get_photon_branch(data, "photon_pt")
        if pt_arr is not None:
            n_ph = np.array([len(pt_arr[i]) for i in range(n_events)])
            all_n_photon.append(n_ph)

        # Leading photon kinematics
        result = extract_tight_leading_photons(data)
        if result is not None:
            pt1, eta1, phi1, e1, pt2, eta2, phi2, e2, mask = result

            sel = apply_baseline_diphoton_selection(data)
            if sel:
                baseline = sel["baseline_mask"]
                mgg = sel["mgg"]
                pt_gg = sel["pt_gg"]

                all_pt1.append(pt1[baseline])
                all_pt2.append(pt2[baseline])
                all_eta1.append(eta1[baseline])
                all_eta2.append(eta2[baseline])
                all_mgg.append(mgg[baseline])
                all_pt_gg.append(pt_gg[baseline])
                all_weights.append(weights[baseline])
                all_types.extend([sample_type] * int(np.sum(baseline)))

                # DeltaR between photons
                deta = np.abs(eta1[baseline] - eta2[baseline])
                dphi = np.abs(phi1[baseline] - phi2[baseline])
                dphi = np.where(dphi > np.pi, 2 * np.pi - dphi, dphi)
                deltaR = np.sqrt(deta ** 2 + dphi ** 2)
                all_deltaR.append(deltaR)

    def concat(arrays):
        if not arrays:
            return np.array([])
        return np.concatenate(arrays)

    kin = {
        "pt1": concat(all_pt1),
        "pt2": concat(all_pt2),
        "eta1": concat(all_eta1),
        "eta2": concat(all_eta2),
        "mgg": concat(all_mgg),
        "pt_gg": concat(all_pt_gg),
        "deltaR": concat(all_deltaR),
        "n_photon": concat(all_n_photon) if all_n_photon else np.array([]),
        "weights": concat(all_weights),
        "types": np.array(all_types),
    }
    return kin


def plot_photon_pt_leading(kin: Dict, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    pt = kin["pt1"]
    w = kin["weights"]
    if len(pt) > 0:
        ax.hist(pt, bins=40, range=(0, 200), weights=w, color="#4477AA",
                histtype="stepfilled", alpha=0.7)
    _setup_atlas_style(ax, "Leading Photon pT", r"$p_T^{\gamma_1}$ [GeV]")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_photon_pt_subleading(kin: Dict, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    pt = kin["pt2"]
    w = kin["weights"]
    if len(pt) > 0:
        ax.hist(pt, bins=40, range=(0, 150), weights=w, color="#66CCEE",
                histtype="stepfilled", alpha=0.7)
    _setup_atlas_style(ax, "Subleading Photon pT", r"$p_T^{\gamma_2}$ [GeV]")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_photon_eta_leading(kin: Dict, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    eta = kin["eta1"]
    w = kin["weights"]
    if len(eta) > 0:
        ax.hist(eta, bins=50, range=(-3, 3), weights=w, color="#4477AA",
                histtype="stepfilled", alpha=0.7)
    _setup_atlas_style(ax, "Leading Photon η", r"$\eta^{\gamma_1}$")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_photon_eta_subleading(kin: Dict, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    eta = kin["eta2"]
    w = kin["weights"]
    if len(eta) > 0:
        ax.hist(eta, bins=50, range=(-3, 3), weights=w, color="#66CCEE",
                histtype="stepfilled", alpha=0.7)
    _setup_atlas_style(ax, "Subleading Photon η", r"$\eta^{\gamma_2}$")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_photon_multiplicity(kin: Dict, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    n = kin["n_photon"]
    if len(n) > 0:
        ax.hist(n, bins=np.arange(0, 10) - 0.5, color="#228833",
                histtype="stepfilled", alpha=0.7)
    _setup_atlas_style(ax, "Photon Multiplicity", r"$N_\gamma$")
    ax.set_xticks(range(0, 9))
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_diphoton_mass_preselection(kin: Dict, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    mgg = kin["mgg"]
    w = kin["weights"]
    if len(mgg) > 0:
        ax.hist(mgg, bins=55, range=(FIT_LOW, FIT_HIGH), weights=w,
                color="#4477AA", histtype="stepfilled", alpha=0.7, label="MC")
    ax.axvspan(BLIND_LOW, BLIND_HIGH, alpha=0.15, color="gray", label="Signal window")
    _setup_atlas_style(ax, r"Diphoton Mass (Preselection)", r"$m_{\gamma\gamma}$ [GeV]")
    ax.legend()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_diphoton_pt(kin: Dict, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    pt = kin["pt_gg"]
    w = kin["weights"]
    if len(pt) > 0:
        ax.hist(pt, bins=40, range=(0, 300), weights=w, color="#EE6677",
                histtype="stepfilled", alpha=0.7)
    _setup_atlas_style(ax, r"Diphoton $p_T$", r"$p_T^{\gamma\gamma}$ [GeV]")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_diphoton_deltaR(kin: Dict, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    dr = kin["deltaR"]
    w = kin["weights"]
    if len(dr) > 0:
        ax.hist(dr, bins=40, range=(0, 6), weights=w, color="#AA3377",
                histtype="stepfilled", alpha=0.7)
    _setup_atlas_style(ax, r"Diphoton $\Delta R$", r"$\Delta R(\gamma_1, \gamma_2)$")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_category_mass(
    region_id: str, hists_dir: str, registry: Dict, out_path: str, cat_num: int = 1
) -> None:
    """Plot m_gg for a specific analysis category."""
    fig, ax = plt.subplots(figsize=(8, 6))

    samples = registry.get("samples", registry)
    data_shown = False

    for sample_id, info in samples.items():
        sample_type = info.get("type", "other")
        path = Path(hists_dir) / region_id / "m_gg" / f"{sample_id}.npz"
        if not path.exists():
            continue
        try:
            d = np.load(str(path), allow_pickle=True)
            edges = d["edges"]
            counts = d["counts"]
            centers = 0.5 * (edges[:-1] + edges[1:])
            bin_width = edges[1] - edges[0]

            if sample_type == "background":
                ax.bar(centers, counts, width=bin_width, alpha=0.6, label=f"Bkg")
            elif sample_type == "signal":
                ax.step(edges, np.append(counts, counts[-1]), where="post",
                        color="red", lw=2, label="Signal")
            elif sample_type == "data" and not data_shown:
                ax.errorbar(centers, counts, yerr=np.sqrt(d["sumw2"]),
                           fmt="ko", ms=3, label="Data", zorder=5)
                data_shown = True
        except Exception:
            continue

    ax.axvspan(BLIND_LOW, BLIND_HIGH, alpha=0.15, color="gray")
    _setup_atlas_style(ax, f"Category {cat_num}: {region_id}",
                       r"$m_{\gamma\gamma}$ [GeV]")
    ax.set_xlim(FIT_LOW, FIT_HIGH)
    ax.legend(fontsize=8)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_cutflow(outputs_dir: str, out_path: str) -> None:
    """Plot cutflow across all samples."""
    fig, ax = plt.subplots(figsize=(10, 6))

    cutflow_labels = [
        "all_events", "ge2_photons", "ge2_tight_photons",
        "lead_pt_gt40", "sublead_pt_gt30", "eta_acceptance", "mass_window_105_160",
    ]

    yields_dir = Path(outputs_dir) / "yields"
    if not yields_dir.exists():
        ax.text(0.5, 0.5, "No cutflow data", transform=ax.transAxes, ha="center")
        _setup_atlas_style(ax, "Cutflow", "Cut step", "Events")
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return

    # Sum all MC yields
    summed = {label: 0.0 for label in cutflow_labels}
    for json_path in yields_dir.glob("*.json"):
        try:
            with open(json_path) as f:
                data = json.load(f)
            if data.get("type") == "data":
                continue
            cf = data.get("cutflow", {})
            for label in cutflow_labels:
                if label in cf:
                    summed[label] += cf[label].get("yield", 0.0)
        except Exception:
            continue

    counts = [summed[l] for l in cutflow_labels]
    x = np.arange(len(cutflow_labels))

    ax.bar(x, counts, color="#4477AA", alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(
        [l.replace("_", "\n") for l in cutflow_labels],
        fontsize=7,
        rotation=30,
        ha="right",
    )
    ax.set_yscale("log")
    _setup_atlas_style(ax, "MC Cutflow", "Cut step", "Weighted events (MC)")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def plot_diphoton_mass_fit(
    fit_result: Optional[Dict],
    hists_dir: str,
    region_id: str,
    registry: Dict,
    out_path: str,
) -> None:
    """Plot diphoton mass with signal+background fit overlay."""
    fig, (ax_main, ax_pull) = plt.subplots(
        2, 1, figsize=(8, 8), gridspec_kw={"height_ratios": [3, 1]}, sharex=True
    )

    # Load data histogram
    samples = registry.get("samples", registry)
    data_edges = None
    data_counts = None
    data_sumw2 = None

    for sample_id, info in samples.items():
        if info.get("type") == "data":
            path = Path(hists_dir) / region_id / "m_gg" / f"{sample_id}.npz"
            if path.exists():
                try:
                    d = np.load(str(path), allow_pickle=True)
                    data_edges = d["edges"]
                    data_counts = d["counts"]
                    data_sumw2 = d["sumw2"]
                except Exception:
                    pass
            break

    x_fit = np.linspace(FIT_LOW, FIT_HIGH, 500)
    bin_width = (FIT_HIGH - FIT_LOW) / 110

    if data_edges is not None:
        centers = 0.5 * (data_edges[:-1] + data_edges[1:])
        bin_w = data_edges[1] - data_edges[0]
        data_err = np.sqrt(np.maximum(data_sumw2, 0))
        mask = data_counts > 0
        ax_main.errorbar(
            centers[mask], data_counts[mask], yerr=data_err[mask],
            fmt="ko", ms=3, label="Data", zorder=5
        )

    # Plot fit curves if available
    bkg_fit = None
    if fit_result is not None:
        try:
            from analysis.stats.fit import (
                dscb_pdf, bernstein_pdf_eval, bernstein_norm,
                FIT_LOW as FL, FIT_HIGH as FH
            )
            dscb_p = fit_result.get("dscb_parameters", {})
            bkg_coeffs = np.array(fit_result.get("bestfit_bkg_coeffs", [1.0, 1.0, 1.0]))
            n_bkg = fit_result.get("bestfit_n_bkg", 0)
            n_sig = fit_result.get("bestfit_n_sig", 0)

            bkg_unnorm = bernstein_pdf_eval(x_fit, bkg_coeffs)
            bkg_n = bernstein_norm(bkg_coeffs)
            bkg_fit = n_bkg * bkg_unnorm / max(bkg_n, 1e-30) * bin_width

            sig_unnorm = dscb_pdf(x_fit, **dscb_p) if dscb_p else np.zeros_like(x_fit)
            x_norm = np.linspace(FL, FH, 1000)
            sig_n = np.trapezoid(dscb_pdf(x_norm, **dscb_p), x_norm) if dscb_p else 1.0
            sig_fit = n_sig * sig_unnorm / max(sig_n, 1e-30) * bin_width

            ax_main.plot(x_fit, bkg_fit, "b--", lw=1.5, label="Background")
            ax_main.plot(x_fit, bkg_fit + sig_fit, "r-", lw=2, label="Signal+Background")
        except Exception as e:
            print(f"Warning: fit overlay failed: {e}")

    ax_main.axvspan(BLIND_LOW, BLIND_HIGH, alpha=0.1, color="gray")
    ax_main.set_xlim(FIT_LOW, FIT_HIGH)
    ax_main.set_ylim(bottom=0)
    ax_main.set_ylabel(f"Events / {bin_width:.1f} GeV", fontsize=12)
    ax_main.legend(fontsize=9)
    ax_main.text(0.05, 0.97, "ATLAS Open Data", transform=ax_main.transAxes,
                 fontsize=9, va="top", fontstyle="italic")

    # Pull plot
    if data_edges is not None and bkg_fit is not None:
        x_bkg_interp = np.interp(centers, x_fit, bkg_fit / bin_width)
        bkg_interp_counts = x_bkg_interp * bin_w
        pull = np.where(
            data_err > 0,
            (data_counts - bkg_interp_counts) / (data_err + 1e-10),
            0.0,
        )
        ax_pull.bar(centers, pull, width=bin_w, color="#4477AA", alpha=0.7)
        ax_pull.axhline(0, color="black", lw=0.8)
        ax_pull.set_ylim(-4, 4)
    else:
        ax_pull.text(0.5, 0.5, "No pull", transform=ax_pull.transAxes, ha="center")

    ax_pull.set_xlabel(r"$m_{\gamma\gamma}$ [GeV]", fontsize=12)
    ax_pull.set_ylabel("Pull", fontsize=10)

    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_all_plots(
    outputs_dir: str,
    registry_path: str,
    regions_path: str,
    fit_id: str,
    out_dir: str,
) -> Dict:
    """Generate all validation plots."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    with open(registry_path) as f:
        registry = json.load(f)

    hists_dir = str(Path(outputs_dir) / "hists")
    yields_dir = str(Path(outputs_dir) / "yields")

    fit_result = None
    results_path = Path(outputs_dir) / "fit" / fit_id / "results.json"
    if results_path.exists():
        try:
            with open(results_path) as f:
                fit_result = json.load(f)
        except Exception:
            pass

    created = {}

    print("Loading kinematics for plotting...")
    try:
        kin = _load_sample_kinematics(registry, max_events_per_sample=100000)
    except Exception as e:
        print(f"Warning: could not load kinematics: {e}")
        kin = {k: np.array([]) for k in [
            "pt1", "pt2", "eta1", "eta2", "mgg", "pt_gg", "deltaR",
            "n_photon", "weights", "types"
        ]}

    # Per-photon plots
    plot_photon_pt_leading(kin, str(out_dir / "photon_pt_leading.png"))
    created["photon_pt_leading"] = str(out_dir / "photon_pt_leading.png")

    plot_photon_pt_subleading(kin, str(out_dir / "photon_pt_subleading.png"))
    created["photon_pt_subleading"] = str(out_dir / "photon_pt_subleading.png")

    plot_photon_eta_leading(kin, str(out_dir / "photon_eta_leading.png"))
    created["photon_eta_leading"] = str(out_dir / "photon_eta_leading.png")

    plot_photon_eta_subleading(kin, str(out_dir / "photon_eta_subleading.png"))
    created["photon_eta_subleading"] = str(out_dir / "photon_eta_subleading.png")

    plot_photon_multiplicity(kin, str(out_dir / "photon_multiplicity.png"))
    created["photon_multiplicity"] = str(out_dir / "photon_multiplicity.png")

    # Diphoton plots
    plot_diphoton_mass_preselection(kin, str(out_dir / "diphoton_mass_preselection.png"))
    created["diphoton_mass_preselection"] = str(out_dir / "diphoton_mass_preselection.png")

    plot_diphoton_pt(kin, str(out_dir / "diphoton_pt.png"))
    created["diphoton_pt"] = str(out_dir / "diphoton_pt.png")

    plot_diphoton_deltaR(kin, str(out_dir / "diphoton_deltaR.png"))
    created["diphoton_deltaR"] = str(out_dir / "diphoton_deltaR.png")

    # Per-category mass plots
    categories = [
        ("SR_UNCONV_CENTRAL_LOW_PTT", 1),
        ("SR_CONV_CENTRAL_LOW_PTT", 2),
        ("SR_CONV_REST_LOW_PTT", 3),
    ]
    for i, (region_id, cat_num) in enumerate(categories, 1):
        out_p = str(out_dir / f"diphoton_mass_category_{i}.png")
        plot_category_mass(region_id, hists_dir, registry, out_p, cat_num=cat_num)
        created[f"diphoton_mass_category_{i}"] = out_p

    # Cutflow plot
    plot_cutflow(outputs_dir, str(out_dir / "cutflow_plot.png"))
    created["cutflow_plot"] = str(out_dir / "cutflow_plot.png")

    # Fit plot (with signal window)
    main_region = "SR_DIPHOTON_INCL"
    plot_diphoton_mass_fit(
        fit_result, hists_dir, main_region, registry,
        str(out_dir / "diphoton_mass_fit.png")
    )
    created["diphoton_mass_fit"] = str(out_dir / "diphoton_mass_fit.png")

    # Pull plot (separate)
    # Reuse the pull subplot as standalone
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.text(0.5, 0.5, "Pull plot (see diphoton_mass_fit.png)",
            transform=ax.transAxes, ha="center", va="center")
    ax.set_xlabel(r"$m_{\gamma\gamma}$ [GeV]")
    ax.set_ylabel("(Data - Fit) / σ")
    fig.savefig(str(out_dir / "diphoton_mass_pull.png"), dpi=150, bbox_inches="tight")
    plt.close(fig)
    created["diphoton_mass_pull"] = str(out_dir / "diphoton_mass_pull.png")

    print(f"Generated {len(created)} plots in {out_dir}")
    return created


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate all validation plots.")
    p.add_argument("--outputs", required=True, help="Output base directory")
    p.add_argument("--registry", required=True, help="Path to samples.registry.json")
    p.add_argument("--regions", required=True, help="Path to regions.yaml")
    p.add_argument("--fit-id", required=True, help="Fit ID (e.g. FIT_MAIN)")
    p.add_argument("--out-dir", required=True, help="Output directory for plots")
    return p


def main():
    args = build_parser().parse_args()

    created = generate_all_plots(
        outputs_dir=args.outputs,
        registry_path=args.registry,
        regions_path=args.regions,
        fit_id=args.fit_id,
        out_dir=args.out_dir,
    )

    print(f"Created {len(created)} plots:")
    for name, path in sorted(created.items()):
        print(f"  {name}: {path}")


if __name__ == "__main__":
    main()
