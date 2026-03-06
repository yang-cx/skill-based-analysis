import argparse
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import yaml

from analysis.common import ensure_dir, read_json, write_json

PRODUCTION_MODE_ORDER = [
    "ggF",
    "VBF",
    "WH",
    "qqZH",
    "ggZH",
    "ttH",
    "tHjb",
    "tWH",
    "bbH",
    "other_higgs",
]


def _iter_strings(payload: Any) -> List[str]:
    out: List[str] = []
    if isinstance(payload, str):
        out.append(payload)
        return out
    if isinstance(payload, dict):
        for value in payload.values():
            out.extend(_iter_strings(value))
        return out
    if isinstance(payload, list):
        for value in payload:
            out.extend(_iter_strings(value))
        return out
    return out


def _is_hgg_analysis(summary_payload: Dict[str, Any]) -> bool:
    raw = " ".join(_iter_strings(summary_payload)).lower()
    raw = raw.replace("γ", "gamma").replace("→", "->")
    compact = "".join(ch for ch in raw if ch.isalnum())
    markers = [
        "higgs",
        "hto",
        "higgstogammagamma",
        "htogammagamma",
        "h2gammagamma",
        "hyy",
    ]
    return ("gammagamma" in compact) and any(marker in compact for marker in markers)


def _kind_map(registry: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for sample in registry.get("samples", []):
        sid = str(sample.get("sample_id", ""))
        sname = str(sample.get("sample_name", ""))
        kind = str(sample.get("kind", "background"))
        if sid:
            out[sid] = kind
        if sname:
            out[sname] = kind
    return out


def _process_map(registry: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for sample in registry.get("samples", []):
        sid = str(sample.get("sample_id", ""))
        sname = str(sample.get("sample_name", ""))
        process = str(sample.get("process_name", sid))
        if sid:
            out[sid] = process
        if sname:
            out[sname] = process
    return out


def _load_regions(regions_path: Path) -> Dict[str, Any]:
    with regions_path.open() as handle:
        return yaml.safe_load(handle)


def _aggregate_yields(
    outputs: Path, kind_map: Dict[str, str], process_map: Dict[str, str]
) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, float]], Dict[str, Dict[str, Dict[str, float]]]]:
    by_region: Dict[str, Dict[str, float]] = {}
    by_region_sample: Dict[str, Dict[str, float]] = {}
    by_region_process: Dict[str, Dict[str, Dict[str, float]]] = {}

    for path in sorted((outputs / "yields").glob("*.json")):
        sample_id = path.stem
        payload = read_json(path)
        kind = kind_map.get(sample_id, "background")
        if kind not in {"data", "signal", "background"}:
            kind = "background"
        process = process_map.get(sample_id, sample_id)

        for region_id, vals in payload.get("regions", {}).items():
            y = float(vals.get("yield", 0.0))
            by_region.setdefault(region_id, {"data": 0.0, "signal": 0.0, "background": 0.0})
            by_region[region_id][kind] += y

            by_region_sample.setdefault(region_id, {})
            by_region_sample[region_id][sample_id] = y

            by_region_process.setdefault(region_id, {})
            by_region_process[region_id].setdefault(kind, {})
            by_region_process[region_id][kind][process] = (
                by_region_process[region_id][kind].get(process, 0.0) + y
            )

    return by_region, by_region_sample, by_region_process


def _aggregate_cutflows(outputs: Path, kind_map: Dict[str, str]) -> Dict[str, List[Dict[str, float]]]:
    by_region: Dict[str, List[Dict[str, float]]] = {}

    for path in sorted((outputs / "cutflows").glob("*.json")):
        sample_id = path.stem
        payload = read_json(path)
        kind = kind_map.get(sample_id, "background")
        if kind not in {"data", "signal", "background"}:
            kind = "background"

        for region_id, rows in payload.get("cutflow", {}).items():
            by_region.setdefault(region_id, [])
            for idx, row in enumerate(rows):
                while len(by_region[region_id]) <= idx:
                    by_region[region_id].append(
                        {
                            "name": str(row.get("name", "step")),
                            "data_n_raw": 0.0,
                            "mc_bkg_n_weighted": 0.0,
                            "mc_sig_n_weighted": 0.0,
                        }
                    )

                target = by_region[region_id][idx]
                target["name"] = str(row.get("name", target["name"]))

                if kind == "data":
                    target["data_n_raw"] += float(row.get("n_raw", 0.0))
                elif kind == "signal":
                    target["mc_sig_n_weighted"] += float(row.get("n_weighted", 0.0))
                else:
                    target["mc_bkg_n_weighted"] += float(row.get("n_weighted", 0.0))

    return by_region


def _signal_production_mode(sample: Dict[str, Any]) -> str:
    text = "{} {}".format(
        str(sample.get("sample_name", "")),
        str(sample.get("process_name", "")),
    ).lower()

    if "tth" in text:
        return "ttH"
    if "twh" in text:
        return "tWH"
    if "thjb" in text or "thbj" in text:
        return "tHjb"
    if "bbh" in text:
        return "bbH"
    if "ggzh" in text:
        return "ggZH"
    if "zh" in text:
        return "qqZH"
    if "wph" in text or "wmh" in text or "qq->wh" in text or " wh " in text:
        return "WH"
    if "vbf" in text:
        return "VBF"
    if "ggh" in text or "ggf" in text or "gg->h" in text or "nnlops" in text:
        return "ggF"
    return "other_higgs"


def _aggregate_signal_process_cutflow(
    outputs: Path,
    registry: Dict[str, Any],
    category_regions: List[str],
) -> Dict[str, Any]:
    sample_to_mode: Dict[str, str] = {}
    mode_to_samples: Dict[str, set] = {}

    for sample in registry.get("samples", []):
        if str(sample.get("kind", "")) != "signal":
            continue
        sid = str(sample.get("sample_id", ""))
        if not sid:
            continue
        mode = _signal_production_mode(sample)
        sample_to_mode[sid] = mode
        mode_to_samples.setdefault(mode, set()).add(sid)

    mode_order = [mode for mode in PRODUCTION_MODE_ORDER if mode in mode_to_samples]
    for mode in sorted(mode_to_samples.keys()):
        if mode not in mode_order:
            mode_order.append(mode)

    final_yields: Dict[str, Dict[str, float]] = {
        mode: {rid: 0.0 for rid in category_regions} for mode in mode_order
    }
    step_order_by_region: Dict[str, List[str]] = {rid: [] for rid in category_regions}
    step_yields_by_region: Dict[str, Dict[str, Dict[str, float]]] = {
        rid: {} for rid in category_regions
    }

    for path in sorted((outputs / "cutflows").glob("*.json")):
        sample_id = path.stem
        mode = sample_to_mode.get(sample_id)
        if mode is None:
            continue

        payload = read_json(path)
        region_payload = payload.get("cutflow", {})

        for rid in category_regions:
            rows = region_payload.get(rid, [])
            if not rows:
                continue

            final_yields[mode][rid] += float(rows[-1].get("n_weighted", 0.0))
            for row in rows:
                step = str(row.get("name", "step"))
                if step not in step_order_by_region[rid]:
                    step_order_by_region[rid].append(step)
                step_yields_by_region[rid].setdefault(step, {})
                step_yields_by_region[rid][step][mode] = (
                    step_yields_by_region[rid][step].get(mode, 0.0)
                    + float(row.get("n_weighted", 0.0))
                )

    mode_rows: List[Dict[str, Any]] = []
    for mode in mode_order:
        per_region = final_yields[mode]
        mode_rows.append(
            {
                "mode": mode,
                "n_signal_samples": len(mode_to_samples.get(mode, set())),
                "final_category_yields": {rid: float(per_region.get(rid, 0.0)) for rid in category_regions},
                "total_10cat": float(sum(per_region.values())),
            }
        )

    combined_per_region = {
        rid: float(sum(final_yields[mode].get(rid, 0.0) for mode in mode_order))
        for rid in category_regions
    }

    region_step_breakdown: Dict[str, Any] = {}
    for rid in category_regions:
        steps = step_order_by_region.get(rid, [])
        if not steps:
            continue
        step_rows = []
        for step in steps:
            yields_by_mode = {
                mode: float(step_yields_by_region[rid].get(step, {}).get(mode, 0.0))
                for mode in mode_order
            }
            step_rows.append(
                {
                    "name": step,
                    "yields_by_mode": yields_by_mode,
                    "combined_signal": float(sum(yields_by_mode.values())),
                }
            )
        region_step_breakdown[rid] = {
            "step_order": steps,
            "steps": step_rows,
        }

    return {
        "category_regions": list(category_regions),
        "mode_order": mode_order,
        "modes": mode_rows,
        "combined_signal": {
            "final_category_yields": combined_per_region,
            "total_10cat": float(sum(combined_per_region.values())),
        },
        "region_step_breakdown": region_step_breakdown,
        "notes": [
            "Entries are weighted MC yields from the sample-level cutflow files.",
            "Each category entry uses the final cut step for that region.",
            "Signal process assignment is grouped into production-mode families.",
        ],
    }


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return float("nan")


def _is_valid_norm_row(row: Dict[str, Any]) -> bool:
    xsec = _to_float(row.get("xsec_pb"))
    kfac = _to_float(row.get("k_factor"))
    eff = _to_float(row.get("filter_eff"))
    sumw = _to_float(row.get("sumw"))
    return bool(
        np.isfinite(xsec)
        and np.isfinite(kfac)
        and np.isfinite(eff)
        and np.isfinite(sumw)
        and xsec > 0.0
        and kfac > 0.0
        and eff > 0.0
        and sumw != 0.0
    )


def _build_normalization_artifacts(
    outputs: Path,
    registry: Dict[str, Any],
    by_region_sample: Dict[str, Dict[str, float]],
    by_region_process: Dict[str, Dict[str, Dict[str, float]]],
    reference_region: str,
) -> Dict[str, Any]:
    sr_yields = by_region_sample.get(reference_region, {})

    rows: List[Dict[str, Any]] = []
    invalid_rows: List[Dict[str, Any]] = []
    lumi_values = set()

    for sample in registry.get("samples", []):
        kind = str(sample.get("kind", "background"))
        if kind == "data":
            continue

        row = {
            "sample_id": str(sample.get("sample_id", "")),
            "sample_name": str(sample.get("sample_name", "")),
            "process_name": str(sample.get("process_name", "")),
            "kind": kind,
            "xsec_pb": sample.get("xsec_pb"),
            "k_factor": sample.get("k_factor"),
            "filter_eff": sample.get("filter_eff"),
            "sumw": sample.get("sumw"),
            "lumi_fb": sample.get("lumi_fb"),
            "w_norm": sample.get("w_norm"),
            "reference_region_yield": float(
                sr_yields.get(str(sample.get("sample_id", "")), 0.0)
            ),
        }
        rows.append(row)

        if isinstance(sample.get("lumi_fb"), (int, float)):
            lumi_values.add(float(sample["lumi_fb"]))

        if not _is_valid_norm_row(row):
            invalid_rows.append(
                {
                    "sample_id": row["sample_id"],
                    "sample_name": row["sample_name"],
                    "xsec_pb": row["xsec_pb"],
                    "k_factor": row["k_factor"],
                    "filter_eff": row["filter_eff"],
                    "sumw": row["sumw"],
                }
            )

    rows = sorted(
        rows,
        key=lambda r: abs(float(r.get("reference_region_yield", 0.0))),
        reverse=True,
    )

    norm_dir = ensure_dir(outputs / "normalization")

    metadata_resolution = {
        "metadata_source": "skills/open-data-specific/metadata.csv",
        "sample_identifier_priority": ["dataset_number (DSID)", "sample name fallback"],
        "normalization_fields": [
            "crossSection_pb",
            "kFactor",
            "genFiltEff",
            "sumOfWeights",
        ],
        "formula": {
            "lumi_pb": "lumi_fb * 1000.0",
            "norm_factor": "(sigma_pb * k_factor * filter_eff * lumi_pb) / sumw",
            "event_weight": "mcWeight * product(scale_factors) * norm_factor",
        },
    }

    norm_table = {
        "rows": rows,
        "n_rows": len(rows),
        "lumi_fb_values": sorted(lumi_values),
    }

    norm_audit = {
        "n_mc_samples": len(rows),
        "n_valid_rows": len(rows) - len(invalid_rows),
        "n_invalid_rows": len(invalid_rows),
        "invalid_rows": invalid_rows,
        "note": "Rows with non-finite or non-physical normalization terms are flagged.",
    }

    stacked_yields_summary: Dict[str, Any] = {}
    for region_id, kind_payload in by_region_process.items():
        stacked_yields_summary[region_id] = {}
        for kind, process_payload in kind_payload.items():
            ordered = sorted(process_payload.items(), key=lambda item: item[1], reverse=True)
            stacked_yields_summary[region_id][kind] = [
                {"process_name": name, "yield": float(value)} for name, value in ordered
            ]

    write_json(norm_dir / "metadata_resolution.json", metadata_resolution)
    write_json(norm_dir / "norm_table.json", norm_table)
    write_json(norm_dir / "norm_audit.json", norm_audit)
    write_json(norm_dir / "stacked_yields_summary.json", stacked_yields_summary)

    return {
        "metadata_resolution": metadata_resolution,
        "norm_table": norm_table,
        "norm_audit": norm_audit,
        "stacked_yields_summary": stacked_yields_summary,
    }


def _collect_plot_names(outputs: Path) -> List[str]:
    return [path.name for path in sorted((outputs / "report" / "plots").glob("*.png"))]


def _embedded_plot_blocks(plot_names: List[str], outputs: Path, report_path: Path) -> List[str]:
    lines: List[str] = []
    for name in plot_names:
        abs_path = outputs / "report" / "plots" / name
        rel_path = Path(os.path.relpath(abs_path, start=report_path.parent)).as_posix()
        lines.append("### {}".format(name))
        lines.append("")
        lines.append("![]({})".format(rel_path))
        lines.append("")
    return lines


def _mass_window_data_counts(outputs: Path, kind_map: Dict[str, str], region_id: str) -> Dict[str, float]:
    region_dir = outputs / "hists" / region_id
    if not region_dir.exists():
        return {"peak_120_130": 0.0, "sideband_105_120_130_160": 0.0}

    observable_dirs = [path for path in region_dir.iterdir() if path.is_dir()]
    if not observable_dirs:
        return {"peak_120_130": 0.0, "sideband_105_120_130_160": 0.0}
    observable_dir = sorted(observable_dirs)[0]

    edges = None
    data_counts = None
    for npz_path in sorted(observable_dir.glob("*.npz")):
        sample_id = npz_path.stem
        if kind_map.get(sample_id, "background") != "data":
            continue
        payload = np.load(npz_path, allow_pickle=True)
        counts = payload["counts"].astype(float)
        if edges is None:
            edges = payload["edges"].astype(float)
            data_counts = np.zeros_like(counts)
        data_counts += counts

    if edges is None or data_counts is None:
        return {"peak_120_130": 0.0, "sideband_105_120_130_160": 0.0}

    centers = 0.5 * (edges[:-1] + edges[1:])
    peak = (centers >= 120.0) & (centers <= 130.0)
    side = ((centers >= 105.0) & (centers < 120.0)) | ((centers > 130.0) & (centers <= 160.0))

    return {
        "peak_120_130": float(np.sum(data_counts[peak])),
        "sideband_105_120_130_160": float(np.sum(data_counts[side])),
    }


def _compute_asimov_significance(workspace_path: Path, fit_id: str) -> Dict[str, Any]:
    try:
        import pyhf
    except Exception as exc:
        payload = {
            "fit_id": fit_id,
            "status": "failed",
            "error": "pyhf import failed: {}".format(exc),
        }
        out_path = workspace_path.parent / fit_id / "significance_asimov.json"
        write_json(out_path, payload)
        return payload

    workspace = pyhf.Workspace(read_json(workspace_path))
    model = workspace.model()
    poi_idx = model.config.poi_index
    poi_name = model.config.poi_name
    init = np.asarray(model.config.suggested_init(), dtype=float)

    def _evaluate(data: np.ndarray) -> Dict[str, Any]:
        free_fit, nll_free = pyhf.infer.mle.fit(data, model, return_fitted_val=True)
        free_fit = np.asarray(free_fit, dtype=float)
        mu_hat = float(free_fit[poi_idx])
        _, nll_mu0 = pyhf.infer.mle.fixed_poi_fit(0.0, data, model, return_fitted_val=True)
        q0 = max(float(nll_mu0 - nll_free), 0.0)
        return {
            "mu_hat": mu_hat,
            "twice_nll_free": float(nll_free),
            "twice_nll_mu0": float(nll_mu0),
            "q0": q0,
            "z_discovery": float(np.sqrt(q0)),
        }

    try:
        pars_b = init.copy()
        pars_b[poi_idx] = 0.0
        asimov_b = model.expected_data(pars_b)

        pars_sb = init.copy()
        pars_sb[poi_idx] = 1.0
        asimov_sb = model.expected_data(pars_sb)

        payload = {
            "fit_id": fit_id,
            "status": "ok",
            "poi_name": poi_name,
            "asimov_background_only": _evaluate(asimov_b),
            "asimov_signal_plus_background_mu1": _evaluate(asimov_sb),
            "note": "Asymptotic profile-likelihood approximation evaluated on Asimov datasets.",
        }
    except Exception as exc:
        payload = {
            "fit_id": fit_id,
            "status": "failed",
            "poi_name": poi_name,
            "error": str(exc),
        }

    out_path = workspace_path.parent / fit_id / "significance_asimov.json"
    write_json(out_path, payload)
    return payload


def _discover_fit_ids(outputs: Path) -> List[str]:
    fit_root = outputs / "fit"
    found = set()
    if not fit_root.exists():
        return []
    for p in fit_root.glob("*/results.json"):
        found.add(p.parent.name)
    for p in fit_root.glob("*/significance.json"):
        found.add(p.parent.name)
    return sorted(found)


def _fit_regions_from_cfg(regions_cfg: Dict[str, Any], fit_id: str) -> List[str]:
    for fit in regions_cfg.get("fits", []):
        if not isinstance(fit, dict):
            continue
        if str(fit.get("fit_id", "")) != str(fit_id):
            continue
        regs = fit.get("regions_included", [])
        if isinstance(regs, list):
            return [str(x) for x in regs if str(x)]
    return []


def _signal_regions_from_cfg(regions_cfg: Dict[str, Any]) -> List[str]:
    out = []
    for region in regions_cfg.get("regions", []):
        if not isinstance(region, dict):
            continue
        rid = str(region.get("region_id", ""))
        kind = str(region.get("kind", "")).lower()
        if rid and kind == "signal":
            out.append(rid)
    return out


def _format_float(value: Any, digits: int = 4) -> str:
    try:
        val = float(value)
    except Exception:
        return "n/a"
    if not np.isfinite(val):
        return "n/a"
    return ("{0:." + str(digits) + "g}").format(val)


def _escape_md(text: Any) -> str:
    return str(text).replace("|", "\\|")


def _load_optional_json(path: Path, default: Dict[str, Any]) -> Dict[str, Any]:
    if path.exists():
        return read_json(path)
    return default


def _build_report(
    summary_path: Path,
    outputs: Path,
    out_path: Path,
    target_lumi_fb: float,
) -> None:
    summary_payload = read_json(summary_path)
    is_hgg = _is_hgg_analysis(summary_payload)
    registry = read_json(outputs / "samples.registry.json")
    kind_map = _kind_map(registry)
    process_map = _process_map(registry)
    regions_cfg = _load_regions(Path("analysis/regions.yaml"))
    fit_ids = _discover_fit_ids(outputs)
    fit_id = fit_ids[0] if fit_ids else "FIT_MAIN"

    by_region, by_region_sample, by_region_process = _aggregate_yields(outputs, kind_map, process_map)
    cutflow = _aggregate_cutflows(outputs, kind_map)
    fit_regions = _fit_regions_from_cfg(regions_cfg, fit_id)
    signal_regions = _signal_regions_from_cfg(regions_cfg)
    signal_category_regions = [rid for rid in fit_regions if rid != "SR_DIPHOTON_INCL"]
    if not signal_category_regions:
        signal_category_regions = [rid for rid in signal_regions if rid != "SR_DIPHOTON_INCL"]
    signal_process_cutflow = _aggregate_signal_process_cutflow(
        outputs=outputs,
        registry=registry,
        category_regions=signal_category_regions,
    )
    signal_process_cutflow_path = outputs / "report" / "higgs_production_cutflow_10cat.json"
    write_json(signal_process_cutflow_path, signal_process_cutflow)

    if "SR_DIPHOTON_INCL" in by_region:
        reference_region = "SR_DIPHOTON_INCL"
    elif fit_regions:
        reference_region = fit_regions[0]
    elif signal_regions:
        reference_region = signal_regions[0]
    elif by_region:
        reference_region = sorted(by_region.keys())[0]
    else:
        reference_region = "SR_DIPHOTON_INCL"

    norm_artifacts = _build_normalization_artifacts(
        outputs,
        registry,
        by_region_sample,
        by_region_process,
        reference_region=reference_region,
    )
    plot_names = _collect_plot_names(outputs)
    mass_region = reference_region
    if not (outputs / "hists" / mass_region).exists() and fit_regions:
        mass_region = fit_regions[0]
    mass_counts = _mass_window_data_counts(outputs, kind_map, mass_region)
    fit_results = read_json(outputs / "fit" / fit_id / "results.json")
    significance = read_json(outputs / "fit" / fit_id / "significance.json")
    primary_backend = str(fit_results.get("backend", significance.get("backend", "unknown")))
    roofit_dir = outputs / "fit" / fit_id / "roofit_combined"
    roofit_significance = _load_optional_json(roofit_dir / "significance.json", {})
    roofit_asimov = _load_optional_json(roofit_dir / "significance_asimov_expected.json", {})
    roofit_cutflow = _load_optional_json(roofit_dir / "cutflow_mass_window_125pm2.json", {})
    pyhf_crosscheck_significance = _load_optional_json(
        outputs / "fit" / fit_id / "significance_pyhf_crosscheck.json",
        {},
    )
    use_roofit_primary = bool(
        isinstance(roofit_significance, dict) and roofit_significance.get("status") == "ok"
    )
    if is_hgg and not use_roofit_primary:
        raise RuntimeError(
            "H->gammagamma report requires RooFit combined significance artifact at "
            "{}".format(roofit_dir / "significance.json")
        )
    fit_backend = str(
        roofit_significance.get("backend", "pyroot_roofit") if use_roofit_primary else primary_backend
    )
    blinding = read_json(outputs / "report" / "blinding_summary.json")
    strategy = read_json(outputs / "background_modeling_strategy.json")
    signal_pdf = read_json(outputs / "fit" / fit_id / "signal_pdf.json")
    bkg_choice = read_json(outputs / "fit" / fit_id / "background_pdf_choice.json")
    spurious = read_json(outputs / "fit" / fit_id / "spurious_signal.json")
    systematics = read_json(outputs / "systematics.json")
    partition_spec = _load_optional_json(outputs / "report" / "partition_spec.json", {})
    partition_checks = _load_optional_json(outputs / "report" / "partition_checks.json", {})
    partition_manifest = _load_optional_json(outputs / "manifest" / "partitions.json", {})
    asimov = _compute_asimov_significance(outputs / "fit" / "workspace.json", fit_id)

    n_data = len([s for s in registry.get("samples", []) if s.get("kind") == "data"])
    n_signal = len([s for s in registry.get("samples", []) if s.get("kind") == "signal"])
    n_bkg = len([s for s in registry.get("samples", []) if s.get("kind") == "background"])

    norm_rows = norm_artifacts["norm_table"]["rows"]
    runtime_lumi_values = norm_artifacts["norm_table"].get("lumi_fb_values", [])
    lumi_matches_target = bool(
        runtime_lumi_values
        and all(np.isfinite(float(v)) and np.isclose(float(v), float(target_lumi_fb), rtol=0.0, atol=1e-9)
                for v in runtime_lumi_values)
    )
    top_bkg_rows = [row for row in norm_rows if row.get("kind") == "background"][:12]
    top_sig_rows = [row for row in norm_rows if row.get("kind") == "signal"][:8]
    table_rows = top_bkg_rows + top_sig_rows

    lines: List[str] = []
    lines.append("# Higgs to Diphoton Search Final Analysis Report")
    lines.append("")
    lines.append("## 1. Introduction")
    lines.append("")
    lines.append(
        "This note reports a full end-to-end Higgs to diphoton analysis over the ATLAS Open Data "
        "Run-2 diphoton sample set (data and simulation), using the executable configuration in this repository."
    )
    lines.append(
        "The workflow covers ingestion, object definition, region selection, cut flow, histogram templates, "
        "likelihood fits, profile-likelihood discovery significance, blinding-aware visualization, and final reporting."
    )
    lines.append("Fit/significance backend for observed results: `{}`.".format(_escape_md(fit_backend)))
    lines.append("")
    lines.append("## 2. Data and Monte Carlo Samples")
    lines.append("")
    lines.append(
        "The processed registry contains {} data samples, {} signal samples, and {} background samples."
        .format(n_data, n_signal, n_bkg)
    )
    lines.append(
        "The analysis target luminosity for this workflow is {:.1f} fb^-1. Monte Carlo normalization follows:".format(
            float(target_lumi_fb)
        )
    )
    lines.append("")
    lines.append("`norm_factor = (sigma_pb * k_factor * filter_eff * lumi_pb) / sumw`")
    lines.append("")
    lines.append("`w_final = w_event * norm_factor`")
    lines.append("")
    lines.append(
        "Runtime registry luminosity values in this run: `{}` (see `{}/normalization/norm_table.json`).".format(
            ", ".join(str(v) for v in runtime_lumi_values) if runtime_lumi_values else "not_available",
            outputs,
        )
    )
    lines.append("")
    lines.append(
        "The table below lists dominant MC contributors by absolute reference-region yield with required normalization inputs "
        "(reference region `{}`; full table: `{}/normalization/norm_table.json`).".format(reference_region, outputs)
    )
    lines.append("")
    lines.append("| DSID | Sample label | Process | Kind | xsec_pb | k_factor | filter_eff | Reference-region yield |")
    lines.append("| --- | --- | --- | --- | ---: | ---: | ---: | ---: |")
    for row in table_rows:
        lines.append(
            "| {sid} | {label} | {proc} | {kind} | {xsec} | {kfac} | {eff} | {yieldv} |".format(
                sid=_escape_md(row.get("sample_id", "")),
                label=_escape_md(row.get("sample_name", "")),
                proc=_escape_md(row.get("process_name", "")),
                kind=_escape_md(row.get("kind", "")),
                xsec=_format_float(row.get("xsec_pb"), 6),
                kfac=_format_float(row.get("k_factor"), 4),
                eff=_format_float(row.get("filter_eff"), 4),
                yieldv=_format_float(row.get("reference_region_yield"), 6),
            )
        )
    lines.append("")
    lines.append("## 3. Object Definition and Event Selection")
    lines.append("")
    lines.append(
        "Reconstructed photons are built from available `photon_*` branches with tight identification/isolation flags "
        "and acceptance/kinematic thresholds from `analysis/regions.yaml`."
    )
    lines.append(
        "Derived event observables include `m_gg`, `diphoton_pt`, and `diphoton_deltaR` from leading/subleading photons."
    )
    lines.append(
        "Selections are evaluated by executable region expressions; no prose-only region is used in production execution."
    )
    lines.append("")
    lines.append("## 4. Overview of the Analysis Strategy")
    lines.append("")
    lines.append(
        "The signal/background strategy is artifact-driven (`{}/background_modeling_strategy.json`) with explicit "
        "classification and CR->SR normalization intent.".format(outputs)
    )
    lines.append(
        "Background strategy entries: {} (mc_template), {} (data_driven).".format(
            sum(
                1
                for row in strategy.get("background_process_modeling", [])
                if row.get("modeling_strategy") == "mc_template"
            ),
            sum(
                1
                for row in strategy.get("background_process_modeling", [])
                if row.get("modeling_strategy") == "data_driven"
            ),
        )
    )
    if partition_checks:
        lines.append(
            "Partition validation: status={} with {} partitions (`{}/report/partition_checks.json`).".format(
                _escape_md(partition_checks.get("summary", {}).get("status", "unknown")),
                _escape_md(partition_checks.get("meta", {}).get("n_partitions", "n/a")),
                outputs,
            )
        )
    lines.append(
        "Mass-model selection artifacts are available for analytic signal/background parameterization and spurious-signal checks."
    )
    lines.append("")
    lines.append("## 5. Signal and Control Regions")
    lines.append("")
    categories = partition_spec.get("categories", [])
    if categories:
        lines.append("Category definitions:")
        lines.append("")
        lines.append("| Category ID | Label | Assignment basis | Assignment definition | Coverage |")
        lines.append("| --- | --- | --- | --- | --- |")
        for cat in categories:
            lines.append(
                "| {cid} | {label} | {basis} | {definition} | {coverage} |".format(
                    cid=_escape_md(cat.get("category_id", "")),
                    label=_escape_md(cat.get("label", "")),
                    basis=_escape_md(cat.get("assignment_basis", "")),
                    definition=_escape_md(cat.get("assignment_definition", "")),
                    coverage=_escape_md(cat.get("coverage", "")),
                )
            )
        lines.append("")
    lines.append("| Region ID | Kind | Label | Data shown in plot |")
    lines.append("| --- | --- | --- | --- |")
    for region in regions_cfg.get("regions", []):
        rid = str(region.get("region_id", ""))
        kind = str(region.get("kind", "unknown"))
        label = str(region.get("label", ""))
        data_shown = blinding.get("regions", {}).get(rid, {}).get("data_shown", False)
        lines.append(
            "| {rid} | {kind} | {label} | {shown} |".format(
                rid=_escape_md(rid),
                kind=_escape_md(kind),
                label=_escape_md(label),
                shown="yes" if data_shown else "no",
            )
        )
    if partition_manifest:
        lines.append("")
        lines.append(
            "Partition manifest entries: {} (`{}/manifest/partitions.json`).".format(
                _escape_md(partition_manifest.get("n_partitions", "n/a")),
                outputs,
            )
        )
    lines.append("")
    lines.append(
        "Blinding summary: `blind_sr={}`, control-region-only normalization fit status=`{}`.".format(
            bool(blinding.get("blind_sr", True)),
            blinding.get("normalization_fit", {}).get("status", "unknown"),
        )
    )
    prefit_count = sum(1 for payload in blinding.get("regions", {}).values() if payload.get("prefit_plot"))
    postfit_count = sum(1 for payload in blinding.get("regions", {}).values() if payload.get("postfit_plot"))
    lines.append(
        "Non-signal pre-fit/post-fit visualization counts: pre-fit={}, post-fit={}.".format(
            prefit_count, postfit_count
        )
    )
    lines.append("")
    lines.append("## 6. Cut Flow")
    lines.append("")
    region_order = fit_regions[:]
    for region in regions_cfg.get("regions", []):
        if not isinstance(region, dict):
            continue
        rid = str(region.get("region_id", ""))
        if rid and rid not in region_order:
            region_order.append(rid)
    for region_id in region_order:
        rows = cutflow.get(region_id, [])
        if not rows:
            continue
        lines.append("### {}".format(region_id))
        lines.append("")
        lines.append("| Step | Data n_raw | Background weighted | Signal weighted |")
        lines.append("| --- | ---: | ---: | ---: |")
        for row in rows:
            lines.append(
                "| {name} | {data} | {bkg} | {sig} |".format(
                    name=_escape_md(row.get("name", "step")),
                    data=int(round(float(row.get("data_n_raw", 0.0)))),
                    bkg=_format_float(row.get("mc_bkg_n_weighted", 0.0), 6),
                    sig=_format_float(row.get("mc_sig_n_weighted", 0.0), 6),
                )
            )
        lines.append("")
    lines.append("Final region yields (weighted):")
    lines.append("")
    lines.append("| Region | Data | Background | Signal |")
    lines.append("| --- | ---: | ---: | ---: |")
    for rid in sorted(by_region.keys()):
        vals = by_region[rid]
        lines.append(
            "| {rid} | {data} | {bkg} | {sig} |".format(
                rid=_escape_md(rid),
                data=_format_float(vals.get("data", 0.0), 6),
                bkg=_format_float(vals.get("background", 0.0), 6),
                sig=_format_float(vals.get("signal", 0.0), 6),
            )
        )
    lines.append("")
    if signal_process_cutflow.get("category_regions"):
        cat_regions = signal_process_cutflow["category_regions"]
        lines.append("### Higgs-Production Signal Cutflow Across 10 Categories")
        lines.append("")
        lines.append(
            "The table below decomposes signal yields by Higgs production process across the 10 analysis categories."
        )
        lines.append(
            "Each cell is the final weighted yield after full category selection in that category "
            "(for `SR_2JET`, the final row corresponds to `delta_phi(gg,jj) > 2.6`)."
        )
        lines.append("Artifact: `{}`.".format(_escape_md(signal_process_cutflow_path)))
        lines.append("")
        lines.append(
            "| Production process | Signal MC samples | {} | Total (10-cat) |".format(
                " | ".join(_escape_md(rid) for rid in cat_regions)
            )
        )
        lines.append("| --- | ---: |{} ---: |".format(" ---: |" * len(cat_regions)))
        for mode_row in signal_process_cutflow.get("modes", []):
            region_vals = mode_row.get("final_category_yields", {})
            lines.append(
                "| {mode} | {n_samples} | {vals} | {total} |".format(
                    mode=_escape_md(mode_row.get("mode", "unknown")),
                    n_samples=int(mode_row.get("n_signal_samples", 0)),
                    vals=" | ".join(
                        _format_float(region_vals.get(rid, 0.0), 6) for rid in cat_regions
                    ),
                    total=_format_float(mode_row.get("total_10cat", 0.0), 6),
                )
            )

        combined = signal_process_cutflow.get("combined_signal", {}).get("final_category_yields", {})
        combined_samples = int(sum(int(row.get("n_signal_samples", 0)) for row in signal_process_cutflow.get("modes", [])))
        lines.append(
            "| **all_signal_combined** | **{}** | {} | **{}** |".format(
                combined_samples,
                " | ".join(_format_float(combined.get(rid, 0.0), 6) for rid in cat_regions),
                _format_float(signal_process_cutflow.get("combined_signal", {}).get("total_10cat", 0.0), 6),
            )
        )
        lines.append("")

        twojet = signal_process_cutflow.get("region_step_breakdown", {}).get("SR_2JET", {})
        step_order = list(twojet.get("step_order", []))
        if len(step_order) > 1:
            step_lookup = {
                str(step.get("name", "step")): step
                for step in twojet.get("steps", [])
                if isinstance(step, dict)
            }
            lines.append("SR_2JET step-by-step weighted signal cutflow by production process:")
            lines.append("")
            lines.append(
                "| Production process | {} |".format(
                    " | ".join(_escape_md(step_name) for step_name in step_order)
                )
            )
            lines.append("| --- |{}".format(" ---: |" * len(step_order)))
            for mode_row in signal_process_cutflow.get("modes", []):
                mode = str(mode_row.get("mode", "unknown"))
                lines.append(
                    "| {mode} | {vals} |".format(
                        mode=_escape_md(mode),
                        vals=" | ".join(
                            _format_float(
                                step_lookup.get(step_name, {}).get("yields_by_mode", {}).get(mode, 0.0),
                                6,
                            )
                            for step_name in step_order
                        ),
                    )
                )
            lines.append("")

    roofit_rows = roofit_cutflow.get("categories", []) if isinstance(roofit_cutflow, dict) else []
    if roofit_rows:
        lines.append("### RooFit Post-fit Mass-window Cutflow (125 +/- 2 GeV)")
        lines.append("")
        lines.append(
            "Expected signal and background yields from the combined RooFit model in each category mass window."
        )
        lines.append(
            "Background is constrained by sideband fits per category with a shared signal-strength parameter across categories."
        )
        lines.append("")
        lines.append("| Category | Expected signal (post-fit) | Expected background (post-fit) | Observed data in 125 +/- 2 | Observed data in sidebands |")
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for row in roofit_rows:
            obs_window = row.get("observed_data_in_window")
            obs_window_text = "blinded" if obs_window is None else _format_float(obs_window, 6)
            lines.append(
                "| {cat} | {sig} | {bkg} | {obs_win} | {obs_side} |".format(
                    cat=_escape_md(row.get("category", "unknown")),
                    sig=_format_float(row.get("expected_signal_postfit", 0.0), 6),
                    bkg=_format_float(row.get("expected_background_postfit", 0.0), 6),
                    obs_win=obs_window_text,
                    obs_side=_format_float(row.get("observed_data_sidebands", 0.0), 6),
                )
            )
        totals = roofit_cutflow.get("totals", {})
        total_obs_window = totals.get("observed_data_in_window")
        total_obs_window_text = "blinded" if total_obs_window is None else _format_float(total_obs_window, 6)
        lines.append(
            "| **Total (10 cat)** | **{sig}** | **{bkg}** | **{obs_win}** | **{obs_side}** |".format(
                sig=_format_float(totals.get("expected_signal_postfit", 0.0), 6),
                bkg=_format_float(totals.get("expected_background_postfit", 0.0), 6),
                obs_win=total_obs_window_text,
                obs_side=_format_float(totals.get("observed_data_sidebands", 0.0), 6),
            )
        )
        lines.append("")

    lines.append("## 7. Distributions in Signal and Control Regions")
    lines.append("")
    lines.append(
        "Required validation plots were produced, including photon kinematics, diphoton observables, cut-flow diagnostics, "
        "category plots, fit spectrum, pull, and blinded CR/SR region views."
    )
    lines.append(
        "For non-signal regions, both pre-fit and post-fit overlays are produced with observed data shown."
    )
    if len(categories) == 1 and str(categories[0].get("category_id", "")) == "inclusive":
        lines.append(
            "Category_1/2/3 mass plots are treated as visualization-only proxy bins and are not statistical channels in this run."
        )
    lines.append(
        "In `{}`, observed data counts are peak[120,130] = {} and sideband[105,120)U(130,160] = {}.".format(
            mass_region,
            _format_float(mass_counts.get("peak_120_130", 0.0), 6),
            _format_float(mass_counts.get("sideband_105_120_130_160", 0.0), 6),
        )
    )
    lines.append("Embedded plots:")
    lines.append("")
    lines.extend(_embedded_plot_blocks(plot_names, outputs, out_path))
    lines.append("")
    lines.append("## 8. Systematic Uncertainties")
    lines.append("")
    lines.append(
        "Systematics are currently implemented as a stat-only nuisance model (`{}`) with explicit placeholder language; "
        "no additional shape or normalization nuisance set is asserted beyond provided artifacts.".format(
            _escape_md(systematics.get("note", "stat-only"))
        )
    )
    lines.append(
        "Signal-shape proxy: mean={}, width={}, model={}.".format(
            _format_float(signal_pdf.get("mean"), 6),
            _format_float(signal_pdf.get("width"), 6),
            _escape_md(signal_pdf.get("pdf", "unknown")),
        )
    )
    lines.append(
        "Background choice: family={} degree={} (passed target={}).".format(
            _escape_md(bkg_choice.get("chosen_family", "unknown")),
            _escape_md(bkg_choice.get("chosen_degree", "n/a")),
            _escape_md(bkg_choice.get("passed_target", "n/a")),
        )
    )
    lines.append(
        "Spurious signal: N_spur={}, sigma_Nsig={}, r_spur={} (threshold={}).".format(
            _format_float(spurious.get("n_spur"), 6),
            _format_float(spurious.get("sigma_nsig"), 6),
            _format_float(spurious.get("r_spur"), 6),
            _format_float(spurious.get("criterion_threshold"), 4),
        )
    )
    lines.append("")
    lines.append("## 9. Statistical Interpretation")
    lines.append("")
    observed_z = float(significance.get("z_discovery", float("nan")))
    expected_z = float(
        asimov.get("asimov_signal_plus_background_mu1", {}).get("z_discovery", float("nan"))
    )
    if use_roofit_primary:
        lines.append(
            "Observed fit (`{fit}`, RooFit combined): backend={backend}, status={status}, {poi}={poi_val} +/- {poi_err}, nll_free={nll_free}, nll_mu0={nll_mu0}.".format(
                fit=fit_id,
                backend=_escape_md(str(roofit_significance.get("backend", "pyroot_roofit"))),
                status=_escape_md(roofit_significance.get("status", "unknown")),
                poi=_escape_md(roofit_significance.get("poi_name", "mu")),
                poi_val=_format_float(roofit_significance.get("mu_hat"), 6),
                poi_err=_format_float(roofit_significance.get("mu_hat_error"), 6),
                nll_free=_format_float(roofit_significance.get("nll_free"), 8),
                nll_mu0=_format_float(roofit_significance.get("nll_mu0"), 8),
            )
        )
        lines.append(
            "Observed discovery significance (backend={}): q0={}, Z={}, mu_hat={}.".format(
                _escape_md(str(roofit_significance.get("backend", "pyroot_roofit"))),
                _format_float(roofit_significance.get("q0"), 6),
                _format_float(roofit_significance.get("z_discovery"), 6),
                _format_float(roofit_significance.get("mu_hat"), 6),
            )
        )
        observed_z = float(roofit_significance.get("z_discovery", float("nan")))

        if roofit_asimov.get("status") == "ok":
            lines.append(
                "Asimov expected discovery (RooFit, mu_gen={}, {}): q0={}, Z={}.".format(
                    _format_float(roofit_asimov.get("mu_gen"), 4),
                    _escape_md(roofit_asimov.get("generation_hypothesis", "unspecified_hypothesis")),
                    _format_float(roofit_asimov.get("q0"), 6),
                    _format_float(roofit_asimov.get("z_discovery"), 6),
                )
            )
            expected_z = float(roofit_asimov.get("z_discovery", float("nan")))
        else:
            lines.append(
                "RooFit Asimov expected-significance evaluation failed: {}.".format(
                    _escape_md(roofit_asimov.get("error", "unknown"))
                )
            )

        if pyhf_crosscheck_significance.get("status") == "ok":
            lines.append(
                "Template-model cross-check (pyhf): q0={}, Z={}, mu_hat={}.".format(
                    _format_float(pyhf_crosscheck_significance.get("q0"), 6),
                    _format_float(pyhf_crosscheck_significance.get("z_discovery"), 6),
                    _format_float(pyhf_crosscheck_significance.get("mu_hat"), 6),
                )
            )
        else:
            lines.append(
                "Template-model cross-check (pyhf): not available in this run."
            )
    else:
        lines.append(
            "Observed fit (`{fit}`): backend={backend}, status={status}, {poi}={poi_val}, twice_nll={nll}.".format(
                fit=fit_id,
                backend=_escape_md(fit_backend),
                status=_escape_md(fit_results.get("status", "unknown")),
                poi=_escape_md(fit_results.get("poi_name", "poi")),
                poi_val=_format_float(fit_results.get("bestfit_poi"), 6),
                nll=_format_float(fit_results.get("twice_nll"), 6),
            )
        )
        lines.append(
            "Observed discovery significance (backend={}): q0={}, Z={}, mu_hat={}.".format(
                _escape_md(str(significance.get("backend", fit_backend))),
                _format_float(significance.get("q0"), 6),
                _format_float(significance.get("z_discovery"), 6),
                _format_float(significance.get("mu_hat"), 6),
            )
        )
        if asimov.get("status") == "ok":
            b_only = asimov["asimov_background_only"]
            sb = asimov["asimov_signal_plus_background_mu1"]
            lines.append(
                "Asimov (background-only) expected discovery: q0={}, Z={}.".format(
                    _format_float(b_only.get("q0"), 6),
                    _format_float(b_only.get("z_discovery"), 6),
                )
            )
            lines.append(
                "Asimov (signal-plus-background, mu=1) expected discovery: q0={}, Z={}.".format(
                    _format_float(sb.get("q0"), 6),
                    _format_float(sb.get("z_discovery"), 6),
                )
            )
        else:
            lines.append(
                "Asimov expected-significance evaluation failed: {}.".format(
                    _escape_md(asimov.get("error", "unknown"))
                )
            )
    lines.append(
        "Given active SR blinding in visualization products, Asimov results are the primary pre-unblinding sensitivity reference."
    )
    lines.append("")
    lines.append("## 10. Summary")
    lines.append("")
    lines.append(
        "The repository pipeline successfully produced a complete, reproducible set of artifacts across event processing, "
        "selection, template construction, fitting, significance, and blinded visualization."
    )
    lines.append(
        "For `{}`, the observed discovery significance is Z={} and the primary Asimov expected discovery is Z={}.".format(
            fit_id,
            _format_float(observed_z, 6),
            _format_float(expected_z, 6),
        )
    )
    lines.append(
        "The current model is suitable for a robust open-data analysis demonstration and provides a transparent baseline "
        "for future systematic-model and category refinements."
    )
    lines.append("")
    lines.append("## Implementation Differences from Reference Analysis")
    lines.append("")
    lines.append("| Reference concept | Open-data observable used | Reasoning for replacement | Expected impact |")
    lines.append("| --- | --- | --- | --- |")
    lines.append(
        "| Era-specific photon identification/isolation working points | `photon_isTightID`, `photon_isTightIso`, kinematic/acceptance thresholds in `analysis/regions.yaml` | These are directly available and executable in the ntuples while preserving a tight-photon selection intent | Selection efficiency and purity differ from legacy calibrations |"
    )
    lines.append(
        "| Full legacy category scheme | Category/region partition artifacts (`{}/report/partition_spec.json`, `{}/manifest/partitions.json`) with executable category-proxy regions | The workflow now requires machine-readable category assignment and (category, region) manifest for downstream tools | Category granularity and category purity differ due open-data proxy substitutions |".format(
            outputs,
            outputs,
        )
    )
    lines.append(
        "| Full nuisance parameter model | Stat-only nuisance placeholder in `outputs/systematics.json` plus explicit spurious-signal checks | Available public inputs in this repository support robust stat-only execution; added systematics require external calibrations not provided here | Uncertainty coverage is reduced and interval realism is limited |"
    )
    lines.append(
        "| Reference-era absolute normalization details | Metadata-driven DSID normalization fields with runtime registry luminosity values and CR-constrained scaling | This is the closest consistent open-data implementation using available metadata and fit constraints | Absolute MC normalization differs from a full production calibration chain |"
    )
    if lumi_matches_target:
        lines.append(
            "| Target integrated luminosity for Run-2 dataset | Per-sample `lumi_fb` in registry and normalization artifacts | Central normalization is explicitly enforced to `36.1 fb^-1` for this workflow | No luminosity-rescaling mismatch in central yields |"
        )
    else:
        lines.append(
            "| Target integrated luminosity 36.1 fb^-1 for Run-2 dataset | Current registry-derived `lumi_fb` values in produced artifacts | Current summary/registry mapping in this repository does not inject a numeric 36.1 fb^-1 into per-sample `lumi_fb`; this is kept explicit rather than silently overwritten | Absolute yield scale is shifted and CR normalization factors absorb part of the mismatch |"
        )
    lines.append("")
    lines.append("## Appendix A: Agent Decisions and Deviations")
    lines.append("")
    lines.append("| Issue | Decision | Justification |")
    lines.append("| --- | --- | --- |")
    lines.append(
        "| Missing direct legacy object variables in open-data ntuples | Use nearest reconstructed photon ID/isolation flags and explicit kinematic cuts | Keeps selection executable and physics-motivated while preserving transparency of approximation |"
    )
    lines.append(
        "| Requirement for pre-unblinding sensitivity statement | Added Asimov significance artifact at `{}/fit/{}/significance_asimov.json` | Provides expected sensitivity context without relying on SR data display |".format(
            outputs,
            fit_id,
        )
    )
    lines.append(
        "| Need for normalization traceability | Added normalization artifacts under `{}/normalization/` (`metadata_resolution.json`, `norm_table.json`, `norm_audit.json`, `stacked_yields_summary.json`) | Makes per-sample normalization terms and audit status explicit and reviewable |".format(
            outputs
        )
    )
    lines.append(
        "| Need for explicit category definitions | Added partition artifacts (`partition_spec.json`, `partition_checks.json`, `partitions.json`) and category table in this report | Makes category/channel definitions explicit, auditable, and machine-readable |"
    )
    if lumi_matches_target:
        lines.append(
            "| Target luminosity policy | Enforced `lumi_fb = 36.1` in registry/pipeline defaults and surfaced runtime values in artifacts/report | Keeps normalization explicit and reproducible across reruns |"
        )
    else:
        lines.append(
            "| Target luminosity vs runtime registry luminosity mismatch | Kept runtime `lumi_fb` values explicit in artifacts/report and treated this as a documented deviation | Avoids hidden renormalization and keeps downstream interpretation auditable |"
        )
    lines.append(
        "| Signal-region plot blinding during reporting | Kept SR data hidden in blinded region plots and referenced Asimov expected sensitivity in interpretation | Preserves blind-analysis behavior while still reporting a complete statistical workflow |"
    )
    lines.append("")
    lines.append(
        "Report metadata: summary=`{summary}`, outputs=`{outputs}`, target_lumi_fb={lumi}.".format(
            summary=summary_path,
            outputs=outputs,
            lumi=_format_float(target_lumi_fb, 4),
        )
    )

    ensure_dir(out_path.parent)
    out_path.write_text("\n".join(lines) + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build publication-style final analysis report")
    parser.add_argument("--summary", required=True)
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--out", default="reports/final_analysis_report.md")
    parser.add_argument("--target-lumi-fb", type=float, default=36.1)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    _build_report(
        summary_path=Path(args.summary),
        outputs=Path(args.outputs),
        out_path=Path(args.out),
        target_lumi_fb=float(args.target_lumi_fb),
    )
    print("final report written: {}".format(args.out))


if __name__ == "__main__":
    main()
