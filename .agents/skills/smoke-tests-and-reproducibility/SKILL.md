---
name: smoke-tests-and-reproducibility
description: "Repository-specific workflow and policy for Smoke Tests and Reproducibility. Use when Codex needs the required artifacts, validation checks, execution steps, or constraints for this analysis stage in the repo."
---

# Smoke Tests and Reproducibility

## Layer 1 — Physics Policy
Automated analysis execution must be reproducible and verifiable across runs.

Policy requirements:
- each critical stage must be testable in a minimal run
- nondeterministic behavior must be controlled
- configuration and code provenance must be recorded
- completion claims require both physics outputs and validation artifacts

## Layer 2 — Workflow Contract
### Required Artifacts
- smoke-test execution artifact with pass/fail status per critical stage
- run-manifest artifact with inputs, configuration fingerprint, and code version
- completion-status artifact indicating whether all required analysis outputs exist

### Acceptance Checks
- summary validation stage passes
- sample-registry and strategy stages pass
- at least one end-to-end mini-run stage passes
- fit and significance stages pass when workspace exists
- blinding, histogram, yield, cut-flow, and report artifacts are all present for completion
- reruns with same inputs/configuration produce consistent metadata fingerprints
- for H->gammagamma resonance fitting, include a PyROOT/RooFit backend-specific smoke check and export the same standard fit/significance schemas

## Layer 3 — Example Implementation
### Smoke Tests (Current Repository)
1. `python -m analysis.config.load_summary --summary analysis/analysis.summary.json --out outputs/summary.normalized.json`
2. `python -m analysis.samples.registry --inputs inputs/ --summary analysis/analysis.summary.json --out outputs/samples.registry.json`
3. `python -m analysis.samples.strategy --registry outputs/samples.registry.json --regions analysis/regions.yaml --summary outputs/summary.normalized.json --out outputs/background_modeling_strategy.json`
4. `python -m analysis.stats.mass_model_selection --fit-id FIT1 --summary outputs/summary.normalized.json --hists outputs/hists --strategy outputs/background_modeling_strategy.json --out outputs/fit/FIT1/background_pdf_choice.json`
5. `python -m analysis.cli run --summary analysis/analysis.summary.json --inputs inputs/ --outputs outputs --max-events 20000 --samples <one_data_sample> <one_mc_sample>`
6. `python -m analysis.stats.fit --workspace outputs/fit/workspace.json --fit-id FIT1 --out outputs/fit/FIT1/results.json`
7. `python -m analysis.stats.significance --workspace outputs/fit/workspace.json --fit-id FIT1 --out outputs/fit/FIT1/significance.json`
8. `python -m analysis.plotting.blinded_regions --outputs outputs --registry outputs/samples.registry.json --regions analysis/regions.yaml --fit-id FIT1`

### Reproducibility Notes (Current Repository)
- include config hash from normalized summary, regions config, and systematics config
- use stable file ordering and fixed seeds when sampling
- store run manifests under a dedicated run directory
- record fit backend in run metadata, with `pyroot_roofit` as primary for H->gammagamma workflows
