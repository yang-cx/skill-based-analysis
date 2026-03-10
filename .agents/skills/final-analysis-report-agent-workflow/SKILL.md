---
name: final-analysis-report-agent-workflow
description: "Repository-specific workflow and policy for Final Analysis Report (ATLAS Open Data Agent Workflow). Use when Codex needs the required artifacts, validation checks, execution steps, or constraints for this analysis stage in the repo."
---

# Final Analysis Report (ATLAS Open Data Agent Workflow)

## Layer 1 — Physics Policy
The final analysis report must communicate the physics analysis in a concise note-style format while preserving transparency of agent decisions.

Policy requirements:
- follow the user-defined analysis goal; do not invent new physics objectives
- document the studied process, discriminating observable, and tested hypothesis
- describe data and simulated samples, including integrated luminosity and run period
- for this repository's Run-2 H->gammagamma workflow, the reported central normalization luminosity must be `36.1 fb^-1` unless an explicit override is declared and justified
- report Monte Carlo normalization based on cross section, k-factor, filter efficiency, and signed generator-weight sum
- define reconstructed objects and event selections using available dataset observables
- document signal and control region purposes and selection logic
- treat blinded analysis as default; only show SR data after explicit unblinding instruction
- for non-signal regions, document both pre-fit and post-fit comparisons between data and MC signal/background
- preserve blinding by hiding signal-region data before unblinding
- describe the statistical interpretation framework and expected (pre-unblinding) results using Asimov-based fits when applicable
- for H->gammagamma workflows, explicitly state `pyroot_roofit` as the primary fit backend when presenting fit/significance results; any `pyhf` result must be labeled as a cross-check
- when expected sensitivity is derived from Asimov pseudo-data, state how Asimov data were generated (source PDF + parameter values from data fit) and whether generation/evaluation used sidebands-only or full mass range
- Asimov pseudo-data figures/tables may include the full mass range (including signal window) in blinded workflows, but must be clearly labeled as expected/Asimov
- for blinded sensitivity claims, expected significance must come from Asimov fits over the full observable range (including signal region), not from observed signal-window data
- when discovery sensitivity is reported from Asimov pseudo-data, document that generation used the background-only hypothesis (`mu = 0`) and that the likelihood test evaluates incompatibility with the signal-plus-background model
- avoid inventing systematic uncertainties when not provided; use explicit placeholder language instead
- include a mandatory appendix that documents all agent deviations, substitutions, and assumptions with justification
- for category-resolved resonance analyses, include a category-by-category mass-window table at `m_gg = 125 +/- 2 GeV` with expected signal and expected background yields
- in cut-flow reporting, include both process-level breakdowns and combined totals for signal and background when multiple processes contribute
- when alternative MC samples exist for the same process, central cut-flow/report yields must use nominal/reference samples only, with alternatives discussed under systematics
- for category-resolved resonance analyses, include one diphoton invariant-mass plot per category with:
  - observed data points (sidebands only in blinded mode)
  - expected post-fit background
  - expected signal stacked on top of background
- when reporting category-combined significance, explicitly state that the combined likelihood uses category-specific background parameters and a shared signal-strength parameter across categories
- every plot embedded in the final report must include a caption that explains plot entries and gives motivation/justification for why the plot is part of the evidence chain
- run-level skill extraction must be executed after report generation, and the report/handoff record must reference `outputs/report/skill_extraction_summary.json`

Normalization relation to state in report:
- `norm_factor = (sigma_pb * k_factor * filter_eff * lumi_pb) / sumw`
- `w_final = w_event * norm_factor`

## Layer 2 — Workflow Contract
### Required Artifacts
- final report artifact in Markdown with the following sections in order:
  1. Introduction
  2. Data and Monte Carlo Samples
  3. Object Definition and Event Selection
  4. Overview of the Analysis Strategy
  5. Signal and Control Regions
  6. Cut Flow
  7. Distributions in Signal and Control Regions
  8. Systematic Uncertainties
  9. Statistical Interpretation
  10. Summary
  Appendix A: Agent Decisions and Deviations
- Monte Carlo sample-table artifact within the report containing DSID, sample label, process, cross section, k-factor, and filter efficiency
- cut-flow table artifact with data counts and weighted simulated yields
- process-resolved cut-flow breakdown artifact (individual processes + combined signal/background totals)
- embedded region-plot artifacts including blinded signal-region visualizations
- embedded pre-fit and post-fit non-signal-region plots
- caption text for each embedded plot (entries + motivation/justification)
- statistical-summary artifact reporting expected sensitivity outputs produced before unblinding
- Asimov-provenance note in the statistical section when Asimov expected significance is reported
- explicit Asimov-hypothesis note (`mu_gen` and model used) when Asimov expected significance is reported
- category mass-window yield-table artifact (expected signal/background per category at `125 +/- 2 GeV`)
- per-category diphoton mass-plot artifact set with stacked signal-over-background expectation
- agent-decision audit artifact in Appendix A with issue, decision, and justification for each deviation
- data-MC discrepancy artifacts:
  - `outputs/report/data_mc_discrepancy_audit.json`
  - `outputs/report/data_mc_check_log.json`
- post-run skill-extraction summary artifact at `outputs/report/skill_extraction_summary.json` (required even when no candidates are proposed)

### Acceptance Checks
- section headers exist and appear in required order
- report explicitly states metadata-driven MC normalization inputs and formula
- report states the luminosity value used in normalization and, for default central results, shows `36.1 fb^-1`
- sample table includes required Monte Carlo normalization columns
- cut-flow presentation distinguishes per-process contributions from combined signal/background totals when multi-process signal/background is used
- report avoids central-yield double counting of nominal and alternative samples for the same physics process
- signal-region plots are marked/blinded with no overlaid data points
- non-signal-region pre-fit and post-fit comparisons are clearly identified and use visible data overlays
- report embeds produced plots directly via markdown image tags instead of citation-only file lists
- each embedded plot has an adjacent caption sentence/paragraph explaining entries and motivation
- report explicitly states that blinding is default and records whether explicit unblinding was requested
- when blinded category mass plots are used, data points are shown in sidebands and hidden in the blinded window unless explicit unblinding is requested
- report includes a category-wise `125 +/- 2 GeV` expected-yield table for signal and background
- report includes one diphoton-mass distribution per active category used in the combined fit
- systematics section contains explicit placeholder statement when systematics are unspecified
- statistical interpretation section documents Asimov/pre-unblinding treatment when blinding is active
- when Asimov significance is reported, the report explicitly distinguishes expected (Asimov) from observed significance and records generation provenance
- when Asimov discovery sensitivity is reported, the report explicitly documents `mu_gen = 0` background-only generation and full-range evaluation including the signal region
- statistical interpretation section states the backend used for the reported fit/significance numbers and confirms `pyroot_roofit` is primary for H->gammagamma
- Appendix A exists and contains at least one structured entry whenever substitutions/deviations occurred
- report (or linked handoff note) references data-MC discrepancy status from `outputs/report/data_mc_discrepancy_audit.json`
- report (or linked handoff note) references `outputs/report/skill_extraction_summary.json` with its status (`none_found` or `candidates_created`)

## Layer 3 — Example Implementation
### Output Location (Current Repository Workflow)
- `reports/final_analysis_report.md`

### Inputs to Reference (Current Repository Workflow)
- analysis summary specification
- region definitions
- metadata table for open-data sample normalization
- cut-flow, yield, fit, significance, and blinding artifacts produced by pipeline stages

### Related Skills
- `$sample-registry-and-normalization`
- `$mc-normalization-metadata-stacking`
- `$plotting-and-report`
- `$control-region-signal-region-blinding-and-visualization`
- `$profile-likelihood-significance`
- `$final-report-review-and-handoff`
- `$extract-new-skill-from-failure`

### Example Generation Path (Current Repository Workflow)
- generate a baseline report from pipeline report stage
- enrich/reshape to match this final section structure
- write final artifact to `reports/final_analysis_report.md`
