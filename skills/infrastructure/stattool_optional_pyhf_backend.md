---
skill_type: infrastructure
domain: hep_analysis
stage: caching
original_id: "26"
original_filename: "26_STATTOOL_OPTIONAL_PYHF_BACKEND.md"
---

# Skill: StatTool Optional PyHF Backend

## Layer 1 — Physics Policy
`stattool` is an additive pyhf tool option and must not replace existing native statistics workflows.

Policy requirements:
- Keep existing in-repo stats implementation intact.
- Use `stattool` only as an optional backend for pyhf fit operations.
- Preserve existing RooFit-primary policy for H->gammagamma workflows.
- For H->gammagamma primary inference, pyhf/stattool is never a substitute for RooFit analytic-function fits.
- Record which pyhf implementation backend was requested and resolved at runtime.

## Layer 2 — Workflow Contract
### Runtime Selection
- Default is native pyhf path: `--pyhf-backend native`.
- Optional values:
  - `--pyhf-backend stattool`
  - `--pyhf-backend auto` (uses `stattool` only when vendored/importable)
- Applies when `--fit-backend pyhf` or when pyhf cross-checks run.
- For H->gammagamma workflows, this skill applies only to cross-check mode and must not override primary RooFit outputs.

### Add-Only Constraint
- Never remove or bypass existing native stats code.
- If `stattool` is unavailable, `auto` must fall back to native.
- If `stattool` is explicitly requested and unavailable, fail clearly with actionable error.
- If RooFit primary capability is unavailable in H->gammagamma workflows, block primary execution instead of promoting pyhf/stattool to primary.

### Provenance Requirements
- Run artifacts must include:
  - `pyhf_backend_requested`
  - `pyhf_backend_resolved`
  - `stattool_available`
  - `stattool_availability_reason`
  - `cross_check_only` (required when pyhf/stattool is used in H->gammagamma workflows)

## Layer 3 — Example Implementation
### Native Default
```bash
python -m analysis.cli run \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --inputs input-data \
  --outputs outputs_native_stats \
  --fit-backend pyhf
```

### Runtime Auto Selection
```bash
python -m analysis.cli run \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --inputs input-data \
  --outputs outputs_auto_stats \
  --fit-backend pyhf \
  --pyhf-backend auto
```

### Force StatTool
```bash
python -m analysis.cli run \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --inputs input-data \
  --outputs outputs_stattool_stats \
  --fit-backend pyhf \
  --pyhf-backend stattool
```
