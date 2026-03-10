---
skill_type: procedure
domain: hep_analysis
stage: fit
original_id: "10"
original_filename: "10_WORKSPACE_AND_FIT_PYHF.md"
---

# Skill: Workspace and Fit (RooFit-Primary for H->gammagamma)

## Layer 1 — Physics Policy
Statistical inference must map selected regions, signal/background models, and nuisance parameters into a likelihood model with explicit parameters of interest.

Policy requirements:
- each fit configuration defines channels, samples, POIs, and nuisance terms
- control-region information may constrain signal-region background normalizations when correlations are defined
- analytic mass-shape choices (when used) must feed the final statistical model consistently
- fit diagnostics and parameter estimates must be preserved for interpretation
- for H->gammagamma resonance workflows, the primary backend must be `pyroot_roofit`; `pyhf` may be used only as an explicitly labeled cross-check
- for category-resolved resonance fits, support arbitrary category counts from configuration (do not hard-code a fixed number of categories)
- for combined category fits, allow one shared signal-strength parameter (`mu`) correlated across categories while keeping background-shape parameters independent per category

## Layer 2 — Workflow Contract
### Required Artifacts
- statistical-workspace artifact per fit configuration
- fit-result artifact containing best-fit POI estimates, uncertainties, status, and diagnostics
- fit-configuration hash/provenance artifact to ensure reproducibility of the model setup
- fit-backend artifact declaring primary backend (`pyroot_roofit` for H->gammagamma) and configuration provenance

### Acceptance Checks
- workspace artifact loads successfully in the chosen inference backend
- fit execution completes with converged status or actionable diagnostics
- POI estimates and uncertainties are present when fit succeeds
- model provenance metadata is attached to fit results
- fit artifact schema remains consistent across backends for downstream significance/reporting stages
- H->gammagamma fit artifacts declare `pyroot_roofit` as the primary backend

## Layer 3 — Example Implementation
### Mapping (Current Repository)
A fit configuration maps to:
- channels: included regions
- samples: signal/background/data
- POIs: parameters of interest
- nuisances: from systematics artifact
- CR/SR correlations: from constraint-map artifact when available
- analytic mass-model choice: from signal/background PDF artifacts when available
- backend: primary `pyroot_roofit` for H->gammagamma resonance analytic-function fits; optional `pyhf` cross-check
- category cardinality: derived from configured `regions_included` or explicit category list override (arbitrary `N`)

### CLI (Current Repository)
`python -m analysis.stats.fit --workspace outputs/fit/workspace.json --fit-id FIT1 --out outputs/fit/FIT1/results.json`

Category-resolved RooFit combined likelihood (arbitrary number of categories):
`python -m analysis.stats.roofit_combined --outputs outputs --registry outputs/samples.registry.json --regions analysis/regions.yaml --fit-id FIT1 --subdir roofit_combined`

### Downstream Reference
After this skill, run:
- `core_pipeline/profile_likelihood_significance.md`
