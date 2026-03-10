---
skill_type: governance
domain: hep_analysis
stage: validation
original_id: "22"
original_filename: "22_AGENT_PRE_FLIGHT_FACT_CHECK.md"
---

# Skill: Agent Pre-Flight Fact Check

## Layer 1 — Physics Policy
Before launching a full analysis workflow, the agent must verify that critical analysis facts are defined unambiguously. If critical facts are missing or ambiguous, the agent must pause and request clarification before execution.

Policy requirements:
- invoke this skill immediately after receiving the analysis task and before large-scale execution
- treat this as a one-time checkpoint before run start
- do not start large computation on incomplete specifications
- after pre-flight passes and execution begins, do not interrupt again until completion unless a hard technical failure prevents continuation
- record any assumptions explicitly
- initialize skill-refresh/checkpoint planning at run start and emit the first refresh checkpoint record
- verify mandatory method constraints are technically satisfiable before run start

## Layer 2 — Workflow Contract
### Inputs
- analysis specification or instruction prompt
- analysis configuration JSON/YAML
- dataset description files
- links to analysis documentation
- repository configuration files
- previous reports/notes describing intended analysis

### Required Fact Checks
1. Measurement objective:
   - verify the scientific objective is explicit (for example search, significance, limits, fit scan)
2. Integrated luminosity:
   - verify luminosity value, units, and data-taking period are clear
3. Signal/background samples:
   - verify signal/background mapping and dataset identifiers are clear
   - verify nominal-vs-alternative sample selection is defined for each central physics process when multiple MC candidates exist
   - verify no decay-mismatched or inclusive samples are silently entering a decay-specific central signal definition
4. Systematic uncertainties:
   - verify there is an explicit statement:
     - systematics list
     - or omitted at this stage
     - or deferred with placeholder plan
5. Signal/control/sideband regions:
   - verify region definitions exist and are logically consistent
   - verify no unintended SR/CR overlap unless explicitly intended
6. Blinding status:
   - verify blinded / partially blinded / unblinded status is explicit
   - if blinded, verify SR data handling policy is explicit
7. Statistical method:
   - verify requested statistical procedure and outputs are explicit
8. Mandatory backend/method capability:
   - verify required primary backend capabilities are available in the runtime
   - for H->gammagamma, verify PyROOT/RooFit analytic-function fit capability for primary fit and significance
9. Runtime/tooling readiness:
   - verify a functioning analysis pipeline/toolchain is available for required stages
   - verify ROOT event ingestion is supported through `uproot`
   - if missing-but-buildable runtime/tooling is detected, plan construction/repair before production execution

### Escalation Rule
- if any critical item above is missing or ambiguous:
  - pause execution
  - present a concise missing/ambiguous-items list to the human
  - request clarification
- if functioning runtime/tooling is missing but buildable in-task:
  - construct/repair the missing pipeline/tooling first
  - run a limited-entry validation pass if needed
  - continue to full-sample execution before declaring completion
- if mandatory backend/method capability is unavailable for the analysis target:
  - block execution for primary results
  - do not auto-substitute a different primary backend
- after clarification is received, proceed and avoid further interruption during run execution

### Required Output
Produce a short pre-flight summary containing:
- pass/fail status
- clarified items (if any)
- assumptions recorded before execution
- skill-refresh initialization status for the `preflight_ready` checkpoint

## Layer 3 — Example Implementation
### Recommended Artifact
- `outputs/report/preflight_fact_check.json` with:
  - `status` (`pass` or `blocked`)
  - `checked_items` (list)
  - `missing_or_ambiguous` (list)
  - `clarifications_received` (list)
  - `assumptions` (list)
  - `ready_to_execute` (bool)
  - `skill_refresh_initialized` (bool)
  - `skill_refresh_checkpoint_id` (string; expected `preflight_ready`)

### Minimum Human Message
- one concise statement that pre-flight passed or is blocked
- if blocked, a compact list of required clarifications

### Related Skills
- `core_pipeline/read_summary_and_validate.md`
- `core_pipeline/sample_registry_and_normalization.md`
- `governance/mc_sample_disambiguation_and_nominal_selection.md`
- `analysis_strategy/signal_background_strategy_and_cr_constraints.md`
- `analysis_strategy/control_region_signal_region_blinding_and_visualization.md`
- `governance/skill_refresh_and_checkpointing.md`
