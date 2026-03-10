# Skill: Data-MC Discrepancy Sanity Check

## Layer 1 — Physics Policy
Data-MC disagreement is a diagnostic signal. It must be investigated and reported, not cosmetically reduced.

Policy requirements:
- explicitly call out substantial data-MC discrepancies in shape and/or normalization
- treat large discrepancies as mandatory triggers for implementation/procedure checks
- never change plotting, normalization, selection, weighting, binning, or sample composition solely to improve visual agreement
- do not treat disagreement alone as proof of implementation failure
- do not suppress, obscure, or de-emphasize discrepant regions/categories in plots or report text
- preserve the distinction between:
  - confirmed implementation bugs (fix + document)
  - unresolved modeling/physics mismatches (retain + report)
- always emit discrepancy-audit artifacts for every production run, including runs with no substantial discrepancy

## Layer 2 — Workflow Contract
### Required Inputs
- data-vs-MC comparison plots and tables (pre-fit/post-fit where applicable)
- region/category definitions
- cut flow and yield artifacts
- normalization artifacts (cross section, k-factor, filter efficiency, luminosity, sum of weights)
- event-weight-definition artifact
- sample registry/mapping artifacts

### Required Artifacts
- discrepancy-audit artifact listing each substantial discrepancy and its context:
  - region/category
  - observable
  - process grouping
  - discrepancy type (shape, normalization, or both)
  - approximate magnitude and affected bins/ranges
- check-log artifact documenting which sanity checks were executed and outcomes
- reporting note artifact that states whether a concrete bug was found/corrected or discrepancy remains unresolved
- explicit "no substantial discrepancy" status path so zero-issue runs are still machine-auditable

### Mandatory Checks When Substantial Discrepancy Is Found
- event-weight application
- luminosity scaling and units
- cross-section, k-factor, filter-efficiency, branching-ratio treatment
- per-sample normalization and duplicate/missing sample handling
- data-MC sample mapping and process grouping
- region/category definitions and overlap logic
- object selections, overlap removal, trigger requirements, trigger scale factors
- blinding logic
- histogram filling logic, variable definition, binning choice
- preselection/cut-flow consistency
- stitching/merging of subsamples
- systematic-variation and pre-fit/post-fit normalization usage
- CR transfer-factor or normalization-factor propagation

### Forbidden Actions
- tuning scale factors or normalization solely to improve agreement
- altering axis limits/binning solely to hide disagreement
- tightening/loosening selections solely to force better agreement
- dropping, merging, or relabeling samples to mask disagreement
- omitting problematic plots from report artifacts
- claiming disagreement is "fixed" without identifying and documenting a concrete implementation error

### Acceptance Checks
- `outputs/report/data_mc_discrepancy_audit.json` exists and is readable for every run
- `outputs/report/data_mc_check_log.json` exists and is readable for every run
- all substantial discrepancies in data-vs-MC plots are explicitly documented
- discrepancy-triggered sanity checks are recorded
- if a bug is found, the fix and impact are documented with updated artifacts
- if no bug is found, discrepancy remains visible in plots and report text
- no change log entry indicates cosmetic-only tuning to improve agreement

## Layer 3 — Example Implementation
### Required Output Artifacts (Current Repository)
- `outputs/report/data_mc_discrepancy_audit.json`
- `outputs/report/data_mc_check_log.json`
- discrepancy summary paragraph in:
  - `outputs/report/report.md`
  - `reports/final_analysis_report.md`

### Suggested `data_mc_discrepancy_audit.json` Fields
- `status` (`no_substantial_discrepancy`, `discrepancy_investigated_bug_found`, `discrepancy_investigated_no_bug_found`)
- `items` (list)
- `checks_performed` (list)
- `bugs_found` (list)
- `unresolved_items` (list)
- `notes`

### Decision Rule
- large discrepancy -> investigate
- confirmed bug -> fix, regenerate affected artifacts, and document
- no confirmed bug -> keep discrepancy visible and report honestly

### Related Skills
- `11_PLOTTING_AND_REPORT.md`
- `13_VISUAL_VERIFICATION.md`
- `18_MC_NORMALIZATION_METADATA_STACKING.md`
- `21_FINAL_REPORT_REVIEW_AND_HANDOFF.md`
