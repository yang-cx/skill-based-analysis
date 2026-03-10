# FILE: analysis/samples/registry.py
"""Build sample registry from input ROOT files."""

import argparse
import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import uproot

from analysis.common import ensure_dir, write_json

# Luminosity for Run-2 2015+2016 ATLAS Open Data
DEFAULT_LUMI_FB = 36.1

# Signal DSIDs known to be H->gammagamma
SIGNAL_DSIDS = {
    343981,  # ggH125_gamgam Powheg+Pythia8
    346797,  # ggH125_gamgam Herwig
    346214,  # VBFH125_gamgam
    346878,  # VBF125_gammagamma Herwig
    345317,  # WmH125J Hyy
    345318,  # WpH125J Hyy
    345319,  # ZH125J Hyy
    346879,  # ZH125 gammagamma Herwig
    346880,  # WmH125 gammagamma Herwig
    346881,  # WpH125 gammagamma Herwig
    346882,  # ggZH125 gammagamma Herwig
    346189,  # ttH_gamgam
    346525,  # ttH125_gamgam alt
    346526,  # ttH125_gamgam Herwig
}

# Background DSID ranges / patterns
DIPHOTON_DSID_RANGE = range(302520, 302535)  # 2DP20 diphoton slices


def _parse_dsid(filename: str) -> Optional[int]:
    """Extract DSID from filename like ODEO_FEB2025_v0_GamGam_mc_<DSID>.<rest>.root"""
    m = re.search(r"_mc_(\d+)\.", filename)
    if m:
        return int(m.group(1))
    return None


def _classify_sample(filename: str, dsid: Optional[int]) -> str:
    """Classify a sample as 'signal', 'background', or 'data'."""
    name = filename.lower()

    # Data files
    if "data15" in name or "data16" in name:
        return "data"

    if dsid is None:
        return "other"

    # Known signal DSIDs
    if dsid in SIGNAL_DSIDS:
        return "signal"

    # Pattern-based signal detection: H->gammagamma processes
    hgg_patterns = [
        r"ggh125.*gamgam",
        r"vbfh125.*gamgam",
        r"wh125.*gamgam",
        r"zh125.*gamgam",
        r"tth.*gamgam",
        r"ggh125.*gammagamma",
        r"vbfh125.*gammagamma",
        r"wh125.*gammagamma",
        r"zh125.*gammagamma",
        r"tth.*gammagamma",
        r"ggzh125.*gammagamma",
        r"_hyy_",
    ]
    for pat in hgg_patterns:
        if re.search(pat, name):
            return "signal"

    # Diphoton background (2DP20)
    if dsid in DIPHOTON_DSID_RANGE:
        return "background"
    if "2dp20" in name:
        return "background"

    # Gammajet
    if re.search(r"gammajet|gamma_jet|gamjet", name):
        return "background"

    # Jetjet
    if re.search(r"jetjet|jet_jet|jj_", name):
        return "background"

    # ttgamma
    if re.search(r"ttgamma|tt_gamma", name):
        return "background"

    # W/Z + gamma
    if re.search(r"(wgamma|zgamma|wplusgamma|wminusgamma)", name):
        return "background"

    # Sherpa diphoton
    if re.search(r"sherpa.*diphoton|diphoton.*sherpa", name):
        return "background"

    return "other"


def _read_mc_metadata(filepath: str, tree_name: str = "analysis") -> Dict:
    """Read xsec, kfac, filteff, sumw from first event of a ROOT file."""
    metadata = {
        "xsec_pb": None,
        "k_factor": None,
        "filter_eff": None,
        "sumw": None,
        "num_events": None,
    }

    try:
        with uproot.open(filepath) as f:
            tree = None
            if tree_name in f:
                tree = f[tree_name]
            else:
                for key in f.keys():
                    obj = f[key]
                    if hasattr(obj, "keys"):
                        tree = obj
                        break

            if tree is None:
                return metadata

            available = set(tree.keys())

            branch_map = {
                "xsec": "xsec_pb",
                "kfac": "k_factor",
                "filteff": "filter_eff",
                "sum_of_weights": "sumw",
                "num_events": "num_events",
            }

            for src, dst in branch_map.items():
                if src in available:
                    try:
                        arr = tree[src].array(library="np", entry_stop=1)
                        if len(arr) > 0:
                            metadata[dst] = float(arr[0])
                    except Exception as e:
                        print(f"Warning: could not read {src} from {filepath}: {e}")

            # If sumw not available directly, try summing mcWeight
            if metadata["sumw"] is None and "mcWeight" in available:
                try:
                    arr = tree["mcWeight"].array(library="np")
                    metadata["sumw"] = float(np.sum(arr))
                    metadata["num_events"] = len(arr)
                except Exception as e:
                    print(f"Warning: could not compute sumw from mcWeight: {e}")

    except Exception as e:
        print(f"Error reading metadata from {filepath}: {e}")

    return metadata


def _compute_norm_factor(
    xsec_pb: Optional[float],
    k_factor: Optional[float],
    filter_eff: Optional[float],
    sumw: Optional[float],
    lumi_fb: float = DEFAULT_LUMI_FB,
) -> Optional[float]:
    """Compute normalization factor: (xsec * kfac * filteff * lumi * 1000) / sumw."""
    if any(v is None for v in [xsec_pb, k_factor, filter_eff, sumw]):
        return None
    if sumw == 0:
        return None
    return (xsec_pb * k_factor * filter_eff * lumi_fb * 1000.0) / sumw


def scan_directory(
    input_dir: str,
    lumi_fb: float = DEFAULT_LUMI_FB,
    verbose: bool = True,
) -> Dict[str, Dict]:
    """Scan input-data/ directory and build sample registry."""
    input_dir = Path(input_dir)
    samples = {}

    # Scan MC directory
    mc_dir = input_dir / "MC"
    if mc_dir.exists():
        for fpath in sorted(mc_dir.glob("*.root")):
            fname = fpath.name
            dsid = _parse_dsid(fname)
            sample_type = _classify_sample(fname, dsid)

            sample_id = str(dsid) if dsid is not None else fname.replace(".root", "")

            if sample_id in samples:
                samples[sample_id]["files"].append(str(fpath))
                continue

            if verbose:
                print(f"  Scanning {fname} (DSID={dsid}, type={sample_type})")

            meta = {}
            if sample_type in ("signal", "background"):
                meta = _read_mc_metadata(str(fpath))

            norm_factor = None
            if sample_type in ("signal", "background"):
                norm_factor = _compute_norm_factor(
                    meta.get("xsec_pb"),
                    meta.get("k_factor"),
                    meta.get("filter_eff"),
                    meta.get("sumw"),
                    lumi_fb=lumi_fb,
                )

            samples[sample_id] = {
                "sample_id": sample_id,
                "dsid": dsid,
                "type": sample_type,
                "files": [str(fpath)],
                "filename": fname,
                "xsec_pb": meta.get("xsec_pb"),
                "k_factor": meta.get("k_factor"),
                "filter_eff": meta.get("filter_eff"),
                "sumw": meta.get("sumw"),
                "num_events": meta.get("num_events"),
                "norm_factor": norm_factor,
                "lumi_fb": lumi_fb if sample_type != "data" else None,
            }

    # Scan data directory
    data_dir = input_dir / "data"
    if data_dir.exists():
        # Group all data files into one combined sample
        data_files_15 = []
        data_files_16 = []

        for fpath in sorted(data_dir.glob("*.root")):
            fname = fpath.name
            if "data15" in fname.lower():
                data_files_15.append(str(fpath))
            elif "data16" in fname.lower():
                data_files_16.append(str(fpath))

        if data_files_15 or data_files_16:
            all_data_files = data_files_15 + data_files_16
            samples["data_run2"] = {
                "sample_id": "data_run2",
                "dsid": None,
                "type": "data",
                "files": all_data_files,
                "filename": "combined_data15_data16",
                "xsec_pb": None,
                "k_factor": None,
                "filter_eff": None,
                "sumw": None,
                "num_events": None,
                "norm_factor": None,
                "lumi_fb": None,
            }

        # Also keep individual period files if needed
        for fpath in sorted(data_dir.glob("*.root")):
            fname = fpath.name
            period_match = re.search(r"(data1[56]_period\w+)", fname, re.IGNORECASE)
            if period_match:
                period_id = period_match.group(1).lower()
                # These are included in data_run2 above; skip as separate entries
                pass

    return samples


def build_registry(
    input_dir: str,
    summary_path: Optional[str] = None,
    lumi_fb: float = DEFAULT_LUMI_FB,
    verbose: bool = True,
) -> Dict:
    """Build the full sample registry."""
    print(f"Scanning {input_dir} for ROOT files...")
    samples = scan_directory(input_dir, lumi_fb=lumi_fb, verbose=verbose)

    # Compute summary statistics
    n_signal = sum(1 for s in samples.values() if s["type"] == "signal")
    n_background = sum(1 for s in samples.values() if s["type"] == "background")
    n_data = sum(1 for s in samples.values() if s["type"] == "data")
    n_other = sum(1 for s in samples.values() if s["type"] == "other")

    print(
        f"Found: {n_signal} signal, {n_background} background, "
        f"{n_data} data, {n_other} other samples"
    )

    registry = {
        "metadata": {
            "lumi_fb": lumi_fb,
            "n_signal": n_signal,
            "n_background": n_background,
            "n_data": n_data,
            "n_other": n_other,
            "input_dir": str(input_dir),
        },
        "samples": samples,
    }

    return registry


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build sample registry from input ROOT files.")
    p.add_argument("--inputs", required=True, help="Path to input-data/ directory")
    p.add_argument(
        "--summary",
        default=None,
        help="Path to analysis summary JSON (optional)",
    )
    p.add_argument(
        "--out",
        required=True,
        help="Output registry JSON path",
    )
    p.add_argument(
        "--target-lumi-fb",
        type=float,
        default=DEFAULT_LUMI_FB,
        help=f"Target luminosity in fb^-1 (default: {DEFAULT_LUMI_FB})",
    )
    p.add_argument("--verbose", action="store_true", default=True)
    p.add_argument("--quiet", action="store_true", default=False)
    return p


def main():
    args = build_parser().parse_args()
    verbose = args.verbose and not args.quiet

    registry = build_registry(
        input_dir=args.inputs,
        summary_path=args.summary,
        lumi_fb=args.target_lumi_fb,
        verbose=verbose,
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_path, registry)
    print(f"Registry written to {out_path}")
    print(f"  Total samples: {len(registry['samples'])}")


if __name__ == "__main__":
    main()
