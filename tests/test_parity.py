import numpy as np

from analysis.common import ensure_dir, write_json
from analysis.validation.parity import run_parity_check


def _write_min_outputs(root, sample_id="s1", yield_value=10.0, hist_scale=1.0):
    out = ensure_dir(root)
    ensure_dir(out / "yields")
    ensure_dir(out / "hists" / "SR" / "m_gg")

    write_json(
        out / "yields" / "{}.json".format(sample_id),
        {
            "sample_id": sample_id,
            "regions": {
                "SR": {
                    "n_raw": 5.0,
                    "yield": float(yield_value),
                    "sumw2": 2.5,
                }
            },
        },
    )
    np.savez(
        out / "hists" / "SR" / "m_gg" / "{}.npz".format(sample_id),
        edges=np.array([0.0, 1.0, 2.0]),
        counts=np.array([1.0, 2.0]) * float(hist_scale),
        sumw2=np.array([1.0, 2.0]),
        metadata='{"region":"SR","observable":"m_gg"}',
    )
    return out


def test_parity_check_pass(tmp_path):
    baseline = _write_min_outputs(tmp_path / "baseline")
    candidate = _write_min_outputs(tmp_path / "candidate")

    report = run_parity_check(
        baseline_outputs=baseline,
        candidate_outputs=candidate,
        abs_tol=1e-9,
        rel_tol=1e-6,
    )
    assert report["status"] == "pass"
    assert report["counts"]["failed_metrics"] == 0
    assert report["counts"]["missing_in_candidate"] == 0
    assert report["counts"]["extra_in_candidate"] == 0


def test_parity_check_fail_on_drift(tmp_path):
    baseline = _write_min_outputs(tmp_path / "baseline", yield_value=10.0, hist_scale=1.0)
    candidate = _write_min_outputs(tmp_path / "candidate", yield_value=30.0, hist_scale=3.0)

    report = run_parity_check(
        baseline_outputs=baseline,
        candidate_outputs=candidate,
        abs_tol=1e-9,
        rel_tol=1e-9,
    )
    assert report["status"] == "fail"
    assert report["counts"]["failed_metrics"] > 0
