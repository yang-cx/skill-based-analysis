import argparse
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import yaml

from analysis.common import ensure_dir, read_json, write_json


def _import_root() -> Any:
    try:
        import ROOT  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on site env
        raise RuntimeError(
            "PyROOT is not available in this environment. "
            "Source an LCG/ROOT setup before running this command."
        ) from exc
    ROOT.gROOT.SetBatch(True)
    return ROOT


def _fit_regions(regions_path: Path, fit_id: str) -> List[str]:
    with regions_path.open() as handle:
        payload = yaml.safe_load(handle)
    for fit in payload.get("fits", []):
        if not isinstance(fit, dict):
            continue
        if str(fit.get("fit_id", "")) != str(fit_id):
            continue
        regions = [str(x) for x in fit.get("regions_included", []) if str(x)]
        if regions:
            return regions
    raise RuntimeError("fit_id '{}' not found in {}".format(fit_id, regions_path))


def _kind_map(registry_path: Path) -> Dict[str, str]:
    payload = read_json(registry_path)
    out: Dict[str, str] = {}
    for sample in payload.get("samples", []):
        sid = str(sample.get("sample_id", ""))
        sname = str(sample.get("sample_name", ""))
        kind = str(sample.get("kind", "background"))
        if sid:
            out[sid] = kind
        if sname:
            out[sname] = kind
    return out


def _aggregate_region_hist(region_dir: Path, kind_map: Dict[str, str]) -> Dict[str, np.ndarray]:
    obs_dir = region_dir / "m_gg"
    if not obs_dir.exists():
        raise RuntimeError("missing histogram directory {}".format(obs_dir))

    edges = None
    data = None
    signal = None
    background = None
    for npz_path in sorted(obs_dir.glob("*.npz")):
        payload = np.load(npz_path, allow_pickle=True)
        counts = payload["counts"].astype(float)
        if edges is None:
            edges = payload["edges"].astype(float)
            shape = counts.shape
            data = np.zeros(shape, dtype=float)
            signal = np.zeros(shape, dtype=float)
            background = np.zeros(shape, dtype=float)
        sid = npz_path.stem
        kind = kind_map.get(sid, "background")
        if kind == "data":
            data += counts
        elif kind == "signal":
            signal += counts
        else:
            background += counts

    if edges is None or data is None or signal is None or background is None:
        raise RuntimeError("no histograms found for {}".format(region_dir.name))

    # Guard against tiny negative bins from weighted MC fluctuations.
    signal = np.clip(signal, 0.0, None)
    background = np.clip(background, 0.0, None)
    data = np.clip(data, 0.0, None)
    return {"edges": edges, "data": data, "signal": signal, "background": background}


def _make_th1(ROOT: Any, name: str, edges: np.ndarray, counts: np.ndarray) -> Any:
    hist = ROOT.TH1D(name, name, int(len(edges) - 1), edges.astype("d"))
    for i, value in enumerate(counts, start=1):
        hist.SetBinContent(i, float(max(value, 0.0)))
    return hist


def _fit_signal_shape(
    ROOT: Any,
    region_id: str,
    mass: Any,
    sig_hist: Any,
    sig_yield_nominal: float,
) -> Dict[str, Any]:
    sig_data = ROOT.RooDataHist(
        "sig_data_{}".format(region_id),
        "sig_data_{}".format(region_id),
        ROOT.RooArgList(mass),
        sig_hist,
    )

    mean = ROOT.RooRealVar("mean_{}".format(region_id), "mean", 125.0, 120.0, 130.0)
    sigma = ROOT.RooRealVar("sigma_{}".format(region_id), "sigma", 1.8, 0.3, 6.0)
    alpha_l = ROOT.RooRealVar("alphaL_{}".format(region_id), "alphaL", 1.5, 0.2, 10.0)
    n_l = ROOT.RooRealVar("nL_{}".format(region_id), "nL", 4.0, 0.5, 80.0)
    alpha_r = ROOT.RooRealVar("alphaR_{}".format(region_id), "alphaR", 1.5, 0.2, 10.0)
    n_r = ROOT.RooRealVar("nR_{}".format(region_id), "nR", 4.0, 0.5, 80.0)

    pdf = ROOT.RooCrystalBall(
        "sig_pdf_{}".format(region_id),
        "sig_pdf_{}".format(region_id),
        mass,
        mean,
        sigma,
        alpha_l,
        n_l,
        alpha_r,
        n_r,
    )

    fit_result = pdf.fitTo(
        sig_data,
        ROOT.RooFit.Save(True),
        ROOT.RooFit.PrintLevel(-1),
        ROOT.RooFit.Strategy(1),
        ROOT.RooFit.SumW2Error(True),
    )

    # Freeze shape in the combined data fit.
    for var in [mean, sigma, alpha_l, n_l, alpha_r, n_r]:
        var.setConstant(True)

    return {
        "pdf": pdf,
        "data": sig_data,
        "vars": {
            "mean": mean,
            "sigma": sigma,
            "alpha_l": alpha_l,
            "n_l": n_l,
            "alpha_r": alpha_r,
            "n_r": n_r,
        },
        "fit_status": int(fit_result.status()),
        "fit_cov_qual": int(fit_result.covQual()),
        "signal_yield_nominal": float(sig_yield_nominal),
    }


def _nll_sum(ROOT: Any, nll_terms: List[Any]) -> Any:
    arg_list = ROOT.RooArgList()
    for term in nll_terms:
        arg_list.add(term)
    return ROOT.RooAddition("nll_sum", "nll_sum", arg_list)


def _minimize(ROOT: Any, nll: Any) -> Dict[str, Any]:
    minim = ROOT.RooMinimizer(nll)
    minim.setPrintLevel(-1)
    minim.setStrategy(1)
    minim.optimizeConst(2)
    status_migrad = int(minim.minimize("Minuit2", "migrad"))
    status_hesse = int(minim.hesse())
    return {
        "status_migrad": status_migrad,
        "status_hesse": status_hesse,
        "nll_value": float(nll.getVal()),
    }


def _bin_integrals(ROOT: Any, pdf: Any, mass: Any, edges: np.ndarray, prefix: str) -> np.ndarray:
    out = np.zeros(len(edges) - 1, dtype=float)
    obs = ROOT.RooArgSet(mass)
    for i in range(len(out)):
        name = "{}_bin_{}".format(prefix, i)
        mass.setRange(name, float(edges[i]), float(edges[i + 1]))
        frac = pdf.createIntegral(obs, ROOT.RooFit.NormSet(obs), ROOT.RooFit.Range(name))
        out[i] = float(frac.getVal())
    return out


def _window_counts(edges: np.ndarray, counts: np.ndarray, lo: float, hi: float) -> float:
    total = 0.0
    for i in range(len(counts)):
        if float(edges[i]) >= lo and float(edges[i + 1]) <= hi:
            total += float(counts[i])
    return total


def _sum_counts_outside_window(edges: np.ndarray, counts: np.ndarray, lo: float, hi: float) -> float:
    total = 0.0
    for i in range(len(counts)):
        if float(edges[i + 1]) <= lo or float(edges[i]) >= hi:
            total += float(counts[i])
    return total


def _make_plot(
    region_id: str,
    edges: np.ndarray,
    data: np.ndarray,
    bkg_postfit: np.ndarray,
    sig_postfit: np.ndarray,
    blind_window: Tuple[float, float],
    show_window_data: bool,
    out_path: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    centers = 0.5 * (edges[:-1] + edges[1:])
    yerr = np.sqrt(np.clip(data, 1.0, None))
    blind_lo, blind_hi = blind_window
    sideband_mask = (centers < blind_lo) | (centers > blind_hi)
    data_mask = np.ones_like(sideband_mask, dtype=bool) if show_window_data else sideband_mask
    splusb = bkg_postfit + sig_postfit

    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    ax.errorbar(
        centers[data_mask],
        data[data_mask],
        yerr=yerr[data_mask],
        fmt="o",
        color="black",
        ms=3.5,
        lw=1.0,
        label="Data (sidebands)" if not show_window_data else "Data",
    )
    ax.stairs(
        bkg_postfit,
        edges,
        color="#1f77b4",
        linewidth=2.0,
        label="Expected background (post-fit sideband fit)",
    )
    ax.stairs(
        splusb,
        edges,
        color="#d62728",
        linewidth=2.0,
        label="Expected signal+background (stacked)",
    )
    ax.fill_between(
        centers,
        bkg_postfit,
        splusb,
        step="mid",
        color="#d62728",
        alpha=0.2,
        label="Signal component (stacked on background)",
    )
    if not show_window_data:
        ax.axvspan(
            blind_lo,
            blind_hi,
            color="gray",
            alpha=0.15,
            label="Blinded {:.0f}-{:.0f} GeV window".format(blind_lo, blind_hi),
        )
    ax.set_xlim(float(edges[0]), float(edges[-1]))
    ax.set_xlabel(r"$m_{\gamma\gamma}$ [GeV]")
    ax.set_ylabel("Events / 1 GeV")
    ax.set_title(region_id)
    ax.legend(loc="best", frameon=False)
    ax.grid(alpha=0.25)
    ensure_dir(out_path.parent)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def run_combined_fit(
    outputs: Path,
    registry: Path,
    regions: Path,
    fit_id: str,
    out_dir: Path,
    categories: Optional[List[str]] = None,
    fit_range: str = "sidebands",
    blind_window: Tuple[float, float] = (120.0, 130.0),
    show_window_data: bool = False,
    signal_scale_for_blind_fit: float = 1.0,
    compute_asimov_sensitivity: bool = True,
    asimov_mu_gen: float = 0.0,
) -> Dict[str, Any]:
    ROOT = _import_root()
    fit_regions = categories[:] if categories else _fit_regions(regions, fit_id)
    if not fit_regions:
        raise RuntimeError("No categories/regions configured for fit '{}'".format(fit_id))
    if fit_range not in {"sidebands", "full"}:
        raise RuntimeError("Unsupported fit_range '{}': use 'sidebands' or 'full'".format(fit_range))
    if blind_window[0] >= blind_window[1]:
        raise RuntimeError("Invalid blind window bounds: {}".format(blind_window))
    if asimov_mu_gen < 0.0:
        raise RuntimeError("Asimov generation mu must be non-negative, got {}".format(asimov_mu_gen))

    kind_map = _kind_map(registry)

    # Common mass observable for all categories.
    mass = ROOT.RooRealVar("mgg", "mgg", 105.0, 160.0)
    mass.setBins(55)
    mass.setRange("fit", 105.0, 160.0)
    mass.setRange("window125pm2", 123.0, 127.0)
    mass.setRange("sideband_low", 105.0, float(blind_window[0]))
    mass.setRange("sideband_high", float(blind_window[1]), 160.0)
    fit_range_name = "fit" if fit_range == "full" else "sideband_low,sideband_high"

    mu = ROOT.RooRealVar("mu", "mu", 1.0, 0.0, 10.0)

    category_payload: Dict[str, Dict[str, Any]] = {}
    significance_nll_terms: List[Any] = []
    keepalive: List[Any] = [mass, mu]

    for region_id in fit_regions:
        agg = _aggregate_region_hist(outputs / "hists" / region_id, kind_map)
        edges = agg["edges"]
        data_counts = agg["data"]
        signal_counts = agg["signal"]
        bkg_counts = agg["background"]

        sig_nom = float(np.sum(signal_counts))
        bkg_nom = float(np.sum(bkg_counts))
        if sig_nom <= 0.0:
            raise RuntimeError("region '{}' has zero nominal signal yield".format(region_id))
        if bkg_nom <= 0.0:
            bkg_nom = max(float(np.sum(data_counts)), 1.0)

        data_hist = _make_th1(ROOT, "h_data_{}".format(region_id), edges, data_counts)
        sig_hist = _make_th1(ROOT, "h_sig_{}".format(region_id), edges, signal_counts)

        data_dh = ROOT.RooDataHist(
            "data_dh_{}".format(region_id),
            "data_dh_{}".format(region_id),
            ROOT.RooArgList(mass),
            data_hist,
        )

        sig_shape = _fit_signal_shape(ROOT, region_id, mass, sig_hist, sig_nom)

        tau = ROOT.RooRealVar("tau_{}".format(region_id), "tau", -0.02, -1.0, 1.0)
        bkg_pdf = ROOT.RooExponential(
            "bkg_pdf_{}".format(region_id),
            "bkg_pdf_{}".format(region_id),
            mass,
            tau,
        )

        s_nom = ROOT.RooConstVar("s_nom_{}".format(region_id), "s_nom", sig_nom)
        nsig = ROOT.RooFormulaVar(
            "nsig_{}".format(region_id),
            "@0*@1",
            ROOT.RooArgList(mu, s_nom),
        )
        nbkg = ROOT.RooRealVar(
            "nbkg_{}".format(region_id),
            "nbkg",
            max(bkg_nom, 1.0),
            0.0,
            max(10.0 * max(float(np.sum(data_counts)), bkg_nom), 1000.0),
        )
        model = ROOT.RooAddPdf(
            "model_{}".format(region_id),
            "model_{}".format(region_id),
            ROOT.RooArgList(sig_shape["pdf"], bkg_pdf),
            ROOT.RooArgList(nsig, nbkg),
        )

        nll = model.createNLL(
            data_dh,
            ROOT.RooFit.Extended(True),
            ROOT.RooFit.Range(fit_range_name),
            ROOT.RooFit.Offset(True),
        )
        significance_nll_terms.append(nll)

        category_payload[region_id] = {
            "edges": edges,
            "data_counts": data_counts,
            "signal_counts_nominal": signal_counts,
            "background_counts_nominal": bkg_counts,
            "data_hist": data_hist,
            "sig_hist": sig_hist,
            "data_dh": data_dh,
            "sig_shape": sig_shape,
            "tau": tau,
            "bkg_pdf": bkg_pdf,
            "s_nom": s_nom,
            "nsig": nsig,
            "nbkg": nbkg,
            "model": model,
            "significance_nll": nll,
        }

        keepalive.extend(
            [
                data_hist,
                sig_hist,
                data_dh,
                sig_shape["data"],
                sig_shape["pdf"],
                sig_shape["vars"]["mean"],
                sig_shape["vars"]["sigma"],
                sig_shape["vars"]["alpha_l"],
                sig_shape["vars"]["n_l"],
                sig_shape["vars"]["alpha_r"],
                sig_shape["vars"]["n_r"],
                tau,
                bkg_pdf,
                s_nom,
                nsig,
                nbkg,
                model,
                nll,
            ]
        )

    # Step 1: blinded/post-fit background shape in requested fit range with fixed signal normalization.
    mu.setVal(float(signal_scale_for_blind_fit))
    mu.setConstant(True)
    sideband_fit_rows: List[Dict[str, Any]] = []
    for region_id in fit_regions:
        payload = category_payload[region_id]
        sb_nll = payload["model"].createNLL(
            payload["data_dh"],
            ROOT.RooFit.Extended(True),
            ROOT.RooFit.Range(fit_range_name),
            ROOT.RooFit.Offset(True),
        )
        sb_fit = _minimize(ROOT, sb_nll)
        payload["sideband_nll"] = sb_nll
        keepalive.append(sb_nll)
        sideband_fit_rows.append(
            {
                "category": region_id,
                "fit_range": fit_range_name,
                "mu_fixed": float(mu.getVal()),
                "tau_postfit": float(payload["tau"].getVal()),
                "nbkg_postfit_total": float(payload["nbkg"].getVal()),
                "fit_status_migrad": int(sb_fit["status_migrad"]),
                "fit_status_hesse": int(sb_fit["status_hesse"]),
                "nll_value": float(sb_fit["nll_value"]),
            }
        )

    # Step 1b: expected sensitivity with Asimov pseudo-data.
    # Asimov is generated from PDFs with parameters from the sideband-constrained data fit.
    asimov_significance: Optional[Dict[str, Any]] = None
    if compute_asimov_sensitivity:
        mu.setVal(float(asimov_mu_gen))
        mu.setConstant(True)
        asimov_nll_terms: List[Any] = []
        asimov_rows: List[Dict[str, Any]] = []
        for region_id in fit_regions:
            payload = category_payload[region_id]
            edges = payload["edges"]
            sig_pdf = payload["sig_shape"]["pdf"]
            bkg_pdf = payload["bkg_pdf"]
            bkg_total = float(payload["nbkg"].getVal())
            sig_total = float(payload["sig_shape"]["signal_yield_nominal"])

            sig_bin_frac = _bin_integrals(ROOT, sig_pdf, mass, edges, "asimov_sig_{}".format(region_id))
            bkg_bin_frac = _bin_integrals(ROOT, bkg_pdf, mass, edges, "asimov_bkg_{}".format(region_id))
            expected_counts = float(asimov_mu_gen) * sig_total * sig_bin_frac + bkg_total * bkg_bin_frac

            asimov_hist = _make_th1(ROOT, "h_asimov_{}".format(region_id), edges, expected_counts)
            asimov_dh = ROOT.RooDataHist(
                "asimov_dh_{}".format(region_id),
                "asimov_dh_{}".format(region_id),
                ROOT.RooArgList(mass),
                asimov_hist,
            )
            asimov_nll = payload["model"].createNLL(
                asimov_dh,
                ROOT.RooFit.Extended(True),
                ROOT.RooFit.Range("fit"),
                ROOT.RooFit.Offset(True),
            )
            asimov_nll_terms.append(asimov_nll)
            keepalive.extend([asimov_hist, asimov_dh, asimov_nll])
            asimov_rows.append(
                {
                    "category": region_id,
                    "mu_gen": float(asimov_mu_gen),
                    "asimov_events_total": float(np.sum(expected_counts)),
                    "bkg_total_from_data_fit": bkg_total,
                    "sig_total_nominal": sig_total,
                }
            )

        asimov_nll_sum = _nll_sum(ROOT, asimov_nll_terms)
        keepalive.append(asimov_nll_sum)

        mu.setConstant(False)
        asimov_free_fit = _minimize(ROOT, asimov_nll_sum)
        asimov_mu_hat = float(mu.getVal())
        asimov_mu_err = float(mu.getError())
        asimov_nll_free = float(asimov_free_fit["nll_value"])

        mu.setVal(0.0)
        mu.setConstant(True)
        asimov_mu0_fit = _minimize(ROOT, asimov_nll_sum)
        asimov_nll_mu0 = float(asimov_mu0_fit["nll_value"])
        mu.setConstant(False)

        asimov_q0 = max(2.0 * (asimov_nll_mu0 - asimov_nll_free), 0.0)
        asimov_z = math.sqrt(asimov_q0)
        asimov_significance = {
            "fit_id": fit_id,
            "status": "ok"
            if asimov_free_fit["status_migrad"] == 0 and asimov_mu0_fit["status_migrad"] == 0
            else "failed",
            "backend": "pyroot_roofit",
            "dataset_type": "asimov",
            "asimov_source": "category PDFs with parameters from sideband-constrained data fit",
            "generation_hypothesis": "background_only" if float(asimov_mu_gen) == 0.0 else "signal_plus_background",
            "mu_gen": float(asimov_mu_gen),
            "generation_fit_range": fit_range_name,
            "evaluation_fit_range": "fit",
            "blind_window_gev": [float(blind_window[0]), float(blind_window[1])],
            "model": "combined_{}cat_dscb_plus_exponential".format(len(fit_regions)),
            "poi_name": "mu",
            "mu_hat": asimov_mu_hat,
            "mu_hat_error": asimov_mu_err,
            "nll_free": asimov_nll_free,
            "nll_mu0": asimov_nll_mu0,
            "q0": asimov_q0,
            "z_discovery": asimov_z,
            "fit_status_free": asimov_free_fit,
            "fit_status_mu0": asimov_mu0_fit,
            "categories": fit_regions,
            "n_categories": len(fit_regions),
            "shared_signal_strength": True,
            "generation_category_summary": asimov_rows,
            "note": (
                "Expected discovery sensitivity from Asimov pseudo-data. "
                "Asimov built over full mass range from sideband-fitted PDFs."
            ),
        }
        if asimov_significance["status"] != "ok":
            asimov_significance["error"] = "Asimov sensitivity fit failed for free or mu=0 hypothesis"

    # Snapshot post-fit values for plotting and window yields.
    postfit_rows: List[Dict[str, Any]] = []
    cutflow_rows: List[Dict[str, Any]] = []
    plots: List[str] = []
    signal_shape_rows: List[Dict[str, Any]] = []

    for region_id in fit_regions:
        payload = category_payload[region_id]
        edges = payload["edges"]
        sig_pdf = payload["sig_shape"]["pdf"]
        bkg_pdf = payload["bkg_pdf"]
        nbkg = payload["nbkg"]
        nsig = payload["nsig"]
        tau = payload["tau"]

        obs = ROOT.RooArgSet(mass)
        sig_frac_window = float(
            sig_pdf.createIntegral(obs, ROOT.RooFit.NormSet(obs), ROOT.RooFit.Range("window125pm2")).getVal()
        )
        bkg_frac_window = float(
            bkg_pdf.createIntegral(obs, ROOT.RooFit.NormSet(obs), ROOT.RooFit.Range("window125pm2")).getVal()
        )
        sig_win = float(signal_scale_for_blind_fit) * float(payload["sig_shape"]["signal_yield_nominal"]) * sig_frac_window
        bkg_win = float(nbkg.getVal()) * bkg_frac_window
        data_win = _window_counts(edges, payload["data_counts"], 123.0, 127.0)
        data_sidebands = _sum_counts_outside_window(edges, payload["data_counts"], blind_window[0], blind_window[1])

        sig_bin_frac = _bin_integrals(ROOT, sig_pdf, mass, edges, "sig_{}".format(region_id))
        bkg_bin_frac = _bin_integrals(ROOT, bkg_pdf, mass, edges, "bkg_{}".format(region_id))
        sig_postfit = float(signal_scale_for_blind_fit) * float(payload["sig_shape"]["signal_yield_nominal"]) * sig_bin_frac
        bkg_postfit = float(nbkg.getVal()) * bkg_bin_frac

        plot_path = outputs / "report" / "plots" / "roofit_combined_mgg_{}.png".format(region_id)
        _make_plot(
            region_id,
            edges,
            payload["data_counts"],
            bkg_postfit,
            sig_postfit,
            blind_window=blind_window,
            show_window_data=show_window_data,
            out_path=plot_path,
        )
        plots.append(str(plot_path))

        postfit_rows.append(
            {
                "category": region_id,
                "mu_for_signal_overlay": float(signal_scale_for_blind_fit),
                "tau_postfit": float(tau.getVal()),
                "nbkg_postfit_total": float(nbkg.getVal()),
                "nsig_overlay_total": float(signal_scale_for_blind_fit) * float(payload["sig_shape"]["signal_yield_nominal"]),
            }
        )
        cutflow_rows.append(
            {
                "category": region_id,
                "mass_window_gev": [123.0, 127.0],
                "expected_signal_postfit": sig_win,
                "expected_background_postfit": bkg_win,
                "observed_data_in_window": data_win if show_window_data else None,
                "observed_data_sidebands": data_sidebands,
            }
        )
        vars_map = payload["sig_shape"]["vars"]
        signal_shape_rows.append(
            {
                "category": region_id,
                "fit_status": int(payload["sig_shape"]["fit_status"]),
                "fit_cov_qual": int(payload["sig_shape"]["fit_cov_qual"]),
                "mean": float(vars_map["mean"].getVal()),
                "sigma": float(vars_map["sigma"].getVal()),
                "alpha_l": float(vars_map["alpha_l"].getVal()),
                "n_l": float(vars_map["n_l"].getVal()),
                "alpha_r": float(vars_map["alpha_r"].getVal()),
                "n_r": float(vars_map["n_r"].getVal()),
                "signal_yield_nominal": float(payload["sig_shape"]["signal_yield_nominal"]),
            }
        )

    # Step 2: significance from combined profile-likelihood in configured fit range.
    nll_sum = _nll_sum(ROOT, significance_nll_terms)
    keepalive.append(nll_sum)
    mu.setConstant(False)
    free_fit = _minimize(ROOT, nll_sum)
    mu_hat = float(mu.getVal())
    mu_err = float(mu.getError())
    nll_free = float(free_fit["nll_value"])

    mu.setVal(0.0)
    mu.setConstant(True)
    mu0_fit = _minimize(ROOT, nll_sum)
    nll_mu0 = float(mu0_fit["nll_value"])
    mu.setConstant(False)

    q0 = max(2.0 * (nll_mu0 - nll_free), 0.0)
    z = math.sqrt(q0)

    significance = {
        "fit_id": fit_id,
        "status": "ok"
        if free_fit["status_migrad"] == 0 and mu0_fit["status_migrad"] == 0
        else "failed",
        "backend": "pyroot_roofit",
        "model": "combined_{}cat_dscb_plus_exponential".format(len(fit_regions)),
        "poi_name": "mu",
        "mu_hat": mu_hat,
        "mu_hat_error": mu_err,
        "nll_free": nll_free,
        "nll_mu0": nll_mu0,
        "q0": q0,
        "z_discovery": z,
        "fit_status_free": free_fit,
        "fit_status_mu0": mu0_fit,
        "categories": fit_regions,
        "n_categories": len(fit_regions),
        "shared_signal_strength": True,
        "background_per_category": "RooExponential with independent slope and normalization per category",
        "signal_per_category": "RooCrystalBall (double-sided) fitted to signal template per category",
        "fit_range": fit_range_name,
        "blind_window_gev": [float(blind_window[0]), float(blind_window[1])],
    }

    if significance["status"] != "ok":
        significance["error"] = "Combined fit failed for free or mu=0 hypothesis"

    cutflow_payload = {
        "fit_id": fit_id,
        "mass_window_gev": [123.0, 127.0],
        "categories": cutflow_rows,
        "totals": {
            "expected_signal_postfit": float(sum(x["expected_signal_postfit"] for x in cutflow_rows)),
            "expected_background_postfit": float(sum(x["expected_background_postfit"] for x in cutflow_rows)),
            "observed_data_in_window": (
                float(sum(float(x["observed_data_in_window"]) for x in cutflow_rows))
                if show_window_data
                else None
            ),
            "observed_data_sidebands": float(sum(x["observed_data_sidebands"] for x in cutflow_rows)),
        },
        "blinding": {
            "show_window_data": bool(show_window_data),
            "blind_window_gev": [float(blind_window[0]), float(blind_window[1])],
            "fit_range": fit_range_name,
        },
    }

    lines = []
    lines.append(
        "| Category | Expected signal (post-fit) | Expected background (post-fit) | "
        "Observed data in 125+-2 | Observed data in sidebands |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for row in cutflow_rows:
        obs_win = (
            "{:.0f}".format(float(row["observed_data_in_window"]))
            if row["observed_data_in_window"] is not None
            else "blinded"
        )
        lines.append(
            "| {cat} | {sig:.6g} | {bkg:.6g} | {obs_win} | {obs_side:.0f} |".format(
                cat=row["category"],
                sig=float(row["expected_signal_postfit"]),
                bkg=float(row["expected_background_postfit"]),
                obs_win=obs_win,
                obs_side=float(row["observed_data_sidebands"]),
            )
        )
    total_obs_win = (
        "{:.0f}".format(float(cutflow_payload["totals"]["observed_data_in_window"]))
        if cutflow_payload["totals"]["observed_data_in_window"] is not None
        else "blinded"
    )
    lines.append(
        "| **Total ({ncat} cat)** | **{sig:.6g}** | **{bkg:.6g}** | "
        "**{obs_win_total}** | **{obs_side:.0f}** |".format(
            ncat=len(fit_regions),
            sig=cutflow_payload["totals"]["expected_signal_postfit"],
            bkg=cutflow_payload["totals"]["expected_background_postfit"],
            obs_win_total=total_obs_win,
            obs_side=cutflow_payload["totals"]["observed_data_sidebands"],
        )
    )

    ensure_dir(out_dir)
    fit_dir = ensure_dir(out_dir)
    write_json(fit_dir / "significance.json", significance)
    if asimov_significance is not None:
        write_json(fit_dir / "significance_asimov_expected.json", asimov_significance)
    write_json(fit_dir / "cutflow_mass_window_125pm2.json", cutflow_payload)
    write_json(fit_dir / "postfit_category_parameters.json", {"categories": postfit_rows})
    write_json(fit_dir / "sideband_fit_parameters.json", {"categories": sideband_fit_rows})
    write_json(fit_dir / "signal_dscb_parameters.json", {"categories": signal_shape_rows})
    (fit_dir / "cutflow_mass_window_125pm2.md").write_text("\n".join(lines) + "\n")

    summary = {
        "fit_id": fit_id,
        "n_categories": len(fit_regions),
        "categories": fit_regions,
        "outputs": {
            "significance_json": str(fit_dir / "significance.json"),
            "significance_asimov_expected_json": (
                str(fit_dir / "significance_asimov_expected.json")
                if asimov_significance is not None
                else None
            ),
            "cutflow_json": str(fit_dir / "cutflow_mass_window_125pm2.json"),
            "cutflow_markdown": str(fit_dir / "cutflow_mass_window_125pm2.md"),
            "postfit_parameters_json": str(fit_dir / "postfit_category_parameters.json"),
            "sideband_fit_parameters_json": str(fit_dir / "sideband_fit_parameters.json"),
            "signal_dscb_parameters_json": str(fit_dir / "signal_dscb_parameters.json"),
            "plots": plots,
        },
        "blinding": {
            "fit_range": fit_range_name,
            "blind_window_gev": [float(blind_window[0]), float(blind_window[1])],
            "show_window_data": bool(show_window_data),
            "signal_scale_for_blind_fit": float(signal_scale_for_blind_fit),
        },
        "asimov_sensitivity": {
            "enabled": bool(compute_asimov_sensitivity),
            "mu_gen": float(asimov_mu_gen),
            "evaluation_fit_range": "fit",
        },
    }
    write_json(fit_dir / "summary.json", summary)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run combined RooFit likelihood with per-category DS-CB signal models"
    )
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--regions", default="analysis/regions.yaml")
    parser.add_argument("--fit-id", default="FIT_MAIN")
    parser.add_argument(
        "--subdir",
        default="roofit_combined",
        help="Subdirectory under outputs/fit/<fit-id>/ for produced artifacts.",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        default=[],
        help="Optional explicit list of category/region IDs to fit. "
        "If omitted, uses regions_included from --fit-id in --regions.",
    )
    parser.add_argument(
        "--fit-range",
        choices=["sidebands", "full"],
        default="sidebands",
        help="Mass range used for data fit. 'sidebands' keeps 120-130 GeV blinded by default.",
    )
    parser.add_argument("--blind-window-low", type=float, default=120.0)
    parser.add_argument("--blind-window-high", type=float, default=130.0)
    parser.add_argument(
        "--show-window-data",
        action="store_true",
        help="Show data points in the blind window on output plots and tables.",
    )
    parser.add_argument(
        "--signal-scale-for-blind-fit",
        type=float,
        default=1.0,
        help="Fixed signal-strength scale used for stacked signal overlay in blinded sideband fit outputs.",
    )
    parser.add_argument(
        "--no-asimov-sensitivity",
        action="store_true",
        help="Disable Asimov expected-sensitivity evaluation.",
    )
    parser.add_argument(
        "--asimov-mu-gen",
        type=float,
        default=0.0,
        help="Signal strength used to generate Asimov pseudo-data (default: 0 for background-only).",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    outputs = Path(args.outputs)
    summary = run_combined_fit(
        outputs=outputs,
        registry=Path(args.registry),
        regions=Path(args.regions),
        fit_id=args.fit_id,
        out_dir=outputs / "fit" / args.fit_id / str(args.subdir),
        categories=[str(x) for x in args.categories if str(x)],
        fit_range=str(args.fit_range),
        blind_window=(float(args.blind_window_low), float(args.blind_window_high)),
        show_window_data=bool(args.show_window_data),
        signal_scale_for_blind_fit=float(args.signal_scale_for_blind_fit),
        compute_asimov_sensitivity=not bool(args.no_asimov_sensitivity),
        asimov_mu_gen=float(args.asimov_mu_gen),
    )
    print("roofit_combined completed: fit_id={} categories={}".format(summary["fit_id"], summary["n_categories"]))
    print("significance: {}".format(summary["outputs"]["significance_json"]))


if __name__ == "__main__":
    main()
