"""Equilibrium-chemistry model cards for ChemWorld."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def equilibrium_chemistry_model_cards() -> tuple[ModelCard, ...]:
    """Return model cards for equilibrium-chemistry kernels."""

    return (
        ModelCard(
            model_id="fixed_tp_ideal_gibbs_minimization",
            module_id="equilibrium_chemistry",
            title="Fixed-TP Ideal Gibbs Minimization",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Small constrained Gibbs minimization slice for benchmark "
                "species sets with element, charge, phase, and nonnegativity constraints."
            ),
            equations=(
                "min_n G = sum_i n_i G_i^0 + R T sum_i n_i ln(x_i_phase)",
                "element constraints: A_element n = b_element",
                "charge constraint: z^T n = q_target",
                "phase restrictions: n_i = 0 for species in disallowed phases",
                "bounds: n_i >= 0",
                "diagnostics: element/charge residuals, bound violation, "
                "rank(A), degrees of freedom, and KKT-style stationarity "
                "residual on free species",
            ),
            assumptions=(
                "Fixed temperature and pressure.",
                "Ideal mixing within each non-solid phase.",
                "Pure condensed solid activities are treated as one.",
                "Species standard Gibbs energies are supplied by the caller.",
            ),
            validity_limits=(
                "Small benchmark systems with explicit species and phases.",
                "No thermodynamic database, activity-coefficient model, or phase stability search.",
                "No automatic species generation or redox/electron basis selection.",
            ),
            failure_modes=(
                "Unknown initial species, nonphysical amounts, duplicate species ids, "
                "or nonpositive T/P raise ValueError.",
                "Phase restrictions with nonzero disallowed initial species raise ValueError.",
                "If allowed species cannot carry a target element, the solver raises ValueError.",
                "Numerical nonconvergence is reported in the result metadata rather than hidden.",
                "KKT diagnostics are local checks for the SLSQP result; they do not prove "
                "global optimality for arbitrary nonideal or database-generated systems.",
            ),
            units={
                "amount": "mol",
                "standard_gibbs": "J/mol",
                "total_gibbs": "J",
                "temperature": "K",
                "pressure": "Pa",
                "charge": "mol charge equivalents",
            },
            reference_reading=(
                "reference_repos/reaktoro/Reaktoro/Equilibrium/EquilibriumSpecs.hpp",
                "reference_repos/reaktoro/Reaktoro/Equilibrium/SmartEquilibriumSolver.hpp",
                "reference_repos/cantera/doc/sphinx/userguide/python-tutorial.md "
                "chemical equilibrium section",
                "reference_repos/pycalphad/pycalphad/core/equilibrium.py",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="analytical-ideal-isomerization",
                    evidence_type="unit_tests",
                    description=(
                        "For A and B with identical element vectors, ideal Gibbs "
                        "minimization reproduces n_B/n_A = exp[-(G_B^0-G_A^0)/RT]."
                    ),
                    status="passing",
                    command_or_path="python -m pytest tests/test_equilibrium_chemistry.py",
                    tolerance="rel=1e-7",
                ),
                ValidationEvidence(
                    evidence_id="stoichiometric-water-formation",
                    evidence_type="unit_tests",
                    description=(
                        "A small H/O stoichiometric system forms H2O while preserving "
                        "element constraints and emitting rank, degree-of-freedom, "
                        "bound, and stationarity diagnostics."
                    ),
                    status="passing",
                    command_or_path="python -m pytest tests/test_equilibrium_chemistry.py",
                    tolerance="element residual < 1e-8 mol",
                ),
                ValidationEvidence(
                    evidence_id="solid-phase-charge-restriction",
                    evidence_type="unit_tests",
                    description=(
                        "A Na+/Cl-/NaCl(s) case checks phase restrictions, charge "
                        "balance, pure-condensed linear-term notes, and active-species "
                        "diagnostics."
                    ),
                    status="passing",
                    command_or_path="python -m pytest tests/test_equilibrium_chemistry.py",
                    tolerance="charge residual < 1e-8 equivalent mol",
                ),
            ),
            model_limit_notes=(
                "This is a ChemWorld-local professional slice, not a Reaktoro clone.",
                "Diagnostics harden the benchmark contract but do not replace rigorous "
                "database-backed speciation, phase selection, or multiphase Gibbs "
                "minimization.",
                "Database-backed aqueous speciation and CALPHAD phase selection "
                "remain future work.",
            ),
            intended_use=(
                "Small hidden equilibrium scenarios for local world-model learning.",
                "Auditable element/charge/phase-constrained equilibrium tasks.",
            ),
        ),
        ModelCard(
            model_id="aqueous_acid_base_ph_observation",
            module_id="equilibrium_chemistry",
            title="Aqueous Acid-Base pH Observation Slice",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Compact monoprotic acid/base equilibrium with charge balance, "
                "temperature-dependent water ion product, bounded Davies activity "
                "corrections, pH-meter style public observation, and sequential "
                "precipitation hooks."
            ),
            equations=(
                "Ka = [H+][A-] / [HA]",
                "Kw(T) = [H+][OH-] from compact tabulated interpolation",
                "electroneutrality: [H+] + strong cations = [OH-] + [A-] + strong anions",
                "log10(gamma_i) = -A z_i^2 (sqrt(I)/(1+sqrt(I)) - 0.3 I)",
                "pH observation: E_mV = -2.303 R T / F * (pH_measured - 7)",
                "precipitation hook: ion product is driven back to Ksp for binary salts",
            ),
            assumptions=(
                "Single monoprotic acid in water.",
                "Davies activities are used only within the declared dilute-ion domain.",
                "Strong ions are fully dissociated.",
                "pH-meter observation adds configurable normal pH noise and resolution rounding.",
                "Precipitation hooks are applied sequentially to declared binary salts.",
            ),
            validity_limits=(
                "Small aqueous benchmark cases.",
                "Davies applicability is limited to ionic strength <= 0.5 mol/kg.",
                "No buffer mixtures, polyprotic acids, complexation, or redox basis selection.",
                "Sequential precipitation hooks are deterministic and order-dependent.",
            ),
            failure_modes=(
                "Negative amounts, nonpositive volume, nonpositive Ksp, or invalid "
                "pH observation noise raise ValueError.",
                "pH bracketing failure raises ValueError instead of returning a "
                "hidden clipped state.",
            ),
            units={
                "amount": "mol",
                "volume": "L",
                "concentration": "mol/L",
                "pH": "dimensionless",
                "electrode_signal": "mV",
                "charge": "mol charge equivalents",
            },
            reference_reading=(
                "reference_repos/reaktoro/Reaktoro/Equilibrium/EquilibriumSpecs.hpp",
                "reference_repos/cantera/doc/sphinx/userguide/python-tutorial.md "
                "chemical equilibrium section",
                "standard analytical weak-acid and Ksp textbook balances",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="monoprotic-weak-acid-charge-balance",
                    evidence_type="unit_tests",
                    description=(
                        "A 0.1 mol/L weak acid returns the expected pH range, "
                        "low dissociation fraction, small charge-balance residual, "
                        "and a public pH observation without species leakage."
                    ),
                    status="passing",
                    command_or_path="python -m pytest tests/test_equilibrium_chemistry.py",
                    tolerance="pH within 0.05 and charge residual < 1e-10",
                ),
                ValidationEvidence(
                    evidence_id="sequential-ksp-hooks",
                    evidence_type="unit_tests",
                    description=(
                        "AgCl and BaSO4 hooks precipitate supersaturated binary "
                        "salts while preserving material balance in a compact ledger."
                    ),
                    status="passing",
                    command_or_path="python -m pytest tests/test_equilibrium_chemistry.py",
                    tolerance="material balance error < 1e-12 mol",
                ),
                ValidationEvidence(
                    evidence_id="electrolyte-davies-runtime-coupling",
                    evidence_type="runtime_integration_and_failure_domain_test",
                    description=(
                        "Electrochemical runtime couples weak-acid charge balance, "
                        "Davies activities, and Ksp hooks; nonconvergence and out-of-domain "
                        "ionic strength fail before committing physical state."
                    ),
                    status="implemented",
                    command_or_path="tests/test_electrochem_equilibrium_coupling.py",
                    tolerance=(
                        "charge/material residual < 1e-9; exact physical rollback on failure"
                    ),
                ),
            ),
            model_limit_notes=(
                "This is a ChemWorld-local benchmark slice for pH and precipitation "
                "feedback, not a rigorous electrolyte speciation package.",
                "Order-dependent precipitation hooks should be replaced by coupled "
                "equilibrium solving in later professional work.",
            ),
            intended_use=(
                "Aqueous characterization tasks where agents can observe pH and infer acidity.",
                "Small precipitation and cleanup scenarios with explicit Ksp hooks.",
            ),
        ),
    )




__all__ = [
    "equilibrium_chemistry_model_cards",
]
