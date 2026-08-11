"""Transport model cards for ChemWorld."""

from __future__ import annotations

from chemworld.physchem.heat_transfer_cards import equipment_heat_transfer_model_cards
from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence
from chemworld.physchem.two_phase_flow_cards import two_phase_flow_model_cards


def transport_model_cards() -> tuple[ModelCard, ...]:
    """Return model-card records for transport kernels with validation status."""

    return (
        *equipment_heat_transfer_model_cards(),
        *two_phase_flow_model_cards(),
        ModelCard(
            model_id="pipe_friction_and_single_phase_pressure_drop",
            module_id="transport",
            title="Pipe Friction And Single-Phase Pressure Drop",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Darcy-Weisbach single-phase pipe pressure drop with explicit "
                "laminar and Haaland friction-factor branches."
            ),
            equations=(
                "Re = rho V D / mu",
                "f_laminar = 64 / Re",
                "f_Haaland = [-1.8 log10((e/D/3.7)^1.11 + 6.9/Re)]^-2",
                "DeltaP = f (L/D) rho V^2 / 2 + K rho V^2 / 2 + rho g dz",
            ),
            assumptions=(
                "Straight circular pipe with incompressible single-phase flow.",
                "Fittings use aggregate K loss coefficient.",
                "Pump work uses hydraulic power divided by an explicit efficiency.",
            ),
            validity_limits=(
                "Laminar branch is normally used below Re=2040.",
                "Haaland branch is documented for approximately 4e3 <= Re <= 1e8.",
                "Haaland roughness range is approximately 1e-6 <= e/D <= 5e-2.",
                "Transitional auto mode is a ChemWorld smooth blend for benchmark continuity.",
            ),
            failure_modes=(
                "Nonpositive density, viscosity, pipe diameter, or length raises ValueError.",
                "strict_validity=True raises on branch-specific validity warnings.",
                "Compressible and two-phase pressure gradients require separate models.",
            ),
            units={
                "density": "kg/m^3",
                "viscosity": "Pa*s",
                "diameter": "m",
                "length": "m",
                "pressure_drop": "Pa",
            },
            reference_reading=(
                "reference_repos/fluids/fluids/friction.py:friction_laminar",
                "reference_repos/fluids/fluids/friction.py:Haaland",
                "reference_repos/fluids/fluids/friction.py:one_phase_dP",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="fluids-haaland-friction-factor",
                    evidence_type="optional_reference_test",
                    description="Compare ChemWorld Haaland branch against fluids.friction.Haaland.",
                    status="implemented",
                    reference_backend="fluids",
                    command_or_path="tests/reference/test_optional_reference_backends.py",
                    tolerance="rtol=1e-12",
                ),
                ValidationEvidence(
                    evidence_id="fluids-one-phase-pressure-drop",
                    evidence_type="optional_reference_test",
                    description=(
                        "Compare single-phase Darcy-Weisbach pressure drop against "
                        "fluids.friction.one_phase_dP with Method='Haaland'."
                    ),
                    status="implemented",
                    reference_backend="fluids",
                    command_or_path="tests/reference/test_optional_reference_backends.py",
                    tolerance="rtol=1e-12",
                ),
            ),
            model_limit_notes=(
                "This card does not cover ChemWorld's homogeneous two-phase proxy.",
                "It does not include Crane fitting tables or compressible-flow corrections.",
            ),
            intended_use=(
                "Reference-validated benchmark pressure-cost and safety features.",
                "Educational inspection of pipe-flow cost ledgers.",
            ),
        ),
        ModelCard(
            model_id="internal_flow_heat_transfer_and_counterflow_hx",
            module_id="transport",
            title="Internal-Flow Heat Transfer And Counterflow Heat Exchanger",
            maturity=MaturityLevel.REFERENCE_VALIDATED,
            summary=(
                "Reference-auditable internal-flow Nusselt correlations and "
                "effectiveness-NTU counterflow heat-exchanger duty checks."
            ),
            equations=(
                "Nu_laminar = constant, default 3.66",
                "Nu_Dittus-Boelter = 0.023 Re^0.8 Pr^n, n=0.4 heating or 0.3 cooling",
                "Nu_Gnielinski = (f/8)(Re-1000)Pr/[1 + 12.7(f/8)^0.5(Pr^(2/3)-1)]",
                "h = Nu k / D",
                "NTU = U A / C_min",
                "epsilon_counterflow = (1 - exp[-NTU(1-Cr)])/(1 - Cr exp[-NTU(1-Cr)])",
                "Q = epsilon C_min (T_hot,in - T_cold,in)",
            ),
            assumptions=(
                "Single-phase internal flow in circular channels.",
                "Gnielinski branch uses a Darcy friction factor; ChemWorld auto mode uses Haaland.",
                "Heat-exchanger calculation is steady counterflow e-NTU with "
                "constant heat capacities.",
            ),
            validity_limits=(
                "Constant laminar Nu is a fully developed benchmark approximation.",
                "Dittus-Boelter is intended for turbulent Re >= 10000 and moderate Pr.",
                "Gnielinski is intended for approximately 3000 <= Re <= 5e6.",
                "No boiling, condensation, shell-side correction, or fouling dynamics are claimed.",
            ),
            failure_modes=(
                "Nonpositive Reynolds, Prandtl, conductivity, diameter, U, "
                "area, or heat capacities raise ValueError.",
                "Gnielinski with Re <= 1000 raises ValueError instead of "
                "returning nonphysical negative Nu.",
                "strict_validity=True raises on method-specific validity warnings.",
            ),
            units={
                "nusselt": "dimensionless",
                "heat_transfer_coefficient": "W/(m^2*K)",
                "overall_u": "W/(m^2*K)",
                "area": "m^2",
                "heat_duty": "W",
                "temperature": "K",
            },
            reference_reading=(
                "reference_repos/fluids/fluids/core.py:Nusselt, Prandtl, Reynolds",
                "reference_repos/idaes-pse/idaes/models/unit_models/"
                "heat_exchanger.py LMTD callbacks",
                "reference_repos/idaes-pse/idaes/models/unit_models/"
                "heat_exchanger_ntu.py e-NTU variables and duty constraint",
                "reference_repos/coolprop docs/source/coolprop/"
                "HighLevelAPI.rst property workflow notes",
            ),
            validation_evidence=(
                ValidationEvidence(
                    evidence_id="fluids-nusselt-definition",
                    evidence_type="optional_reference_test",
                    description=(
                        "Compare ChemWorld h = Nu k / D round-trip against fluids.core.Nusselt."
                    ),
                    status="implemented",
                    reference_backend="fluids",
                    command_or_path="tests/reference/test_optional_reference_backends.py",
                    tolerance="rtol=1e-12",
                ),
                ValidationEvidence(
                    evidence_id="counterflow-duty-balance",
                    evidence_type="unit_tests",
                    description=(
                        "Verify hot-side heat loss, cold-side heat gain, "
                        "effectiveness, maximum duty, and balance residual."
                    ),
                    status="passing",
                    command_or_path="python -m pytest tests/test_transport.py",
                    tolerance="absolute residual near machine precision",
                ),
            ),
            model_limit_notes=(
                "This slice does not model boiling or condensation.",
                "Shell corrections, fouling dynamics, and phase-change ledgers are "
                "implemented by the separate equipment heat-transfer model card.",
            ),
            intended_use=(
                "Reference-validated heat-duty and thermal-cost ledgers.",
                "Future reactor jacket and exchanger tasks with explicit heat-transfer metadata.",
            ),
        ),
    )


__all__ = [
    "transport_model_cards",
]
