import argparse
from pathlib import Path
from typing import Any, Dict

import awkward as ak
import numpy as np

from analysis.common import ensure_dir, run_metadata, write_json, read_json
from analysis.io.readers import load_events
from analysis.objects.photons import build_photons
from analysis.samples.weights import event_weight
from analysis.selections.engine import load_regions, region_masks



def _lookup_sample(registry: Dict[str, Any], sample_id: str) -> Dict[str, Any]:
    for sample in registry.get("samples", []):
        if sample_id in (sample.get("sample_id"), sample.get("sample_name")):
            return sample
    raise KeyError("sample not found in registry: {}".format(sample_id))



def yields_from_masks(masks: Dict[str, ak.Array], weights: ak.Array) -> Dict[str, Dict[str, float]]:
    out = {}
    for rid, mask in masks.items():
        w = ak.to_numpy(weights[mask])
        out[rid] = {
            "n_raw": float(np.sum(ak.to_numpy(mask))),
            "yield": float(np.sum(w)),
            "sumw2": float(np.sum(w * w)),
        }
    return out



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate regions and yields")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--regions", required=True)
    parser.add_argument("--max-events", type=int, default=None)
    parser.add_argument("--out", required=True)
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    registry = read_json(Path(args.registry))
    sample = _lookup_sample(registry, args.sample)

    regions_cfg = load_regions(Path(args.regions))
    events = load_events(
        sample["files"],
        sample.get("tree_name", "analysis"),
        branches=None,
        max_events=args.max_events,
    )
    photon_cfg = regions_cfg.get("globals", {}).get("photons", {})
    events = build_photons(events, photon_cfg)

    weights = event_weight(events, sample)
    masks = region_masks(events, regions_cfg)
    yields = yields_from_masks(masks, weights)

    payload = {
        "sample_id": sample["sample_id"],
        "regions": yields,
        "meta": run_metadata(Path(registry.get("summary", "analysis/summary.json")), Path(args.regions)),
    }

    out_path = Path(args.out)
    ensure_dir(out_path.parent)
    write_json(out_path, payload)

    print("region yields for {}".format(sample["sample_id"]))
    for rid, vals in yields.items():
        print(
            "{}\tn_raw={}\tyield={:.6g}".format(
                rid,
                int(vals["n_raw"]),
                vals["yield"],
            )
        )


if __name__ == "__main__":
    main()
