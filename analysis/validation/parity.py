# FILE: analysis/validation/parity.py
"""Parity check: compare yields and histograms between two output directories."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from analysis.common import ensure_dir, write_json


def _load_yield_files(outputs_dir: str) -> Dict[str, Dict]:
    """Load all yield JSON files from an outputs directory."""
    yields_dir = Path(outputs_dir) / "yields"
    result = {}
    if not yields_dir.exists():
        return result
    for json_path in sorted(yields_dir.glob("*.json")):
        try:
            with open(json_path) as f:
                data = json.load(f)
            sample_id = data.get("sample_id", json_path.stem)
            result[sample_id] = data
        except Exception as e:
            print(f"Warning: could not load {json_path}: {e}")
    return result


def _load_histogram_files(outputs_dir: str) -> Dict[str, Dict]:
    """Load all histogram .npz files from outputs/hists/."""
    hists_dir = Path(outputs_dir) / "hists"
    result = {}
    if not hists_dir.exists():
        return result
    for npz_path in sorted(hists_dir.rglob("*.npz")):
        try:
            rel = npz_path.relative_to(hists_dir)
            key = str(rel)
            d = np.load(str(npz_path), allow_pickle=True)
            result[key] = {
                "edges": np.asarray(d["edges"]),
                "counts": np.asarray(d["counts"]),
                "sumw2": np.asarray(d["sumw2"]),
            }
        except Exception as e:
            print(f"Warning: could not load {npz_path}: {e}")
    return result


def _compare_scalar(
    key: str,
    baseline: Any,
    candidate: Any,
    abs_tol: float,
    rel_tol: float,
) -> Optional[Dict]:
    """Compare two scalar values. Returns failure detail or None if OK."""
    if baseline is None and candidate is None:
        return None
    if baseline is None or candidate is None:
        return {
            "key": key,
            "reason": "one_is_none",
            "baseline": baseline,
            "candidate": candidate,
        }
    try:
        b = float(baseline)
        c = float(candidate)
        if b == 0 and c == 0:
            return None
        if abs(b - c) <= abs_tol:
            return None
        rel_diff = abs(b - c) / (abs(b) + 1e-30)
        if rel_diff <= rel_tol:
            return None
        return {
            "key": key,
            "reason": "value_mismatch",
            "baseline": b,
            "candidate": c,
            "abs_diff": abs(b - c),
            "rel_diff": rel_diff,
        }
    except (TypeError, ValueError):
        if baseline == candidate:
            return None
        return {
            "key": key,
            "reason": "non_numeric_mismatch",
            "baseline": str(baseline),
            "candidate": str(candidate),
        }


def compare_yields(
    baseline_yields: Dict,
    candidate_yields: Dict,
    abs_tol: float,
    rel_tol: float,
) -> Tuple[List[Dict], int, int]:
    """Compare yield dictionaries.

    Returns (failures, n_missing_in_candidate, n_extra_in_candidate).
    """
    failures = []
    n_missing = 0
    n_extra = 0

    baseline_keys = set(baseline_yields.keys())
    candidate_keys = set(candidate_yields.keys())

    missing = baseline_keys - candidate_keys
    extra = candidate_keys - baseline_keys
    n_missing = len(missing)
    n_extra = len(extra)

    for sid in missing:
        failures.append({
            "type": "missing_sample",
            "sample_id": sid,
            "reason": "sample not in candidate",
        })

    # Compare common samples
    for sample_id in baseline_keys & candidate_keys:
        b_info = baseline_yields[sample_id]
        c_info = candidate_yields[sample_id]

        b_regions = b_info.get("regions", {})
        c_regions = c_info.get("regions", {})

        for region_id in set(b_regions.keys()) | set(c_regions.keys()):
            if region_id not in b_regions:
                failures.append({
                    "type": "extra_region",
                    "sample_id": sample_id,
                    "region_id": region_id,
                    "reason": "region not in baseline",
                })
                continue
            if region_id not in c_regions:
                failures.append({
                    "type": "missing_region",
                    "sample_id": sample_id,
                    "region_id": region_id,
                    "reason": "region not in candidate",
                })
                continue

            b_r = b_regions[region_id]
            c_r = c_regions[region_id]

            for metric in ("yield", "sumw2"):
                detail = _compare_scalar(
                    f"{sample_id}/{region_id}/{metric}",
                    b_r.get(metric),
                    c_r.get(metric),
                    abs_tol=abs_tol,
                    rel_tol=rel_tol,
                )
                if detail:
                    detail["type"] = "yield_mismatch"
                    detail["sample_id"] = sample_id
                    detail["region_id"] = region_id
                    detail["metric"] = metric
                    failures.append(detail)

    return failures, n_missing, n_extra


def compare_histograms(
    baseline_hists: Dict,
    candidate_hists: Dict,
    abs_tol: float,
    rel_tol: float,
) -> Tuple[List[Dict], int, int]:
    """Compare histogram dictionaries.

    Returns (failures, n_missing_in_candidate, n_extra_in_candidate).
    """
    failures = []

    baseline_keys = set(baseline_hists.keys())
    candidate_keys = set(candidate_hists.keys())

    missing = baseline_keys - candidate_keys
    extra = candidate_keys - baseline_keys
    n_missing = len(missing)
    n_extra = len(extra)

    for key in missing:
        failures.append({
            "type": "missing_histogram",
            "key": key,
            "reason": "histogram not in candidate",
        })

    for key in baseline_keys & candidate_keys:
        b_hist = baseline_hists[key]
        c_hist = candidate_hists[key]

        for field in ("edges", "counts", "sumw2"):
            b_arr = b_hist.get(field)
            c_arr = c_hist.get(field)

            if b_arr is None and c_arr is None:
                continue
            if b_arr is None or c_arr is None:
                failures.append({
                    "type": "missing_histogram_field",
                    "key": key,
                    "field": field,
                    "reason": "one array is None",
                })
                continue

            if b_arr.shape != c_arr.shape:
                failures.append({
                    "type": "histogram_shape_mismatch",
                    "key": key,
                    "field": field,
                    "baseline_shape": list(b_arr.shape),
                    "candidate_shape": list(c_arr.shape),
                })
                continue

            # Element-wise comparison
            abs_diff = np.abs(b_arr - c_arr)
            rel_diff = abs_diff / (np.abs(b_arr) + 1e-30)
            fail_mask = (abs_diff > abs_tol) & (rel_diff > rel_tol)

            if np.any(fail_mask):
                n_fail = int(np.sum(fail_mask))
                max_diff = float(np.max(abs_diff[fail_mask]))
                failures.append({
                    "type": "histogram_value_mismatch",
                    "key": key,
                    "field": field,
                    "n_failing_bins": n_fail,
                    "max_abs_diff": max_diff,
                })

    return failures, n_missing, n_extra


def run_parity_check(
    baseline_outputs: str,
    candidate_outputs: str,
    abs_tol: float = 1e-9,
    rel_tol: float = 1e-6,
) -> Dict:
    """Compare yields JSON and histogram npz between two output directories.

    Returns dict with:
    - status: "pass" or "fail"
    - counts.failed_metrics: int
    - counts.missing_in_candidate: int
    - counts.extra_in_candidate: int
    - details: list of failure dicts
    """
    print(f"Comparing outputs:")
    print(f"  Baseline:  {baseline_outputs}")
    print(f"  Candidate: {candidate_outputs}")

    # Load data
    baseline_yields = _load_yield_files(baseline_outputs)
    candidate_yields = _load_yield_files(candidate_outputs)
    baseline_hists = _load_histogram_files(baseline_outputs)
    candidate_hists = _load_histogram_files(candidate_outputs)

    print(f"  Baseline:  {len(baseline_yields)} yield files, {len(baseline_hists)} histograms")
    print(f"  Candidate: {len(candidate_yields)} yield files, {len(candidate_hists)} histograms")

    all_failures = []
    total_missing = 0
    total_extra = 0

    # Compare yields
    yield_failures, y_missing, y_extra = compare_yields(
        baseline_yields, candidate_yields, abs_tol, rel_tol
    )
    all_failures.extend(yield_failures)
    total_missing += y_missing
    total_extra += y_extra

    # Compare histograms
    hist_failures, h_missing, h_extra = compare_histograms(
        baseline_hists, candidate_hists, abs_tol, rel_tol
    )
    all_failures.extend(hist_failures)
    total_missing += h_missing
    total_extra += h_extra

    n_failed = len(all_failures)
    status = "pass" if n_failed == 0 else "fail"

    result = {
        "status": status,
        "counts": {
            "failed_metrics": n_failed,
            "missing_in_candidate": total_missing,
            "extra_in_candidate": total_extra,
        },
        "details": all_failures,
        "configuration": {
            "abs_tol": abs_tol,
            "rel_tol": rel_tol,
        },
    }

    print(f"Parity check: {status.upper()}")
    print(f"  Failed metrics: {n_failed}")
    print(f"  Missing in candidate: {total_missing}")
    print(f"  Extra in candidate: {total_extra}")

    return result
