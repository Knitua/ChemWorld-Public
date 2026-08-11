"""Model cards for cooling-crystallization unit models."""

from __future__ import annotations

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def crystallization_unit_model_cards() -> tuple[ModelCard, ...]:
    return (
        ModelCard(
            model_id="cooling_crystallization_population_balance_v1",
            module_id="separations",
            title="Cooling Crystallization With Compact Population Balance",
            maturity=MaturityLevel.PROFESSIONAL_CANDIDATE,
            summary=(
                "Linear cooling crystallization driven by a provenance-tagged "
                "van't Hoff solubility curve, power-law primary nucleation and "
                "growth, impurity occlusion, and cohort CSD reporting."
            ),
            equations=(
                "ln(C*/C*_ref) = -DeltaH_diss/R (1/T - 1/T_ref)",
                "S = C/C*; sigma = max(S - 1, 0)",
                "B = k_b sigma^b",
                "G = k_g sigma^g",
                "m_particle = rho pi d^3 / 6",
                "n_impurity,occluded = min(n_impurity, r_occ(sigma) Delta n_crystal)",
            ),
            assumptions=(
                "The mother-liquor volume is constant and perfectly mixed.",
                "Temperature follows a declared linear cooling ramp.",
                "Primary nucleation and size-independent linear growth use "
                "power-law relative-supersaturation kinetics.",
                "Each integration step adds a crystal-size cohort; available "
                "supersaturated target material caps nucleation and growth.",
                "Seed crystals are the target compound and enter the target "
                "material ledger as an external amount.",
            ),
            validity_limits=(
                "The entire cooling ramp must lie inside the declared "
                "solubility-curve temperature range.",
                "Kinetic, density, molecular-weight, nucleus-size, and seed "
                "parameters require scenario-specific provenance.",
                "The compact cohort method reports number-based CSD metadata "
                "but does not solve agglomeration or breakage kernels.",
            ),
            failure_modes=(
                "Heating ramps, invalid component mappings, out-of-range "
                "temperatures, and nonphysical parameters fail early.",
                "No seed and zero primary nucleation produce an explicit "
                "no-crystal-population warning.",
                "A final supersaturation above 1.05 produces a kinetic "
                "incompletion warning rather than forcing equilibrium.",
                "The formal runtime additionally rejects ineffective seeds, target "
                "depletion, excessive cooling rate, absent crystallization transfer, "
                "solver non-convergence, and component or particle-moment non-closure.",
            ),
            units={
                "temperature": "K",
                "time": "s",
                "solubility/concentration": "mol/L",
                "nucleation rate": "1/(L s)",
                "growth rate/particle diameter": "m/s; m",
                "density": "kg/m^3",
                "molecular weight": "kg/mol",
                "seed mass": "g",
                "component amount": "mol",
            },
            reference_reading=(
                "Population-balance method of moments and discretized cohort "
                "conventions for batch cooling crystallization.",
                "van't Hoff solubility relation and power-law nucleation/growth "
                "kinetics used in benchmark crystallization literature.",
                "IDAES unit-model conventions for explicit component material "
                "balances, state variables, and provenance-tagged parameters.",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="vanthoff-solubility-cooling-order",
                    evidence_type="analytical_test",
                    description=(
                        "Checks the reference point, monotonic cooling order, "
                        "and declared temperature-domain failure."
                    ),
                    status="implemented",
                    command_or_path="tests/test_crystallization_units.py",
                    tolerance="pytest.approx at reference temperature",
                ),
                ValidationEvidence(
                    evidence_id="cooling-crystallization-population-ledger",
                    evidence_type="unit_test",
                    description=(
                        "Checks deeper-cooling recovery, seeded growth without "
                        "primary nucleation, impurity-occlusion purity response, "
                        "CSD quantile order, provenance, and material closure."
                    ),
                    status="implemented",
                    command_or_path="tests/test_crystallization_units.py",
                    tolerance="component material residual < 1e-10",
                ),
                ValidationEvidence(
                    evidence_id="cooling-crystallization-runtime-coupling",
                    evidence_type="dynamic_runtime_test",
                    description=(
                        "Proves the formal operation calls the validated provider, "
                        "records temperature/supersaturation/nucleation/growth history, "
                        "closes component and M0-M3 ledgers, responds to cooling/seed/time "
                        "perturbations, couples filtration, and rolls back failed domains."
                    ),
                    status="implemented",
                    command_or_path="tests/test_crystallization_coupling.py",
                    tolerance=(
                        "component and particle target residual <= 1e-10 mol; "
                        "failure cases commit no crystallization state"
                    ),
                ),
            ),
            model_limit_notes=(
                "Professional-candidate denotes an auditable benchmark PBM "
                "slice, not an industrial crystallizer design package.",
                "Secondary nucleation, agglomeration, breakage, shape, polymorph "
                "selection, hydrodynamics, and heat-balance coupling are absent.",
            ),
            intended_use=(
                "Cooling, seeding, purity, and CSD tradeoff benchmark tasks.",
                "World-model studies that need supersaturation and particle "
                "history rather than a scalar crystal-size proxy.",
            ),
        ),
    )


__all__ = ["crystallization_unit_model_cards"]
