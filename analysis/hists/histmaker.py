import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import awkward as ak
import numpy as np

from analysis.common import ensure_dir, read_json
from analysis.io.readers import load_events
from analysis.objects.photons import build_photons
from analysis.samples.weights import event_weight
from analysis.selections.engine import load_regions, region_masks



def _lookup_sample(registry: Dict[str, Any], sample_id: str) -> Dict[str, Any]:
    for sample in registry.get("samples", []):
        if sample_id in (sample.get("sample_id"), sample.get("sample_name")):
            return sample
    raise KeyError("sample not found in registry: {}".format(sample_id))



def _binning_from_fit(fit: Dict[str, Any]) -> Tuple[np.ndarray, str]:
    observable = fit.get("observable", "m_gg")
    binning = fit.get("binning", {})

    if isinstance(binning, dict) and binning.get("type") == "uniform":
        lo, hi = binning.get("range", [105.0, 160.0])
        nbins = int(binning.get("nbins", 55))
        edges = np.linspace(float(lo), float(hi), nbins + 1)
        return edges, observable

    # Default when binning is not fully specified.
    edges = np.linspace(105.0, 160.0, 56)
    return edges, observable



def _hist(values: ak.Array, weights: ak.Array, edges: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    v = ak.to_numpy(values)
    w = ak.to_numpy(weights)
    counts, _ = np.histogram(v, bins=edges, weights=w)
    sumw2, _ = np.histogram(v, bins=edges, weights=w * w)
    return counts.astype(np.float64), sumw2.astype(np.float64)



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Histogram maker")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--regions", required=True)
    parser.add_argument("--summary", required=True)
    parser.add_argument("--max-events", type=int, default=None)
    parser.add_argument("--out", required=True)
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    registry = read_json(Path(args.registry))
    sample = _lookup_sample(registry, args.sample)
    regions_cfg = load_regions(Path(args.regions))

    events = load_events(sample["files"], sample.get("tree_name", "analysis"), max_events=args.max_events)
    photon_cfg = regions_cfg.get("globals", {}).get("photons", {})
    events = build_photons(events, photon_cfg)

    weights = event_weight(events, sample)
    masks = region_masks(events, regions_cfg)

    fits = regions_cfg.get("fits", [])
    if not fits:
        fits = [{"fit_id": "FIT_MAIN", "regions_included": list(masks.keys()), "observable": "m_gg"}]

    out_root = Path(args.out)
    ensure_dir(out_root)

    produced = []
    for fit in fits:
        edges, observable = _binning_from_fit(fit)
        regions_included = fit.get("regions_included", [])
        for rid in regions_included:
            if rid not in masks:
                continue
            mask = masks[rid]
            vals = events[observable] if observable in events.fields else events["m_gg"]
            counts, sumw2 = _hist(vals[mask], weights[mask], edges)

            target = out_root / rid / observable
            ensure_dir(target)
            path = target / (sample["sample_id"] + ".npz")
            meta = {
                "region": rid,
                "sample": sample["sample_id"],
                "observable": observable,
                "fit_id": fit.get("fit_id", "FIT_MAIN"),
            }
            np.savez(path, edges=edges, counts=counts, sumw2=sumw2, metadata=json.dumps(meta))

            integral = float(np.sum(counts))
            produced.append({"path": str(path), "integral": integral, "region": rid})

    print("histograms produced: {}".format(len(produced)))
    for item in produced:
        print("{}\tintegral={:.6g}".format(item["path"], item["integral"]))


if __name__ == "__main__":
    main()
