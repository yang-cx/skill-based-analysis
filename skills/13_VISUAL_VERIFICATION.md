# Skill: Visualization-Based Verification

## Layer 1 — Physics Policy
Visual validation is mandatory for establishing that reconstructed objects, selections, categorization, and final signal extraction are physically reasonable.

Policy requirements:
- validate object-level behavior before interpreting final fits
- validate event-level observables used in selection and fitting
- validate selection behavior via cut flow and multiplicity diagnostics
- validate category behavior when categories are used
- validate final fit quality and residual structure
- validate control/non-signal region agreement in both pre-fit and post-fit views
- in blinded mode, verify that non-signal plots show data while signal-region plots hide data
- apply clear plotting conventions: physical axis labels, uncertainty display where available, consistent binning, appropriate scaling, no misleading smoothing
- when verification plots are embedded in reports, each plot should include a caption explaining plotted entries and why this diagnostic is required

## Layer 2 — Workflow Contract
### Required Artifacts
- object-level diagnostic plot artifacts for leading/subleading photon kinematics and acceptance-sensitive observables
- event-level diagnostic plot artifacts for diphoton mass preselection, diphoton transverse momentum, and angular separation
- selection-validation artifacts including cut-flow visualization and photon multiplicity
- category-validation plot artifacts for each active category
- final-result plot artifacts including fitted mass spectrum and pull/residual distribution
- pre-fit and post-fit non-signal-region comparison plot artifacts
- verification-status artifact that records presence/absence of required diagnostics

### Acceptance Checks
- all required object-level diagnostics exist
- all required event-level diagnostics exist
- cut-flow visualization and multiplicity diagnostics exist
- category diagnostics exist for every active category
- final fit and pull diagnostics exist
- pre-fit and post-fit non-signal-region diagnostics exist
- blinding behavior matches policy: data shown in non-signal regions, hidden in signal regions unless explicitly unblinded
- verification stage fails if any required diagnostic artifact is missing
- reporting-stage integration should fail if required verification plots are embedded without explanatory captions

## Layer 3 — Example Implementation
### Required Plot Names (Current Repository)
- `photon_pt_leading.png`
- `photon_pt_subleading.png`
- `photon_eta_leading.png`
- `photon_eta_subleading.png`
- `diphoton_mass_preselection.png`
- `diphoton_pt.png`
- `diphoton_deltaR.png`
- `photon_multiplicity.png`
- `cutflow_plot.png`
- `cutflow_table.json`
- `diphoton_mass_category_*.png`
- `diphoton_mass_fit.png`
- `diphoton_mass_pull.png`

### Output Location (Current Repository)
- `outputs/report/plots/`

### Blinding Coordination
If blinded operation is active, also apply:
- `17_CONTROL_REGION_SIGNAL_REGION_BLINDING_AND_VISUALIZATION.md`
