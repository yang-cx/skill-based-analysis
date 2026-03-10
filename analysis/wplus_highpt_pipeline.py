import argparse
import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import awkward as ak
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import uproot

from analysis.common import ensure_dir, write_json


LUMI_FB_DEFAULT = 36.1
BLIND_SIGNAL_REGIONS = {
    "SR_inclusive",
    "SR_inclusive2j",
    "SR_collinear",
    "SR_back_to_back",
}
REGION_ORDER = [
    "SR_inclusive",
    "SR_inclusive2j",
    "SR_collinear",
    "SR_back_to_back",
    "CR_ttbar",
    "CR_Zjets",
    "CR_multijet",
    "VR_multijet_lowMET",
]
PROCESS_ORDER = [
    "signal_wlnu",
    "wtaunu",
    "ttbar",
    "single_top",
    "zjets",
    "diboson",
    "ewk_vjj",
]
PROCESS_LABELS = {
    "data": "Data",
    "signal_wlnu": "W->enu/munu (signal)",
    "wtaunu": "W->taunu",
    "ttbar": "ttbar+X",
    "single_top": "Single-top",
    "zjets": "Z/gamma*+jets",
    "diboson": "Diboson/triboson",
    "ewk_vjj": "EWK V+jj",
}
PROCESS_COLORS = {
    "signal_wlnu": "#e15759",
    "wtaunu": "#ff9d4d",
    "ttbar": "#4e79a7",
    "single_top": "#59a14f",
    "zjets": "#76b7b2",
    "diboson": "#af7aa1",
    "ewk_vjj": "#edc948",
}

BRANCHES = [
    "eventNumber",
    "mcWeight",
    "num_events",
    "sum_of_weights",
    "xsec",
    "kfac",
    "filteff",
    "ScaleFactor_PILEUP",
    "ScaleFactor_ELE",
    "ScaleFactor_MUON",
    "ScaleFactor_LepTRIGGER",
    "ScaleFactor_MLTRIGGER",
    "ScaleFactor_JVT",
    "ScaleFactor_BTAG",
    "ScaleFactor_FTAG",
    "lep_pt",
    "lep_eta",
    "lep_phi",
    "lep_e",
    "lep_type",
    "lep_charge",
    "lep_ptvarcone30",
    "lep_topoetcone20",
    "lep_d0sig",
    "jet_pt",
    "jet_eta",
    "jet_phi",
    "jet_e",
    "jet_btag_quantile",
    "jet_jvt",
    "met",
    "met_phi",
    "trigE",
    "trigM",
]

OBSERVABLES: Dict[str, Dict[str, Any]] = {
    "deltaRmin_l_jet100": {
        "label": r"$\Delta R_{\min}(\ell,\mathrm{jet}_{p_T>100})$",
        "bins": np.linspace(0.0, 6.0, 25),
    },
    "ptlv_over_ptclosestjet100": {
        "label": r"$p_T^{\ell\nu}/p_T^{\mathrm{closest\ jet}_{100}}$",
        "bins": np.linspace(0.0, 2.5, 26),
    },
    "mjj": {
        "label": r"$m_{jj}$ [GeV]",
        "bins": np.linspace(0.0, 3000.0, 31),
    },
    "leading_jet_pt": {
        "label": r"Leading jet $p_T$ [GeV]",
        "bins": np.linspace(500.0, 2000.0, 31),
    },
    "pt_lv": {
        "label": r"$p_T^{\ell\nu}$ [GeV]",
        "bins": np.linspace(0.0, 1500.0, 31),
    },
    "jet_multiplicity": {
        "label": r"Jet multiplicity",
        "bins": np.arange(-0.5, 10.5, 1.0),
    },
    "st": {
        "label": r"$S_T$ [GeV]",
        "bins": np.linspace(0.0, 3500.0, 36),
    },
    "met": {
        "label": r"$E_T^{\mathrm{miss}}$ [GeV]",
        "bins": np.linspace(0.0, 800.0, 33),
    },
}

PLOTS_BY_REGION = {
    "SR_inclusive": ["leading_jet_pt", "deltaRmin_l_jet100", "jet_multiplicity", "pt_lv"],
    "SR_inclusive2j": ["mjj", "st", "ptlv_over_ptclosestjet100"],
    "SR_collinear": ["leading_jet_pt", "ptlv_over_ptclosestjet100", "jet_multiplicity"],
    "SR_back_to_back": ["leading_jet_pt", "ptlv_over_ptclosestjet100", "jet_multiplicity"],
    "CR_ttbar": ["leading_jet_pt", "jet_multiplicity", "st"],
    "CR_Zjets": ["leading_jet_pt", "jet_multiplicity", "mjj"],
    "CR_multijet": ["leading_jet_pt", "jet_multiplicity", "met"],
    "VR_multijet_lowMET": ["leading_jet_pt", "jet_multiplicity", "met"],
}

DSID_RE = re.compile(r"_mc_(\d+)\.")


@dataclass
class SampleSpec:
    path: Path
    group: str
    is_data: bool
    w_norm: float


def _safe_first(arr: ak.Array, index: int, default: float = 0.0) -> ak.Array:
    padded = ak.pad_none(arr, index + 1, axis=1, clip=True)
    return ak.fill_none(padded[:, index], default)


def _delta_phi(phi1: ak.Array, phi2: ak.Array) -> ak.Array:
    dphi = phi1 - phi2
    return (dphi + np.pi) % (2.0 * np.pi) - np.pi


def _inv_mass_from_pt_eta_phi_e(
    pt1: ak.Array,
    eta1: ak.Array,
    phi1: ak.Array,
    e1: ak.Array,
    pt2: ak.Array,
    eta2: ak.Array,
    phi2: ak.Array,
    e2: ak.Array,
) -> ak.Array:
    px1 = pt1 * np.cos(phi1)
    py1 = pt1 * np.sin(phi1)
    pz1 = pt1 * np.sinh(eta1)
    px2 = pt2 * np.cos(phi2)
    py2 = pt2 * np.sin(phi2)
    pz2 = pt2 * np.sinh(eta2)

    e = e1 + e2
    px = px1 + px2
    py = py1 + py2
    pz = pz1 + pz2
    m2 = e * e - (px * px + py * py + pz * pz)
    m2 = ak.where(m2 < 0.0, 0.0, m2)
    return np.sqrt(m2)


def _to_numpy(arr: ak.Array) -> np.ndarray:
    return np.asarray(ak.to_numpy(arr), dtype=float)


def _extract_dsid(path: Path) -> Optional[int]:
    m = DSID_RE.search(path.name)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _classify_mc(path: Path) -> Optional[str]:
    name = path.name.lower()
    dsid = _extract_dsid(path)

    if re.search(r"sh_2211_w(?:enu|munu)_maxhtptv2_", name):
        return "signal_wlnu"

    if re.search(r"sh_2211_wtaunu|sh_2214_wtaunu", name):
        return "wtaunu"

    if re.search(
        r"sh_2211_(?:zee|zmumu|znunu)_maxhtptv2_|"
        r"sh_2211_(?:zee|zmumu)_maxhtptv2_m10_40_|"
        r"sh_2214_ztautau_maxhtptv2_|"
        r"sh_2214_ztt_maxhtptv2_|"
        r"sh_2211_z(?:ee|mm|tt|nunu)2jets_min_n_tchannel",
        name,
    ):
        return "zjets"

    if re.search(r"sh_2211_w(?:enu|munu|taunu)2jets_min_n_tchannel", name):
        return "ewk_vjj"

    if re.search(r"ttbar|ttw|ttz|ttgamma|ttbarww|zprime3000_tt|sh_228_ttw", name):
        return "ttbar"

    if re.search(r"singletop|_tchan_|_schan_|_tw_|phpy8eg_tw|_twz_|_tz_", name):
        return "single_top"

    if re.search(
        r"sherpa_222_.*(?:www|wwz|wzz|zzz)|"
        r"sh_2211_wlvwqq|sh_2211_wlvzqq|sh_2211_wlvzbb|"
        r"sh_2212_.*(?:llvv|lvvv|vvvv)|"
        r"sh_2211_wqqzvv|sh_2211_wqqzll|sh_2211_zqqzvv|sh_2211_zbbzvv",
        name,
    ):
        return "diboson"

    # Include known top alternatives from open-data campaign.
    if dsid in {411233, 411234, 411316, 601491, 601495, 601497, 410470, 410471}:
        return "ttbar"

    if dsid in {
        410644,
        410645,
        410658,
        410659,
        410560,
        410408,
        600017,
        600018,
        600019,
        600020,
        601352,
        601355,
        601624,
        601627,
        601628,
        601631,
        601761,
        601762,
        601763,
        601764,
        601487,
        601489,
    }:
        return "single_top"

    return None


def _read_mc_norm(path: Path, lumi_fb: float) -> float:
    try:
        with uproot.open(path) as f:
            tree = f["analysis"]
            available = set(tree.keys())
            branches = [b for b in ["sum_of_weights", "xsec", "kfac", "filteff"] if b in available]
            if not branches:
                return 1.0
            row = tree.arrays(branches, entry_start=0, entry_stop=1, library="np")
            sumw = float(row["sum_of_weights"][0]) if "sum_of_weights" in row else np.nan
            xsec = float(row["xsec"][0]) if "xsec" in row else np.nan
            kfac = float(row["kfac"][0]) if "kfac" in row else 1.0
            eff = float(row["filteff"][0]) if "filteff" in row else 1.0
            if not np.isfinite(sumw) or sumw == 0.0:
                return 1.0
            if not np.isfinite(xsec) or xsec <= 0.0:
                return 1.0
            if not np.isfinite(kfac) or kfac <= 0.0:
                kfac = 1.0
            if not np.isfinite(eff) or eff <= 0.0:
                eff = 1.0
            lumi_pb = float(lumi_fb) * 1000.0
            return float((xsec * kfac * eff * lumi_pb) / abs(sumw))
    except Exception:
        return 1.0


def _build_sample_list(inputs: Path, lumi_fb: float) -> Tuple[List[SampleSpec], Dict[str, int]]:
    data_files = sorted((inputs / "data").glob("*.root"))
    mc_files = sorted((inputs / "MC").glob("*.root"))

    specs: List[SampleSpec] = []
    counts = {"data_files": 0, "mc_selected_files": 0, "mc_total_files": len(mc_files)}

    for path in data_files:
        specs.append(SampleSpec(path=path, group="data", is_data=True, w_norm=1.0))
        counts["data_files"] += 1

    for path in mc_files:
        group = _classify_mc(path)
        if group is None:
            continue
        specs.append(
            SampleSpec(
                path=path,
                group=group,
                is_data=False,
                w_norm=_read_mc_norm(path, lumi_fb=lumi_fb),
            )
        )
        counts["mc_selected_files"] += 1

    return specs, counts


def _mc_weight(chunk: ak.Array, w_norm: float) -> ak.Array:
    n = len(chunk)
    base = np.ones(n, dtype=np.float64)

    if "mcWeight" in chunk.fields:
        mcw = ak.to_numpy(chunk["mcWeight"])
        # Stabilize bounded-event runs by using positive-weight magnitudes.
        base *= np.abs(mcw)

    for sf in [
        "ScaleFactor_PILEUP",
        "ScaleFactor_ELE",
        "ScaleFactor_MUON",
        "ScaleFactor_LepTRIGGER",
        "ScaleFactor_MLTRIGGER",
        "ScaleFactor_JVT",
        "ScaleFactor_BTAG",
        "ScaleFactor_FTAG",
    ]:
        if sf in chunk.fields:
            base *= np.abs(ak.to_numpy(chunk[sf]))

    base *= float(w_norm)
    base = np.nan_to_num(base, nan=0.0, posinf=0.0, neginf=0.0)
    return ak.Array(base)


def _compute_event_content(chunk: ak.Array) -> Dict[str, Any]:
    lep_pt = chunk["lep_pt"]
    lep_eta = chunk["lep_eta"]
    lep_phi = chunk["lep_phi"]
    lep_e = chunk["lep_e"]
    lep_type = chunk["lep_type"]
    lep_charge = chunk["lep_charge"]
    lep_ptvar = chunk["lep_ptvarcone30"]
    lep_topo = chunk["lep_topoetcone20"]
    trig_e = chunk["trigE"] if "trigE" in chunk.fields else ak.zeros_like(chunk["met"])
    trig_m = chunk["trigM"] if "trigM" in chunk.fields else ak.zeros_like(chunk["met"])

    abs_lep_eta = abs(lep_eta)
    e_acc = (abs_lep_eta < 1.37) | ((abs_lep_eta > 1.52) & (abs_lep_eta < 2.47))
    mu_acc = abs_lep_eta < 2.4
    lep_acc = ((lep_type == 11) & e_acc) | ((lep_type == 13) & mu_acc)

    lep_pt_nonzero = ak.where(lep_pt > 1e-6, lep_pt, 1.0)
    rel_ptvar = lep_ptvar / lep_pt_nonzero
    rel_topo = lep_topo / lep_pt_nonzero
    iso_tight = (rel_ptvar < 0.15) & (rel_topo < 0.15)
    iso_loose = (rel_ptvar < 0.25) & (rel_topo < 0.25)

    signal_lep_mask = lep_acc & (lep_pt > 30.0) & iso_tight
    antiiso_lep_mask = lep_acc & (lep_pt > 30.0) & (~iso_tight) & iso_loose
    loose_lep_mask = lep_acc & (lep_pt > 10.0) & iso_loose

    def _sorted(mask: ak.Array) -> Tuple[ak.Array, ak.Array, ak.Array, ak.Array, ak.Array]:
        pt_sel = lep_pt[mask]
        eta_sel = lep_eta[mask]
        phi_sel = lep_phi[mask]
        e_sel = lep_e[mask]
        type_sel = lep_type[mask]
        q_sel = lep_charge[mask]
        order = ak.argsort(pt_sel, axis=1, ascending=False)
        return (
            pt_sel[order],
            eta_sel[order],
            phi_sel[order],
            e_sel[order],
            type_sel[order],
            q_sel[order],
        )

    sig_pt, sig_eta, sig_phi, sig_e, sig_type, sig_charge = _sorted(signal_lep_mask)
    anti_pt, anti_eta, anti_phi, anti_e, anti_type, anti_charge = _sorted(antiiso_lep_mask)
    loose_pt, loose_eta, loose_phi, loose_e, loose_type, loose_charge = _sorted(loose_lep_mask)

    n_signal = ak.values_astype(ak.num(sig_pt, axis=1), np.int32)
    n_antiiso = ak.values_astype(ak.num(anti_pt, axis=1), np.int32)
    n_loose = ak.values_astype(ak.num(loose_pt, axis=1), np.int32)

    lead_pt = _safe_first(sig_pt, 0, 0.0)
    lead_eta = _safe_first(sig_eta, 0, 0.0)
    lead_phi = _safe_first(sig_phi, 0, 0.0)
    lead_type = _safe_first(sig_type, 0, 0)
    lead_charge = _safe_first(sig_charge, 0, 0)

    anti_lead_pt = _safe_first(anti_pt, 0, 0.0)
    anti_lead_eta = _safe_first(anti_eta, 0, 0.0)
    anti_lead_phi = _safe_first(anti_phi, 0, 0.0)
    anti_lead_type = _safe_first(anti_type, 0, 0)
    anti_lead_charge = _safe_first(anti_charge, 0, 0)

    lead_trigger = ak.where(
        lead_type == 11,
        trig_e > 0,
        ak.where(lead_type == 13, trig_m > 0, False),
    )
    anti_trigger = ak.where(
        anti_lead_type == 11,
        trig_e > 0,
        ak.where(anti_lead_type == 13, trig_m > 0, False),
    )

    loose1_pt = _safe_first(loose_pt, 0, 0.0)
    loose2_pt = _safe_first(loose_pt, 1, 0.0)
    loose1_eta = _safe_first(loose_eta, 0, 0.0)
    loose2_eta = _safe_first(loose_eta, 1, 0.0)
    loose1_phi = _safe_first(loose_phi, 0, 0.0)
    loose2_phi = _safe_first(loose_phi, 1, 0.0)
    loose1_e = _safe_first(loose_e, 0, 0.0)
    loose2_e = _safe_first(loose_e, 1, 0.0)
    loose1_type = _safe_first(loose_type, 0, 0)
    loose2_type = _safe_first(loose_type, 1, 0)
    loose1_charge = _safe_first(loose_charge, 0, 0)
    loose2_charge = _safe_first(loose_charge, 1, 0)
    has_two_loose = n_loose >= 2
    mll = ak.where(
        has_two_loose,
        _inv_mass_from_pt_eta_phi_e(
            loose1_pt,
            loose1_eta,
            loose1_phi,
            loose1_e,
            loose2_pt,
            loose2_eta,
            loose2_phi,
            loose2_e,
        ),
        0.0,
    )
    sfos = (
        has_two_loose
        & (loose1_type == loose2_type)
        & ((loose1_charge * loose2_charge) < 0)
    )

    jet_pt = chunk["jet_pt"]
    jet_eta = chunk["jet_eta"]
    jet_phi = chunk["jet_phi"]
    jet_e = chunk["jet_e"]
    jet_abs_eta = abs(jet_eta)

    jet_mask = (jet_pt > 30.0) & (jet_abs_eta < 2.5)
    if "jet_jvt" in chunk.fields:
        jet_mask = jet_mask & ((jet_abs_eta >= 2.4) | (chunk["jet_jvt"] >= 0.5))

    jet_pt_sel = jet_pt[jet_mask]
    jet_eta_sel = jet_eta[jet_mask]
    jet_phi_sel = jet_phi[jet_mask]
    jet_e_sel = jet_e[jet_mask]

    jet_order = ak.argsort(jet_pt_sel, axis=1, ascending=False)
    jet_pt_sorted = jet_pt_sel[jet_order]
    jet_eta_sorted = jet_eta_sel[jet_order]
    jet_phi_sorted = jet_phi_sel[jet_order]
    jet_e_sorted = jet_e_sel[jet_order]

    n_jets = ak.values_astype(ak.num(jet_pt_sorted, axis=1), np.int32)
    lead_jet_pt = _safe_first(jet_pt_sorted, 0, 0.0)

    btag_quant = (
        chunk["jet_btag_quantile"]
        if "jet_btag_quantile" in chunk.fields
        else ak.zeros_like(jet_pt)
    )
    n_btag = ak.values_astype(ak.sum(jet_mask & (btag_quant >= 4), axis=1), np.int32)

    dr_lj = np.sqrt(
        (jet_eta_sel - lead_eta) ** 2 + _delta_phi(jet_phi_sel, lead_phi) ** 2
    )
    min_dr_lj = ak.fill_none(ak.min(dr_lj, axis=1, mask_identity=True), np.inf)

    jet100_mask = jet_mask & (jet_pt > 100.0)
    jet100_pt = jet_pt[jet100_mask]
    jet100_eta = jet_eta[jet100_mask]
    jet100_phi = jet_phi[jet100_mask]
    dr_lj100 = np.sqrt(
        (jet100_eta - lead_eta) ** 2 + _delta_phi(jet100_phi, lead_phi) ** 2
    )
    min_dr_lj100 = ak.fill_none(ak.min(dr_lj100, axis=1, mask_identity=True), np.inf)
    dr_lj100_order = ak.argsort(dr_lj100, axis=1, ascending=True)
    jet100_pt_by_dr = jet100_pt[dr_lj100_order]
    closest_jet100_pt = _safe_first(jet100_pt_by_dr, 0, np.nan)

    has_two_jets = n_jets >= 2
    j1_pt = _safe_first(jet_pt_sorted, 0, 0.0)
    j2_pt = _safe_first(jet_pt_sorted, 1, 0.0)
    j1_eta = _safe_first(jet_eta_sorted, 0, 0.0)
    j2_eta = _safe_first(jet_eta_sorted, 1, 0.0)
    j1_phi = _safe_first(jet_phi_sorted, 0, 0.0)
    j2_phi = _safe_first(jet_phi_sorted, 1, 0.0)
    j1_e = _safe_first(jet_e_sorted, 0, 0.0)
    j2_e = _safe_first(jet_e_sorted, 1, 0.0)
    mjj = ak.where(
        has_two_jets,
        _inv_mass_from_pt_eta_phi_e(j1_pt, j1_eta, j1_phi, j1_e, j2_pt, j2_eta, j2_phi, j2_e),
        np.nan,
    )

    met = chunk["met"]
    met_phi = chunk["met_phi"]
    lv_px = lead_pt * np.cos(lead_phi) + met * np.cos(met_phi)
    lv_py = lead_pt * np.sin(lead_phi) + met * np.sin(met_phi)
    pt_lv = np.sqrt(lv_px * lv_px + lv_py * lv_py)
    ptlv_over_ptclosest = ak.where(closest_jet100_pt > 0.0, pt_lv / closest_jet100_pt, np.nan)
    st = lead_pt + met + ak.sum(jet_pt_sorted, axis=1)

    baseline_common = (
        (n_signal == 1)
        & lead_trigger
        & (met > 30.0)
        & (n_jets >= 1)
        & (lead_jet_pt > 500.0)
        & (min_dr_lj > 0.4)
    )
    baseline_sr = baseline_common & (n_btag == 0)

    regions = {
        "SR_inclusive": baseline_sr,
        "SR_inclusive2j": baseline_sr & (n_jets >= 2),
        "SR_collinear": baseline_sr & (min_dr_lj100 < 2.6),
        "SR_back_to_back": baseline_sr & (min_dr_lj100 >= 2.6),
        "CR_ttbar": baseline_common & (n_btag >= 2),
        "CR_Zjets": (
            (n_loose == 2)
            & sfos
            & (loose1_pt > 30.0)
            & (mll > 60.0)
            & (mll < 120.0)
            & (met > 30.0)
            & (n_jets >= 1)
            & (lead_jet_pt > 500.0)
            & (n_btag == 0)
        ),
        "CR_multijet": (
            (n_signal == 0)
            & (n_antiiso == 1)
            & anti_trigger
            & (anti_lead_pt > 30.0)
            & (met > 30.0)
            & (n_jets >= 1)
            & (lead_jet_pt > 500.0)
        ),
        "VR_multijet_lowMET": baseline_sr & (met < 100.0),
    }

    observables = {
        "deltaRmin_l_jet100": min_dr_lj100,
        "ptlv_over_ptclosestjet100": ptlv_over_ptclosest,
        "mjj": mjj,
        "leading_jet_pt": lead_jet_pt,
        "pt_lv": pt_lv,
        "jet_multiplicity": ak.values_astype(n_jets, float),
        "st": st,
        "met": met,
    }

    return {
        "regions": regions,
        "observables": observables,
    }


def _init_histograms() -> Dict[str, Dict[str, Dict[str, np.ndarray]]]:
    out: Dict[str, Dict[str, Dict[str, np.ndarray]]] = {}
    for rid in REGION_ORDER:
        out[rid] = {}
        for obs, spec in OBSERVABLES.items():
            nb = len(spec["bins"]) - 1
            out[rid][obs] = {g: np.zeros(nb, dtype=float) for g in (["data"] + PROCESS_ORDER)}
    return out


def _update_accumulators(
    group: str,
    weights: ak.Array,
    content: Dict[str, Any],
    yields: Dict[str, Dict[str, Dict[str, float]]],
    histos: Dict[str, Dict[str, Dict[str, np.ndarray]]],
) -> None:
    for rid, mask in content["regions"].items():
        if rid not in yields:
            yields[rid] = {}
        if group not in yields[rid]:
            yields[rid][group] = {"sumw": 0.0, "sumw2": 0.0, "n_raw": 0}

        w = _to_numpy(weights[mask])
        yields[rid][group]["sumw"] += float(np.sum(w))
        yields[rid][group]["sumw2"] += float(np.sum(w * w))
        yields[rid][group]["n_raw"] += int(np.sum(_to_numpy(mask)))

        for obs, values in content["observables"].items():
            vals = _to_numpy(values[mask])
            finite = np.isfinite(vals)
            if not np.any(finite):
                continue
            ww = w[finite]
            vv = vals[finite]
            counts, _ = np.histogram(vv, bins=OBSERVABLES[obs]["bins"], weights=ww)
            histos[rid][obs][group] += counts


def _derive_scale_factor(
    yields: Mapping[str, Mapping[str, Mapping[str, float]]],
    region_id: str,
    target_group: str,
    clip_max: float = 5.0,
) -> float:
    if region_id not in yields:
        return 1.0
    region = yields[region_id]
    data = float(region.get("data", {}).get("sumw", 0.0))
    target = float(region.get(target_group, {}).get("sumw", 0.0))
    others = 0.0
    for group in PROCESS_ORDER:
        if group == target_group:
            continue
        others += float(region.get(group, {}).get("sumw", 0.0))
    if target <= 0.0:
        return 1.0
    sf = (data - others) / target
    if not np.isfinite(sf):
        return 1.0
    return float(np.clip(sf, 0.0, clip_max))


def _apply_scale_factors_to_yields(
    yields: Mapping[str, Mapping[str, Mapping[str, float]]],
    scales: Mapping[str, float],
) -> Dict[str, Dict[str, Dict[str, float]]]:
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    for rid, groups in yields.items():
        out[rid] = {}
        for group, vals in groups.items():
            sf = float(scales.get(group, 1.0))
            if group == "data":
                sf = 1.0
            out[rid][group] = {
                "sumw": float(vals.get("sumw", 0.0)) * sf,
                "sumw2": float(vals.get("sumw2", 0.0)) * sf * sf,
                "n_raw": int(vals.get("n_raw", 0)),
            }
    return out


def _apply_scale_factors_to_hists(
    histos: Mapping[str, Mapping[str, Mapping[str, np.ndarray]]],
    scales: Mapping[str, float],
) -> Dict[str, Dict[str, Dict[str, np.ndarray]]]:
    out: Dict[str, Dict[str, Dict[str, np.ndarray]]] = {}
    for rid, obs_map in histos.items():
        out[rid] = {}
        for obs, group_map in obs_map.items():
            out[rid][obs] = {}
            for group, arr in group_map.items():
                sf = float(scales.get(group, 1.0))
                if group == "data":
                    sf = 1.0
                out[rid][obs][group] = arr.astype(float) * sf
    return out


def _plot_stack(
    region_id: str,
    obs_key: str,
    hists_scaled: Mapping[str, Mapping[str, Mapping[str, np.ndarray]]],
    blind_data: bool,
    out_path: Path,
) -> None:
    edges = OBSERVABLES[obs_key]["bins"]
    xlabel = OBSERVABLES[obs_key]["label"]
    width = np.diff(edges)
    centers = 0.5 * (edges[:-1] + edges[1:])

    fig, ax = plt.subplots(figsize=(8, 5))
    bottom = np.zeros_like(centers)
    for group in PROCESS_ORDER:
        vals = np.asarray(hists_scaled[region_id][obs_key].get(group, np.zeros_like(centers)))
        if np.sum(vals) <= 0.0:
            continue
        ax.bar(
            edges[:-1],
            vals,
            width=width,
            align="edge",
            bottom=bottom,
            color=PROCESS_COLORS.get(group, "#999999"),
            edgecolor="white",
            linewidth=0.4,
            label=PROCESS_LABELS.get(group, group),
        )
        bottom = bottom + vals

    data_vals = np.asarray(hists_scaled[region_id][obs_key].get("data", np.zeros_like(centers)))
    if blind_data:
        ax.text(
            0.03,
            0.93,
            "Data blinded",
            transform=ax.transAxes,
            fontsize=10,
            bbox={"facecolor": "white", "edgecolor": "gray", "alpha": 0.9},
        )
    else:
        yerr = np.sqrt(np.clip(data_vals, 0.0, None))
        ax.errorbar(centers, data_vals, yerr=yerr, fmt="o", color="black", ms=3, label="Data")

    ax.step(edges[:-1], bottom, where="post", color="black", linewidth=1.1, label="Total MC")
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Events / bin")
    ax.set_title("{}: {}".format(region_id, obs_key))
    ax.grid(alpha=0.2)
    if np.max(bottom) > 0.0:
        ax.set_ylim(0.0, np.max(bottom) * 1.35)
    ax.legend(fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _format_float(value: float, digits: int = 4) -> str:
    if not np.isfinite(value):
        return "n/a"
    return ("{0:." + str(digits) + "g}").format(value)


def _build_report(
    out_dir: Path,
    report_path: Path,
    yields_raw: Mapping[str, Mapping[str, Mapping[str, float]]],
    yields_scaled: Mapping[str, Mapping[str, Mapping[str, float]]],
    scale_factors: Mapping[str, float],
    lumi_fb: float,
    files_stats: Mapping[str, Any],
    max_events_per_file: Optional[int],
) -> None:
    lumi_pb = float(lumi_fb) * 1000.0

    def _sum_mc(region_id: str, payload: Mapping[str, Mapping[str, Mapping[str, float]]]) -> float:
        return float(
            sum(float(payload.get(region_id, {}).get(g, {}).get("sumw", 0.0)) for g in PROCESS_ORDER)
        )

    lines: List[str] = []
    lines.append("# Blinded W+jets High-pT Analysis (36.1 fb^-1)")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        "This document reports a blinded measurement workflow for W+jets at high jet transverse momentum "
        "using ATLAS open data (target luminosity 36.1 fb^-1)."
    )
    lines.append(
        "Signal regions are blinded for data, while control/validation regions are shown and used to constrain background normalizations."
    )
    lines.append("")
    lines.append("## Dataset and Processing Scope")
    lines.append("")
    lines.append("- Input: `input-data/data` and `input-data/MC`")
    lines.append("- Integrated luminosity used for MC normalization: {} fb^-1".format(_format_float(lumi_fb, 3)))
    lines.append("- Data files processed: {}".format(int(files_stats.get("data_files", 0))))
    lines.append(
        "- MC files available/selected for this analysis model: {}/{}".format(
            int(files_stats.get("mc_selected_files", 0)),
            int(files_stats.get("mc_total_files", 0)),
        )
    )
    if max_events_per_file is None:
        lines.append("- Event cap per file: none (full file processing)")
    else:
        lines.append("- Event cap per file: {}".format(int(max_events_per_file)))
    lines.append("")
    lines.append("## Object and Event Selection")
    lines.append("")
    lines.append("- Exactly one isolated lepton (electron or muon), pT > 30 GeV, trigger matched.")
    lines.append("- MET > 30 GeV.")
    lines.append("- Jets: pT > 30 GeV, |eta| < 2.5, JVT proxy applied in central region.")
    lines.append("- Leading jet pT > 500 GeV.")
    lines.append("- DeltaR(lepton, selected jets) > 0.4.")
    lines.append("- b-jet veto in SRs; ttbar CR uses >=2 b-tagged jets (b-tag proxy from quantile >= 4).")
    lines.append("")
    lines.append("Signal-region definitions:")
    lines.append("- `SR_inclusive`: baseline")
    lines.append("- `SR_inclusive2j`: baseline + >=2 jets")
    lines.append("- `SR_collinear`: baseline + DeltaRmin(l, jet100) < 2.6")
    lines.append("- `SR_back_to_back`: baseline + DeltaRmin(l, jet100) >= 2.6")
    lines.append("")
    lines.append("Control/validation regions:")
    lines.append("- `CR_ttbar`: baseline with >=2 b-tag jets")
    lines.append("- `CR_Zjets`: exactly two SFOS leptons, 60 < mll < 120 GeV, high-pT jet baseline")
    lines.append("- `CR_multijet`: anti-isolated single-lepton selection")
    lines.append("- `VR_multijet_lowMET`: SR-like baseline with MET < 100 GeV")
    lines.append("")
    lines.append("## Background Model and CR Constraints")
    lines.append("")
    lines.append("CR-derived normalization factors (applied globally to yields/plots):")
    lines.append(
        "- ttbar scale from `CR_ttbar`: {}".format(
            _format_float(float(scale_factors.get("ttbar", 1.0)), 4)
        )
    )
    lines.append(
        "- Z+jets scale from `CR_Zjets`: {}".format(
            _format_float(float(scale_factors.get("zjets", 1.0)), 4)
        )
    )
    lines.append("")
    lines.append("## Region Yields")
    lines.append("")
    lines.append(
        "| Region | Data | Total MC (scaled) | Signal W->e/munu | W->taunu | ttbar+X | single-top | Z+jets | diboson | EWK V+jj |"
    )
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for rid in REGION_ORDER:
        region_scaled = yields_scaled.get(rid, {})
        data_val = float(region_scaled.get("data", {}).get("sumw", 0.0))
        if rid in BLIND_SIGNAL_REGIONS:
            data_cell = "BLINDED"
        else:
            data_cell = _format_float(data_val, 5)
        total_mc = _sum_mc(rid, yields_scaled)
        row = [
            rid,
            data_cell,
            _format_float(total_mc, 5),
        ]
        for g in PROCESS_ORDER:
            row.append(_format_float(float(region_scaled.get(g, {}).get("sumw", 0.0)), 5))
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9]
            )
        )
    lines.append("")
    lines.append("## Fiducial Cross-Section Proxies")
    lines.append("")
    lines.append(
        "Expected fiducial cross-section proxies are computed from scaled signal yield as sigma = N_signal / L."
    )
    lines.append("| Region | sigma_exp [fb] | data-bkg sigma [fb] |")
    lines.append("|---|---:|---:|")
    for rid in ["SR_inclusive", "SR_inclusive2j", "SR_collinear", "SR_back_to_back"]:
        sig_y = float(yields_scaled.get(rid, {}).get("signal_wlnu", {}).get("sumw", 0.0))
        bkg_y = float(
            sum(
                float(yields_scaled.get(rid, {}).get(g, {}).get("sumw", 0.0))
                for g in PROCESS_ORDER
                if g != "signal_wlnu"
            )
        )
        data_y = float(yields_scaled.get(rid, {}).get("data", {}).get("sumw", 0.0))
        sigma_exp = sig_y / lumi_pb if lumi_pb > 0.0 else np.nan
        sigma_data_sub = (data_y - bkg_y) / lumi_pb if lumi_pb > 0.0 else np.nan
        data_sub_cell = "BLINDED" if rid in BLIND_SIGNAL_REGIONS else _format_float(sigma_data_sub, 5)
        lines.append("| {} | {} | {} |".format(rid, _format_float(sigma_exp, 5), data_sub_cell))
    lines.append("")
    lines.append("## Plots")
    lines.append("")
    lines.append("All plots are under `plots/`. Signal-region plots are blinded for data by construction.")
    lines.append("")
    for rid in REGION_ORDER:
        plot_dir = out_dir / "plots" / rid
        if not plot_dir.exists():
            continue
        for png in sorted(plot_dir.glob("*.png")):
            rel = Path(os.path.relpath(png, start=report_path.parent)).as_posix()
            lines.append("### {} / {}".format(rid, png.stem))
            lines.append("")
            lines.append("![]({})".format(rel))
            lines.append("")
    lines.append("## Implementation Differences from Reference Analysis")
    lines.append("")
    lines.append(
        "- Reference concept: full 140 fb^-1 Run-2 publication analysis with unfolding and complete nuisance model."
    )
    lines.append(
        "  Open-data implementation: 36.1 fb^-1 normalized reconstruction-level workflow with blinded SRs and CR-driven normalization for major backgrounds."
    )
    lines.append(
        "  Expected impact: absolute precision and unfolded particle-level comparability are reduced."
    )
    lines.append("")
    lines.append(
        "- Reference concept: dedicated b-tag and fake-lepton calibrations."
    )
    lines.append(
        "  Open-data implementation: b-tag proxy from jet quantile and anti-isolation proxy CR for multijet."
    )
    lines.append(
        "  Expected impact: residual normalization/modeling mismatches in heavy-flavor and fake-lepton components."
    )
    lines.append("")
    lines.append(
        "- Reference concept: electron/muon channel unfolding and combination."
    )
    lines.append(
        "  Open-data implementation: combined reconstruction-level e+mu selections in one pass for operational robustness."
    )
    lines.append(
        "  Expected impact: channel-specific systematics and migration effects are not separated."
    )
    lines.append("")
    lines.append("## Reproducibility")
    lines.append("")
    lines.append("- Script: `analysis/wplus_highpt_pipeline.py`")
    lines.append("- Run timestamp (UTC): {}".format(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
    lines.append("- Output directory: `{}`".format(out_dir))

    ensure_dir(report_path.parent)
    report_path.write_text("\n".join(lines) + "\n")


def run_pipeline(
    inputs: Path,
    outputs: Path,
    lumi_fb: float,
    max_events_per_file: Optional[int],
    step_size: str,
) -> Dict[str, Any]:
    ensure_dir(outputs)
    ensure_dir(outputs / "plots")

    samples, sample_counts = _build_sample_list(inputs=inputs, lumi_fb=lumi_fb)
    if not samples:
        raise RuntimeError("No samples selected for W+jets workflow.")

    yields: Dict[str, Dict[str, Dict[str, float]]] = {}
    histos = _init_histograms()
    processed_events_by_group: Dict[str, int] = defaultdict(int)
    file_level_rows: List[Dict[str, Any]] = []

    total_files = len(samples)
    for idx, spec in enumerate(samples, start=1):
        print(
            "[{}/{}] processing {} ({})".format(
                idx,
                total_files,
                spec.path.name,
                spec.group,
            ),
            flush=True,
        )
        file_events = 0
        tree_path = "{}:analysis".format(spec.path)
        for chunk in uproot.iterate(
            [tree_path],
            expressions=BRANCHES,
            library="ak",
            step_size=step_size,
        ):
            if max_events_per_file is not None and file_events >= max_events_per_file:
                break
            if max_events_per_file is not None:
                keep = max_events_per_file - file_events
                if keep <= 0:
                    break
                if len(chunk) > keep:
                    chunk = chunk[:keep]

            file_events += len(chunk)
            processed_events_by_group[spec.group] += len(chunk)

            content = _compute_event_content(chunk)
            weights = ak.Array(np.ones(len(chunk), dtype=np.float64)) if spec.is_data else _mc_weight(chunk, spec.w_norm)
            _update_accumulators(
                group=spec.group,
                weights=weights,
                content=content,
                yields=yields,
                histos=histos,
            )

        file_level_rows.append(
            {
                "file": str(spec.path),
                "group": spec.group,
                "is_data": bool(spec.is_data),
                "w_norm": float(spec.w_norm),
                "events_processed": int(file_events),
            }
        )
        print("  -> events processed: {}".format(file_events), flush=True)

    sf_ttbar = _derive_scale_factor(yields=yields, region_id="CR_ttbar", target_group="ttbar")
    sf_zjets = _derive_scale_factor(yields=yields, region_id="CR_Zjets", target_group="zjets")
    scales = {"ttbar": sf_ttbar, "zjets": sf_zjets}

    yields_scaled = _apply_scale_factors_to_yields(yields=yields, scales=scales)
    histos_scaled = _apply_scale_factors_to_hists(histos=histos, scales=scales)

    plot_index: List[str] = []
    for rid in REGION_ORDER:
        region_plot_dir = ensure_dir(outputs / "plots" / rid)
        for obs in PLOTS_BY_REGION.get(rid, []):
            out_path = region_plot_dir / "{}.png".format(obs)
            _plot_stack(
                region_id=rid,
                obs_key=obs,
                hists_scaled=histos_scaled,
                blind_data=(rid in BLIND_SIGNAL_REGIONS),
                out_path=out_path,
            )
            plot_index.append(str(out_path))

    summary_payload = {
        "lumi_fb": float(lumi_fb),
        "max_events_per_file": int(max_events_per_file) if max_events_per_file is not None else None,
        "step_size": step_size,
        "sample_counts": sample_counts,
        "processed_events_by_group": {k: int(v) for k, v in sorted(processed_events_by_group.items())},
        "scale_factors": scales,
        "yields_raw": yields,
        "yields_scaled": yields_scaled,
        "plots": plot_index,
    }
    write_json(outputs / "summary.json", summary_payload)
    write_json(outputs / "file_manifest.json", {"rows": file_level_rows, "n_rows": len(file_level_rows)})

    report_path = outputs / "report" / "wplus_highpt_blinded_report.md"
    _build_report(
        out_dir=outputs,
        report_path=report_path,
        yields_raw=yields,
        yields_scaled=yields_scaled,
        scale_factors=scales,
        lumi_fb=lumi_fb,
        files_stats=sample_counts,
        max_events_per_file=max_events_per_file,
    )

    return {
        "outputs": str(outputs),
        "summary": str(outputs / "summary.json"),
        "report": str(report_path),
        "file_manifest": str(outputs / "file_manifest.json"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run blinded W+jets high-pT analysis workflow")
    parser.add_argument("--inputs", default="input-data", help="Input directory with data/ and MC/")
    parser.add_argument("--outputs", default=None, help="Output directory (defaults to timestamped)")
    parser.add_argument("--lumi-fb", type=float, default=LUMI_FB_DEFAULT)
    parser.add_argument(
        "--max-events-per-file",
        type=int,
        default=350000,
        help="Per-file event cap for practical turnaround; set <=0 for full-file processing.",
    )
    parser.add_argument("--step-size", default="80 MB", help="uproot iterate step size")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    max_events = int(args.max_events_per_file)
    if max_events <= 0:
        max_events = None

    if args.outputs:
        outputs = Path(args.outputs)
    else:
        run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        outputs = Path("outputs_wplus_highpt_{}".format(run_id))

    result = run_pipeline(
        inputs=Path(args.inputs),
        outputs=outputs,
        lumi_fb=float(args.lumi_fb),
        max_events_per_file=max_events,
        step_size=str(args.step_size),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
