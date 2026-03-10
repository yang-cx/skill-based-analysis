import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import awkward as ak
import numpy as np
import uproot

from analysis.common import ensure_dir, run_metadata, write_json

DSID_RE = re.compile(r"_mc_(\d+)\.")
DEFAULT_TARGET_LUMI_FB = 36.1


def _extract_lumi_fb(summary: Dict[str, Any], target_lumi_fb: Optional[float] = None) -> float:
    if target_lumi_fb is not None:
        lumi = float(target_lumi_fb)
        if lumi <= 0.0:
            raise ValueError("target_lumi_fb must be positive")
        return lumi

    meta = summary.get("analysis_metadata", {})
    candidates = [
        "integrated_luminosity_fb",
        "lumi_fb",
        "luminosity_fb",
        "integrated_luminosity",
    ]
    for key in candidates:
        value = meta.get(key)
        if isinstance(value, (int, float)):
            return float(value)

    # Try nested dicts with value+unit patterns.
    for key, value in meta.items():
        if not isinstance(value, dict):
            continue
        if "lumi" not in key.lower() and "luminosity" not in key.lower():
            continue
        v = value.get("value")
        if isinstance(v, (int, float)):
            unit = str(value.get("unit", "fb")).lower()
            if "pb" in unit:
                return float(v) / 1000.0
            return float(v)
    return DEFAULT_TARGET_LUMI_FB



def _load_metadata_csv(path: Path) -> Dict[str, Dict[str, Any]]:
    mapping: Dict[str, Dict[str, Any]] = {}
    if not path.exists():
        return mapping
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            dsid = str(row.get("dataset_number", "")).strip()
            if not dsid:
                continue
            mapping[dsid] = row
    return mapping



def _find_files(inputs: Path) -> Tuple[List[Path], List[Path]]:
    data_dir = inputs / "data"
    mc_dir = inputs / "MC"
    data_files = sorted(data_dir.glob("*.root")) if data_dir.exists() else []
    mc_files = sorted(mc_dir.glob("*.root")) if mc_dir.exists() else []
    return data_files, mc_files



def _read_norm_info(path: Path) -> Dict[str, Any]:
    info = {
        "sumw": "not_specified",
        "xsec_pb": "not_specified",
        "k_factor": 1.0,
        "filter_eff": 1.0,
        "tree_name": "analysis",
        "n_events": 0,
        "available_branches": [],
    }

    try:
        with uproot.open(path) as f:
            tree = f["analysis"]
            info["tree_name"] = "analysis"
            info["n_events"] = int(tree.num_entries)
            branches = list(tree.keys())
            info["available_branches"] = branches

            small = tree.arrays(
                [
                    b
                    for b in ["sum_of_weights", "xsec", "kfac", "filteff"]
                    if b in branches
                ],
                entry_start=0,
                entry_stop=1,
                library="ak",
            )

            if "sum_of_weights" in small.fields:
                info["sumw"] = float(ak.to_numpy(small["sum_of_weights"])[0])
            if "xsec" in small.fields:
                info["xsec_pb"] = float(ak.to_numpy(small["xsec"])[0])
            if "kfac" in small.fields:
                info["k_factor"] = float(ak.to_numpy(small["kfac"])[0])
            if "filteff" in small.fields:
                info["filter_eff"] = float(ak.to_numpy(small["filteff"])[0])
    except Exception:
        pass

    return info



def _sample_kind(kind_hint: str, process_name: str, filename: str) -> str:
    if kind_hint == "data":
        return "data"

    token = (process_name + " " + filename).lower()
    signal_markers = ["h125", "hyy", "gammagamma", "gamgam", "_yy", "higgs"]
    if (
        ("h125" in token or "hyy" in token or "higgs" in token or "125" in token)
        and any(x in token for x in signal_markers)
    ):
        return "signal"
    return "background"



def _to_float_or_ns(value: Any) -> Any:
    if value == "not_specified":
        return value
    try:
        return float(value)
    except Exception:
        return "not_specified"



def _compute_w_norm(sample: Dict[str, Any]) -> Any:
    if sample["kind"] == "data":
        return 1.0

    xsec = sample["xsec_pb"]
    k = sample["k_factor"]
    eff = sample["filter_eff"]
    lumi = sample["lumi_fb"]
    sumw = sample["sumw"]

    if any(v == "not_specified" for v in [xsec, k, eff, lumi, sumw]):
        return "not_specified"
    if float(sumw) == 0.0:
        return "not_specified"

    return (float(xsec) * float(k) * float(eff) * float(lumi) * 1000.0) / float(sumw)



def build_registry(
    inputs: Path,
    summary_path: Path,
    out: Path,
    target_lumi_fb: Optional[float] = None,
) -> Dict[str, Any]:
    with summary_path.open() as f:
        summary = json.load(f)

    lumi_fb = _extract_lumi_fb(summary, target_lumi_fb=target_lumi_fb)
    metadata_map = _load_metadata_csv(Path("skills/open-data-specific/metadata.csv"))

    data_files, mc_files = _find_files(inputs)

    samples: List[Dict[str, Any]] = []

    def append_sample(path: Path, kind_hint: str) -> None:
        basename = path.name
        dsid_match = DSID_RE.search(basename)
        dsid = dsid_match.group(1) if dsid_match else ""
        meta_csv = metadata_map.get(dsid, {})

        norm = _read_norm_info(path)

        process_name = meta_csv.get("process") or basename.replace(".root", "")

        sample = {
            "sample_id": dsid if dsid else basename.replace(".root", ""),
            "sample_name": basename.replace(".root", ""),
            "process_name": process_name,
            "kind": _sample_kind(kind_hint, process_name, basename),
            "files": [str(path)],
            "xsec_pb": _to_float_or_ns(norm["xsec_pb"]),
            "k_factor": _to_float_or_ns(norm["k_factor"]),
            "filter_eff": _to_float_or_ns(norm["filter_eff"]),
            "sumw": _to_float_or_ns(norm["sumw"]),
            "lumi_fb": float(lumi_fb),
            "weight_expr": "event_weight",
            "n_events": int(norm["n_events"]),
            "tree_name": norm["tree_name"],
        }

        # Fill missing normalization from metadata.csv when possible.
        if sample["xsec_pb"] == "not_specified" and meta_csv.get("crossSection_pb"):
            sample["xsec_pb"] = float(meta_csv["crossSection_pb"])
        if sample["k_factor"] == "not_specified" and meta_csv.get("kFactor"):
            sample["k_factor"] = float(meta_csv["kFactor"])
        if sample["filter_eff"] == "not_specified" and meta_csv.get("genFiltEff"):
            sample["filter_eff"] = float(meta_csv["genFiltEff"])
        if sample["sumw"] == "not_specified" and meta_csv.get("sumOfWeights"):
            sample["sumw"] = float(meta_csv["sumOfWeights"])

        sample["w_norm"] = _compute_w_norm(sample)
        if sample["kind"] == "data":
            sample["w_norm"] = 1.0
            sample["xsec_pb"] = "not_specified"
            sample["k_factor"] = 1.0
            sample["filter_eff"] = 1.0
            sample["sumw"] = float(sample["n_events"]) if sample["n_events"] else "not_specified"

        samples.append(sample)

    for p in data_files:
        append_sample(p, "data")
    for p in mc_files:
        append_sample(p, "mc")

    registry = {
        "inputs": str(inputs),
        "summary": str(summary_path),
        "normalization": {
            "target_lumi_fb": float(lumi_fb),
            "source": "cli_override" if target_lumi_fb is not None else "summary_or_default",
        },
        "samples": samples,
        "meta": run_metadata(summary_path, Path("analysis/regions.yaml")),
    }
    write_json(out, registry)
    return registry



def _print_table(samples: List[Dict[str, Any]]) -> None:
    print("sample_id\tkind\tn_files\txsec_pb\tsumw\tw_norm")
    for s in samples:
        print(
            "{sid}\t{kind}\t{nf}\t{xsec}\t{sumw}\t{wn}".format(
                sid=s["sample_id"],
                kind=s["kind"],
                nf=len(s["files"]),
                xsec=s["xsec_pb"],
                sumw=s["sumw"],
                wn=s["w_norm"],
            )
        )



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build sample registry")
    parser.add_argument("--inputs", required=True, help="Input directory containing data/ and MC/")
    parser.add_argument("--summary", required=True, help="Path to analysis summary JSON")
    parser.add_argument("--out", required=True, help="Output registry JSON")
    parser.add_argument(
        "--target-lumi-fb",
        type=float,
        default=DEFAULT_TARGET_LUMI_FB,
        help="Integrated luminosity in fb^-1 used for MC normalization.",
    )
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    out = Path(args.out)
    ensure_dir(out.parent)
    registry = build_registry(
        Path(args.inputs),
        Path(args.summary),
        out,
        target_lumi_fb=float(args.target_lumi_fb),
    )

    print("registry built: {} samples".format(len(registry["samples"])))
    _print_table(registry["samples"])


if __name__ == "__main__":
    main()
