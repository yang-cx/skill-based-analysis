from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from analysis.common import read_json


def _import_root() -> Any:
    try:
        import ROOT  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "PyROOT/RooFit is unavailable in this environment. "
            "Install ROOT with PyROOT bindings to use backend=pyroot_roofit."
        ) from exc
    ROOT.gROOT.SetBatch(True)
    return ROOT


def _extract_workspace_templates(workspace_path: Path) -> Dict[str, Any]:
    ws_spec = read_json(workspace_path)
    channels = ws_spec.get("channels", [])
    observations = {str(obs.get("name", "")): obs for obs in ws_spec.get("observations", [])}

    signal_parts: List[np.ndarray] = []
    background_parts: List[np.ndarray] = []
    data_parts: List[np.ndarray] = []
    bins_per_channel: List[int] = []
    channel_order: List[str] = []

    for channel in channels:
        channel_name = str(channel.get("name", ""))
        if not channel_name:
            continue
        obs = observations.get(channel_name)
        if obs is None:
            continue

        data = np.asarray(obs.get("data", []), dtype=float)
        if data.size == 0:
            continue

        sig = np.zeros_like(data, dtype=float)
        bkg = np.zeros_like(data, dtype=float)
        samples = channel.get("samples", [])
        for sample in samples:
            values = np.asarray(sample.get("data", []), dtype=float)
            if values.shape != data.shape:
                raise ValueError(
                    "Workspace channel '{}' has inconsistent sample/data bin counts".format(channel_name)
                )
            sample_name = str(sample.get("name", "")).lower()
            if sample_name == "signal":
                sig += values
                continue
            if sample_name == "background":
                bkg += values
                continue

            # Fallback classification for non-canonical sample names.
            modifier_names = [str(mod.get("name", "")).lower() for mod in sample.get("modifiers", [])]
            if "mu" in modifier_names:
                sig += values
            else:
                bkg += values

        signal_parts.append(np.clip(sig, 0.0, None))
        background_parts.append(np.clip(bkg, 0.0, None))
        data_parts.append(np.clip(data, 0.0, None))
        bins_per_channel.append(int(data.size))
        channel_order.append(channel_name)

    if not data_parts:
        raise ValueError("Workspace contains no usable channels/observations for RooFit backend")

    signal = np.concatenate(signal_parts)
    background = np.concatenate(background_parts)
    data = np.concatenate(data_parts)

    return {
        "signal": np.clip(signal, 0.0, None),
        "background": np.clip(background, 0.0, None),
        "data": np.clip(data, 0.0, None),
        "channel_order": channel_order,
        "bins_per_channel": bins_per_channel,
        "n_channels": len(channel_order),
        "n_bins_total": int(data.size),
    }


def _to_roo_data_hist(ROOT: Any, name: str, obs: Any, values: np.ndarray) -> Dict[str, Any]:
    n_bins = int(values.size)
    hist = ROOT.TH1D(name, name, n_bins, 0.5, float(n_bins) + 0.5)
    for idx, value in enumerate(values, start=1):
        hist.SetBinContent(idx, float(max(value, 0.0)))
    data_hist = ROOT.RooDataHist(
        "{}_dh".format(name),
        "{}_dh".format(name),
        ROOT.RooArgList(obs),
        hist,
    )
    return {"th1": hist, "datahist": data_hist}


def _build_roofit_context(workspace_path: Path) -> Dict[str, Any]:
    ROOT = _import_root()
    templates = _extract_workspace_templates(workspace_path)

    signal = templates["signal"]
    background = templates["background"]
    data = templates["data"]

    if float(np.sum(signal)) <= 0.0:
        raise ValueError("RooFit backend requires non-zero signal template integral")
    if float(np.sum(background)) <= 0.0:
        raise ValueError("RooFit backend requires non-zero background template integral")

    n_bins = int(templates["n_bins_total"])
    obs = ROOT.RooRealVar("template_bin", "template_bin", 0.5, float(n_bins) + 0.5)
    obs.setBins(n_bins)

    h_data = _to_roo_data_hist(ROOT, "data", obs, data)
    h_sig = _to_roo_data_hist(ROOT, "signal", obs, signal)
    h_bkg = _to_roo_data_hist(ROOT, "background", obs, background)

    pdf_signal = ROOT.RooHistPdf(
        "pdf_signal",
        "pdf_signal",
        ROOT.RooArgSet(obs),
        h_sig["datahist"],
    )
    pdf_background = ROOT.RooHistPdf(
        "pdf_background",
        "pdf_background",
        ROOT.RooArgSet(obs),
        h_bkg["datahist"],
    )

    total_signal_nominal = float(np.sum(signal))
    total_data = float(np.sum(data))
    total_background_nominal = float(np.sum(background))

    mu_max = max(10.0, 5.0 * total_data / max(total_signal_nominal, 1e-9))
    mu = ROOT.RooRealVar("mu", "mu", 1.0, 0.0, float(mu_max))
    n_sig_nominal = ROOT.RooConstVar("n_sig_nominal", "n_sig_nominal", float(total_signal_nominal))
    n_sig = ROOT.RooFormulaVar("n_sig", "@0*@1", ROOT.RooArgList(mu, n_sig_nominal))

    n_bkg_init = max(float(total_background_nominal), 1e-6)
    n_bkg_max = max(5.0 * total_data + 5.0 * n_bkg_init, 1e3)
    n_bkg = ROOT.RooRealVar("n_bkg", "n_bkg", n_bkg_init, 0.0, float(n_bkg_max))

    model = ROOT.RooAddPdf(
        "model",
        "model",
        ROOT.RooArgList(pdf_signal, pdf_background),
        ROOT.RooArgList(n_sig, n_bkg),
    )

    return {
        "ROOT": ROOT,
        "templates": templates,
        "obs": obs,
        "datahist": h_data["datahist"],
        "mu": mu,
        "n_bkg": n_bkg,
        "model": model,
        # Keep these alive for RooFit object ownership stability.
        "keepalive": [h_data, h_sig, h_bkg, pdf_signal, pdf_background, n_sig_nominal, n_sig],
    }


def _fit_extended_model(context: Dict[str, Any]) -> Any:
    ROOT = context["ROOT"]
    fit_result = context["model"].fitTo(
        context["datahist"],
        ROOT.RooFit.Extended(True),
        ROOT.RooFit.Save(True),
        ROOT.RooFit.PrintLevel(-1),
        ROOT.RooFit.Strategy(1),
    )
    return fit_result


def run_roofit_fit(workspace_path: Path) -> Dict[str, Any]:
    try:
        ctx = _build_roofit_context(workspace_path)
        fit_result = _fit_extended_model(ctx)

        status_code = int(fit_result.status())
        cov_qual = int(fit_result.covQual())
        mu_hat = float(ctx["mu"].getVal())
        mu_err = float(ctx["mu"].getError())
        n_bkg_hat = float(ctx["n_bkg"].getVal())
        n_bkg_err = float(ctx["n_bkg"].getError())
        twice_nll = float(2.0 * fit_result.minNll())

        status = "ok" if status_code == 0 else "failed"
        payload = {
            "status": status,
            "poi_name": "mu",
            "bestfit_poi": mu_hat,
            "poi_uncertainty": mu_err,
            "bestfit_all": [mu_hat, n_bkg_hat],
            "bestfit_errors": [mu_err, n_bkg_err],
            "bestfit_labels": ["mu", "n_bkg"],
            "twice_nll": twice_nll,
            "n_pars": 2,
            "backend": "pyroot_roofit",
            "backend_status_code": status_code,
            "backend_cov_qual": cov_qual,
            "fit_method": (
                "RooFit extended binned likelihood over pyhf workspace templates "
                "(all channels flattened into a combined binned observable)."
            ),
            "workspace_summary": {
                "n_channels": int(ctx["templates"]["n_channels"]),
                "n_bins_total": int(ctx["templates"]["n_bins_total"]),
                "bins_per_channel": list(ctx["templates"]["bins_per_channel"]),
                "channel_order": list(ctx["templates"]["channel_order"]),
            },
        }
        if status != "ok":
            payload["error"] = "RooFit fit returned non-zero status {}".format(status_code)
        return payload
    except Exception as exc:
        return {
            "status": "failed",
            "poi_name": "mu",
            "bestfit_poi": 1.0,
            "bestfit_all": [],
            "twice_nll": None,
            "n_pars": 2,
            "backend": "pyroot_roofit",
            "error": str(exc),
        }


def run_roofit_significance(workspace_path: Path) -> Dict[str, Any]:
    try:
        ctx = _build_roofit_context(workspace_path)

        fit_free = _fit_extended_model(ctx)
        free_status = int(fit_free.status())
        mu_hat = float(ctx["mu"].getVal())
        twice_nll_free = float(2.0 * fit_free.minNll())

        ctx["mu"].setVal(0.0)
        ctx["mu"].setConstant(True)
        fit_mu0 = _fit_extended_model(ctx)
        mu0_status = int(fit_mu0.status())
        twice_nll_mu0 = float(2.0 * fit_mu0.minNll())

        q0_raw = float(twice_nll_mu0 - twice_nll_free)
        q0 = max(q0_raw, 0.0)
        z = float(np.sqrt(q0))

        status_ok = (free_status == 0) and (mu0_status == 0)
        payload = {
            "status": "ok" if status_ok else "failed",
            "poi_name": "mu",
            "mu_hat": mu_hat,
            "twice_nll_free": twice_nll_free,
            "twice_nll_mu0": twice_nll_mu0,
            "q0": q0,
            "z_discovery": z,
            "backend": "pyroot_roofit",
            "backend_status_code_free": free_status,
            "backend_status_code_mu0": mu0_status,
            "note": "Asymptotic profile-likelihood approximation (one-sided).",
        }
        if not status_ok:
            payload["error"] = "RooFit status free={} mu0={}".format(free_status, mu0_status)
        return payload
    except Exception as exc:
        return {
            "status": "failed",
            "poi_name": "mu",
            "error": str(exc),
            "mu_hat": None,
            "twice_nll_free": None,
            "twice_nll_mu0": None,
            "q0": None,
            "z_discovery": None,
            "backend": "pyroot_roofit",
        }
