from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from analysis.common import read_json, write_json


def _tolerance_limit(reference: float, abs_tol: float, rel_tol: float) -> float:
    return max(float(abs_tol), float(rel_tol) * max(abs(float(reference)), 1.0))


def _collect_yields(outputs: Path) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for path in sorted((outputs / "yields").glob("*.json")):
        payload = read_json(path)
        sample_id = str(payload.get("sample_id", path.stem))
        for region_id, stats in payload.get("regions", {}).items():
            for metric in ["n_raw", "yield", "sumw2"]:
                value = stats.get(metric)
                if isinstance(value, (int, float)):
                    key = "yield:{}:{}:{}".format(sample_id, region_id, metric)
                    out[key] = float(value)
    return out


def _collect_hist_integrals(outputs: Path) -> Dict[str, float]:
    out: Dict[str, float] = {}
    hists_root = outputs / "hists"
    if not hists_root.exists():
        return out

    for npz_path in sorted(hists_root.rglob("*.npz")):
        try:
            payload = np.load(npz_path, allow_pickle=True)
            counts = np.asarray(payload["counts"], dtype=float)
            rel = npz_path.relative_to(hists_root).as_posix()
            out["hist:{}:integral".format(rel)] = float(np.sum(counts))
        except Exception:
            continue
    return out


def _compare_maps(
    baseline: Dict[str, float],
    candidate: Dict[str, float],
    abs_tol: float,
    rel_tol: float,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    failures: List[Dict[str, Any]] = []
    missing_in_candidate = sorted(set(baseline.keys()) - set(candidate.keys()))
    extra_in_candidate = sorted(set(candidate.keys()) - set(baseline.keys()))

    for key in sorted(set(baseline.keys()) & set(candidate.keys())):
        base = float(baseline[key])
        cand = float(candidate[key])
        diff = abs(cand - base)
        limit = _tolerance_limit(base, abs_tol=abs_tol, rel_tol=rel_tol)
        if diff > limit:
            failures.append(
                {
                    "key": key,
                    "baseline": base,
                    "candidate": cand,
                    "abs_diff": diff,
                    "allowed_diff": limit,
                }
            )

    return failures, missing_in_candidate, extra_in_candidate


def run_parity_check(
    *,
    baseline_outputs: Path,
    candidate_outputs: Path,
    abs_tol: float,
    rel_tol: float,
    out_path: Path | None = None,
) -> Dict[str, Any]:
    baseline_map: Dict[str, float] = {}
    baseline_map.update(_collect_yields(baseline_outputs))
    baseline_map.update(_collect_hist_integrals(baseline_outputs))

    candidate_map: Dict[str, float] = {}
    candidate_map.update(_collect_yields(candidate_outputs))
    candidate_map.update(_collect_hist_integrals(candidate_outputs))

    failures, missing_in_candidate, extra_in_candidate = _compare_maps(
        baseline=baseline_map,
        candidate=candidate_map,
        abs_tol=abs_tol,
        rel_tol=rel_tol,
    )

    baseline_empty = len(baseline_map) == 0
    status = (
        "pass"
        if (
            not baseline_empty
            and not failures
            and not missing_in_candidate
            and not extra_in_candidate
        )
        else "fail"
    )
    payload: Dict[str, Any] = {
        "status": status,
        "baseline_outputs": str(baseline_outputs.resolve()),
        "candidate_outputs": str(candidate_outputs.resolve()),
        "tolerances": {
            "absolute": float(abs_tol),
            "relative": float(rel_tol),
        },
        "counts": {
            "baseline_metrics": len(baseline_map),
            "candidate_metrics": len(candidate_map),
            "failed_metrics": len(failures),
            "missing_in_candidate": len(missing_in_candidate),
            "extra_in_candidate": len(extra_in_candidate),
        },
        "baseline_empty": baseline_empty,
        "failed_metrics": failures[:500],
        "missing_in_candidate": missing_in_candidate[:500],
        "extra_in_candidate": extra_in_candidate[:500],
    }

    if out_path is not None:
        write_json(out_path, payload)
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two pipeline output directories for yield/hist parity."
    )
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--abs-tol", type=float, default=1e-6)
    parser.add_argument("--rel-tol", type=float, default=1e-3)
    parser.add_argument("--out", default=None)
    parser.add_argument(
        "--fail-on-mismatch",
        action="store_true",
        help="Exit non-zero when parity does not pass.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    report = run_parity_check(
        baseline_outputs=Path(args.baseline),
        candidate_outputs=Path(args.candidate),
        abs_tol=float(args.abs_tol),
        rel_tol=float(args.rel_tol),
        out_path=Path(args.out) if args.out else None,
    )
    print("parity status={}".format(report.get("status", "unknown")))
    print("failed_metrics={}".format(report.get("counts", {}).get("failed_metrics", 0)))
    print(
        "missing_in_candidate={}".format(
            report.get("counts", {}).get("missing_in_candidate", 0)
        )
    )
    print(
        "extra_in_candidate={}".format(
            report.get("counts", {}).get("extra_in_candidate", 0)
        )
    )

    if bool(args.fail_on_mismatch) and report.get("status") != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
