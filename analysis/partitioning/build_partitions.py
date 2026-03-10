import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

from analysis.common import ensure_dir, run_metadata, write_json


REGION_KIND_TO_TYPE = {
    "signal": "SR",
    "control": "CR",
    "validation": "VR",
}


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open() as handle:
        payload = yaml.safe_load(handle)
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("YAML at {} must be a mapping".format(path))
    return payload


def _default_categories() -> List[Dict[str, Any]]:
    return [
        {
            "category_id": "inclusive",
            "label": "Inclusive category",
            "assignment_basis": "topology_selection",
            "assignment_definition": "True",
            "mutually_exclusive": True,
            "coverage": "full",
            "is_default": True,
            "priority": 0,
            "notes": "Auto-generated inclusive fallback category.",
        }
    ]


def _normalize_categories(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = payload.get("categories", [])
    if not isinstance(raw, list) or not raw:
        return _default_categories()

    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError("category entry {} must be a mapping".format(idx))
        cid = str(row.get("category_id", "")).strip()
        if not cid:
            raise ValueError("category entry {} missing category_id".format(idx))

        out.append(
            {
                "category_id": cid,
                "label": str(row.get("label", cid)),
                "assignment_basis": str(row.get("assignment_basis", "topology_selection")),
                "assignment_definition": str(row.get("assignment_definition", "True")),
                "mutually_exclusive": bool(row.get("mutually_exclusive", True)),
                "coverage": str(row.get("coverage", "full")),
                "is_default": bool(row.get("is_default", False)),
                "priority": int(row.get("priority", idx)),
                "notes": str(row.get("notes", "")),
            }
        )
    return out


def _fit_domain_by_region(regions_cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for fit in regions_cfg.get("fits", []):
        if not isinstance(fit, dict):
            continue
        observable = str(fit.get("observable", ""))
        binning = fit.get("binning", {}) if isinstance(fit.get("binning"), dict) else {}
        fit_range = None
        if isinstance(binning.get("range"), list) and len(binning["range"]) == 2:
            fit_range = [float(binning["range"][0]), float(binning["range"][1])]
        for region_id in fit.get("regions_included", []):
            rid = str(region_id)
            out[rid] = {
                "fit_id": str(fit.get("fit_id", "FIT_MAIN")),
                "observable": observable,
                "range": fit_range,
            }
    return out


def _normalize_regions(regions_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    regions = regions_cfg.get("regions", [])
    if not isinstance(regions, list):
        raise ValueError("regions YAML must contain a list under 'regions'")
    return [r for r in regions if isinstance(r, dict)]


def _build_partition_rows(
    categories: List[Dict[str, Any]],
    regions: List[Dict[str, Any]],
    fit_domain_map: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    region_rows: List[Dict[str, Any]] = []
    partition_rows: List[Dict[str, Any]] = []

    for region in regions:
        region_id = str(region.get("region_id", "")).strip()
        if not region_id:
            raise ValueError("region missing region_id")
        kind = str(region.get("kind", "other")).strip().lower()
        region_type = REGION_KIND_TO_TYPE.get(kind, "OTHER")

        fit_info = fit_domain_map.get(region_id)
        if fit_info:
            selection_basis = str(region.get("selection_basis", "fit_domain"))
            selection_definition = "fit_domain:{obs}:[{lo},{hi}]".format(
                obs=fit_info.get("observable", "observable"),
                lo=fit_info.get("range", [None, None])[0],
                hi=fit_info.get("range", [None, None])[1],
            )
        else:
            selection_basis = str(region.get("selection_basis", "topology_selection"))
            selection_definition = str(region.get("selection", "not_specified"))

        blinding_policy = {
            "data_shown_default": False if region_type == "SR" else True,
            "mode": "blinded_default" if region_type == "SR" else "shown_default",
        }

        reg_row = {
            "region_id": region_id,
            "region_type": region_type,
            "kind": kind,
            "label": str(region.get("label", region_id)),
            "selection_basis": selection_basis,
            "selection_definition": selection_definition,
            "fit_domain": fit_info or None,
            "blinding_policy": blinding_policy,
        }
        region_rows.append(reg_row)

        for category in categories:
            partition_rows.append(
                {
                    "category_id": category["category_id"],
                    "region_id": region_id,
                    "region_type": region_type,
                    "selection_basis": selection_basis,
                    "selection_definition": selection_definition,
                    "blinding_policy": blinding_policy,
                    "notes": str(region.get("notes", "")),
                }
            )

    return region_rows, partition_rows


def _validation_checks(
    categories: List[Dict[str, Any]],
    regions: List[Dict[str, Any]],
    partition_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    category_ids = [c["category_id"] for c in categories]
    default_count = sum(1 for c in categories if c.get("is_default"))
    all_mutually_exclusive = all(bool(c.get("mutually_exclusive", True)) for c in categories)
    has_full_coverage = any(str(c.get("coverage", "")).lower() == "full" for c in categories)

    pair_keys = [(p["category_id"], p["region_id"]) for p in partition_rows]
    unique_pairs = set(pair_keys)
    duplicates = len(pair_keys) - len(unique_pairs)

    region_ids = [str(r.get("region_id", "")).strip() for r in regions if str(r.get("region_id", "")).strip()]
    manifest_region_ids = sorted({p["region_id"] for p in partition_rows})
    region_consistent = sorted(set(region_ids)) == manifest_region_ids

    fit_domain_rows = [p for p in partition_rows if p.get("selection_basis") == "fit_domain"]
    diphoton_ok = all("fit_domain:" in str(p.get("selection_definition", "")) for p in fit_domain_rows)

    sr_rows = [p for p in partition_rows if p.get("region_type") == "SR"]
    blinding_ready = all(not p.get("blinding_policy", {}).get("data_shown_default", True) for p in sr_rows)

    checks = {
        "category_exclusivity": {
            "status": "pass" if all_mutually_exclusive else "fail",
            "detail": "Declarative check from category configuration.",
        },
        "category_coverage": {
            "status": "pass" if has_full_coverage else "warn",
            "detail": "At least one category declares coverage=full." if has_full_coverage else "No category declares full coverage.",
        },
        "partition_uniqueness": {
            "status": "pass" if duplicates == 0 else "fail",
            "duplicate_count": int(duplicates),
        },
        "region_enumeration_consistency": {
            "status": "pass" if region_consistent else "fail",
            "n_regions_declared": len(set(region_ids)),
            "n_regions_in_manifest": len(manifest_region_ids),
        },
        "diphoton_compatibility": {
            "status": "pass" if diphoton_ok else "fail",
            "n_fit_domain_partitions": len(fit_domain_rows),
        },
        "blinding_readiness": {
            "status": "pass" if blinding_ready else "fail",
            "n_signal_partitions": len(sr_rows),
        },
        "meta": {
            "n_categories": len(category_ids),
            "n_regions": len(set(region_ids)),
            "n_partitions": len(partition_rows),
            "n_default_categories": int(default_count),
        },
    }

    hard_fail_keys = [
        "category_exclusivity",
        "partition_uniqueness",
        "region_enumeration_consistency",
        "diphoton_compatibility",
        "blinding_readiness",
    ]
    has_fail = any(checks[k]["status"] == "fail" for k in hard_fail_keys)
    checks["summary"] = {
        "status": "fail" if has_fail else "pass",
        "hard_fail_checks": hard_fail_keys,
    }
    return checks


def build_partitions(
    categories_path: Path,
    regions_path: Path,
    out_spec: Path,
    out_manifest: Path,
    out_checks: Path,
) -> Dict[str, Any]:
    categories_cfg = _load_yaml(categories_path)
    regions_cfg = _load_yaml(regions_path)

    categories = _normalize_categories(categories_cfg)
    regions = _normalize_regions(regions_cfg)
    fit_domain_map = _fit_domain_by_region(regions_cfg)

    region_rows, partition_rows = _build_partition_rows(categories, regions, fit_domain_map)
    checks = _validation_checks(categories, regions, partition_rows)

    spec_payload = {
        "categories": categories,
        "regions": region_rows,
        "partitions": partition_rows,
        "meta": run_metadata(Path("analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json"), regions_path),
        "inputs": {
            "categories": str(categories_path),
            "regions": str(regions_path),
        },
    }

    manifest_payload = {
        "partitions": [
            {
                "category_id": row["category_id"],
                "region_id": row["region_id"],
                "region_type": row["region_type"],
            }
            for row in partition_rows
        ],
        "n_partitions": len(partition_rows),
    }

    checks_payload = {
        **checks,
        "inputs": {
            "categories": str(categories_path),
            "regions": str(regions_path),
        },
    }

    ensure_dir(out_spec.parent)
    ensure_dir(out_manifest.parent)
    ensure_dir(out_checks.parent)
    write_json(out_spec, spec_payload)
    write_json(out_manifest, manifest_payload)
    write_json(out_checks, checks_payload)
    return checks_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build and validate category/region partitions")
    parser.add_argument("--categories", required=True)
    parser.add_argument("--regions", required=True)
    parser.add_argument("--out-spec", required=True)
    parser.add_argument("--out-manifest", required=True)
    parser.add_argument("--out-checks", required=True)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    checks = build_partitions(
        categories_path=Path(args.categories),
        regions_path=Path(args.regions),
        out_spec=Path(args.out_spec),
        out_manifest=Path(args.out_manifest),
        out_checks=Path(args.out_checks),
    )

    print(
        "partition checks status={} categories={} regions={} partitions={}".format(
            checks.get("summary", {}).get("status", "unknown"),
            checks.get("meta", {}).get("n_categories", 0),
            checks.get("meta", {}).get("n_regions", 0),
            checks.get("meta", {}).get("n_partitions", 0),
        )
    )


if __name__ == "__main__":
    main()

