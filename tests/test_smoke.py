from pathlib import Path

import pytest

from analysis.cli import (
    _assert_hgg_roofit_artifacts,
    _enforce_backend_policy,
    _fit_regions_from_cfg,
    _is_hgg_analysis,
    build_parser,
)
from analysis.config.load_summary import load_and_validate


def test_cli_parser_has_run():
    parser = build_parser()
    args = parser.parse_args(["run", "--summary", "a.json", "--inputs", "in", "--outputs", "out"])
    assert args.command == "run"
    assert args.fit_backend == "pyroot_roofit"
    assert args.pyhf_backend == "native"


def test_summary_validation_structure():
    summary_path = Path("analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json")
    normalized = load_and_validate(summary_path)
    assert "_inventory" in normalized
    assert normalized["_inventory"]["n_signal_regions"] >= 1


def test_hgg_backend_policy_requires_roofit():
    summary_path = Path("analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json")
    normalized = load_and_validate(summary_path)
    assert _is_hgg_analysis(normalized) is True

    with pytest.raises(RuntimeError):
        _enforce_backend_policy(normalized, "pyhf")

    _enforce_backend_policy(normalized, "pyroot_roofit")


def test_hgg_roofit_artifact_gate(tmp_path: Path):
    outputs = tmp_path / "outputs"
    fit_id = "FIT_MAIN"
    fit_regions = ["SR_A", "SR_B"]

    roofit_dir = outputs / "fit" / fit_id / "roofit_combined"
    (outputs / "report" / "plots").mkdir(parents=True, exist_ok=True)
    roofit_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "significance.json",
        "signal_dscb_parameters.json",
        "sideband_fit_parameters.json",
        "cutflow_mass_window_125pm2.json",
    ]:
        (roofit_dir / name).write_text("{}")
    for rid in fit_regions:
        (outputs / "report" / "plots" / "roofit_combined_mgg_{}.png".format(rid)).write_text("x")

    _assert_hgg_roofit_artifacts(outputs=outputs, fit_id=fit_id, fit_regions=fit_regions)

    (outputs / "report" / "plots" / "roofit_combined_mgg_SR_B.png").unlink()
    with pytest.raises(RuntimeError):
        _assert_hgg_roofit_artifacts(outputs=outputs, fit_id=fit_id, fit_regions=fit_regions)


def test_fit_regions_from_cfg():
    cfg = {
        "fits": [
            {"fit_id": "FIT1", "regions_included": ["A", "B"]},
            {"fit_id": "FIT2", "regions_included": ["C"]},
        ]
    }
    assert _fit_regions_from_cfg(cfg, "FIT1") == ["A", "B"]
    assert _fit_regions_from_cfg(cfg, "FITX") == []
