# rootmltool

`rootmltool` is a deterministic Python package for inspecting ROOT files and extracting analysis-ready data for ML workflows.

## Features

- Inspect ROOT file structure (trees, branches, metadata)
- Extract selected branches from a tree
- Apply deterministic event filters
- Convert extracted data to dict/numpy/pandas/parquet outputs
- Use programmatically or from a CLI
- Wrap with a JSON contract via `run_tool(payload: dict) -> dict`

## Install

```bash
pip install .
```

For parquet export support:

```bash
pip install .[parquet]
```

For development:

```bash
pip install .[dev,parquet]
```

## CLI

Inspect a ROOT file:

```bash
rootmltool inspect --path ./events.root
```

Extract selected branches with a filter:

```bash
rootmltool extract \
  --path ./events.root \
  --tree Events \
  --branches pt eta \
  --filter pt:gt:20 \
  --output-format pandas
```

## Programmatic usage

```python
from rootmltool.inspect import inspect_root_file
from rootmltool.extract import extract_branches
from rootmltool.schemas import ExtractionRequest

summary = inspect_root_file("events.root")

request = ExtractionRequest(
    path="events.root",
    tree="Events",
    branches=["pt", "eta"],
    output_format="dict",
)
result = extract_branches(request)
```

## LangGraph tool wrapper

```python
from rootmltool.tool_entrypoint import run_tool

response = run_tool({
    "action": "inspect",
    "input": {"path": "events.root"}
})
```

## Notes

- Library modules avoid printing and raise structured custom exceptions.
- Full physics-specific logic and advanced ROOT edge-case handling are intentionally left as TODOs.
