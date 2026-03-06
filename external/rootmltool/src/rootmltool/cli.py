"""Command-line interface for rootmltool."""

from __future__ import annotations

import argparse
import json
from typing import Any

from rich.console import Console
from rich.table import Table

from .exceptions import RootMLToolError, ValidationError
from .extract import extract_branches
from .inspect import inspect_root_file
from .schemas import ExtractionRequest, FilterCondition


def _coerce_value(raw: str) -> Any:
    """Best-effort scalar coercion from CLI strings."""
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"

    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


def _parse_filter_expression(expression: str) -> FilterCondition:
    """Parse `branch:op:value` syntax into a filter condition."""
    parts = expression.split(":", 2)
    if len(parts) != 3:
        raise ValidationError(
            code="invalid_filter_expression",
            message="Filter must be `branch:op:value`.",
            details={"expression": expression},
        )

    branch, op, raw_value = parts
    value: Any
    if op == "in":
        value = [_coerce_value(item.strip()) for item in raw_value.split(",") if item.strip()]
    else:
        value = _coerce_value(raw_value)

    return FilterCondition(branch=branch, op=op, value=value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rootmltool", description="ROOT inspection and extraction CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a ROOT file")
    inspect_parser.add_argument("--path", required=True, help="Path to ROOT file")
    inspect_parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")

    extract_parser = subparsers.add_parser("extract", help="Extract branches from a ROOT tree")
    extract_parser.add_argument("--path", required=True, help="Path to ROOT file")
    extract_parser.add_argument("--tree", required=True, help="Tree name")
    extract_parser.add_argument("--branches", nargs="+", required=True, help="Branch names to extract")
    extract_parser.add_argument("--entry-start", type=int, default=None, help="First entry index")
    extract_parser.add_argument("--entry-stop", type=int, default=None, help="Final entry index (exclusive)")
    extract_parser.add_argument(
        "--filter",
        action="append",
        default=[],
        help="Filter in branch:op:value format; can be repeated",
    )
    extract_parser.add_argument(
        "--output-format",
        choices=["dict", "numpy", "pandas", "parquet"],
        default="dict",
        help="Result output format",
    )
    extract_parser.add_argument("--output-path", default=None, help="Parquet destination path")
    extract_parser.add_argument("--no-data", action="store_true", help="Return metadata only")
    extract_parser.add_argument("--json", action="store_true", dest="json_output", help="Print JSON output")

    return parser


def _render_inspect_table(console: Console, summary: dict[str, Any]) -> None:
    table = Table(title="ROOT File Summary")
    table.add_column("Tree")
    table.add_column("Entries", justify="right")
    table.add_column("Branches", justify="right")

    for tree in summary["trees"]:
        table.add_row(tree["name"], str(tree["num_entries"]), str(len(tree["branches"])))

    console.print(table)


def _render_extract_table(console: Console, result: dict[str, Any]) -> None:
    table = Table(title="Extraction Result")
    table.add_column("Branch")
    table.add_column("Shape")

    for branch, shape in result["shapes"].items():
        table.add_row(branch, str(shape))

    console.print(f"Events: {result['num_events']}")
    if result.get("output_path"):
        console.print(f"Output: {result['output_path']}")
    console.print(table)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    console = Console()

    try:
        if args.command == "inspect":
            summary = inspect_root_file(args.path).model_dump(mode="json")
            if args.json_output:
                console.print_json(json.dumps(summary))
            else:
                _render_inspect_table(console, summary)
            return 0

        filters = [_parse_filter_expression(expr) for expr in args.filter]
        request = ExtractionRequest(
            path=args.path,
            tree=args.tree,
            branches=args.branches,
            filters=filters,
            entry_start=args.entry_start,
            entry_stop=args.entry_stop,
            output_format=args.output_format,
            output_path=args.output_path,
            include_data=not args.no_data,
        )
        result = extract_branches(request).model_dump(mode="json")

        if args.json_output:
            console.print_json(json.dumps(result))
        else:
            _render_extract_table(console, result)

        return 0
    except RootMLToolError as exc:
        console.print(f"[red]{exc.code}[/red]: {exc.message}")
        if exc.details:
            console.print_json(json.dumps(exc.details))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
