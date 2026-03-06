# Skill: Plotting and Report

## Layer 1 — Physics Policy
Result communication must make agreement and discrepancies between data and expectations auditable.

Policy requirements:
- provide region-level observable visualizations with consistent binning and axis semantics
- when blinded mode is active, show observed data in non-signal regions and hide observed data in signal regions
- provide both pre-fit and post-fit region visualizations for non-signal regions
- pre-fit must represent nominal Monte Carlo normalization before fitting
- post-fit must use fitted normalization/nuisance values derived from control-region constraints
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
- pre-fit region-plot artifact set for non-signal regions
- post-fit region-plot artifact set for non-signal regions
- cut-flow visualization artifact
- narrative report artifact integrating methodology, yields, fit outcomes, significance, and key diagnostics
- report markdown with embedded plot images (not path-only citation lists)
- artifact-link inventory enabling traceability from report statements to produced artifacts
- category-resolved mass-plot artifact set with stacked signal overlays and explicit blinding behavior
- plot-caption artifact content in the report markdown (caption text adjacent to each embedded image)

### Acceptance Checks
- at least one observable plot exists for each fit region
- pre-fit and post-fit non-signal-region plots both exist and are embedded in reporting artifacts
- non-signal-region pre-fit/post-fit plots display data points and stacked signal/background expectations
- report includes event-selection summary, cut flow summary, and fit result summary
- report includes significance summary when significance artifacts exist
- report includes blinding summary when blinding artifacts exist
- report uses inline markdown image tags (for example `![](plots/<name>.png)`) for produced plots
- when category-resolved resonance plots are produced, there is one plot per active category and blinded windows hide data points unless unblinded
- every embedded image in report markdown is immediately accompanied by a caption that explains entries and motivation

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
