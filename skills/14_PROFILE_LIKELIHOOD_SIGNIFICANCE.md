# Skill: Profile Likelihood Discovery Significance

## Layer 1 — Physics Policy
Discovery significance is computed with a profile-likelihood-ratio test comparing background-only and unconstrained fits.

Policy requirements:
- perform a conditional fit with signal strength fixed to the background-only hypothesis (`mu = 0`)
- perform an unconditional fit where signal strength is free
- construct the one-sided discovery test statistic
- for H->gammagamma workflows, compute primary significance with `pyroot_roofit`; if an optional cross-check backend is used, apply the same `q0` definition
- for category-combined fits, construct a single combined likelihood over all configured categories with one shared POI (`mu`) and category-specific background parameters
- when blinding is active for resonance windows, significance metadata must declare whether fits used full range or sideband-only ranges
- when evaluating expected sensitivity during blinded analysis development, significance must be computed using Asimov pseudo-data rather than observed signal-region data
- Asimov pseudo-data for sensitivity evaluation must be generated over the full observable range, including the signal region
- Asimov generation must use PDFs loaded with parameter values obtained from fits to real data (often sideband-constrained under blinding)
- for discovery-significance sensitivity evaluation, generate the Asimov dataset under the background-only hypothesis (`mu = 0`)
- then evaluate incompatibility of the background-only hypothesis with the signal-plus-background model via the profile-likelihood discovery test statistic
- Asimov datasets are pseudo-data (not observed data), so they can be evaluated/visualized in the full mass range including the signal window
- significance results must clearly label whether they are observed-data or Asimov-based expected results

Test statistic definition:
`q0 = -2 ln lambda(0) = 2 * (NLL_mu0 - NLL_muhat)`

One-sided discovery convention:
- `q0 = max(q0, 0)`

Asymptotic significance:
- `Z = sqrt(q0)`

## Layer 2 — Workflow Contract
### Required Artifacts
- per-fit significance artifact containing fit identifiers, POI metadata, NLL values, test statistic, significance, status diagnostics, and fit-range/blinding metadata for category-resolved fits
- optional Asimov significance artifact per fit containing:
  - Asimov dataset type (`background_only`, `signal_plus_background`)
  - source PDF/model provenance
  - parameter-source provenance (for example data-fit snapshot used to generate Asimov)
  - fit range used for Asimov generation/evaluation
  - generation hypothesis details (for example `mu_gen = 0` for background-only discovery sensitivity)

### Acceptance Checks
- significance artifact exists for each fit under test
- successful result satisfies `q0 >= 0`
- successful result satisfies `z_discovery = sqrt(q0)` within numerical tolerance
- failed result includes actionable diagnostic information
- for the required PyROOT backend in H->gammagamma workflows, exported NLL values and POI conventions are mapped consistently into the standard significance schema
- significance artifacts for category-combined fits list categories included and whether `mu` is shared across them
- Asimov significance artifacts explicitly declare that inputs are pseudo-data and include generation provenance
- observed and Asimov significance outputs are not conflated in reporting
- when an Asimov sensitivity result is reported in blinded workflows, Asimov generation/evaluation range includes the signal region (full observable range)
- discovery-sensitivity Asimov artifacts explicitly document background-only generation hypothesis (`mu_gen = 0`)

## Layer 3 — Example Implementation
### Required Fields (Current Repository)
- `fit_id`
- `status`
- `poi_name`
- `mu_hat`
- `twice_nll_mu0`
- `twice_nll_free`
- `q0`
- `z_discovery`
- `error` (if failed)
- `dataset_type` (recommended: `observed` or `asimov`)
- `asimov_source` (required when `dataset_type=asimov`)
- `fit_range` (recommended for blinded workflows)
- `mu_gen` (required when `dataset_type=asimov`)

### CLI (Current Repository)
`python -m analysis.stats.significance --workspace outputs/fit/workspace.json --fit-id FIT1 --out outputs/fit/FIT1/significance.json`

Asimov expected-significance artifact (example):
`python -m analysis.stats.significance --workspace outputs/fit/workspace.json --fit-id FIT1 --out outputs/fit/FIT1/significance_asimov.json`
