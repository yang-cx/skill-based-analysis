# FILE: analysis/selections/regions.py
"""Selection engine: apply region selections to events."""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import awkward as ak
import numpy as np

from analysis.common import ensure_dir, write_json
from analysis.io.readers import load_events

# ------------------------------------------------------------------
# Physical constants / thresholds
# ------------------------------------------------------------------
MGG_LOW = 105.0   # GeV
MGG_HIGH = 160.0  # GeV
MGG_BLIND_LOW = 120.0
MGG_BLIND_HIGH = 130.0
LEAD_PT_MIN = 40.0   # GeV
SUBLEAD_PT_MIN = 30.0  # GeV
ETA_BARREL_MAX = 1.37
ETA_CRACK_LOW = 1.37
ETA_CRACK_HIGH = 1.52
ETA_TRANSITION_LOW = 1.3
ETA_TRANSITION_HIGH = 1.75
ETA_ENDCAP_MAX = 2.37
ETA_CENTRAL = 0.75

PTT_SPLIT = 60.0  # GeV

# VBF jet cuts
VBF_JET_PT_MIN = 25.0   # GeV
VBF_JET_ETA_MAX = 4.5
VBF_DETA_JJ_MIN = 2.8
VBF_MJJ_MIN = 400.0  # GeV
VBF_DPHI_GG_JJ_MIN = 2.6  # rad


# ------------------------------------------------------------------
# Utility: compute diphoton invariant mass
# ------------------------------------------------------------------
def compute_mgg(pt1, eta1, phi1, e1, pt2, eta2, phi2, e2):
    """Compute diphoton invariant mass in GeV.

    Uses 4-momentum addition: m^2 = (E1+E2)^2 - |p1+p2|^2
    """
    # Convert to Cartesian
    px1 = pt1 * np.cos(phi1)
    py1 = pt1 * np.sin(phi1)
    pz1 = pt1 * np.sinh(eta1)
    px2 = pt2 * np.cos(phi2)
    py2 = pt2 * np.sin(phi2)
    pz2 = pt2 * np.sinh(eta2)

    px = px1 + px2
    py = py1 + py2
    pz = pz1 + pz2
    E = e1 + e2

    m2 = E ** 2 - (px ** 2 + py ** 2 + pz ** 2)
    # Protect against numerical issues
    m2 = np.maximum(m2, 0.0)
    return np.sqrt(m2)


def compute_diphoton_kinematics(pt1, eta1, phi1, e1, pt2, eta2, phi2, e2):
    """Compute diphoton system kinematics: mgg, pt_gg, eta_gg, phi_gg."""
    px1 = pt1 * np.cos(phi1)
    py1 = pt1 * np.sin(phi1)
    pz1 = pt1 * np.sinh(eta1)
    px2 = pt2 * np.cos(phi2)
    py2 = pt2 * np.sin(phi2)
    pz2 = pt2 * np.sinh(eta2)

    px = px1 + px2
    py = py1 + py2
    pz = pz1 + pz2
    E = e1 + e2

    pt_gg = np.sqrt(px ** 2 + py ** 2)
    phi_gg = np.arctan2(py, px)
    eta_gg = np.where(pt_gg > 0, np.arcsinh(pz / (pt_gg + 1e-30)), 0.0)

    m2 = np.maximum(E ** 2 - (px ** 2 + py ** 2 + pz ** 2), 0.0)
    mgg = np.sqrt(m2)

    return mgg, pt_gg, phi_gg, eta_gg


def compute_ptt(pt1, phi1, pt2, phi2, pt_gg, phi_gg):
    """Compute pTt: component of diphoton pT orthogonal to (p1_T - p2_T) direction.

    pTt = |p_gg_T x p̂_12| where p̂_12 = unit vector along (p1_T - p2_T)

    Cross product in 2D (z-component):
    pTt = |p_gg_x * (py1 - py2) - p_gg_y * (px1 - px2)| / |p1_T - p2_T|
    """
    px1 = pt1 * np.cos(phi1)
    py1 = pt1 * np.sin(phi1)
    px2 = pt2 * np.cos(phi2)
    py2 = pt2 * np.sin(phi2)

    px_gg = pt_gg * np.cos(phi_gg)
    py_gg = pt_gg * np.sin(phi_gg)

    dpx = px1 - px2
    dpy = py1 - py2
    dp_mag = np.sqrt(dpx ** 2 + dpy ** 2)

    # Cross product magnitude (2D): |a x b| = |ax*by - ay*bx|
    cross = np.abs(px_gg * dpy - py_gg * dpx)

    # Avoid division by zero
    ptt = np.where(dp_mag > 1e-10, cross / dp_mag, 0.0)
    return ptt


# ------------------------------------------------------------------
# Photon selection helpers
# ------------------------------------------------------------------
def _safe_to_numpy(arr):
    """Convert awkward array to numpy, handling ragged arrays."""
    try:
        return np.asarray(arr)
    except Exception:
        return ak.to_numpy(arr)


def _get_scalar(data: Dict, key: str, n_events: int) -> Optional[np.ndarray]:
    """Get a scalar branch as numpy array."""
    if key not in data:
        return None
    arr = data[key]
    try:
        result = np.asarray(arr)
        if result.shape == () or len(result) == 0:
            return result
        return result
    except Exception:
        try:
            return ak.to_numpy(arr)
        except Exception:
            return None


def _get_photon_branch(data: Dict, key: str) -> Optional[ak.Array]:
    """Get a per-photon (jagged) branch."""
    if key not in data:
        return None
    arr = data[key]
    if isinstance(arr, ak.Array):
        return arr
    try:
        return ak.Array(arr)
    except Exception:
        return None


def _extract_leading_pair_vectorized(pt_arr, eta_arr, phi_arr, e_arr, tight_arr=None):
    """Vectorized extraction of leading/subleading photons using awkward arrays.

    Applies tight-ID filter if tight_arr is provided.
    Returns (pt1, eta1, phi1, e1, pt2, eta2, phi2, e2, mask_ge2).
    """
    n_events = len(pt_arr)

    # Apply tight ID mask if available
    if tight_arr is not None:
        try:
            tight_bool = tight_arr.astype(bool) if hasattr(tight_arr, 'astype') else tight_arr == True
            pt_sel = pt_arr[tight_bool]
            eta_sel = eta_arr[tight_bool]
            phi_sel = phi_arr[tight_bool]
            e_sel = e_arr[tight_bool]
        except Exception:
            pt_sel, eta_sel, phi_sel, e_sel = pt_arr, eta_arr, phi_arr, e_arr
    else:
        pt_sel, eta_sel, phi_sel, e_sel = pt_arr, eta_arr, phi_arr, e_arr

    # Sort each event by pT descending using awkward argsort
    try:
        order = ak.argsort(pt_sel, axis=1, ascending=False, stable=True)
        pt_sorted = pt_sel[order]
        eta_sorted = eta_sel[order]
        phi_sorted = phi_sel[order]
        e_sorted = e_sel[order]

        n_tight = ak.to_numpy(ak.num(pt_sorted))
        mask_ge2 = n_tight >= 2

        # Pad to at least 2 entries so indexing is safe
        pt_pad = ak.pad_none(pt_sorted, 2, clip=True)
        eta_pad = ak.pad_none(eta_sorted, 2, clip=True)
        phi_pad = ak.pad_none(phi_sorted, 2, clip=True)
        e_pad = ak.pad_none(e_sorted, 2, clip=True)

        pt1 = ak.to_numpy(ak.fill_none(pt_pad[:, 0], 0.0))
        eta1 = ak.to_numpy(ak.fill_none(eta_pad[:, 0], 0.0))
        phi1 = ak.to_numpy(ak.fill_none(phi_pad[:, 0], 0.0))
        e1 = ak.to_numpy(ak.fill_none(e_pad[:, 0], 0.0))
        pt2 = ak.to_numpy(ak.fill_none(pt_pad[:, 1], 0.0))
        eta2 = ak.to_numpy(ak.fill_none(eta_pad[:, 1], 0.0))
        phi2 = ak.to_numpy(ak.fill_none(phi_pad[:, 1], 0.0))
        e2 = ak.to_numpy(ak.fill_none(e_pad[:, 1], 0.0))

        return pt1, eta1, phi1, e1, pt2, eta2, phi2, e2, mask_ge2
    except Exception as exc:
        # Slow fallback
        return _extract_leading_pair_loop(pt_arr, eta_arr, phi_arr, e_arr, tight_arr)


def _extract_leading_pair_loop(pt_arr, eta_arr, phi_arr, e_arr, tight_arr=None):
    """Slow loop-based fallback for leading pair extraction."""
    n_events = len(pt_arr)
    pt1 = np.zeros(n_events); eta1 = np.zeros(n_events)
    phi1 = np.zeros(n_events); e1 = np.zeros(n_events)
    pt2 = np.zeros(n_events); eta2 = np.zeros(n_events)
    phi2 = np.zeros(n_events); e2 = np.zeros(n_events)
    mask_ge2 = np.zeros(n_events, dtype=bool)

    for i in range(n_events):
        try:
            pts = np.asarray(pt_arr[i])
            etas = np.asarray(eta_arr[i])
            phis = np.asarray(phi_arr[i])
            es = np.asarray(e_arr[i])
            if tight_arr is not None:
                try:
                    tight = np.asarray(tight_arr[i]).astype(bool)
                    if len(tight) == len(pts):
                        pts = pts[tight]; etas = etas[tight]
                        phis = phis[tight]; es = es[tight]
                except Exception:
                    pass
            if len(pts) >= 2:
                order = np.argsort(pts)[::-1]
                pt1[i] = pts[order[0]]; eta1[i] = etas[order[0]]
                phi1[i] = phis[order[0]]; e1[i] = es[order[0]]
                pt2[i] = pts[order[1]]; eta2[i] = etas[order[1]]
                phi2[i] = phis[order[1]]; e2[i] = es[order[1]]
                mask_ge2[i] = True
        except Exception:
            pass
    return pt1, eta1, phi1, e1, pt2, eta2, phi2, e2, mask_ge2


def extract_leading_photons(data: Dict) -> Optional[Tuple]:
    """Extract leading and subleading photon properties (vectorized)."""
    pt_arr = _get_photon_branch(data, "photon_pt")
    eta_arr = _get_photon_branch(data, "photon_eta")
    phi_arr = _get_photon_branch(data, "photon_phi")
    e_arr = _get_photon_branch(data, "photon_e")
    if pt_arr is None or eta_arr is None or phi_arr is None or e_arr is None:
        return None
    return _extract_leading_pair_vectorized(pt_arr, eta_arr, phi_arr, e_arr)


def extract_tight_photons(data: Dict) -> Optional[np.ndarray]:
    """Count tight-ID photons per event (vectorized)."""
    tight_arr = _get_photon_branch(data, "photon_isTightID")
    if tight_arr is None:
        return None
    try:
        tight_bool = tight_arr == True  # noqa: E712
        return ak.to_numpy(ak.sum(tight_bool, axis=1))
    except Exception:
        n_events = len(tight_arr)
        n_tight = np.zeros(n_events, dtype=int)
        for i in range(n_events):
            try:
                n_tight[i] = int(np.sum(np.asarray(tight_arr[i]).astype(bool)))
            except Exception:
                pass
        return n_tight


def extract_tight_leading_photons(data: Dict) -> Optional[Tuple]:
    """Extract leading/subleading photons requiring tight ID (vectorized)."""
    pt_arr = _get_photon_branch(data, "photon_pt")
    eta_arr = _get_photon_branch(data, "photon_eta")
    phi_arr = _get_photon_branch(data, "photon_phi")
    e_arr = _get_photon_branch(data, "photon_e")
    tight_arr = _get_photon_branch(data, "photon_isTightID")

    if pt_arr is None or eta_arr is None or phi_arr is None or e_arr is None:
        return None

    return _extract_leading_pair_vectorized(pt_arr, eta_arr, phi_arr, e_arr, tight_arr)


def extract_tight_photon_property(data: Dict, prop_key: str) -> Optional[Tuple]:
    """Extract a per-photon property for the leading/subleading tight photons.

    Returns (prop1, prop2) numpy arrays sorted the same way as extract_tight_leading_photons.
    """
    pt_arr = _get_photon_branch(data, "photon_pt")
    prop_arr = _get_photon_branch(data, prop_key)
    tight_arr = _get_photon_branch(data, "photon_isTightID")

    if pt_arr is None or prop_arr is None:
        return None

    try:
        # Apply tight ID
        if tight_arr is not None:
            tight_bool = tight_arr == True  # noqa: E712
            pt_sel = pt_arr[tight_bool]
            prop_sel = prop_arr[tight_bool]
        else:
            pt_sel = pt_arr
            prop_sel = prop_arr

        # Sort by pT descending (same order as extract_tight_leading_photons)
        order = ak.argsort(pt_sel, axis=1, ascending=False, stable=True)
        prop_sorted = prop_sel[order]

        prop_pad = ak.pad_none(prop_sorted, 2, clip=True)
        prop1 = ak.to_numpy(ak.fill_none(prop_pad[:, 0], 0.0))
        prop2 = ak.to_numpy(ak.fill_none(prop_pad[:, 1], 0.0))
        return prop1, prop2
    except Exception:
        n = len(pt_arr) if pt_arr is not None else 0
        return np.zeros(n), np.zeros(n)


# ------------------------------------------------------------------
# Photon kinematic quality checks
# ------------------------------------------------------------------
def passes_eta_acceptance(eta: np.ndarray) -> np.ndarray:
    """Check photon is in |eta| < 2.37 excluding crack 1.37-1.52."""
    abs_eta = np.abs(eta)
    in_barrel = abs_eta < ETA_BARREL_MAX
    in_endcap = (abs_eta >= ETA_CRACK_HIGH) & (abs_eta < ETA_ENDCAP_MAX)
    return in_barrel | in_endcap


def is_unconv_proxy(
    eta1: np.ndarray,
    eta2: np.ndarray,
    ptcone20_1: Optional[np.ndarray] = None,
    ptcone20_2: Optional[np.ndarray] = None,
    pt1: Optional[np.ndarray] = None,
    pt2: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Proxy for 'both photons unconverted'.

    Primary proxy: relative track isolation ptcone20/pT < 0.04 for both photons.
    Unconverted photons have fewer associated tracks → lower ptcone20.
    Converted photons tend to have higher ptcone20 due to e+e- tracks.
    Fallback: both photons in barrel |eta| < 0.9 (inner barrel, lower material).
    """
    if ptcone20_1 is not None and ptcone20_2 is not None and pt1 is not None and pt2 is not None:
        # Relative track isolation proxy (threshold 0.04 = 4%)
        safe_pt1 = np.where(pt1 > 1.0, pt1, 1.0)
        safe_pt2 = np.where(pt2 > 1.0, pt2, 1.0)
        rel_iso1 = ptcone20_1 / safe_pt1
        rel_iso2 = ptcone20_2 / safe_pt2
        return (rel_iso1 < 0.04) & (rel_iso2 < 0.04)
    # Fallback: inner barrel proxy
    return (np.abs(eta1) < 0.9) & (np.abs(eta2) < 0.9)


def is_transition(eta1: np.ndarray, eta2: np.ndarray) -> np.ndarray:
    """At least one photon has 1.3 < |eta| < 1.75."""
    t1 = (np.abs(eta1) > ETA_TRANSITION_LOW) & (np.abs(eta1) < ETA_TRANSITION_HIGH)
    t2 = (np.abs(eta2) > ETA_TRANSITION_LOW) & (np.abs(eta2) < ETA_TRANSITION_HIGH)
    return t1 | t2


def is_central(eta1: np.ndarray, eta2: np.ndarray) -> np.ndarray:
    """Both photons have |eta| < 0.75."""
    return (np.abs(eta1) < ETA_CENTRAL) & (np.abs(eta2) < ETA_CENTRAL)


# ------------------------------------------------------------------
# Jet kinematics for VBF
# ------------------------------------------------------------------
def extract_vbf_jets(data: Dict):
    """Extract leading/subleading VBF-quality jets (vectorized).

    Returns (n_vbf, vbf_topo, jpt1, jeta1, jphi1, je1, jpt2, jeta2, jphi2, je2).
    """
    jet_pt_arr = _get_photon_branch(data, "jet_pt")
    jet_eta_arr = _get_photon_branch(data, "jet_eta")
    jet_phi_arr = _get_photon_branch(data, "jet_phi")
    jet_e_arr = _get_photon_branch(data, "jet_e")
    jet_jvt_arr = _get_photon_branch(data, "jet_jvt")

    # Determine n_events from photon array
    ph_pt = data.get("photon_pt")
    n_events = len(ph_pt) if ph_pt is not None else 0

    _zero = np.zeros(n_events)
    _zero_int = np.zeros(n_events, dtype=int)
    _zero_bool = np.zeros(n_events, dtype=bool)

    if jet_pt_arr is None or jet_eta_arr is None:
        return _zero_int, _zero_bool, _zero, _zero, _zero, _zero, _zero, _zero, _zero, _zero

    try:
        # Apply JVT for central jets (|eta| < 2.5)
        if jet_jvt_arr is not None:
            central_mask = np.abs(jet_eta_arr) < 2.5
            jvt_ok = ak.where(central_mask, jet_jvt_arr > 0.59, True)
        else:
            jvt_ok = ak.ones_like(jet_pt_arr, dtype=bool)

        # Apply VBF quality cuts
        pt_cut = jet_pt_arr > VBF_JET_PT_MIN
        eta_cut = np.abs(jet_eta_arr) < VBF_JET_ETA_MAX
        quality = pt_cut & eta_cut & jvt_ok

        # Select good jets
        jpt_sel = jet_pt_arr[quality]
        jeta_sel = jet_eta_arr[quality]
        jphi_sel = jet_phi_arr[quality] if jet_phi_arr is not None else ak.zeros_like(jpt_sel)
        je_sel = jet_e_arr[quality] if jet_e_arr is not None else ak.zeros_like(jpt_sel)

        # Count VBF jets per event
        n_vbf = ak.to_numpy(ak.num(jpt_sel)).astype(int)

        # Sort by pT descending
        order = ak.argsort(jpt_sel, axis=1, ascending=False, stable=True)
        jpt_s = jpt_sel[order]
        jeta_s = jeta_sel[order]
        jphi_s = jphi_sel[order]
        je_s = je_sel[order]

        # Pad to at least 2 entries
        jpt_p = ak.pad_none(jpt_s, 2, clip=True)
        jeta_p = ak.pad_none(jeta_s, 2, clip=True)
        jphi_p = ak.pad_none(jphi_s, 2, clip=True)
        je_p = ak.pad_none(je_s, 2, clip=True)

        jpt1 = ak.to_numpy(ak.fill_none(jpt_p[:, 0], 0.0))
        jeta1 = ak.to_numpy(ak.fill_none(jeta_p[:, 0], 0.0))
        jphi1 = ak.to_numpy(ak.fill_none(jphi_p[:, 0], 0.0))
        je1 = ak.to_numpy(ak.fill_none(je_p[:, 0], 0.0))
        jpt2 = ak.to_numpy(ak.fill_none(jpt_p[:, 1], 0.0))
        jeta2 = ak.to_numpy(ak.fill_none(jeta_p[:, 1], 0.0))
        jphi2 = ak.to_numpy(ak.fill_none(jphi_p[:, 1], 0.0))
        je2 = ak.to_numpy(ak.fill_none(je_p[:, 1], 0.0))

        return n_vbf, _zero_bool, jpt1, jeta1, jphi1, je1, jpt2, jeta2, jphi2, je2

    except Exception:
        # Fallback: return zeros
        return _zero_int, _zero_bool, _zero, _zero, _zero, _zero, _zero, _zero, _zero, _zero


def compute_dijet_kinematics(jpt1, jeta1, jphi1, je1, jpt2, jeta2, jphi2, je2):
    """Compute dijet invariant mass and delta_eta."""
    jpx1 = jpt1 * np.cos(jphi1)
    jpy1 = jpt1 * np.sin(jphi1)
    jpz1 = jpt1 * np.sinh(jeta1)
    jpx2 = jpt2 * np.cos(jphi2)
    jpy2 = jpt2 * np.sin(jphi2)
    jpz2 = jpt2 * np.sinh(jeta2)

    px = jpx1 + jpx2
    py = jpy1 + jpy2
    pz = jpz1 + jpz2
    E = je1 + je2
    phi_jj = np.arctan2(py, px)

    m2 = np.maximum(E ** 2 - (px ** 2 + py ** 2 + pz ** 2), 0.0)
    mjj = np.sqrt(m2)
    deta_jj = np.abs(jeta1 - jeta2)

    return mjj, deta_jj, phi_jj


def compute_dphi(phi1: np.ndarray, phi2: np.ndarray) -> np.ndarray:
    """Compute |delta phi| in [0, pi]."""
    dphi = np.abs(phi1 - phi2)
    dphi = np.where(dphi > np.pi, 2 * np.pi - dphi, dphi)
    return dphi


# ------------------------------------------------------------------
# Event weight extraction
# ------------------------------------------------------------------
def extract_event_weights(data: Dict, norm_factor: float, is_data: bool) -> np.ndarray:
    """Extract per-event weights."""
    n_events = 0
    for key in ["photon_pt", "photon_n", "mcWeight"]:
        if key in data:
            try:
                n_events = len(data[key])
                break
            except Exception:
                pass

    if n_events == 0:
        return np.ones(0)

    if is_data:
        return np.ones(n_events)

    mc_weight = np.ones(n_events)
    sf_pileup = np.ones(n_events)
    sf_photon = np.ones(n_events)

    if "mcWeight" in data:
        try:
            mc_weight = np.asarray(data["mcWeight"]).astype(float)
        except Exception:
            pass

    if "ScaleFactor_PILEUP" in data:
        try:
            sf_pileup = np.asarray(data["ScaleFactor_PILEUP"]).astype(float)
        except Exception:
            pass

    if "ScaleFactor_PHOTON" in data:
        try:
            sf_photon = np.asarray(data["ScaleFactor_PHOTON"]).astype(float)
        except Exception:
            pass

    return mc_weight * sf_pileup * sf_photon * norm_factor


# ------------------------------------------------------------------
# Main baseline selection
# ------------------------------------------------------------------
def apply_baseline_diphoton_selection(data: Dict) -> Dict:
    """Apply baseline diphoton selection.

    Requires:
    - >= 2 tight photons
    - Lead pT > 40 GeV, sublead pT > 30 GeV
    - Both photons in eta acceptance (|eta|<2.37, not crack)
    - 105 < mgg < 160 GeV

    Returns dict of per-event numpy arrays.
    """
    result = extract_tight_leading_photons(data)
    if result is None:
        return {}

    pt1, eta1, phi1, e1, pt2, eta2, phi2, e2, mask_ge2 = result

    n_events = len(pt1)

    # Kinematic cuts
    pass_ge2 = mask_ge2
    pass_lead_pt = pt1 > LEAD_PT_MIN
    pass_sublead_pt = pt2 > SUBLEAD_PT_MIN
    pass_eta1 = passes_eta_acceptance(eta1)
    pass_eta2 = passes_eta_acceptance(eta2)
    pass_eta = pass_eta1 & pass_eta2

    # Compute mgg
    mgg, pt_gg, phi_gg, eta_gg = compute_diphoton_kinematics(pt1, eta1, phi1, e1, pt2, eta2, phi2, e2)
    pass_mgg = (mgg > MGG_LOW) & (mgg < MGG_HIGH)

    # Combined baseline
    baseline = pass_ge2 & pass_lead_pt & pass_sublead_pt & pass_eta & pass_mgg

    # pTt
    ptt = compute_ptt(pt1, phi1, pt2, phi2, pt_gg, phi_gg)

    # Conversion proxy using ptcone20/pT ratio
    ptcone20_result = extract_tight_photon_property(data, "photon_ptcone20")
    if ptcone20_result is not None:
        ptcone20_1, ptcone20_2 = ptcone20_result
        unconv = is_unconv_proxy(eta1, eta2, ptcone20_1, ptcone20_2, pt1, pt2)
    else:
        unconv = is_unconv_proxy(eta1, eta2)
    conv = ~unconv
    central = is_central(eta1, eta2)
    transition = is_transition(eta1, eta2)
    rest = ~central & ~transition

    return {
        "baseline_mask": baseline,
        "pt1": pt1, "eta1": eta1, "phi1": phi1, "e1": e1,
        "pt2": pt2, "eta2": eta2, "phi2": phi2, "e2": e2,
        "mgg": mgg,
        "pt_gg": pt_gg,
        "phi_gg": phi_gg,
        "ptt": ptt,
        "unconv": unconv,
        "conv": conv,
        "central": central,
        "rest": rest,
        "transition": transition,
        "n_events": n_events,
    }


def apply_vbf_category(sel: Dict, data: Dict) -> np.ndarray:
    """Identify VBF 2-jet events."""
    if not sel:
        return np.zeros(0, dtype=bool)

    baseline = sel["baseline_mask"]
    phi_gg = sel["phi_gg"]

    # Get jet info
    jet_result = extract_vbf_jets(data)
    n_vbf, _, jpt1, jeta1, jphi1, je1, jpt2, jeta2, jphi2, je2 = jet_result

    mjj, deta_jj, phi_jj = compute_dijet_kinematics(jpt1, jeta1, jphi1, je1, jpt2, jeta2, jphi2, je2)
    dphi_gg_jj = compute_dphi(phi_gg, phi_jj)

    vbf_2jet = (
        baseline
        & (n_vbf >= 2)
        & (deta_jj > VBF_DETA_JJ_MIN)
        & (mjj > VBF_MJJ_MIN)
        & (dphi_gg_jj > VBF_DPHI_GG_JJ_MIN)
    )
    return vbf_2jet


def apply_region_selections(data: Dict, norm_factor: float = 1.0, is_data: bool = False) -> Dict[str, np.ndarray]:
    """Apply all region selections. Returns dict mapping region_id -> boolean mask."""
    sel = apply_baseline_diphoton_selection(data)
    if not sel:
        return {}

    baseline = sel["baseline_mask"]
    mgg = sel["mgg"]
    ptt = sel["ptt"]
    unconv = sel["unconv"]
    conv = sel["conv"]
    central = sel["central"]
    rest = sel["rest"]
    transition = sel["transition"]

    # Sideband mask (for CR)
    sideband = ((mgg >= MGG_LOW) & (mgg < MGG_BLIND_LOW)) | ((mgg > MGG_BLIND_HIGH) & (mgg <= MGG_HIGH))

    # VBF 2-jet category (first priority)
    vbf_mask = apply_vbf_category(sel, data)
    non_vbf = baseline & ~vbf_mask

    # Transition category: at least one photon with 1.3 < |eta| < 1.75
    # (but not VBF)
    transition_mask = non_vbf & transition

    # Remaining after VBF and transition
    remain = non_vbf & ~transition

    # --- Define 8 categories based on conv/unconv x central/rest x ptt ---
    ptt_low = ptt < PTT_SPLIT
    ptt_high = ptt >= PTT_SPLIT

    regions = {
        # Inclusive SR
        "SR_DIPHOTON_INCL": baseline,

        # Control region: sidebands
        "CR_BKG_SHAPE_CHECKS": baseline & sideband,

        # VBF 2-jet
        "SR_2JET": vbf_mask,

        # Transition (no pTt split)
        "SR_CONV_TRANSITION": transition_mask,

        # Unconverted central
        "SR_UNCONV_CENTRAL_LOW_PTT": remain & unconv & central & ptt_low,
        "SR_UNCONV_CENTRAL_HIGH_PTT": remain & unconv & central & ptt_high,

        # Unconverted rest
        "SR_UNCONV_REST_LOW_PTT": remain & unconv & rest & ptt_low,
        "SR_UNCONV_REST_HIGH_PTT": remain & unconv & rest & ptt_high,

        # Converted central
        "SR_CONV_CENTRAL_LOW_PTT": remain & conv & central & ptt_low,
        "SR_CONV_CENTRAL_HIGH_PTT": remain & conv & central & ptt_high,

        # Converted rest
        "SR_CONV_REST_LOW_PTT": remain & conv & rest & ptt_low,
        "SR_CONV_REST_HIGH_PTT": remain & conv & rest & ptt_high,
    }

    return regions, sel, mgg, ptt


def run_region_selection(
    sample_id: str,
    registry: Dict,
    regions_yaml_path: Optional[str] = None,
    out_path: Optional[str] = None,
) -> Dict:
    """Run region selection for a sample and return yield summary."""
    samples = registry.get("samples", registry)
    if sample_id not in samples:
        raise KeyError(f"Sample '{sample_id}' not found in registry.")

    sample_info = samples[sample_id]
    files = sample_info.get("files", [])
    sample_type = sample_info.get("type", "other")
    norm_factor = sample_info.get("norm_factor") or 1.0
    is_data = sample_type == "data"

    print(f"Loading sample {sample_id} ({sample_type}), {len(files)} file(s)...")

    # Key branches needed for selection
    branches = [
        "photon_pt", "photon_eta", "photon_phi", "photon_e",
        "photon_n", "photon_isTightID", "photon_isTightIso",
        "photon_ptcone20", "photon_topoetcone40",
        "jet_pt", "jet_eta", "jet_phi", "jet_e", "jet_jvt",
        "mcWeight", "ScaleFactor_PILEUP", "ScaleFactor_PHOTON",
    ]

    data = load_events(files, branches=branches)
    if not data:
        print(f"Warning: no data loaded for sample {sample_id}")
        return {}

    weights = extract_event_weights(data, norm_factor, is_data)

    try:
        result = apply_region_selections(data, norm_factor=norm_factor, is_data=is_data)
    except Exception as e:
        print(f"Error in region selection for {sample_id}: {e}")
        return {}

    regions, sel, mgg, ptt = result

    # Compute yields per region
    yields = {}
    for region_id, mask in regions.items():
        if len(mask) == 0:
            yields[region_id] = {"n_raw": 0, "yield": 0.0, "sumw2": 0.0}
            continue

        n_raw = int(np.sum(mask))
        w = weights[mask]
        yield_val = float(np.sum(w))
        sumw2 = float(np.sum(w ** 2))
        yields[region_id] = {
            "n_raw": n_raw,
            "yield": yield_val,
            "sumw2": sumw2,
        }

    output = {
        "sample_id": sample_id,
        "type": sample_type,
        "norm_factor": norm_factor,
        "n_events_processed": len(weights),
        "regions": yields,
    }

    if out_path is not None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        write_json(out_path, output)
        print(f"Written region yields to {out_path}")

    return output


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Apply region selections to events.")
    p.add_argument("--sample", required=True, help="Sample ID from registry")
    p.add_argument("--registry", required=True, help="Path to samples.registry.json")
    p.add_argument("--regions", default=None, help="Path to regions.yaml (optional)")
    p.add_argument(
        "--out",
        required=True,
        help="Output JSON file path for region yields",
    )
    return p


def main():
    args = build_parser().parse_args()

    with open(args.registry) as f:
        registry = json.load(f)

    result = run_region_selection(
        sample_id=args.sample,
        registry=registry,
        regions_yaml_path=args.regions,
        out_path=args.out,
    )

    if result:
        print(f"Region yields for {args.sample}:")
        for region_id, info in result.get("regions", {}).items():
            print(f"  {region_id}: n_raw={info['n_raw']}, yield={info['yield']:.2f}")


if __name__ == "__main__":
    main()
