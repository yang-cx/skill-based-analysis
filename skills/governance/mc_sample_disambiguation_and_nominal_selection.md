---
skill_type: governance
domain: hep_analysis
stage: validation
original_id: "34"
original_filename: "34_MC_SAMPLE_DISAMBIGUATION_AND_NOMINAL_SELECTION.md"
---

# Skill: MC Sample Disambiguation and Nominal Selection

## Layer 1 — Physics Policy
When multiple MC datasets can represent the same nominal physics process, the agent must identify one unique central sample set per process before computing central yields or building the statistical model.

Policy requirements:
- inspect all available MC candidates before assigning central signal/background sample sets
- define a stable physics-process key that separates production mode, decay/final state, and analysis role
- use semantically meaningful dataset-name tokens and metadata to identify candidates, especially:
  - generator
  - parton shower / hadronization configuration
  - PDF / tune markers
  - decay or final-state markers
- do not use simple numeric indexing alone (for example `001`, `002`, `v1`, `v2`) as evidence that two datasets are physically distinct or ordered
- for a decay-specific analysis, central signal samples must match the targeted decay/final state exactly
- inclusive-Higgs samples or Higgs samples for other decays must not enter central `H -> gamma gamma` signal yields unless an explicit and justified combination policy is declared
- when multiple plausible candidates remain for one process, select one nominal/reference dataset and mark the rest as alternatives, cross-checks, or systematic-only inputs
- if the meaning of candidate samples or the nominal choice is ambiguous, stop and ask the human before execution continues
- record the human clarification and selection rationale in machine-readable artifacts and in the final report appendix

## Layer 2 — Workflow Contract
### Inputs
- available MC file inventory
- sample registry with file paths and dataset names
- open-data metadata tables when available
- analysis objective and target final state
- prior reports or notes describing intended signal/background definitions

### Required Artifacts
- MC sample disambiguation artifact at `outputs/report/mc_sample_selection.json` containing:
  - `status` (`resolved` or `blocked`)
  - `analysis_target`
  - `processes` (list of per-process decisions)
  - `ambiguous_processes` (list)
  - `human_clarifications` (list)
  - `notes`
- per-process entries in `processes` containing:
  - `process_key`
  - `analysis_role`
  - `selected_nominal_samples`
  - `alternative_samples`
  - `excluded_samples`
  - `selection_basis`
  - `ambiguity_status`
  - `requires_human_clarification`
- final report appendix section documenting why each nominal sample set was chosen from the available candidates

### Decision Procedure
1. Enumerate all candidate MC files relevant to the target process family.
2. Group candidates by physics meaning, not by filename order:
   - production mode
   - decay/final state
   - generator / shower / PDF implementation
3. Reject candidates whose final state does not match the central analysis target unless they are explicitly designated as alternative or cross-check samples.
4. For each physics process, identify one nominal/reference sample set for central yields and fits.
5. If two or more candidates remain equally plausible and the repository context does not resolve them, block and request human clarification.
6. Record the chosen nominal sample set and the rejected/alternative candidates with justification.

### Acceptance Checks
- each central physics process has exactly one nominal/reference sample set
- central-yield and fit inputs exclude alternative or non-matching-decay samples unless an explicit policy says otherwise
- sample-selection logic relies on physics-meaning tokens and metadata, not simple index ordering
- ambiguous nominal choices block execution until clarified by a human
- final report main body discusses the samples used, while the appendix explains why those samples were selected over other available files

## Layer 3 — Example Implementation
### Recommended `mc_sample_selection.json` Shape
```json
{
  "status": "resolved",
  "analysis_target": "pp -> H -> gamma gamma",
  "processes": [
    {
      "process_key": "ggF_Hyy",
      "analysis_role": "signal_nominal",
      "selected_nominal_samples": ["343981"],
      "alternative_samples": ["346797"],
      "excluded_samples": ["345060", "345097"],
      "selection_basis": [
        "matches H->gammagamma target final state",
        "Powheg+Pythia8 nominal over alternative Herwig shower sample"
      ],
      "ambiguity_status": "resolved",
      "requires_human_clarification": false
    }
  ],
  "ambiguous_processes": [],
  "human_clarifications": [],
  "notes": []
}
```

### Related Skills
- `governance/agent_pre_flight_fact_check.md`
- `core_pipeline/sample_registry_and_normalization.md`
- `physics_facts/mc_normalization_metadata_stacking.md`
- `core_pipeline/final_analysis_report_agent_workflow.md`
