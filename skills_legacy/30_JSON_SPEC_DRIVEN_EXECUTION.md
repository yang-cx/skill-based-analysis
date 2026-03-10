# Skill: JSON-Spec-Driven Analysis Execution

## Layer 1 — Physics Policy
The structured analysis JSON is the execution source of truth. Trigger prompts should stay minimal and point to the JSON.

Policy requirements:
- use the referenced analysis JSON as the primary specification for objectives, regions, observables, and fit scope
- run summary validation before production execution
- treat free-form narrative as secondary context unless the user gives an explicit override
- apply global workflow policies from the skills pack (blinding, reporting, discrepancy checks, handoff checks)
- default to full-statistics execution unless user scope explicitly requests partial statistics
- when the selected runtime pipeline is not fully JSON-native, create an explicit mapping from JSON intent to runtime configuration and document deviations
- if a user constraint overrides JSON content (for example luminosity, backend, or blinding scope), record the override explicitly
- do not silently drop JSON-defined fit regions, observables, or process roles

## Layer 2 — Workflow Contract
### Inputs
- analysis JSON path provided by user/prompt
- input data/MC directory
- runtime constraints (if any)

### Required Artifacts
- `outputs/report/spec_validation_summary.json`
- `outputs/report/spec_to_runtime_mapping.json`
- `outputs/report/deviations_from_spec.json`
- `outputs/report/execution_contract.json`

### Acceptance Checks
- analysis JSON exists and is readable
- summary validation succeeds (or failure is surfaced and execution stops)
- selected runtime regions/observables are traceable to JSON fields
- each runtime override is listed with `source = user_override`
- each approximation/substitution is listed with reason and expected analysis impact
- final report references the JSON path used for the run

### Minimum `execution_contract.json` fields
- `analysis_json`
- `inputs_path`
- `outputs_path`
- `full_statistics_required`
- `full_statistics_completed`
- `lumi_fb_runtime`
- `blinding_mode`
- `fit_backend_primary`
- `notes`

## Layer 3 — Example Implementation
### JSON Validation
`python -m analysis.config.load_summary --summary analysis/<analysis>.analysis.json --out outputs/summary.normalized.json`

### JSON-Native Pipeline (example)
`python -m analysis.cli run --summary analysis/<analysis>.analysis.json --inputs input-data --outputs outputs --all-samples`

### Non-JSON-Native Pipeline (example)
- run the dedicated pipeline
- write `spec_to_runtime_mapping.json` and `deviations_from_spec.json` to preserve JSON traceability

### Related Skills
- `02_READ_SUMMARY_AND_VALIDATE.md`
- `29_FULL_STATISTICS_EXECUTION_POLICY.md`
- `19_FINAL_ANALYSIS_REPORT_AGENT_WORKFLOW.md`
- `21_FINAL_REPORT_REVIEW_AND_HANDOFF.md`
