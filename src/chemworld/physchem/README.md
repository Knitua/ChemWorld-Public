# ChemWorld PhysChem Core

This package contains compact physical-chemistry primitives used by ChemWorld
world-law modules. It is not a vendor copy of Cantera, thermo, chemicals, or
other reference projects.

Current scope:

- element metadata for benchmark-relevant elements;
- formula parsing with element conservation support;
- molecular-weight and elemental-fraction utilities;
- JSON-friendly `ComponentSpec` with checksum-validated CAS, optional
  InChI/InChIKey, formula/charge/molecular-weight validation, provenance, and
  uncertainty metadata;
- versioned immutable `ComponentIdentityRegistry` with identifier/alias/CAS/
  InChI/InChIKey collision checks, canonical SHA-256, curated identities, and
  exact JSON readback;
- canonical semantic dimension catalog and exponent algebra covering process,
  thermodynamic, transport, electrochemical, spectroscopy/NMR/MS detector,
  cost, and risk quantities, plus strict field-unit contracts;
- deterministic source-ranked data conflict audits with scalar tolerance,
  required uncertainty, warning/hard-fail findings, source provenance,
  tamper-evident dataset cards, and trajectory dataset provenance;
- self-contained `MixtureSpec`;
- explicit-unit `PropertyCorrelation` records.
- local property evaluators for vapor pressure, heat capacity, enthalpy,
  phase-change enthalpy, density, viscosity, surface tension, mixture rules,
  and safety proxies.
- vapor-pressure reports with pressure, analytic `dP/dT`, `dlnP/dT`, validity
  status, method family, and reference-reading provenance for vapor or
  caller-supplied sublimation correlations.
- pure-fluid saturation reports with `T -> Psat`, bracketed `P -> Tsat`
  inversion, normal-boiling-point convenience calls, critical-region warnings,
  residual diagnostics, and reference-reading provenance.
- public property-equation contracts for required coefficients, input
  dimensions, output dimensions, and model cards.
- curated reference-checked property packages for water, ethanol, acetone,
  toluene, methane, and carbon dioxide using DIPPR101 vapor pressure and
  Poling ideal-gas heat-capacity correlations.
- general reaction-network specs for species, reactions, stoichiometric
  matrices, element-balance checks, YAML/JSON mechanism loading, rate-law
  evaluation, and deterministic batch ODE integration.
- Cantera-comparable irreversible and reversible first-order reaction ODE
  reference cases with analytical trajectory validation and a reaction
  kinetics model card.
- NASA7 thermochemistry for species Cp/H/S/G, Cantera-style YAML thermo
  parsing, segment-continuity diagnostics, reaction Delta H/S/G, equilibrium
  constants from species Gibbs energies, and a thermochemistry model card.
- thermochemistry-coupled reversible Arrhenius rates with explicit
  dimensionless-to-concentration equilibrium conversion and
  `k_reverse = k_forward / K_c` detailed balance.
- finite-difference kinetic sensitivity reports with normalized local response
  coefficients, uncertainty propagation summaries, and explanation rankings.
- a curated mechanism/scenario library with balanced mechanism files, task
  cards, default initial states, operating windows, qualitative behavior
  metadata, and a programmatic validation report.
- spectroscopy and chromatography signal synthesis for mechanism-linked HPLC,
  GC, UV-vis, IR, and NMR raw signals with peak overlap, calibration curves,
  baseline drift, detection limits, and replicate measurements.
- a Beer-Lambert UV-vis calibration slice with explicit path length, sample
  dilution, molar absorptivity, blank absorbance, LOD/LOQ, and model-card
  evidence.
- an HPLC/GC chromatography retention slice with dead time, retention factor,
  theoretical plates, baseline peak width, adjacent resolution, calibration
  uncertainty, and model-card evidence.
- an empirical chromatography method layer with HPLC organic-fraction and
  temperature sensitivity, GC van't Hoff retention, n-alkane retention-index
  interpolation, detector response calibration with LOD/LOQ, and asymmetric
  peak fronting/tailing flags.
- a first-order proton NMR evidence layer with provenance-tagged shift anchors,
  s/d/t/q/quint/dd/m multiplicity and J metadata, Pascal stick intensities,
  amount-weighted integration, solvent/reference correction, and overlap,
  second-order, exchangeable, and unresolved-multiplet warnings.
- a small-formula mass-spectrometry layer with natural-abundance H/C/N/O/F/
  Si/P/S/Cl/Br isotope convolution, nominal and probability-weighted exact-mass
  envelopes, curated fragment/neutral-loss metadata, and detector response RSD.
- mechanism-backed reactor kernels for batch, semi-batch, CSTR, and PFR
  calculations with material and energy ledgers.
- dynamic CSTR startup/shutdown flow programs with residence-time metadata,
  analytical wash-in/wash-out limits, and multiple-steady-state stability evidence.
- tubular PFR axial profiles with geometry consistency, Darcy-Weisbach pressure
  loss, distributed thermal boundaries, and analytical hydraulic/thermal checks.
- dynamic batch reactor heat-release/sampling slice with NASA7 reaction
  enthalpy coupling, step/linear jacket temperature programs, destructive
  sampling events, and material/energy ledger evidence.
- an exothermic CSTR multiple-steady-state reference case with analytical
  energy-balance roots, stability classification, and a reactor model card.
- local equation-of-state calculations for ideal gas, Peng-Robinson, and SRK
  states with compressibility roots, explicit root-selection policies,
  fugacity coefficients, residual enthalpy, residual entropy, residual Gibbs
  energy, and model-card evidence.
- phase-equilibrium utilities for ideal, Margules, Wilson, NRTL, and UNIQUAC
  activity coefficients, auditable UNIQUAC `phi/theta/tau` reports, Raoult
  K-values, isothermal flash, bubble/dew pressure, bubble/dew temperature
  reports backed by pure saturation reports, gamma-phi K-value reports, binary
  relative-volatility crossing diagnostics, Rachford-Rice diagnostics, and
  liquid-liquid extraction splits.
- a professional-candidate fixed-TP gamma-phi flash unit with iterated liquid
  composition, per-component vapor/liquid material ledgers, caller-supplied
  phase enthalpies, heat duty, convergence status, and explicit fugacity and
  Poynting-factor hooks.
- reaction-equilibrium and electrolyte utilities for mass-action reaction
  extents, van't Hoff equilibrium constants, fixed-TP ideal Gibbs minimization,
  weak-acid pH, water ion product, precipitation, charge balance, ionic
  strength, and solid solubility.
- electrochemical thermodynamics and charge accounting for Nernst equilibrium
  potentials, Butler-Volmer currents, Faraday charge-to-extent conversion,
  Faradaic efficiency, and electrical-work ledgers.
- a professional-candidate planar diffusion-layer current model with
  `i_lim=nFADC/delta`, surface depletion, finite-reservoir linear/exponential
  bulk depletion, kinetic/transport current caps, transition time, and
  useful-versus-side charge/current-efficiency ledgers.
- a deterministic potentiostatic/galvanostatic setpoint controller with
  versioned ramp/hold recipes, range/slew clipping, sampled traces, segment
  operation logs, canonical recipe/execution SHA-256, and exact replay checks.
- a Randles double-layer RC transient with potential/current step modes,
  terminal/interfacial potential, capacitive/Faradaic/total current traces,
  exact integrated charge ledgers, and startup/short-trace warnings.
- versioned electrochemical scenario cards with public redox/geometry/window/
  side-reaction metadata, private hidden-parameter ranges, salted split-aware
  generation, public digests, and direct reaction/ohmic/diffusion/RC bundles.
- downstream separation unit operations for multistage extraction,
  evaporation, VLE-coupled shortcut distillation, crystallization, filtration,
  drying, and purity/recovery/cost/risk scoring.
- a professional-candidate extraction-train model with intrinsic partition
  provenance, aqueous/organic activity corrections, fresh-solvent stages,
  aqueous wash sequences, mass-conserving entrainment, and stage-level
  recovery, purity, rejection, convergence, and balance reports.
- a professional-candidate cooling-crystallization model with a van't Hoff
  solubility curve, supersaturation history, power-law primary nucleation and
  growth, explicit seed mass, impurity occlusion, capped material transfer,
  and number-based D10/D50/D90/CV/fines CSD metadata.
- fluid-mechanics and heat-transfer kernels for Reynolds/Prandtl/Peclet/Nusselt
  numbers, explicit Nusselt branch metadata, Darcy friction factors, pipe
  pressure drop, pump work, mixing power, jacket heat transfer, counterflow heat
  exchangers with hot/cold duty-balance checks, packed-bed pressure drop, and
  homogeneous two-phase pressure-drop proxies.
- a reference-validated horizontal Lockhart-Martinelli/Chisholm separated-flow
  pressure-drop model exposing phase Reynolds numbers, original friction
  factors, single-phase anchors, Martinelli parameter, multiplier, Chisholm
  regime constant, and endpoint/microchannel validity warnings.
- a professional-candidate equipment heat-transfer ledger for jacket, coil,
  and shell surfaces with declared geometry corrections, time-evolving fouling,
  lumped sensible dynamics, boiling/condensation plateaus, phase-crossing
  warnings, and signed sensible/latent energy closure.
- a professional-candidate pressure/temperature safety envelope with relief
  set and MAWP thresholds, Arrhenius/Semenov runaway slope indicators, MTSR,
  projected time-to-limit, relief-load capacity, explicit risk/cost components,
  and Gym-ready constraint flags.
- versioned JSON equipment cards for vessels, pumps, mixers, condensers, heat
  exchangers, and columns with provenance-tagged ratings, shared unit-bearing
  min/max constraints, normalized margins, utilization, warning/hard severity,
  and deterministic feasibility reports.
- optional reference-backend validation helpers for locally comparing selected
  ChemWorld formulas against `chemicals`, `fluids`, and later heavier
  scientific backends without making them runtime dependencies.

Design rules:

- keep specs serializable with plain JSON types;
- fail early on unknown elements, invalid phases, invalid units, or invalid
  fractions;
- fail early on unsupported property equations, missing coefficients,
  unit-dimension mismatches, phase-incompatible mixtures, duplicate policy
  tags, and component-disallowed property correlations;
- keep property correlations separate from component identity;
- keep mechanism definitions separate from reactor and task logic;
- keep species thermochemistry separate from kinetic rate-law parameters except
  when a rate law explicitly declares a thermochemical equilibrium source;
- keep mechanism scenario cards as the bridge between physical mechanism,
  benchmark task semantics, initial conditions, and qualitative expectations;
- keep virtual instruments as observation kernels over species amounts and
  processed estimates, not as hidden-state dumps;
- keep reactor residence time, feed/outlet flow, and heat-transfer contracts
  explicit;
- keep EOS component critical properties, mixture parameters, phase-root
  selection, fugacity outputs, residual properties, and departure metadata
  inspectable;
- keep phase-equilibrium models explicit about activity assumptions,
  vapor-pressure inputs, partition coefficients, mass-balance errors, flash
  convergence, caller-supplied enthalpy data, and heat-duty sign conventions;
- keep reaction-equilibrium and electrolyte models explicit about fixed
  constraints, supplied Gibbs energies, activity proxies, charge balance, phase
  restrictions, saturation state, and nonnegative extents or species amounts;
- keep electrochemical models explicit about sign conventions, electron number,
  activities, measured/interfacial potential, ohmic drop, Faradaic charge,
  electrical work, and the absence of full-cell effects such as double-layer
  dynamics or mass-transfer limiting current unless those effects have their
  own validated slice;
- keep unit-operation results as named outlet streams plus cost, risk,
  heat-duty, solvent-loss, and material-balance ledgers;
- keep extraction models explicit about intrinsic versus composition-corrected
  distribution coefficients, fresh-phase staging, wash order, entrained phase
  volume, stage efficiency, and target loss during cleanup;
- keep crystallization models explicit about solubility provenance, thermal
  path, seed mass, kinetic parameters, supersaturation, impurity occlusion,
  crystal population basis, and whether the runtime task has adopted the model;
- keep transport/equipment calculations explicit about SI units, flow regime,
  pressure-drop components, heat-duty sign conventions, Nusselt-correlation
  validity limits, exchanger duty residuals, and equipment metadata;
- keep phase-aware heat transfer explicit about surface correction provenance,
  elapsed fouling time, saturation boundary, available phase inventory, and
  sensible-versus-latent duty signs;
- declare property units and validity ranges on every correlation;
- reject unbalanced reaction networks before simulation;
- add optional reference-backend comparisons only as skipped tests or adapters;
- do not copy source code from `reference_repos/`.
