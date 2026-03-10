# Skills Repository (Semantic Structure)

This README replaces `00_INDEX.md` and serves as the top-level navigator for the refactored skills tree.

## Directory Layout
- `core_pipeline/`: end-to-end procedural analysis workflow stages
- `analysis_strategy/`: analysis-design and strategy decisions
- `physics_facts/`: domain facts and invariant technical rules
- `governance/`: policy and integrity guardrails
- `infrastructure/`: operational support, caching, and reproducibility
- `meta/`: skill-lifecycle governance
- `interfaces/`: translation/execution interfaces (JSON and narrative)
- `open_data_specific/`: dataset-release-specific references

## Legacy Index Content (Refactored Paths)

# Skill: Skills Pack Index

## Layer 1 — Physics Policy
The analysis skill pack must encode a complete, scientifically coherent HEP workflow from analysis definition to statistical interpretation.

Core policy requirements:
- Keep analysis decisions config-driven and reproducible.
- Start execution from a referenced analysis JSON file; trigger prompts should be minimal and JSON-first.
- Preserve a clear chain from event selection through statistical inference.
- Treat signal and background modeling choices as explicit methodological choices.
- For the default Run-2 H->gammagamma workflow in this repository, central MC normalization must use `lumi_fb = 36.1`.
- For H->gammagamma resonance analyses in this repository, use `pyroot_roofit` as the mandatory primary backend for mass fits and significance; non-ROOT backends may be used only as explicitly labeled cross-checks.
- Never replace existing workflow implementations when adding tools from other projects; keep new tools as additive, selectable options.
- Enforce blinding where required by the analysis strategy.
- Require visual and statistical validation before declaring completion.
- Require execution of post-run skill extraction (`meta/extract_new_skill_from_failure.md`) for every completed run; missing extraction blocks handoff-ready status.
- Use the term **cut flow** consistently.
- Default production runs must use full statistics unless partial scope is explicitly requested or a same-task fast-test then full-run pattern is declared.

## Layer 2 — Workflow Contract
### Required Artifacts
- normalized analysis-definition artifact with validated region and fit semantics
- spec-to-runtime mapping artifact (required when runtime pipeline is not fully JSON-native)
- deviations-from-spec artifact with explicit substitutions/assumptions
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
- each run references an explicit analysis JSON path
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
- Analysis summary JSON: `analysis/<analysis>.analysis.json`
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
1. Optional: convert narrative analysis text into structured analysis JSON and produce a gap report.
2. Run agent pre-flight fact check and resolve critical ambiguities.
3. Parse and validate summary JSON.
4. Apply JSON-spec-driven execution contract (including runtime mapping/deviation logging).
5. Build sample registry.
6. Build metadata-driven MC normalization factors for stacked components (when metadata workflow is used).
7. Build category/region partition specification, checks, and manifest.
8. Build signal/background strategy and CR/SR normalization map.
9. Ingest events.
10. Build objects.
11. Apply selections and region masks.
12. Produce cut flow and yields.
13. Produce histograms for fit observables.
14. Build signal/background mass-shape models and run spurious-signal model selection.
15. Build statistical model and run fits.
16. Compute discovery significance from profile likelihood ratio.
17. Produce blinded CR/SR visualization products.
18. Make plots and report.
19. Run smoke tests.
20. Run final report review and handoff assessment.
21. Mandatory: run extract-new-skill-from-failure assessment and write any proposals to `candidate_skills/`, plus `outputs/report/skill_extraction_summary.json` even when zero candidates are created.

### Skill List (Current Repository)
Core pipeline skills:
- `core_pipeline/bootstrap_repo.md`
- `interfaces/narrative_to_analysis_json_translator.md`
- `governance/agent_pre_flight_fact_check.md`
- `interfaces/json_spec_driven_execution.md`
- `governance/full_statistics_execution_policy.md`
- `core_pipeline/read_summary_and_validate.md`
- `core_pipeline/sample_registry_and_normalization.md`
- `physics_facts/mc_normalization_metadata_stacking.md`
- `analysis_strategy/signal_background_strategy_and_cr_constraints.md`
- `core_pipeline/event_io_and_columnar_model.md`
- `physics_facts/object_definitions.md`
- `core_pipeline/selection_engine_and_regions.md`
- `core_pipeline/cut_flow_and_yields.md`
- `core_pipeline/histogramming_and_templates.md`
- `infrastructure/freeze_analysis_histogram_products.md`
- `analysis_strategy/signal_shape_and_spurious_signal_model_selection.md`
- `core_pipeline/systematics_and_nuisances.md`
- `core_pipeline/workspace_and_fit_pyhf.md`
- `core_pipeline/plotting_and_report.md`
- `core_pipeline/final_analysis_report_agent_workflow.md`
- `analysis_strategy/control_region_signal_region_blinding_and_visualization.md`
- `infrastructure/smoke_tests_and_reproducibility.md`
- `core_pipeline/profile_likelihood_significance.md`
- `analysis_strategy/category_channel_region_partitioning.md`
- `core_pipeline/final_report_review_and_handoff.md`
- `meta/extract_new_skill_from_failure.md`

Verification skills:
- `infrastructure/visual_verification.md`
- `physics_facts/histogram_plotting_invariants.md`
- `governance/data_mc_discrepancy_sanity_check.md`
- `infrastructure/rootmltool_cached_analysis.md`
- `infrastructure/stattool_optional_pyhf_backend.md`
