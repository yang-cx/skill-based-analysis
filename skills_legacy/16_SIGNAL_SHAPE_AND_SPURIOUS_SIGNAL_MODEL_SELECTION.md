# Skill: Signal Shape and Spurious-Signal Background Model Selection

## Layer 1 — Physics Policy
For analytic mass-fit analyses, derive signal and background parameterizations with explicit spurious-signal control.

Policy requirements:
- obtain the signal mass distribution from selected signal simulation with proper weights
- fit an analytic signal PDF (commonly double-sided Crystal Ball) to extract shape parameters
- scan candidate background functional forms with increasing complexity
- evaluate spurious signal by fitting signal-plus-background to a background-only template
- for resonance searches in this repository (notably `H->gammagamma`), PyROOT/RooFit is the mandatory primary backend for analytic-function fitting
- backend choice must remain transparent: export machine-readable JSON summaries even when PyROOT is used
- for category-resolved diphoton fits, fit a double-sided Crystal Ball signal shape independently in each category
- category-resolved workflows must support arbitrary category counts from fit configuration (not fixed to a specific number)

Spurious-signal metric:
- `N_spur`: fitted signal yield on background-only template
- `sigma_Nsig`: uncertainty on fitted signal yield
- `r_spur = |N_spur| / sigma_Nsig`

Selection policy:
- target `r_spur < 0.2`
- choose lowest-complexity candidate that passes
- if multiple candidates pass at same complexity, prefer smaller `|N_spur|`
- if none pass, escalate complexity; if none still pass, choose smallest `r_spur` and flag noncompliance

## Layer 2 — Workflow Contract
### Required Artifacts
- signal-PDF artifact with fit parameters, covariance information (when available), and fit status
- background-scan artifact listing all tested functional forms and complexity levels
- background-choice artifact recording selected model and explicit selection rationale
- spurious-signal artifact with `N_spur`, `sigma_Nsig`, `r_spur`, and pass/fail flag
- backend-provenance artifact recording `pyroot_roofit` as primary backend and any optional cross-check backend
- category-wise signal-shape artifact containing DS-CB parameters and fit status per category for RooFit combined workflows

### Acceptance Checks
- signal-PDF fit converges or returns actionable diagnostics
- background scan includes all tested candidate forms
- chosen background model includes explicit rule-based justification
- spurious-signal result includes pass/fail status against the target criterion
- fitted parameter values and fit status from PyROOT are exported in non-ROOT machine-readable form

## Layer 3 — Example Implementation
### Expected Outputs (Current Repository)
- `outputs/fit/<fit_id>/signal_pdf.json`
- `outputs/fit/<fit_id>/background_pdf_scan.json`
- `outputs/fit/<fit_id>/background_pdf_choice.json`
- `outputs/fit/<fit_id>/spurious_signal.json`
- `outputs/fit/<fit_id>/roofit_combined/signal_dscb_parameters.json` (required for H->gammagamma category-resolved workflows)

### CLI (Current Repository)
`python -m analysis.stats.mass_model_selection --fit-id FIT1 --summary outputs/summary.normalized.json --hists outputs/hists --strategy outputs/background_modeling_strategy.json --out outputs/fit/FIT1/background_pdf_choice.json`

### Downstream Reference
Use outputs in:
- `09_SYSTEMATICS_AND_NUISANCES.md`
- `10_WORKSPACE_AND_FIT_PYHF.md`
- `11_PLOTTING_AND_REPORT.md`
