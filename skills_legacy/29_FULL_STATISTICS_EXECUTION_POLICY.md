# Skill: Full-Statistics Execution Policy

## Layer 1 — Physics Policy
Final analysis claims must be based on full statistics for the selected samples.

Policy requirements:
- default execution must use full statistics (all events in each selected sample/file)
- partial-statistics execution is allowed only when:
  - the user explicitly requests partial statistics, or
  - a fast test is needed for validation, with the explicit expectation that a full-statistics run is completed in the same task before handoff
- never present partial-statistics outputs as final analysis results unless the user explicitly requested a partial-only deliverable
- if a fast test is used first, clearly mark it as non-final and keep its outputs separate from final full-statistics outputs
- if full-statistics execution fails for technical reasons, report the blocker and classify the task as incomplete rather than silently handing off partial results

## Layer 2 — Workflow Contract
### Inputs
- user request and constraints
- analysis run configuration
- sample/file inventory
- runtime control flags (for example event caps)

### Decision Logic
1. Determine run mode:
   - `full_required` by default
   - `partial_allowed_user_requested` only when user explicitly asks for partial statistics
   - `fast_test_then_full_required` when agent performs a short validation run first
2. For `full_required`:
   - disable event caps and process complete selected samples
3. For `fast_test_then_full_required`:
   - run fast test with explicit cap and test-labeled output directory
   - run full-statistics production pass in the same task with separate final output directory
4. Do not finalize the task until one of these is true:
   - full-statistics run completed, or
   - user explicitly approved partial-only scope

### Required Artifacts
- statistics-policy artifact:
  - `outputs/report/statistics_policy.json`
  - fields:
    - `mode` in `{full_required, partial_allowed_user_requested, fast_test_then_full_required}`
    - `user_requested_partial` (bool)
    - `fast_test_used` (bool)
    - `full_statistics_completed` (bool)
    - `final_outputs_source` (`full_statistics` or `partial_statistics`)
    - `notes` (list)
- run manifest must clearly record event-cap configuration and whether full statistics were achieved
- if fast test is used, separate output roots should be used for test vs final runs

### Acceptance Checks
- if user did not explicitly request partial-only results, `full_statistics_completed` must be `true`
- final report and handoff artifacts must point to full-statistics outputs unless user explicitly requested partial-only scope
- any fast-test artifacts must be labeled non-final in report/handoff text
- no silent fallback from full to partial statistics is allowed

## Layer 3 — Example Implementation
### Current Repository (W+jets pipeline)
Full-statistics run:
```bash
.venv/bin/python -m analysis.wplus_highpt_pipeline \
  --inputs input-data \
  --lumi-fb 36.0 \
  --max-events-per-file 0
```

Fast test then full-statistics run (same task):
```bash
# Non-final fast test
.venv/bin/python -m analysis.wplus_highpt_pipeline \
  --inputs input-data \
  --lumi-fb 36.0 \
  --max-events-per-file 20000 \
  --outputs outputs_wplus_fasttest

# Final full-statistics production run
.venv/bin/python -m analysis.wplus_highpt_pipeline \
  --inputs input-data \
  --lumi-fb 36.0 \
  --max-events-per-file 0 \
  --outputs outputs_wplus_fullstat
```

Suggested `statistics_policy.json`:
- set `mode = full_required` for default runs
- set `mode = fast_test_then_full_required` when a fast test precedes a same-task full run
- set `mode = partial_allowed_user_requested` only when explicitly requested by the user

### Related Skills
- `22_AGENT_PRE_FLIGHT_FACT_CHECK.md`
- `12_SMOKE_TESTS_AND_REPRODUCIBILITY.md`
- `19_FINAL_ANALYSIS_REPORT_AGENT_WORKFLOW.md`
- `21_FINAL_REPORT_REVIEW_AND_HANDOFF.md`
