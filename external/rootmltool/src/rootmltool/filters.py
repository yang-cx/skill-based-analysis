"""Deterministic event filter helpers."""

from __future__ import annotations

import operator
from collections.abc import Callable, Sequence
from typing import Any

import awkward as ak
import numpy as np

from .exceptions import ValidationError
from .schemas import FilterCondition

EventFilter = Callable[[ak.Array], ak.Array]

_OPS: dict[str, Callable[[Any, Any], Any]] = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "ge": operator.ge,
    "lt": operator.lt,
    "le": operator.le,
}


def build_filter_callable(condition: FilterCondition) -> EventFilter:
    """Build a callable that returns a boolean event mask for one condition."""

    def _filter(arrays: ak.Array) -> ak.Array:
        return _evaluate_condition(arrays, condition)

    return _filter


def _evaluate_condition(arrays: ak.Array, condition: FilterCondition) -> ak.Array:
    """Evaluate a single filter condition and return a boolean mask."""
    if condition.branch not in arrays.fields:
        raise ValidationError(
            code="missing_filter_branch",
            message="Filter branch is not present in extracted arrays.",
            details={"branch": condition.branch, "available": list(arrays.fields)},
        )

    target = arrays[condition.branch]

    if condition.op == "in":
        values = condition.value if isinstance(condition.value, list) else [condition.value]
        try:
            mask_np = np.isin(np.asarray(ak.to_numpy(target)), np.asarray(values))
            return ak.Array(mask_np)
        except Exception as exc:
            raise ValidationError(
                code="unsupported_in_filter",
                message="`in` filter currently supports flat numeric/string branches only.",
                details={"branch": condition.branch, "error": str(exc)},
            ) from exc

    comparator = _OPS[condition.op]
    try:
        return comparator(target, condition.value)
    except Exception as exc:
        raise ValidationError(
            code="filter_evaluation_failed",
            message="Failed to evaluate filter condition.",
            details={"condition": condition.model_dump(mode="json"), "error": str(exc)},
        ) from exc


def apply_filter_conditions(
    arrays: ak.Array,
    conditions: Sequence[FilterCondition],
) -> ak.Array:
    """Apply all conditions with logical AND semantics."""
    if not conditions:
        return arrays

    mask = None
    for condition in conditions:
        current = _evaluate_condition(arrays, condition)
        mask = current if mask is None else (mask & current)

    # TODO: Add configurable filter composition (AND/OR groups).
    return arrays[mask]
