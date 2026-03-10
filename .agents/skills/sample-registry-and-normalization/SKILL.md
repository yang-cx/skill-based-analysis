---
name: sample-registry-and-normalization
description: "Repository-specific workflow and policy for Sample Registry and Normalization. Use when Codex needs the required artifacts, validation checks, execution steps, or constraints for this analysis stage in the repo."
---

# Sample Registry and Normalization

## Layer 1 — Physics Policy
Each sample must be mapped to a physics process and classified as data, signal, or background with an explicit normalization convention.

Policy requirements:
- preserve process identity and sample provenance
- distinguish data from simulated samples
- support analysis-context-dependent process roles (the same physics process may be signal in one analysis and background in another)
- apply a consistent MC normalization based on cross section, correction factors, luminosity, and generator-weight sum
- for this ATLAS Open Data Run-2 H->gammagamma workflow, use `lumi_fb = 36.1` for central MC normalization unless an explicit analysis-level override is requested and documented
- record missing normalization inputs explicitly rather than silently assuming values
- when multiple MC samples exist for one physics process (for example alternate generators/modeling), define one nominal/reference sample set for central yields and mark alternative samples for systematic variations only

Normalization convention for simulated samples:
`w_norm = (xsec_pb * k_factor * filter_eff * lumi_fb * 1000.0) / sumw`

## Layer 2 — Workflow Contract
### Required Artifacts
- sample-registry artifact containing sample identity, process mapping, classification, and normalization inputs
- process-role mapping artifact declaring, per analysis target, which processes are treated as signal vs background
- nominal-vs-alternative sample mapping artifact per physics process
- normalization-expression artifact describing how per-event weights are formed
- normalization-audit artifact listing missing inputs and warnings

### Acceptance Checks
- every registered sample has exactly one classification among data, signal, background
- each sample contains process identity and source-file linkage
- process-role assignment is unambiguous for the active analysis objective
- normalization terms are present or explicitly marked as not specified
- normalization value is computable when all required terms are available
- default central-yield registry rows for MC have `lumi_fb = 36.1`
- central-yield workflows include only nominal/reference samples per physics process; alternatives are flagged as non-central

## Layer 3 — Example Implementation
### Registry Fields (Current Repository)
For each sample:
- `sample_id`
- `process_name`
- `kind`: `data | signal | background`
- `analysis_role` (recommended): `signal_nominal | background_nominal | signal_alternative | background_alternative`
- `is_nominal` (recommended boolean)
- `nominal_process_key` (recommended stable physics-process key)
- `files`
- `xsec_pb`
- `k_factor`
- `filter_eff`
- `sumw`
- `lumi_fb`
- `weight_expr`

### CLI (Current Repository)
`python -m analysis.samples.registry --inputs inputs/ --summary analysis/analysis.summary.json --out outputs/samples.registry.json --target-lumi-fb 36.1`

### Downstream Reference
After this skill, run:
- `$mc-normalization-metadata-stacking` for metadata.csv-driven normalization of multi-sample MC stacks in ATLAS Open Data workflows
- `$signal-background-strategy-and-cr-constraints`
