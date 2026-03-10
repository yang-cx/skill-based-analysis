import argparse
from pathlib import Path
from typing import Any, Dict

import awkward as ak
import numpy as np
import yaml

from analysis.io.readers import load_events
from analysis.common import ensure_dir, read_json



def _as_bool(arr: ak.Array) -> ak.Array:
    return ak.values_astype(arr, np.bool_)



def _safe_first(arr: ak.Array, index: int, default: float = 0.0) -> ak.Array:
    padded = ak.pad_none(arr, index + 1, axis=1, clip=True)
    out = padded[:, index]
    return ak.fill_none(out, default)



def _delta_phi(phi1: ak.Array, phi2: ak.Array) -> ak.Array:
    dphi = phi1 - phi2
    return (dphi + np.pi) % (2 * np.pi) - np.pi



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
    m2 = ak.where(m2 < 0, 0, m2)
    return np.sqrt(m2)



def _load_photon_cfg(regions_path: Path) -> Dict[str, Any]:
    with regions_path.open() as f:
        regions = yaml.safe_load(f)
    globals_cfg = regions.get("globals", {}) if isinstance(regions, dict) else {}
    photons = globals_cfg.get("photons", {}) if isinstance(globals_cfg, dict) else {}
    return photons



def build_photons(events: ak.Array, cfg: Dict[str, Any]) -> ak.Array:
    if "photon_pt" not in events.fields:
        raise RuntimeError("photon branches are missing from events")

    min_pt = float(cfg.get("min_pt_gev", 25.0))
    max_abs_eta = float(cfg.get("max_abs_eta", 2.37))
    crack_veto = bool(cfg.get("crack_veto", True))
    iso_cfg = cfg.get("iso", "not_specified")

    photon_pt = events["photon_pt"]
    photon_eta = events["photon_eta"]
    photon_phi = events["photon_phi"]
    photon_e = events["photon_e"]
    photon_topo = (
        events["photon_topoetcone40"]
        if "photon_topoetcone40" in events.fields
        else ak.zeros_like(photon_pt)
    )

    mask = photon_pt > min_pt
    mask = mask & (abs(photon_eta) < max_abs_eta)

    if crack_veto:
        abs_eta = abs(photon_eta)
        mask = mask & ~((abs_eta > 1.37) & (abs_eta < 1.52))

    if "photon_isTightID" in events.fields:
        mask = mask & _as_bool(events["photon_isTightID"])

    if iso_cfg == "tight" and "photon_isTightIso" in events.fields:
        mask = mask & _as_bool(events["photon_isTightIso"])
    elif iso_cfg == "loose" and "photon_isLooseIso" in events.fields:
        mask = mask & _as_bool(events["photon_isLooseIso"])
    elif iso_cfg == "not_specified":
        # Open-data approximation: use tight isolation when available.
        if "photon_isTightIso" in events.fields:
            mask = mask & _as_bool(events["photon_isTightIso"])

    pt_tight = photon_pt[mask]
    eta_tight = photon_eta[mask]
    phi_tight = photon_phi[mask]
    e_tight = photon_e[mask]
    topo_tight = photon_topo[mask]

    order = ak.argsort(pt_tight, axis=1, ascending=False)
    pt_sorted = pt_tight[order]
    eta_sorted = eta_tight[order]
    phi_sorted = phi_tight[order]
    e_sorted = e_tight[order]
    topo_sorted = topo_tight[order]

    lead_pt = _safe_first(pt_sorted, 0)
    sublead_pt = _safe_first(pt_sorted, 1)
    lead_eta = _safe_first(eta_sorted, 0)
    sublead_eta = _safe_first(eta_sorted, 1)
    lead_phi = _safe_first(phi_sorted, 0)
    sublead_phi = _safe_first(phi_sorted, 1)
    lead_e = _safe_first(e_sorted, 0)
    sublead_e = _safe_first(e_sorted, 1)
    lead_topo = _safe_first(topo_sorted, 0)
    sublead_topo = _safe_first(topo_sorted, 1)

    n_tight = ak.values_astype(ak.num(pt_tight, axis=1), np.int32)
    has_two = n_tight >= 2

    m_gg = ak.where(
        has_two,
        _inv_mass_from_pt_eta_phi_e(
            lead_pt,
            lead_eta,
            lead_phi,
            lead_e,
            sublead_pt,
            sublead_eta,
            sublead_phi,
            sublead_e,
        ),
        0.0,
    )

    dphi = _delta_phi(lead_phi, sublead_phi)
    lead_px = lead_pt * np.cos(lead_phi)
    lead_py = lead_pt * np.sin(lead_phi)
    sublead_px = sublead_pt * np.cos(sublead_phi)
    sublead_py = sublead_pt * np.sin(sublead_phi)

    gg_px = lead_px + sublead_px
    gg_py = lead_py + sublead_py
    gg_phi = np.arctan2(gg_py, gg_px)

    diphoton_pt = ak.where(
        has_two,
        np.sqrt(gg_px**2 + gg_py**2),
        0.0,
    )
    diphoton_deltaR = ak.where(
        has_two,
        np.sqrt((lead_eta - sublead_eta) ** 2 + dphi**2),
        0.0,
    )
    p_diff_x = lead_px - sublead_px
    p_diff_y = lead_py - sublead_py
    p_diff_norm = np.sqrt(p_diff_x**2 + p_diff_y**2)
    p_diff_norm = ak.where(p_diff_norm > 1e-6, p_diff_norm, 1e-6)
    diphoton_ptt = ak.where(
        has_two,
        abs(gg_px * p_diff_y - gg_py * p_diff_x) / p_diff_norm,
        0.0,
    )

    # Proxy geometry flags used to approximate legacy converted/unconverted category logic.
    has_transition_photon = (
        ((abs(lead_eta) > 1.3) & (abs(lead_eta) < 1.75))
        | ((abs(sublead_eta) > 1.3) & (abs(sublead_eta) < 1.75))
    )
    is_central_photon_pair = (abs(lead_eta) < 0.75) & (abs(sublead_eta) < 0.75)
    conversion_proxy = ak.where(has_two, (lead_topo + sublead_topo) > 0.0, False)

    # Build VBF-like dijet observables from available reconstructed jets.
    if {"jet_pt", "jet_eta", "jet_phi", "jet_e"}.issubset(set(events.fields)):
        jet_pt = events["jet_pt"]
        jet_eta = events["jet_eta"]
        jet_phi = events["jet_phi"]
        jet_e = events["jet_e"]
        jet_abs_eta = abs(jet_eta)

        jet_pass_pt = ak.where(jet_abs_eta > 2.5, jet_pt > 30.0, jet_pt > 25.0)
        jet_pass_eta = jet_abs_eta < 4.5
        if "jet_jvt" in events.fields:
            jet_pass_jvt = (jet_abs_eta >= 2.5) | (events["jet_jvt"] >= 0.75)
        else:
            jet_pass_jvt = ak.ones_like(jet_pt, dtype=np.bool_)

        jet_mask = jet_pass_pt & jet_pass_eta & jet_pass_jvt
        jet_pt_sel = jet_pt[jet_mask]
        jet_eta_sel = jet_eta[jet_mask]
        jet_phi_sel = jet_phi[jet_mask]
        jet_e_sel = jet_e[jet_mask]

        jet_order = ak.argsort(jet_pt_sel, axis=1, ascending=False)
        jet_pt_sorted = jet_pt_sel[jet_order]
        jet_eta_sorted = jet_eta_sel[jet_order]
        jet_phi_sorted = jet_phi_sel[jet_order]
        jet_e_sorted = jet_e_sel[jet_order]

        n_jets_vbf = ak.values_astype(ak.num(jet_pt_sorted, axis=1), np.int32)
        has_two_jets = n_jets_vbf >= 2

        lead_jet_pt = _safe_first(jet_pt_sorted, 0)
        sublead_jet_pt = _safe_first(jet_pt_sorted, 1)
        lead_jet_eta = _safe_first(jet_eta_sorted, 0)
        sublead_jet_eta = _safe_first(jet_eta_sorted, 1)
        lead_jet_phi = _safe_first(jet_phi_sorted, 0)
        sublead_jet_phi = _safe_first(jet_phi_sorted, 1)
        lead_jet_e = _safe_first(jet_e_sorted, 0)
        sublead_jet_e = _safe_first(jet_e_sorted, 1)

        m_jj = ak.where(
            has_two_jets,
            _inv_mass_from_pt_eta_phi_e(
                lead_jet_pt,
                lead_jet_eta,
                lead_jet_phi,
                lead_jet_e,
                sublead_jet_pt,
                sublead_jet_eta,
                sublead_jet_phi,
                sublead_jet_e,
            ),
            0.0,
        )
        delta_eta_jj = ak.where(has_two_jets, abs(lead_jet_eta - sublead_jet_eta), 0.0)
        jj_px = lead_jet_pt * np.cos(lead_jet_phi) + sublead_jet_pt * np.cos(sublead_jet_phi)
        jj_py = lead_jet_pt * np.sin(lead_jet_phi) + sublead_jet_pt * np.sin(sublead_jet_phi)
        jj_phi = np.arctan2(jj_py, jj_px)
        delta_phi_gg_jj = ak.where(has_two_jets, abs(_delta_phi(gg_phi, jj_phi)), 0.0)
    else:
        n_jets_vbf = ak.Array(np.zeros(len(events), dtype=np.int32))
        lead_jet_pt = ak.Array(np.zeros(len(events), dtype=float))
        sublead_jet_pt = ak.Array(np.zeros(len(events), dtype=float))
        lead_jet_eta = ak.Array(np.zeros(len(events), dtype=float))
        sublead_jet_eta = ak.Array(np.zeros(len(events), dtype=float))
        lead_jet_phi = ak.Array(np.zeros(len(events), dtype=float))
        sublead_jet_phi = ak.Array(np.zeros(len(events), dtype=float))
        lead_jet_e = ak.Array(np.zeros(len(events), dtype=float))
        sublead_jet_e = ak.Array(np.zeros(len(events), dtype=float))
        m_jj = ak.Array(np.zeros(len(events), dtype=float))
        delta_eta_jj = ak.Array(np.zeros(len(events), dtype=float))
        delta_phi_gg_jj = ak.Array(np.zeros(len(events), dtype=float))

    is_vbf_2jet = (
        (n_jets_vbf >= 2)
        & (delta_eta_jj > 2.8)
        & (m_jj > 400.0)
        & (delta_phi_gg_jj > 2.6)
    )

    out = ak.with_field(events, mask, "photon_mask_tight")
    out = ak.with_field(out, n_tight, "n_photons_tight")
    out = ak.with_field(out, lead_pt, "lead_photon_pt")
    out = ak.with_field(out, sublead_pt, "sublead_photon_pt")
    out = ak.with_field(out, lead_eta, "lead_photon_eta")
    out = ak.with_field(out, sublead_eta, "sublead_photon_eta")
    out = ak.with_field(out, lead_phi, "lead_photon_phi")
    out = ak.with_field(out, sublead_phi, "sublead_photon_phi")
    out = ak.with_field(out, lead_e, "lead_photon_e")
    out = ak.with_field(out, sublead_e, "sublead_photon_e")
    out = ak.with_field(out, lead_topo, "lead_photon_topoetcone40")
    out = ak.with_field(out, sublead_topo, "sublead_photon_topoetcone40")
    out = ak.with_field(out, m_gg, "m_gg")
    out = ak.with_field(out, diphoton_pt, "diphoton_pt")
    out = ak.with_field(out, diphoton_deltaR, "diphoton_deltaR")
    out = ak.with_field(out, diphoton_ptt, "diphoton_ptt")
    out = ak.with_field(out, has_transition_photon, "has_transition_photon")
    out = ak.with_field(out, is_central_photon_pair, "is_central_photon_pair")
    out = ak.with_field(out, conversion_proxy, "conversion_proxy")
    out = ak.with_field(out, n_jets_vbf, "n_jets_vbf")
    out = ak.with_field(out, lead_jet_pt, "lead_jet_pt")
    out = ak.with_field(out, sublead_jet_pt, "sublead_jet_pt")
    out = ak.with_field(out, lead_jet_eta, "lead_jet_eta")
    out = ak.with_field(out, sublead_jet_eta, "sublead_jet_eta")
    out = ak.with_field(out, lead_jet_phi, "lead_jet_phi")
    out = ak.with_field(out, sublead_jet_phi, "sublead_jet_phi")
    out = ak.with_field(out, lead_jet_e, "lead_jet_e")
    out = ak.with_field(out, sublead_jet_e, "sublead_jet_e")
    out = ak.with_field(out, m_jj, "m_jj")
    out = ak.with_field(out, delta_eta_jj, "delta_eta_jj")
    out = ak.with_field(out, delta_phi_gg_jj, "delta_phi_gg_jj")
    out = ak.with_field(out, is_vbf_2jet, "is_vbf_2jet")

    return out



def _lookup_sample(registry: dict, sample_id: str) -> dict:
    for s in registry.get("samples", []):
        if sample_id in (s.get("sample_id"), s.get("sample_name")):
            return s
    raise KeyError("sample not found: {}".format(sample_id))



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build photon object columns")
    parser.add_argument("--sample", required=True)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--regions", required=True)
    parser.add_argument("--max-events", type=int, default=None)
    parser.add_argument("--out", required=True)
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    registry = read_json(Path(args.registry))
    sample = _lookup_sample(registry, args.sample)
    cfg = _load_photon_cfg(Path(args.regions))

    events = load_events(
        files=sample["files"],
        tree_name=sample.get("tree_name", "analysis"),
        branches=None,
        max_events=args.max_events,
    )
    out = build_photons(events, cfg)

    out_path = Path(args.out)
    ensure_dir(out_path.parent)
    ak.to_parquet(out, out_path)

    avg_n = float(np.mean(ak.to_numpy(out["n_photons_tight"]))) if len(out) else 0.0
    n_pass = int(np.sum(ak.to_numpy(out["n_photons_tight"] >= 2))) if len(out) else 0
    print("avg_n_photons_tight={:.3f}".format(avg_n))
    print("events_pass_2ph_preselection={}".format(n_pass))


if __name__ == "__main__":
    main()
