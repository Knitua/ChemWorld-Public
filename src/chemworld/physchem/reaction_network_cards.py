"""Reaction-network model cards for ChemWorld."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def reaction_kinetics_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="reaction_ode_mass_action_arrhenius_reference_slice",
            module_id="reaction_kinetics",
            title="Mass-Action and Arrhenius Reaction-Network ODE Slice",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "ChemWorld-owned balanced reaction-network ODE implementation "
                "for isothermal constant-volume batch kinetics. The reference "
                "slice covers explicit concentration/activity bases, independent "
                "reaction orders, reversible and competing networks, catalyst "
                "deactivation, stiff/nonstiff policies, and auditable conservation."
            ),
            equations=(
                "dn/dt = V * S * r(c, T)",
                "r_forward = k_f prod_i c_i^nu_i",
                "k(T) = A T^b exp(-Ea/(RT))",
                ("r_net = k_f c_A - k_r c_B, k_r = k_f / K_eq for the validated reversible case"),
                (
                    "K_c(T) = exp(-Delta G_rxn^0/RT) * C0^(sum nu_i) "
                    "for the NASA7 detailed-balance slice"
                ),
                "[M]_eff = sum_i alpha_i C_i",
                "Pr = k0(T) [M]_eff / k_inf(T)",
                "k_Lindemann = k_inf Pr / (1 + Pr)",
                "k_Troe = k_Lindemann F_Troe(T, Pr, a, T1, T2, T3)",
                "S = (1/y) d y / d ln(p) for finite-difference sensitivity reports",
                "a_i = gamma_i C_i / C_standard for activity-basis rate laws",
            ),
            assumptions=(
                "well-mixed homogeneous phase",
                "constant volume",
                "constant temperature",
                "element- and charge-balanced stoichiometric reactions",
                "activity coefficients are caller-supplied or ideal (gamma_i=1)",
                "falloff tests use homogeneous gas-phase collision-efficiency proxies",
            ),
            validity_limits=(
                "analytical reference cases are first-order A=>B and A<=>B networks",
                (
                    "falloff validation is limited to compact third-body, Lindemann, "
                    "and Troe formulas; no chemically activated bimolecular pressure "
                    "dependence or surface-coverage model is included"
                ),
                "rate coefficient units must be consistent with mol/L concentration powers",
                "homogeneous constant-volume systems only; transport is out of scope",
            ),
            failure_modes=(
                "negative or nonfinite rate coefficients raise errors",
                "unbalanced mechanisms fail at ReactionNetworkSpec construction",
                "stiff systems require an explicit stiff-capable solver policy",
                "terminal events only support named species-amount thresholds",
                "negative collision efficiencies and invalid Troe parameters raise errors",
            ),
            units={
                "amount": "mol",
                "volume": "L",
                "temperature": "K",
                "time": "s",
                "rate": "mol/L/s",
            },
            reference_reading=(
                (
                    "Cantera: reference_repos/cantera/doc/sphinx/reference/"
                    "reactors/index.md covers ReactorNet ODE/DAE integration."
                ),
                (
                    "Cantera: reference_repos/cantera/doc/sphinx/yaml/"
                    "reactions.md covers equation and rate-constant contracts."
                ),
                (
                    "Cantera: reference_repos/cantera/test/python/"
                    "test_reaction.py covers ArrheniusRate formulas."
                ),
                (
                    "RMG-Py: reference_repos/rmg-py/rmgpy/kinetics/"
                    "arrhenius.pyx covers get_rate_coefficient."
                ),
                (
                    "RMG-Py: reference_repos/rmg-py/rmgpy/reaction.py "
                    "covers reverse rates from k_forward/K_eq."
                ),
                (
                    "Cantera: reference_repos/cantera/include/cantera/zeroD/"
                    "ReactorNet.h defines normalized sensitivity coefficients "
                    "S=(1/y)dy/dp for registered reaction multipliers."
                ),
                (
                    "RMG/Arkane: reference_repos/rmg-py/arkane/"
                    "sensitivity.py perturbs kinetic/energy parameters, reruns "
                    "the job, and reports finite-difference sensitivity coefficients."
                ),
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="reaction-ode-analytical-cases",
                    evidence_type="unit_test",
                    description=(
                        "Irreversible and reversible first-order batch ODE "
                        "cases compare numerical integration against analytical trajectories."
                    ),
                    status="implemented",
                    command_or_path="tests/test_reaction_network.py",
                    tolerance="rtol=1e-7, atol=1e-9 mol",
                ),
                ValidationEvidence(
                    evidence_id="independent-scipy-method-cross-check",
                    evidence_type="reference_test",
                    description=(
                        "ChemWorld LSODA trajectories are compared with a separately "
                        "invoked tight-tolerance SciPy DOP853 boundary for both "
                        "analytical cases."
                    ),
                    status="implemented",
                    reference_backend="scipy.integrate.solve_ivp",
                    command_or_path="tests/test_reaction_kinetics_reference.py",
                    tolerance="comparison rtol=2e-7, atol=2e-9 mol",
                ),
                ValidationEvidence(
                    evidence_id="cantera-arrhenius-rate-optional",
                    evidence_type="optional_reference_test",
                    description=(
                        "If Cantera is importable, compare ChemWorld Arrhenius "
                        "rate constants against ct.ArrheniusRate for the same A, b, Ea."
                    ),
                    status="implemented_optional",
                    reference_backend="Cantera",
                    command_or_path="tests/reference/test_optional_reference_backends.py",
                    tolerance="rtol=1e-12",
                ),
                ValidationEvidence(
                    evidence_id="stiff-jacobian-conservation-event-tests",
                    evidence_type="unit_test",
                    description=(
                        "A Robertson-like network exercises BDF with a supplied "
                        "finite-difference Jacobian, nonnegativity and invariant drift; "
                        "a DOP853 case verifies terminal event localization."
                    ),
                    status="implemented",
                    command_or_path="tests/test_reaction_kinetics_reference.py",
                    tolerance="conservation drift <1e-7 mol",
                ),
                ValidationEvidence(
                    evidence_id="competition-deactivation-response-tests",
                    evidence_type="response_test",
                    description=(
                        "Parallel/series competition produces distinct signed kinetic "
                        "sensitivities and catalyst loading/deactivation changes product response."
                    ),
                    status="implemented",
                    command_or_path="tests/test_reaction_kinetics_reference.py",
                    tolerance="all declared response directions and >1e-3 sensitivity",
                ),
                ValidationEvidence(
                    evidence_id="nasa7-detailed-balance-rate-test",
                    evidence_type="unit_test",
                    description=(
                        "NASA7 species Gibbs energies determine K_eq(T), reverse "
                        "rate constants, and the equilibrium ratio in a reversible "
                        "batch ODE case."
                    ),
                    status="implemented",
                    command_or_path="tests/test_reaction_network.py",
                    tolerance="equilibrium ratio checked at 5e-3 relative tolerance",
                ),
                ValidationEvidence(
                    evidence_id="pressure-dependent-falloff-rate-tests",
                    evidence_type="unit_test",
                    description=(
                        "Third-body collision efficiencies, Lindemann low/high-pressure "
                        "limits, Troe broadening, and bath-gas-sensitive batch ODE "
                        "integration are checked with deterministic compact cases."
                    ),
                    status="implemented",
                    command_or_path="tests/test_reaction_network.py",
                    tolerance="pytest.approx local tolerances for analytical limits",
                ),
                ValidationEvidence(
                    evidence_id="kinetic-finite-difference-sensitivity-test",
                    evidence_type="unit_test",
                    description=(
                        "Finite-difference sensitivity of an irreversible "
                        "first-order batch product amount matches the analytical "
                        "d ln(y) / d ln(k) expression and emits a ranked explanation report."
                    ),
                    status="implemented",
                    command_or_path="tests/test_reaction_network.py",
                    tolerance="relative local sensitivity checked at 5e-4",
                ),
            ),
            model_limit_notes=(
                (
                    "This validates the bounded reaction-ODE slice represented by "
                    "this model card; broader kinetics remain outside its scope."
                ),
                (
                    "Optional Cantera evidence is environment-dependent and is not "
                    "counted as passed when the dependency is unavailable."
                ),
                "Runtime adapter promotion is separate from this implementation evidence.",
            ),
            intended_use=(
                "benchmark reaction-network sanity checks",
                "mechanism-card validation",
                "pressure-dependent qualitative kinetics checks",
                "foundation for task-specific reaction optimization and reactor models",
            ),
        ),
    )


__all__ = [
    "reaction_kinetics_model_cards",
]
