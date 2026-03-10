# FILE: analysis/samples/strategy.py
"""Build signal/background modeling strategy from registry."""

import argparse
import json
from pathlib import Path
from typing import Dict, Optional

from analysis.common import ensure_dir, write_json


def build_strategy(
    registry: Dict,
    regions_cfg: Optional[Dict] = None,
    summary: Optional[Dict] = None,
) -> Dict:
    """Build background modeling strategy per sample.

    Background MC samples get method='mc_template'.
    Signal samples get method='signal_model'.
    Data has no method (data-driven background).
    """
    samples = registry.get("samples", registry)

    strategy_entries = {}
    for sample_id, info in samples.items():
        sample_type = info.get("type", "other")

        if sample_type == "signal":
            method = "signal_model"
        elif sample_type == "background":
            method = "mc_template"
        elif sample_type == "data":
            method = None  # data-driven
        else:
            method = "other"

        entry = {
            "sample_id": sample_id,
            "type": sample_type,
            "method": method,
        }
        if method == "signal_model":
            entry["signal_pdf"] = "double_sided_crystal_ball"
            entry["fit_range_gev"] = [105.0, 160.0]
            entry["mH_gev"] = 125.0
        elif method == "mc_template":
            entry["template_observable"] = "m_gammagamma"
            entry["fit_range_gev"] = [105.0, 160.0]
        elif method is None:
            entry["background_pdf"] = "bernstein_polynomial"
            entry["fit_range_gev"] = [105.0, 160.0]
            entry["sideband_low"] = [105.0, 120.0]
            entry["sideband_high"] = [130.0, 160.0]

        strategy_entries[sample_id] = entry

    # Collect all region IDs from summary or regions_cfg
    all_region_ids = []
    if summary is not None:
        for r in summary.get("signal_regions", []):
            all_region_ids.append(r["signal_region_id"])
        for r in summary.get("control_regions", []):
            all_region_ids.append(r["control_region_id"])
    elif regions_cfg is not None:
        all_region_ids = list(regions_cfg.keys())

    # Build per-region strategy
    region_strategy = {}
    for rid in all_region_ids:
        is_sr = rid.startswith("SR_")
        region_strategy[rid] = {
            "region_id": rid,
            "is_signal_region": is_sr,
            "background_method": "bernstein_polynomial_fit_to_data",
            "signal_method": "double_sided_crystal_ball",
            "blinded": is_sr,
        }

    strategy = {
        "metadata": {
            "description": "Background modeling strategy for H->gammagamma analysis",
            "background_method_default": "mc_template",
            "signal_method": "signal_model",
            "data_method": "data_driven_fit",
        },
        "samples": strategy_entries,
        "regions": region_strategy,
    }

    return strategy


def build_cr_sr_constraint_map(
    strategy: Dict,
    summary: Optional[Dict] = None,
) -> Dict:
    """Build control-region to signal-region constraint map."""
    region_strategy = strategy.get("regions", {})

    sr_ids = [rid for rid, info in region_strategy.items() if info.get("is_signal_region")]
    cr_ids = [rid for rid, info in region_strategy.items() if not info.get("is_signal_region")]

    constraint_map = {
        "signal_regions": sr_ids,
        "control_regions": cr_ids,
        "constraints": [],
    }

    # For each CR, map it to constrain background in SRs
    for cr_id in cr_ids:
        constraint_map["constraints"].append(
            {
                "cr_id": cr_id,
                "constrains_sr": sr_ids,
                "constraint_type": "background_shape",
                "method": "sideband_fit",
            }
        )

    return constraint_map


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build signal/background modeling strategy from registry."
    )
    p.add_argument("--registry", required=True, help="Path to samples.registry.json")
    p.add_argument("--regions", default=None, help="Path to regions.yaml (optional)")
    p.add_argument(
        "--summary",
        default=None,
        help="Path to analysis summary JSON (optional)",
    )
    p.add_argument(
        "--out",
        required=True,
        help="Output background_modeling_strategy.json path",
    )
    return p


def main():
    args = build_parser().parse_args()

    with open(args.registry) as f:
        registry = json.load(f)

    # Load optional regions config
    regions_cfg = None
    if args.regions is not None:
        try:
            import yaml

            with open(args.regions) as f:
                regions_cfg = yaml.safe_load(f)
        except ImportError:
            print("Warning: pyyaml not available; skipping regions.yaml")
        except FileNotFoundError:
            print(f"Warning: regions file not found: {args.regions}")

    # Load optional summary
    summary = None
    if args.summary is not None:
        try:
            with open(args.summary) as f:
                summary = json.load(f)
        except FileNotFoundError:
            print(f"Warning: summary file not found: {args.summary}")

    strategy = build_strategy(registry, regions_cfg=regions_cfg, summary=summary)
    constraint_map = build_cr_sr_constraint_map(strategy, summary=summary)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(out_path, strategy)
    print(f"Strategy written to {out_path}")

    cr_sr_path = out_path.parent / "cr_sr_constraint_map.json"
    write_json(cr_sr_path, constraint_map)
    print(f"CR-SR constraint map written to {cr_sr_path}")


if __name__ == "__main__":
    main()
