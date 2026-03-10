# Skill: MC Normalization from Open-Data Metadata for Multi-Component Stacks

## Layer 1 — Physics Policy
For ATLAS Open Data education/outreach ntuples, Monte Carlo normalization for stacked comparisons must be anchored to official metadata totals rather than skim-level event counts.

Policy requirements:
- normalize each simulated sample using cross section, k-factor, generator filter efficiency, and signed generator-weight sum from official metadata
- apply one per-sample normalization factor to all events/files belonging to that sample identifier
- construct per-event final weight as event-level weight product multiplied by the per-sample normalization factor
- for the default Run-2 H->gammagamma workflow in this repository, set `lumi_fb = 36.1` for central MC normalization
- preserve signed-weight behavior; do not replace signed generator-weight sums with raw event counts
- enforce unit consistency by converting luminosity from fb^-1 to pb^-1 before applying normalization
- keep each stacked color component traceable to its physics process/sample identifier
- treat generator filter efficiency as production-level correction; do not reapply it as an analysis-selection correction
- if multiple samples correspond to the same physics process (for example nominal vs alternative generator), define and enforce a nominal/reference sample for central stacked yields to prevent double counting

Normalization definition:
- `L_pb = lumi_fb * 1000.0`
- `norm_factor = (sigma_pb * k_factor * filter_eff * L_pb) / sumw`
- `w_final = w_event * norm_factor`

## Layer 2 — Workflow Contract
### Required Artifacts
- metadata-resolution artifact mapping sample identifiers to normalization fields and documenting any column-name interpretation rules
- per-sample normalization-table artifact containing sample identifier, label, cross section, k-factor, filter efficiency, signed sum of generator weights, and resulting normalization factor
- event-weight-definition artifact documenting the event-level weight factors used in `w_event`
- normalization-audit artifact containing luminosity, normalized sample list, missing/invalid metadata rows, skipped samples, and sanity-check outcomes
- stacked-yield summary artifact reporting weighted contributions per stacked component
- nominal-reference selection artifact per physics process indicating which sample(s) enter central stacks vs systematic-variation-only stacks

### Acceptance Checks
- each normalized sample has finite normalization inputs with `sigma_pb > 0`, `k_factor > 0`, `filter_eff > 0`, and `sumw != 0`
- no sample uses raw generated event count as a substitute for signed generator-weight sum
- identical sample identifiers across multiple files share one normalization factor
- normalization scales linearly with luminosity; doubling luminosity doubles predicted weighted MC yields
- default normalization audit records `lumi_fb = 36.1` for central results unless an explicit override is declared
- ambiguous sample-label matching is rejected or resolved with explicit identifier mapping
- signed-weight samples are handled without removing negative-weight contributions
- central stacked yields do not include both nominal and alternative samples for the same process simultaneously unless an explicit weighted-combination policy is declared

## Layer 3 — Example Implementation
### Inputs (Current Repository Workflow)
- `skills/metadata.csv`
- MC sample identifiers (`dataset_number`/DSID preferred; `physics_short` only when unique)
- target luminosity `lumi_fb`
- event-level ntuple weights (`weight_mc` or `mcEventWeight`, plus optional correction factors)

### Expected Metadata Fields (or mapped equivalents)
- DSID/sample identifier: `dataset_number`
- sample label: `physics_short`
- cross section (pb): `crossSection_pb`
- filter efficiency: `genFiltEff`
- k-factor: `kFactor`
- signed sum of weights: `sumOfWeights`
- optional: `sumOfWeightsSquared`, `nEvents` (sanity checks only)

### Column-Mapping Heuristics
- DSID-like column contains integer sample identifiers (often six-digit)
- cross-section-like column contains positive floats and name hints such as `cross` or `pb`
- filter efficiency values are commonly in `(0, 1]`
- k-factor values are positive and often close to unity
- signed sum-of-weights values are nonzero and can differ from event counts

### Procedure (Current Repository Workflow)
1. Read `skills/metadata.csv` and build a DSID-keyed lookup.
2. Validate normalization fields per requested sample.
3. Compute per-sample normalization factors using luminosity conversion.
4. Build final event weights: generator/event weight times optional corrections times normalization factor.
5. Fill per-sample histograms and stack components by physics category.
6. Resolve nominal vs alternative samples per process for central-yield stacking.
7. Run audit checks including luminosity scaling, control-region reasonableness checks, and double-count protection for duplicated process representations.

### Deliverables (Current Repository Workflow)
- `norm_table.json` with per-sample normalization terms and computed factors
- nominal-vs-alternative mapping snippet in the audit output
- report audit snippet summarizing:
  - luminosity used
  - normalized sample identifiers
  - missing metadata rows
  - column-mapping assumptions
  - skipped/invalid samples
