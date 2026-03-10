from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import awkward as ak
import uproot

from analysis.common import ensure_dir, write_json


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def vendored_rootml_src_path() -> Path:
    return _repo_root() / "external" / "rootmltool" / "src"


def _ensure_vendored_rootml_importable() -> None:
    src = vendored_rootml_src_path()
    if not src.exists():
        raise RuntimeError("Vendored rootmltool source not found: {}".format(src))
    src_s = str(src)
    if src_s not in sys.path:
        sys.path.insert(0, src_s)


def rootmltool_is_available() -> Tuple[bool, str]:
    src = vendored_rootml_src_path()
    if not src.exists():
        return False, "vendored source missing"
    try:
        _ensure_vendored_rootml_importable()
        import rootmltool  # noqa: F401

        return True, "ok"
    except Exception as exc:
        return False, str(exc)


def _available_branches_for_sample(
    files: List[str],
    tree_name: str,
    requested_branches: Iterable[str],
) -> List[str]:
    req = list(requested_branches)
    if not req or not files:
        return []

    try:
        with uproot.open(files[0]) as f:
            if tree_name not in f:
                return req
            available = set(f[tree_name].keys())
        chosen = [b for b in req if b in available]
        return chosen if chosen else req
    except Exception:
        return req


def _source_signature(files: List[str]) -> str:
    rows: List[str] = []
    for path_s in files:
        path = Path(path_s).expanduser().resolve()
        try:
            st = path.stat()
            rows.append("{}:{}:{}".format(path, st.st_size, st.st_mtime_ns))
        except Exception:
            rows.append("{}:missing".format(path))
    h = hashlib.sha256()
    for row in rows:
        h.update(row.encode("utf-8"))
    return h.hexdigest()


def _cache_manifest(
    sample_id: str,
    files: List[str],
    tree_name: str,
    branches: List[str],
    max_events: int | None,
) -> Dict[str, Any]:
    return {
        "schema_version": "1",
        "sample_id": str(sample_id),
        "source_files": [str(Path(p).expanduser().resolve()) for p in files],
        "source_signature": _source_signature(files),
        "tree_name": str(tree_name),
        "branches": list(branches),
        "max_events": int(max_events) if isinstance(max_events, int) else None,
    }


def _manifest_matches(path: Path, expected: Dict[str, Any]) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return payload == expected


def load_events_with_rootml_cache(
    *,
    sample_id: str,
    files: Iterable[str],
    tree_name: str,
    branches: Iterable[str],
    max_events: int | None,
    cache_dir: Path,
    reuse_cache: bool = True,
) -> Tuple[ak.Array, Dict[str, Any]]:
    file_list = [str(Path(p).expanduser().resolve()) for p in files]
    selected_branches = _available_branches_for_sample(file_list, tree_name, branches)
    if not selected_branches:
        raise RuntimeError(
            "No branches selected for sample {} with backend rootmltool.".format(sample_id)
        )

    ensure_dir(cache_dir)
    cache_path = cache_dir / "{}.arrays.json".format(sample_id)
    manifest_path = cache_dir / "{}.arrays.meta.json".format(sample_id)

    expected_manifest = _cache_manifest(
        sample_id=sample_id,
        files=file_list,
        tree_name=tree_name,
        branches=selected_branches,
        max_events=max_events,
    )
    cache_hit = bool(
        reuse_cache
        and cache_path.exists()
        and _manifest_matches(manifest_path, expected_manifest)
    )

    if not cache_hit:
        _ensure_vendored_rootml_importable()
        from rootmltool.tool_entrypoint import run_tool

        payload = {
            "action": "convert_root_to_array",
            "input": {
                "process": str(sample_id),
                "input_paths": file_list,
                "tree": str(tree_name),
                "branches": selected_branches,
                "output_path": str(cache_path),
                "max_events": int(max_events) if isinstance(max_events, int) else None,
            },
        }
        response = run_tool(payload)
        if not response.get("ok"):
            error = response.get("error", {})
            raise RuntimeError(
                "rootmltool conversion failed for {}: {} ({})".format(
                    sample_id,
                    error.get("code", "unknown_error"),
                    error.get("message", "no message"),
                )
            )
        write_json(manifest_path, expected_manifest)

    try:
        converted = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(
            "Failed to load rootmltool cache for {} at {}: {}".format(
                sample_id, cache_path, exc
            )
        )

    data_map = converted.get("data", {})
    events = ak.Array(data_map)
    if isinstance(max_events, int) and max_events >= 0:
        events = events[:max_events]

    return events, {
        "cache_path": str(cache_path),
        "cache_manifest_path": str(manifest_path),
        "cache_hit": cache_hit,
        "backend": "rootmltool",
        "selected_branches": selected_branches,
    }
