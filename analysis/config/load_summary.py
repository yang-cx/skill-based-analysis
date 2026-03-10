import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from analysis.common import ensure_dir, run_metadata, write_json
from analysis.config.summary_schema import parse_summary


ID_FIELDS = (
    "region_id",
    "signal_region_id",
    "control_region_id",
    "signature_id",
    "fit_id",
)


def _norm_string(value: str) -> str:
    return " ".join(value.strip().split())



def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return _norm_string(value)
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            nk = _norm_string(k) if isinstance(k, str) else k
            nv = _normalize(v)
            if nk in ID_FIELDS and isinstance(nv, str):
                nv = nv.strip()
            out[nk] = nv
        return out
    return value



def _extract_id(entry: Dict[str, Any], candidates: Sequence[str]) -> str:
    for key in candidates:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""



def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        out = []
        for v in value:
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
        return out
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []



def _check_unique(ids: Iterable[str], label: str) -> List[str]:
    seen = set()
    dup = set()
    for rid in ids:
        if rid in seen:
            dup.add(rid)
        seen.add(rid)
    if dup:
        return ["duplicate {} IDs: {}".format(label, ", ".join(sorted(dup)))]
    return []



def validate_crossrefs(summary: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any]]:
    errors: List[str] = []

    sr = summary.get("signal_regions", [])
    cr = summary.get("control_regions", [])
    fits = summary.get("fit_setup", [])
    sigs = summary.get("signal_signatures", [])
    results = summary.get("results", [])

    sr_ids = [_extract_id(x, ("region_id", "signal_region_id")) for x in sr if isinstance(x, dict)]
    cr_ids = [_extract_id(x, ("region_id", "control_region_id")) for x in cr if isinstance(x, dict)]
    fit_ids = [_extract_id(x, ("fit_id",)) for x in fits if isinstance(x, dict)]
    signature_ids = [_extract_id(x, ("signature_id",)) for x in sigs if isinstance(x, dict)]

    sr_ids = [x for x in sr_ids if x]
    cr_ids = [x for x in cr_ids if x]
    fit_ids = [x for x in fit_ids if x]
    signature_ids = [x for x in signature_ids if x]

    errors.extend(_check_unique(sr_ids, "signal_region"))
    errors.extend(_check_unique(cr_ids, "control_region"))

    all_regions = set(sr_ids) | set(cr_ids)
    for fit in fits:
        if not isinstance(fit, dict):
            continue
        fid = _extract_id(fit, ("fit_id",)) or "<unknown_fit>"
        for rid in _as_list(fit.get("regions_included")):
            if rid not in all_regions:
                errors.append(
                    "fit_setup {} references unknown region {}".format(fid, rid)
                )

    known_sigs = set(signature_ids)
    for reg in sr:
        if not isinstance(reg, dict):
            continue
        rid = _extract_id(reg, ("region_id", "signal_region_id")) or "<unknown_sr>"
        for sid in _as_list(reg.get("associated_signature_ids")):
            if sid not in known_sigs:
                errors.append(
                    "signal_region {} references unknown signature_id {}".format(rid, sid)
                )

    known_fits = set(fit_ids)
    for idx, res in enumerate(results):
        if not isinstance(res, dict):
            continue
        afid = _extract_id(res, ("associated_fit_id",))
        if afid and afid not in known_fits:
            errors.append(
                "results[{}] references unknown associated_fit_id {}".format(idx, afid)
            )

    fit_observables = sorted(
        {
            _extract_id(reg, ("fit_observable", "observable"))
            for reg in sr
            if isinstance(reg, dict)
        }
        - {""}
    )
    pois = sorted(
        {
            poi
            for fit in fits
            if isinstance(fit, dict)
            for poi in _as_list(fit.get("parameters_of_interest"))
        }
    )

    inventory = {
        "n_signal_regions": len(sr_ids),
        "n_control_regions": len(cr_ids),
        "fit_ids": sorted(set(fit_ids)),
        "fit_observables": fit_observables,
        "pois": pois,
    }
    return errors, inventory



def load_and_validate(summary_path: Path) -> Dict[str, Any]:
    with summary_path.open() as f:
        payload = json.load(f)

    # Structural validation via Pydantic.
    parse_summary(payload)

    normalized = _normalize(payload)
    errors, inventory = validate_crossrefs(normalized)
    if errors:
        raise ValueError("Summary cross-reference validation failed:\n- " + "\n- ".join(errors))

    normalized["_inventory"] = inventory
    normalized["_meta"] = run_metadata(summary_path, Path("analysis/regions.yaml"))
    return normalized



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load and validate analysis summary JSON")
    parser.add_argument("--summary", required=True, help="Path to analysis summary JSON")
    parser.add_argument("--out", required=False, help="Output path for normalized JSON")
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    summary_path = Path(args.summary)
    normalized = load_and_validate(summary_path)

    out_path = Path(args.out) if args.out else Path("outputs/summary.normalized.json")
    ensure_dir(out_path.parent)
    write_json(out_path, normalized)

    inv = normalized["_inventory"]
    print(
        "summary validated: SR={} CR={} fits={} observables={} pois={}".format(
            inv["n_signal_regions"],
            inv["n_control_regions"],
            len(inv["fit_ids"]),
            len(inv["fit_observables"]),
            len(inv["pois"]),
        )
    )


if __name__ == "__main__":
    main()
