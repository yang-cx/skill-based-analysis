# Skill: Control/Signal Region Blinding and Visualization

## Layer 1 — Physics Policy
Blinding protects against analysis bias by preventing inspection of signal-region data during model development and validation.

Policy requirements:
- blinded operation is the default mode for all analyses unless an explicit user unblinding directive is provided
- control-region visualizations may show observed data and modeled expectations
- in blinded mode, all non-signal regions (CR/VR/SB) should show observed data overlaid with signal and background expectations
- signal-region visualizations must hide observed data during blinded operation
- signal expectation must be stacked on top of background expectation in region plots
- normalization used for expected region plots should be derived from control-region-only fitting when blinding is active
- produce both pre-fit and post-fit views for non-signal regions:
  - pre-fit: nominal Monte Carlo normalization before fitting
  - post-fit: expectations normalized with fitted CR-constrained parameters
- control and signal region selections must be mutually exclusive for blinded workflows unless an explicit overlap exception is documented
- unblinding is an explicit, deliberate action outside the default workflow
- for diphoton resonance category fits, background normalization/shape must be fitted to data using sidebands only (for example `105-120` and `130-160 GeV`) while the blinded peak window is excluded from data constraints
- blinded category mass plots may show full-range expected background and expected signal+background curves, but observed data points must be shown only in sidebands unless explicit unblinding is requested
- expected signal overlay should be stacked on top of the post-fit background expectation in blinded category plots
- Asimov pseudo-data products are exempt from observed-data blinding restrictions because they are generated from model PDFs, not real detector data
- when Asimov pseudo-data are shown, outputs must be explicitly labeled as Asimov/expected and must not be presented as observed data
- for blinded sensitivity evaluation, Asimov pseudo-data can be generated/evaluated over the full mass range (including the blinded signal window) while observed-data fits remain sideband-constrained

## Layer 2 — Workflow Contract
### Required Artifacts
- control-region-only normalization-fit artifact containing fitted normalization parameters and fit status
- blinding-summary artifact indicating region classification and whether data were shown or hidden
- region-visualization artifact set covering all declared control and signal regions
- pre-fit non-signal-region visualization artifact set with data, background, and signal overlays
- post-fit non-signal-region visualization artifact set with data, background, and signal overlays
- blinding overlap-audit artifact confirming SR events are excluded from CR normalization scope by default
- sideband-only background-fit artifact for blinded resonance categories (fit-range declaration + per-category parameters)
- blinded category mass-plot artifact set with:
  - observed data points in sidebands only
  - full-range post-fit background curve
  - stacked signal-on-background expectation

### Acceptance Checks
- normalization-fit artifact confirms control-region-only fit scope
- blinding-summary artifact marks signal regions as data hidden during blinded operation
- number of produced region plots equals number of declared regions
- for each declared non-signal region, both pre-fit and post-fit plots exist
- non-signal-region plots show observed data points in both pre-fit and post-fit views
- stacked composition places signal above background in expectation plots
- overlap audit confirms zero SR/CR overlap for blinded normalization unless an explicit exception is declared
- signal-region data are shown only when explicit unblinding is requested
- blinded resonance mass plots hide data points in the blinded peak window while preserving sideband data points
- sideband-fit artifacts explicitly record sideband ranges used for fit constraints
- stacked expected signal contribution appears above expected background in blinded resonance plots

## Layer 3 — Example Implementation
### CLI (Current Repository)
Blinded (default):
`python -m analysis.plotting.blinded_regions --outputs outputs --registry outputs/samples.registry.json --regions analysis/regions.yaml --fit-id FIT1`

Explicit unblind:
`python -m analysis.plotting.blinded_regions --outputs outputs --registry outputs/samples.registry.json --regions analysis/regions.yaml --fit-id FIT1 --unblind-sr`

### Expected Outputs (Current Repository)
- `outputs/fit/<fit_id>/blinded_cr_fit.json`
- `outputs/report/blinding_summary.json`
- `outputs/report/plots/blinded_region_<region_id>.png`
- `outputs/report/plots/prefit_region_<region_id>.png` (non-signal regions)
- `outputs/report/plots/postfit_region_<region_id>.png` (non-signal regions)
- `outputs/fit/<fit_id>/roofit_combined/sideband_fit_parameters.json` (required for H->gammagamma category-resolved workflows)
- `outputs/report/plots/roofit_combined_mgg_<category>.png` (required for H->gammagamma category-resolved workflows)

### Downstream Reference
Use with:
- `11_PLOTTING_AND_REPORT.md`
- `13_VISUAL_VERIFICATION.md`
