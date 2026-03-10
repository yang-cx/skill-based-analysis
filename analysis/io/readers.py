import argparse
import json
from pathlib import Path
from typing import Iterable, List, Optional

import awkward as ak
import numpy as np
import uproot

from analysis.common import ensure_dir, read_json



def _sample_lookup(registry: dict, sample_id: str) -> dict:
    for sample in registry.get("samples", []):
        if sample.get("sample_id") == sample_id or sample.get("sample_name") == sample_id:
            return sample
    raise KeyError("sample not found in registry: {}".format(sample_id))



def load_events(
    files: Iterable[str],
    tree_name: str = "analysis",
    branches: Optional[List[str]] = None,
    max_events: Optional[int] = None,
) -> ak.Array:
    file_list = list(files)
    paths = ["{}:{}".format(f, tree_name) for f in file_list]

    expressions = branches
    if branches:
        try:
            with uproot.open(file_list[0]) as f:
                available = set(f[tree_name].keys())
            expressions = [b for b in branches if b in available]
            if not expressions:
                raise RuntimeError(
                    "No requested branches are available in {}:{}".format(
                        file_list[0], tree_name
                    )
                )
        except Exception:
            expressions = branches

    chunks = []
    total = 0
    for arr in uproot.iterate(paths, expressions=expressions, library="ak", step_size="50 MB"):
        n = len(arr)
        if max_events is not None and total + n > max_events:
            keep = max_events - total
            arr = arr[:keep]
            n = len(arr)
        chunks.append(arr)
        total += n
        if max_events is not None and total >= max_events:
            break

    if not chunks:
        return ak.Array({})
    if len(chunks) == 1:
        return chunks[0]
    return ak.concatenate(chunks, axis=0)



def _collection_size(events: ak.Array, field: str) -> float:
    if field not in events.fields:
        return 0.0
    value = events[field]
    if isinstance(value.layout, ak.contents.Content) and value.ndim > 1:
        return float(np.mean(ak.to_numpy(ak.num(value, axis=1))))
    return 0.0



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read ROOT events into columnar cache")
    parser.add_argument("--registry", required=True, help="samples.registry.json")
    parser.add_argument("--sample", required=True, help="sample_id or sample_name")
    parser.add_argument("--max-events", type=int, default=None, help="Maximum events")
    parser.add_argument("--out", required=True, help="Output cache parquet file")
    parser.add_argument(
        "--branches",
        nargs="*",
        default=None,
        help="Optional explicit branch list; defaults to all branches",
    )
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    registry = read_json(Path(args.registry))
    sample = _sample_lookup(registry, args.sample)

    tree_name = sample.get("tree_name", "analysis")
    events = load_events(sample["files"], tree_name, args.branches, args.max_events)

    out_path = Path(args.out)
    ensure_dir(out_path.parent)
    ak.to_parquet(events, out_path)

    print("loaded {} events for {}".format(len(events), sample["sample_id"]))
    print("fields: {}".format(", ".join(events.fields)))
    for obj in ["photon_pt", "jet_pt", "lep_pt", "tau_pt"]:
        if obj in events.fields:
            print("avg_size_{}={:.3f}".format(obj, _collection_size(events, obj)))


if __name__ == "__main__":
    main()
