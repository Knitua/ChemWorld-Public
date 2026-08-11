"""Shared physical-chemical law registry for ChemWorld."""

from __future__ import annotations

from chemworld.backends import semi_mechanistic_backend_spec
from chemworld.foundation import WorldLawSpec
from chemworld.world.continuous_flow import ContinuousFlowModuleSpec
from chemworld.world.crystallization import CrystallizationModuleSpec
from chemworld.world.distillation import DistillationModuleSpec
from chemworld.world.electrochemistry import ElectrochemistryModuleSpec
from chemworld.world.instruments import instrument_contracts
from chemworld.world.observation_kernel import ObservationModuleSpec
from chemworld.world.operations import INSTRUMENTS, OPERATION_TYPES
from chemworld.world.parameters import WORLD_FAMILY_VERSION
from chemworld.world.phase_kernel import PhaseModuleSpec
from chemworld.world.reaction_kernel import ReactionModuleSpec
from chemworld.world.separation_kernel import SeparationModuleSpec
from chemworld.world.thermal_kernel import ThermalModuleSpec

MODULE_VERSIONS = {
    "reaction": ReactionModuleSpec().version,
    "thermal": ThermalModuleSpec().version,
    "phase_partition": PhaseModuleSpec().version,
    "separation": SeparationModuleSpec().version,
    "crystallization": CrystallizationModuleSpec().version,
    "distillation": DistillationModuleSpec().version,
    "continuous_flow": ContinuousFlowModuleSpec().version,
    "electrochemistry": ElectrochemistryModuleSpec().version,
    "observation": ObservationModuleSpec().version,
}


def constitution_rules() -> tuple[str, ...]:
    return (
        "material_conservation",
        "nonnegative_state",
        "species_registry_membership",
        "state_numeric_values_finite",
        "unit_consistency",
        "yield_upper_bound",
        "energy_balance",
        "phase_mass_balance",
        "observation_non_omniscient",
        "observation_values_finite_and_bounded",
        "observation_mask_consistent",
        "observation_signal_and_accounting_integrity",
        "measurement_has_cost",
        "action_preconditions",
        "safety_constraints",
        "public_private_reproducibility",
        "single_declared_runtime_provider_path",
        "provider_diagnostics_do_not_inflate_runtime_maturity",
    )


def world_law_spec() -> WorldLawSpec:
    """Return the formal shared world law used by every ChemWorld task."""

    contracts = {
        instrument_id: contract.to_dict()
        for instrument_id, contract in instrument_contracts().items()
    }
    backend = semi_mechanistic_backend_spec().to_dict()
    return WorldLawSpec(
        law_version=WORLD_FAMILY_VERSION,
        ontology_registry={
            "substance_registry_policy": "scenario_compiled_mechanism",
            "phases": ["reactor_liquid", "aqueous", "organic", "solid"],
            "vessels": ["batch_reactor", "separator", "assay_vial"],
            "instruments": list(INSTRUMENTS),
            "modules": [
                ReactionModuleSpec().to_dict(),
                ThermalModuleSpec().to_dict(),
                PhaseModuleSpec().to_dict(),
                SeparationModuleSpec().to_dict(),
                CrystallizationModuleSpec().to_dict(),
                DistillationModuleSpec().to_dict(),
                ContinuousFlowModuleSpec().to_dict(),
                ElectrochemistryModuleSpec().to_dict(),
                ObservationModuleSpec().to_dict(),
            ],
        },
        physical_constitution="PhysicalConstitutionChecklist",
        operation_registry=OPERATION_TYPES,
        transition_kernel_registry=(
            "reaction_ode",
            "thermal_energy_balance",
            "phase_partition",
            "separation",
            "crystallization",
            "distillation",
            "continuous_flow",
            "electrochemistry",
            "instrument_cost",
        ),
        observation_kernel_registry=("instrument_observation",),
        instrument_registry=contracts,
        module_versions=MODULE_VERSIONS,
        backend=backend,
        constitution_rules=constitution_rules(),
        scenario_generators=("chemworld.scenario.default",),
    )


__all__ = ["MODULE_VERSIONS", "constitution_rules", "world_law_spec"]
