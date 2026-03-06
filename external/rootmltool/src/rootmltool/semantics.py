"""Deterministic branch-name/type heuristics for physics meaning inference.

This module intentionally uses rule-based logic only (no LLM inference).
"""

from __future__ import annotations

from typing import Any


_OBJECT_ALIAS_TO_CANONICAL: dict[str, str] = {
    # Generic leptons
    "lep": "lepton",
    "lepton": "lepton",
    # Electrons
    "el": "electron",
    "ele": "electron",
    "electron": "electron",
    # Muons
    "mu": "muon",
    "muon": "muon",
    # Photons
    "ph": "photon",
    "gam": "photon",
    "gamma": "photon",
    "photon": "photon",
    # Taus
    "tau": "tau",
    # Jets
    "jet": "jet",
    "largerjet": "large_r_jet",
    "largejet": "large_r_jet",
    "fatjet": "large_r_jet",
    # MET
    "met": "met",
    "etmiss": "met",
}

_CANONICAL_OBJECT_INFO: dict[str, tuple[str, str]] = {
    "lepton": ("Lepton", "lepton"),
    "electron": ("Electron", "electron"),
    "muon": ("Muon", "muon"),
    "photon": ("Photon", "photon"),
    "tau": ("Tau", "tau"),
    "jet": ("Jet", "jet"),
    "large_r_jet": ("Large-R jet", "large_r_jet"),
    "met": ("Missing transverse momentum", "met"),
}

_KNOWN_QUANTITY_PREFIXES: tuple[str, ...] = (
    "pt",
    "eta",
    "phi",
    "e",
    "m",
    "charge",
    "n",
    "ntracks",
    "truthmatched",
    "trigmatched",
    "istightid",
    "ptcone30",
    "etcone20",
    "bdtid",
    "tau32",
    "d2",
    "mv2c10",
    "jvt",
    "syst",
    "energy",
)


def _dtype_kind(dtype: str) -> str:
    text = dtype.lower()
    if "vector" in text or "jagged" in text:
        return "collection"
    if "bool" in text:
        return "boolean"
    if "int" in text or "uint" in text:
        return "integer"
    if "float" in text or "double" in text:
        return "float"
    return "unknown"


def _quantity_from_name(name: str) -> tuple[str | None, str | None]:
    """Return (meaning, units) inferred from suffix/pattern."""
    lowered = name.lower()
    compact = lowered.replace("_", "")

    if lowered.endswith("_pt") or compact.endswith("pt"):
        return ("Transverse momentum", "analysis-dependent (often GeV or MeV)")
    if lowered.endswith("_eta") or compact.endswith("eta"):
        return ("Pseudorapidity", None)
    if lowered.endswith("_phi") or compact.endswith("phi"):
        return ("Azimuthal angle", "radians")
    if lowered.endswith("_e") or compact.endswith("energy"):
        return ("Energy", "analysis-dependent (often GeV or MeV)")
    if lowered.endswith("_m") or compact.endswith("mass"):
        return ("Invariant mass", "analysis-dependent (often GeV or MeV)")
    if lowered.endswith("_charge") or compact.endswith("charge"):
        return ("Electric charge", "e")
    if lowered.endswith("_n") or lowered.endswith("_ntracks") or compact.endswith("count"):
        return ("Object multiplicity / count", None)
    if lowered.endswith("_truthmatched") or compact.endswith("truthmatched"):
        return ("Truth-matching flag", None)
    if lowered.endswith("_trigmatched") or compact.endswith("trigmatched"):
        return ("Trigger-matching flag", None)
    if lowered.endswith("_istightid") or compact.endswith("istightid"):
        return ("Tight ID selection flag", None)
    if lowered.endswith("_ptcone30") or lowered.endswith("_etcone20") or compact.endswith("ptcone30") or compact.endswith("etcone20"):
        return ("Isolation observable", "analysis-dependent")
    if lowered.endswith("_bdtid") or compact.endswith("bdtid"):
        return ("BDT-based tau ID score", None)
    if lowered.endswith("_tau32") or compact.endswith("tau32"):
        return ("Substructure variable tau32", None)
    if lowered.endswith("_d2") or compact.endswith("d2"):
        return ("Substructure variable D2", None)
    if lowered.endswith("_mv2c10") or compact.endswith("mv2c10"):
        return ("b-tagging discriminator score (MV2c10)", None)
    if lowered.endswith("_jvt") or compact.endswith("jvt"):
        return ("Jet Vertex Tagger discriminant", None)
    if lowered.endswith("_syst") or compact.endswith("syst"):
        return ("Systematic variation of nominal quantity", None)
    return (None, None)


def _object_info_from_name(name: str) -> tuple[str | None, str | None]:
    """Infer canonical object label/category from branch aliases."""
    lowered = name.lower()
    token = lowered.split("_", 1)[0]
    canonical = _OBJECT_ALIAS_TO_CANONICAL.get(token)
    if canonical:
        return _CANONICAL_OBJECT_INFO[canonical]

    compact = lowered.replace("_", "")
    for alias in sorted(_OBJECT_ALIAS_TO_CANONICAL, key=len, reverse=True):
        if not compact.startswith(alias):
            continue
        remainder = compact[len(alias):]
        if not remainder or remainder.startswith(_KNOWN_QUANTITY_PREFIXES):
            canonical = _OBJECT_ALIAS_TO_CANONICAL[alias]
            return _CANONICAL_OBJECT_INFO[canonical]

    return (None, None)


def infer_physics_meaning(branch_name: str, dtype: str) -> dict[str, Any]:
    """Infer branch-level physics meaning from name and type.

    Returns
    -------
    dict[str, Any]
        Keys:
        - physics_meaning: str
        - physics_category: str
        - physics_units: str | None
        - physics_confidence: float in [0, 1]
        - inference_source: str
    """
    name = branch_name.strip()
    lowered = name.lower()
    kind = _dtype_kind(dtype)

    # Exact, high-confidence mappings.
    exact: dict[str, tuple[str, str, str | None, float]] = {
        "runnumber": ("Run identifier", "event_metadata", None, 0.99),
        "eventnumber": ("Event identifier", "event_metadata", None, 0.99),
        "channelnumber": ("MC channel / process identifier", "event_metadata", None, 0.95),
        "mcweight": ("Generator-level Monte Carlo event weight", "weights", None, 0.98),
        "xsection": ("Sample cross-section normalization", "normalization", "pb (typical)", 0.95),
        "sumweights": ("Sum of generator event weights", "normalization", None, 0.95),
        "met_et": ("Missing transverse momentum magnitude", "met", "analysis-dependent (often GeV or MeV)", 0.98),
        "met_phi": ("Missing transverse momentum azimuth", "met", "radians", 0.98),
    }
    if lowered in exact:
        meaning, category, units, confidence = exact[lowered]
        return {
            "physics_meaning": meaning,
            "physics_category": category,
            "physics_units": units,
            "physics_confidence": confidence,
            "inference_source": "name_type_heuristics_v1",
        }

    if lowered.startswith("scalefactor_"):
        return {
            "physics_meaning": "Efficiency / calibration scale factor weight",
            "physics_category": "weights",
            "physics_units": None,
            "physics_confidence": 0.97,
            "inference_source": "name_type_heuristics_v1",
        }

    if lowered.startswith("trig"):
        return {
            "physics_meaning": "Trigger decision flag",
            "physics_category": "trigger",
            "physics_units": None,
            "physics_confidence": 0.92 if kind == "boolean" else 0.78,
            "inference_source": "name_type_heuristics_v1",
        }

    quantity, units = _quantity_from_name(lowered)
    object_label, object_category = _object_info_from_name(lowered)

    if object_label and quantity:
        return {
            "physics_meaning": f"{object_label} {quantity.lower()}",
            "physics_category": object_category,
            "physics_units": units,
            "physics_confidence": 0.88,
            "inference_source": "name_type_heuristics_v1",
        }

    if quantity:
        return {
            "physics_meaning": quantity,
            "physics_category": "kinematics_or_flags",
            "physics_units": units,
            "physics_confidence": 0.72,
            "inference_source": "name_type_heuristics_v1",
        }

    # Conservative fallback keeps behavior deterministic and explicit.
    fallback_meaning = {
        "boolean": "Boolean analysis flag",
        "integer": "Integer code or count",
        "float": "Floating-point analysis observable",
        "collection": "Per-event collection observable",
    }.get(kind, "Unclassified analysis variable")

    return {
        "physics_meaning": fallback_meaning,
        "physics_category": "unclassified",
        "physics_units": None,
        "physics_confidence": 0.35,
        "inference_source": "name_type_heuristics_v1",
    }


# TODO: Externalize mapping rules into a versioned YAML for experiment-specific customizations.
