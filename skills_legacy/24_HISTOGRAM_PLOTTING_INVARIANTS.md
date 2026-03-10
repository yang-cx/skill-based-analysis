# Skill: Histogram Plotting Invariants

## Layer 1 — Physics Policy
All 1D histogram plots must satisfy consistent statistical and visual invariants unless the user explicitly overrides them.

Policy requirements:
- Applies to all 1D histograms, overlays, and ratio-panel comparisons.
- Use line-only (step) style by default: no filled histogram areas.
- Distinguish overlays by line color/style/width, not fill.
- Use common bin edges across overlaid distributions.
- Default bin count is 20 when not explicitly specified.
- Compute x-axis range from distribution statistics using global `[min(mean_i - 3*sigma_i), max(mean_i + 3*sigma_i)]`.
- Display per-bin statistical uncertainties for every plotted histogram.
- Keep normalization mode consistent within a figure (counts, density, or area-normalized).
- If normalized, scale uncertainties consistently after normalization.
- For overlays, include a ratio panel with shared x-axis.
- Ratio convention is `A_i / B`, where `B` is nominal (first distribution if not provided).
- Ratio y-range is fixed to `[0.5, 1.5]` with a horizontal reference line at `1.0`.
- Propagate ratio uncertainty as:
  - `sigma_R = R * sqrt((sigma_A/A)^2 + (sigma_B/B)^2)` (independent-statistics assumption).
- Handle edge cases safely:
  - If `B == 0`, mask/omit ratio bin.
  - If `A == 0` and `B != 0`, ratio is `0` with safe uncertainty handling.
- Include nominal-reference behavior in ratio panel (reference line/band around 1.0 with nominal uncertainty context).
- Rules are backend-agnostic (ROOT/matplotlib/mplhep/etc.).

## Layer 2 — Workflow Contract
### Required Artifacts
- 1D histogram figures with visible statistical uncertainties.
- Overlay figures with shared binning and ratio panels.
- Ratio panels with fixed `[0.5, 1.5]` y-range and `R=1` reference line.
- Plot metadata (or reproducible code path) showing binning and normalization choice.

### Acceptance Checks
- No fill-style histogram rendering unless explicitly requested.
- Overlays use identical bin edges.
- Default binning falls back to 20 if not otherwise set.
- X-axis range follows the statistical `mean ± 3 sigma` policy unless overridden.
- Every histogram includes visible error bars/uncertainty representation.
- Ratio panels are present for overlays and contain no NaN/Inf values.
- Division-by-zero bins are masked, not plotted as undefined values.
- Ratio uncertainty propagation uses the invariant formula above.
- Normalization and uncertainty scaling are internally consistent.

## Layer 3 — Example Implementation
### Uncertainty Rules
- Unweighted: `sigma_bin = sqrt(N_bin)`
- Weighted: `sigma_bin = sqrt(sum(w^2)_bin)`

### Ratio Rules
- `R = A / B`
- `sigma_R = R * sqrt((sigma_A/A)^2 + (sigma_B/B)^2)`
- If `B == 0`, do not compute ratio for that bin.

### Override Policy
- Any exception to these invariants must be explicitly requested by user instruction or required by non-1D-plot context.
