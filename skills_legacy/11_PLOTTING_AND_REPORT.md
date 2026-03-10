# Skill: Plotting and Report

## Layer 1 — Physics Policy
Result communication must make agreement and discrepancies between data and expectations auditable.

Policy requirements:
- provide region-level observable visualizations with consistent binning and axis semantics
- when blinded mode is active, show observed data in non-signal regions and hide observed data in sensitive signal-region content
- provide both pre-fit and post-fit region visualizations for control regions
- provide both pre-fit and post-fit region visualizations for signal regions in unblinded mode
- in blinded mode, signal-region visualizations must either:
  - omit observed-data signal-region plots, or
  - mask the sensitive signal window (for example a resonance window such as `125 +/- 5 GeV`) while keeping allowed sidebands visible when appropriate
- pre-fit must represent nominal Monte Carlo normalization before fitting
- post-fit must use fitted normalization/nuisance values derived from fit constraints
- include cut flow summaries and fit summaries in the final narrative
- include signal/background modeling rationale and uncertainty context
- include blinding policy behavior when the analysis is blinded
- for category-resolved resonance fits, provide one mass distribution per active category with data points (sidebands-only when blinded), post-fit background, and stacked signal-on-background expectation
- every embedded plot in narrative outputs must include a caption that:
  - explains plotted entries (for example data points, background expectation, signal expectation, fit components)
  - states why the plot is produced (motivation/justification in analysis workflow)

## Layer 2 — Workflow Contract
### Required Artifacts
- region-plot artifact set for fit observables
- pre-fit region-plot artifact set for control regions
- post-fit region-plot artifact set for control regions
- pre-fit and post-fit signal-region plot artifact sets for unblinded mode
- blinded signal-region handling artifact documenting whether SR plots are omitted or sensitive windows are masked
- cut-flow visualization artifact
- narrative report artifact integrating methodology, yields, fit outcomes, significance, and key diagnostics
- report markdown with embedded plot images (not path-only citation lists)
- artifact-link inventory enabling traceability from report statements to produced artifacts
- category-resolved mass-plot artifact set with stacked signal overlays and explicit blinding behavior
- plot-caption artifact content in the report markdown (caption text adjacent to each embedded image)
- discrepancy artifacts for data-MC checks:
  - `outputs/report/data_mc_discrepancy_audit.json`
  - `outputs/report/data_mc_check_log.json`

### Acceptance Checks
- at least one observable plot exists for each fit region
- pre-fit and post-fit control-region plots both exist and are embedded in reporting artifacts
- in unblinded mode, pre-fit and post-fit signal-region plots exist and include observed data across full SR
- in blinded mode, signal-region observed data are either omitted or explicitly masked in sensitive windows with documented boundaries
- control-region pre-fit/post-fit plots display data points and stacked signal/background expectations
- report includes event-selection summary, cut flow summary, and fit result summary
- report includes significance summary when significance artifacts exist
- report includes blinding summary when blinding artifacts exist
- report uses inline markdown image tags (for example `![](plots/<name>.png)`) for produced plots
- when category-resolved resonance plots are produced, there is one plot per active category and blinded windows hide data points unless unblinded
- every embedded image in report markdown is immediately accompanied by a caption that explains entries and motivation
- substantial data-MC discrepancies are explicitly called out and not hidden by cosmetic-only changes
- discrepancy artifacts exist even when no substantial discrepancy is found

## Layer 3 — Example Implementation
### Report Inputs (Current Repository)
- `outputs/background_modeling_strategy.json`
- `outputs/fit/*/signal_pdf.json`
- `outputs/fit/*/background_pdf_choice.json`
- `outputs/fit/*/spurious_signal.json`
- `outputs/report/blinding_summary.json`
- `outputs/fit/*/blinded_cr_fit.json`
- `outputs/fit/*/results.json`
- `outputs/fit/*/significance.json`

### CLI (Current Repository)
`python -m analysis.report.make_report --summary outputs/summary.normalized.json --outputs outputs --out outputs/report/report.md`

### Downstream Reference
Use:
- `17_CONTROL_REGION_SIGNAL_REGION_BLINDING_AND_VISUALIZATION.md`
- `19_FINAL_ANALYSIS_REPORT_AGENT_WORKFLOW.md`
- `28_DATA_MC_DISCREPANCY_SANITY_CHECK.md`
