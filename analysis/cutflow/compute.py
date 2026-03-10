# FILE: analysis/cutflow/compute.py
"""Compute cut flows and yields per region per sample."""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional

import awkward as ak
import numpy as np

from analysis.common import ensure_dir, write_json
from analysis.io.readers import load_events
from analysis.selections.regions import (
    apply_baseline_diphoton_selection,
    apply_vbf_category,
    compute_diphoton_kinematics,
    compute_ptt,
    extract_event_weights,
    extract_tight_leading_photons,
    is_central,
    is_transition,
    passes_eta_acceptance,
    MGG_LOW,
    MGG_HIGH,
    MGG_BLIND_LOW,
    MGG_BLIND_HIGH,
    LEAD_PT_MIN,
    SUBLEAD_PT_MIN,
    PTT_SPLIT,
)


def compute_cutflow_for_sample(
    sample_id: str,
    registry: Dict,
    out_dir: str,
) -> Dict:
    """Compute step-by-step cutflow and yields for a sample.

    Returns dict with per-region yields.
    """
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
        "photon_n", "photon_isTightID", "photon_isTightIso",
        "photon_ptcone20", "photon_topoetcone40",
        "jet_pt", "jet_eta", "jet_phi", "jet_e", "jet_jvt",
        "mcWeight", "ScaleFactor_PILEUP", "ScaleFactor_PHOTON",
    ]

    print(f"  Loading {sample_id}: {len(files)} file(s)")
    data = load_events(files, branches=branches)

    if not data:
        print(f"  Warning: no data for {sample_id}")
        return {"sample_id": sample_id, "regions": {}}

    weights = extract_event_weights(data, norm_factor, is_data)
    n_total = len(weights)

    def yield_info(mask: np.ndarray) -> Dict:
        n_raw = int(np.sum(mask))
        w = weights[mask] if len(mask) > 0 else np.zeros(0)
        return {
            "n_raw": n_raw,
            "yield": float(np.sum(w)),
            "sumw2": float(np.sum(w ** 2)),
        }

    # ---- Step-by-step cuts ----
    steps = {}

    # Step 0: all events
    steps["all_events"] = yield_info(np.ones(n_total, dtype=bool))

    # Get photon arrays
    from analysis.selections.regions import _get_photon_branch

    pt_arr = _get_photon_branch(data, "photon_pt")
    eta_arr = _get_photon_branch(data, "photon_eta")
    phi_arr = _get_photon_branch(data, "photon_phi")
    e_arr = _get_photon_branch(data, "photon_e")
    tight_arr = _get_photon_branch(data, "photon_isTightID")

    if pt_arr is None:
        return {"sample_id": sample_id, "regions": {}}

    # Step 1: >= 2 photons (vectorized)
    n_ph = ak.to_numpy(ak.num(pt_arr))
    mask_ge2 = n_ph >= 2
    steps["ge2_photons"] = yield_info(mask_ge2)

    # Step 2: >= 2 tight photons (vectorized)
    if tight_arr is not None:
        try:
            n_tight = ak.to_numpy(ak.sum(tight_arr == True, axis=1))  # noqa: E712
        except Exception:
            n_tight = ak.to_numpy(ak.num(tight_arr[tight_arr > 0]))
    else:
        n_tight = n_ph
    mask_ge2tight = n_tight >= 2
    steps["ge2_tight_photons"] = yield_info(mask_ge2tight)

    # Step 3-onwards: use the baseline selection
    result = extract_tight_leading_photons(data)
    if result is None:
        return {"sample_id": sample_id, "regions": {}}

    pt1, eta1, phi1, e1, pt2, eta2, phi2, e2, mask_ge2_ph = result

    # Step 3: lead pT > 40 GeV
    mask_lead_pt = mask_ge2_ph & (pt1 > LEAD_PT_MIN)
    steps["lead_pt_gt40"] = yield_info(mask_lead_pt)

    # Step 4: sublead pT > 30 GeV
    mask_sublead_pt = mask_lead_pt & (pt2 > SUBLEAD_PT_MIN)
    steps["sublead_pt_gt30"] = yield_info(mask_sublead_pt)

    # Step 5: eta acceptance
    pass_eta = passes_eta_acceptance(eta1) & passes_eta_acceptance(eta2)
    mask_eta = mask_sublead_pt & pass_eta
    steps["eta_acceptance"] = yield_info(mask_eta)

    # Compute mgg, pTt
    mgg, pt_gg, phi_gg, eta_gg = compute_diphoton_kinematics(pt1, eta1, phi1, e1, pt2, eta2, phi2, e2)
    ptt = compute_ptt(pt1, phi1, pt2, phi2, pt_gg, phi_gg)

    # Step 6: mass window 105-160 GeV
    mask_mgg = mask_eta & (mgg > MGG_LOW) & (mgg < MGG_HIGH)
    steps["mass_window_105_160"] = yield_info(mask_mgg)

    # This is the baseline
    baseline = mask_mgg

    # Region masks
    sideband = baseline & (
        ((mgg >= MGG_LOW) & (mgg < MGG_BLIND_LOW))
        | ((mgg > MGG_BLIND_HIGH) & (mgg <= MGG_HIGH))
    )

    from analysis.selections.regions import apply_vbf_category, _get_photon_branch
    sel = {
        "baseline_mask": baseline,
        "pt1": pt1, "eta1": eta1, "phi1": phi1, "e1": e1,
        "pt2": pt2, "eta2": eta2, "phi2": phi2, "e2": e2,
        "mgg": mgg, "pt_gg": pt_gg, "phi_gg": phi_gg,
        "ptt": ptt,
    }
    vbf_mask = apply_vbf_category(sel, data)
    non_vbf = baseline & ~vbf_mask

    central = is_central(eta1, eta2)
    transition_mask = is_transition(eta1, eta2)

    transition_cat = non_vbf & transition_mask
    remain = non_vbf & ~transition_mask

    ptt_low = ptt < PTT_SPLIT
    ptt_high = ptt >= PTT_SPLIT

    # Open-data 6-category scheme: no conv/unconv split (conversion status unavailable).
    # "central" = both photons |eta| < 0.75; "rest" = not central, not transition.
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

    region_yields = {rid: yield_info(mask) for rid, mask in region_masks.items()}

    # Output per-sample yield JSON
    out_dir_path = Path(out_dir)
    yields_dir = out_dir_path / "yields"
    yields_dir.mkdir(parents=True, exist_ok=True)

    sample_yield = {
        "sample_id": sample_id,
        "type": sample_type,
        "norm_factor": norm_factor,
        "n_events_processed": n_total,
        "cutflow": steps,
        "regions": region_yields,
    }
    write_json(yields_dir / f"{sample_id}.json", sample_yield)

    return sample_yield


def compute_all_cutflows(registry: Dict, out_dir: str) -> Dict:
    """Compute cutflows for all samples in the registry."""
    samples = registry.get("samples", registry)
    out_dir_path = Path(out_dir)

    all_yields = {}
    for sample_id, info in samples.items():
        sample_type = info.get("type", "other")
        if sample_type == "other":
            print(f"Skipping {sample_id} (type=other)")
            continue

        print(f"Processing {sample_id} ({sample_type})...")
        try:
            result = compute_cutflow_for_sample(sample_id, registry, out_dir)
            all_yields[sample_id] = result
        except Exception as e:
            print(f"  Error: {e}")
            all_yields[sample_id] = {"sample_id": sample_id, "error": str(e)}

    # Compute per-region cutflow summaries
    cutflows_dir = out_dir_path / "cutflows"
    cutflows_dir.mkdir(parents=True, exist_ok=True)

    # Gather all region IDs
    all_regions = set()
    for result in all_yields.values():
        all_regions.update(result.get("regions", {}).keys())

    for region_id in all_regions:
        region_summary = {
            "region_id": region_id,
            "samples": {},
        }
        total_yield = 0.0
        total_sumw2 = 0.0
        for sample_id, result in all_yields.items():
            info = result.get("regions", {}).get(region_id)
            if info is not None:
                region_summary["samples"][sample_id] = info
                if result.get("type") != "data":
                    total_yield += info.get("yield", 0.0)
                    total_sumw2 += info.get("sumw2", 0.0)

        region_summary["total_mc_yield"] = total_yield
        region_summary["total_mc_sumw2"] = total_sumw2
        write_json(cutflows_dir / f"{region_id}.json", region_summary)

    return all_yields


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compute cut flows and yields per region per sample."
    )
    p.add_argument("--registry", required=True, help="Path to samples.registry.json")
    p.add_argument("--regions", default=None, help="Path to regions.yaml (optional)")
    p.add_argument("--out-dir", required=True, help="Output base directory")
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

    out_dir = args.out_dir

    if args.sample is not None:
        print(f"Processing single sample: {args.sample}")
        result = compute_cutflow_for_sample(args.sample, registry, out_dir)
        print(f"Done. Regions:")
        for rid, info in result.get("regions", {}).items():
            print(f"  {rid}: n_raw={info['n_raw']}, yield={info['yield']:.2f}")
    else:
        print("Processing all samples...")
        all_yields = compute_all_cutflows(registry, out_dir)
        n = len(all_yields)
        print(f"Done. Processed {n} samples.")


if __name__ == "__main__":
    main()
