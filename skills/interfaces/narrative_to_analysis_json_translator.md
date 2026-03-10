---
skill_type: interface
domain: hep_analysis
stage: translation
original_id: "31"
original_filename: "31_NARRATIVE_TO_ANALYSIS_JSON_TRANSLATOR.md"
---

# Skill: Narrative-to-Analysis-JSON Translator

## Layer 1 — Physics Policy
Convert free-form analysis narratives into the repository analysis JSON schema before execution. This translation is for specification quality control, not for inventing physics content.

Policy requirements:
- convert narrative statements into structured JSON fields used by the analysis summary schema
- preserve user-provided facts; do not fabricate missing numerical values or unsupported claims
- represent unknown or missing details explicitly (for example `not_specified`) instead of guessing
- produce a gap report that identifies missing, ambiguous, and non-actionable items
- validate the produced JSON with existing summary validation tools
- require explicit assumptions/deviations log before using the generated JSON for production

## Layer 2 — Workflow Contract
### Inputs
- narrative analysis text (prompt, note, or document)
- optional reference JSON to reuse naming conventions

### Required Artifacts
- generated analysis JSON draft: `analysis/<name>.analysis.json`
- gap report: `outputs/report/analysis_json_gap_report.json`
- source trace map: `outputs/report/analysis_json_source_trace.json`

### Translation Steps
1. Extract core metadata (analysis name, energy, luminosity context, objective).
2. Extract signal signature and background-process definitions.
3. Extract SR/CR definitions, region purposes, and fit observables.
4. Extract fit setup and expected reported result types.
5. Fill unresolved fields with explicit placeholders (`not_specified`) and log them.
6. Run summary validation and iterate until schema/cross-reference checks pass.
7. Emit gap report and unresolved-questions list.

### Acceptance Checks
- generated JSON passes `analysis.config.load_summary` validation
- all top-level sections required by schema are present
- every unresolved item is listed in the gap report
- each assumption is tracked with rationale and expected impact
- output clearly distinguishes `provided_by_user` vs `assumed_by_agent`

### Minimum `analysis_json_gap_report.json` fields
- `status` (`pass_with_gaps` or `pass_no_gaps`)
- `missing_required_details` (list)
- `ambiguous_items` (list)
- `non_actionable_narrative_items` (list)
- `assumptions_applied` (list)
- `questions_for_user` (list)

## Layer 3 — Example Implementation
### Validate Draft JSON
`python -m analysis.config.load_summary --summary analysis/<name>.analysis.json --out outputs/summary.normalized.json`

### Suggested Handoff Rule
- do not start production execution until `analysis_json_gap_report.json` is produced and reviewed

### Related Skills
- `core_pipeline/read_summary_and_validate.md`
- `governance/agent_pre_flight_fact_check.md`
- `interfaces/json_spec_driven_execution.md`
