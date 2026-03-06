"""Deterministic conversion from ROOT TTrees to analysis-ready array payloads."""

from __future__ import annotations

import ast
import json
import operator
from pathlib import Path
from typing import Any

import awkward as ak

from .exceptions import ConversionError, RootMLToolError, ValidationError
from .io import read_tree_arrays
from .schemas import ConvertRootToArrayRequest, ConvertRootToArrayResult


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
    ast.And: operator.and_,
    ast.Or: operator.or_,
}
_ALLOWED_COMPARISON_OPERATORS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def _parse_preselection(preselection: str) -> ast.Expression:
    """Parse preselection into AST and reject malformed expressions."""
    try:
        parsed = ast.parse(preselection, mode="eval")
    except SyntaxError as exc:
        raise ValidationError(
            code="invalid_preselection_syntax",
            message="`preselection` contains invalid syntax.",
            details={"preselection": preselection, "error": str(exc)},
        ) from exc

    # Support common shorthand like: `pt > 20 & abs(eta) < 2.5`
    # by normalizing it to: `(pt > 20) & (abs(eta) < 2.5)`.
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


def _preselection_symbol_names(parsed: ast.Expression) -> set[str]:
    """Return variable names referenced by a parsed preselection expression."""
    names = {node.id for node in ast.walk(parsed) if isinstance(node, ast.Name)}
    return {name for name in names if name not in _ALLOWED_FUNCTIONS}


def _merged_branch_list(request: ConvertRootToArrayRequest) -> list[str]:
    """Return deterministic branch read order for observables, weights, and preselection."""
    merged = list(request.branches)
    if request.weight_branch and request.weight_branch not in merged:
        merged.append(request.weight_branch)
    if request.preselection:
        symbols = sorted(_preselection_symbol_names(_parse_preselection(request.preselection)))
        for symbol in symbols:
            if symbol not in merged:
                merged.append(symbol)
    return merged


def _concatenate_records(records: list[ak.Array]) -> ak.Array:
    """Concatenate record arrays along event axis."""
    if len(records) == 1:
        return records[0]
    return ak.concatenate(records, axis=0)


def _evaluate_preselection_node(
    node: ast.AST,
    variables: dict[str, Any],
    preselection: str,
) -> Any:
    """Safely evaluate a restricted preselection AST using awkward-compatible operators."""
    if isinstance(node, ast.Expression):
        return _evaluate_preselection_node(node.body, variables, preselection)

    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ValidationError(
                code="unknown_preselection_symbol",
                message="`preselection` references a symbol that is not a loaded branch.",
                details={"symbol": node.id, "preselection": preselection},
            )
        return variables[node.id]

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise ValidationError(
            code="invalid_preselection_constant",
            message="`preselection` may only use numeric or boolean constants.",
            details={"constant": repr(node.value), "preselection": preselection},
        )

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCTIONS:
            raise ValidationError(
                code="invalid_preselection_function",
                message="`preselection` uses an unsupported function.",
                details={"preselection": preselection},
            )
        if node.keywords or len(node.args) != 1:
            raise ValidationError(
                code="invalid_preselection_function_args",
                message="Supported preselection functions must use exactly one positional argument.",
                details={"function": node.func.id, "preselection": preselection},
            )
        return _ALLOWED_FUNCTIONS[node.func.id](
            _evaluate_preselection_node(node.args[0], variables, preselection)
        )

    if isinstance(node, ast.UnaryOp):
        op_fn = _ALLOWED_UNARY_OPERATORS.get(type(node.op))
        if op_fn is None:
            raise ValidationError(
                code="invalid_preselection_unary_operator",
                message="`preselection` uses an unsupported unary operator.",
                details={"operator": type(node.op).__name__, "preselection": preselection},
            )
        return op_fn(_evaluate_preselection_node(node.operand, variables, preselection))

    if isinstance(node, ast.BinOp):
        op_fn = _ALLOWED_BINARY_OPERATORS.get(type(node.op))
        if op_fn is None:
            raise ValidationError(
                code="invalid_preselection_binary_operator",
                message="`preselection` uses an unsupported binary operator.",
                details={"operator": type(node.op).__name__, "preselection": preselection},
            )
        left = _evaluate_preselection_node(node.left, variables, preselection)
        right = _evaluate_preselection_node(node.right, variables, preselection)
        return op_fn(left, right)

    if isinstance(node, ast.BoolOp):
        op_fn = _ALLOWED_BOOLEAN_OPERATORS.get(type(node.op))
        if op_fn is None:
            raise ValidationError(
                code="invalid_preselection_boolean_operator",
                message="`preselection` uses an unsupported boolean operator.",
                details={"operator": type(node.op).__name__, "preselection": preselection},
            )
        values = [
            _evaluate_preselection_node(value, variables, preselection)
            for value in node.values
        ]
        output = values[0]
        for value in values[1:]:
            output = op_fn(output, value)
        return output

    if isinstance(node, ast.Compare):
        left = _evaluate_preselection_node(node.left, variables, preselection)
        result = None
        for op, comparator in zip(node.ops, node.comparators):
            op_fn = _ALLOWED_COMPARISON_OPERATORS.get(type(op))
            if op_fn is None:
                raise ValidationError(
                    code="invalid_preselection_comparison_operator",
                    message="`preselection` uses an unsupported comparison operator.",
                    details={"operator": type(op).__name__, "preselection": preselection},
                )
            right = _evaluate_preselection_node(comparator, variables, preselection)
            current = op_fn(left, right)
            result = current if result is None else (result & current)
            left = right
        return result

    raise ValidationError(
        code="invalid_preselection_ast_node",
        message="`preselection` contains unsupported syntax.",
        details={"node": type(node).__name__, "preselection": preselection},
    )


def _apply_preselection(arrays: ak.Array, preselection: str | None) -> ak.Array:
    """Filter arrays with an optional deterministic preselection expression."""
    if preselection is None:
        return arrays

    parsed = _parse_preselection(preselection)
    variables = {name: arrays[name] for name in arrays.fields}
    raw_mask = _evaluate_preselection_node(parsed, variables, preselection)

    if isinstance(raw_mask, bool):
        return arrays if raw_mask else arrays[:0]

    try:
        mask = ak.values_astype(ak.Array(raw_mask), bool)
    except Exception as exc:
        raise ValidationError(
            code="invalid_preselection_mask",
            message="`preselection` did not produce a valid boolean mask.",
            details={"preselection": preselection, "error": str(exc)},
        ) from exc

    if len(mask) != len(arrays):
        raise ValidationError(
            code="invalid_preselection_mask_length",
            message="`preselection` mask length must match event count.",
            details={"mask_length": len(mask), "n_events": len(arrays)},
        )

    return arrays[mask]


def _to_serializable_data_map(arrays: ak.Array, branches: list[str]) -> dict[str, list[Any]]:
    """Build output observable payload."""
    payload: dict[str, list[Any]] = {}
    for branch in branches:
        payload[branch] = ak.to_list(arrays[branch])
    return payload


def convert_root_to_array(
    request: ConvertRootToArrayRequest | dict[str, Any],
) -> ConvertRootToArrayResult:
    """Convert one process worth of ROOT files into JSON-serializable arrays."""
    if isinstance(request, dict):
        request = ConvertRootToArrayRequest.model_validate(request)

    try:
        source_records: list[ak.Array] = []
        read_branches = _merged_branch_list(request)

        for input_path in request.input_paths:
            source_records.append(
                read_tree_arrays(
                    path=input_path,
                    tree=request.tree,
                    branches=read_branches,
                )
            )

        merged = _concatenate_records(source_records)
        filtered = _apply_preselection(merged, request.preselection)
        if request.max_events is not None:
            filtered = filtered[: int(request.max_events)]

        data_payload = _to_serializable_data_map(
            arrays=filtered,
            branches=request.branches,
        )
        weights_payload = (
            ak.to_list(filtered[request.weight_branch])
            if request.weight_branch is not None
            else None
        )

        result = ConvertRootToArrayResult(
            process=request.process,
            n_events=int(len(filtered)),
            data=data_payload,
            weights=weights_payload,
            metadata={
                "source_files": [str(Path(p).expanduser().resolve()) for p in request.input_paths],
                "tree_name": request.tree,
                "preselection": request.preselection,
                "max_events": request.max_events,
                "backend": "uproot",
            },
        )

        if request.output_path:
            output_path = Path(request.output_path).expanduser().resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("w", encoding="utf-8") as f:
                json.dump(result.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

        return result
    except RootMLToolError:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard
        raise ConversionError(
            code="convert_root_to_array_failed",
            message="Unexpected failure during ROOT-to-array conversion.",
            details={"error": str(exc)},
        ) from exc


# TODO: Add optional chunked conversion for very large datasets.
