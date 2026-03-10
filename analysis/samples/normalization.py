# FILE: analysis/samples/normalization.py
"""Compute per-sample normalization table from registry."""

import argparse
import json
from pathlib import Path
from typing import Dict, Optional

from analysis.common import ensure_dir, write_json

DEFAULT_LUMI_FB = 36.1


def _compute_norm_factor(
    xsec_pb: Optional[float],
    k_factor: Optional[float],
    filter_eff: Optional[float],
    sumw: Optional[float],
    lumi_fb: float = DEFAULT_LUMI_FB,
) -> Optional[float]:
    """Compute normalization: (xsec * kfac * filteff * lumi * 1000) / sumw."""
    if any(v is None for v in [xsec_pb, k_factor, filter_eff, sumw]):
        return None
    if sumw == 0.0:
        return None
    return (xsec_pb * k_factor * filter_eff * lumi_fb * 1000.0) / sumw


def build_norm_table(registry: Dict, lumi_fb: float = DEFAULT_LUMI_FB) -> Dict:
    """Build normalization table from registry."""
    samples = registry.get("samples", registry)
    norm_table = {}
    audit_entries = []

    for sample_id, info in samples.items():
        sample_type = info.get("type", "other")

        if sample_type == "data":
            norm_table[sample_id] = {
                "sample_id": sample_id,
                "type": sample_type,
                "norm_factor": 1.0,
                "xsec_pb": None,
                "k_factor": None,
                "filter_eff": None,
                "sumw": None,
                "lumi_fb": None,
                "note": "data: weight=1",
            }
            audit_entries.append(
                {
                    "sample_id": sample_id,
                    "type": sample_type,
                    "norm_factor": 1.0,
                    "status": "ok",
                }
            )
            continue

        xsec_pb = info.get("xsec_pb")
        k_factor = info.get("k_factor")
        filter_eff = info.get("filter_eff")
        sumw = info.get("sumw")

        # Use stored norm_factor if available, else recompute
        stored_norm = info.get("norm_factor")
        if stored_norm is not None:
            norm_factor = stored_norm
            status = "ok"
        else:
            norm_factor = _compute_norm_factor(
                xsec_pb, k_factor, filter_eff, sumw, lumi_fb=lumi_fb
            )
            status = "ok" if norm_factor is not None else "missing_metadata"

        norm_table[sample_id] = {
            "sample_id": sample_id,
            "type": sample_type,
            "norm_factor": norm_factor,
            "xsec_pb": xsec_pb,
            "k_factor": k_factor,
            "filter_eff": filter_eff,
            "sumw": sumw,
            "lumi_fb": lumi_fb,
            "note": f"norm=(xsec*kfac*filteff*{lumi_fb}*1000)/sumw",
        }

        audit_entries.append(
            {
                "sample_id": sample_id,
                "type": sample_type,
                "xsec_pb": xsec_pb,
                "k_factor": k_factor,
                "filter_eff": filter_eff,
                "sumw": sumw,
                "norm_factor": norm_factor,
                "status": status,
            }
        )

    n_ok = sum(1 for a in audit_entries if a["status"] == "ok")
    n_missing = sum(1 for a in audit_entries if a["status"] == "missing_metadata")

    audit = {
        "summary": {
            "n_samples": len(audit_entries),
            "n_ok": n_ok,
            "n_missing_metadata": n_missing,
            "lumi_fb": lumi_fb,
        },
        "entries": audit_entries,
    }

    return norm_table, audit


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Compute per-sample normalization table from registry."
    )
    p.add_argument("--registry", required=True, help="Path to samples.registry.json")
    p.add_argument("--out-dir", required=True, help="Output directory")
    p.add_argument(
        "--lumi-fb",
        type=float,
        default=DEFAULT_LUMI_FB,
        help=f"Luminosity in fb^-1 (default: {DEFAULT_LUMI_FB})",
    )
    return p


def main():
    args = build_parser().parse_args()

    with open(args.registry) as f:
        registry = json.load(f)

    norm_table, audit = build_norm_table(registry, lumi_fb=args.lumi_fb)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    norm_path = out_dir / "norm_table.json"
    audit_path = out_dir / "norm_audit.json"

    write_json(norm_path, norm_table)
    write_json(audit_path, audit)

    print(f"Normalization table: {norm_path}")
    print(f"Normalization audit: {audit_path}")
    print(f"  {audit['summary']['n_ok']} samples OK, "
          f"{audit['summary']['n_missing_metadata']} missing metadata")


if __name__ == "__main__":
    main()
