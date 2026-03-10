# Skill: Object Definitions

## Layer 1 — Physics Policy
Define reconstructed objects first, then construct event-level selections from those objects.

Policy requirements:
- object quality and kinematic selections must be explicit and reproducible
- leading/subleading object definitions must be deterministic
- event-level features should be derived from validated object collections
- analysis thresholds and working points should come from configuration, not hardcoded logic

## Layer 2 — Workflow Contract
### Required Artifacts
- object-augmented event artifact containing selection masks, multiplicities, and leading/subleading kinematics
- object-definition metadata artifact documenting thresholds and working points used
- object-QA summary artifact with basic rates (for example average object multiplicity)

### Acceptance Checks
- object masks and multiplicities are consistent with underlying collections
- leading/subleading quantities are defined only where multiplicity requirements are satisfied
- configured thresholds/working points are traceable in metadata
- missing required configuration is flagged with warning or explicit failure

## Layer 3 — Example Implementation
### Pattern (Current Repository)
- `build_photons(events, cfg) -> events` adds derived columns and masks
- analogous builders for jets/leptons as needed

### Configuration Sources (Current Repository)
- `analysis/regions.yaml` (preferred)
- structured summary fields when available

### CLI (Current Repository)
`python -m analysis.objects.photons --sample <ID> --registry outputs/samples.registry.json --regions analysis/regions.yaml --out outputs/cache/<ID>.objects.parquet`
