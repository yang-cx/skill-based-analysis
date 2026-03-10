"""Common utilities."""
import json
import os
from pathlib import Path


def ensure_dir(path):
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path, data, indent=2):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=indent)
    return path


def read_json(path):
    with open(path) as f:
        return json.load(f)
