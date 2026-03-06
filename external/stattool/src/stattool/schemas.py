"""Pydantic schemas and structured errors for stattool contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


@dataclass(slots=True)
class StatToolError(Exception):
    """Base exception with machine-readable error details."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable error payload."""
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ValidationError(StatToolError):
    """Raised when schema or contract validation fails."""


class WorkspaceBuildError(StatToolError):
    """Raised when workspace construction fails unexpectedly."""


class FitError(StatToolError):
    """Raised when fit execution fails unexpectedly."""


class NormProcessConfig(BaseModel):
    """Normalization modifier behavior for one process."""

    model_config = ConfigDict(extra="forbid")

    free: bool = True
    shared_group: str | None = None

    @model_validator(mode="after")
    def normalize_values(self) -> "NormProcessConfig":
        """Normalize optional shared group string."""
        if self.shared_group is not None:
            stripped = self.shared_group.strip()
            self.shared_group = stripped or None
        return self


class BuildPyhfWorkspaceRequest(BaseModel):
    """Input payload for deterministic pyhf workspace creation."""

    model_config = ConfigDict(extra="forbid")

    analysis_version: str = Field(min_length=1)
    process_files: list[str] = Field(min_length=1)
    signal_process: str = Field(min_length=1)
    norm_config: dict[str, NormProcessConfig] = Field(default_factory=dict)
    output_workspace_path: str = Field(min_length=1)


class RegionYieldsInput(BaseModel):
    """Per-region histogram payload from compute_binned_yields."""

    model_config = ConfigDict(extra="forbid")

    observable: str = Field(min_length=1)
    bin_edges: list[float] = Field(min_length=2)
    yields: list[float]

    @model_validator(mode="after")
    def validate_histogram_shape(self) -> "RegionYieldsInput":
        """Validate edge monotonicity and yields length."""
        edges = [float(value) for value in self.bin_edges]
        for i in range(len(edges) - 1):
            if edges[i + 1] <= edges[i]:
                raise ValueError("`bin_edges` must be strictly increasing.")
        if len(self.yields) != len(edges) - 1:
            raise ValueError("`yields` length must equal len(bin_edges) - 1.")

        self.bin_edges = edges
        self.yields = [float(value) for value in self.yields]
        return self


class ProcessYieldsInput(BaseModel):
    """Validated process-wise input file for workspace building."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str | None = None
    analysis_version: str = Field(min_length=1)
    process: str = Field(min_length=1)
    is_data: bool
    regions: dict[str, RegionYieldsInput] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceChannelSummary(BaseModel):
    """Compact channel summary emitted by workspace builder."""

    model_config = ConfigDict(extra="forbid")

    name: str
    samples: list[str] = Field(default_factory=list)
    n_bins: int = Field(ge=0)


class BuildPyhfWorkspaceResult(BaseModel):
    """Result payload for deterministic workspace creation."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    analysis_version: str
    workspace_path: str
    signal_process: str
    poi_name: str
    channels: list[WorkspaceChannelSummary] = Field(default_factory=list)
    samples: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FitOptions(BaseModel):
    """Fit options container (currently minimal)."""

    model_config = ConfigDict(extra="forbid")

    strategy: str = "default"


class FitPyhfModelRequest(BaseModel):
    """Input payload for deterministic pyhf model fitting."""

    model_config = ConfigDict(extra="forbid")

    workspace_path: str = Field(min_length=1)
    poi_name: str = Field(min_length=1)
    initial_parameters: dict[str, float] = Field(default_factory=dict)
    parameter_bounds: dict[str, list[float]] = Field(default_factory=dict)
    fixed_parameters: list[str] = Field(default_factory=list)
    fit_options: FitOptions = Field(default_factory=FitOptions)

    @model_validator(mode="after")
    def validate_bounds(self) -> "FitPyhfModelRequest":
        """Validate user-provided fit bounds."""
        normalized_bounds: dict[str, list[float]] = {}
        for name, bounds in self.parameter_bounds.items():
            if len(bounds) != 2:
                raise ValueError("Each parameter bound must be [low, high].")
            low = float(bounds[0])
            high = float(bounds[1])
            if high <= low:
                raise ValueError("Parameter upper bound must be greater than lower bound.")
            normalized_bounds[name] = [low, high]
        self.parameter_bounds = normalized_bounds

        self.initial_parameters = {
            name: float(value) for name, value in self.initial_parameters.items()
        }
        self.fixed_parameters = [name for name in self.fixed_parameters if name.strip()]
        return self


class ParameterEstimate(BaseModel):
    """Best-fit estimate for one model parameter."""

    model_config = ConfigDict(extra="forbid")

    value: float
    error: float = Field(ge=0.0)


class FitPyhfModelResult(BaseModel):
    """Result payload for pyhf fit action."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    poi: str
    nll: float
    parameters: dict[str, ParameterEstimate] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScanNLLCurveRequest(BaseModel):
    """Input payload for profiling NLL against one fixed parameter."""

    model_config = ConfigDict(extra="forbid")

    workspace_path: str = Field(min_length=1)
    parameter_name: str = Field(min_length=1)
    poi_name: str = Field(default="mu", min_length=1)
    initial_parameters: dict[str, float] = Field(default_factory=dict)
    parameter_bounds: dict[str, list[float]] = Field(default_factory=dict)
    fixed_parameters: list[str] = Field(default_factory=list)
    scan_min: float | None = None
    scan_max: float | None = None
    n_steps: int = Field(default=10, ge=2)
    output_png_path: str = Field(min_length=1)
    output_txt_path: str | None = None
    fit_options: FitOptions = Field(default_factory=FitOptions)

    @model_validator(mode="after")
    def validate_scan_inputs(self) -> "ScanNLLCurveRequest":
        """Validate bounds and normalize numeric fields."""
        normalized_bounds: dict[str, list[float]] = {}
        for name, bounds in self.parameter_bounds.items():
            if len(bounds) != 2:
                raise ValueError("Each parameter bound must be [low, high].")
            low = float(bounds[0])
            high = float(bounds[1])
            if high <= low:
                raise ValueError("Parameter upper bound must be greater than lower bound.")
            normalized_bounds[name] = [low, high]
        self.parameter_bounds = normalized_bounds

        self.initial_parameters = {
            name: float(value) for name, value in self.initial_parameters.items()
        }
        self.fixed_parameters = [name for name in self.fixed_parameters if name.strip()]

        if self.scan_min is not None:
            self.scan_min = float(self.scan_min)
        if self.scan_max is not None:
            self.scan_max = float(self.scan_max)
        if self.scan_min is not None and self.scan_max is not None and self.scan_max <= self.scan_min:
            raise ValueError("scan_max must be greater than scan_min.")

        if self.output_txt_path is not None:
            stripped = self.output_txt_path.strip()
            self.output_txt_path = stripped or None

        return self


class NLLScanPoint(BaseModel):
    """One profiled scan point."""

    model_config = ConfigDict(extra="forbid")

    value: float
    nll: float
    delta_nll: float = Field(ge=0.0)


class ScanNLLCurveResult(BaseModel):
    """Result payload for NLL profile scan action."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    parameter_name: str
    poi_name: str
    best_fit_value: float
    best_fit_error: float = Field(ge=0.0)
    scan_min: float
    scan_max: float
    n_steps: int = Field(ge=2)
    output_png_path: str
    output_txt_path: str
    points: list[NLLScanPoint] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolPayload(BaseModel):
    """Envelope schema for stattool action dispatch."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["build_pyhf_workspace", "fit_pyhf_model", "scan_nll_curve"]
    input: dict[str, Any]
