# Skill: Selection Engine and Regions

## Layer 1 — Physics Policy
Analysis regions must be defined as explicit, executable selection logic with clear semantic roles.

Policy requirements:
- each region has an identifier and role: signal, control, or validation
- region selections must be machine-executable and scientifically interpretable
- control and signal assignments must be consistent with the statistical strategy
- signal and control regions used together in a fit must be mutually exclusive at event level unless explicitly overridden with justification
- unresolved prose-only selections are insufficient for production execution

## Layer 2 — Workflow Contract
### Required Artifacts
- region-definition artifact with executable selection expressions
- per-sample region mask/yield artifact (weighted and unweighted)
- region-consistency artifact verifying references used by fit configurations
- SR/CR overlap-matrix artifact (pairwise overlap counts/fractions) with pass/fail status

### Acceptance Checks
- each referenced region exists and has executable logic
- region yields are produced for each processed sample
- fit-configuration region references resolve successfully
- SR/CR overlap checks fail fast when non-zero overlap is found for pairs without explicit `allow_overlap=true` override
- failures identify which region expression is missing or invalid

## Layer 3 — Example Implementation
### Region Model (Current Repository)
Each region contains:
- `region_id`
- `kind`: `signal | control | validation`
- `selection`
- optional `cutflow_steps`

### CLI (Current Repository)
`python -m analysis.selections.regions --sample <ID> --registry outputs/samples.registry.json --regions analysis/regions.yaml --out outputs/regions/<ID>.regions.json`

### Coordination Note
Control-vs-signal assignments are consumed by:
- `15_SIGNAL_BACKGROUND_STRATEGY_AND_CR_CONSTRAINTS.md`
