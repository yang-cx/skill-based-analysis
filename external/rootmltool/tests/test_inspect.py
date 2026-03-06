"""Tests for ROOT file inspection."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import uproot

from rootmltool.inspect import inspect_root_file
from rootmltool.semantics import infer_physics_meaning


def _create_synthetic_root(path: Path) -> None:
    with uproot.recreate(path) as root_file:
        root_file["Events"] = {
            "pt": np.array([10.0, 25.0, 45.0], dtype=np.float32),
            "eta": np.array([0.1, -1.2, 0.4], dtype=np.float32),
            "charge": np.array([1, -1, 1], dtype=np.int32),
        }


def test_inspect_root_file_returns_expected_structure(tmp_path: Path) -> None:
    root_path = tmp_path / "synthetic.root"
    _create_synthetic_root(root_path)

    summary = inspect_root_file(str(root_path))

    assert summary.path.endswith("synthetic.root")
    assert summary.metadata["num_trees"] == 1

    events_tree = summary.trees[0]
    assert events_tree.name == "Events"
    assert events_tree.num_entries == 3

    branch_names = {branch.name for branch in events_tree.branches}
    assert branch_names == {"pt", "eta", "charge"}
    assert all(branch.dtype for branch in events_tree.branches)
    assert all(branch.physics_meaning for branch in events_tree.branches)
    assert all(branch.inference_source == "name_type_heuristics_v1" for branch in events_tree.branches)

    dumped = summary.model_dump(mode="json")
    assert dumped["metadata"]["backend"] == "uproot"
    assert dumped["trees"][0]["branches"][0]["physics_meaning"] is not None


def test_inspect_root_file_without_ttree_does_not_crash(tmp_path: Path) -> None:
    root_path = tmp_path / "no_tree.root"
    with uproot.recreate(root_path):
        pass

    summary = inspect_root_file(str(root_path))

    assert summary.trees == []
    assert summary.metadata["num_trees"] == 0
    assert "no_ttrees_found" in summary.metadata["warnings"]


def test_alias_object_prefixes_are_recognized() -> None:
    cases = {
        "el_pt": "electron",
        "ele_eta": "electron",
        "mu_pt": "muon",
        "muon_eta": "muon",
        "ph_pt": "photon",
        "gam_eta": "photon",
        "gamma_phi": "photon",
        "tau_pt": "tau",
    }

    for branch_name, expected_category in cases.items():
        inferred = infer_physics_meaning(branch_name, "float")
        assert inferred["physics_category"] == expected_category
        assert inferred["physics_confidence"] >= 0.88
