# Skill: Cut Flow and Yields

## Layer 1 — Physics Policy
A cut flow must describe event reduction step-by-step and preserve both unweighted and weighted interpretations.

Policy requirements:
- cut flow is ordered and physically meaningful
- each step reports unweighted counts and weighted yields
- report per-step and cumulative efficiencies
- final selected yield must match the sample contribution used in downstream histogramming
- for signal and background, provide both:
  - per-process contributions (process-level breakdown)
  - combined totals (all signal processes combined, all background processes combined)
- avoid double counting when multiple samples represent one physics process; only nominal/reference samples contribute to central cut-flow totals

## Layer 2 — Workflow Contract
### Required Artifacts
- cut-flow table artifact per sample with ordered step metrics
- region-yield artifact per sample with unweighted counts, weighted yields, and uncertainty proxy terms (for example sum of squared weights)
- cut-flow provenance artifact linking steps to region definitions
- process-aggregated cut-flow artifact (per process + combined signal/background totals)
- nominal-sample selection audit for cut-flow central values

### Acceptance Checks
- cut-flow steps are ordered and complete
- unweighted event counts do not increase across stricter sequential cuts
- final cut-flow selection agrees with region-yield selection used downstream
- weighted yields and uncertainty proxies are finite and reported
- process-level sums are consistent with combined signal/background totals within tolerance
- alternative/systematic-only samples do not contribute to central cut-flow totals unless explicitly configured

## Layer 3 — Example Implementation
### Output Schema (Current Repository)
Cut flow entries:
- `name`, `n_raw`, `n_weighted`, `eff_step`, `eff_cum`

Yield entries:
- `n_raw`, `yield`, `sumw2`

Recommended process-level aggregate entries:
- `process_name`, `role` (`signal` or `background`), `is_nominal`, `yield`
- combined rows: `signal_total`, `background_total`

### CLI (Current Repository)
`python -m analysis.selections.engine --sample <ID> --registry outputs/samples.registry.json --regions analysis/regions.yaml --cutflow --out outputs/cutflows/<ID>.json`
