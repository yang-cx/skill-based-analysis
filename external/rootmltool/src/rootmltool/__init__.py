"""Deterministic ROOT inspection and extraction toolkit."""

from importlib.metadata import PackageNotFoundError, version

from .binned_yields import compute_binned_yields
from .convert import convert_root_to_array
from .extract import extract_branches
from .inspect import inspect_root_file
from .tool_entrypoint import run_tool

try:
    __version__ = version("rootmltool")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "__version__",
    "compute_binned_yields",
    "convert_root_to_array",
    "extract_branches",
    "inspect_root_file",
    "run_tool",
]
