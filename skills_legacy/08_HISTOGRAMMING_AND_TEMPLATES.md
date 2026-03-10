# Skill: Histogramming and Templates

## Layer 1 — Physics Policy
Histogram templates must encode fit observables with consistent binning and statistical information.

Policy requirements:
- observables and binning should follow the analysis definition
- if binning is unspecified, choose a deterministic default and document it
- each histogram must include statistical uncertainty information (for example sum of squared weights)
- template integrals should reproduce selected yields within tolerance

## Layer 2 — Workflow Contract
### Required Artifacts
- per-region, per-observable, per-sample histogram-template artifact containing edges, counts, and uncertainty terms
- histogram-metadata artifact with observable name, region, sample, and binning provenance
- binning-decision artifact when default binning is used

### Acceptance Checks
- templates exist for every sample that enters each fit region
- histogram binning is consistent within each fit observable definition
- template integrals are consistent with region yields within tolerance
- metadata identifies region, sample, and observable for every template

## Layer 3 — Example Implementation
### Portable Format (Current Repository)
`.npz` files with:
- bin edges
- counts
- sumw2
- metadata (region, sample, observable)

Suggested layout:
`outputs/hists/<region_id>/<observable>/<sample_id>.npz`

### CLI (Current Repository)
`python -m analysis.hists.histmaker --sample <ID> --registry outputs/samples.registry.json --regions analysis/regions.yaml --summary outputs/summary.normalized.json --out outputs/hists/`

### Downstream Reference
If analytic mass fits are used, run:
- `16_SIGNAL_SHAPE_AND_SPURIOUS_SIGNAL_MODEL_SELECTION.md`
