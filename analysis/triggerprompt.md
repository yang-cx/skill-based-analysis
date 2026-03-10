
Carry out the following data analysis (still blinded) and return a paper quality document with all the results


# Narrative Description of the Analysis

## Analysis Objective

This analysis measures the production of **W bosons produced in association with high-transverse-momentum jets (W+jets)** in proton–proton collisions. The goal is to study the behavior of the Standard Model in a kinematic regime where the jet transverse momentum is extremely large, providing sensitivity to QCD dynamics and testing the accuracy of theoretical predictions in boosted regimes. The signal process corresponds to **pp → W(ℓν) + jets**, where the W boson decays leptonically to either an electron or a muon and a neutrino. Because the neutrino escapes detection, the experimental signature consists of **one isolated charged lepton, missing transverse momentum, and energetic jets**.

---

## Signal Signature

The characteristic signal signature contains:

- Exactly **one isolated electron or muon**
- **Missing transverse energy (MET)** arising from the neutrino in the W decay
- **One or more high-pT jets**, with at least one jet having extremely large transverse momentum

The analysis targets events where the W boson is produced together with a very energetic jet system, which probes regions of phase space sensitive to higher-order QCD effects and electroweak corrections.

---

## Object Definitions

### Leptons

Lepton candidates consist of **electrons or muons** reconstructed with the following criteria:

- Transverse momentum:  
  **pT > 10 GeV**
- Electron pseudorapidity acceptance:  
  **|η| < 1.37 or 1.52 < |η| < 2.47**
- Muon pseudorapidity acceptance:  
  **|η| < 2.4**

For event selection, the **leading lepton must have pT > 30 GeV** and must be matched to the trigger.

### Jets

Jets are reconstructed and selected using the following requirements:

- **Jet transverse momentum pT > 30 GeV**
- **Jet rapidity |y| < 2.5**

Events are required to contain **at least one jet with pT > 500 GeV**, ensuring the analysis focuses on the boosted regime.

Jets containing **b-hadrons are identified using the DL1r b-tagging algorithm**, and events containing b-tagged jets are rejected to suppress backgrounds from top-quark production.

### Missing Transverse Momentum

The **missing transverse momentum (MET)** is calculated as the negative vector sum of the transverse momenta of all reconstructed physics objects (electrons, muons, jets, photons) together with a soft term constructed from tracks not associated with these objects.

### Overlap Removal

An overlap-removal procedure ensures that reconstructed objects are uniquely assigned:

- Jets near electrons may be removed
- Electrons close to jets may be removed
- Muons near jets are removed

This avoids double counting of detector signals.

---

## Event Selection

Events must satisfy the following baseline selection:

- Exactly **one lepton (electron or muon)**
- Leading lepton **pT > 30 GeV**
- Lepton matched to trigger
- **At least one jet with pT > 500 GeV**
- **ΔR(lepton, jet) > 0.4**
- **No additional leptons**
- **b-jet veto**

This selection defines the **inclusive signal region baseline**.

---

## Signal Regions

The analysis defines several **signal regions** based on jet multiplicity and the geometric relationship between the lepton and jets.

### Inclusive Region

The **inclusive region** includes all events satisfying the baseline event selection described above.

### Inclusive-2-Jet Region

This region targets events with additional jet activity:

- All inclusive requirements
- **At least two jets**

### Collinear Region

This region targets events where the W boson and the jet system are relatively aligned.

Additional requirement:

- Minimum angular separation between the lepton and a jet with pT > 100 GeV:


input data are in input-data. there are directories for data and MC. analysis/ATLAS_2024_Wplus_high_pT_jets.analysis.json is a reference. but our analysis only has 36 fb-1 integrated luminosity