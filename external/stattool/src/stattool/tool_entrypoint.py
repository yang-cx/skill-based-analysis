"""LangGraph-oriented dispatch entrypoint for stattool actions."""

from __future__ import annotations

from typing import Any

from .fit import fit_pyhf_model
from .scan import scan_nll_curve
from .schemas import (
    BuildPyhfWorkspaceRequest,
    FitPyhfModelRequest,
    ScanNLLCurveRequest,
    StatToolError,
    ToolPayload,
    ValidationError,
)
from .workspace import build_pyhf_workspace


def run_tool(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate payload, dispatch action, and return envelope output."""
    try:
        parsed = ToolPayload.model_validate(payload)

        if parsed.action == "build_pyhf_workspace":
            request = BuildPyhfWorkspaceRequest.model_validate(parsed.input)
            result = build_pyhf_workspace(request)
            return {
                "ok": True,
                "action": "build_pyhf_workspace",
                "result": result.model_dump(mode="json"),
            }

        if parsed.action == "scan_nll_curve":
            request = ScanNLLCurveRequest.model_validate(parsed.input)
            result = scan_nll_curve(request)
            return {
                "ok": True,
                "action": "scan_nll_curve",
                "result": result.model_dump(mode="json"),
            }

        request = FitPyhfModelRequest.model_validate(parsed.input)
        result = fit_pyhf_model(request)
        return {
            "ok": True,
            "action": "fit_pyhf_model",
            "result": result.model_dump(mode="json"),
        }
    except StatToolError as exc:
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
