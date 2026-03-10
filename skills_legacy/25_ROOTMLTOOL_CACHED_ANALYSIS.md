# Skill: RootMLTool Cached Analysis Backend Selection

## Layer 1 — Physics Policy
Switching event I/O backends must not change physics conclusions beyond defined numerical tolerance.

Policy requirements:
- Existing native pipeline behavior must remain present and unchanged.
- Only the ingestion/cache stage may change when selecting `rootmltool`; object definitions, selections, histogramming, and statistical fitting must remain unchanged.
- `rootmltool` is a candidate/operational backend, not an automatic physics-model change.
- Backend promotion to default requires a documented parity pass against a native-baseline run.

## Layer 2 — Workflow Contract
### Runtime Backend Selection
- Default behavior is `analysis.cli run --event-backend native`.
- Use `analysis.cli run --event-backend auto` when you want runtime backend selection.
- `auto` resolves to `rootmltool` when vendored source is available/importable; otherwise it resolves to `native`.
- Use `--event-backend native` for baseline/reference production.
- Use `--event-backend rootmltool` when JSON intermediates are required for fast reruns.

### RootMLTool Cache Behavior
- RootML cache artifacts are written under `outputs/cache/rootmltool/`.
- Per-sample artifacts:
  - `<sample_id>.arrays.json`
  - `<sample_id>.arrays.meta.json`
- Cache reuse is enabled by default.
- Force rebuild with `--no-rootml-cache-reuse`.

### Parity Gate (Required Before Promotion)
- Run baseline and candidate with identical inputs, region config, and event cap.
- Compare outputs with:
  - `python -m analysis.cli parity-check --baseline <native_outputs> --candidate <rootml_outputs> --out <report.json> --fail-on-mismatch`
- Promotion requirement:
  - parity status must be `pass` (no failed metrics, no missing metrics, no extra metrics).

## Layer 3 — Example Implementation
### Baseline Run
```bash
python -m analysis.cli run \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --inputs input-data \
  --outputs outputs_native_ref \
  --event-backend native
```

### Candidate Run (Runtime Choice)
```bash
python -m analysis.cli run \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --inputs input-data \
  --outputs outputs_auto_candidate \
  --event-backend auto
```

### Required Parity Check
```bash
python -m analysis.cli parity-check \
  --baseline outputs_native_ref \
  --candidate outputs_auto_candidate \
  --out outputs_auto_candidate/report/parity_native_vs_auto.json \
  --fail-on-mismatch
```
