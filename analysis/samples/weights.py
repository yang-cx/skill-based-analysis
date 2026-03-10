from typing import Dict, List

import awkward as ak
import numpy as np


SCALE_FACTOR_CANDIDATES: List[str] = [
    "ScaleFactor_PILEUP",
    "ScaleFactor_PHOTON",
    "ScaleFactor_MLTRIGGER",
    "ScaleFactor_LepTRIGGER",
    "ScaleFactor_MuTRIGGER",
    "ScaleFactor_ElTRIGGER",
    "ScaleFactor_ELE",
    "ScaleFactor_MUON",
    "ScaleFactor_JVT",
    "ScaleFactor_BTAG",
    "ScaleFactor_FTAG",
    "ScaleFactor_TAU",
    "ScaleFactor_TauTRIGGER",
    "ScaleFactor_DiTauTRIGGER",
]



def event_weight(events: ak.Array, sample: Dict) -> ak.Array:
    n = len(events)
    base = np.ones(n, dtype=np.float64)

    if sample.get("kind") == "data":
        return ak.Array(base)

    if "mcWeight" in events.fields:
        base = base * ak.to_numpy(events["mcWeight"])

    for sf in SCALE_FACTOR_CANDIDATES:
        if sf in events.fields:
            base = base * ak.to_numpy(events[sf])

    w_norm = sample.get("w_norm", "not_specified")
    if isinstance(w_norm, (int, float)):
        base = base * float(w_norm)

    base = np.nan_to_num(base, nan=0.0, posinf=0.0, neginf=0.0)
    return ak.Array(base)
