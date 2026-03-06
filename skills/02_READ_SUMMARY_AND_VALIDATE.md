# Skill: Read Summary and Validate

## Layer 1 — Physics Policy
The structured analysis definition is the source of truth for analysis intent and must be internally consistent.

Policy requirements:
- region identifiers must be unique and unambiguous
- fit-region references must resolve to declared regions
- signal-signature associations must resolve to declared signatures
- reported fit references must resolve to declared fits
- SR/CR overlap policy must be explicit: mutually exclusive by default, with any exception declared and justified
- invalid or ambiguous analysis definitions must fail fast
- this validation skill is executed after `22_AGENT_PRE_FLIGHT_FACT_CHECK.md` has confirmed execution readiness

## Layer 2 — Workflow Contract
### Required Artifacts
- normalized analysis-definition artifact with canonicalized identifiers and fields
- validation-inventory artifact summarizing number of regions, fit IDs, observables, and POIs
- validation-diagnostic artifact describing any schema or cross-reference failures
- overlap-policy validation artifact listing SR/CR pairs and overlap allowance flags

### Acceptance Checks
- all required keys and enums validate
- signal-region and control-region identifiers are unique
- each fit region reference resolves to an existing region
- each signal-signature reference resolves to an existing signature
- each result-to-fit reference resolves to an existing fit configuration
- each SR/CR pair used together in a fit has declared overlap policy; default is `allow_overlap = false`

## Layer 3 — Example Implementation
### CLI (Current Repository)
`python -m analysis.config.load_summary --summary analysis/analysis.summary.json --out outputs/summary.normalized.json`

### Outputs (Current Repository)
- `outputs/summary.normalized.json`
- console inventory with number of SR/CR, fit IDs, observables, and POIs

### Related Skills
- `22_AGENT_PRE_FLIGHT_FACT_CHECK.md`
