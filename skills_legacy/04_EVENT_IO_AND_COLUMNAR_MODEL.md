# Skill: Event IO and Columnar Model

## Layer 1 — Physics Policy
Event ingestion must preserve the information required for object definition, event selection, and weighting.

Policy requirements:
- support event-level and object-level observables
- preserve variable-length object collections
- keep event weights available for downstream weighted yields and fits
- permit scalable reading for large samples without changing physics content

## Layer 2 — Workflow Contract
### Required Artifacts
- columnar event artifact containing scalar event fields and jagged object collections
- IO diagnostics artifact with event counts and available field inventory
- optional cache artifact for reuse in downstream stages

### Acceptance Checks
- loaded event count is reported and non-negative
- required analysis fields are present or explicitly flagged missing
- object collections preserve per-event multiplicity
- event-weight information is retained or explicitly derived

## Layer 3 — Example Implementation
### Supported IO (Current Repository)
- ROOT via `uproot`
- Parquet via `pyarrow/pandas`
- Awkward Array internal representation

### Function Contract (Current Repository)
`load_events(files, tree_name, branches, max_events=None) -> events`

### CLI (Current Repository)
`python -m analysis.io.readers --registry outputs/samples.registry.json --sample <ID> --max-events 10000 --out outputs/cache/<ID>.parquet`
