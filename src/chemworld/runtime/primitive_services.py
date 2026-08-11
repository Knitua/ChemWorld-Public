"""Primitive operation services for the transactional runtime."""

from __future__ import annotations

from typing import Any

import numpy as np

from chemworld.foundation import (
    WorldState,
    equipment_settings,
    process_with_metrics,
    scale_phase_ledger,
    upsert_equipment_record,
)
from chemworld.runtime.species import MechanismSpeciesView
from chemworld.world.actions import CATALYSTS, SOLVENTS
from chemworld.world.parameters import ChemWorldParameters
from chemworld.world.thermal_kernel import account_temperature_transition


def _action_float(action: dict[str, Any], key: str, default: float) -> float:
    value = action.get(key, default)
    return float(np.asarray(value).reshape(-1)[0])


def _action_index(action: dict[str, Any], key: str, default: int, count: int) -> int:
    return int(np.clip(int(_action_float(action, key, float(default))), 0, count - 1))


class ChemWorldPrimitiveOperationServices:
    """Apply primitive material, sampling, quench, evaporation, and penalty updates."""

    def __init__(self, world: ChemWorldParameters, species_view: MechanismSpeciesView) -> None:
        self.world = world
        self.species_view = species_view

    def add_reagent(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        amount = float(np.clip(_action_float(action, "amount_mol", 0.003), 0.0, 0.040))
        species = state.species_amounts.copy()
        reactant = self.species_view.reactant_species(state)
        for species_id, addition in self.species_view.reagent_charge_amounts(
            state,
            limiting_amount_mol=amount,
        ).items():
            species[species_id] = species.get(species_id, 0.0) + addition
        species_ledger = self.species_view.record_added_reactant(
            state.species,
            reactant_species=reactant,
            amount_mol=amount,
        )
        ledger = state.ledger.with_updates(cost=state.ledger.cost + 0.03 * amount / 0.01)
        return state.replace(species_amounts=species, ledger=ledger, species=species_ledger)

    def add_solvent(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        volume = float(np.clip(_action_float(action, "volume_L", 0.025), 0.0, 0.080))
        solvent = _action_index(action, "solvent", 0, len(SOLVENTS))
        previous_settings = equipment_settings(state.equipment, "batch_reactor")
        equipment = upsert_equipment_record(
            state.equipment,
            equipment_id="batch_reactor",
            equipment_type="batch_reactor",
            attached_vessel_id=state.vessel_id,
            status="configured",
            settings={
                "solvent": solvent,
                "solvent_volume_L": float(previous_settings.get("solvent_volume_L", 0.0))
                + volume,
            },
        )
        ledger = state.ledger.with_updates(
            cost=state.ledger.cost + volume * 8.0 * float(self.world.solvent_costs[solvent])
        )
        return state.replace(volume_L=state.volume_L + volume, ledger=ledger, equipment=equipment)

    def add_catalyst(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        amount = float(np.clip(_action_float(action, "catalyst_amount_mol", 0.00020), 0.0, 0.005))
        catalyst = _action_index(action, "catalyst", 0, len(CATALYSTS))
        previous_settings = equipment_settings(state.equipment, "batch_reactor")
        species = state.species_amounts.copy()
        active_catalyst = self.species_view.active_catalyst_species(state)
        if active_catalyst is not None:
            species[active_catalyst] = species.get(active_catalyst, 0.0) + amount
        equipment = upsert_equipment_record(
            state.equipment,
            equipment_id="batch_reactor",
            equipment_type="batch_reactor",
            attached_vessel_id=state.vessel_id,
            status="configured",
            settings={
                "catalyst": catalyst,
                "catalyst_amount_mol": float(
                    previous_settings.get("catalyst_amount_mol", 0.0)
                )
                + amount,
            },
        )
        ledger = state.ledger.with_updates(
            cost=state.ledger.cost
            + 4.0 * amount / 0.001 * float(self.world.catalyst_costs[catalyst])
        )
        return state.replace(species_amounts=species, ledger=ledger, equipment=equipment)

    def sample(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        volume = float(np.clip(_action_float(action, "sample_volume_L", 0.0001), 0.0, 0.002))
        volume = min(volume, max(state.volume_L, 0.0))
        fraction = 0.0 if state.volume_L <= 0 else volume / state.volume_L
        species = {key: value * (1.0 - fraction) for key, value in state.species_amounts.items()}
        ledger = state.ledger.with_updates(
            sample_consumed_L=state.ledger.sample_consumed_L + volume,
            cost=state.ledger.cost + 0.01,
        )
        return state.replace(
            species_amounts=species,
            phases=scale_phase_ledger(
                state.phases,
                amount_factor=1.0 - fraction,
                volume_factor=1.0 - fraction,
            ),
            volume_L=state.volume_L - volume,
            ledger=ledger,
        )

    def quench(self, state: WorldState) -> WorldState:
        target = max(298.15, state.temperature_K - 45.0)
        sensible_magnitude = abs(
            self.world.rho_cp_J_per_L_K * state.volume_L * (target - state.temperature_K)
        )
        duration = max(sensible_magnitude / 250.0, 1.0)
        thermal = account_temperature_transition(
            state=state,
            world=self.world,
            final_temperature_K=target,
            duration_s=duration,
        )
        ledger = state.ledger.with_updates(
            time_s=state.ledger.time_s + duration,
            cost=state.ledger.cost + 0.03 + abs(thermal.jacket_energy_J) / 250_000.0,
            energy_jacket_J=state.ledger.energy_jacket_J + thermal.jacket_energy_J,
            heat_loss_J=state.ledger.heat_loss_J + thermal.heat_loss_J,
        )
        metadata = {
            **state.metadata,
            "last_energy_transition": {"operation": "quench", **thermal.to_dict()},
        }
        return state.replace(
            temperature_K=target,
            quenched=True,
            ledger=ledger,
            metadata=metadata,
        )

    def evaporate(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        duration = float(np.clip(_action_float(action, "duration_s", 600.0), 0.0, 14_400.0))
        target_temperature = float(
            np.clip(_action_float(action, "target_temperature_K", 328.15), 298.15, 390.0)
        )
        removal = float(
            np.clip(
                0.08 + duration / 7200.0 + (target_temperature - 298.15) / 420.0,
                0.0,
                0.70,
            )
        )
        process_metrics = {} if state.process is None else state.process.metrics
        solvent_loss = min(
            1.0,
            float(process_metrics.get("solvent_loss", 0.0)) + removal,
        )
        process = process_with_metrics(state.process, solvent_loss=solvent_loss)
        ledger = state.ledger.with_updates(
            time_s=state.ledger.time_s + duration,
            cost=state.ledger.cost + duration / 3600.0 * 0.040,
            risk=min(1.0, state.ledger.risk + 0.04 * removal),
            energy_jacket_J=state.ledger.energy_jacket_J + 45.0 * duration,
        )
        return state.replace(
            volume_L=state.volume_L * (1.0 - 0.55 * removal),
            temperature_K=target_temperature,
            ledger=ledger,
            process=process,
        )

    def penalize_invalid(self, state: WorldState) -> WorldState:
        ledger = state.ledger.with_updates(
            cost=state.ledger.cost + 0.01,
            risk=min(1.0, state.ledger.risk + 0.08),
        )
        return state.replace(ledger=ledger)


__all__ = ["ChemWorldPrimitiveOperationServices"]
