import argparse
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

from analysis.common import ensure_dir, read_json, write_json


DATA_DRIVEN_HINTS = (
    "data-driven",
    "datadriven",
    "sideband",
    "abcd",
    "fake",
    "nonprompt",
    "template from data",
)



def _slug(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "process"



def _region_inventory(regions_path: Path) -> Dict[str, List[str]]:
    with regions_path.open() as f:
        payload = yaml.safe_load(f)

    sr = []
    cr = []
    vr = []
    for region in payload.get("regions", []):
        rid = region.get("region_id")
        kind = str(region.get("kind", "")).lower()
        if not rid:
            continue
        if kind == "signal":
            sr.append(rid)
        elif kind == "control":
            cr.append(rid)
        else:
            vr.append(rid)
    return {"signal_regions": sr, "control_regions": cr, "validation_regions": vr}



def _summary_text_blob(summary: Dict[str, Any]) -> str:
    chunks = []
    for key in ["background_processes", "analysis_design_insights", "analysis_objectives"]:
        value = summary.get(key)
        if value is not None:
            chunks.append(str(value).lower())
    return " ".join(chunks)



def _looks_data_driven(process_name: str, summary_blob: str) -> bool:
    token = process_name.lower()
    if any(hint in token for hint in DATA_DRIVEN_HINTS):
        return True
    # If explicit process appears with a data-driven hint in summary text, treat as such.
    return any(hint in summary_blob and token in summary_blob for hint in DATA_DRIVEN_HINTS)



def build_strategy(
    registry_path: Path,
    regions_path: Path,
    summary_path: Path,
    out_path: Path,
) -> Dict[str, Any]:
    registry = read_json(registry_path)
    regions = _region_inventory(regions_path)
    summary = read_json(summary_path) if summary_path and summary_path.exists() else {}
    summary_blob = _summary_text_blob(summary)

    samples = registry.get("samples", [])
    classification = {"data": [], "signal": [], "background": []}
    proc_map: Dict[str, Dict[str, Any]] = {}

    for sample in samples:
        sid = str(sample.get("sample_id"))
        kind = str(sample.get("kind", "background"))
        process = str(sample.get("process_name", sid))
        if kind not in classification:
            kind = "background"
        classification[kind].append(sid)

        proc = proc_map.setdefault(
            process,
            {
                "process_name": process,
                "sample_ids": [],
                "kind": kind,
            },
        )
        proc["sample_ids"].append(sid)
        # Preserve signal/data label if any sample in process has that label.
        if kind in ("signal", "data"):
            proc["kind"] = kind

    sr_ids = regions["signal_regions"]
    cr_ids = regions["control_regions"]
    has_transfer = bool(sr_ids and cr_ids)

    backgrounds = []
    constraints = []
    for process, info in sorted(proc_map.items()):
        if info["kind"] != "background":
            continue

        data_driven = _looks_data_driven(process, summary_blob)
        modeling_strategy = "data_driven" if data_driven else "mc_template"
        normalization_source = "control_regions" if has_transfer else "simulation"

        backgrounds.append(
            {
                "process_name": process,
                "sample_ids": sorted(info["sample_ids"]),
                "modeling_strategy": modeling_strategy,
                "normalization_source": normalization_source,
                "control_regions": cr_ids,
                "signal_regions": sr_ids,
                "correlated_between_cr_sr": has_transfer,
            }
        )

        constraints.append(
            {
                "constraint_id": "norm_{}".format(_slug(process)),
                "process_name": process,
                "normalization_source": normalization_source,
                "control_regions": cr_ids,
                "signal_regions": sr_ids,
                "correlated": has_transfer,
            }
        )

    strategy = {
        "inputs": {
            "registry": str(registry_path),
            "regions": str(regions_path),
            "summary": str(summary_path) if summary_path else None,
        },
        "classification": classification,
        "background_process_modeling": backgrounds,
        "notes": {
            "data_driven_detection": "keyword-based heuristic plus summary context scan",
            "cr_sr_correlation_rule": "if both CR and SR exist, normalization is correlated by default",
        },
    }

    ensure_dir(out_path.parent)
    write_json(out_path, strategy)
    write_json(out_path.parent / "samples.classification.json", classification)
    write_json(out_path.parent / "cr_sr_constraint_map.json", {"constraints": constraints})
    return strategy



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Derive signal/background strategy and CR->SR normalization constraints"
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument("--regions", required=True)
    parser.add_argument("--summary", required=False, default="analysis/analysis.summary.json")
    parser.add_argument("--out", required=True)
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    summary_path = Path(args.summary) if args.summary else None
    strategy = build_strategy(
        registry_path=Path(args.registry),
        regions_path=Path(args.regions),
        summary_path=summary_path,
        out_path=Path(args.out),
    )

    n_data = len(strategy["classification"]["data"])
    n_sig = len(strategy["classification"]["signal"])
    n_bkg = len(strategy["classification"]["background"])
    n_proc = len(strategy["background_process_modeling"])

    print(
        "strategy built: data_samples={} signal_samples={} background_samples={} background_processes={}".format(
            n_data,
            n_sig,
            n_bkg,
            n_proc,
        )
    )


if __name__ == "__main__":
    main()
