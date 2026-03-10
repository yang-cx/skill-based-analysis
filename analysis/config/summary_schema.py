from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SignalRegion(BaseModel):
    model_config = ConfigDict(extra="allow")
    region_id: Optional[str] = None
    fit_observable: Optional[str] = None
    associated_signature_ids: List[str] = Field(default_factory=list)


class ControlRegion(BaseModel):
    model_config = ConfigDict(extra="allow")
    region_id: Optional[str] = None


class FitSetup(BaseModel):
    model_config = ConfigDict(extra="allow")
    fit_id: Optional[str] = None
    regions_included: List[str] = Field(default_factory=list)
    parameters_of_interest: List[str] = Field(default_factory=list)


class ResultEntry(BaseModel):
    model_config = ConfigDict(extra="allow")
    associated_fit_id: Optional[str] = None


class SignalSignature(BaseModel):
    model_config = ConfigDict(extra="allow")
    signature_id: Optional[str] = None


class AnalysisSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    analysis_metadata: Dict[str, Any]
    analysis_objectives: List[Dict[str, Any]] = Field(default_factory=list)
    signal_signatures: List[SignalSignature] = Field(default_factory=list)
    background_processes: List[Dict[str, Any]] = Field(default_factory=list)
    signal_regions: List[SignalRegion] = Field(default_factory=list)
    control_regions: List[ControlRegion] = Field(default_factory=list)
    fit_setup: List[FitSetup] = Field(default_factory=list)
    results: List[ResultEntry] = Field(default_factory=list)


def parse_summary(payload: Dict[str, Any]) -> AnalysisSummary:
    return AnalysisSummary.model_validate(payload)
