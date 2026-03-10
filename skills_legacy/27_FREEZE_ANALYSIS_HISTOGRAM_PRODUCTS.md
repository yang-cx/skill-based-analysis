# Skill: Freeze Analysis Histogram Products

## Layer 1 — Physics Policy
Histogram templates produced from expensive event processing should be frozen into immutable, reusable artifacts so downstream analysis can iterate without rerunning event loops.

Policy requirements:
- Freeze only after histogram production has passed basic integrity checks.
- Preserve statistical content required for physics reuse (`counts`, `sumw2`, bin edges).
- Keep repository-native histogram format (`.npz`) as the authoritative physics artifact in this codebase.
- JSON exports are secondary agent-readable sidecars.
- Never replace existing baseline workflows; freezing is additive and optional.
- Frozen artifacts are immutable once finalized.

## Layer 2 — Workflow Contract
### When To Use
- Run immediately after `08_HISTOGRAMMING_AND_TEMPLATES.md` is complete.
- Use for repeated downstream tasks:
  - plotting
  - workspace building
  - fit and significance reruns
  - report updates
  - optimization scans

### Required Inputs
- `outputs/hists/` templates (`<region>/<observable>/<sample>.npz`)
- `outputs/summary.normalized.json`
- `outputs/samples.registry.json` (if available)
- run provenance:
  - analysis name/version
  - git commit
  - config hash
  - timestamp

### Required Frozen Bundle Artifacts
- `outputs/frozen/<freeze_id>/manifest_index.json`
- `outputs/frozen/<freeze_id>/<sample>/<region>/<observable>/nominal.npz`
- `outputs/frozen/<freeze_id>/<sample>/<region>/<observable>/manifest.json`
- `outputs/frozen/<freeze_id>/<sample>/<region>/<observable>/nominal.json` (agent-readable sidecar)
- `outputs/frozen/<freeze_id>/validation_report.json`

`freeze_id` must be deterministic and include at least:
- analysis version
- config hash prefix
- git commit prefix

### Cache Key Rules
Each frozen histogram manifest must include a deterministic `cache_key` computed from canonical JSON over:
- analysis version
- sample/process id
- region id
- observable
- bin edges
- config hash
- git commit
- weight/modeling metadata available at freeze time

Recommended hash:
- `sha256(canonical_json_bytes)`

Canonicalization rules:
- sort keys
- UTF-8 encoding
- no whitespace-dependent formatting

### Reuse Logic
Before writing a new frozen artifact:
1. Search existing frozen bundles for matching `cache_key`.
2. Validate checksum(s) and required files.
3. Reuse only if both key and checksum validation pass.

If mismatch or corruption is found:
- write a new `freeze_id` bundle (do not overwrite existing bundle content).

### Invalidation Rules
Must invalidate (regenerate freeze artifacts) when any of these change:
- region selections or cut logic
- observable definitions or binning
- dataset membership
- event weighting recipe
- object definitions / working points
- systematic configuration
- histogramming code affecting numerical content

May reuse frozen artifacts when only these change:
- plotting style
- axis ranges
- report formatting/text
- visualization grouping that does not alter bin content

### Validation Requirements
Each frozen artifact must be validated:
- `len(counts) == len(edges) - 1`
- `len(sumw2) == len(counts)`
- no NaN/Inf in `counts` or `sumw2`
- manifest includes required provenance fields
- checksum recorded and reproducible

`validation_report.json` must include:
- status (`pass`/`fail`)
- number of artifacts checked
- failed checks (if any)
- missing files (if any)

### Safety Rules
- Never silently overwrite an existing finalized artifact file.
- Use temp-file write + atomic rename for each artifact.
- If target path exists with different checksum, create a new bundle directory.

## Layer 3 — Example Implementation
### Repository-Native Source Layout
- `outputs/hists/<region>/<observable>/<sample>.npz`

### Frozen Layout
```text
outputs/frozen/<freeze_id>/
  manifest_index.json
  validation_report.json
  <sample>/
    <region>/
      <observable>/
        nominal.npz
        nominal.json
        manifest.json
```

### Minimum Manifest Fields (`manifest.json`)
- `freeze_id`
- `cache_key`
- `sample`
- `region`
- `observable`
- `bin_edges`
- `checksum_nominal_npz`
- `source_npz_path`
- `analysis_version`
- `config_hash`
- `git_commit`
- `timestamp_utc`
- `blinding_state` (if available)

### Related Skills
- `08_HISTOGRAMMING_AND_TEMPLATES.md`
- `10_WORKSPACE_AND_FIT_PYHF.md`
- `11_PLOTTING_AND_REPORT.md`
- `12_SMOKE_TESTS_AND_REPRODUCIBILITY.md`

