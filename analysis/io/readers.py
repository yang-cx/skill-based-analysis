# FILE: analysis/io/readers.py
"""Load events from ROOT ntuples using uproot."""

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Union

import awkward as ak
import numpy as np
import uproot


def load_events(
    files: Union[str, List[str]],
    tree_name: str = "analysis",
    branches: Optional[List[str]] = None,
    max_events: Optional[int] = None,
) -> Dict[str, np.ndarray]:
    """Load events from one or more ROOT files.

    Parameters
    ----------
    files:
        A single file path or list of file paths.
    tree_name:
        Name of the TTree inside the ROOT file.
    branches:
        List of branch names to read. If None, reads all branches.
    max_events:
        Maximum number of events to load (None = all).

    Returns
    -------
    dict mapping branch_name -> numpy or awkward array.
    Variable-length (jagged) arrays for photon_*, jet_* are kept as
    awkward arrays; scalar branches become numpy arrays.
    """
    if isinstance(files, (str, Path)):
        files = [str(files)]
    else:
        files = [str(f) for f in files]

    all_arrays: Dict[str, list] = {}
    total_loaded = 0

    for filepath in files:
        if max_events is not None and total_loaded >= max_events:
            break

        remaining = None if max_events is None else max_events - total_loaded

        try:
            with uproot.open(filepath) as root_file:
                # Try to find the tree
                tree = None
                if tree_name in root_file:
                    tree = root_file[tree_name]
                else:
                    # Search for a tree
                    for key in root_file.keys():
                        obj = root_file[key]
                        if hasattr(obj, "keys"):
                            tree = obj
                            break
                    if tree is None:
                        print(f"Warning: tree '{tree_name}' not found in {filepath}")
                        continue

                # Determine which branches to read
                available = set(tree.keys())
                if branches is not None:
                    read_branches = [b for b in branches if b in available]
                    missing = set(branches) - set(read_branches)
                    if missing:
                        print(f"Warning: branches not found in {filepath}: {missing}")
                else:
                    read_branches = list(available)

                if not read_branches:
                    continue

                # Read events
                kwargs = {"entry_stop": remaining} if remaining is not None else {}
                arrays = tree.arrays(read_branches, library="ak", **kwargs)

                n_events = len(arrays[read_branches[0]])
                total_loaded += n_events

                for branch in read_branches:
                    if branch not in all_arrays:
                        all_arrays[branch] = []
                    all_arrays[branch].append(arrays[branch])

        except Exception as e:
            print(f"Error reading {filepath}: {e}")
            continue

    if not all_arrays:
        return {}

    # Concatenate across files
    result = {}
    for branch, chunks in all_arrays.items():
        if not chunks:
            continue
        try:
            combined = ak.concatenate(chunks, axis=0)
            # Convert to numpy if possible (non-jagged)
            if combined.ndim == 1:
                try:
                    result[branch] = np.asarray(combined)
                except Exception:
                    result[branch] = combined
            else:
                result[branch] = combined
        except Exception as e:
            print(f"Warning: could not concatenate branch {branch}: {e}")
            result[branch] = chunks[0] if len(chunks) == 1 else chunks

    return result


def save_to_parquet(data: Dict, out_path: str) -> None:
    """Save event data dict to parquet format using awkward-array."""
    import awkward as ak

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Build an awkward record array
    fields = {}
    for key, arr in data.items():
        try:
            fields[key] = ak.Array(arr)
        except Exception as e:
            print(f"Warning: skipping branch {key} for parquet: {e}")

    if not fields:
        print("No data to save.")
        return

    record = ak.Array(fields)
    ak.to_parquet(record, str(out_path))
    print(f"Saved {len(record)} events to {out_path}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Load events from ROOT ntuples and cache to parquet."
    )
    p.add_argument("--registry", required=True, help="Path to samples.registry.json")
    p.add_argument("--sample", required=True, help="Sample ID to load")
    p.add_argument(
        "--max-events", type=int, default=None, help="Maximum events to load"
    )
    p.add_argument("--out", required=True, help="Output parquet file path")
    p.add_argument("--tree", default="analysis", help="TTree name (default: analysis)")
    p.add_argument("--branches", nargs="*", default=None, help="Branch names to read")
    return p


def main():
    args = build_parser().parse_args()

    # Load registry
    with open(args.registry) as f:
        registry = json.load(f)

    samples = registry.get("samples", registry)
    if args.sample not in samples:
        raise KeyError(f"Sample '{args.sample}' not found in registry.")

    sample_info = samples[args.sample]
    files = sample_info.get("files", [])
    if not files:
        raise ValueError(f"No files listed for sample '{args.sample}'.")

    print(f"Loading sample '{args.sample}' from {len(files)} file(s)...")
    data = load_events(
        files,
        tree_name=args.tree,
        branches=args.branches,
        max_events=args.max_events,
    )

    n_events = 0
    for arr in data.values():
        try:
            n_events = len(arr)
            break
        except Exception:
            pass

    print(f"Loaded {n_events} events, {len(data)} branches.")
    save_to_parquet(data, args.out)


if __name__ == "__main__":
    main()
