"""LangGraph-oriented tool entrypoint wrapper."""

from __future__ import annotations

from typing import Any

from .binned_yields import compute_binned_yields
from .convert import convert_root_to_array
from .exceptions import RootMLToolError, ValidationError
from .extract import extract_branches
from .inspect import inspect_root_file
from .schemas import (
    ComputeBinnedYieldsRequest,
    ConvertRootToArrayRequest,
    ExtractionRequest,
    ToolPayload,
)


def run_tool(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate payload, dispatch action, and return structured JSON output."""
    try:
        parsed = ToolPayload.model_validate(payload)

        if parsed.action == "inspect":
            path = parsed.input.get("path")
            if not isinstance(path, str):
                raise ValidationError(
                    code="invalid_inspect_input",
                    message="Inspect action requires `input.path` as a string.",
                    details={"input": parsed.input},
                )
            result = inspect_root_file(path)
            return {
                "ok": True,
                "action": "inspect",
                "result": result.model_dump(mode="json"),
            }

        if parsed.action == "convert_root_to_array":
            request = ConvertRootToArrayRequest.model_validate(parsed.input)
            result = convert_root_to_array(request)
            return {
                "ok": True,
                "action": "convert_root_to_array",
                "result": result.model_dump(mode="json"),
            }

        if parsed.action == "compute_binned_yields":
            request = ComputeBinnedYieldsRequest.model_validate(parsed.input)
            result = compute_binned_yields(request)
            return {
                "ok": True,
                "action": "compute_binned_yields",
                "result": result.model_dump(mode="json"),
            }

        request = ExtractionRequest.model_validate(parsed.input)
        result = extract_branches(request)
        return {
            "ok": True,
            "action": "extract",
            "result": result.model_dump(mode="json"),
        }
    except RootMLToolError as exc:
        return {
            "ok": False,
            "error": exc.to_dict(),
        }
    except Exception as exc:
        wrapped = ValidationError(
            code="tool_payload_invalid",
            message="Tool payload validation failed.",
            details={"error": str(exc)},
        )
        return {
            "ok": False,
            "error": wrapped.to_dict(),
        }
