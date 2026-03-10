import argparse
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import awkward as ak
import numpy as np
import yaml

from analysis.common import ensure_dir, run_metadata, write_json, read_json
from analysis.io.readers import load_events
from analysis.objects.photons import build_photons
from analysis.samples.weights import event_weight


BOOL_WORD_REPLACEMENTS = {
    r"\band\b": "&",
    r"\bor\b": "|",
    r"\bnot\b": "~",
}



def in_range(x: ak.Array, lo: float, hi: float) -> ak.Array:
    return (x >= lo) & (x <= hi)



def deltaR(eta1: ak.Array, phi1: ak.Array, eta2: ak.Array, phi2: ak.Array) -> ak.Array:
    dphi = (phi1 - phi2 + np.pi) % (2 * np.pi) - np.pi
    return np.sqrt((eta1 - eta2) ** 2 + dphi**2)



def inv_mass(
    pt1: ak.Array,
    eta1: ak.Array,
    phi1: ak.Array,
    e1: ak.Array,
    pt2: ak.Array,
    eta2: ak.Array,
    phi2: ak.Array,
    e2: ak.Array,
) -> ak.Array:
    px1 = pt1 * np.cos(phi1)
    py1 = pt1 * np.sin(phi1)
    pz1 = pt1 * np.sinh(eta1)

    px2 = pt2 * np.cos(phi2)
    py2 = pt2 * np.sin(phi2)
    pz2 = pt2 * np.sinh(eta2)

    e = e1 + e2
    px = px1 + px2
    py = py1 + py2
    pz = pz1 + pz2
    m2 = e * e - (px * px + py * py + pz * pz)
    m2 = ak.where(m2 < 0, 0, m2)
    return np.sqrt(m2)



def _normalize_expr(expr: str) -> str:
    norm = " ".join(str(expr).split())
    for pat, repl in BOOL_WORD_REPLACEMENTS.items():
        norm = re.sub(pat, repl, norm)
    return norm



def evaluate_expression(events: ak.Array, expr: str) -> ak.Array:
    if expr is None or str(expr).strip() == "" or str(expr).strip() == "not_specified":
        raise ValueError("selection expression is not executable: {}".format(expr))

    norm_expr = _normalize_expr(str(expr))
    scope = {field: events[field] for field in events.fields}
    helpers = {
        "in_range": in_range,
        "abs": abs,
        "deltaR": deltaR,
        "inv_mass": inv_mass,
        "np": np,
    }
    try:
        value = eval(norm_expr, {"__builtins__": {}}, {**helpers, **scope})
    except Exception as exc:
        raise ValueError("failed to evaluate expression '{}': {}".format(expr, exc))

    # Ensure boolean array-like output.
    out = ak.values_astype(value, np.bool_)
    if len(out) != len(events):
        raise ValueError("expression '{}' did not return event-length mask".format(expr))
    return out



def load_regions(path: Path) -> Dict[str, Any]:
    with path.open() as f:
        payload = yaml.safe_load(f)
    if not isinstance(payload, dict):
        raise ValueError("regions YAML must be a mapping")
    return payload



def region_masks(events: ak.Array, regions_cfg: Dict[str, Any]) -> Dict[str, ak.Array]:
    regions = regions_cfg.get("regions", [])
    if not isinstance(regions, list):
        raise ValueError("regions YAML must contain a list under 'regions'")

    required = regions_cfg.get("derived_columns", {}).get("required", [])
    for field in required:
        if field not in events.fields:
            raise ValueError("missing required derived column: {}".format(field))

    masks = {}
    for region in regions:
        rid = region.get("region_id")
        if not rid:
            raise ValueError("region_id missing in regions YAML")
        sel = region.get("selection")
        masks[rid] = evaluate_expression(events, sel)
    return masks



def compute_cutflow(
    events: ak.Array,
    region: Dict[str, Any],
    weights: ak.Array,
) -> List[Dict[str, Any]]:
    steps = region.get("cutflow_steps", [])
    if not steps:
        steps = [{"name": "selection", "expr": region.get("selection")}]

    cumulative = ak.Array(np.ones(len(events), dtype=np.bool_))
    n_prev_raw = float(len(events))
    n_init_raw = float(len(events))

    rows = []
    for step in steps:
        name = step.get("name", "unnamed_step")
        expr = step.get("expr")
        mask = evaluate_expression(events, expr)
        cumulative = cumulative & mask

        n_raw = float(np.sum(ak.to_numpy(cumulative)))
        n_weighted = float(np.sum(ak.to_numpy(weights[cumulative])))
        eff_step = (n_raw / n_prev_raw) if n_prev_raw > 0 else 0.0
        eff_cum = (n_raw / n_init_raw) if n_init_raw > 0 else 0.0
        n_prev_raw = n_raw

        rows.append(
            {
                "name": name,
                "n_raw": n_raw,
                "n_weighted": n_weighted,
                "eff_step": eff_step,
                "eff_cum": eff_cum,
            }
        )

    return rows



def _lookup_sample(registry: Dict[str, Any], sample_id: str) -> Dict[str, Any]:
    for sample in registry.get("samples", []):
        if sample_id in (sample.get("sample_id"), sample.get("sample_name")):
            return sample
    raise KeyError("sample not found in registry: {}".format(sample_id))



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Selection engine and cut flow")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--regions", required=True)
    parser.add_argument("--max-events", type=int, default=None)
    parser.add_argument("--cutflow", action="store_true")
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

    region_list = regions_cfg.get("regions", [])
    out_rows = {}
    for region in region_list:
        rid = region.get("region_id")
        out_rows[rid] = compute_cutflow(events, region, weights)

    payload = {
        "sample_id": sample["sample_id"],
        "cutflow": out_rows,
        "meta": run_metadata(Path(registry.get("summary", "analysis/summary.json")), Path(args.regions)),
    }
    out_path = Path(args.out)
    ensure_dir(out_path.parent)
    write_json(out_path, payload)

    print("cut flow written: {}".format(out_path))
    for rid, rows in out_rows.items():
        if rows:
            last = rows[-1]
            print("{} -> n_raw={} n_weighted={:.6g}".format(rid, last["n_raw"], last["n_weighted"]))


if __name__ == "__main__":
    main()
