---
name: extract-new-skill-from-failure
description: "Repository-specific workflow and policy for Extract New Skill from Failure. Use when Codex needs the required artifacts, validation checks, execution steps, or constraints for this analysis stage in the repo."
---

# Extract New Skill from Failure

## Layer 1 — Physics Policy
After a run completes and the final report is produced, evaluate execution outcomes for reusable capability gaps. Convert recurring gaps into candidate skills for human review, without auto-promoting them into production skills.

Governance requirements:
- approved production skills exist only in `skills/`
- newly proposed skills must be written in `candidate_skills/`
- files in `candidate_skills/` are not active skills
- do not move/promote candidate skills into `skills/` without explicit human approval
- run this step after task completion and final report generation
- run this step for every completed production run (mandatory default)
- always emit `outputs/report/skill_extraction_summary.json`, including zero-candidate runs

Operational requirements:
- use only observable run artifacts (reports, logs, warnings/errors, patches, workflow notes, outputs)
- do not rely on hidden internal reasoning traces
- create candidate skills only for likely recurring patterns, not one-off mistakes

## Layer 2 — Workflow Contract
### Inputs
- final report
- run logs and warning/error outputs
- execution notes
- code patches/workflow adjustments made during the run
- unusual numerical or structural outputs

### Detection Targets
Identify whether execution exposed:
- workaround-required failures
- repeated friction points
- improvised missing procedures
- missing decision logic causing confusion
- missing factual info that forced guessing
- missing validation/safety checks

### Decision Rule
Create candidate skills only when the issue is likely to recur.

Do not create candidate skills for:
- simple coding mistakes
- typographical errors
- one-time environment problems
- trivial syntax fixes
- purely incidental issues

### Candidate Skill Requirements
For each candidate skill, create a file under `candidate_skills/` including:
- Skill name
- Status: `candidate`
- Problem solved
- Run evidence that motivated it
- Intended scope
- Inputs
- Outputs
- Trigger conditions
- Constraints/invariants
- Why this is reusable vs a local patch

### Required Human Summary
Produce a concise summary listing:
- number of candidate skills proposed
- each candidate skill name
- motivating failure/workaround
- expected future utility

Explicitly state:
- candidate skills require human approval before promotion into `skills/`

## Layer 3 — Example Implementation
### Required Artifacts
- candidate skill files:
  - `candidate_skills/<candidate_name>.md`
- run-level extraction summary:
  - `outputs/report/skill_extraction_summary.json`

Suggested `skill_extraction_summary.json` fields:
- `status` (`none_found` or `candidates_created`)
- `n_candidates`
- `candidates` (list of file paths)
- `evidence_sources` (list of artifact paths)
- `promotion_rule` (`human_approval_required`)

### Trigger Condition
- invoke after:
  1. analysis execution is complete
  2. final report has been generated
  3. final handoff/review is being prepared (completion gate)

### Related Skills
- `$final-report-review-and-handoff`
- `$final-analysis-report-agent-workflow`
- `$smoke-tests-and-reproducibility`
