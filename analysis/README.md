# Analysis Package README

This package implements a config-driven diphoton analysis pipeline under `analysis/`.
It is designed to be usable by both human analysts and coding agents.

## Reusability Assessment

Short answer: **yes, reusable**, with clear caveats.

Reusable strengths:
- Modular stage layout (`config`, `samples`, `io`, `objects`, `selections`, `hists`, `stats`, `plotting`, `report`)
- CLI entrypoints for each stage and one end-to-end orchestrator (`analysis.cli run`)
- Structured JSON/NPZ outputs for automation and auditing
- Deterministic run metadata (`config_hash`, timestamp, git commit when available)

Current caveats:
- Object model currently focuses on diphoton variables (photon branches and derived `m_gg` observables)
- Region expression engine uses Python `eval` over event columns (safe only in trusted workflows)
- Sample kind inference (`signal/background`) uses filename/process heuristics
- Statistical model is simplified (normalization factors, minimal nuisance treatment)

## Package Architecture

Top-level modules:
- `analysis/config`: summary loading + schema/cross-reference checks
- `analysis/samples`: sample registry + normalization + per-event weight construction
- `analysis/samples/strategy.py`: signal/background classification and CR->SR normalization strategy
- `analysis/io`: ROOT reading (uproot) + parquet caching helpers
- `analysis/objects`: derived physics objects/columns (currently photon-centric)
- `analysis/selections`: region DSL evaluation, masks, cut flow
- `analysis/hists`: template histogram production (`.npz`)
- `analysis/stats`: workspace building + pyhf fit
- `analysis/plotting`: verification/final plots required by skill 13
- `analysis/plotting/blinded_regions.py`: CR-only normalization fit and SR-blinded region plots
- `analysis/report`: narrative report generation
- `analysis/cli.py`: orchestrates full pipeline

Execution flow:
1. Validate and normalize summary JSON
2. Build sample registry from `input-data/{data,MC}`
3. Derive signal/background strategy and CR->SR normalization constraints
4. Load ROOT events and build derived diphoton columns
5. Evaluate regions from `analysis/regions.yaml`
6. Produce cut flows, yields, templates
7. Build workspace, run fit
8. Generate plots and report

## Input Contracts

Required inputs:
- Summary JSON: `analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json`
- Categories YAML: `analysis/categories.yaml`
- Executable regions: `analysis/regions.yaml`
- Data/MC ROOT files: `input-data/data/*.root`, `input-data/MC/*.root`

Important:
- Every active region in `analysis/regions.yaml` must have executable selections.
- If a desired observable is unavailable in ROOT branches, substitute with a closest available one and document it in the report.

## Output Contracts

Pipeline writes under `outputs/`:
- `cutflows/*.json`
- `yields/*.json`
- `hists/<region>/<observable>/<sample>.npz`
- `fit/<fit_id>/results.json`
- `fit/<fit_id>/significance.json`
- `background_modeling_strategy.json`
- `samples.classification.json`
- `cr_sr_constraint_map.json`
- `report/partition_spec.json`
- `report/partition_checks.json`
- `manifest/partitions.json`
- `fit/<fit_id>/blinded_cr_fit.json`
- `report/blinding_summary.json`
- `report/plots/blinded_region_<region_id>.png`
- `report/report.md`
- `report/plots/*.png`
- `inventory/*.json`
- `runs/<timestamp>/run_manifest.json`

## Environment Setup

```bash
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install numpy pyyaml uproot awkward pyarrow pandas matplotlib pyhf pydantic pytest
```

## CLI Usage

### 1) Stage-by-stage commands

Validate summary:
```bash
python -m analysis.config.load_summary \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --out outputs/summary.normalized.json
```

Build sample registry:
```bash
python -m analysis.samples.registry \
  --inputs input-data \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --out outputs/samples.registry.json
```

Derive signal/background strategy and CR->SR constraints:
```bash
python -m analysis.samples.strategy \
  --registry outputs/samples.registry.json \
  --regions analysis/regions.yaml \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --out outputs/background_modeling_strategy.json
```

Build category x region partitions:
```bash
python -m analysis.partitioning.build_partitions \
  --categories analysis/categories.yaml \
  --regions analysis/regions.yaml \
  --out-spec outputs/report/partition_spec.json \
  --out-manifest outputs/manifest/partitions.json \
  --out-checks outputs/report/partition_checks.json
```

Read one sample to parquet cache:
```bash
python -m analysis.io.readers \
  --registry outputs/samples.registry.json \
  --sample 302521 \
  --max-events 10000 \
  --out outputs/cache/302521.parquet
```

Build photon/diphoton derived columns:
```bash
python -m analysis.objects.photons \
  --sample 302521 \
  --registry outputs/samples.registry.json \
  --regions analysis/regions.yaml \
  --max-events 10000 \
  --out outputs/cache/302521.objects.parquet
```

Compute region yields for one sample:
```bash
python -m analysis.selections.regions \
  --sample 302521 \
  --registry outputs/samples.registry.json \
  --regions analysis/regions.yaml \
  --max-events 10000 \
  --out outputs/regions/302521.regions.json
```

Compute cut flow for one sample:
```bash
python -m analysis.selections.engine \
  --sample 302521 \
  --registry outputs/samples.registry.json \
  --regions analysis/regions.yaml \
  --max-events 10000 \
  --cutflow \
  --out outputs/cutflows/302521.json
```

Produce templates:
```bash
python -m analysis.hists.histmaker \
  --sample 302521 \
  --registry outputs/samples.registry.json \
  --regions analysis/regions.yaml \
  --summary outputs/summary.normalized.json \
  --max-events 10000 \
  --out outputs/hists
```

Build workspace:
```bash
python -m analysis.stats.pyhf_workspace \
  --summary outputs/summary.normalized.json \
  --hists outputs/hists \
  --systematics outputs/systematics.json \
  --registry outputs/samples.registry.json \
  --out outputs/fit/workspace.json
```

Run fit:
```bash
python -m analysis.stats.fit \
  --workspace outputs/fit/workspace.json \
  --fit-id FIT_MAIN \
  --out outputs/fit/FIT_MAIN/results.json
```

Compute discovery significance:
```bash
python -m analysis.stats.significance \
  --workspace outputs/fit/workspace.json \
  --fit-id FIT_MAIN \
  --out outputs/fit/FIT_MAIN/significance.json
```

Generate plots:
```bash
python -m analysis.plotting.plots \
  --outputs outputs \
  --registry outputs/samples.registry.json
```

Generate blinded CR/SR region plots:
```bash
python -m analysis.plotting.blinded_regions \
  --outputs outputs \
  --registry outputs/samples.registry.json \
  --regions analysis/regions.yaml \
  --fit-id FIT_MAIN
```

Generate report:
```bash
python -m analysis.report.make_report \
  --summary outputs/summary.normalized.json \
  --outputs outputs \
  --out outputs/report/report.md
```

### 2) End-to-end orchestrator

Help:
```bash
python -m analysis.cli --help
```

Mini run (default sample subset: one data + one background + one signal):
```bash
python -m analysis.cli run \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --categories analysis/categories.yaml \
  --inputs input-data \
  --outputs outputs \
  --max-events 20000
```

Full registry run:
```bash
python -m analysis.cli run \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --categories analysis/categories.yaml \
  --inputs input-data \
  --outputs outputs \
  --all-samples \
  --max-events 2000
```

Targeted sample list:
```bash
python -m analysis.cli run \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --categories analysis/categories.yaml \
  --inputs input-data \
  --outputs outputs \
  --samples 302521 343981 ODEO_FEB2025_v0_GamGam_data15_periodD.GamGam \
  --max-events 50000
```

Optional runtime backend selection (additive, non-replacing):
```bash
python -m analysis.cli run \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --categories analysis/categories.yaml \
  --inputs input-data \
  --outputs outputs_auto \
  --event-backend auto
```

Optional PyHF implementation selection (additive, non-replacing):
```bash
python -m analysis.cli run \
  --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json \
  --categories analysis/categories.yaml \
  --inputs input-data \
  --outputs outputs_pyhf_auto \
  --fit-backend pyhf \
  --pyhf-backend auto
```

Parity check between two output directories (native vs rootmltool/auto):
```bash
python -m analysis.cli parity-check \
  --baseline outputs_native \
  --candidate outputs_auto \
  --out outputs_auto/report/parity_native_vs_auto.json \
  --fail-on-mismatch
```

## For Agents (Automation Playbook)

Recommended agent behavior:
1. Run `analysis.config.load_summary` and fail on cross-reference errors.
2. Build `samples.registry.json` and verify at least one `data` and one `MC` sample exist.
3. Ensure every active region selection in `analysis/regions.yaml` is executable.
4. Run `analysis.cli run` with explicit `--max-events` and either `--all-samples` or `--samples`.
5. Verify required artifacts exist before declaring completion:
   - `outputs/cutflows/*.json`
   - `outputs/yields/*.json`
   - `outputs/hists/**/*.npz`
   - `outputs/fit/*/results.json`
   - `outputs/fit/*/significance.json`
   - `outputs/report/report.md`
   - required plot files in `outputs/report/plots/`

## For Human Scientists

Typical workflow:
1. Start with a mini run for rapid iteration.
2. Inspect:
   - `outputs/inventory/*.json` (branch and file inventory)
   - `outputs/yields/*.json` and `outputs/cutflows/*.json`
   - `outputs/report/plots/*`
3. Tune object thresholds or region definitions in `analysis/regions.yaml`.
4. Re-run all samples for production.
5. Review `outputs/report/report.md` and fit diagnostics in `outputs/fit/*`.

## Extension Points

Common modifications for new analyses:
- New objects/features: add builders under `analysis/objects/`.
- Additional derived columns: extend `analysis.objects.photons.build_photons` or add modules.
- Region logic: edit `analysis/regions.yaml` selections and cutflow steps.
- Weight model: modify `analysis/samples/weights.py`.
- Improved statistical model/systematics: extend `analysis/stats/pyhf_workspace.py`.
- Custom reports: extend `analysis/report/make_report.py`.

## Known Limitations and Next Improvements

- Selection DSL currently relies on Python expression evaluation.
- Systematics are simplified and should be expanded for publication-grade results.
- Signal/background inference should ideally come from explicit metadata mapping, not string heuristics.
- Current plotting/reporting is tuned to diphoton validation and can be generalized further.

## Quick Validation Checklist

```bash
python -m analysis.cli --help
python -m analysis.config.load_summary --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json --out outputs/summary.normalized.json
python -m analysis.samples.registry --inputs input-data --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json --out outputs/samples.registry.json
python -m analysis.cli run --summary analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json --inputs input-data --outputs outputs --max-events 20000
```

If these pass and required outputs exist, the package is operational.
