from pathlib import Path

from analysis.stats.fit import build_parser, run_fit


def test_fit_parser():
    parser = build_parser()
    args = parser.parse_args(
        [
            "--workspace",
            "w.json",
            "--fit-id",
            "FIT1",
            "--out",
            "o.json",
        ]
    )
    assert args.fit_id == "FIT1"
    assert args.backend == "pyhf"
    assert args.pyhf_backend == "native"


def test_run_fit_uses_stattool_backend_when_resolved(monkeypatch):
    monkeypatch.setattr("analysis.stats.fit.resolve_pyhf_backend", lambda _b: "stattool")
    monkeypatch.setattr(
        "analysis.stats.fit.run_stattool_fit",
        lambda workspace_path, poi_name="mu": {
            "status": "ok",
            "backend": "pyhf",
            "pyhf_backend": "stattool",
            "poi_name": poi_name,
            "bestfit_poi": 1.2,
            "bestfit_all": [1.2],
            "twice_nll": 10.0,
            "n_pars": 1,
        },
    )

    result = run_fit(Path("workspace.json"), backend="pyhf", pyhf_backend="auto")
    assert result["status"] == "ok"
    assert result["pyhf_backend"] == "stattool"


def test_run_fit_uses_native_backend_when_resolved(monkeypatch):
    monkeypatch.setattr("analysis.stats.fit.resolve_pyhf_backend", lambda _b: "native")
    monkeypatch.setattr(
        "analysis.stats.fit._run_pyhf_fit_native",
        lambda _workspace: {
            "status": "ok",
            "backend": "pyhf",
            "pyhf_backend": "native",
            "poi_name": "mu",
            "bestfit_poi": 1.0,
            "bestfit_all": [1.0],
            "twice_nll": 8.0,
            "n_pars": 1,
        },
    )

    result = run_fit(Path("workspace.json"), backend="pyhf", pyhf_backend="auto")
    assert result["status"] == "ok"
    assert result["pyhf_backend"] == "native"
