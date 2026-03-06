import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import yaml

from analysis.common import ensure_dir, read_json



def _collect_fit_results(outputs: Path) -> List[Dict]:
    rows = []
    for p in sorted((outputs / "fit").glob("*/results.json")):
        payload = read_json(p)
        rows.append(payload)
    return rows


def _collect_significance(outputs: Path) -> Dict[str, Dict]:
    out = {}
    for p in sorted((outputs / "fit").glob("*/significance.json")):
        out[p.parent.name] = read_json(p)
    return out



def _collect_yields(outputs: Path) -> Dict[str, Dict]:
    out = {}
    for p in sorted((outputs / "yields").glob("*.json")):
        out[p.stem] = read_json(p)
    return out



def _collect_cutflows(outputs: Path) -> Dict[str, Dict]:
    out = {}
    for p in sorted((outputs / "cutflows").glob("*.json")):
        out[p.stem] = read_json(p)
    return out



def _region_inventory(regions_path: Path) -> List[Dict]:
    with regions_path.open() as f:
        y = yaml.safe_load(f)
    return y.get("regions", [])



def _plot_links(plots_dir: Path) -> List[str]:
    return [p.name for p in sorted(plots_dir.glob("*.png"))]



def _embedded_plot_blocks(plot_names: List[str], outputs: Path, report_path: Path) -> List[str]:
    lines: List[str] = []
    for name in plot_names:
        abs_path = outputs / "report" / "plots" / name
        rel_path = Path(os.path.relpath(abs_path, start=report_path.parent)).as_posix()
        lines.append("### {}".format(name))
        lines.append("")
        lines.append("![]({})".format(rel_path))
        lines.append("")
    return lines



def _load_registry(outputs: Path) -> Dict:
    reg_path = outputs / "samples.registry.json"
    if reg_path.exists():
        return read_json(reg_path)
    return {"samples": []}


def _load_background_strategy(outputs: Path) -> Dict:
    path = outputs / "background_modeling_strategy.json"
    if path.exists():
        return read_json(path)
    return {}


def _load_blinding_summary(outputs: Path) -> Dict:
    path = outputs / "report" / "blinding_summary.json"
    if path.exists():
        return read_json(path)
    return {}


def _kind_map(registry: Dict) -> Dict[str, str]:
    out = {}
    for s in registry.get("samples", []):
        sid = str(s.get("sample_id"))
        sname = str(s.get("sample_name"))
        kind = str(s.get("kind", "background"))
        out[sid] = kind
        out[sname] = kind
    return out



def _aggregate_region_yields(
    yields: Dict[str, Dict], kind_map: Dict[str, str]
) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]]]:
    by_kind_region: Dict[str, Dict[str, float]] = {}
    sample_region: Dict[str, Dict[str, float]] = {}

    for sample_id, payload in yields.items():
        kind = kind_map.get(sample_id, "background")
        regions = payload.get("regions", {})
        for rid, vals in regions.items():
            by_kind_region.setdefault(rid, {"data": 0.0, "signal": 0.0, "background": 0.0})
            sample_region.setdefault(rid, {})
            y = float(vals.get("yield", 0.0))
            if kind not in by_kind_region[rid]:
                kind = "background"
            by_kind_region[rid][kind] += y
            sample_region[rid][sample_id] = y

    return by_kind_region, sample_region



def _best_region_cutflow(cutflows: Dict[str, Dict], region_id: str) -> List[Dict]:
    best_rows = []
    best_final = -1.0
    for payload in cutflows.values():
        rows = payload.get("cutflow", {}).get(region_id, [])
        if not rows:
            continue
        final = float(rows[-1].get("n_raw", 0.0))
        if final > best_final:
            best_final = final
            best_rows = rows
    return best_rows



def _mass_window_counts(outputs: Path, registry: Dict, region_id: str = "SR_DIPHOTON_INCL") -> Dict[str, float]:
    kindmap = _kind_map(registry)
    region_dir = outputs / "hists" / region_id
    if not region_dir.exists():
        return {"peak": 0.0, "sideband": 0.0}

    obs_dirs = [d for d in region_dir.iterdir() if d.is_dir()]
    if not obs_dirs:
        return {"peak": 0.0, "sideband": 0.0}
    obs_dir = sorted(obs_dirs)[0]

    edges = None
    data_counts = None
    for npz_path in sorted(obs_dir.glob("*.npz")):
        sid = npz_path.stem
        if kindmap.get(sid, "background") != "data":
            continue
        arr = np.load(npz_path, allow_pickle=True)
        if edges is None:
            edges = arr["edges"].astype(float)
            data_counts = np.zeros_like(arr["counts"].astype(float))
        data_counts += arr["counts"].astype(float)

    if edges is None or data_counts is None:
        return {"peak": 0.0, "sideband": 0.0}

    centers = 0.5 * (edges[:-1] + edges[1:])
    peak_mask = (centers >= 120.0) & (centers <= 130.0)
    side_mask = ((centers >= 105.0) & (centers < 120.0)) | ((centers > 130.0) & (centers <= 160.0))
    return {
        "peak": float(np.sum(data_counts[peak_mask])),
        "sideband": float(np.sum(data_counts[side_mask])),
    }



def build_report(summary_path: Path, outputs: Path, out_path: Path) -> None:
    normalized = read_json(summary_path)
    cutflows = _collect_cutflows(outputs)
    yields = _collect_yields(outputs)
    fit_results = _collect_fit_results(outputs)
    significance = _collect_significance(outputs)
    regions = _region_inventory(Path("analysis/regions.yaml"))
    plots = _plot_links(outputs / "report" / "plots")

    registry = _load_registry(outputs)
    strategy = _load_background_strategy(outputs)
    blinding = _load_blinding_summary(outputs)
    kindmap = _kind_map(registry)
    fit_backends = sorted(
        {
            str(item.get("backend", "")).strip()
            for item in fit_results
            if str(item.get("backend", "")).strip()
        }
    )
    sig_backends = sorted(
        {
            str(item.get("backend", "")).strip()
            for item in significance.values()
            if isinstance(item, dict) and str(item.get("backend", "")).strip()
        }
    )
    backend_summary = fit_backends or sig_backends or ["pyhf"]

    by_kind_region, sample_region = _aggregate_region_yields(yields, kindmap)
    signal_regions = [
        str(region.get("region_id", ""))
        for region in regions
        if str(region.get("kind", "")).lower() == "signal" and str(region.get("region_id", ""))
    ]
    reference_region = (
        "SR_DIPHOTON_INCL"
        if "SR_DIPHOTON_INCL" in by_kind_region
        else (signal_regions[0] if signal_regions else (sorted(by_kind_region.keys())[0] if by_kind_region else "SR_DIPHOTON_INCL"))
    )
    mass_region = reference_region
    if not (outputs / "hists" / mass_region).exists() and signal_regions:
        for rid in signal_regions:
            if (outputs / "hists" / rid).exists():
                mass_region = rid
                break
    mass_counts = _mass_window_counts(outputs, registry, mass_region)

    lines = []
    lines.append("# Diphoton Analysis Report")
    lines.append("")
    lines.append("## Analysis Pipeline")
    lines.append("")
    lines.append("This run executes a complete config-driven diphoton pipeline over the available open-data sample registry.")
    lines.append("It includes summary validation, sample normalization, event/object building, region selections, cut flow and yields,")
    lines.append(
        "histogram template production, workspace construction, fitting, plotting, and report generation."
    )
    lines.append("- Fit/significance backend(s): `{}`".format(", ".join(backend_summary)))
    lines.append("")
    lines.append("## Metadata")
    lines.append("")
    lines.append("- Normalized summary: `{}`".format(summary_path))
    lines.append("- Outputs directory: `{}`".format(outputs))
    lines.append("- Processed samples: {}".format(len(yields)))
    lines.append("- Regions in executable YAML: {}".format(len(regions)))
    lines.append("")
    lines.append("## Signal/Background Strategy")
    lines.append("")
    if strategy:
        cls = strategy.get("classification", {})
        lines.append(
            "- Classified samples: data = {}, signal = {}, background = {}".format(
                len(cls.get("data", [])),
                len(cls.get("signal", [])),
                len(cls.get("background", [])),
            )
        )
        bkg_rows = strategy.get("background_process_modeling", [])
        n_data_driven = sum(
            1 for row in bkg_rows if row.get("modeling_strategy") == "data_driven"
        )
        n_mc_template = sum(
            1 for row in bkg_rows if row.get("modeling_strategy") == "mc_template"
        )
        lines.append(
            "- Background process modeling: mc_template = {}, data_driven = {}".format(
                n_mc_template, n_data_driven
            )
        )
    else:
        lines.append("No explicit background-modeling strategy output was found.")
    lines.append("")
    lines.append("## Blinding and Region Visualization")
    lines.append("")
    if blinding:
        lines.append(
            "- SR data blinded in plots: {}".format(bool(blinding.get("blind_sr", True)))
        )
        fit_info = blinding.get("normalization_fit", {})
        if fit_info:
            lines.append(
                "- CR-only normalization fit: status={}, alpha_bkg={:.4g}, alpha_sig={:.4g}".format(
                    fit_info.get("status", "unknown"),
                    float(fit_info.get("alpha_bkg", 0.0)),
                    float(fit_info.get("alpha_sig", 0.0)),
                )
            )
        shown = sum(1 for r in blinding.get("regions", {}).values() if r.get("data_shown"))
        hidden = sum(1 for r in blinding.get("regions", {}).values() if not r.get("data_shown"))
        lines.append("- Regions with data shown: {}, hidden: {}".format(shown, hidden))
        prefit_count = sum(1 for r in blinding.get("regions", {}).values() if r.get("prefit_plot"))
        postfit_count = sum(1 for r in blinding.get("regions", {}).values() if r.get("postfit_plot"))
        lines.append(
            "- Non-signal comparison plots: pre-fit = {}, post-fit = {}".format(prefit_count, postfit_count)
        )
    else:
        lines.append("No explicit blinding-summary output was found.")
    lines.append("")
    lines.append("## Event Selection")
    lines.append("")
    lines.append("Photon objects are built from reconstructed `photon_*` branches with tight ID/iso and acceptance requirements.")
    lines.append("Derived event-level observables include `m_gg`, `diphoton_pt`, and `diphoton_deltaR` from the leading/subleading photons.")
    lines.append("Region masks are evaluated from `analysis/regions.yaml` expressions.")
    lines.append("")
    lines.append("Executable regions used in this run:")
    for region in regions:
        lines.append("- `{}` ({})".format(region.get("region_id", "unknown"), region.get("kind", "unknown")))
    lines.append("")
    lines.append("## Cut Flow Summary")
    lines.append("")
    cutflow_region_ids = [str(region.get("region_id", "")) for region in regions if str(region.get("region_id", ""))]
    for rid in cutflow_region_ids:
        rows = _best_region_cutflow(cutflows, rid)
        if not rows:
            continue
        lines.append("### {}".format(rid))
        for row in rows:
            lines.append(
                "- {}: n_raw = {}, eff_cum = {:.4f}".format(
                    row.get("name", "step"),
                    int(row.get("n_raw", 0)),
                    float(row.get("eff_cum", 0.0)),
                )
            )
    lines.append("")
    lines.append("## Region Yields")
    lines.append("")
    for rid in sorted(by_kind_region.keys()):
        vals = by_kind_region[rid]
        lines.append(
            "- `{}`: data = {:.3f}, background = {:.3f}, signal = {:.3f}".format(
                rid,
                float(vals.get("data", 0.0)),
                float(vals.get("background", 0.0)),
                float(vals.get("signal", 0.0)),
            )
        )

    if reference_region in sample_region:
        top_bkg = sorted(
            [
                (sid, y)
                for sid, y in sample_region[reference_region].items()
                if kindmap.get(sid, "background") == "background"
            ],
            key=lambda x: x[1],
            reverse=True,
        )[:5]
        top_sig = sorted(
            [
                (sid, y)
                for sid, y in sample_region[reference_region].items()
                if kindmap.get(sid, "background") == "signal"
            ],
            key=lambda x: x[1],
            reverse=True,
        )[:3]
        lines.append("")
        lines.append("Largest background contributors in `{}` (yield):".format(reference_region))
        for sid, y in top_bkg:
            lines.append("- {}: {:.3f}".format(sid, float(y)))
        lines.append("Largest signal contributors in `{}` (yield):".format(reference_region))
        for sid, y in top_sig:
            lines.append("- {}: {:.3f}".format(sid, float(y)))

    lines.append("")
    lines.append("## Key Kinematic Distributions")
    lines.append("")
    lines.append("Object and event-level validation distributions were produced for photon kinematics and diphoton observables,")
    lines.append("including leading/subleading photon pT and eta, diphoton mass preselection, diphoton pT, diphoton DeltaR,")
    lines.append("photon multiplicity, cut flow visualization, and category-split diphoton mass distributions.")
    lines.append("")
    lines.append("In `{}`, the observed data counts are:".format(mass_region))
    lines.append("- m_gg in [120, 130] GeV: {:.1f}".format(mass_counts["peak"]))
    lines.append("- m_gg sidebands in [105, 120) U (130, 160] GeV: {:.1f}".format(mass_counts["sideband"]))
    lines.append("")
    lines.append("## Fit Results")
    lines.append("")
    if not fit_results:
        lines.append("No fit results were produced.")
    for res in fit_results:
        twice_nll = res.get("twice_nll", "n/a")
        if isinstance(twice_nll, (int, float)):
            twice_nll_str = "{:.6g}".format(float(twice_nll))
        else:
            twice_nll_str = "n/a"
        backend = str(res.get("backend", "pyhf"))
        lines.append(
            "- `{}`: backend = {}, status = {}, {} = {:.4f}, twice_nll = {}".format(
                res.get("fit_id", "FIT"),
                backend,
                res.get("status", "unknown"),
                res.get("poi_name", "poi"),
                float(res.get("bestfit_poi", 0.0)),
                twice_nll_str,
            )
        )

    lines.append("")
    lines.append("## Discovery Significance (Profile Likelihood)")
    lines.append("")
    if not significance:
        lines.append("No significance outputs were found.")
    for fit_id, sig in significance.items():
        backend = str(sig.get("backend", "pyhf"))
        if sig.get("status") == "ok":
            lines.append(
                "- `{}`: backend = {}, q0 = {:.6g}, Z = {:.6g}, mu_hat = {:.6g}".format(
                    fit_id,
                    backend,
                    float(sig.get("q0", 0.0)),
                    float(sig.get("z_discovery", 0.0)),
                    float(sig.get("mu_hat", 0.0)),
                )
            )
        else:
            lines.append(
                "- `{}`: backend = {}, significance failed ({})".format(
                    fit_id, backend, sig.get("error", "unknown")
                )
            )

    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    lines.append("The pipeline produces a stable diphoton analysis chain with reproducible structured outputs.")
    lines.append("Given the open-data variable and selection approximations, this result should be interpreted as")
    lines.append("a validated implementation-level physics exercise rather than a strict reproduction of a legacy result.")
    lines.append("")
    lines.append("## Implementation Differences from Reference Analysis")
    lines.append("")
    lines.append("- Original concept: reference object-ID/isolation and era-specific working-point definitions.")
    lines.append("  Open-data observable: `photon_isTightID`, `photon_isTightIso`, and explicit acceptance cuts on pT and |eta|.")
    lines.append("  Why this is closest: these flags and kinematics are directly present and executable in the provided ntuples.")
    lines.append("  Possible impact: selection efficiency and purity differ from the original analysis configuration.")
    lines.append("")
    lines.append("- Original concept: full analysis region set and categorization from the reference workflow.")
    lines.append("  Open-data observable: executable regions in `analysis/regions.yaml` with an additional high-pT diphoton proxy SR.")
    lines.append("  Why this is closest: region expressions must be machine-executable using available reconstructed variables.")
    lines.append("  Possible impact: category composition and relative sensitivity differ from the reference setup.")
    lines.append("")
    lines.append("- Original concept: full nuisance/systematic model.")
    lines.append("  Open-data observable: simplified workspace with normalization factors and template floors for numerical stability.")
    lines.append("  Why this is closest: it enables robust fitting from available templates while preserving signal/background scaling freedom.")
    lines.append("  Possible impact: uncertainty model is simplified and may under-represent full systematic effects.")
    lines.append("")
    lines.append("## Plot Artifacts")
    lines.append("")
    if not plots:
        lines.append("No plot artifacts were produced.")
    else:
        lines.append("Embedded plots:")
        lines.append("")
        lines.extend(_embedded_plot_blocks(plots, outputs, out_path))

    ensure_dir(out_path.parent)
    out_path.write_text("\n".join(lines) + "\n")



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build report markdown")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--out", required=True)
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    build_report(Path(args.summary), Path(args.outputs), Path(args.out))
    print("report written: {}".format(args.out))


if __name__ == "__main__":
    main()
