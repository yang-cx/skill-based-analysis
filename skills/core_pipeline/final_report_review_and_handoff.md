---
skill_type: procedure
domain: hep_analysis
stage: reporting
original_id: "21"
original_filename: "21_FINAL_REPORT_REVIEW_AND_HANDOFF.md"
---

# Skill: Final Report Review and Handoff

## Layer 1 — Physics Policy
After analysis execution and report generation, perform a structured review to detect anomalies, assess completion status, and prepare a handoff record for human or agent continuation.

Policy requirements:
- run this review immediately after report generation for each production run
- treat the final report as both:
  - a human-readable result narrative
  - a technical state record for continuation
- flag suspicious values and inconsistencies instead of silently accepting them
- separate hard failures from warnings
- ensure continuation-critical metadata and artifact paths are explicitly documented
- preserve blinding policy when reviewing statistical/plot outputs
- enforce post-run skill extraction as a completion gate; missing extraction summary is a handoff blocker
- enforce data-MC discrepancy artifact completion as a gate; missing discrepancy artifacts are handoff blockers
- enforce skill-refresh/checkpoint completion as a gate; missing or failing checkpoint status is a handoff blocker

## Layer 2 — Workflow Contract
### Inputs
- final analysis report
- cut-flow and yield tables/artifacts
- generated plots
- fit/significance artifacts
- run configuration files
- workflow execution logs/manifests
- `outputs/report/mc_sample_selection.json`
- `outputs/report/skill_extraction_summary.json`
- `outputs/report/data_mc_discrepancy_audit.json`
- `outputs/report/data_mc_check_log.json`
- `outputs/report/skill_refresh_plan.json`
- `outputs/report/skill_refresh_log.jsonl`
- `outputs/report/skill_checkpoint_status.json`

### Review Steps
1. Completeness check:
   - confirm required sections are present:
     - introduction/task summary
     - dataset description
     - object definitions and selections
     - signal/control regions
     - cut flow tables
     - distribution plots
     - statistical interpretation
     - summary
   - confirm sample descriptions include:
     - separate data and Monte Carlo descriptions
     - MC generator and simulation configuration
     - MC process modeling and signal/background role
   - when multiple candidate MC samples existed, confirm the report contains a dedicated appendix describing the nominal/reference sample selection rationale
   - flag missing sections
2. Narrative-scope check:
   - verify event-selection narrative discusses only regions entering the log-likelihood fit
   - verify each fit region has its fit observable documented
3. Numerical sanity checks:
   - detect suspicious patterns:
     - zero yields where events are expected
     - unusually large yields
     - placeholders (`0`, `NaN`, dummy constants)
     - fit parameters at boundaries
     - zero/unrealistic uncertainties
     - significance values inconsistent with yields/model
4. Plot validation:
   - detect issues:
     - empty histograms
     - missing distributions
     - axis-range mismatch
     - missing expected data points
     - stack mismatch vs totals
   - verify fit-state normalization semantics:
     - pre-fit plots use nominal MC prediction
     - post-fit plots use fitted normalization values
   - verify blinding semantics:
     - blinded mode hides sensitive SR data by omission or masking
     - unblinded mode shows observed data across full SR
5. Consistency checks:
   - verify:
     - table yields align with histogram integrals/fit summaries
     - categories referenced in text exist in plots/artifacts
     - regions used in text match fit configuration
6. Workflow outcome assessment:
   - classify run status:
     - completed successfully
     - completed with warnings
     - partially completed
     - major failure
7. Handoff preparation:
   - confirm report/handoff includes:
     - datasets used
     - MC sample-selection rationale artifact and appendix location
     - normalization method/luminosity
     - region/category definitions
     - key configuration parameters
     - systematics model scope
     - statistical model and backend
     - exact output artifact locations
   - flag missing continuation-critical information
8. Skill-extraction completion gate:
   - verify `outputs/report/skill_extraction_summary.json` exists and is readable
   - verify summary `status` is either `none_found` or `candidates_created`
   - if `candidates_created`, verify listed `candidate_skills/*` files exist
   - if this gate fails, classify run status as `partially completed` or `major failure` (not handoff-ready)
9. Data-MC discrepancy completion gate:
   - verify `outputs/report/data_mc_discrepancy_audit.json` exists and is readable
   - verify discrepancy-audit `status` is one of:
     - `no_substantial_discrepancy`
     - `discrepancy_investigated_bug_found`
     - `discrepancy_investigated_no_bug_found`
   - verify `outputs/report/data_mc_check_log.json` exists and is readable
   - if this gate fails, classify run status as `partially completed` or `major failure` (not handoff-ready)
10. Skill-refresh/checkpoint completion gate:
   - verify `outputs/report/skill_refresh_plan.json` exists and is readable
   - verify `outputs/report/skill_refresh_log.jsonl` exists and is readable
   - verify `outputs/report/skill_checkpoint_status.json` exists and is readable
   - verify checkpoint status is `pass`
   - if this gate fails, classify run status as `partially completed` or `major failure` (not handoff-ready)

### Required Output
Produce a structured review summary containing:
- overall run status
- detected anomalies
- issues requiring human attention
- handoff-readiness statement (sufficient/insufficient for continuation)
- skill-extraction gate result and any blocking gaps
- data-MC discrepancy gate result and any blocking gaps
- skill-refresh/checkpoint gate result and any blocking gaps

## Layer 3 — Example Implementation
### Recommended Output Artifact
- `outputs/report/final_report_review.json` containing:
  - `status`
  - `anomalies` (list)
  - `consistency_issues` (list)
  - `missing_sections` (list)
  - `handoff_ready` (bool)
  - `handoff_gaps` (list)
  - `checked_artifacts` (paths)
  - `skill_extraction_checked` (bool)
  - `skill_extraction_status` (`none_found`, `candidates_created`, or `missing`)
  - `data_mc_discrepancy_checked` (bool)
  - `data_mc_discrepancy_status` (`no_substantial_discrepancy`, `discrepancy_investigated_bug_found`, `discrepancy_investigated_no_bug_found`, or `missing`)
  - `skill_refresh_checked` (bool)
  - `skill_refresh_status` (`pass` or `missing_or_failed`)

### Minimum Human Summary
- one concise run-status paragraph
- bulleted anomaly list (or explicit "none found")
- handoff readiness confirmation with any blocking gaps

### Related Skills
- `core_pipeline/plotting_and_report.md`
- `infrastructure/visual_verification.md`
- `core_pipeline/final_analysis_report_agent_workflow.md`
- `governance/mc_sample_disambiguation_and_nominal_selection.md`
- `core_pipeline/profile_likelihood_significance.md`
- `governance/skill_refresh_and_checkpointing.md`
