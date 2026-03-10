---
skill_type: procedure
domain: hep_analysis
stage: bootstrap
original_id: "01"
original_filename: "01_BOOTSTRAP_REPO.md"
---

# Skill: Bootstrap Repo

## Layer 1 — Physics Policy
The analysis software foundation must support faithful propagation of physics intent from configuration to results.

Policy requirements:
- Separate analysis logic into clear stages so each physics decision is traceable.
- Keep infrastructure generic enough to support multiple channels and observables.
- Ensure the end-to-end pipeline can be rerun reproducibly.
- Avoid embedding analysis-specific thresholds directly in infrastructure code.
- If required pipeline modules or useful tooling are missing but buildable in-repository, construct/restore them as part of execution rather than stopping with placeholder-only artifacts.
- Keep PyROOT dependencies isolated and available as a first-class requirement for H->gammagamma resonance-fit workflows.
- Keep ROOT event-ingestion dependencies centered on `uproot` for event processing.

## Layer 2 — Workflow Contract
### Required Artifacts
- analysis package scaffold artifact with stage-oriented modules
- stage entrypoint artifact enabling each stage to run independently
- end-to-end orchestrator artifact that executes all stages consistently
- minimal test artifact that verifies package integrity
- runtime-recovery artifact documenting constructed/restored pipeline modules and tooling when initial runtime capability was missing

### Acceptance Checks
- stage entrypoints are executable
- orchestrator entrypoint is discoverable and runnable
- at least one validation stage executes from the orchestrator
- tests can be invoked and report pass/fail status
- if the repository initially lacked a functioning pipeline/tooling, bootstrap produces a runnable replacement path for required stages before handoff
- bootstrapped event-ingestion path supports ROOT processing through `uproot`
- H->gammagamma production pipeline is runnable with required PyROOT/RooFit backend support; non-resonance paths may remain runnable without PyROOT

## Layer 3 — Example Implementation
### Required Structure (Current Repository)
```text
analysis/
  __init__.py
  cli.py
  config/
    __init__.py
    summary_schema.py
    load_summary.py
  samples/
    __init__.py
    registry.py
    weights.py
  io/
    __init__.py
    readers.py
    columnar.py
  objects/
    __init__.py
    photons.py
    jets.py
    leptons.py
  selections/
    __init__.py
    engine.py
    regions.py
  hists/
    __init__.py
    histmaker.py
  stats/
    __init__.py
    pyhf_workspace.py
    fit.py
  plotting/
    __init__.py
    plots.py
  report/
    __init__.py
    make_report.py
tests/
analysis/analysis.summary.json
analysis/regions.yaml
outputs/  (gitignored)
```

### CLI Convention (Current Repository)
- `python -m analysis.config.load_summary --summary analysis/analysis.summary.json`
- `python -m analysis.samples.registry --inputs inputs/ --summary analysis/analysis.summary.json`
- `python -m analysis.selections.regions --regions analysis/regions.yaml ...`
- `python -m analysis.cli run --summary ... --inputs ... --outputs ...`

### Acceptance Commands (Current Repository)
- `python -m analysis.cli --help`
- `python -m analysis.config.load_summary --summary analysis/analysis.summary.json`
- `pytest -q`
