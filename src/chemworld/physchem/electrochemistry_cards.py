"""Electrochemistry model cards for ChemWorld."""

from __future__ import annotations

from chemworld.physchem.electrochem_control_cards import (
    electrochem_control_model_cards,
)
from chemworld.physchem.electrochem_double_layer_cards import (
    electrochem_double_layer_model_cards,
)
from chemworld.physchem.electrochem_transport_cards import (
    electrochem_transport_model_cards,
)
from chemworld.physchem.electrochemical_scenario_model_cards import (
    electrochemical_scenario_model_cards,
)
from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence


def electrochemistry_model_cards() -> tuple[ModelCard, ...]:
    """Return model-card metadata for the electrochemistry slice."""

    return (
        *electrochem_control_model_cards(),
        *electrochem_double_layer_model_cards(),
        *electrochem_transport_model_cards(),
        *electrochemical_scenario_model_cards(),
        ModelCard(
            model_id="nernst_butler_volmer_faradaic_v1",
            module_id="electrochemistry",
            title="Nernst, Butler-Volmer, and Faradaic conversion kernel",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Compact electrochemical thermodynamics and charge-accounting "
                "kernel for virtual electrode-conversion tasks."
            ),
            equations=(
                "E_eq = E0 - RT/(nF) ln Q",
                "i = i0 A [exp(alpha_a nF eta/RT) - exp(-alpha_c nF eta/RT)]",
                "R_cell = L/(kappa A) + R_contact",
                "E_interface = E_measured - i R_cell",
                "P_ohmic = i^2 R_cell",
                "extent = |i| t FE / (nF)",
                "W_elec = |E_measured i t|",
            ),
            assumptions=(
                "Activities are dimensionless and supplied by the world state.",
                "Electrolyte resistance is a lumped Ohm-law cell resistance.",
                "No double-layer dynamics, spatial electrolyte gradients, or "
                "porous-electrode transport.",
                "A finite applied current is capped by the Butler-Volmer kinetic current.",
            ),
            validity_limits=(
                "Designed for benchmark-scale virtual conversions, not battery design.",
                "Requires positive temperature and positive electron number.",
                "Requires positive electrolyte conductivity, electrode area, and "
                "electrode gap when ohmic drop is enabled.",
                "Extreme overpotentials are exponent-clipped for numerical stability.",
            ),
            failure_modes=(
                "Missing activity calibration can distort Nernst potentials.",
                "Lumped electrolyte resistance cannot represent concentration gradients "
                "or porous-electrode tortuosity.",
                "Large time steps do not update activities continuously during electrolysis.",
                "Large requested currents can exceed kinetic support or voltage-window limits.",
            ),
            units={
                "potential": "V",
                "current": "A",
                "charge": "C",
                "extent": "mol",
                "energy": "J",
                "resistance": "ohm",
                "conductivity": "S/m",
                "electrode_gap": "m",
                "electrode_area": "m^2",
            },
            reference_reading=(
                "reference_repos/cantera/doc/sphinx/reference/kinetics/"
                "reaction-rates.md: Butler-Volmer overpotential form",
                "reference_repos/cantera/data/lithium_ion_battery.yaml: "
                "electrolyte/interface battery mechanism organization",
                "reference_repos/idaes-pse/idaes/models_extra/power_generation/"
                "unit_models/soc_submodels/triple_phase_boundary.py: voltage-drop "
                "and resistive-heating terms",
                "Standard electrochemical thermodynamics: DeltaG = -nFE and Ohm-law iR loss",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="electrochemistry-identity-tests",
                    evidence_type="unit-test",
                    description=(
                        "Nernst direction, zero-current equilibrium, Butler-Volmer sign, "
                        "Faraday charge conversion, Ohm-law voltage drop, resistance scaling, "
                        "and electrolysis energy-loss tests."
                    ),
                    status="implemented",
                    command_or_path="tests/test_electrochemistry.py",
                    tolerance="1e-9 to 1e-6 relative checks",
                ),
            ),
            model_limit_notes=(
                "This slice replaces the previous empirical electrolysis proxy but "
                "remains below a full porous-electrode, electrolyte-transport, or "
                "battery-cell model.",
            ),
            intended_use=(
                "Electrochemical conversion benchmark tasks.",
                "Teaching and agent evaluation where charge accounting must be visible.",
            ),
        ),
    )


__all__ = [
    "electrochemistry_model_cards",
]
