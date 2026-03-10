"""Load and validate the analysis summary JSON."""
import argparse
import json
from pathlib import Path

from analysis.common import write_json


def load_and_validate(summary_path):
    with open(summary_path) as f:
        data = json.load(f)

    sr_ids = [r["signal_region_id"] for r in data.get("signal_regions", [])]
    cr_ids = [r["control_region_id"] for r in data.get("control_regions", [])]
    fit_ids = [f["fit_id"] for f in data.get("fit_setup", [])]
    observables = list({
        r.get("fit_observable", "m_gammagamma")
        for r in data.get("signal_regions", []) + data.get("control_regions", [])
    })
    pois = list({
        poi
        for f in data.get("fit_setup", [])
        for poi in f.get("parameters_of_interest", [])
    })

    # Cross-reference checks
    for fit in data.get("fit_setup", []):
        for rid in fit.get("regions_included", []):
            assert rid in sr_ids or rid in cr_ids, f"Fit region {rid} not declared"

    # Overlap policy: default mutually exclusive
    overlap_policy = []
    for sr in sr_ids:
        for cr in cr_ids:
            overlap_policy.append({"sr": sr, "cr": cr, "allow_overlap": False})

    inventory = {
        "n_signal_regions": len(sr_ids),
        "n_control_regions": len(cr_ids),
        "n_fits": len(fit_ids),
        "signal_region_ids": sr_ids,
        "control_region_ids": cr_ids,
        "fit_ids": fit_ids,
        "observables": observables,
        "pois": pois,
    }
    data["_inventory"] = inventory
    data["_overlap_policy"] = overlap_policy
    return data


def build_parser():
    p = argparse.ArgumentParser()
    p.add_argument("--summary", required=True)
    p.add_argument("--out", required=True)
    return p


def main():
    args = build_parser().parse_args()
    result = load_and_validate(Path(args.summary))
    write_json(args.out, result)
    inv = result["_inventory"]
    print(f"Validated: {inv['n_signal_regions']} SRs, {inv['n_control_regions']} CRs, "
          f"{inv['n_fits']} fits, observables={inv['observables']}")


if __name__ == "__main__":
    main()
