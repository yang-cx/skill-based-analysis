# 13 TeV 2025 Data — Beta

In 2025 a updated and increased set of proton-proton (pp) collision data was released by the ATLAS Collaboration to the public for educational purposes. The data has been collected by the ATLAS detector at the LHC at 13 TeV during the year 2015 and 2016 and corresponds to an integrated luminosity of 36 fb<sup>-1</sup>. The pp collision data is accompanied by a set of MC simulated samples describing several processes which are used to model the expected distributions of different signal and background events.

<div class="centered-button-container">
  <a href="https://opendata.cern/record/93910" class="download-vm-button" target="_blank">Explore the 13 TeV Data for Education</a>
</div>

The released samples are provided in a simplified data format, reducing the information content of the data released as [open data for research](/docs/data/for_research/pp_data) in 2024. The easiest way to access all the data is through the [atlasopenmagic package](/docs/atlasopenmagic).

The resulting format is a [ROOT](https://root.cern.ch/) tuple with about 80 branches (variables/features). For those not familiar with this modular scientific software toolkit, please refer to the [ROOT documentation](https://root.cern.ch/documentation), which provides a rich set of tutorials and code examples. 

Several final-state collections are provided within this release specifically tailored towards the example notebooks provided [here](/docs/documentation/example_analyses/analysis_examples_education_2020). The selections applied to select events and the corresponding name of each collection are shown below:


| Selection                     | Collection Name|
|:------------------------------------------:|:-------------------------------:|
| At least one lepton with at least $7~$GeV of $p_{T}$ and $30~$GeV of missing transverse momentum (i.e. a leptonically-decaying W-boson enhanced selection)     | 1LMET30 |          
| Two to four leptons with at least $7~$GeV of $p_{T}$ each                                                                                                     | 2to4lep |        
| At least two muons with at least $10~$GeV of $p_{T}$ (i.e. a leptonically-decaying Z-boson enhanced selection)                                                 | 2muons  |       
| At least three jets with at least $20~$GeV of $p_{T}$, at least one lepton passing tight identification requirements with at least $7~$GeV of $p_{T}$, and $30~$GeV of missing transverse momentum (i.e. a semi-leptonic top-quark enhanced selection) | 3J1LMET30 |
| At least two photons with at least $25~$GeV of $p_{T}$ each (i.e. a Higgs boson decaying to two photons enhanced selection) | GamGam  |
| At least two jets with at least $20~$GeV of $p_{T}$, at least two leptons passing tight identification requirements with at least $7~$GeV of $p_{T}$, and $30~$GeV of missing transverse momentum (i.e. a di-leptonic top-quark enhanced selection)   | 2J2LMET30 |
| At least two jets with at least $20~$GeV of $p_{T}$ identified as containing at least one heavy flavor hadron using the $70\%$ working point (i.e. a Higgs boson decaying to b-quarks enhanced selection)                         | 2bjets |
| At least three leptons with at least $7~$GeV of $p_{T}$ each                       | 3lep |
| Exactly three leptons with at least $7~$GeV of $p_{T}$ (i.e. a leptonically-decaying W+Z boson enhanced selection)           | exactly3lep |
| At least four leptons with at least $7~$GeV of $p_{T}$ each                       | 4lep |
| Exactly four leptons with at least $7~$GeV of $p_{T}$ (i.e. a leptonically-decaying ZZ boson or Higgs to four leptons enhanced selection)            | exactly4lep |


## Reconstructed physics objects
Several reconstructed physics objects (electrons, muons, photons, tau-leptons, small-R jets, large-R jets) are contained within the 13 TeV ATLAS Open Data, and their preselection requirements are detailed below:


|Electron (e)             | Muon ($\mu$)           | Photon ($\gamma$)     |
|:-----------------------:|:----------------------:|:---------------------:|
| InDet & EMCAL rec.      | InDet & MS rec.        | InDet & EMCAL rec.    |
| $p_T > 7$ GeV           | $p_T > 7$ GeV          | $E_T > 25$ GeV        |
| $\|\eta\|< 2.47$        | $\|\eta\| < 2.5$       | $\|\eta\| < 2.37$     |

<br/>

| $\tau$-leptons | Small-R jets                        | Large-R jets                       |
|:-----------------------------------------------:|:----------------------:|:-----------------------------------------------:|
| InDet & EMCAL rec.                              | EMCAL & HCAL rec.      | EMCAL & HCAL rec.                               |
| $p_T > 20 $ GeV                                 | anti-kt, R = 0.4       | anti-kt, R = 1.0                                |
| $\|\eta\| < 2.5$                                | $ p_T > 20 $ GeV       | $ p_T > 250 $ GeV                               |
|                                                 | $ \|\eta\| < 2.5 $     | $ \|\eta\| < 2.0 $                              |
|                                                 | b-tagging (DL1dv01)    | trimming: $ R_{sub} = 0.2 $, $ f_{cut} = 0.05 $ |
<br/>

## Variable list

The full list of ROOT branches (variables/features) contained within in this dataset is presented in the list below:

| Variable Name                     | C++ type| Description
|-------------------|------|-------------|
| `num_events` | `double` |  number of originally number of simulated events, neglecting the event weights |
| `sum_of_weights` | `double` |  the square root of the sum of the event weights |
| `sum_of_weights_squared` | `double` |  the square root of the sum of the square of the event weights  |
| `runNumber` | `unsigned int` |  run identifier |
| `eventNumber` | `unsigned long long` |  event identifier |
| `channelNumber` | `unsigned int` |  simulated data dataset ID e.g. $gg \rightarrow H \rightarrow ZZ^* \rightarrow e^+e^-e^+e^-$ is 345060  |
| `mcWeight` | `float` |  weight of a simulated event |
| `filteff` | `float` | efficiency of simulated process, e.g. if Higgs is forced to decay into two tau leptons in the simulated sample the filter efficiency reflects this |
| `kfac` | `float` | corrections to the cross section due to higher order calculations |
| `xsec` | `float` | the cross section in picobarn of the simulated process |
| `ScaleFactor_PILEUP` | `float` |  scalefactor for pileup reweighting |
| `ScaleFactor_ELE` | `float` |  scalefactor for electron efficiency |
| `ScaleFactor_MUON` | `float` |  scalefactor for muon efficiency |
| `ScaleFactor_PHOTON` | `float` |  scalefactor for photon efficiency  |
| `ScaleFactor_TAU` | `float` |  scalefactor for tau efficiency |
| `ScaleFactor_BTAG` | `float` |  scalefactor for b-tagging algorithm using continous working point |
| `ScaleFactor_LepTRIGGER` | `float` |  scalefactor for different operating efficiencies of used lepton triggers |
| `ScaleFactor_TauTRIGGER` | `float` |  scalefactor for different operating efficiencies of used tau triggers |
| `ScaleFactor_DiTauTRIGGER` | `float` |  scalefactor for different operating efficiencies of used ditau triggers |
| `ScaleFactor_ElTRIGGER` | `Float_t` | scalefactor for different operating efficiencies of used single electron triggers | 
| `ScaleFactor_FTAG` | `Float_t` | scalefactor for b-tagging algorithm using continous working point | 
| `ScaleFactor_JVT` | `Float_t` | scalefactor for jet vertex tagger (JVT) algorithm using the neural net (NN) working point| 
| `ScaleFactor_MLTRIGGER` | `Float_t` | scalefactor for different operating efficiencies of used multilepton triggers | 
| `ScaleFactor_MuTRIGGER` | `Float_t` | scalefactor for different operating efficiencies of used single muon triggers | 
| `TriggerMatch_DILEPTON` | `Float_t` | scalefactor for different operating efficiencies of used di-lepton triggers| 
| `trigDE` |  `bool` | boolean whether the event has been selected by any of the di-electron triggers |
| `trigDM` |  `bool` | boolean whether the event has been selected by any of the di-muon triggers |
| `trigMET` |  `bool` | boolean whether the event has been selected by any of the missing transverse energy triggers |
| `trigML` |  `bool` | boolean whether the event has been selected by any of the multi-lepton triggers |
| `trigE` | `bool` |  boolean whether the event has been selected by any of the single electron triggers |
| `trigM` | `bool` |  boolean whether the event has been selected by any of the single muon triggers |
| `trigP` | `bool` |  boolean whether the event has been selected by any of the single photon triggers |
| `trigT` | `bool` |  boolean whether the event has been selected by any of the single tau triggers |
| `trigDT` | `bool` |  boolean whether the event has been selected by any of the di-tau triggers |
| `lep_n` | `int` |  number of preselected leptons |
| `lep_isTrigMatched` | `vector<bool>` |  boolean signifying whether the lepton is triggering the event |
| `lep_pt` | `vector<float>` |  transverse momentum of the lepton |
| `lep_eta` | `vector<float>` |  pseudo-rapidity of the lepton |
| `lep_phi` | `vector<float>` |  azimuthal angle of the lepton |
| `lep_e` | `vector<float>` |  energy of the lepton |
| `lep_z0` | `vector<float>` |  z-coordinate of the track associated to the lepton wrt. primary vertex |
| `lep_d0` | `vector<float>` |  transverse coordinate (in the xy-plane) of the track associated to the lepton wrt. primary vertex |
| `lep_d0sig` | `vector<float>` |  $d_0$ divided by the uncertainty of the $d_0$ measurement |
| `lep_charge` | `vector<int>` |  charge of the lepton |
| `lep_type` | `vector<int>` |  number signifying the lepton type (e (11) or mu (13)) |
| `lep_isLooseID` | `vector<bool>` | boolean indicating whether lepton satisfies loose ID reconstruction criteria |
| `lep_isMediumID` | `vector<bool>` | boolean indicating whether lepton satisfies medium ID reconstruction criteria |
| `lep_isTightID` | `vector<bool>` | boolean indicating whether lepton satisfies tight ID reconstruction criteria |
| `lep_isLooseIso` | `vector<bool>` | boolean indicating whether lepton satisfies loose isolation criteria |
| `lep_isTightIso` | `vector<bool>` | boolean indicating whether lepton satisfies tight isolation criteria |
| `lep_ptvarcone30` | `vector<float>` |  scalar sum of track $p_T$ in a variable sized cone with $\Delta R_{max}=0.3$ around the lepton |
| `lep_topoetcone20` | `vector<float>` |  scalar sum of calorimeter $E_T$ in a cone of $\Delta R=0.2$ around lepton |
| `tau_n` | `int` |  number of preselected tau leptons |
| `tau_pt` | `vector<float>` |  transverse momentum of the tau lepton |
| `tau_eta` | `vector<float>` |  pseudo-rapidity of the tau lepton |
| `tau_phi` | `vector<float>` |  azimuthal angle of the tau lepton |
| `tau_e` | `vector<float>` |  energy of the tau lepton |
| `tau_charge` | `vector<int>` |  charge of the tau lepton |
| `tau_isTight` | `vector<bool>` |  boolean indicating whether tau lepton satisfies tight ID reconstruction criteria |
| `tau_nTracks` | `vector<int>` | number of core tracks for reconstructed tau lepton (either 1 or 3)  |
| `tau_RNNEleScore` | `vector<float>` | RNN electron score to identify leptonically decaying taus |
| `tau_RNNJetScore` | `vector<float>` | RNN jet score to identify hadronically decaying taus  |
| `photon_n` | `int` |  number of preselected photons |
| `photon_pt` | `vector<float>` |  transverse momentum of the photon |
| `photon_eta` | `vector<float>` |  pseudo-rapidity of the photon |
| `photon_phi` | `vector<float>` |  azimuthal angle of the photon |
| `photon_e` | `vector<float>` |  energy of the photon |
| `photon_ptcone20` | `vector<float>` |  scalar sum of track $p_T$ in a cone of R=0.2 around photon |
| `photon_topoetcone40` | `vector<float>` |  scalar sum of track $E_T$ in a cone of R=0.4 around photon |
| `photon_isLooseID` | `vector<bool>` | boolean indicating whether photon satisfies loose ID reconstruction criteria |
| `photon_isTightID` | `vector<bool>` | boolean indicating whether photon satisfies tight ID reconstruction criteria |
| `photon_isLooseIso` | `vector<bool>` | boolean indicating whether photon satisfies loose isolation criteria |
| `photon_isTightIso` | `vector<bool>` | boolean indicating whether photon satisfies tight isolation criteria |
| `met` | `float` |  transverse energy of the missing momentum vector |
| `met_phi` | `float` |  azimuthal angle of the missing momentum vector |
| `met_mpx` | `float` |  x-component of the missing momentum vector |
| `met_mpy` | `float` |  y-component of the missing momentum vector |
| `jet_n` | `int` |  number of preselected jets |
| `jet_pt` | `vector<float>` |  transverse momentum of the jet |
| `jet_eta` | `vector<float>` |  pseudo-rapidity of the jet |
| `jet_phi` | `vector<float>` |  azimuthal angle of the jet |
| `jet_e` | `vector<float>` |  energy of the jet |
| `jet_jvt` | `vector<float>` |  jet vertex tagging of the jet |
| `jet_btag_quantile` | `vector<int>` |  the quantile of the continous working point of the DL1dv0 b-jet tagger |
| `jet_pt_jer1` | `vector<float>` |  transverse momentum of the jet after applying a specific systematic uncertainty from the jet energy resolution calibration |
| `jet_pt_jer2` | `vector<float>` |  transverse momentum of the jet after applying a specific systematic uncertainty from the jet energy resolution calibration |
| `largeRJet_n` | `int` |  number of preselected jets |
| `largeRJet_pt` | `vector<float>` |  transverse momentum of the large radius jet |
| `largeRJet_eta` | `vector<float>` |  pseudo-rapidity of the large radius jet |
| `largeRJet_phi` | `vector<float>` |  azimuthal angle of the large radius jet |
| `largeRJet_e` | `vector<float>` |  energy of the large radius jet |
| `largeRJet_m` | `vector<float>` |  mass of the large radius jet |
| `largeRJet_D2` | `vector<float>` |  variable to identify jets from hadronic Z-boson decays ([JHEP12(2014)009](https://link.springer.com/article/10.1007/JHEP12(2014)009)) |
| `truth_elec_eta` | `vector<float>` | pseudo-rapidity of the truth electrons  |
| `truth_elec_n`   | `Int_t`         | number of truth electrons  |
| `truth_elec_phi` | `vector<float>` | azimuthal angle of the truth electrons  |
| `truth_elec_pt`  | `vector<float>` | transverse momentum of the truth electrons  |
| `truth_jet_eta`  | `vector<float>` | pseudo-rapidity of the truth jets  |
| `truth_jet_m`    | `vector<float>` | mass of the truth jets  |
| `truth_jet_n`    | `Int_t`         | number of truth jets  |
| `truth_jet_phi`  | `vector<float>` | azimuthal angle of the truth jets  |
| `truth_jet_pt`   | `vector<float>` | transverse momentum of the truth jets  |
| `truth_met`      | `Float_t`       | truth missing transverse energy  |
| `truth_met_phi`  | `Float_t`       | azimuthal angle of the truth missing transverse energy  |
| `truth_muon_eta` | `vector<float>` | pseudo-rapidity of the truth muon  |
| `truth_muon_n`   | `Int_t`         | number of truth muons  |
| `truth_muon_phi` | `vector<float>` | azimuthal angle of the truth muons  |
| `truth_muon_pt`  | `vector<float>` | transverse momentum of the truth muons  |
| `truth_photon_eta` | `vector<float>` | pseudo-rapidity of the truth photons       |
| `truth_photon_n`   | `Int_t`         | number of truth photons                    |
| `truth_photon_phi` | `vector<float>` | azimuthal angle of the truth photons        |
| `truth_photon_pt`  | `vector<float>` | transverse momentum of the truth photons   |
| `truth_tau_eta`    | `vector<float>` | pseudo-rapidity of the truth taus         |
| `truth_tau_n`      | `Int_t`         | number of truth taus                      |
| `truth_tau_phi`    | `vector<float>` | azimuthal angle of the truth taus         |
| `truth_tau_pt`     | `vector<float>` | transverse momentum of the truth taus     |
