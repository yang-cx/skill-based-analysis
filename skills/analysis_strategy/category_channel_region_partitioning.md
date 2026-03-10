---
skill_type: decision
domain: hep_analysis
stage: design
original_id: "20"
original_filename: "20_CATEGORY_CHANNEL_REGION_PARTITIONING.md"
---

# Skill: Category/Channel x Region Partitioning (SR/CR/SB/VR) for LHC Analyses

## Layer 1 - Physics Policy

### Objective
Represent the analysis phase space using two orthogonal concepts:

1. Category/Channel axis (topology or sensitivity partition)
2. Region axis (statistical usage partition)

This structure must support both complex analyses (multiple categories/channels) and simple analyses (single inclusive selection).

### Category/Channel Definition

Categories/channels divide events into mutually exclusive subsets with different signal-to-background behavior or physics topology.

Examples:
- diphoton analysis categories
- jet multiplicity channels (`0-jet`, `1-jet`, `2-jet`)
- VBF-tagged events
- boosted Higgs events

Rules:
- each event must be assigned to exactly one category/channel
- category assignment must be mutually exclusive
- categories should cover all selected events unless an explicit `unassigned` bucket is documented

Inclusive fallback:
- if no natural category split exists, define a single category:
- `category_id = inclusive`

### Region Definition

Regions define statistical usage of events:
- `SR` signal region
- `CR` control region
- `SB` sideband
- `VR` validation region

The atomic statistical key is:
- `(category, region)`

### Diphoton Mass-Spectrum Analyses

For analyses such as `H -> gamma gamma`, both approaches must be supported:

1. Explicit windows:
- `SR` peak window
- `SB` sideband windows

2. Conceptual regions within a full-spectrum fit:
- fit uses full mass range (for example `105-160 GeV`)
- `SR` corresponds to peak interpretation
- `SB` corresponds to sideband interpretation

### Consistency Rules

- category assignments must be exclusive
- category assignments must be complete unless explicitly documented otherwise
- regions must be explicitly defined via selection logic or statistical interpretation
- region definitions must declare type (`SR`, `CR`, `SB`, `VR`, or `OTHER`)
- if blinding is active, it must operate at `(category, region)` granularity
- downstream statistical tools must consume category lists dynamically; no fixed category count should be assumed

## Layer 2 - Workflow Contract

### Inputs

1. Category/channel definition artifact:
- category identifiers
- category assignment logic

2. Region definition artifact:
- region identifiers
- associated category (directly or by cartesian mapping rule)
- region type
- selection basis and logic

3. Optional observable definitions when regions depend on mass/fit-domain ranges.

### Required Artifacts

1. Partition specification artifact (machine-readable):
- category list
- region list
- category-region mapping

For each `(category, region)` entry:
- `category_id`
- `region_id`
- `region_type`
- `selection_basis`
- `selection_definition`
- `blinding_policy`
- optional notes/justification

Selection basis examples:
- `mass_window`
- `control_variable`
- `topology_selection`
- `fit_domain`

2. Partition completeness/exclusivity report (machine-readable):
- category assignment exclusivity
- category assignment coverage
- region enumeration consistency
- duplicate partition checks

3. Partition manifest artifact:
- flat authoritative list of atomic partitions
- fields:
  - `category_id`
  - `region_id`
  - `region_type`

Downstream users:
- cut flow
- histogramming
- statistical model building
- plotting

### Acceptance Checks

1. Category exclusivity:
- no event can satisfy assignment rules for multiple categories

2. Category coverage:
- selected events are assigned to a category or explicitly tracked as `unassigned`

3. Partition uniqueness:
- each `(category, region)` appears exactly once

4. Region enumeration consistency:
- all referenced regions appear in the manifest

5. Diphoton compatibility:
- if `selection_basis = fit_domain`, artifact includes fit observable range metadata

6. Blinding readiness:
- signal partitions default to `data_shown = false` unless explicit unblinding directive exists

7. Dynamic category compatibility:
- downstream fit/plot workflows can run with arbitrary number of configured categories without code changes

## Layer 3 - Tool Binding (Current Repository)

### Example Inputs
- `analysis/categories.yaml`
- `analysis/regions.yaml`

### Expected Outputs
- `outputs/report/partition_spec.json`
- `outputs/report/partition_checks.json`
- `outputs/manifest/partitions.json`

### CLI
`python -m analysis.partitioning.build_partitions --categories analysis/categories.yaml --regions analysis/regions.yaml --out-spec outputs/report/partition_spec.json --out-manifest outputs/manifest/partitions.json --out-checks outputs/report/partition_checks.json`

### Implementation Notes
- exclusivity checks can be declarative or event-level, but must be explicit in checks metadata
- region definitions should remain structured for machine interpretation
- diphoton mass analyses should support both window-based and full-fit-domain semantics
- downstream tools should consume `outputs/manifest/partitions.json` rather than re-deriving partition logic
