---
name: systematics-and-nuisances
description: "Repository-specific workflow and policy for Systematics and Nuisances. Use when Codex needs the required artifacts, validation checks, execution steps, or constraints for this analysis stage in the repo."
---

# Systematics and Nuisances

## Layer 1 — Physics Policy
Systematic uncertainties must be represented as nuisance parameters with explicit scope and correlation assumptions.

Policy requirements:
- support at least normalization and statistical uncertainties
- include shape uncertainties when variation templates are available
- define which samples and regions are affected by each nuisance
- encode CR/SR correlation assumptions for constrained backgrounds
- if only statistical uncertainties are available, record that limitation explicitly
- when multiple MC samples model one physics process, treat non-nominal samples as variation inputs for systematics rather than additional central-yield contributions

## Layer 2 — Workflow Contract
### Required Artifacts
- nuisance-model artifact listing nuisance names, types, affected components, and correlations
- optional shape-variation artifact set for up/down template variations
- uncertainty-provenance artifact documenting assumptions and missing inputs
- nominal-vs-variation sample mapping artifact for each process entering systematics

### Acceptance Checks
- every nuisance has declared type and affected scope
- correlations across regions/processes are explicitly stated or defaulted with metadata
- statistical model can be constructed using the nuisance artifact
- stat-only fallback is explicitly flagged when applied
- central yields used for fits/cut flows do not double count alternate generator/modeling samples
- variation samples are linked to a nominal process and used only through nuisance variations

## Layer 3 — Example Implementation
### Data Model (Current Repository)
`outputs/systematics.json` includes:
- nuisance name
- type: `norm | shape | stat`
- affected samples/regions
- optional correlation group

Additional inputs when available:
- `outputs/background_modeling_strategy.json`
- `outputs/cr_sr_constraint_map.json`
- `outputs/fit/*/spurious_signal.json`

### CLI (Current Repository)
`python -m analysis.stats.pyhf_workspace --summary outputs/summary.normalized.json --hists outputs/hists --systematics outputs/systematics.json --out outputs/fit/workspace.json`
