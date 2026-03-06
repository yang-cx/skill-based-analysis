import json
from pathlib import Path

import numpy as np

from analysis.common import write_json
from analysis.plotting.blinded_regions import run_blinded_region_visualization


def _write_npz(path: Path, edges: np.ndarray, counts: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        edges=np.asarray(edges, dtype=float),
        counts=np.asarray(counts, dtype=float),
        sumw2=np.asarray(counts, dtype=float),
        metadata=json.dumps({"note": "test"}),
    )


def test_blinded_region_outputs_include_prefit_postfit(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    registry_path = outputs / "samples.registry.json"
    regions_path = tmp_path / "regions.yaml"
    fit_id = "FIT_TEST"

    write_json(
        registry_path,
        {
            "samples": [
                {"sample_id": "data", "sample_name": "data", "kind": "data"},
                {"sample_id": "bkg", "sample_name": "bkg", "kind": "background"},
                {"sample_id": "sig", "sample_name": "sig", "kind": "signal"},
            ]
        },
    )
    regions_path.write_text(
        "\n".join(
            [
                "regions:",
                "  - region_id: CR_TEST",
                "    kind: control",
                "  - region_id: SR_TEST",
                "    kind: signal",
                "",
            ]
        )
    )
    write_json(outputs / "fit" / fit_id / "results.json", {"bestfit_poi": 1.0})

    edges = np.array([105.0, 120.0, 130.0, 160.0], dtype=float)
    _write_npz(
        outputs / "hists" / "CR_TEST" / "m_gg" / "data.npz",
        edges,
        np.array([100.0, 40.0, 90.0], dtype=float),
    )
    _write_npz(
        outputs / "hists" / "CR_TEST" / "m_gg" / "bkg.npz",
        edges,
        np.array([95.0, 35.0, 80.0], dtype=float),
    )
    _write_npz(
        outputs / "hists" / "CR_TEST" / "m_gg" / "sig.npz",
        edges,
        np.array([2.0, 5.0, 2.0], dtype=float),
    )
    _write_npz(
        outputs / "hists" / "SR_TEST" / "m_gg" / "data.npz",
        edges,
        np.array([20.0, 10.0, 20.0], dtype=float),
    )
    _write_npz(
        outputs / "hists" / "SR_TEST" / "m_gg" / "bkg.npz",
        edges,
        np.array([18.0, 8.0, 16.0], dtype=float),
    )
    _write_npz(
        outputs / "hists" / "SR_TEST" / "m_gg" / "sig.npz",
        edges,
        np.array([1.0, 3.0, 1.0], dtype=float),
    )

    summary = run_blinded_region_visualization(
        outputs=outputs,
        registry_path=registry_path,
        regions_path=regions_path,
        fit_id=fit_id,
        blind_sr=True,
    )

    cr = summary["regions"]["CR_TEST"]
    sr = summary["regions"]["SR_TEST"]

    assert cr["data_shown"] is True
    assert sr["data_shown"] is False

    assert cr["prefit_plot"] is not None
    assert cr["postfit_plot"] is not None
    assert sr["prefit_plot"] is None
    assert sr["postfit_plot"] is None

    assert Path(cr["plot"]).exists()
    assert Path(cr["prefit_plot"]).exists()
    assert Path(cr["postfit_plot"]).exists()
    assert Path(sr["plot"]).exists()
    assert (outputs / "report" / "blinding_overlap_audit.json").exists()

