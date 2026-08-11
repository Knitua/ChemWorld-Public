"""Reaction advancement and thermal-risk services for the transactional runtime."""

from __future__ import annotations

from typing import Any

import numpy as np

from chemworld.foundation import (
    WorldState,
    equipment_settings,
    process_with_metrics,
    upsert_equipment_record,
)
from chemworld.runtime.species import MechanismSpeciesView
from chemworld.world.parameters import ChemWorldParameters
from chemworld.world.reaction_kernel import integrate_compiled_reaction_ode
from chemworld.world.thermal_kernel import pressure_and_risk


def _action_float(action: dict[str, Any], key: str, default: float) -> float:
    value = action.get(key, default)
    return float(np.asarray(value).reshape(-1)[0])


def _bounded_action_float(
    action: dict[str, Any],
    key: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    value = _action_float(action, key, default)
    if not np.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{key} must be finite and in [{minimum}, {maximum}]")
    return value


class ChemWorldReactionThermalServices:
    """Advance reaction state and apply thermal pressure/risk ledgers."""

    def __init__(
        self,
        world: ChemWorldParameters,
        species_view: MechanismSpeciesView,
    ) -> None:
        self.world = world
        self.species_view = species_view

    def integrate(
        self,
        state: WorldState,
        action: dict[str, Any],
        *,
        heat: bool,
    ) -> WorldState:
        duration = _bounded_action_float(
            action,
            "duration_s",
            600.0,
            minimum=1.0,
            maximum=14_400.0,
        )
        target_temperature = _bounded_action_float(
            action,
            "target_temperature_K",
            state.temperature_K,
            minimum=250.0,
            maximum=520.0,
        )
        reactor_settings = equipment_settings(state.equipment, "batch_reactor")
        stirring_speed = _bounded_action_float(
            action,
            "stirring_speed_rpm",
            float(reactor_settings.get("stirring_speed_rpm", 600.0)),
            minimum=100.0,
            maximum=1200.0,
        )
        compiled_mechanism = self.species_view.mechanism
        if compiled_mechanism is None:
            raise RuntimeError("Reaction advancement requires a compiled mechanism")
        try:
            result = integrate_compiled_reaction_ode(
                state=state,
                world=self.world,
                compiled_mechanism=compiled_mechanism,
                duration_s=duration,
                target_temperature_K=target_temperature,
                heat=heat,
                stirring_speed_rpm=stirring_speed,
            )
        except (RuntimeError, ValueError):
            # The kernel transaction manager owns rollback.  Return a candidate
            # that deterministically fails the vessel-temperature constitution;
            # no physical or resource mutation from the failed model is kept.
            maximum_temperature = 470.0
            if state.vessels is not None and state.vessel_id in state.vessels.vessels:
                maximum_temperature = state.vessels.vessels[
                    state.vessel_id
                ].max_temperature_K
            return state.replace(temperature_K=maximum_temperature + 1.0)
        if result is None:
            raise RuntimeError("positive-duration reaction advance returned no result")
        ledger = state.ledger.with_updates(
            time_s=state.ledger.time_s + result.duration_s,
            cost=state.ledger.cost + result.cost_delta,
            energy_jacket_J=state.ledger.energy_jacket_J + result.energy_jacket_J,
            heat_reaction_J=state.ledger.heat_reaction_J + result.heat_reaction_J,
            heat_loss_J=state.ledger.heat_loss_J + result.heat_loss_J,
        )
        advance_index = int(reactor_settings.get("reaction_advance_index", 0)) + 1
        operation_type = "heat" if heat else "wait"
        equipment = upsert_equipment_record(
            state.equipment,
            equipment_id="batch_reactor",
            equipment_type="batch_reactor",
            attached_vessel_id=state.vessel_id,
            status="advanced",
            settings={
                "stirring_speed_rpm": result.stirring_speed_rpm,
                "reaction_advance_index": advance_index,
                "last_operation": operation_type,
                "last_operation_semantic": "advance",
                "repeat_semantic": "each committed repeat advances additional physical time",
                "runtime_provider_id": result.provider_id,
                "reaction_runtime_model_id": result.model_id,
                "reaction_model_id": result.provenance["reaction_network_model_id"],
                "reactor_model_id": result.provenance["reactor_model_id"],
                "reaction_network_id": result.provenance["network_id"],
                "mechanism_id": result.provenance["mechanism_id"],
                "mechanism_version": result.provenance["mechanism_version"],
                "mechanism_hash": result.provenance["mechanism_hash"],
                "solver_diagnostic": result.solver_diagnostic,
                "reactor_diagnostic": result.reactor_diagnostic,
                "termination_reason": result.termination_reason,
                "material_balance_error_mol": result.material_balance_error_mol,
                "maximum_conservation_drift_mol": result.maximum_conservation_drift_mol,
                "element_inventory_residuals_mol": result.element_inventory_residuals_mol,
                "charge_inventory_residual_mol": result.charge_inventory_residual_mol,
                "energy_balance_residual_J": result.energy_balance_residual_J,
                "trajectory_digest": result.trajectory_digest,
            },
        )
        process = process_with_metrics(
            state.process,
            reaction_advance_count=float(advance_index),
            reaction_cumulative_time_s=(
                float(
                    0.0
                    if state.process is None
                    else state.process.metrics.get("reaction_cumulative_time_s", 0.0)
                )
                + result.duration_s
            ),
        )
        return state.replace(
            species_amounts=result.species_amounts,
            temperature_K=result.temperature_K,
            ledger=ledger,
            equipment=equipment,
            process=process,
        )

    def with_risk_and_pressure(self, state: WorldState) -> WorldState:
        flow_settings = equipment_settings(state.equipment, "flow_reactor")
        pressure_override = flow_settings.get("outlet_pressure_Pa")
        pressure, risk = pressure_and_risk(
            state=state,
            solvent_risks=self.world.solvent_risks,
            pressure_override_Pa=(
                float(pressure_override)
                if isinstance(pressure_override, int | float)
                else None
            ),
        )
        return state.replace(pressure_Pa=pressure, ledger=state.ledger.with_updates(risk=risk))


__all__ = ["ChemWorldReactionThermalServices"]
