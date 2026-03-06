import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import awkward as ak
import numpy as np
import yaml

from analysis.common import ensure_dir, read_json, run_metadata, write_json
from analysis.config.load_summary import load_and_validate
from analysis.hists.histmaker import _binning_from_fit, _hist
from analysis.io.readers import load_events
from analysis.io.rootml_backend import load_events_with_rootml_cache, rootmltool_is_available
from analysis.objects.photons import build_photons
from analysis.plotting.blinded_regions import run_blinded_region_visualization
from analysis.plotting.plots import main as plotting_main
from analysis.partitioning.build_partitions import build_partitions
from analysis.report.make_report import build_report
from analysis.samples.registry import build_registry
from analysis.samples.strategy import build_strategy
from analysis.samples.weights import event_weight
from analysis.selections.engine import compute_cutflow, load_regions, region_masks
from analysis.stats.fit import run_fit
from analysis.stats.stattool_backend import resolve_pyhf_backend, stattool_is_available
from analysis.stats.mass_model_selection import run_mass_model_selection
from analysis.stats.pyhf_workspace import build_workspace
from analysis.stats.roofit_combined import run_combined_fit
from analysis.stats.significance import compute_discovery_significance
from analysis.validation.parity import run_parity_check



def _required_branches() -> List[str]:
    return [
        "eventNumber",
        "runNumber",
        "mcWeight",
        "num_events",
        "sum_of_weights",
        "xsec",
        "kfac",
        "filteff",
        "photon_pt",
        "photon_eta",
        "photon_phi",
        "photon_e",
        "photon_topoetcone40",
        "photon_isTightID",
        "photon_isTightIso",
        "photon_isLooseIso",
        "ScaleFactor_PILEUP",
        "ScaleFactor_PHOTON",
        "ScaleFactor_MLTRIGGER",
        "ScaleFactor_JVT",
        "ScaleFactor_BTAG",
        "ScaleFactor_FTAG",
        "met",
        "met_phi",
        "jet_pt",
        "jet_eta",
        "jet_phi",
        "jet_e",
        "jet_jvt",
    ]



def _representative_files(inputs: Path) -> Dict[str, Path]:
    data_files = sorted((inputs / "data").glob("*.root"))
    mc_files = sorted((inputs / "MC").glob("*.root"))
    if not data_files or not mc_files:
        raise RuntimeError("input-data inventory missing data or MC ROOT files")
    return {"data": data_files[0], "mc": mc_files[0]}



def _branch_meaning(branch: str) -> str:
    if branch.startswith("photon_"):
        return "Reconstructed photon collection variable"
    if branch.startswith("jet_") or branch.startswith("largeRJet_"):
        return "Reconstructed jet collection variable"
    if branch.startswith("lep_"):
        return "Reconstructed lepton collection variable"
    if branch.startswith("tau_"):
        return "Reconstructed tau collection variable"
    if branch.startswith("truth_"):
        return "Truth-level auxiliary variable"
    if branch.startswith("ScaleFactor_"):
        return "Per-event scale factor"
    if branch.startswith("trig") or branch.startswith("Trigger"):
        return "Trigger bit or trigger matching flag"
    if branch in {"mcWeight", "xsec", "kfac", "filteff", "sum_of_weights", "sum_of_weights_squared", "num_events"}:
        return "Normalization and Monte Carlo weight input"
    if branch in {"met", "met_phi", "met_mpx", "met_mpy"}:
        return "Missing transverse momentum"
    if branch in {"eventNumber", "runNumber", "channelNumber", "category"}:
        return "Event/run/sample identifier"
    if branch in {"sig_ph", "n_sig_ph"}:
        return "Auxiliary signal-photon indexing metadata"
    return "Auxiliary analysis branch"



def _inventory_inputs(inputs: Path, outputs: Path) -> None:
    import uproot

    inv_dir = ensure_dir(outputs / "inventory")

    data_files = sorted((inputs / "data").glob("*.root"))
    mc_files = sorted((inputs / "MC").glob("*.root"))

    inventory = {
        "data_files": [str(p) for p in data_files],
        "mc_files": [str(p) for p in mc_files],
    }

    reps = _representative_files(inputs)
    rep_details = {}
    for kind, path in reps.items():
        with uproot.open(path) as f:
            trees = [k for k, v in f.classnames().items() if "TTree" in v]
            main_tree = "analysis;1" if "analysis;1" in trees else (trees[0] if trees else None)
            if main_tree is None:
                raise RuntimeError("No TTree found in {}".format(path))
            tree = f[main_tree]
            branches = list(tree.keys())
            rep_details[kind] = {
                "file": str(path),
                "main_tree": main_tree,
                "entries": int(tree.num_entries),
                "branches": branches,
            }

    mapping = {}
    all_branches = sorted(
        set(rep_details["data"]["branches"]) | set(rep_details["mc"]["branches"])
    )
    for b in all_branches:
        mapping[b] = _branch_meaning(b)

    inventory["representative"] = rep_details
    write_json(inv_dir / "input_inventory.json", inventory)
    write_json(inv_dir / "branch_to_meaning.json", mapping)



def _select_samples(
    samples: List[Dict[str, Any]], requested: List[str], all_samples: bool = False
) -> List[Dict[str, Any]]:
    if all_samples:
        return list(samples)

    if requested:
        req = set(requested)
        out = [
            s
            for s in samples
            if s.get("sample_id") in req or s.get("sample_name") in req
        ]
        if not out:
            raise RuntimeError("None of requested samples found: {}".format(", ".join(requested)))
        return out

    # Default mini-run for practicality: one data + one background + one signal.
    data = next((s for s in samples if s.get("kind") == "data"), None)
    background = next((s for s in samples if s.get("kind") == "background"), None)
    signal = next((s for s in samples if s.get("kind") == "signal"), None)
    out = []
    if data:
        out.append(data)
    if background and background is not data:
        out.append(background)
    if signal and signal not in out:
        out.append(signal)
    return out



def _write_cutflow_and_yields(
    sample: Dict[str, Any],
    events: ak.Array,
    weights: ak.Array,
    regions_cfg: Dict[str, Any],
    out_root: Path,
    summary_path: Path,
    regions_path: Path,
) -> Dict[str, Dict[str, float]]:
    masks = region_masks(events, regions_cfg)

    yields = {}
    cutflow_payload = {"sample_id": sample["sample_id"], "cutflow": {}}
    for region in regions_cfg.get("regions", []):
        rid = region.get("region_id")
        if rid not in masks:
            continue
        mask = masks[rid]
        w = ak.to_numpy(weights[mask])
        yields[rid] = {
            "n_raw": float(np.sum(ak.to_numpy(mask))),
            "yield": float(np.sum(w)),
            "sumw2": float(np.sum(w * w)),
        }

        cutflow_rows = compute_cutflow(events, region, weights)
        cutflow_payload["cutflow"][rid] = cutflow_rows

    cutflow_payload["meta"] = run_metadata(summary_path, regions_path)
    yield_payload = {
        "sample_id": sample["sample_id"],
        "regions": yields,
        "meta": run_metadata(summary_path, regions_path),
    }

    write_json(out_root / "cutflows" / (sample["sample_id"] + ".json"), cutflow_payload)
    write_json(out_root / "yields" / (sample["sample_id"] + ".json"), yield_payload)
    write_json(out_root / "regions" / (sample["sample_id"] + ".regions.json"), yield_payload)
    return yields



def _write_hists(
    sample: Dict[str, Any],
    events: ak.Array,
    weights: ak.Array,
    masks: Dict[str, ak.Array],
    regions_cfg: Dict[str, Any],
    out_root: Path,
) -> None:
    fits = regions_cfg.get("fits", [])
    if not fits:
        fits = [{"fit_id": "FIT_MAIN", "regions_included": list(masks.keys()), "observable": "m_gg"}]

    fit_regions = set()

    for fit in fits:
        edges, observable = _binning_from_fit(fit)
        obs = observable if observable in events.fields else "m_gg"
        for rid in fit.get("regions_included", []):
            if rid not in masks:
                continue
            fit_regions.add(rid)
            counts, sumw2 = _hist(events[obs][masks[rid]], weights[masks[rid]], edges)
            target = out_root / "hists" / rid / obs
            ensure_dir(target)
            meta = {
                "region": rid,
                "sample": sample["sample_id"],
                "observable": obs,
                "fit_id": fit.get("fit_id", "FIT_MAIN"),
            }
            np.savez(
                target / (sample["sample_id"] + ".npz"),
                edges=edges,
                counts=counts,
                sumw2=sumw2,
                metadata=json.dumps(meta),
            )

    # Also persist templates for non-fit regions (for blinded/control visualizations).
    aux_edges = np.linspace(105.0, 160.0, 56)
    aux_obs = "m_gg"
    if fits:
        aux_edges, fit_obs = _binning_from_fit(fits[0])
        aux_obs = fit_obs if fit_obs in events.fields else "m_gg"

    all_regions = []
    for region in regions_cfg.get("regions", []):
        if not isinstance(region, dict):
            continue
        rid = region.get("region_id")
        if rid:
            all_regions.append(rid)

    for rid in all_regions:
        if rid in fit_regions or rid not in masks:
            continue
        counts, sumw2 = _hist(events[aux_obs][masks[rid]], weights[masks[rid]], aux_edges)
        target = out_root / "hists" / rid / aux_obs
        ensure_dir(target)
        meta = {
            "region": rid,
            "sample": sample["sample_id"],
            "observable": aux_obs,
            "fit_id": "AUX_VIS",
        }
        np.savez(
            target / (sample["sample_id"] + ".npz"),
            edges=aux_edges,
            counts=counts,
            sumw2=sumw2,
            metadata=json.dumps(meta),
        )



def _write_systematics(out_root: Path) -> Path:
    syst_path = out_root / "systematics.json"
    payload = {
        "nuisances": [
            {
                "name": "stat_only",
                "type": "stat",
                "affected_samples": "all",
                "affected_regions": "all",
            }
        ],
        "note": "Systematics not fully specified; using stat-only model.",
    }
    write_json(syst_path, payload)
    return syst_path



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


def _enforce_backend_policy(summary_payload: Dict[str, Any], fit_backend: str) -> None:
    if not _is_hgg_analysis(summary_payload):
        return
    backend_name = str(fit_backend).strip().lower()
    if backend_name != "pyroot_roofit":
        raise RuntimeError(
            "H->gammagamma workflow requires --fit-backend pyroot_roofit "
            "(pyhf is allowed only as a labeled cross-check)."
        )


def _fit_ids_from_regions_cfg(regions_cfg: Dict[str, Any]) -> List[str]:
    fit_ids = [
        str(fit.get("fit_id", "FIT_MAIN"))
        for fit in regions_cfg.get("fits", [])
        if isinstance(fit, dict)
    ]
    return fit_ids if fit_ids else ["FIT_MAIN"]


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


def _assert_hgg_roofit_artifacts(outputs: Path, fit_id: str, fit_regions: List[str]) -> None:
    roofit_dir = outputs / "fit" / fit_id / "roofit_combined"
    required = [
        roofit_dir / "significance.json",
        roofit_dir / "signal_dscb_parameters.json",
        roofit_dir / "sideband_fit_parameters.json",
        roofit_dir / "cutflow_mass_window_125pm2.json",
    ]
    for region in fit_regions:
        required.append(outputs / "report" / "plots" / "roofit_combined_mgg_{}.png".format(region))

    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(
            "Missing required H->gammagamma RooFit artifacts for {}: {}".format(
                fit_id,
                ", ".join(missing),
            )
        )


def _visual_verification_check(outputs: Path) -> None:
    required = [
        "photon_pt_leading.png",
        "photon_pt_subleading.png",
        "photon_eta_leading.png",
        "photon_eta_subleading.png",
        "diphoton_mass_preselection.png",
        "diphoton_pt.png",
        "diphoton_deltaR.png",
        "photon_multiplicity.png",
        "cutflow_plot.png",
        "diphoton_mass_fit.png",
        "diphoton_mass_pull.png",
    ]

    plots_dir = outputs / "report" / "plots"
    missing = [name for name in required if not (plots_dir / name).exists()]
    if not (plots_dir / "cutflow_table.json").exists():
        missing.append("cutflow_table.json")

    # Category plots are mandatory when categorization exists; we always create 3 proxy categories.
    cat_missing = [
        name
        for name in [
            "diphoton_mass_category_1.png",
            "diphoton_mass_category_2.png",
            "diphoton_mass_category_3.png",
        ]
        if not (plots_dir / name).exists()
    ]
    missing.extend(cat_missing)

    if missing:
        raise RuntimeError("visual verification failed, missing: {}".format(", ".join(missing)))


def _resolve_event_backend(requested_backend: str) -> str:
    backend = str(requested_backend).strip().lower()
    if backend in {"native", "rootmltool"}:
        return backend
    if backend != "auto":
        raise RuntimeError("Unsupported event backend: {}".format(requested_backend))

    available, _reason = rootmltool_is_available()
    if available:
        return "rootmltool"
    return "native"


def _run_parity_check_command(args: argparse.Namespace) -> None:
    out_path = Path(args.out) if args.out else None
    report = run_parity_check(
        baseline_outputs=Path(args.baseline),
        candidate_outputs=Path(args.candidate),
        abs_tol=float(args.abs_tol),
        rel_tol=float(args.rel_tol),
        out_path=out_path,
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
        raise RuntimeError("parity check failed")



def run_pipeline(args: argparse.Namespace) -> None:
    outputs = Path(args.outputs)
    ensure_dir(outputs)
    for sub in [
        "cutflows",
        "yields",
        "hists",
        "fit",
        "report",
        "cache",
        "regions",
        "runs",
        "manifest",
    ]:
        ensure_dir(outputs / sub)

    summary_path = Path(args.summary)
    categories_path = Path(args.categories)
    regions_path = Path("analysis/regions.yaml")

    normalized = load_and_validate(summary_path)
    normalized_path = outputs / "summary.normalized.json"
    write_json(normalized_path, normalized)
    is_hgg = _is_hgg_analysis(normalized)
    _enforce_backend_policy(normalized, args.fit_backend)

    registry_path = outputs / "samples.registry.json"
    registry = build_registry(
        Path(args.inputs),
        summary_path,
        registry_path,
        target_lumi_fb=float(args.target_lumi_fb),
    )
    build_strategy(
        registry_path=registry_path,
        regions_path=regions_path,
        summary_path=summary_path,
        out_path=outputs / "background_modeling_strategy.json",
    )

    _inventory_inputs(Path(args.inputs), outputs)

    selected = _select_samples(
        registry["samples"], args.samples or [], all_samples=args.all_samples
    )
    if not selected:
        raise RuntimeError("No samples selected for run")
    event_backend = _resolve_event_backend(args.event_backend)
    rootml_cache_dir = outputs / "cache" / "rootmltool"
    ensure_dir(rootml_cache_dir)
    print(
        "event_backend_requested={} resolved={}".format(
            args.event_backend, event_backend
        )
    )

    regions_cfg = load_regions(regions_path)
    partition_checks = build_partitions(
        categories_path=categories_path,
        regions_path=regions_path,
        out_spec=outputs / "report" / "partition_spec.json",
        out_manifest=outputs / "manifest" / "partitions.json",
        out_checks=outputs / "report" / "partition_checks.json",
    )
    if partition_checks.get("summary", {}).get("status") != "pass":
        raise RuntimeError("partition validation failed: {}".format(partition_checks.get("summary", {})))
    photon_cfg = regions_cfg.get("globals", {}).get("photons", {})
    fit_ids = _fit_ids_from_regions_cfg(regions_cfg)

    for sample in selected:
        if event_backend == "rootmltool":
            events, rootml_meta = load_events_with_rootml_cache(
                sample_id=str(sample["sample_id"]),
                files=sample["files"],
                tree_name=sample.get("tree_name", "analysis"),
                branches=_required_branches(),
                max_events=args.max_events,
                cache_dir=rootml_cache_dir,
                reuse_cache=not bool(args.no_rootml_cache_reuse),
            )
            print(
                "sample={} rootml_cache_hit={} cache={}".format(
                    sample["sample_id"],
                    rootml_meta.get("cache_hit"),
                    rootml_meta.get("cache_path"),
                )
            )
        else:
            events = load_events(
                sample["files"],
                tree_name=sample.get("tree_name", "analysis"),
                branches=_required_branches(),
                max_events=args.max_events,
            )
        events = build_photons(events, photon_cfg)
        weights = event_weight(events, sample)

        cache_path = outputs / "cache" / (sample["sample_id"] + ".objects.parquet")
        ak.to_parquet(events, cache_path)

        yields = _write_cutflow_and_yields(
            sample,
            events,
            weights,
            regions_cfg,
            outputs,
            summary_path,
            regions_path,
        )

        masks = region_masks(events, regions_cfg)
        _write_hists(sample, events, weights, masks, regions_cfg, outputs)

    systematics_path = _write_systematics(outputs)

    for fit_id in fit_ids:
        model_choice = run_mass_model_selection(
            fit_id=fit_id,
            summary_path=normalized_path,
            hists_dir=outputs / "hists",
            strategy_path=outputs / "background_modeling_strategy.json",
            out_path=outputs / "fit" / fit_id / "background_pdf_choice.json",
        )
        if model_choice.get("status") != "ok":
            raise RuntimeError(
                "mass-model selection failed for {}: {}".format(
                    fit_id,
                    model_choice.get("error", "unknown_error"),
                )
            )

    workspace_path = outputs / "fit" / "workspace.json"
    workspace = build_workspace(
        summary_path=normalized_path,
        hists_dir=outputs / "hists",
        systematics_path=systematics_path,
        out_path=workspace_path,
        registry_path=registry_path,
    )

    run_pyhf_crosscheck = bool(is_hgg and not bool(getattr(args, "no_pyhf_crosscheck", False)))
    stattool_available, stattool_reason = stattool_is_available()
    pyhf_backend_resolved = (
        resolve_pyhf_backend(args.pyhf_backend)
        if (str(args.fit_backend).strip().lower() == "pyhf" or run_pyhf_crosscheck)
        else str(args.pyhf_backend)
    )
    print(
        "pyhf_backend_requested={} resolved={} stattool_available={}".format(
            args.pyhf_backend,
            pyhf_backend_resolved,
            stattool_available,
        )
    )
    for fit_id in fit_ids:
        roofit_summary = None
        if is_hgg:
            roofit_summary = run_combined_fit(
                outputs=outputs,
                registry=registry_path,
                regions=regions_path,
                fit_id=fit_id,
                out_dir=outputs / "fit" / fit_id / "roofit_combined",
                categories=_fit_regions_from_cfg(regions_cfg, fit_id),
                fit_range="sidebands",
                blind_window=(120.0, 130.0),
                show_window_data=False,
                signal_scale_for_blind_fit=1.0,
                compute_asimov_sensitivity=True,
                asimov_mu_gen=0.0,
            )
            signif = read_json(outputs / "fit" / fit_id / "roofit_combined" / "significance.json")
            signif["fit_id"] = fit_id
            result = {
                "status": signif.get("status", "unknown"),
                "fit_id": fit_id,
                "backend": "pyroot_roofit",
                "fit_method": "roofit_combined_category_likelihood",
                "poi_name": str(signif.get("poi_name", "mu")),
                "bestfit_poi": float(signif.get("mu_hat", 0.0)),
                "poi_uncertainty": float(signif.get("mu_hat_error", 0.0)),
                "bestfit_all": [float(signif.get("mu_hat", 0.0))],
                "bestfit_errors": [float(signif.get("mu_hat_error", 0.0))],
                "bestfit_labels": [str(signif.get("poi_name", "mu"))],
                "twice_nll": (
                    2.0 * float(signif.get("nll_free"))
                    if signif.get("nll_free") is not None
                    else None
                ),
                "n_pars": 1,
            }
            write_json(outputs / "fit" / fit_id / "results.json", result)
            write_json(outputs / "fit" / fit_id / "significance.json", signif)
            primary_backend_name = "pyroot_roofit"
        else:
            result = run_fit(
                workspace_path,
                backend=args.fit_backend,
                pyhf_backend=args.pyhf_backend,
            )
            result["fit_id"] = fit_id
            write_json(outputs / "fit" / fit_id / "results.json", result)

            signif = compute_discovery_significance(
                workspace_path,
                backend=args.fit_backend,
                pyhf_backend=args.pyhf_backend,
            )
            signif["fit_id"] = fit_id
            write_json(outputs / "fit" / fit_id / "significance.json", signif)
            primary_backend_name = str(args.fit_backend)

        if result.get("status") != "ok":
            raise RuntimeError(
                "primary fit failed for {} backend={}: {}".format(
                    fit_id,
                    primary_backend_name,
                    result.get("error", "unknown_error"),
                )
            )
        if signif.get("status") != "ok":
            raise RuntimeError(
                "primary significance failed for {} backend={}: {}".format(
                    fit_id,
                    primary_backend_name,
                    signif.get("error", "unknown_error"),
                )
            )

        pyhf_fit = None
        pyhf_sig = None
        if run_pyhf_crosscheck:
            pyhf_fit = run_fit(
                workspace_path,
                backend="pyhf",
                pyhf_backend=args.pyhf_backend,
            )
            pyhf_fit["fit_id"] = fit_id
            pyhf_fit["crosscheck"] = True
            pyhf_fit["crosscheck_label"] = "pyhf_template_crosscheck"
            write_json(outputs / "fit" / fit_id / "results_pyhf_crosscheck.json", pyhf_fit)

            pyhf_sig = compute_discovery_significance(
                workspace_path,
                backend="pyhf",
                pyhf_backend=args.pyhf_backend,
            )
            pyhf_sig["fit_id"] = fit_id
            pyhf_sig["crosscheck"] = True
            pyhf_sig["crosscheck_label"] = "pyhf_template_crosscheck"
            write_json(outputs / "fit" / fit_id / "significance_pyhf_crosscheck.json", pyhf_sig)

        write_json(
            outputs / "fit" / fit_id / "fit_backend.json",
            {
                "fit_id": fit_id,
                "primary_backend": primary_backend_name,
                "pyhf_backend_requested": str(args.pyhf_backend),
                "pyhf_backend_resolved": str(pyhf_backend_resolved),
                "stattool_available": bool(stattool_available),
                "stattool_availability_reason": str(stattool_reason),
                "workspace": str(workspace_path),
                "primary_fit_status": result.get("status", "unknown"),
                "primary_significance_status": signif.get("status", "unknown"),
                "roofit_combined_summary": (
                    str(outputs / "fit" / fit_id / "roofit_combined" / "summary.json")
                    if roofit_summary is not None
                    else None
                ),
                "cross_checks": {
                    "pyhf": {
                        "enabled": run_pyhf_crosscheck,
                        "fit_status": pyhf_fit.get("status", "not_run") if pyhf_fit else "not_run",
                        "significance_status": pyhf_sig.get("status", "not_run") if pyhf_sig else "not_run",
                    }
                },
            },
        )

    # Reuse plotting module CLI entry for consistency.
    import sys

    argv_backup = sys.argv[:]
    try:
        sys.argv = ["analysis.plotting.plots", "--outputs", str(outputs), "--registry", str(registry_path)]
        plotting_main()
    finally:
        sys.argv = argv_backup

    for fit_id in fit_ids:
        run_blinded_region_visualization(
            outputs=outputs,
            registry_path=registry_path,
            regions_path=regions_path,
            fit_id=fit_id,
            blind_sr=True,
        )
        if is_hgg:
            _assert_hgg_roofit_artifacts(
                outputs=outputs,
                fit_id=fit_id,
                fit_regions=_fit_regions_from_cfg(regions_cfg, fit_id),
            )

    report_path = outputs / "report" / "report.md"
    build_report(normalized_path, outputs, report_path)

    _visual_verification_check(outputs)

    run_manifest = {
        "selected_samples": [s["sample_id"] for s in selected],
        "max_events": args.max_events,
        "target_lumi_fb": float(args.target_lumi_fb),
        "event_backend_requested": str(args.event_backend),
        "event_backend_resolved": str(event_backend),
        "rootml_cache_dir": str(rootml_cache_dir),
        "fit_backend_primary": args.fit_backend,
        "pyhf_backend_requested": str(args.pyhf_backend),
        "pyhf_backend_resolved": str(pyhf_backend_resolved),
        "stattool_available": bool(stattool_available),
        "stattool_availability_reason": str(stattool_reason),
        "analysis_is_hgg": bool(is_hgg),
        "pyhf_crosscheck_enabled": bool(run_pyhf_crosscheck),
        "meta": run_metadata(summary_path, regions_path, systematics_path),
    }
    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    write_json(outputs / "runs" / run_id / "run_manifest.json", run_manifest)

    print("pipeline completed")
    print("selected_samples={}".format(",".join(run_manifest["selected_samples"])))
    print("workspace_channels={}".format(len(workspace.get("channels", []))))



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diphoton analysis pipeline CLI")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="Run end-to-end pipeline")
    run.add_argument("--summary", required=True)
    run.add_argument("--categories", default="analysis/categories.yaml")
    run.add_argument("--inputs", required=True)
    run.add_argument("--outputs", required=True)
    run.add_argument("--max-events", type=int, default=None)
    run.add_argument("--samples", nargs="*", default=[])
    run.add_argument("--all-samples", action="store_true")
    run.add_argument("--fit-backend", default="pyroot_roofit", choices=["pyhf", "pyroot_roofit"])
    run.add_argument(
        "--no-pyhf-crosscheck",
        action="store_true",
        help="Disable optional pyhf cross-check artifacts.",
    )
    run.add_argument(
        "--target-lumi-fb",
        type=float,
        default=36.1,
        help="Integrated luminosity in fb^-1 used for MC normalization.",
    )
    run.add_argument(
        "--event-backend",
        default="native",
        choices=["native", "rootmltool", "auto"],
        help="Event I/O backend. Default keeps native path; 'auto' prefers rootmltool when available.",
    )
    run.add_argument(
        "--no-rootml-cache-reuse",
        action="store_true",
        help="Force regeneration of rootmltool JSON cache artifacts.",
    )
    run.add_argument(
        "--pyhf-backend",
        default="native",
        choices=["native", "stattool", "auto"],
        help="PyHF implementation backend (additive). Default keeps native path.",
    )

    parity = sub.add_parser(
        "parity-check",
        help="Compare two outputs directories for yields/hist parity.",
    )
    parity.add_argument("--baseline", required=True)
    parity.add_argument("--candidate", required=True)
    parity.add_argument("--abs-tol", type=float, default=1e-6)
    parity.add_argument("--rel-tol", type=float, default=1e-3)
    parity.add_argument("--out", default=None)
    parity.add_argument("--fail-on-mismatch", action="store_true")

    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run":
        run_pipeline(args)
        return
    if args.command == "parity-check":
        _run_parity_check_command(args)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
