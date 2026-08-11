"""Phase-ledger and downstream separation services for the transactional runtime."""

from __future__ import annotations

from typing import Any

import numpy as np

from chemworld.foundation import (
    WorldState,
    equipment_settings,
    upsert_equipment_record,
)
from chemworld.foundation.state import selected_phase_id
from chemworld.physchem.extraction_units import (
    DistributionCoefficientModelSpec,
)
from chemworld.physchem.phase_equilibrium_units import (
    LLEContactorSpec,
    StabilityAwareExtractionRequest,
    simulate_stability_aware_extraction,
)
from chemworld.runtime.phase_ledger_services import (
    ChemWorldPhaseLedgerServices,
    action_float,
    empty_phase,
)
from chemworld.runtime.species import MechanismSpeciesView
from chemworld.runtime.vnext_downstream import (
    PhaseSlice,
    run_bounded_transfer,
    run_sorbent_drying,
    run_vacuum_concentration,
)
from chemworld.world.actions import SOLVENTS
from chemworld.world.parameters import ChemWorldParameters
from chemworld.world.phase_kernel import (
    INDEPENDENT_NOMINAL_SOLVENT_EXTRACTANT_PAIR_V1,
    partition_split,
)
from chemworld.world.species_roles import PHASE_PRODUCT_AMOUNT_KEY


class ChemWorldPhaseSeparationServices:
    """Maintain phase ledgers and execute extraction-style separation steps."""

    def __init__(
        self,
        world: ChemWorldParameters,
        species_view: MechanismSpeciesView,
        *,
        nominal_pair_contract: str | None = None,
    ) -> None:
        if nominal_pair_contract not in {
            None,
            INDEPENDENT_NOMINAL_SOLVENT_EXTRACTANT_PAIR_V1,
        }:
            raise ValueError(
                f"Unsupported partition nominal-pair contract: {nominal_pair_contract!r}"
            )
        self.world = world
        self.species_view = species_view
        self.nominal_pair_contract = nominal_pair_contract
        self.phase_ledgers = ChemWorldPhaseLedgerServices(species_view)

    def add_phase(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        volume = float(np.clip(action_float(action, "volume_L", 0.015), 0.0, 0.060))
        phase_name = str(action.get("phase", "aqueous"))
        if phase_name not in {"aqueous", "organic"}:
            phase_name = "organic"
        phase_ledger = self.phase_ledgers.phase_ledger(state)
        phase = phase_ledger.setdefault(phase_name, empty_phase())
        phase["volume_L"] += volume
        ledger = state.ledger.with_updates(cost=state.ledger.cost + 0.015 + 0.35 * volume)
        return self.phase_ledgers.with_phase_ledger(
            state,
            phase_ledger,
            phase_settled=False,
            selected_phase=None,
            ledger=ledger,
            volume_L=state.volume_L + volume,
        )

    def add_extractant(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        volume = float(np.clip(action_float(action, "volume_L", 0.018), 0.0, 0.060))
        extractant = int(np.clip(action_float(action, "extractant", 3.0), 0, len(SOLVENTS) - 1))
        phase_ledger = self.phase_ledgers.phase_ledger(state)
        organic = phase_ledger.setdefault("organic", empty_phase())
        organic["volume_L"] += volume
        extractor_settings = equipment_settings(state.equipment, "liquid_liquid_extractor")
        equipment = upsert_equipment_record(
            state.equipment,
            equipment_id="liquid_liquid_extractor",
            equipment_type="liquid_liquid_extractor",
            attached_vessel_id=state.vessel_id,
            settings={
                "extractant": extractant,
                "extractant_volume_L": float(
                    extractor_settings.get("extractant_volume_L", 0.0)
                )
                + volume,
            },
        )
        risk = min(
            1.0,
            state.ledger.risk
            + 0.04
            + 0.05 * float(self.world.solvent_risks[extractant]),
        )
        ledger = state.ledger.with_updates(
            cost=state.ledger.cost + 0.025 + 0.80 * volume,
            risk=risk,
        )
        return self.phase_ledgers.with_phase_ledger(
            state,
            phase_ledger,
            metadata_updates={"extractant": extractant},
            phase_settled=False,
            selected_phase=None,
            ledger=ledger,
            volume_L=state.volume_L + volume,
            equipment=equipment,
        )

    def mix_phases(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        duration = float(np.clip(action_float(action, "duration_s", 180.0), 0.0, 1800.0))
        stirring = float(np.clip(action_float(action, "stirring_speed_rpm", 700.0), 100.0, 1200.0))
        phase_ledger = self.phase_ledgers.phase_ledger(state)
        phase_ledger.setdefault(
            "aqueous",
            {
                "volume_L": max(
                    state.volume_L - phase_ledger.get("organic", {}).get("volume_L", 0.0), 0.0
                ),
                PHASE_PRODUCT_AMOUNT_KEY: 0.0,
                "impurity_mol": 0.0,
                "solvent_loss": 0.0,
            },
        )
        organic = phase_ledger.setdefault("organic", empty_phase(0.015))
        aqueous = phase_ledger["aqueous"]
        reactor_liquid = phase_ledger.pop("reactor_liquid", None)
        if reactor_liquid is not None:
            aqueous["volume_L"] += float(reactor_liquid.get("volume_L", 0.0))
        p_total = self.phase_ledgers.phase_product_amount(state)
        impurity_total = self.phase_ledgers.phase_impurity_amount(state)
        extractor_settings = equipment_settings(state.equipment, "liquid_liquid_extractor")
        reactor_settings = equipment_settings(state.equipment, "batch_reactor")
        partition_inputs: dict[str, Any] = {}
        if (
            self.nominal_pair_contract
            == INDEPENDENT_NOMINAL_SOLVENT_EXTRACTANT_PAIR_V1
        ):
            solvent = int(reactor_settings.get("solvent", 0))
            partition_inputs = {
                "extractant": int(extractor_settings.get("extractant", solvent)),
                "nominal_pair_contract": self.nominal_pair_contract,
            }
        else:
            # Preserve the historical runtime law for every task/contract except
            # the explicitly selected partition v3 benchmark.
            solvent = int(
                extractor_settings.get(
                    "extractant",
                    reactor_settings.get("solvent", 0),
                )
            )
        split = partition_split(
            product_mol=p_total,
            impurity_mol=impurity_total,
            solvent=solvent,
            temperature_K=state.temperature_K,
            duration_s=duration,
            stirring_speed_rpm=stirring,
            organic_volume_L=organic["volume_L"],
            aqueous_volume_L=aqueous["volume_L"],
            coefficient_multiplier=self.world.domain_parameter(
                "partition_coefficient_multiplier"
            ),
            coefficient_exponent=self.world.domain_parameter(
                "partition_coefficient_exponent"
            ),
            phase_volume_multiplier=self.world.domain_parameter(
                "partition_phase_volume_multiplier"
            ),
            **partition_inputs,
        )
        organic[PHASE_PRODUCT_AMOUNT_KEY] = split["organic_product_mol"]
        aqueous[PHASE_PRODUCT_AMOUNT_KEY] = split["aqueous_product_mol"]
        organic["impurity_mol"] = split["organic_impurity_mol"]
        aqueous["impurity_mol"] = split["aqueous_impurity_mol"]
        equipment = upsert_equipment_record(
            state.equipment,
            equipment_id="phase_mixer",
            equipment_type="phase_mixer",
            attached_vessel_id=state.vessel_id,
            status="configured",
            settings={"stirring_speed_rpm": stirring},
        )
        ledger = state.ledger.with_updates(
            time_s=state.ledger.time_s + duration,
            cost=state.ledger.cost + 0.01 + duration / 3600.0 * 0.015,
        )
        return self.phase_ledgers.with_phase_ledger(
            state,
            phase_ledger,
            metadata_updates={
                "partition_coefficient": split["partition_coefficient"],
                "impurity_partition_coefficient": split["impurity_partition_coefficient"],
                "lle_phase_status": split["lle_phase_status"],
                "lle_minimum_tpd_like": split["lle_minimum_tpd_like"],
                "lle_partition_log_spread": split["lle_partition_log_spread"],
                "extraction_model_id": split["extraction_model_id"],
                "extraction_converged": split["extraction_converged"],
                "extraction_material_balance_error_mol": split[
                    "extraction_material_balance_error_mol"
                ],
                "extraction_entrained_aqueous_volume_L": split[
                    "extraction_entrained_aqueous_volume_L"
                ],
                "extraction_provenance": list(split["extraction_provenance"]),
            },
            phase_settled=False,
            ledger=ledger,
            equipment=equipment,
        )

    def settle_phases(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        duration = float(np.clip(action_float(action, "duration_s", 300.0), 0.0, 3600.0))
        phase_ledger = self.phase_ledgers.phase_ledger(state)
        ledger = state.ledger.with_updates(
            time_s=state.ledger.time_s + duration,
            cost=state.ledger.cost + duration / 3600.0 * 0.006,
        )
        return self.phase_ledgers.with_phase_ledger(
            state,
            phase_ledger,
            phase_settled=duration >= 60.0,
            ledger=ledger,
        )

    def separate_phase(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        target = str(action.get("target_phase", "organic"))
        if target not in {"organic", "aqueous"}:
            target = "organic"
        phase_ledger = self.phase_ledgers.phase_ledger(state)
        selected = phase_ledger.get(
            target,
            {
                "volume_L": state.volume_L,
                PHASE_PRODUCT_AMOUNT_KEY: self.phase_ledgers.phase_product_amount(state),
                "impurity_mol": 0.0,
                "solvent_loss": 0.0,
            },
        )
        entrained_volume_L = float(
            state.metadata.get("extraction_entrained_aqueous_volume_L", 0.0)
        )
        contact_volume_L = sum(
            max(float(values.get("volume_L", 0.0)), 0.0)
            for values in phase_ledger.values()
        )
        entrainment_fraction = float(
            np.clip(entrained_volume_L / max(contact_volume_L, 1.0e-12), 0.0, 1.0)
        )
        phase_ledger[target] = {
            "volume_L": selected["volume_L"],
            PHASE_PRODUCT_AMOUNT_KEY: selected[PHASE_PRODUCT_AMOUNT_KEY],
            "impurity_mol": selected["impurity_mol"],
            "solvent_loss": selected.get("solvent_loss", 0.0) + entrainment_fraction,
        }
        ledger = state.ledger.with_updates(cost=state.ledger.cost + 0.025)
        return self.phase_ledgers.with_phase_ledger(
            state,
            phase_ledger,
            phase_settled=True,
            selected_phase=target,
            ledger=ledger,
            volume_L=phase_ledger[target]["volume_L"],
        )

    def wash_phase(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        volume = float(np.clip(action_float(action, "wash_volume_L", 0.010), 0.0, 0.040))
        phase_ledger = self.phase_ledgers.phase_ledger(state)
        target = selected_phase_id(state.phases) or "organic"
        phase = phase_ledger.setdefault(
            target,
            {
                "volume_L": state.volume_L,
                PHASE_PRODUCT_AMOUNT_KEY: self.phase_ledgers.phase_product_amount(state),
                "impurity_mol": 0.0,
                "solvent_loss": 0.0,
            },
        )
        feed = {
            "product": max(float(phase[PHASE_PRODUCT_AMOUNT_KEY]), 0.0),
            "impurity": max(float(phase["impurity_mol"]), 0.0),
        }
        if sum(feed.values()) <= 0.0 or target != "organic":
            ledger = state.ledger.with_updates(
                cost=state.ledger.cost + 0.02 + 0.25 * volume
            )
            return self.phase_ledgers.with_phase_ledger(
                state,
                phase_ledger,
                selected_phase=target,
                ledger=ledger,
                volume_L=phase["volume_L"],
            )
        distribution_model = DistributionCoefficientModelSpec(
            model_id="runtime_wash_distribution_v1",
            component_ids=("product", "impurity"),
            intrinsic_partition_coefficients={
                "product": max(
                    float(state.metadata.get("partition_coefficient", 1.0)),
                    0.05,
                ),
                "impurity": max(
                    float(
                        state.metadata.get("impurity_partition_coefficient", 0.25)
                    ),
                    0.05,
                ),
            },
            provenance_id="chemworld-world-law-vnext-wash-policy",
        )
        result = simulate_stability_aware_extraction(
            StabilityAwareExtractionRequest(
                feed_amounts_mol=feed,
                distribution_model=distribution_model,
                target_component="product",
                contactor=LLEContactorSpec(
                    aqueous_volume_L=max(volume, 1.0e-9),
                    organic_volume_L=max(float(phase["volume_L"]), 1.0e-9),
                    extraction_stages=1,
                    extraction_stage_efficiency=0.95,
                    extraction_entrainment_fraction=0.01,
                    maximum_contact_volume_L=max(
                        volume + float(phase["volume_L"]), 0.10
                    ),
                ),
                temperature_K=state.temperature_K,
            )
        )
        retained = result.outlet("extract")
        removed = result.outlet("raffinate")
        stage = result.stage_reports[0]
        phase[PHASE_PRODUCT_AMOUNT_KEY] = retained["product"]
        phase["impurity_mol"] = retained["impurity"]
        phase["volume_L"] += stage.entrained_volume_L
        phase["solvent_loss"] += stage.entrained_volume_L / max(
            volume,
            1.0e-12,
        )
        wash_waste = phase_ledger.setdefault("wash_aqueous", empty_phase())
        wash_waste[PHASE_PRODUCT_AMOUNT_KEY] += removed["product"]
        wash_waste["impurity_mol"] += removed["impurity"]
        wash_waste["volume_L"] += max(
            volume - stage.entrained_volume_L,
            0.0,
        )
        ledger = state.ledger.with_updates(
            cost=state.ledger.cost + 0.02 + 0.25 * volume,
            risk=min(1.0, state.ledger.risk + 0.02 * (1.0 - result.impurity_rejection)),
        )
        return self.phase_ledgers.with_phase_ledger(
            state,
            phase_ledger,
            metadata_updates={
                "wash_model_id": result.model_id,
                "wash_distribution_model_id": result.distribution_model_id,
                "wash_material_balance_error_mol": result.material_balance_error_mol,
                "wash_converged": result.all_stages_converged,
                "wash_entrained_aqueous_volume_L": (
                    result.entrained_volume_L
                ),
                "wash_provenance": list(result.provenance),
            },
            selected_phase=target,
            ledger=ledger,
            volume_L=phase["volume_L"],
        )

    def dry_phase(self, state: WorldState) -> WorldState:
        phase_ledger = self.phase_ledgers.phase_ledger(state)
        target = selected_phase_id(state.phases) or "organic"
        phase = phase_ledger.setdefault(
            target,
            {
                "volume_L": state.volume_L,
                PHASE_PRODUCT_AMOUNT_KEY: self.phase_ledgers.phase_product_amount(state),
                "impurity_mol": 0.0,
                "solvent_loss": 0.0,
            },
        )
        phase_slice = PhaseSlice(
            product_mol=max(float(phase[PHASE_PRODUCT_AMOUNT_KEY]), 0.0),
            impurity_mol=max(float(phase["impurity_mol"]), 0.0),
            volume_L=max(float(phase["volume_L"]), 0.0),
            solvent_loss=max(float(phase.get("solvent_loss", 0.0)), 0.0),
        )
        metadata_updates: dict[str, Any] = {
            "drying_model_id": "chemworld_sorbent_drying_vnext",
            "drying_skipped_empty_phase": not phase_slice.has_material,
        }
        if phase_slice.has_material:
            result = run_sorbent_drying(phase_slice)
            phase[PHASE_PRODUCT_AMOUNT_KEY] = result.dried_liquid_amounts_mol.get(
                "product", 0.0
            )
            phase["impurity_mol"] = result.dried_liquid_amounts_mol.get(
                "impurity", 0.0
            )
            phase["volume_L"] = result.dried_liquid_volume_L
            phase["solvent_loss"] = result.residual_drying_component_fraction
            spent = phase_ledger.setdefault("spent_sorbent", empty_phase())
            spent[PHASE_PRODUCT_AMOUNT_KEY] += result.spent_sorbent_inventory_mol.get(
                "product", 0.0
            )
            spent["impurity_mol"] += result.spent_sorbent_inventory_mol.get(
                "impurity", 0.0
            )
            spent["volume_L"] += result.retained_liquid_volume_L
            metadata_updates.update(
                {
                    "drying_endpoint_met": result.endpoint_met,
                    "drying_material_balance_error_mol": result.material_balance_error_mol,
                    "drying_volume_balance_error_L": result.volume_balance_error_L,
                    "drying_product_recovery": result.product_recovery,
                    "drying_warnings": list(result.warnings),
                    "drying_provenance": list(result.provenance),
                    "drying_provider_path": (
                        "chemworld.physchem.drying_adapter_manifest."
                        "SorbentDryingProvider"
                    ),
                }
            )
        ledger = state.ledger.with_updates(
            time_s=state.ledger.time_s + 300.0, cost=state.ledger.cost + 0.018
        )
        equipment = upsert_equipment_record(
            state.equipment,
            equipment_id="sorbent_dryer",
            equipment_type="finite_capacity_sorbent_dryer",
            attached_vessel_id=state.vessel_id,
            status="dried",
            settings=metadata_updates,
        )
        return self.phase_ledgers.with_phase_ledger(
            state,
            phase_ledger,
            selected_phase=target,
            ledger=ledger,
            volume_L=phase["volume_L"],
            equipment=equipment,
        )

    def concentrate_phase(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        duration = float(np.clip(action_float(action, "duration_s", 300.0), 0.0, 3600.0))
        phase_ledger = self.phase_ledgers.phase_ledger(state)
        target = selected_phase_id(state.phases) or "organic"
        phase = phase_ledger.setdefault(
            target,
            {
                "volume_L": state.volume_L,
                PHASE_PRODUCT_AMOUNT_KEY: self.phase_ledgers.phase_product_amount(state),
                "impurity_mol": 0.0,
                "solvent_loss": 0.0,
            },
        )
        phase_slice = PhaseSlice(
            product_mol=max(float(phase[PHASE_PRODUCT_AMOUNT_KEY]), 0.0),
            impurity_mol=max(float(phase["impurity_mol"]), 0.0),
            volume_L=max(float(phase["volume_L"]), 0.0),
            solvent_loss=max(float(phase.get("solvent_loss", 0.0)), 0.0),
        )
        metadata_updates: dict[str, Any] = {
            "concentration_model_id": "chemworld_vacuum_concentration_vnext",
            "concentration_skipped_empty_phase": not phase_slice.has_material,
        }
        concentration_extent = 0.0
        heat_duty_J = 0.0
        if phase_slice.has_material:
            result = run_vacuum_concentration(
                phase_slice,
                initial_temperature_K=state.temperature_K,
                duration_s=duration,
            )
            phase[PHASE_PRODUCT_AMOUNT_KEY] = result.liquid_amounts_mol.get("product", 0.0)
            phase["impurity_mol"] = result.liquid_amounts_mol.get("impurity", 0.0)
            phase["volume_L"] = result.final_equivalent_liquid_volume_L
            condensate = phase_ledger.setdefault("concentrate_condensate", empty_phase())
            condensate[PHASE_PRODUCT_AMOUNT_KEY] += result.condensate_amounts_mol.get(
                "product", 0.0
            )
            condensate["impurity_mol"] += result.condensate_amounts_mol.get(
                "impurity", 0.0
            )
            condensate["volume_L"] += result.condensate_equivalent_liquid_volume_L
            vent = phase_ledger.setdefault("concentrate_vent", empty_phase())
            vent[PHASE_PRODUCT_AMOUNT_KEY] += result.vent_amounts_mol.get("product", 0.0)
            vent["impurity_mol"] += result.vent_amounts_mol.get("impurity", 0.0)
            vent["volume_L"] += result.vent_equivalent_liquid_volume_L
            concentration_extent = 1.0 - result.solvent_remaining_fraction
            phase["solvent_loss"] += concentration_extent
            heat_duty_J = result.heat_duty_J
            metadata_updates.update(
                {
                    "concentration_endpoint_met": result.endpoint_met,
                    "concentration_termination_reason": result.termination_reason,
                    "concentration_material_balance_error_mol": (
                        result.material_balance_error_mol
                    ),
                    "concentration_energy_balance_error_J": result.energy_balance_error_J,
                    "concentration_target_recovery": result.target_recovery,
                    "concentration_warnings": list(result.warnings),
                    "concentration_provenance": list(result.provenance),
                    "concentration_provider_path": (
                        "chemworld.physchem.concentration_adapter_manifest."
                        "VacuumConcentrationProvider"
                    ),
                }
            )
        ledger = state.ledger.with_updates(
            time_s=state.ledger.time_s + duration,
            cost=state.ledger.cost + duration / 3600.0 * 0.035,
            risk=min(1.0, state.ledger.risk + 0.015 * concentration_extent),
            energy_jacket_J=state.ledger.energy_jacket_J + heat_duty_J,
        )
        equipment = upsert_equipment_record(
            state.equipment,
            equipment_id="vacuum_concentrator",
            equipment_type="energy_limited_vacuum_concentrator",
            attached_vessel_id=state.vessel_id,
            status="concentrated",
            settings=metadata_updates,
        )
        return self.phase_ledgers.with_phase_ledger(
            state,
            phase_ledger,
            selected_phase=target,
            ledger=ledger,
            volume_L=phase["volume_L"],
            equipment=equipment,
        )

    def transfer_phase(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        fraction = float(np.clip(action_float(action, "transfer_fraction", 0.98), 0.0, 1.0))
        phase_ledger = self.phase_ledgers.phase_ledger(state)
        target = selected_phase_id(state.phases) or "organic"
        phase = phase_ledger.setdefault(
            target,
            {
                "volume_L": state.volume_L,
                PHASE_PRODUCT_AMOUNT_KEY: self.phase_ledgers.phase_product_amount(state),
                "impurity_mol": 0.0,
                "solvent_loss": 0.0,
            },
        )
        phase_slice = PhaseSlice(
            product_mol=max(float(phase[PHASE_PRODUCT_AMOUNT_KEY]), 0.0),
            impurity_mol=max(float(phase["impurity_mol"]), 0.0),
            volume_L=max(float(phase["volume_L"]), 0.0),
            solvent_loss=max(float(phase.get("solvent_loss", 0.0)), 0.0),
        )
        metadata_updates: dict[str, Any] = {
            "transfer_model_id": "chemworld_transfer_holdup_vnext",
            "transfer_skipped_empty_phase": not phase_slice.has_material,
        }
        delivered_fraction = 0.0
        if phase_slice.has_material:
            result = run_bounded_transfer(phase_slice, fraction=fraction)
            phase[PHASE_PRODUCT_AMOUNT_KEY] = result.target_delivered_amounts_mol.get(
                "product", 0.0
            )
            phase["impurity_mol"] = result.target_delivered_amounts_mol.get(
                "impurity", 0.0
            )
            phase["volume_L"] = result.target_delivered_volume_L
            source_heel = phase_ledger.setdefault("transfer_source_heel", empty_phase())
            source_heel[PHASE_PRODUCT_AMOUNT_KEY] += result.source_remaining_amounts_mol.get(
                "product", 0.0
            )
            source_heel["impurity_mol"] += result.source_remaining_amounts_mol.get(
                "impurity", 0.0
            )
            source_heel["volume_L"] += result.source_remaining_volume_L
            line_holdup = phase_ledger.setdefault("transfer_line_holdup", empty_phase())
            line_holdup[PHASE_PRODUCT_AMOUNT_KEY] += result.final_line_amounts_mol.get(
                "product", 0.0
            )
            line_holdup["impurity_mol"] += result.final_line_amounts_mol.get(
                "impurity", 0.0
            )
            line_holdup["volume_L"] += result.final_line_volume_L
            delivered_fraction = result.overall_source_delivery_fraction
            phase["solvent_loss"] += 1.0 - delivered_fraction
            metadata_updates.update(
                {
                    "transfer_material_balance_error_mol": result.material_balance_error_mol,
                    "transfer_volume_balance_error_L": result.volume_balance_error_L,
                    "transfer_source_heel_volume_L": result.source_remaining_volume_L,
                    "transfer_line_holdup_volume_L": result.final_line_volume_L,
                    "transfer_delivery_fraction": delivered_fraction,
                    "transfer_warnings": list(result.warnings),
                    "transfer_provenance": list(result.provenance),
                    "transfer_provider_path": (
                        "chemworld.physchem.transfer_adapter_manifest."
                        "TransferUnitProvider"
                    ),
                }
            )
        ledger = state.ledger.with_updates(cost=state.ledger.cost + 0.01)
        equipment = upsert_equipment_record(
            state.equipment,
            equipment_id="transfer_line",
            equipment_type="finite_holdup_transfer_line",
            attached_vessel_id=state.vessel_id,
            status="transferred",
            settings=metadata_updates,
        )
        return self.phase_ledgers.with_phase_ledger(
            state,
            phase_ledger,
            selected_phase=target,
            ledger=ledger,
            volume_L=phase["volume_L"],
            equipment=equipment,
        )


__all__ = ["ChemWorldPhaseSeparationServices"]
