---
name: skills-pack-index
description: "Repository-wide analysis workflow index and policy contract. Use when Codex needs the overall stage ordering, required artifacts, acceptance checks, or cross-skill coordination rules for this HEP analysis repo."
---

# Skills Pack Index

## Layer 1 — Physics Policy
The analysis skill pack must encode a complete, scientifically coherent HEP workflow from analysis definition to statistical interpretation.

Core policy requirements:
- Keep analysis decisions config-driven and reproducible.
- Preserve a clear chain from event selection through statistical inference.
- Treat signal and background modeling choices as explicit methodological choices.
- For the default Run-2 H->gammagamma workflow in this repository, central MC normalization must use `lumi_fb = 36.1`.
- For H->gammagamma resonance analyses in this repository, use `pyroot_roofit` as the mandatory primary backend for mass fits and significance; non-ROOT backends may be used only as explicitly labeled cross-checks.
- Never replace existing workflow implementations when adding tools from other projects; keep new tools as additive, selectable options.
- Enforce blinding where required by the analysis strategy.
- Require visual and statistical validation before declaring completion.
- Require execution of post-run skill extraction (`$extract-new-skill-from-failure`) for every completed run; missing extraction blocks handoff-ready status.
- Use the term **cut flow** consistently.

## Layer 2 — Workflow Contract
### Required Artifacts
- normalized analysis-definition artifact with validated region and fit semantics
- sample-classification and normalization artifact
- process-role and nominal-vs-alternative sample mapping artifacts for context-dependent signal/background definitions
- open-data metadata-driven normalization artifact for multi-component MC stacking (when this workflow is used)
- signal/background strategy artifact including control-to-signal normalization intent
- category/region partition specification artifact (category axis x region axis)
- partition completeness/exclusivity check artifact
- partition manifest artifact for downstream stages
- region-selection artifact with cut flow and yield summaries
- process-resolved cut-flow artifact (individual process contributions plus combined signal/background totals)
- region-overlap audit artifact documenting SR/CR overlap checks and any explicit exceptions
- histogram-template artifact for fit observables
- signal-shape and background-model-selection artifacts when analytic mass modeling is used
- category-resolved RooFit artifacts for the H->gammagamma analytic resonance workflow (per-category DS-CB parameters, sideband-fit parameters, blinded category mass plots, and mass-window expected-yield table)
- systematic-uncertainty artifact
- statistical-workspace artifact and per-fit result artifacts
- fit-backend declaration artifact per fit with `pyroot_roofit` primary-backend provenance and any optional cross-check backend notes
- discovery-significance artifact per fit
- optional Asimov expected-significance artifact per fit with generation provenance
- Asimov sensitivity artifacts should document full-range generation/evaluation and tested generation hypothesis (for example `mu_gen = 0` for discovery sensitivity)
- blinding-summary artifact and blinded region-visualization artifact set
- visual-verification artifact set for required diagnostics
- data-MC discrepancy artifacts (`outputs/report/data_mc_discrepancy_audit.json`, `outputs/report/data_mc_check_log.json`) for every run, including zero-discrepancy runs
- narrative analysis report artifact
- final publication-style report artifact with agent decision appendix
- skill-extraction summary artifact at `outputs/report/skill_extraction_summary.json` (required even when no candidates are found)

### Acceptance Checks
- all pipeline-stage artifacts exist and are readable by downstream stages
- each declared fit has a fit-result artifact and significance artifact
- each declared fit has an explicit backend declaration and backend-consistent diagnostics
- each H->gammagamma fit declares `pyroot_roofit` as the primary backend
- region-level histograms, yields, and cut flows are mutually consistent within tolerance
- signal and control regions used together in a fit are mutually exclusive at event level unless an explicit, justified overlap exception is declared
- blinding metadata confirms signal-region data handling policy
- required verification plots are present
- substantial data-MC discrepancies are explicitly reported and not cosmetically tuned away
- `outputs/report/data_mc_discrepancy_audit.json` exists, is readable, and declares `status` in `{no_substantial_discrepancy, discrepancy_investigated_bug_found, discrepancy_investigated_no_bug_found}`
- `outputs/report/data_mc_check_log.json` exists and is readable
- final report summarizes selection, modeling, fit, significance, and implementation differences
- partition checks confirm category coverage/exclusivity and unique `(category, region)` keys
- central yields/cut flows do not double count physics processes represented by both nominal and alternative MC samples
- `outputs/report/skill_extraction_summary.json` exists, is readable, and has `status` in `{none_found, candidates_created}`

## Layer 3 — Example Implementation
### Required Inputs (Current Repository)
- Analysis summary JSON: `analysis/analysis.summary.json`
- Samples: `inputs/` (or a provided path)
- Output directory: `outputs/`

### Minimum Outputs (Current Repository)
- `outputs/cutflows/*.json`
- `outputs/cutflows_process_breakdown.json` (or equivalent process-resolved cut-flow artifact)
- `outputs/yields/*.json`
- `outputs/hists/**/*.npz` (or ROOT, but be consistent)
- `outputs/fit/*/results.json`
- `outputs/fit/*/significance.json`
- `outputs/background_modeling_strategy.json`
- `outputs/samples.classification.json`
- `outputs/cr_sr_constraint_map.json`
- `outputs/report/partition_spec.json`
- `outputs/report/partition_checks.json`
- `outputs/manifest/partitions.json`
- `outputs/fit/*/signal_pdf.json`
- `outputs/fit/*/background_pdf_scan.json`
- `outputs/fit/*/background_pdf_choice.json`
- `outputs/fit/*/spurious_signal.json`
- `outputs/fit/*/blinded_cr_fit.json`
- `outputs/fit/*/roofit_combined/significance.json` (required for H->gammagamma workflows)
- `outputs/fit/*/roofit_combined/signal_dscb_parameters.json` (required for H->gammagamma workflows)
- `outputs/fit/*/roofit_combined/sideband_fit_parameters.json` (required for H->gammagamma workflows)
- `outputs/fit/*/roofit_combined/cutflow_mass_window_125pm2.json` (required for H->gammagamma workflows)
- `outputs/report/plots/roofit_combined_mgg_*.png` (required for H->gammagamma workflows)
- `outputs/report/blinding_summary.json`
- `outputs/report/plots/blinded_region_*.png`
- `outputs/report/report.md`
- `outputs/report/*.png`
- `outputs/report/data_mc_discrepancy_audit.json`
- `outputs/report/data_mc_check_log.json`
- `outputs/report/skill_extraction_summary.json`

### Canonical Pipeline Stages (Current Repository)
1. Run agent pre-flight fact check and resolve critical ambiguities.
2. Parse and validate summary JSON.
3. Build sample registry.
4. Build metadata-driven MC normalization factors for stacked components (when metadata workflow is used).
5. Build category/region partition specification, checks, and manifest.
6. Build signal/background strategy and CR/SR normalization map.
7. Ingest events.
8. Build objects.
9. Apply selections and region masks.
10. Produce cut flow and yields.
11. Produce histograms for fit observables.
12. Build signal/background mass-shape models and run spurious-signal model selection.
13. Build statistical model and run fits.
14. Compute discovery significance from profile likelihood ratio.
15. Produce blinded CR/SR visualization products.
16. Make plots and report.
17. Run smoke tests.
18. Run final report review and handoff assessment.
19. Mandatory: run extract-new-skill-from-failure assessment and write any proposals to `candidate_skills/`, plus `outputs/report/skill_extraction_summary.json` even when zero candidates are created.

### Skill List (Current Repository)
Core pipeline skills:
- `$bootstrap-repo`
- `$agent-pre-flight-fact-check`
- `$read-summary-and-validate`
- `$sample-registry-and-normalization`
- `$mc-normalization-metadata-stacking`
- `$signal-background-strategy-and-cr-constraints`
- `$event-io-and-columnar-model`
- `$object-definitions`
- `$selection-engine-and-regions`
- `$cut-flow-and-yields`
- `$histogramming-and-templates`
- `$freeze-analysis-histogram-products`
- `$signal-shape-and-spurious-signal-model-selection`
- `$systematics-and-nuisances`
- `$workspace-and-fit-pyhf`
- `$plotting-and-report`
- `$final-analysis-report-agent-workflow`
- `$control-region-signal-region-blinding-and-visualization`
- `$smoke-tests-and-reproducibility`
- `$profile-likelihood-significance`
- `$category-channel-region-partitioning`
- `$final-report-review-and-handoff`
- `$extract-new-skill-from-failure`

Verification skills:
- `$visual-verification`
- `$histogram-plotting-invariants`
- `$data-mc-discrepancy-sanity-check`
- `$rootmltool-cached-analysis`
- `$stattool-optional-pyhf-backend`
