import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import awkward as ak
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

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



def _load_cache_events(cache_dir: Path, kind_map: Dict[str, str]) -> Dict[str, ak.Array]:
    grouped = {"data": [], "signal": [], "background": []}
    for pq in sorted(cache_dir.glob("*.objects.parquet")):
        sample_id = pq.name.replace(".objects.parquet", "")
        kind = kind_map.get(sample_id, "background")
        arr = ak.from_parquet(pq)
        grouped.setdefault(kind, []).append(arr)

    out = {}
    for kind, parts in grouped.items():
        if not parts:
            continue
        out[kind] = parts[0] if len(parts) == 1 else ak.concatenate(parts, axis=0)
    return out



def _hist_plot(values: np.ndarray, bins: np.ndarray, out: Path, xlabel: str, ylabel: str = "Events") -> None:
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.hist(values, bins=bins, histtype="stepfilled", alpha=0.65, color="#2f4f4f")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)



def _to_np(arr: ak.Array) -> np.ndarray:
    return np.asarray(ak.to_numpy(arr), dtype=float)



def _make_object_event_plots(events: ak.Array, out_dir: Path) -> None:
    n2 = events["n_photons_tight"] >= 2

    _hist_plot(_to_np(events["lead_photon_pt"]), np.linspace(0, 250, 60), out_dir / "photon_pt_leading.png", "pT(gamma1) [GeV]")
    _hist_plot(_to_np(events["sublead_photon_pt"]), np.linspace(0, 200, 60), out_dir / "photon_pt_subleading.png", "pT(gamma2) [GeV]")
    _hist_plot(_to_np(events["lead_photon_eta"]), np.linspace(-2.6, 2.6, 52), out_dir / "photon_eta_leading.png", "eta(gamma1)")
    _hist_plot(_to_np(events["sublead_photon_eta"]), np.linspace(-2.6, 2.6, 52), out_dir / "photon_eta_subleading.png", "eta(gamma2)")

    _hist_plot(_to_np(events["m_gg"][n2]), np.linspace(100, 180, 80), out_dir / "diphoton_mass_preselection.png", "m(gammagamma) [GeV]")
    _hist_plot(_to_np(events["diphoton_pt"][n2]), np.linspace(0, 300, 80), out_dir / "diphoton_pt.png", "pT(gammagamma) [GeV]")
    _hist_plot(_to_np(events["diphoton_deltaR"][n2]), np.linspace(0, 6, 60), out_dir / "diphoton_deltaR.png", "DeltaR(gamma1,gamma2)")

    _hist_plot(_to_np(events["n_photons_tight"]), np.arange(-0.5, 8.5, 1), out_dir / "photon_multiplicity.png", "N tight photons")



def _make_cutflow_plot(cutflow_jsons: List[Path], out_dir: Path) -> None:
    if not cutflow_jsons:
        write_json(out_dir / "cutflow_table.json", {"cutflow": {}})
        return

    payload = read_json(cutflow_jsons[0])
    write_json(out_dir / "cutflow_table.json", payload)

    cutflow = payload.get("cutflow", {})
    if not cutflow:
        return
    first_region = sorted(cutflow.keys())[0]
    rows = cutflow[first_region]

    names = [r["name"] for r in rows]
    vals = [r["n_raw"] for r in rows]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(range(len(vals)), vals, marker="o", color="#b22222")
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=30, ha="right")
    ax.set_ylabel("Events")
    ax.set_title("Cut flow")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_dir / "cutflow_plot.png", dpi=140)
    plt.close(fig)



def _load_region_hists(hists_dir: Path, region: str) -> Dict[str, np.ndarray]:
    region_dir = hists_dir / region
    if not region_dir.exists():
        return {}
    obs_dirs = [p for p in region_dir.iterdir() if p.is_dir()]
    if not obs_dirs:
        return {}
    obs_dir = sorted(obs_dirs)[0]

    out = {}
    for npz_path in sorted(obs_dir.glob("*.npz")):
        data = np.load(npz_path, allow_pickle=True)
        out[npz_path.stem] = {
            "edges": data["edges"].astype(float),
            "counts": data["counts"].astype(float),
            "sumw2": data["sumw2"].astype(float),
            "meta": json.loads(str(data["metadata"])),
        }
    return out



def _make_category_plots(events: ak.Array, out_dir: Path) -> None:
    # Proxy categories from diphoton pT quantiles.
    n2 = events["n_photons_tight"] >= 2
    m = _to_np(events["m_gg"][n2])
    pt = _to_np(events["diphoton_pt"][n2])
    if len(m) == 0:
        return

    q1, q2 = np.quantile(pt, [1.0 / 3.0, 2.0 / 3.0])
    cats = [
        (pt <= q1, "1"),
        ((pt > q1) & (pt <= q2), "2"),
        (pt > q2, "3"),
    ]

    for mask, name in cats:
        fig, ax = plt.subplots(figsize=(7, 5))
        ax.hist(m[mask], bins=np.linspace(105, 160, 56), histtype="stepfilled", alpha=0.65, color="#1f77b4")
        ax.set_xlabel("m(gammagamma) [GeV]")
        ax.set_ylabel("Events")
        ax.set_title("Category {}".format(name))
        ax.grid(alpha=0.2)
        fig.tight_layout()
        fig.savefig(out_dir / ("diphoton_mass_category_{}.png".format(name)), dpi=140)
        plt.close(fig)



def _make_fit_and_pull_plots(
    hists_dir: Path,
    fit_results_dir: Path,
    out_dir: Path,
    kind_map: Dict[str, str],
) -> None:
    regions = [p.name for p in hists_dir.iterdir() if p.is_dir()]
    if not regions:
        return
    region = sorted(regions)[0]
    region_hists = _load_region_hists(hists_dir, region)
    if not region_hists:
        return

    # Aggregate by sample kind.
    edges = None
    signal = None
    background = None
    data = None
    for sample, h in region_hists.items():
        edges = h["edges"]
        kind = kind_map.get(sample, "background")
        if kind == "data":
            data = h["counts"] if data is None else data + h["counts"]
        elif kind == "signal":
            signal = h["counts"] if signal is None else signal + h["counts"]
        else:
            background = h["counts"] if background is None else background + h["counts"]

    if background is None:
        background = np.zeros_like(next(iter(region_hists.values()))["counts"])
    if signal is None:
        signal = np.zeros_like(background)
    if data is None:
        data = background + signal

    mu = 1.0
    fit_files = sorted(fit_results_dir.glob("*/results.json"))
    if fit_files:
        fit_payload = read_json(fit_files[0])
        if isinstance(fit_payload.get("bestfit_poi"), (int, float)):
            mu = float(fit_payload["bestfit_poi"])

    model = background + mu * signal
    centers = 0.5 * (edges[:-1] + edges[1:])

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.step(edges[:-1], model, where="post", color="#d62728", label="Model")
    ax.errorbar(centers, data, yerr=np.sqrt(np.clip(data, 0, None)), fmt="o", color="black", label="Data", ms=3)
    ax.set_xlabel("m(gammagamma) [GeV]")
    ax.set_ylabel("Events / bin")
    ax.legend()
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_dir / "diphoton_mass_fit.png", dpi=140)
    plt.close(fig)

    pull = (data - model) / np.sqrt(np.clip(model, 1e-6, None))
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.axhline(0.0, color="black", lw=1)
    ax.bar(centers, pull, width=np.diff(edges), align="center", color="#2ca02c", alpha=0.7)
    ax.set_xlabel("m(gammagamma) [GeV]")
    ax.set_ylabel("Pull")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_dir / "diphoton_mass_pull.png", dpi=140)
    plt.close(fig)



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Produce validation and final plots")
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--registry", default="outputs/samples.registry.json")
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    outputs = Path(args.outputs)
    plots_dir = ensure_dir(outputs / "report" / "plots")
    cache_dir = outputs / "cache"
    hists_dir = outputs / "hists"
    fit_dir = outputs / "fit"

    kind_map = _load_kind_map(Path(args.registry))
    grouped = _load_cache_events(cache_dir, kind_map)
    events = grouped.get("data")
    if events is None:
        events = grouped.get("signal")
    if events is None:
        events = grouped.get("background")

    if events is not None and len(events) > 0:
        _make_object_event_plots(events, plots_dir)
        _make_category_plots(events, plots_dir)

    _make_cutflow_plot(sorted((outputs / "cutflows").glob("*.json")), plots_dir)
    _make_fit_and_pull_plots(hists_dir, fit_dir, plots_dir, kind_map)

    print("plots written under {}".format(plots_dir))


if __name__ == "__main__":
    main()
