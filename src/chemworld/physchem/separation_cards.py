"""Model cards for ChemWorld separation kernels."""

from __future__ import annotations

from chemworld.physchem.crystallization_cards import crystallization_unit_model_cards
from chemworld.physchem.extraction_cards import extraction_unit_model_cards
from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def separation_model_cards() -> tuple[ModelCard, ...]:
    return (
        *crystallization_unit_model_cards(),
        *extraction_unit_model_cards(),
        ModelCard(
            model_id="lle_tpd_style_phase_stability",
            module_id="separations",
            title="TPD-Style Liquid-Liquid Phase Split Diagnostic",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Material-conserving liquid-liquid split layer with a "
                "partition-seeded tangent-plane-distance-style phase-stability "
                "diagnostic and explicit initialization policy."
            ),
            equations=(
                "w_org,i proportional z_i K_i V_org",
                "w_aq,i proportional z_i V_aq / K_i",
                "TPD_like(w) = sum_i w_i[ln(w_i gamma_i(w)) - ln(z_i gamma_i(z))]",
                "min_TPD_like = min(TPD_org, TPD_aq) - partition/nonideality drive",
                "n_org,i = eta_stage F_i K_i V_org / (K_i V_org + V_aq) + entrainment",
            ),
            assumptions=(
                "partition coefficients are supplied by task/scenario or downstream model",
                "activity coefficients come from the local ideal/Wilson/NRTL/UNIQUAC layer",
                "negative TPD-like scores indicate a two-liquid split is favored",
                "stage efficiency models incomplete mixing and approach to the split",
                "entrainment is an explicit mass-conserving transfer term",
            ),
            validity_limits=(
                "requires positive phase volumes and positive partition coefficients",
                "component set in optional activity model must match the feed",
                "does not perform global Gibbs minimization or rigorous tie-line tracing",
                "best suited to benchmark extraction tasks and qualitative LLE planning",
            ),
            failure_modes=(
                "non-positive volumes or partition coefficients fail early",
                "negative or zero-total feed amounts fail early",
                "activity-model component mismatch fails early",
                "low stage efficiency is recorded as a diagnostic warning",
            ),
            units={
                "feed_amount": "mol",
                "phase_volume": "L",
                "temperature": "K",
                "partition_coefficient": "dimensionless",
                "tpd_like": "dimensionless",
            },
            reference_reading=(
                (
                    "Michelsen TPD stability analysis motivates the "
                    "tangent-plane-distance form used for the diagnostic."
                ),
                (
                    "phasepy.equilibrium.flash and thermo flash workflows "
                    "separate stability/initialization diagnostics from the "
                    "final material split; ChemWorld follows that contract "
                    "without claiming rigorous multiphase minimization."
                ),
                (
                    "IDAES flash-style unit models make material balances "
                    "first-class outputs; this LLE slice keeps component "
                    "balance errors explicit in the separation ledger."
                ),
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="lle-tpd-diagnostic-phase-split",
                    evidence_type="unit_test",
                    description=(
                        "Tests verify the analytical uniform-partition identity "
                        "for ideal single-liquid classification, "
                        "partition-driven two-liquid classification, "
                        "initialization composition normalization, material "
                        "balance, metadata propagation, and extraction-task "
                        "runtime integration."
                    ),
                    status="implemented",
                    command_or_path=("tests/test_phase_equilibrium.py; tests/test_separations.py"),
                    tolerance="pytest.approx and exact balance checks",
                ),
            ),
            model_limit_notes=(
                "This is a TPD-style diagnostic and mass-balanced split "
                "solver, not a rigorous LLE flash package.",
                "Tie-line tracing, TPD minimization over arbitrary trial "
                "compositions, electrolyte LLE, density-coupled volume "
                "prediction and parameter-estimation workflows remain outside this model's scope.",
            ),
            intended_use=(
                "reaction-to-purification extraction steps",
                "partition-discovery world-model learning tasks",
                "agent-facing explanations of recovery/purity tradeoffs",
            ),
        ),
        ModelCard(
            model_id="vle_shortcut_distillation",
            module_id="separations",
            title="VLE-Coupled Shortcut Distillation",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Constant-relative-volatility shortcut distillation model "
                "whose separation factors are derived from Raoult/activity "
                "VLE K-values rather than arbitrary volatility scores."
            ),
            equations=(
                "K_i = gamma_i Psat_i / (phi_i P)",
                "alpha_i,HK = K_i / K_HK",
                "N_eff = N_theoretical * tray_efficiency * R/(1+R)",
                "(D_i/B_i)/(D_j/B_j) = (alpha_i/alpha_j)**N_eff",
                "sum_i D_i = distillate_cut * sum_i F_i",
            ),
            assumptions=(
                "constant relative volatility at the supplied temperature and pressure",
                "total condenser/reboiler shortcut behavior represented by reflux-scaled stages",
                "no tray hydraulics, flooding, pressure profile, or rigorous MESH solve",
                "latent heat duty scales with internal vapor traffic",
            ),
            validity_limits=(
                "requires positive vapor pressures and positive VLE K-values",
                "light key must be more volatile than heavy key under supplied VLE conditions",
                "intended for benchmark-scale binary or small multicomponent separations",
                "not valid for azeotropic, reactive, or multiple-liquid-phase columns",
            ),
            failure_modes=(
                "missing feed, vapor-pressure, or latent-heat components raise validation errors",
                (
                    "invalid pressure, temperature, cut fraction, reflux, or "
                    "stage efficiency fails early"
                ),
                "key order that contradicts VLE K-values fails instead of silently swapping labels",
            ),
            units={
                "feed_amount": "mol",
                "pressure": "Pa",
                "temperature": "K",
                "vapor_pressure": "Pa",
                "latent_heat": "J/mol",
                "heat_duty": "J",
            },
            reference_reading=(
                (
                    "IDAES: reference_repos/idaes-pse/idaes/models/unit_models/"
                    "flash.py builds a 0D flash with phase-equilibrium state "
                    "blocks, material balances, energy balances, and vapor/liquid outlets."
                ),
                (
                    "IDAES: activity_coeff_prop_pack.py _make_flash_eq defines "
                    "total/component balances and a smooth VLE flash formulation."
                ),
                (
                    "thermo: README and thermo.flash.flash_vl.FlashVL show "
                    "FlashVL objects built from constants, property correlations, "
                    "liquid/gas phases, and PT/VF flash specifications."
                ),
                (
                    "phasepy: phasepy.equilibrium.flash solves PT flash with "
                    "K-values, Rachford-Rice mass balance, accelerated "
                    "successive substitution, and Gibbs minimization fallback."
                ),
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="vle-shortcut-fenske-identity",
                    evidence_type="unit_test",
                    description=(
                        "Binary and multicomponent tests verify material "
                        "balance, VLE-derived key ordering, and the analytical "
                        "Fenske distribution-ratio identity."
                    ),
                    status="implemented",
                    command_or_path="tests/test_separations.py",
                    tolerance="pytest.approx local tolerances",
                ),
            ),
            model_limit_notes=(
                "This is a professional shortcut slice for benchmark tasks, "
                "not a replacement for rigorous IDAES column MESH models.",
                "Azeotrope detection, tray hydraulics, rigorous pressure-drop "
                "profiles, and column costing remain open work.",
            ),
            intended_use=(
                "reaction-to-purification task kernels",
                "purity/recovery/cost tradeoff benchmark cases",
                "agent planning tasks that need interpretable VLE-coupled separation behavior",
            ),
        ),
        ModelCard(
            model_id="fenske_underwood_gilliland_sizing",
            module_id="separations",
            title="Binary Fenske-Underwood-Gilliland Distillation Sizing",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Binary shortcut column-sizing report that combines Fenske "
                "minimum stages, Underwood minimum reflux for a saturated "
                "liquid feed, and Eduljee's explicit Gilliland correlation."
            ),
            equations=(
                "N_min = ln[(xD_LK/xD_HK)(xB_HK/xB_LK)] / ln(alpha_LK,HK)",
                "Underwood root: sum_i alpha_i z_i/(alpha_i - theta) = 1 - q, with q = 1",
                "Underwood reflux: R_min + 1 = sum_i alpha_i xD_i/(alpha_i - theta)",
                "X = (R - R_min)/(R + 1)",
                "Y = (N - N_min)/(N + 1)",
                "Y = 1 - exp[((1 + 54.4 X)/(11 + 117.2 X))((X - 1)/sqrt(X))]",
            ),
            assumptions=(
                "binary light-key/heavy-key separation",
                "constant relative volatility supplied by the caller",
                "saturated liquid feed with q = 1",
                "total-condenser shortcut semantics and no tray hydraulics",
                "feed-stage estimate is a Fenske-style composition-distance heuristic",
            ),
            validity_limits=(
                "relative volatility must be greater than one",
                "bottoms_light < feed_light < distillate_light",
                "reflux ratio must exceed the calculated Underwood minimum",
                "pressure profile is only reported as a warning and does not update alpha",
                "not valid for azeotropes, multicomponent key distribution, or reactive columns",
            ),
            failure_modes=(
                "missing provenance raises a validation error",
                "invalid mole fractions, pressure, alpha, or stage efficiency fail early",
                "reflux below minimum fails instead of returning an infinite-stage proxy",
                "unsupported feed_quality values fail instead of silently using q=1 equations",
            ),
            units={
                "pressure": "Pa",
                "relative_volatility": "dimensionless",
                "mole_fraction": "dimensionless",
                "reflux_ratio": "dimensionless",
                "stage_count": "dimensionless",
            },
            reference_reading=(
                (
                    "IDAES tray_column.py configures rigorous columns around "
                    "number_of_trays, feed_tray_location, condenser/reboiler "
                    "blocks, optional heat transfer, pressure change, and a "
                    "property_package; ChemWorld's report exposes the analogous "
                    "sizing fields without pretending to solve MESH equations."
                ),
                (
                    "IDAES condenser.py defines a reflux_ratio split fraction "
                    "R/(1+R), reinforcing that reflux is a first-class column "
                    "contract rather than a hidden score multiplier."
                ),
                (
                    "IDAES reboiler.py exposes heat duty, pressure-change hooks, "
                    "and optional boilup ratio; ChemWorld records pressure "
                    "warnings now and leaves rigorous boilup for D7/MESH work."
                ),
                (
                    "thermo README shows flash/property-package workflows built "
                    "from constants, correlations, phase models, and result "
                    "objects; ChemWorld keeps alpha/provenance explicit here."
                ),
                (
                    "phasepy.equilibrium.flash uses K-values, Rachford-Rice, "
                    "and Gibbs fallback for real flash problems; this shortcut "
                    "sizing report deliberately remains a binary column design slice."
                ),
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="fug-binary-stage-sizing",
                    evidence_type="unit_test",
                    description=(
                        "Tests validate Fenske analytical stage counts, "
                        "Underwood minimum reflux, Gilliland monotonicity with "
                        "reflux ratio, feed-stage bounds, pressure warnings, "
                        "and failure cases."
                    ),
                    status="implemented",
                    command_or_path="tests/test_separations.py",
                    tolerance="pytest.approx local tolerances",
                ),
            ),
            model_limit_notes=(
                "This is a professional shortcut sizing layer, not a rigorous "
                "rate-based or equilibrium-stage column solve.",
                "Multicomponent Underwood roots, Murphree efficiency profiles, "
                "boilup calculation, hydraulics, flooding, weeping, pressure "
                "drop integration, and column costing remain open deepening work.",
            ),
            intended_use=(
                "distillation task planning and report generation",
                "purification task model cards that need explicit reflux/stage assumptions",
                "agent explanations comparing high purity, reflux cost, and tray count",
            ),
        ),
    )


__all__ = ["separation_model_cards"]
