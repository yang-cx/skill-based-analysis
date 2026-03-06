You are a Codex analysis agent working inside this repository:

~/disk/skill-based-analysis

Follow below instruction to complete a Higgs to diphoton search using the 36 fb-1 atlas open data samples(including data and MC)

What is available
- Skills pack: skills/*.md (start with skills/00_INDEX.md and follow all skill contracts)
- Example placeholder region selections: analysis/regions.yaml
- Structured analysis summary (authoritative reproduction target): analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json
- Input ROOT ntuples (symlinks to open data): input-data/data and input-data/MC
- Repo docs: README.md


Hard constraints
- Do NOT quote or copy raw text from analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json verbatim in the final report.
- You MUST use analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json as the primary implementation target and
  implement the analysis to closely reproduce it with available open-data observables.
- Photon identification and isolation variables may differ from the reference analysis era. You must inspect the
  actual branches present in the ROOT ntuples and determine the closest usable equivalents.
- If anything in analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json is inconsistent with what is available
  in the open data samples (missing variables, different definitions, unavailable observables, etc.), you are allowed
  to substitute the closest feasible replacement that exists in the dataset.

Compatibility rule
- Any substitutions or approximations must be explicitly documented.
- The justification must be written in a dedicated section of the final report titled:

  "Implementation Differences from Reference Analysis"

- For each substitution include:
  - the reference concept (without quoting the JSON)
  - the observable available in the open data
  - the reasoning for the replacement
  - the expected impact on the analysis if relevant

Mission
Complete the analysis. Implement and execute an end-to-end diphoton analysis pipeline from input-data/ to outputs/, fully reproducible and CLI-driven,
guided by the skills pack and analysis/ATLAS_2012_H_to_gammagamma_discovery.analysis.json as the reference target.
analysis/regions.yaml is a placeholder example and should be updated/replaced as needed to achieve close reproduction.
Run this over all samples.

Definition of done:

The analysis must be completed. All data is processed, expected discovery signficance shall be determined, a paper like report is written. 
