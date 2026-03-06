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

## Layer 2 — Workflow Contract
### Inputs
- final analysis report
- cut-flow and yield tables/artifacts
- generated plots
- fit/significance artifacts
- run configuration files
- workflow execution logs/manifests

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
   - flag missing sections
2. Numerical sanity checks:
   - detect suspicious patterns:
     - zero yields where events are expected
     - unusually large yields
     - placeholders (`0`, `NaN`, dummy constants)
     - fit parameters at boundaries
     - zero/unrealistic uncertainties
     - significance values inconsistent with yields/model
3. Plot validation:
   - detect issues:
     - empty histograms
     - missing distributions
     - axis-range mismatch
     - missing expected data points
     - stack mismatch vs totals
4. Consistency checks:
   - verify:
     - table yields align with histogram integrals/fit summaries
     - categories referenced in text exist in plots/artifacts
     - regions used in text match fit configuration
5. Workflow outcome assessment:
   - classify run status:
     - completed successfully
     - completed with warnings
     - partially completed
     - major failure
6. Handoff preparation:
   - confirm report/handoff includes:
     - datasets used
     - normalization method/luminosity
     - region/category definitions
     - key configuration parameters
     - systematics model scope
     - statistical model and backend
     - exact output artifact locations
   - flag missing continuation-critical information

### Required Output
Produce a structured review summary containing:
- overall run status
- detected anomalies
- issues requiring human attention
- handoff-readiness statement (sufficient/insufficient for continuation)

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

### Minimum Human Summary
- one concise run-status paragraph
- bulleted anomaly list (or explicit "none found")
- handoff readiness confirmation with any blocking gaps

### Related Skills
- `11_PLOTTING_AND_REPORT.md`
- `13_VISUAL_VERIFICATION.md`
- `19_FINAL_ANALYSIS_REPORT_AGENT_WORKFLOW.md`
- `14_PROFILE_LIKELIHOOD_SIGNIFICANCE.md`
