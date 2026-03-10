import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from analysis.common import ensure_dir, read_json, run_metadata, write_json



def _load_npz(path: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict[str, Any]]:
    data = np.load(path, allow_pickle=True)
    edges = data["edges"].astype(float)
    counts = data["counts"].astype(float)
    sumw2 = data["sumw2"].astype(float)
    meta = json.loads(str(data["metadata"]))
    return edges, counts, sumw2, meta



def _registry_kind_map(registry_path: Path) -> Dict[str, str]:
    if not registry_path.exists():
        return {}
    reg = read_json(registry_path)
    out = {}
    for s in reg.get("samples", []):
        out[str(s.get("sample_id"))] = s.get("kind", "background")
        out[str(s.get("sample_name"))] = s.get("kind", "background")
    return out



def _load_or_init_systematics(path: Path) -> Dict[str, Any]:
    if path.exists():
        return read_json(path)

    payload = {
        "nuisances": [
            {
                "name": "stat_only",
                "type": "stat",
                "affected_samples": "all",
                "affected_regions": "all",
            }
        ],
        "note": "No explicit systematics specified; stat-only model.",
    }
    write_json(path, payload)
    return payload



def _allowed_channels_from_summary(summary_path: Path) -> List[str]:
    if not summary_path.exists():
        return []
    try:
        payload = read_json(summary_path)
    except Exception:
        return []

    channels: List[str] = []
    for fit in payload.get("fit_setup", []):
        if not isinstance(fit, dict):
            continue
        regions = fit.get("regions_included", [])
        if not isinstance(regions, list):
            continue
        for rid in regions:
            sid = str(rid)
            if sid and sid not in channels:
                channels.append(sid)
    return channels


def build_workspace(
    summary_path: Path,
    hists_dir: Path,
    systematics_path: Path,
    out_path: Path,
    registry_path: Path,
) -> Dict[str, Any]:
    kind_map = _registry_kind_map(registry_path)
    systematics = _load_or_init_systematics(systematics_path)
    allowed_channels = set(_allowed_channels_from_summary(summary_path))

    channels = []
    observations = []

    for region_dir in sorted([p for p in hists_dir.iterdir() if p.is_dir()]):
        if allowed_channels and region_dir.name not in allowed_channels:
            continue
        observable_dirs = [p for p in region_dir.iterdir() if p.is_dir()]
        if not observable_dirs:
            continue
        obs_dir = sorted(observable_dirs)[0]

        group_counts: Dict[str, np.ndarray] = {}
        group_sumw2: Dict[str, np.ndarray] = {}
        data_counts = None

        for npz_path in sorted(obs_dir.glob("*.npz")):
            _, counts, sumw2, meta = _load_npz(npz_path)
            sid = str(meta.get("sample", npz_path.stem))
            kind = kind_map.get(sid, "background")

            if kind == "data":
                data_counts = counts if data_counts is None else data_counts + counts
                continue

            group = "signal" if kind == "signal" else "background"
            if group not in group_counts:
                group_counts[group] = np.zeros_like(counts)
                group_sumw2[group] = np.zeros_like(sumw2)
            group_counts[group] += counts
            group_sumw2[group] += sumw2

        if "background" not in group_counts and "signal" not in group_counts:
            continue

        samples = []
        if "signal" in group_counts:
            signal_data = np.clip(group_counts["signal"], 1e-6, None)
            samples.append(
                {
                    "name": "signal",
                    "data": signal_data.tolist(),
                    "modifiers": [
                        {"name": "mu", "type": "normfactor", "data": None}
                    ],
                }
            )

        if "background" in group_counts:
            background_data = np.clip(group_counts["background"], 1e-6, None)
            samples.append(
                {
                    "name": "background",
                    "data": background_data.tolist(),
                    "modifiers": [
                        {"name": "bkg_norm", "type": "normfactor", "data": None}
                    ],
                }
            )

        channels.append({"name": region_dir.name, "samples": samples})

        if data_counts is None:
            bkg = group_counts.get("background")
            sig = group_counts.get("signal")
            if bkg is None:
                data_counts = sig
            elif sig is None:
                data_counts = bkg
            else:
                data_counts = bkg + sig
        observations.append({"name": region_dir.name, "data": data_counts.tolist()})

    workspace = {
        "channels": channels,
        "observations": observations,
        "measurements": [
            {
                "name": "Measurement",
                "config": {
                    "poi": "mu",
                    "parameters": [
                        {"name": "bkg_norm", "inits": [1.0], "bounds": [[0.01, 10.0]]}
                    ],
                },
            }
        ],
        "version": "1.0.0",
    }

    write_json(out_path, workspace)
    write_json(
        out_path.with_suffix(".meta.json"),
        {
            "systematics": systematics,
            "run": run_metadata(summary_path, Path("analysis/regions.yaml"), systematics_path),
        },
    )
    return workspace



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build pyhf workspace")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--hists", required=True)
    parser.add_argument("--systematics", required=True)
    parser.add_argument("--registry", default="outputs/samples.registry.json")
    parser.add_argument("--out", required=True)
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    out_path = Path(args.out)
    ensure_dir(out_path.parent)

    workspace = build_workspace(
        summary_path=Path(args.summary),
        hists_dir=Path(args.hists),
        systematics_path=Path(args.systematics),
        out_path=out_path,
        registry_path=Path(args.registry),
    )

    print("workspace written: {}".format(out_path))
    print("channels={}".format(len(workspace.get("channels", []))))


if __name__ == "__main__":
    main()
