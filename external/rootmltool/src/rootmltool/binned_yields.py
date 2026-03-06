"""Deterministic region-wise binned yield computation from array JSON payloads."""

from __future__ import annotations

import ast
import json
import operator
from pathlib import Path
from typing import Any

import numpy as np

from .exceptions import ConversionError, RootMLToolError, ValidationError
from .schemas import (
    ComputeBinnedYieldsRequest,
    ComputeBinnedYieldsResult,
    ConvertRootToArrayResult,
)


_ALLOWED_FUNCTIONS = {"abs": abs}
_ALLOWED_UNARY_OPERATORS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Invert: operator.invert,
}
_ALLOWED_BINARY_OPERATORS = {
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
}
_ALLOWED_BOOLEAN_OPERATORS = {
    ast.And: np.logical_and,
    ast.Or: np.logical_or,
}
_ALLOWED_COMPARISON_OPERATORS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def _parse_cut_expression(cut: str) -> ast.Expression:
    """Parse cut string into a safe AST expression."""
    try:
        parsed = ast.parse(cut, mode="eval")
    except SyntaxError as exc:
        raise ValidationError(
            code="invalid_cut_syntax",
            message="Region cut contains invalid syntax.",
            details={"cut": cut, "error": str(exc)},
        ) from exc

    # Normalize shorthand such as `pt > 20 & abs(eta) < 2.5`.
    body = parsed.body
    if (
        isinstance(body, ast.Compare)
        and len(body.ops) == 2
        and len(body.comparators) == 2
        and isinstance(body.comparators[0], ast.BinOp)
        and isinstance(body.comparators[0].op, (ast.BitAnd, ast.BitOr))
    ):
        middle = body.comparators[0]
        normalized = ast.Expression(
            body=ast.BinOp(
                left=ast.Compare(
                    left=body.left,
                    ops=[body.ops[0]],
                    comparators=[middle.left],
                ),
                op=middle.op,
                right=ast.Compare(
                    left=middle.right,
                    ops=[body.ops[1]],
                    comparators=[body.comparators[1]],
                ),
            )
        )
        return ast.fix_missing_locations(normalized)

    return parsed


def _evaluate_cut_node(node: ast.AST, variables: dict[str, Any], cut: str) -> Any:
    """Evaluate a restricted cut AST against numpy-backed variables."""
    if isinstance(node, ast.Expression):
        return _evaluate_cut_node(node.body, variables, cut)

    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ValidationError(
                code="unknown_cut_symbol",
                message="Region cut references a symbol that is not present in data.",
                details={"symbol": node.id, "cut": cut},
            )
        return variables[node.id]

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise ValidationError(
            code="invalid_cut_constant",
            message="Region cut supports only numeric or boolean constants.",
            details={"constant": repr(node.value), "cut": cut},
        )

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS:
            raise ValidationError(
                code="invalid_cut_function",
                message="Region cut uses an unsupported function.",
                details={"cut": cut},
            )
        if node.keywords or len(node.args) != 1:
            raise ValidationError(
                code="invalid_cut_function_args",
                message="Supported cut functions must use exactly one positional argument.",
                details={"function": node.func.id, "cut": cut},
            )
        arg = _evaluate_cut_node(node.args[0], variables, cut)
        return _ALLOWED_FUNCTIONS[node.func.id](arg)

    if isinstance(node, ast.UnaryOp):
        op_fn = _ALLOWED_UNARY_OPERATORS.get(type(node.op))
        if op_fn is None:
            raise ValidationError(
                code="invalid_cut_unary_operator",
                message="Region cut uses an unsupported unary operator.",
                details={"operator": type(node.op).__name__, "cut": cut},
            )
        operand = _evaluate_cut_node(node.operand, variables, cut)
        return op_fn(operand)

    if isinstance(node, ast.BinOp):
        op_fn = _ALLOWED_BINARY_OPERATORS.get(type(node.op))
        if op_fn is None:
            raise ValidationError(
                code="invalid_cut_binary_operator",
                message="Region cut uses an unsupported binary operator.",
                details={"operator": type(node.op).__name__, "cut": cut},
            )
        left = _evaluate_cut_node(node.left, variables, cut)
        right = _evaluate_cut_node(node.right, variables, cut)
        return op_fn(left, right)

    if isinstance(node, ast.BoolOp):
        op_fn = _ALLOWED_BOOLEAN_OPERATORS.get(type(node.op))
        if op_fn is None:
            raise ValidationError(
                code="invalid_cut_boolean_operator",
                message="Region cut uses an unsupported boolean operator.",
                details={"operator": type(node.op).__name__, "cut": cut},
            )
        values = [_evaluate_cut_node(value, variables, cut) for value in node.values]
        output = values[0]
        for value in values[1:]:
            output = op_fn(output, value)
        return output

    if isinstance(node, ast.Compare):
        left = _evaluate_cut_node(node.left, variables, cut)
        result = None
        for op, comparator in zip(node.ops, node.comparators):
            op_fn = _ALLOWED_COMPARISON_OPERATORS.get(type(op))
            if op_fn is None:
                raise ValidationError(
                    code="invalid_cut_comparison_operator",
                    message="Region cut uses an unsupported comparison operator.",
                    details={"operator": type(op).__name__, "cut": cut},
                )
            right = _evaluate_cut_node(comparator, variables, cut)
            current = op_fn(left, right)
            result = current if result is None else (result & current)
            left = right
        return result

    raise ValidationError(
        code="invalid_cut_ast_node",
        message="Region cut contains unsupported syntax.",
        details={"node": type(node).__name__, "cut": cut},
    )


def _normalize_mask(raw_mask: Any, n_events: int, cut: str) -> np.ndarray:
    """Normalize cut output to a 1D boolean mask."""
    if isinstance(raw_mask, (bool, np.bool_)):
        return np.full(n_events, bool(raw_mask), dtype=bool)

    mask = np.asarray(raw_mask)
    if mask.ndim != 1:
        raise ValidationError(
            code="invalid_cut_mask_shape",
            message="Region cut must produce a 1D mask.",
            details={"shape": list(mask.shape), "cut": cut},
        )
    if len(mask) != n_events:
        raise ValidationError(
            code="invalid_cut_mask_length",
            message="Region cut mask length must match event count.",
            details={"mask_length": int(len(mask)), "n_events": int(n_events), "cut": cut},
        )
    return mask.astype(bool)


def _load_array_payload(path: str) -> ConvertRootToArrayResult:
    """Load and validate convert_root_to_array output JSON."""
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise ValidationError(
            code="input_array_not_found",
            message="input_array_path does not point to an existing file.",
            details={"input_array_path": str(resolved)},
        )
    try:
        with resolved.open("r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        raise ValidationError(
            code="input_array_invalid_json",
            message="Failed to parse input_array_path as JSON.",
            details={"input_array_path": str(resolved), "error": str(exc)},
        ) from exc

    try:
        return ConvertRootToArrayResult.model_validate(payload)
    except Exception as exc:
        raise ValidationError(
            code="input_array_schema_invalid",
            message="input_array_path does not match convert_root_to_array result schema.",
            details={"input_array_path": str(resolved), "error": str(exc)},
        ) from exc


def _validate_event_alignment(data: dict[str, np.ndarray]) -> int:
    """Ensure all observable arrays share the same event axis length."""
    if not data:
        return 0
    lengths = {name: int(len(values)) for name, values in data.items()}
    unique_lengths = set(lengths.values())
    if len(unique_lengths) != 1:
        raise ValidationError(
            code="inconsistent_event_lengths",
            message="Observable arrays have inconsistent event counts.",
            details={"lengths": lengths},
        )
    return next(iter(unique_lengths))


def compute_binned_yields(
    request: ComputeBinnedYieldsRequest | dict[str, Any],
) -> ComputeBinnedYieldsResult:
    """Compute deterministic per-region binned yields for a single process."""
    if isinstance(request, dict):
        request = ComputeBinnedYieldsRequest.model_validate(request)

    try:
        converted = _load_array_payload(request.input_array_path)

        if converted.process != request.process:
            raise ValidationError(
                code="process_mismatch",
                message="Requested process does not match process in input array payload.",
                details={
                    "request_process": request.process,
                    "payload_process": converted.process,
                },
            )

        variables = {name: np.asarray(values) for name, values in converted.data.items()}
        n_events = _validate_event_alignment(variables)

        weights: np.ndarray | None = None
        if converted.weights is not None:
            weights = np.asarray(converted.weights, dtype=float)
            if weights.ndim != 1 or len(weights) != n_events:
                raise ValidationError(
                    code="weights_length_mismatch",
                    message="Weights must be a 1D array aligned with event count.",
                    details={
                        "weights_shape": list(weights.shape),
                        "weights_length": int(len(weights)) if weights.ndim > 0 else 0,
                        "n_events": int(n_events),
                    },
                )

        regions_result: dict[str, dict[str, Any]] = {}
        for region_name, region in request.regions.items():
            if region.observable not in variables:
                raise ValidationError(
                    code="missing_observable_branch",
                    message="Region observable is not present in input data.",
                    details={
                        "region": region_name,
                        "observable": region.observable,
                        "available_observables": sorted(variables.keys()),
                    },
                )

            parsed_cut = _parse_cut_expression(region.cut)
            raw_mask = _evaluate_cut_node(parsed_cut, variables, region.cut)
            mask = _normalize_mask(raw_mask, n_events, region.cut)

            observable_values = np.asarray(variables[region.observable], dtype=float)
            selected_values = observable_values[mask]
            selected_weights = weights[mask] if weights is not None else None

            yields, _ = np.histogram(
                selected_values,
                bins=np.asarray(region.bin_edges, dtype=float),
                weights=selected_weights,
            )

            regions_result[region_name] = {
                "observable": region.observable,
                "bin_edges": [float(edge) for edge in region.bin_edges],
                "yields": [float(value) for value in yields.tolist()],
            }

        return ComputeBinnedYieldsResult(
            schema_version="1.0",
            analysis_version=request.analysis_version,
            process=request.process,
            is_data=request.is_data,
            regions=regions_result,
            metadata={
                "source_array": str(Path(request.input_array_path).expanduser().resolve()),
                "n_events_processed": int(n_events),
            },
        )
    except RootMLToolError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise ConversionError(
            code="compute_binned_yields_failed",
            message="Unexpected failure during binned yield computation.",
            details={"error": str(exc)},
        ) from exc

