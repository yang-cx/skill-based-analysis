import hashlib
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def stable_sha256(parts: Iterable[str]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
    return h.hexdigest()


def read_json(path: Path) -> Dict[str, Any]:
    with path.open() as f:
        return json.load(f)


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("w") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def read_text(path: Path) -> str:
    with path.open() as f:
        return f.read()


def now_utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        )
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


def build_config_hash(summary_path: Path, regions_path: Path, systematics_path: Path = None) -> str:
    parts = []
    for p in [summary_path, regions_path, systematics_path]:
        if p is None:
            continue
        p = Path(p)
        if p.exists():
            parts.append(read_text(p))
        else:
            parts.append("missing:" + str(p))
    return stable_sha256(parts)


def run_metadata(summary_path: Path, regions_path: Path, systematics_path: Path = None) -> Dict[str, Any]:
    return {
        "timestamp_utc": now_utc_iso(),
        "config_hash": build_config_hash(summary_path, regions_path, systematics_path),
        "git_commit": git_commit(),
        "cwd": os.getcwd(),
    }
