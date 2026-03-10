---
skill_type: decision
domain: hep_analysis
stage: design
original_id: "15"
original_filename: "15_SIGNAL_BACKGROUND_STRATEGY_AND_CR_CONSTRAINTS.md"
---

# Skill: Signal/Background Strategy and CR Constraints

## Layer 1 — Physics Policy
Signal and background modeling choices must be explicitly classified and linked to control-to-signal normalization assumptions.

Policy requirements:
- classify all samples as data, signal, or background
- treat signal/background assignment as analysis-target dependent (for example inclusive Higgs analyses vs process-targeted analyses such as ttH)
- define whether each background is modeled by simulation templates or data-driven methods
- declare whether control-region constraints transfer to signal regions for each constrained background
- require constrained CR->SR mappings to be disjoint at event level by default; any overlap must be explicit and justified
- preserve compatibility with analyses where background shape is analytic and simulation is used mainly for functional-form studies

## Layer 2 — Workflow Contract
### Required Artifacts
- sample-classification artifact listing data/signal/background sample memberships
- analysis-target declaration artifact describing which process(es) are the signal hypothesis for this run
- background-modeling-strategy artifact describing per-process modeling mode and normalization source
- control-to-signal constraint-map artifact defining constrained backgrounds, source/control regions, target/signal regions, and correlation intent
- CR/SR overlap-policy artifact for each constrained mapping

### Acceptance Checks
- every sample is classified exactly once
- process-role choices are consistent with the declared analysis target and are documented when deviating from an inclusive treatment
- each background process has explicit modeling strategy metadata
- each constrained background has explicit control-to-signal mapping metadata
- each constrained CR->SR mapping declares overlap policy and passes overlap checks unless an explicit exception is recorded
- downstream statistical modeling can consume these artifacts without ambiguity

## Layer 3 — Example Implementation
### Expected Outputs (Current Repository)
- `outputs/background_modeling_strategy.json`
- `outputs/samples.classification.json`
- `outputs/cr_sr_constraint_map.json`

### CLI (Current Repository)
`python -m analysis.samples.strategy --registry outputs/samples.registry.json --regions analysis/regions.yaml --summary outputs/summary.normalized.json --out outputs/background_modeling_strategy.json`

### Downstream Reference
Use before:
- `core_pipeline/systematics_and_nuisances.md`
- `core_pipeline/workspace_and_fit_pyhf.md`

Summarize in:
- `core_pipeline/plotting_and_report.md`
