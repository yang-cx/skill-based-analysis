# FILE: analysis/partitioning/build_partitions.py
"""Build (category, region) partition pairs for the analysis."""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from analysis.common import ensure_dir, write_json


def _load_yaml(path: str) -> Dict:
    """Load a YAML file, falling back to JSON if yaml unavailable."""
    path = Path(path)
    if not path.exists():
        return {}
    try:
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f)
        return data or {}
    except ImportError:
        # Fall back to trying JSON
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            return {}


def build_partitions(
    categories_path: str,
    regions_path: str,
    out_spec: str,
    out_manifest: str,
    out_checks: str,
) -> Dict:
    """Build partition pairs from categories and regions config.

    Returns checks dict with summary.status = 'pass' or 'fail'.
    """
    categories_cfg_raw = _load_yaml(categories_path)
    regions_cfg_raw = _load_yaml(regions_path)

    # Unwrap top-level "categories" or "regions" wrapper keys
    if isinstance(categories_cfg_raw, dict) and list(categories_cfg_raw.keys()) == ["categories"]:
        categories_cfg = categories_cfg_raw["categories"]
    else:
        categories_cfg = categories_cfg_raw

    if isinstance(regions_cfg_raw, dict) and "regions" in regions_cfg_raw:
        regions_cfg = regions_cfg_raw["regions"]
    else:
        regions_cfg = regions_cfg_raw

    # Extract all region IDs from regions config
    all_region_ids = set()
    if isinstance(regions_cfg, dict):
        all_region_ids = set(regions_cfg.keys())
    elif isinstance(regions_cfg, list):
        for item in regions_cfg:
            if isinstance(item, dict):
                rid = item.get("region_id", item.get("id", None))
                if rid:
                    all_region_ids.add(rid)
            elif isinstance(item, str):
                all_region_ids.add(item)

    # Extract categories with their associated regions
    categories = {}
    if isinstance(categories_cfg, dict):
        for cat_id, cat_info in categories_cfg.items():
            if isinstance(cat_info, dict):
                cat_regions = cat_info.get("regions", [])
                categories[cat_id] = {
                    "regions": cat_regions,
                    "description": cat_info.get("description", ""),
                }
            elif isinstance(cat_info, list):
                categories[cat_id] = {"regions": cat_info, "description": ""}
    elif isinstance(categories_cfg, list):
        for item in categories_cfg:
            if isinstance(item, dict):
                cat_id = item.get("id", item.get("name", str(len(categories))))
                cat_regions = item.get("regions", [])
                categories[cat_id] = {
                    "regions": cat_regions,
                    "description": item.get("description", ""),
                }

    # If no categories config, create a single default category with all regions
    if not categories and all_region_ids:
        categories["default"] = {
            "regions": sorted(all_region_ids),
            "description": "Default category containing all regions",
        }

    # Build Cartesian product of (category, region) pairs
    partitions = []
    seen_pairs = set()
    duplicate_pairs = []

    for cat_id, cat_info in categories.items():
        cat_regions = cat_info.get("regions", [])
        for region_id in cat_regions:
            pair = (cat_id, region_id)
            if pair in seen_pairs:
                duplicate_pairs.append({"category": cat_id, "region": region_id})
            else:
                seen_pairs.add(pair)
                partitions.append(
                    {
                        "category": cat_id,
                        "region": region_id,
                        "partition_id": f"{cat_id}__{region_id}",
                    }
                )

    # Completeness check: every region in regions_cfg should appear in at least one category
    regions_in_categories = set()
    for cat_info in categories.values():
        regions_in_categories.update(cat_info.get("regions", []))

    uncovered_regions = all_region_ids - regions_in_categories
    extra_regions = regions_in_categories - all_region_ids  # in categories but not regions.yaml

    # Build checks
    checks_passed = True
    check_details = []

    if duplicate_pairs:
        checks_passed = False
        check_details.append(
            {
                "check": "exclusivity",
                "status": "fail",
                "message": f"Found {len(duplicate_pairs)} duplicate (category, region) pairs",
                "duplicates": duplicate_pairs,
            }
        )
    else:
        check_details.append(
            {"check": "exclusivity", "status": "pass", "message": "No duplicate pairs"}
        )

    if uncovered_regions:
        # Not a hard failure if regions.yaml is empty/missing
        if all_region_ids:
            checks_passed = False
            check_details.append(
                {
                    "check": "completeness",
                    "status": "fail",
                    "message": f"{len(uncovered_regions)} regions not covered by any category",
                    "uncovered": sorted(uncovered_regions),
                }
            )
        else:
            check_details.append(
                {
                    "check": "completeness",
                    "status": "pass",
                    "message": "No regions.yaml to check against",
                }
            )
    else:
        check_details.append(
            {
                "check": "completeness",
                "status": "pass",
                "message": f"All {len(all_region_ids)} regions covered",
            }
        )

    if extra_regions:
        check_details.append(
            {
                "check": "extra_regions",
                "status": "warn",
                "message": f"{len(extra_regions)} regions in categories not in regions.yaml",
                "extra": sorted(extra_regions),
            }
        )

    checks = {
        "summary": {
            "status": "pass" if checks_passed else "fail",
            "n_partitions": len(partitions),
            "n_categories": len(categories),
            "n_regions": len(all_region_ids),
            "n_duplicate_pairs": len(duplicate_pairs),
            "n_uncovered_regions": len(uncovered_regions),
        },
        "meta": {
            "n_categories": len(categories),
            "n_regions": len(all_region_ids),
            "n_partitions": len(partitions),
        },
        "checks": check_details,
    }

    # Build partition spec
    partition_spec = {
        "categories": {
            cat_id: {
                "description": info.get("description", ""),
                "regions": info.get("regions", []),
                "n_regions": len(info.get("regions", [])),
            }
            for cat_id, info in categories.items()
        },
        "regions": sorted(all_region_ids),
        "partitions": partitions,
        "n_partitions": len(partitions),
    }

    # Build manifest
    manifest = {
        "partitions": [
            {
                "partition_id": p["partition_id"],
                "category": p["category"],
                "region": p["region"],
                "status": "active",
            }
            for p in partitions
        ],
        "total": len(partitions),
    }

    # Write outputs
    for path in [out_spec, out_manifest, out_checks]:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    write_json(out_spec, partition_spec)
    write_json(out_manifest, manifest)
    write_json(out_checks, checks)

    return checks


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Build (category, region) partition pairs."
    )
    p.add_argument("--categories", required=True, help="Path to categories.yaml")
    p.add_argument("--regions", required=True, help="Path to regions.yaml")
    p.add_argument(
        "--out-spec",
        required=True,
        help="Output partition spec JSON path",
    )
    p.add_argument(
        "--out-manifest",
        required=True,
        help="Output partitions manifest JSON path",
    )
    p.add_argument(
        "--out-checks",
        required=True,
        help="Output partition checks JSON path",
    )
    return p


def main():
    args = build_parser().parse_args()

    checks = build_partitions(
        categories_path=args.categories,
        regions_path=args.regions,
        out_spec=args.out_spec,
        out_manifest=args.out_manifest,
        out_checks=args.out_checks,
    )

    status = checks["summary"]["status"]
    n_partitions = checks["summary"]["n_partitions"]
    print(f"Partition check status: {status}")
    print(f"  {n_partitions} partitions built")
    for chk in checks["checks"]:
        icon = "OK" if chk["status"] == "pass" else ("WARN" if chk["status"] == "warn" else "FAIL")
        print(f"  [{icon}] {chk['check']}: {chk['message']}")

    if status == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
