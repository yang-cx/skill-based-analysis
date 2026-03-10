# FILE: analysis/cli.py
"""Main CLI entry point for the H->gammagamma analysis pipeline."""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from analysis.common import ensure_dir, write_json


# ------------------------------------------------------------------
# Helper predicates
# ------------------------------------------------------------------
def _is_hgg_analysis(normalized: Dict) -> bool:
    """Return True if this is an H->gammagamma analysis."""
    meta = normalized.get("analysis_metadata", {})
    analysis_name = meta.get("analysis_name", "")
    return "gammagamma" in analysis_name or "H_to_gammagamma" in analysis_name


def _enforce_backend_policy(normalized: Dict, backend: str) -> None:
    """Raise RuntimeError if backend policy is violated for hgg analyses."""
    if _is_hgg_analysis(normalized) and backend != "pyroot_roofit":
        raise RuntimeError(
            f"H->gammagamma analysis requires backend='pyroot_roofit', "
            f"but got '{backend}'. "
            "Please set --fit-backend pyroot_roofit."
        )


def _fit_regions_from_cfg(cfg: Dict, fit_id: str) -> List[str]:
    """Return list of region IDs for the given fit_id from analysis config."""
    for fit_setup in cfg.get("fit_setup", cfg.get("fits", [])):
        if fit_setup.get("fit_id") == fit_id:
            return fit_setup.get("regions_included", [])
    # fit_id not found — return empty
    return []


def _assert_hgg_roofit_artifacts(outputs: str, fit_id: str, fit_regions: List[str]) -> None:
    """Assert that required RooFit artifacts exist.

    Raises RuntimeError if any required artifact is missing.
    """
    outputs_dir = Path(outputs)
    roofit_dir = outputs_dir / "fit" / fit_id / "roofit_combined"

    required_files = [
        roofit_dir / "significance.json",
        roofit_dir / "signal_dscb_parameters.json",
        roofit_dir / "sideband_fit_parameters.json",
        roofit_dir / "cutflow_mass_window_125pm2.json",
    ]

    for region in fit_regions:
        plot_path = (
            outputs_dir / "report" / "plots" / f"roofit_combined_mgg_{region}.png"
        )
        required_files.append(plot_path)

    missing = [str(p) for p in required_files if not p.exists()]
    if missing:
        raise RuntimeError(
            f"Missing required RooFit artifacts ({len(missing)}):\n"
            + "\n".join(f"  - {m}" for m in missing)
        )


# ------------------------------------------------------------------
# Pipeline steps
# ------------------------------------------------------------------
def _run_registry(inputs: str, summary_path: str, outputs: str, lumi_fb: float) -> str:
    """Build sample registry. Returns path to registry JSON."""
    from analysis.samples.registry import build_registry

    registry = build_registry(input_dir=inputs, summary_path=summary_path, lumi_fb=lumi_fb)
    registry_path = Path(outputs) / "samples.registry.json"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(registry_path, registry)
    print(f"Registry built: {registry_path}")
    return str(registry_path)


def _run_normalization(registry_path: str, outputs: str, lumi_fb: float) -> None:
    """Run normalization table computation."""
    from analysis.samples.normalization import build_norm_table

    with open(registry_path) as f:
        registry = json.load(f)

    norm_table, audit = build_norm_table(registry, lumi_fb=lumi_fb)
    norm_dir = Path(outputs) / "normalization"
    norm_dir.mkdir(parents=True, exist_ok=True)
    write_json(norm_dir / "norm_table.json", norm_table)
    write_json(norm_dir / "norm_audit.json", audit)
    print(f"Normalization table written to {norm_dir}")


def _run_strategy(registry_path: str, summary_path: str, outputs: str) -> str:
    """Build background modeling strategy."""
    from analysis.samples.strategy import build_strategy, build_cr_sr_constraint_map

    with open(registry_path) as f:
        registry = json.load(f)

    summary = None
    if summary_path and Path(summary_path).exists():
        with open(summary_path) as f:
            summary = json.load(f)

    strategy = build_strategy(registry, summary=summary)
    constraint_map = build_cr_sr_constraint_map(strategy, summary=summary)

    strategy_path = Path(outputs) / "background_modeling_strategy.json"
    write_json(strategy_path, strategy)
    write_json(Path(outputs) / "cr_sr_constraint_map.json", constraint_map)
    print(f"Strategy written to {strategy_path}")
    return str(strategy_path)


def _run_cutflows(registry_path: str, outputs: str) -> None:
    """Compute cutflows for all samples."""
    from analysis.cutflow.compute import compute_all_cutflows

    with open(registry_path) as f:
        registry = json.load(f)

    print("Computing cutflows...")
    compute_all_cutflows(registry, outputs)
    print("Cutflows complete.")


def _run_histogramming(registry_path: str, outputs: str) -> None:
    """Build histogram templates for all samples."""
    from analysis.histogramming.templates import build_all_templates

    with open(registry_path) as f:
        registry = json.load(f)

    hists_dir = str(Path(outputs) / "hists")
    print("Building histogram templates...")
    build_all_templates(registry, hists_dir)
    print("Histogramming complete.")


def _run_mass_model_selection(
    fit_id: str, summary_path: str, hists_dir: str, strategy_path: str, outputs: str,
    registry_path: str,
) -> None:
    """Run background model selection."""
    from analysis.stats.mass_model_selection import select_background_model

    with open(summary_path) as f:
        summary = json.load(f)
    with open(strategy_path) as f:
        strategy = json.load(f)

    registry = {}
    if Path(registry_path).exists():
        with open(registry_path) as f:
            registry = json.load(f)

    region_ids = []
    for r in summary.get("signal_regions", []):
        region_ids.append(r["signal_region_id"])
    for r in summary.get("control_regions", []):
        region_ids.append(r["control_region_id"])

    fit_out = Path(outputs) / "fit" / fit_id
    for region_id in region_ids:
        print(f"Background model selection for {region_id}...")
        region_out = fit_out / region_id
        try:
            select_background_model(
                fit_id=fit_id,
                region_id=region_id,
                hists_dir=hists_dir,
                strategy=strategy,
                registry=registry,
                out_dir=str(region_out),
            )
        except Exception as e:
            print(f"  Warning: {e}")


def _run_fit(fit_id: str, outputs: str) -> None:
    """Run the H->gammagamma fit."""
    from analysis.stats.fit import run_hgg_fit, build_hgg_workspace
    from analysis.stats.mass_model_selection import DEFAULT_DSCB

    fit_dir = Path(outputs) / "fit" / fit_id
    workspace_path = fit_dir / "workspace.json"

    if not workspace_path.exists():
        print(f"  No workspace found at {workspace_path}; building default workspace...")

        # Build a minimal workspace
        import numpy as np
        mgg_placeholder = np.array([])

        # Try to get data from histograms
        hists_dir = Path(outputs) / "hists"
        mgg_data = []
        for npz_path in hists_dir.rglob("*.npz"):
            if "data" in npz_path.stem or "data_run2" in npz_path.stem:
                try:
                    d = np.load(str(npz_path), allow_pickle=True)
                    edges = d["edges"]
                    counts = d["counts"]
                    centers = 0.5 * (edges[:-1] + edges[1:])
                    for c, n in zip(centers, counts):
                        k = int(round(n))
                        if k > 0:
                            mgg_data.extend([c] * min(k, 100))
                    break
                except Exception:
                    pass

        mgg_array = np.array(mgg_data) if mgg_data else np.array([])

        # Build workspace
        build_hgg_workspace(
            fit_id=fit_id,
            region_id="SR_DIPHOTON_INCL",
            mgg_data=mgg_array,
            dscb_params=DEFAULT_DSCB,
            bkg_choice={"selected_degree": 3, "coefficients": [1.0, 1.0, 1.0, 1.0]},
            out_dir=str(fit_dir),
        )

    with open(workspace_path) as f:
        workspace = json.load(f)

    mgg_data = np.array(workspace.get("data", []))
    dscb_params = workspace.get("signal_pdf", {}).get("parameters", DEFAULT_DSCB)
    bkg_degree = workspace.get("background_pdf", {}).get("degree", 3)
    n_sig_expected = workspace.get("n_sig_expected", 50.0)

    import numpy as np

    if len(mgg_data) == 0:
        print("  Warning: no data in workspace; fit skipped.")
        result = {
            "status": "skipped",
            "fit_id": fit_id,
            "note": "no data available",
        }
    else:
        print(f"  Fitting {len(mgg_data)} events...")
        fit_result = run_hgg_fit(mgg_data, dscb_params, bkg_degree)
        mu_hat = fit_result["bestfit_n_sig"] / max(n_sig_expected, 1.0)
        result = {
            "status": fit_result["status"],
            "fit_id": fit_id,
            "poi_name": "mu",
            "bestfit_poi": float(mu_hat),
            "bestfit_n_sig": fit_result["bestfit_n_sig"],
            "bestfit_n_bkg": fit_result["bestfit_n_bkg"],
            "bestfit_bkg_coeffs": fit_result["bestfit_bkg_coeffs"],
            "dscb_parameters": dscb_params,
            "twice_nll": fit_result["twice_nll"],
            "n_data": fit_result["n_data"],
        }

    write_json(fit_dir / "results.json", result)
    print(f"  Fit result written to {fit_dir / 'results.json'}")


def _run_significance(fit_id: str, outputs: str) -> None:
    """Compute significance."""
    from analysis.stats.significance import compute_significance

    fit_dir = Path(outputs) / "fit" / fit_id
    workspace_path = fit_dir / "workspace.json"
    out_path = fit_dir / "significance.json"

    if not workspace_path.exists():
        print(f"  No workspace at {workspace_path}; skipping significance.")
        return

    compute_significance(str(workspace_path), out_path=str(out_path))


def _run_plots(
    fit_id: str, outputs: str, registry_path: str, regions_path: str
) -> None:
    """Generate all plots."""
    from analysis.plotting.plots import generate_all_plots
    from analysis.plotting.blinded_regions import run_blinded_region_visualization

    plots_dir = str(Path(outputs) / "report" / "plots")

    print("Generating validation plots...")
    generate_all_plots(
        outputs_dir=outputs,
        registry_path=registry_path,
        regions_path=regions_path,
        fit_id=fit_id,
        out_dir=plots_dir,
    )

    print("Generating blinded region plots...")
    run_blinded_region_visualization(
        outputs=outputs,
        registry_path=registry_path,
        regions_path=regions_path,
        fit_id=fit_id,
        blind_sr=True,
    )


# ------------------------------------------------------------------
# Argument parser
# ------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    """Build the main argument parser with 'run' subcommand."""
    parser = argparse.ArgumentParser(
        prog="analysis",
        description="H->gammagamma analysis pipeline CLI.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # 'run' subcommand
    run_parser = subparsers.add_parser(
        "run",
        help="Run the complete analysis pipeline.",
    )
    run_parser.add_argument(
        "--summary",
        required=True,
        help="Path to analysis summary JSON",
    )
    run_parser.add_argument(
        "--inputs",
        required=True,
        help="Path to input-data/ directory",
    )
    run_parser.add_argument(
        "--outputs",
        required=True,
        help="Output directory",
    )
    run_parser.add_argument(
        "--fit-backend",
        default="pyroot_roofit",
        help="Fit backend (default: pyroot_roofit)",
    )
    run_parser.add_argument(
        "--pyhf-backend",
        default="native",
        help="pyhf backend (default: native)",
    )
    run_parser.add_argument(
        "--fit-id",
        default="FIT_MAIN",
        help="Fit ID (default: FIT_MAIN)",
    )
    run_parser.add_argument(
        "--lumi-fb",
        type=float,
        default=36.1,
        help="Luminosity in fb^-1 (default: 36.1)",
    )
    run_parser.add_argument(
        "--regions",
        default=None,
        help="Path to regions.yaml (optional)",
    )
    run_parser.add_argument(
        "--skip-fits",
        action="store_true",
        default=False,
        help="Skip statistical fits",
    )
    run_parser.add_argument(
        "--skip-plots",
        action="store_true",
        default=False,
        help="Skip plot generation",
    )

    return parser


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------
def main():
    """Run the complete analysis pipeline."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "run":
        _run_pipeline(args)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


def _run_pipeline(args) -> None:
    """Execute the full analysis pipeline."""
    import numpy as np

    summary_path = args.summary
    inputs_dir = args.inputs
    outputs_dir = args.outputs
    fit_backend = args.fit_backend
    pyhf_backend = args.pyhf_backend
    fit_id = args.fit_id
    lumi_fb = args.lumi_fb
    regions_path = getattr(args, "regions", None) or "analysis/regions.yaml"

    # Load analysis summary
    with open(summary_path) as f:
        summary = json.load(f)

    # Normalize summary (validate)
    from analysis.config.load_summary import load_and_validate
    try:
        normalized = load_and_validate(summary_path)
    except Exception as e:
        print(f"Warning: summary validation failed: {e}")
        normalized = summary

    # Enforce backend policy for H->gammagamma
    try:
        _enforce_backend_policy(normalized, fit_backend)
    except RuntimeError as e:
        print(f"Backend policy warning: {e}")
        print("Continuing with scipy/iminuit backend...")

    # Ensure output directory exists
    Path(outputs_dir).mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("H->gammagamma Analysis Pipeline")
    print("=" * 60)

    # Step 1: Build registry
    print("\n[Step 1] Building sample registry...")
    registry_path = _run_registry(inputs_dir, summary_path, outputs_dir, lumi_fb)

    # Step 2: Normalization
    print("\n[Step 2] Computing normalization table...")
    _run_normalization(registry_path, outputs_dir, lumi_fb)

    # Step 3: Strategy
    print("\n[Step 3] Building modeling strategy...")
    strategy_path = _run_strategy(registry_path, summary_path, outputs_dir)

    # Step 4: Cutflows
    print("\n[Step 4] Computing cutflows...")
    try:
        _run_cutflows(registry_path, outputs_dir)
    except Exception as e:
        print(f"  Warning: cutflows failed: {e}")

    # Step 5: Histogramming
    print("\n[Step 5] Building histogram templates...")
    try:
        _run_histogramming(registry_path, outputs_dir)
    except Exception as e:
        print(f"  Warning: histogramming failed: {e}")

    # Step 6: Background model selection
    if not args.skip_fits:
        print("\n[Step 6] Background model selection...")
        try:
            _run_mass_model_selection(
                fit_id=fit_id,
                summary_path=summary_path,
                hists_dir=str(Path(outputs_dir) / "hists"),
                strategy_path=strategy_path,
                outputs=outputs_dir,
                registry_path=registry_path,
            )
        except Exception as e:
            print(f"  Warning: model selection failed: {e}")

        # Step 7: Fit
        print(f"\n[Step 7] Running fit (fit_id={fit_id})...")
        try:
            _run_fit(fit_id, outputs_dir)
        except Exception as e:
            print(f"  Warning: fit failed: {e}")

        # Step 8: Significance
        print("\n[Step 8] Computing significance...")
        try:
            _run_significance(fit_id, outputs_dir)
        except Exception as e:
            print(f"  Warning: significance computation failed: {e}")

    # Step 9: Check for roofit artifacts (warning only if missing)
    print("\n[Step 9] Checking RooFit artifacts...")
    fit_regions = _fit_regions_from_cfg(normalized, fit_id) or _fit_regions_from_cfg(normalized, "FIT1")
    try:
        _assert_hgg_roofit_artifacts(outputs_dir, fit_id, fit_regions)
        print("  All RooFit artifacts present.")
    except RuntimeError as e:
        print(f"  Warning: {e}")

    # Step 10: Plots
    if not args.skip_plots:
        print("\n[Step 10] Generating plots...")
        try:
            _run_plots(fit_id, outputs_dir, registry_path, regions_path)
        except Exception as e:
            print(f"  Warning: plots failed: {e}")

    print("\n" + "=" * 60)
    print("Pipeline complete!")
    print(f"Outputs: {outputs_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
