"""Pydantic schemas for deterministic JSON I/O contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BranchSummary(BaseModel):
    """Describes a branch available in a ROOT TTree."""

    model_config = ConfigDict(extra="forbid")

    name: str
    dtype: str
    interpretation: str | None = None
    title: str | None = None
    physics_meaning: str | None = None
    physics_category: str | None = None
    physics_units: str | None = None
    physics_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    inference_source: str | None = None


class TreeSummary(BaseModel):
    """Describes a TTree and its branch-level structure."""

    model_config = ConfigDict(extra="forbid")

    name: str
    num_entries: int = Field(ge=0)
    branches: list[BranchSummary] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RootFileSummary(BaseModel):
    """Top-level summary returned by file inspection."""

    model_config = ConfigDict(extra="forbid")

    path: str
    trees: list[TreeSummary] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FilterCondition(BaseModel):
    """Simple deterministic condition evaluated against one branch."""

    model_config = ConfigDict(extra="forbid")

    branch: str
    op: Literal["eq", "ne", "gt", "ge", "lt", "le", "in"]
    value: Any


class ExtractionRequest(BaseModel):
    """Request schema for branch extraction."""

    model_config = ConfigDict(extra="forbid")

    path: str
    tree: str
    branches: list[str] = Field(min_length=1)
    filters: list[FilterCondition] = Field(default_factory=list)
    entry_start: int | None = Field(default=None, ge=0)
    entry_stop: int | None = Field(default=None, ge=0)
    output_format: Literal["dict", "numpy", "pandas", "parquet"] = "dict"
    output_path: str | None = None
    include_data: bool = True

    @model_validator(mode="after")
    def validate_ranges(self) -> "ExtractionRequest":
        """Ensure entry bounds are coherent."""
        if (
            self.entry_start is not None
            and self.entry_stop is not None
            and self.entry_stop < self.entry_start
        ):
            raise ValueError("entry_stop must be greater than or equal to entry_start")
        return self


class ExtractionResult(BaseModel):
    """Result schema for branch extraction."""

    model_config = ConfigDict(extra="forbid")

    path: str
    tree: str
    selected_branches: list[str] = Field(default_factory=list)
    num_events: int = Field(ge=0)
    output_format: Literal["dict", "numpy", "pandas", "parquet"]
    output_path: str | None = None
    shapes: dict[str, list[int]] = Field(default_factory=dict)
    data: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConvertRootToArrayRequest(BaseModel):
    """Request schema for deterministic ROOT-to-array conversion."""

    model_config = ConfigDict(extra="forbid")

    process: str = Field(min_length=1)
    input_paths: list[str] = Field(min_length=1)
    tree: str = Field(default="Events", min_length=1)
    branches: list[str] = Field(min_length=1)
    weight_branch: str | None = None
    preselection: str | None = None
    max_events: int | None = Field(default=None, ge=1)
    output_path: str | None = None

    @model_validator(mode="after")
    def normalize_fields(self) -> "ConvertRootToArrayRequest":
        """Normalize and validate branch fields."""
        normalized = []
        for branch in self.branches:
            stripped = branch.strip()
            if not stripped:
                continue
            normalized.append(stripped)
        if not normalized:
            raise ValueError("`branches` must contain at least one non-empty branch name.")
        self.branches = list(dict.fromkeys(normalized))

        if self.weight_branch is not None:
            stripped = self.weight_branch.strip()
            self.weight_branch = stripped or None

        if self.preselection is not None:
            stripped = self.preselection.strip()
            self.preselection = stripped or None

        return self


class ConvertRootToArrayResult(BaseModel):
    """Result schema for ROOT-to-array conversion."""

    model_config = ConfigDict(extra="forbid")

    process: str
    n_events: int = Field(ge=0)
    data: dict[str, list[Any]] = Field(default_factory=dict)
    weights: list[Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegionBinningDefinition(BaseModel):
    """Region-level binning definition for deterministic yield computation."""

    model_config = ConfigDict(extra="forbid")

    cut: str = Field(min_length=1)
    observable: str = Field(min_length=1)
    bin_edges: list[float] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_bin_edges(self) -> "RegionBinningDefinition":
        """Require strictly increasing bin edges."""
        edges = [float(edge) for edge in self.bin_edges]
        for i in range(len(edges) - 1):
            if edges[i + 1] <= edges[i]:
                raise ValueError("`bin_edges` must be strictly increasing.")
        self.bin_edges = edges
        return self


class ComputeBinnedYieldsRequest(BaseModel):
    """Request schema for deterministic per-region binned yield computation."""

    model_config = ConfigDict(extra="forbid")

    analysis_version: str = Field(min_length=1)
    process: str = Field(min_length=1)
    is_data: bool
    input_array_path: str = Field(min_length=1)
    regions: dict[str, RegionBinningDefinition] = Field(min_length=1)


class RegionBinnedYields(BaseModel):
    """Per-region histogram yields."""

    model_config = ConfigDict(extra="forbid")

    observable: str
    bin_edges: list[float] = Field(min_length=2)
    yields: list[float]


class ComputeBinnedYieldsResult(BaseModel):
    """Result schema for deterministic per-region binned yield computation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    analysis_version: str
    process: str
    is_data: bool
    regions: dict[str, RegionBinnedYields] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolPayload(BaseModel):
    """Generic JSON contract for LangGraph tool invocation."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["inspect", "extract", "convert_root_to_array", "compute_binned_yields"]
    input: dict[str, Any]
