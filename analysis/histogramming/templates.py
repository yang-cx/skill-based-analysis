# FILE: analysis/histogramming/templates.py
"""Produce histogram templates for m_gg in each region per sample."""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from analysis.common import ensure_dir, write_json
from analysis.io.readers import load_events
from analysis.selections.regions import (
    apply_baseline_diphoton_selection,
    apply_vbf_category,
    compute_diphoton_kinematics,
    compute_ptt,
    extract_event_weights,
    is_central,
    is_transition,
    MGG_LOW,
    MGG_HIGH,
    MGG_BLIND_LOW,
    MGG_BLIND_HIGH,
    LEAD_PT_MIN,
    SUBLEAD_PT_MIN,
    PTT_SPLIT,
)

# Histogram configuration
HIST_BINS = 110
HIST_LOW = 105.0   # GeV
HIST_HIGH = 160.0  # GeV


def make_histogram(values: np.ndarray, weights: Optional[np.ndarray] = None) -> Dict:
    """Create a histogram with fixed binning for m_gg.

    Returns dict with 'edges', 'counts', 'sumw2'.
    """
    edges = np.linspace(HIST_LOW, HIST_HIGH, HIST_BINS + 1)

    if weights is None:
        weights = np.ones(len(values))

    counts, _ = np.histogram(values, bins=edges, weights=weights)
    sumw2, _ = np.histogram(values, bins=edges, weights=weights ** 2)

    return {
        "edges": edges,
        "counts": counts,
        "sumw2": sumw2,
    }


def save_histogram(
    hist: Dict,
    out_path: str,
    metadata: Optional[Dict] = None,
) -> None:
    """Save histogram to .npz file."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    save_dict = {
        "edges": hist["edges"],
        "counts": hist["counts"],
        "sumw2": hist["sumw2"],
    }

    if metadata is not None:
        meta_str = json.dumps(metadata)
        save_dict["metadata"] = np.array([meta_str], dtype=object)

    np.savez(str(out_path), **save_dict)


def build_templates_for_sample(
    sample_id: str,
    registry: Dict,
    out_dir: str,
) -> Dict:
    """Build m_gg histogram templates for all regions for a sample."""
    samples = registry.get("samples", registry)
    if sample_id not in samples:
        raise KeyError(f"Sample '{sample_id}' not found in registry.")

    sample_info = samples[sample_id]
    files = sample_info.get("files", [])
    sample_type = sample_info.get("type", "other")
    norm_factor = sample_info.get("norm_factor") or 1.0
    is_data = sample_type == "data"

    branches = [
        "photon_pt", "photon_eta", "photon_phi", "photon_e",
        "photon_n", "photon_isTightID",
        "jet_pt", "jet_eta", "jet_phi", "jet_e", "jet_jvt",
        "mcWeight", "ScaleFactor_PILEUP", "ScaleFactor_PHOTON",
    ]

    print(f"  Histogramming {sample_id} ({sample_type})...")
    data = load_events(files, branches=branches)

    if not data:
        print(f"  Warning: no data for {sample_id}")
        return {}

    weights = extract_event_weights(data, norm_factor, is_data)

    sel = apply_baseline_diphoton_selection(data)
    if not sel:
        print(f"  Warning: selection failed for {sample_id}")
        return {}

    baseline = sel["baseline_mask"]
    mgg = sel["mgg"]
    ptt = sel["ptt"]
    eta1 = sel["eta1"]
    eta2 = sel["eta2"]
    phi_gg = sel["phi_gg"]

    sideband = baseline & (
        ((mgg >= MGG_LOW) & (mgg < MGG_BLIND_LOW))
        | ((mgg > MGG_BLIND_HIGH) & (mgg <= MGG_HIGH))
    )

    vbf_mask = apply_vbf_category(sel, data)
    non_vbf = baseline & ~vbf_mask

    central = is_central(eta1, eta2)
    transition_flag = is_transition(eta1, eta2)

    transition_cat = non_vbf & transition_flag
    remain = non_vbf & ~transition_flag

    ptt_low = ptt < PTT_SPLIT
    ptt_high = ptt >= PTT_SPLIT

    # Open-data 6-category scheme: no conv/unconv split (conversion status unavailable)
    region_masks = {
        "SR_DIPHOTON_INCL": baseline,
        "CR_BKG_SHAPE_CHECKS": sideband,
        "SR_2JET": vbf_mask,
        "SR_TRANSITION": transition_cat,
        "SR_CENTRAL_LOW_PTT": remain & central & ptt_low,
        "SR_CENTRAL_HIGH_PTT": remain & central & ptt_high,
        "SR_REST_LOW_PTT": remain & ~central & ptt_low,
        "SR_REST_HIGH_PTT": remain & ~central & ptt_high,
    }

    out_dir_path = Path(out_dir)
    created = {}

    for region_id, mask in region_masks.items():
        mgg_sel = mgg[mask]
        w_sel = weights[mask]

        hist = make_histogram(mgg_sel, w_sel)

        metadata = {
            "region": region_id,
            "observable": "m_gammagamma",
            "sample_id": sample_id,
            "sample_type": sample_type,
            "n_events": int(np.sum(mask)),
            "bins": HIST_BINS,
            "low": HIST_LOW,
            "high": HIST_HIGH,
        }

        out_path = out_dir_path / region_id / "m_gg" / f"{sample_id}.npz"
        save_histogram(hist, str(out_path), metadata=metadata)
        created[region_id] = str(out_path)

    print(f"  Saved {len(created)} region histograms for {sample_id}")
    return created


def build_all_templates(registry: Dict, out_dir: str) -> Dict:
    """Build histograms for all samples."""
    samples = registry.get("samples", registry)
    all_created = {}

    for sample_id, info in samples.items():
        sample_type = info.get("type", "other")
        if sample_type == "other":
            continue

        try:
            created = build_templates_for_sample(sample_id, registry, out_dir)
            all_created[sample_id] = created
        except Exception as e:
            print(f"  Error for {sample_id}: {e}")
            all_created[sample_id] = {"error": str(e)}

    return all_created


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build m_gg histogram templates per region per sample."
    )
    p.add_argument("--registry", required=True, help="Path to samples.registry.json")
    p.add_argument("--regions", default=None, help="Path to regions.yaml (optional)")
    p.add_argument("--out-dir", required=True, help="Output directory for histograms")
    p.add_argument(
        "--sample",
        default=None,
        help="Process only this sample ID (default: all)",
    )
    return p


def main():
    args = build_parser().parse_args()

    with open(args.registry) as f:
        registry = json.load(f)

    if args.sample is not None:
        print(f"Building templates for sample: {args.sample}")
        created = build_templates_for_sample(args.sample, registry, args.out_dir)
        print(f"Created {len(created)} histogram files.")
    else:
        print("Building templates for all samples...")
        all_created = build_all_templates(registry, args.out_dir)
        n_total = sum(len(v) for v in all_created.values() if isinstance(v, dict))
        print(f"Created histograms for {len(all_created)} samples, {n_total} total files.")


if __name__ == "__main__":
    main()
