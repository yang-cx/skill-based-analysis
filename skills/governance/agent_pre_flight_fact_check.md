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

### Escalation Rule
- if any critical item above is missing or ambiguous:
  - pause execution
  - present a concise missing/ambiguous-items list to the human
  - request clarification
- after clarification is received, proceed and avoid further interruption during run execution

### Required Output
Produce a short pre-flight summary containing:
- pass/fail status
- clarified items (if any)
- assumptions recorded before execution

## Layer 3 — Example Implementation
### Recommended Artifact
- `outputs/report/preflight_fact_check.json` with:
  - `status` (`pass` or `blocked`)
  - `checked_items` (list)
  - `missing_or_ambiguous` (list)
  - `clarifications_received` (list)
  - `assumptions` (list)
  - `ready_to_execute` (bool)

### Minimum Human Message
- one concise statement that pre-flight passed or is blocked
- if blocked, a compact list of required clarifications

### Related Skills
- `core_pipeline/read_summary_and_validate.md`
- `core_pipeline/sample_registry_and_normalization.md`
- `analysis_strategy/signal_background_strategy_and_cr_constraints.md`
- `analysis_strategy/control_region_signal_region_blinding_and_visualization.md`
