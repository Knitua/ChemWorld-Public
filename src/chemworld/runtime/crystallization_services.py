"""Crystallization state-update services for the transactional runtime."""

from __future__ import annotations

from typing import Any

import numpy as np

from chemworld.foundation import (
    WorldState,
    equipment_settings,
    process_with_metrics,
    upsert_equipment_record,
)
from chemworld.foundation.state import PhaseLedger, PhaseRecord
from chemworld.physchem.crystallization_units import (
    CoolingCrystallizationResult,
    CrystallizationExecutionSpec,
    CrystallizationKineticsSpec,
    SolubilityCurveSpec,
)
from chemworld.physchem.crystallization_validation import CrystallizationGridCase
from chemworld.physchem.elements import molecular_weight
from chemworld.runtime.species import MechanismSpeciesView
from chemworld.world.parameters import ChemWorldParameters
from chemworld.world.thermal_kernel import account_temperature_transition


def _action_float(action: dict[str, Any], key: str, default: float) -> float:
    value = action.get(key, default)
    return float(np.asarray(value).reshape(-1)[0])


def _solid_phase_amounts(
    state: WorldState,
    *,
    target_species: str,
    impurity_species: str,
) -> tuple[float, float]:
    if state.phases is None or "solid" not in state.phases.phases:
        return 0.0, 0.0
    solid = state.phases.phases["solid"]
    return (
        float(solid.species_amounts_mol.get(target_species, 0.0)),
        float(solid.species_amounts_mol.get(impurity_species, 0.0)),
    )


def _crystallization_phases(
    state: WorldState,
    *,
    target_species: str,
    impurity_species: str,
    product_mol: float,
    impurity_mol: float,
    mother_liquor_volume_L: float | None = None,
    solid_selected: bool = True,
) -> PhaseLedger:
    mother_liquor_volume = (
        state.volume_L if mother_liquor_volume_L is None else mother_liquor_volume_L
    )
    product_mol = float(np.clip(product_mol, 0.0, state.species_amounts.get(target_species, 0.0)))
    impurity_mol = float(
        np.clip(impurity_mol, 0.0, state.species_amounts.get(impurity_species, 0.0))
    )
    solid_amounts = dict.fromkeys(state.species_amounts, 0.0)
    solid_amounts[target_species] = product_mol
    solid_amounts[impurity_species] = impurity_mol
    liquor_amounts = state.species_amounts.copy()
    liquor_amounts[target_species] = max(
        liquor_amounts.get(target_species, 0.0) - product_mol,
        0.0,
    )
    liquor_amounts[impurity_species] = max(
        liquor_amounts.get(impurity_species, 0.0) - impurity_mol,
        0.0,
    )
    return PhaseLedger(
        {
            "mother_liquor": PhaseRecord(
                phase_id="mother_liquor",
                vessel_id=state.vessel_id,
                phase_type="liquid",
                volume_L=mother_liquor_volume,
                species_amounts_mol=liquor_amounts,
                settled=True,
                selected=not solid_selected,
                metadata={},
            ),
            "solid": PhaseRecord(
                phase_id="solid",
                vessel_id=state.vessel_id,
                phase_type="solid",
                volume_L=0.0,
                species_amounts_mol=solid_amounts,
                settled=True,
                selected=solid_selected,
                metadata={},
            ),
        }
    )


class ChemWorldCrystallizationServices:
    """Apply seed, cooling crystallization, and filtration updates."""

    def __init__(
        self,
        world: ChemWorldParameters,
        species_view: MechanismSpeciesView,
    ) -> None:
        self.world = world
        self.species_view = species_view
        self.runtime_provider: Any | None = None
        self.last_provider_execution: dict[str, Any] = {}

    def _target_molecular_weight_kg_mol(self) -> float:
        target = self.species_view.primary_target_species
        species = self.species_view.mechanism.network.species[
            self.species_view.mechanism.network.species_index[target]
        ]
        return molecular_weight(species.composition) / 1000.0

    def seed_crystals(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        seed_mass = float(np.clip(_action_float(action, "seed_mass_g", 0.005), 0.0, 0.050))
        target_species = self.species_view.primary_target_species
        impurity_species = self.species_view.primary_impurity_species
        seed_target_mol = seed_mass / 1000.0 / self._target_molecular_weight_kg_mol()
        previous_settings = equipment_settings(state.equipment, "crystallizer")
        cumulative_seed_mass = float(previous_settings.get("crystal_seed_mass_g", 0.0)) + seed_mass
        cumulative_seed_target = (
            float(previous_settings.get("seed_target_mol", 0.0)) + seed_target_mol
        )
        existing_solid_product, existing_solid_impurity = _solid_phase_amounts(
            state,
            target_species=target_species,
            impurity_species=impurity_species,
        )
        species_amounts = state.species_amounts.copy()
        species_amounts[target_species] = species_amounts.get(target_species, 0.0) + seed_target_mol
        augmented_state = state.replace(species_amounts=species_amounts)
        phases = _crystallization_phases(
            augmented_state,
            target_species=target_species,
            impurity_species=impurity_species,
            product_mol=existing_solid_product + seed_target_mol,
            impurity_mol=existing_solid_impurity,
            solid_selected=False,
        )
        equipment = upsert_equipment_record(
            augmented_state.equipment,
            equipment_id="crystallizer",
            equipment_type="crystallizer",
            attached_vessel_id=augmented_state.vessel_id,
            status="seeded" if seed_mass > 0.0 else "configured",
            settings={
                "crystal_seeded": seed_mass > 0.0,
                "crystal_seed_mass_g": cumulative_seed_mass,
                "seed_target_mol": cumulative_seed_target,
                "seed_charge_count": int(previous_settings.get("seed_charge_count", 0)) + 1,
                "last_seed_time_s": augmented_state.ledger.time_s,
                "seed_model_id": "explicit_target_seed_mass_v1",
            },
        )
        process_metrics = {} if state.process is None else state.process.metrics
        initial_target = max(
            float(
                process_metrics.get(
                    "pre_separation_product_mol",
                    self.species_view.target_amount(state),
                )
            ),
            1.0e-12,
        )
        process = process_with_metrics(
            augmented_state.process,
            pre_separation_product_mol=initial_target,
        )
        ledger = augmented_state.ledger.with_updates(
            cost=augmented_state.ledger.cost + 0.012 + 0.20 * seed_mass
        )
        return augmented_state.replace(
            ledger=ledger,
            equipment=equipment,
            phases=phases,
            process=process,
        )

    def cool_crystallize(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        duration = float(np.clip(_action_float(action, "duration_s", 1200.0), 0.0, 14_400.0))
        target_temperature = float(
            np.clip(_action_float(action, "target_temperature_K", 278.15), 250.0, 330.0)
        )
        crystallizer_settings = equipment_settings(state.equipment, "crystallizer")
        target_species = self.species_view.primary_target_species
        impurity_species = self.species_view.primary_impurity_species
        seed_mass_g = float(crystallizer_settings.get("crystal_seed_mass_g", 0.0))
        seed_target_mol = float(crystallizer_settings.get("seed_target_mol", 0.0))
        p_mol = self.species_view.target_amount(state)
        dissolved_product_mol = max(p_mol - seed_target_mol, 0.0)
        impurity_mol = self.species_view.impurity_amount(state)
        target_molecular_weight = self._target_molecular_weight_kg_mol()
        initial_concentration = dissolved_product_mol / max(state.volume_L, 1.0e-12)
        solvent_index = int(
            equipment_settings(state.equipment, "batch_reactor").get("solvent", 0)
        )
        material_coupling_enabled = (
            state.metadata.get("crystallization_material_family_id")
            == "reaction-crystallization-latent-materials-v1"
        )
        if material_coupling_enabled and solvent_index not in range(4):
            raise ValueError("configured solvent index is outside the material contract")
        solubility_multiplier = (
            float(
                self.world.crystallization_solvent_solubility_multipliers[
                    solvent_index
                ]
            )
            if material_coupling_enabled
            else 1.0
        )
        nucleation_multiplier = (
            float(
                self.world.crystallization_solvent_nucleation_multipliers[
                    solvent_index
                ]
            )
            if material_coupling_enabled
            else 1.0
        )
        growth_multiplier = (
            float(
                self.world.crystallization_solvent_growth_multipliers[solvent_index]
            )
            if material_coupling_enabled
            else 1.0
        )
        occlusion_multiplier = (
            float(
                self.world.crystallization_solvent_occlusion_multipliers[
                    solvent_index
                ]
            )
            if material_coupling_enabled
            else 1.0
        )
        reference_solubility = (
            self.world.crystallization_reference_solubility_mol_L
            * self.world.domain_parameter("crystallization_solubility_multiplier")
            * solubility_multiplier
        )
        dissolution_enthalpy = 20_000.0
        solubility = SolubilityCurveSpec(
            model_id="runtime_vanthoff_material_solubility_v2",
            reference_solubility_mol_L=reference_solubility,
            reference_temperature_K=298.15,
            dissolution_enthalpy_J_mol=dissolution_enthalpy,
            minimum_temperature_K=250.0,
            maximum_temperature_K=430.0,
            provenance_id="chemworld-world-law-v0.2-solubility-policy",
        )
        kinetics = CrystallizationKineticsSpec(
            model_id="runtime_cooling_population_balance_v1",
            primary_nucleation_coefficient_per_L_s=(
                2.0e7 * self.world.domain_parameter("crystallization_nucleation_multiplier")
                * nucleation_multiplier
            ),
            primary_nucleation_exponent=2.0,
            growth_coefficient_m_s=2.0e-8 * growth_multiplier,
            growth_exponent=1.0,
            crystal_density_kg_m3=1200.0,
            target_molecular_weight_kg_mol=target_molecular_weight,
            nucleus_diameter_m=8.0e-6,
            impurity_occlusion_mol_per_mol=0.02 * occlusion_multiplier,
            supersaturation_occlusion_factor=0.5,
            fines_threshold_m=20.0e-6,
            provenance_id="chemworld-world-law-v0.2-crystallization-kinetics",
        )
        case = CrystallizationGridCase(
            feed_amounts_mol={
                target_species: dissolved_product_mol,
                impurity_species: impurity_mol,
            },
            target_component=target_species,
            impurity_component=impurity_species,
            solvent_volume_L=max(state.volume_L, 1.0e-9),
            initial_temperature_K=state.temperature_K,
            final_temperature_K=target_temperature,
            duration_s=max(duration, 1.0e-9),
            solubility_curve=solubility,
            kinetics=kinetics,
            seed_mass_g=seed_mass_g,
            seed_diameter_m=100.0e-6,
        )
        execution_spec = CrystallizationExecutionSpec.closed_loop_runtime()
        provider = self.runtime_provider
        if provider is None:
            from chemworld.physchem.crystallization_adapter_manifest import (
                ValidatedCrystallizationRuntimeProvider,
            )

            provider = ValidatedCrystallizationRuntimeProvider()
        time_steps = max(24, min(120, round(duration / 30.0)))
        provider_result = provider.evaluate(
            {
                "case": case,
                "time_steps": time_steps,
                "execution_spec": execution_spec,
            }
        )
        contract = provider.model_contract
        self.last_provider_execution = {
            "model_id": contract.model_id,
            "provider_path": contract.provider_path,
            "maturity": contract.maturity.value,
            "role": contract.role.value,
            "success": provider_result.success,
            "failure_reason": provider_result.failure_reason,
            "diagnostics": dict(provider_result.diagnostics),
            "provenance": list(provider_result.provenance),
        }
        if not provider_result.success:
            raise ValueError(
                provider_result.failure_reason or "crystallization runtime provider failed"
            )
        result = provider_result.outputs.get("result")
        if not isinstance(result, CoolingCrystallizationResult):
            raise ValueError("crystallization runtime provider returned no validated result")
        from chemworld.physchem.crystallization_adapter_manifest import (
            crystallization_runtime_adapter_manifest,
        )

        provider_manifest_hash = crystallization_runtime_adapter_manifest().manifest_hash
        crystallized = result.crystals_amounts_mol[target_species]
        crystallized_from_solution = result.crystallized_from_solution_mol
        occluded_impurity = result.crystals_amounts_mol[impurity_species]
        process_metrics = {} if state.process is None else state.process.metrics
        initial_p = max(
            float(process_metrics.get("pre_separation_product_mol", dissolved_product_mol)),
            dissolved_product_mol,
            1.0e-12,
        )
        process = process_with_metrics(
            state.process,
            pre_separation_product_mol=initial_p,
            seed_target_mol=seed_target_mol,
            crystallized_from_solution_mol=crystallized_from_solution,
            crystal_yield=float(np.clip(crystallized_from_solution / initial_p, 0.0, 1.0)),
            seed_excluded_recovery=float(
                np.clip(crystallized_from_solution / initial_p, 0.0, 1.0)
            ),
            crystal_purity=float(np.clip(result.crystal_purity, 0.0, 1.0)),
            crystal_size=float(
                np.clip(result.crystal_size_distribution.d50_m / 250.0e-6, 0.0, 1.0)
            ),
            crystal_csd_quality=float(
                np.clip(
                    0.55
                    * (
                        1.0
                        - np.clip(
                            result.crystal_size_distribution.coefficient_of_variation,
                            0.0,
                            1.0,
                        )
                    )
                    + 0.45 * (1.0 - result.crystal_size_distribution.fines_number_fraction),
                    0.0,
                    1.0,
                )
            ),
            crystal_fines_fraction=float(
                np.clip(
                    result.crystal_size_distribution.fines_number_fraction,
                    0.0,
                    1.0,
                )
            ),
        )
        cooling_depth = float(np.clip((state.temperature_K - target_temperature) / 55.0, 0.0, 1.0))
        crystallization_heat = -dissolution_enthalpy * crystallized_from_solution
        thermal = account_temperature_transition(
            state=state,
            world=self.world,
            final_temperature_K=target_temperature,
            duration_s=max(duration, 1.0e-9),
            phase_change_heat_J=crystallization_heat,
        )
        ledger = state.ledger.with_updates(
            time_s=state.ledger.time_s + duration,
            cost=(
                state.ledger.cost
                + 0.018
                + duration / 3600.0 * 0.018
                + abs(thermal.jacket_energy_J) / 250_000.0
            ),
            risk=max(0.0, state.ledger.risk - 0.02 * cooling_depth),
            energy_jacket_J=state.ledger.energy_jacket_J + thermal.jacket_energy_J,
            heat_reaction_J=state.ledger.heat_reaction_J + thermal.phase_change_heat_J,
            heat_loss_J=state.ledger.heat_loss_J + thermal.heat_loss_J,
        )
        phases = _crystallization_phases(
            state,
            target_species=target_species,
            impurity_species=impurity_species,
            product_mol=crystallized,
            impurity_mol=occluded_impurity,
        )
        execution_history = list(crystallizer_settings.get("execution_history", ()))
        execution_history.append(
            {
                "execution_index": len(execution_history) + 1,
                "model_id": contract.model_id,
                "provider_path": contract.provider_path,
                "provider_manifest_hash": provider_manifest_hash,
                "initial_temperature_K": state.temperature_K,
                "final_temperature_K": target_temperature,
                "duration_s": duration,
                "seed_mass_g": seed_mass_g,
                "target_recovery": result.target_recovery,
                "crystal_purity": result.crystal_purity,
                "csd_d50_m": result.crystal_size_distribution.d50_m,
                "diagnostics": dict(provider_result.diagnostics),
                "provenance": list(provider_result.provenance),
            }
        )
        equipment = upsert_equipment_record(
            state.equipment,
            equipment_id="crystallizer",
            equipment_type="crystallizer",
            attached_vessel_id=state.vessel_id,
            status="completed",
            settings={
                "crystallization_model_id": result.model_id,
                "provider_path": contract.provider_path,
                "provider_manifest_hash": provider_manifest_hash,
                "provider_maturity": contract.maturity.value,
                "provider_role": contract.role.value,
                "provider_diagnostics": dict(provider_result.diagnostics),
                "provider_provenance": list(provider_result.provenance),
                "execution_history": execution_history,
                "execution_spec": execution_spec.to_dict(),
                "solubility_model_id": solubility.model_id,
                "reference_solubility_mol_L": reference_solubility,
                "reference_solubility_temperature_K": solubility.reference_temperature_K,
                "feed_concentration_mol_L": initial_concentration,
                "kinetics_model_id": kinetics.model_id,
                "seed_target_mol": seed_target_mol,
                "crystallized_from_solution_mol": crystallized_from_solution,
                "thermal_transition": thermal.to_dict(),
                "material_balance_error_mol": result.material_balance_error_mol,
                "component_balance_errors_mol": result.component_balance_errors_mol,
                "particle_target_balance_error_mol": (result.particle_target_balance_error_mol),
                "growth_solver_converged": result.growth_solver_converged,
                "growth_solver_iterations": result.growth_solver_iterations,
                "growth_solver_max_residual_mol": result.growth_solver_max_residual_mol,
                "cooling_rate_K_s": result.cooling_rate_K_s,
                "maximum_supersaturation_ratio": result.maximum_supersaturation_ratio,
                "final_supersaturation_ratio": result.final_supersaturation_ratio,
                "csd_d10_m": result.crystal_size_distribution.d10_m,
                "csd_d50_m": result.crystal_size_distribution.d50_m,
                "csd_d90_m": result.crystal_size_distribution.d90_m,
                "csd_cv": result.crystal_size_distribution.coefficient_of_variation,
                "csd_fines_number_fraction": (
                    result.crystal_size_distribution.fines_number_fraction
                ),
                "csd_total_particle_count": (result.crystal_size_distribution.total_particle_count),
                "csd_number_moment_0": result.crystal_size_distribution.number_moment_0,
                "csd_length_moment_1_m": (result.crystal_size_distribution.length_moment_1_m),
                "csd_area_moment_2_m2": (result.crystal_size_distribution.area_moment_2_m2),
                "csd_volume_moment_3_m3": (result.crystal_size_distribution.volume_moment_3_m3),
                "temperature_history_K": [
                    state.temperature_K,
                    *[step.temperature_K for step in result.step_reports],
                ],
                "supersaturation_history": [
                    step.supersaturation_ratio for step in result.step_reports
                ],
                "nucleation_history_per_L_s": [
                    step.nucleation_rate_per_L_s for step in result.step_reports
                ],
                "growth_history_m_s": [step.growth_rate_m_s for step in result.step_reports],
                "model_warnings": list(result.warnings),
                "provenance": result.provenance,
            },
        )
        metadata = {
            **state.metadata,
            "last_energy_transition": {
                "operation": "cool_crystallize",
                **thermal.to_dict(),
            },
        }
        return state.replace(
            temperature_K=target_temperature,
            ledger=ledger,
            process=process,
            phases=phases,
            equipment=equipment,
            metadata=metadata,
        )

    def filter_crystals(self, state: WorldState) -> WorldState:
        target_species = self.species_view.primary_target_species
        impurity_species = self.species_view.primary_impurity_species
        solid_product, solid_impurity = _solid_phase_amounts(
            state,
            target_species=target_species,
            impurity_species=impurity_species,
        )
        product = solid_product * 0.96
        impurity = solid_impurity * 0.92
        purity = product / max(product + impurity, 1.0e-12)
        process_metrics = {} if state.process is None else state.process.metrics
        crystallizer_settings = equipment_settings(state.equipment, "crystallizer")
        seed_target_mol = float(crystallizer_settings.get("seed_target_mol", 0.0))
        retained_seed_mol = min(seed_target_mol, solid_product) * 0.96
        product_from_solution = max(product - retained_seed_mol, 0.0)
        target_amount = max(self.species_view.target_amount(state) - seed_target_mol, 0.0)
        initial_p = max(
            float(process_metrics.get("pre_separation_product_mol", target_amount)),
            1.0e-12,
        )
        solvent_loss = min(
            1.0,
            float(process_metrics.get("solvent_loss", 0.0)) + 0.04,
        )
        process = process_with_metrics(
            state.process,
            pre_separation_product_mol=initial_p,
            solvent_loss=solvent_loss,
            retained_seed_mol=retained_seed_mol,
            filtered_product_from_solution_mol=product_from_solution,
            crystal_yield=float(np.clip(product_from_solution / initial_p, 0.0, 1.0)),
            seed_excluded_recovery=float(
                np.clip(product_from_solution / initial_p, 0.0, 1.0)
            ),
            crystal_purity=float(np.clip(purity, 0.0, 1.0)),
            recovery=float(np.clip(product_from_solution / initial_p, 0.0, 1.0)),
            purity=float(np.clip(purity, 0.0, 1.0)),
        )
        ledger = state.ledger.with_updates(
            time_s=state.ledger.time_s + 480.0,
            cost=state.ledger.cost + 0.026,
        )
        phases = _crystallization_phases(
            state,
            target_species=target_species,
            impurity_species=impurity_species,
            product_mol=product,
            impurity_mol=impurity,
            mother_liquor_volume_L=state.volume_L * 0.92,
        )
        phase_totals = phases.total_amounts_mol()
        filter_balance_error = max(
            (
                abs(state.species_amounts.get(species_id, 0.0) - amount_mol)
                for species_id, amount_mol in phase_totals.items()
            ),
            default=0.0,
        )
        equipment = upsert_equipment_record(
            state.equipment,
            equipment_id="crystal_filter",
            equipment_type="solid_liquid_filter",
            attached_vessel_id=state.vessel_id,
            status="completed",
            settings={
                "crystals_filtered": True,
                "filtered_product_mol": product,
                "retained_seed_mol": retained_seed_mol,
                "filtered_product_from_solution_mol": product_from_solution,
                "filtered_impurity_mol": impurity,
                "filter_purity": purity,
                "target_solid_retention_fraction": 0.96,
                "impurity_solid_retention_fraction": 0.92,
                "target_returned_to_filtrate_mol": solid_product - product,
                "impurity_returned_to_filtrate_mol": solid_impurity - impurity,
                "component_balance_error_mol": filter_balance_error,
                "provenance": [
                    "ChemWorld solid-liquid filtration retention ledger v1",
                    "coupled to cooling_crystallization_population_balance_v1 solid phase",
                ],
            },
        )
        return state.replace(
            ledger=ledger,
            phases=phases,
            process=process,
            equipment=equipment,
        )


__all__ = ["ChemWorldCrystallizationServices"]
