"""Deterministic pyhf workspace construction from per-process binned yields."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schemas import (
    BuildPyhfWorkspaceRequest,
    BuildPyhfWorkspaceResult,
    ProcessYieldsInput,
    StatToolError,
    ValidationError,
    WorkspaceBuildError,
    WorkspaceChannelSummary,
)


def _normalize_parameter_token(value: str) -> str:
    """Normalize raw strings into pyhf-friendly parameter tokens."""
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip())
    normalized = normalized.strip("_")
    return normalized or "param"


def _read_process_payload(path: str) -> ProcessYieldsInput:
    """Load and validate one per-process JSON payload."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise ValidationError(
            code="process_file_not_found",
            message="`process_files` entry does not point to an existing file.",
            details={"path": str(resolved)},
        )

    try:
        with resolved.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        raise ValidationError(
            code="process_file_invalid_json",
            message="Failed to parse process file JSON.",
            details={"path": str(resolved), "error": str(exc)},
        ) from exc

    try:
        return ProcessYieldsInput.model_validate(payload)
    except Exception as exc:
        raise ValidationError(
            code="process_file_schema_invalid",
            message="Process file does not match expected binned-yields schema.",
            details={"path": str(resolved), "error": str(exc)},
        ) from exc


def _validate_analysis_versions(
    records: list[ProcessYieldsInput],
    analysis_version: str,
) -> None:
    """Ensure all process payloads match the requested analysis version."""
    mismatches = [
        {
            "process": record.process,
            "analysis_version": record.analysis_version,
        }
        for record in records
        if record.analysis_version != analysis_version
    ]
    if mismatches:
        raise ValidationError(
            code="analysis_version_mismatch",
            message="All process files must match request.analysis_version.",
            details={
                "expected": analysis_version,
                "mismatches": mismatches,
            },
        )


def _validate_region_compatibility(records: list[ProcessYieldsInput]) -> list[str]:
    """Validate region naming and bin-edge compatibility across process files."""
    if not records:
        return []

    reference = records[0]
    reference_regions = set(reference.regions.keys())
    reference_edges = {
        region_name: list(region.bin_edges)
        for region_name, region in reference.regions.items()
    }

    for record in records[1:]:
        if set(record.regions.keys()) != reference_regions:
            raise ValidationError(
                code="region_set_mismatch",
                message="All process payloads must define the same region names.",
                details={
                    "reference_process": reference.process,
                    "process": record.process,
                    "reference_regions": sorted(reference_regions),
                    "regions": sorted(record.regions.keys()),
                },
            )

        for region_name, region in record.regions.items():
            if list(region.bin_edges) != reference_edges[region_name]:
                raise ValidationError(
                    code="bin_edges_mismatch",
                    message="Region bin edges must be identical across process payloads.",
                    details={
                        "region": region_name,
                        "reference_process": reference.process,
                        "process": record.process,
                        "reference_bin_edges": reference_edges[region_name],
                        "bin_edges": list(region.bin_edges),
                    },
                )

    return sorted(reference_regions)


def _resolve_modifier_name(
    process: str,
    signal_process: str,
    norm_config: dict[str, Any],
) -> tuple[str, bool]:
    """Resolve the normalization modifier name and free/fixed setting."""
    process_cfg = norm_config.get(process)
    free = True if process_cfg is None else bool(process_cfg.free)

    if process == signal_process:
        return "mu", free

    shared_group = None if process_cfg is None else process_cfg.shared_group
    if shared_group:
        return f"norm_{_normalize_parameter_token(shared_group)}", free

    return f"norm_{_normalize_parameter_token(process)}", free


def _build_workspace_spec(
    request: BuildPyhfWorkspaceRequest,
    mc_records: list[ProcessYieldsInput],
    data_record: ProcessYieldsInput,
    region_names: list[str],
) -> tuple[dict[str, Any], list[WorkspaceChannelSummary], list[str]]:
    """Build pyhf workspace spec and compact summaries."""
    mc_by_process = {record.process: record for record in mc_records}
    process_names = sorted(mc_by_process.keys())

    unknown_norm_cfg = sorted(set(request.norm_config.keys()) - set(process_names))
    if unknown_norm_cfg:
        raise ValidationError(
            code="unknown_norm_config_process",
            message="norm_config contains process names absent from MC payloads.",
            details={"unknown_processes": unknown_norm_cfg},
        )

    if request.signal_process not in mc_by_process:
        raise ValidationError(
            code="signal_process_missing",
            message="signal_process was not found in MC process payloads.",
            details={
                "signal_process": request.signal_process,
                "available_processes": process_names,
            },
        )

    channels: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    channel_summaries: list[WorkspaceChannelSummary] = []

    modifier_free_map: dict[str, bool] = {}
    modifier_owner: dict[str, str] = {}

    for region_name in region_names:
        region_samples: list[dict[str, Any]] = []
        for process in process_names:
            record = mc_by_process[process]
            region = record.regions[region_name]

            modifier_name, free = _resolve_modifier_name(
                process=process,
                signal_process=request.signal_process,
                norm_config=request.norm_config,
            )

            if modifier_name in modifier_free_map and modifier_free_map[modifier_name] != free:
                raise ValidationError(
                    code="conflicting_norm_config",
                    message=(
                        "Processes sharing a normalization modifier must agree on free/fixed setting."
                    ),
                    details={
                        "modifier": modifier_name,
                        "first_process": modifier_owner[modifier_name],
                        "second_process": process,
                        "first_free": modifier_free_map[modifier_name],
                        "second_free": free,
                    },
                )

            modifier_free_map[modifier_name] = free
            modifier_owner.setdefault(modifier_name, process)

            region_samples.append(
                {
                    "name": process,
                    "data": [float(value) for value in region.yields],
                    "modifiers": [
                        {
                            "name": modifier_name,
                            "type": "normfactor",
                            "data": None,
                        }
                    ],
                }
            )

        observation_region = data_record.regions[region_name]
        observations.append(
            {
                "name": region_name,
                "data": [float(value) for value in observation_region.yields],
            }
        )

        channels.append({"name": region_name, "samples": region_samples})
        channel_summaries.append(
            WorkspaceChannelSummary(
                name=region_name,
                samples=[sample["name"] for sample in region_samples],
                n_bins=len(observation_region.bin_edges) - 1,
            )
        )

    poi_name = "mu"
    if poi_name not in modifier_free_map:
        raise ValidationError(
            code="poi_modifier_missing",
            message="Signal process did not produce required POI modifier `mu`.",
            details={"signal_process": request.signal_process},
        )

    ordered_modifiers = sorted(modifier_free_map.keys(), key=lambda name: (name != poi_name, name))

    parameters = [
        {
            "name": modifier,
            "inits": [1.0],
            "bounds": [[0.0, 10.0]],
            "fixed": not modifier_free_map[modifier],
        }
        for modifier in ordered_modifiers
    ]

    workspace_spec = {
        "version": "1.0.0",
        "channels": channels,
        "observations": observations,
        "measurements": [
            {
                "name": "measurement",
                "config": {
                    "poi": poi_name,
                    "parameters": parameters,
                },
            }
        ],
    }

    return workspace_spec, channel_summaries, process_names


def build_pyhf_workspace(
    request: BuildPyhfWorkspaceRequest | dict[str, Any],
) -> BuildPyhfWorkspaceResult:
    """Build and persist a deterministic pyhf workspace JSON."""
    if isinstance(request, dict):
        request = BuildPyhfWorkspaceRequest.model_validate(request)

    try:
        records = [_read_process_payload(path) for path in request.process_files]
        _validate_analysis_versions(records, request.analysis_version)

        data_records = [record for record in records if record.is_data]
        mc_records = [record for record in records if not record.is_data]

        if len(data_records) != 1:
            raise ValidationError(
                code="invalid_data_process_count",
                message="Exactly one is_data=true process payload is required.",
                details={"count": len(data_records)},
            )
        if not mc_records:
            raise ValidationError(
                code="missing_mc_processes",
                message="At least one MC process payload is required.",
                details={},
            )

        region_names = _validate_region_compatibility(records)

        workspace_spec, channel_summaries, process_names = _build_workspace_spec(
            request=request,
            mc_records=mc_records,
            data_record=data_records[0],
            region_names=region_names,
        )

        output_path = Path(request.output_workspace_path).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(workspace_spec, handle, indent=2, ensure_ascii=False)

        return BuildPyhfWorkspaceResult(
            schema_version="1.0",
            analysis_version=request.analysis_version,
            workspace_path=str(output_path),
            signal_process=request.signal_process,
            poi_name="mu",
            channels=channel_summaries,
            samples=process_names,
            metadata={
                "n_process_files": len(records),
                "n_mc_processes": len(process_names),
                "data_process": data_records[0].process,
                "regions": region_names,
            },
        )
    except StatToolError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise WorkspaceBuildError(
            code="workspace_build_failed",
            message="Unexpected failure during pyhf workspace construction.",
            details={"error": str(exc)},
        ) from exc

