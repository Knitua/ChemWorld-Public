"""Instrument cost and destructive-sampling services for the transactional runtime."""

from __future__ import annotations

from math import isfinite
from typing import Any

from chemworld.foundation import (
    PhysicalConstitution,
    WorldState,
    equipment_settings,
    instrument_completed,
    instrument_equipment_id,
    scale_phase_ledger,
    upsert_equipment_record,
)
from chemworld.world.instruments import (
    INSTRUMENT_RUNTIME_MODEL_ID,
    INSTRUMENT_RUNTIME_PROVENANCE,
    INSTRUMENT_RUNTIME_PROVIDER_PATH,
    instrument_contracts,
    instrument_runtime_contract_hash,
)
from chemworld.world.operations import instrument_name


class ChemWorldInstrumentCostServices:
    """Apply measurement cost, sample consumption, and assay markers."""

    def __init__(self, constitution: PhysicalConstitution) -> None:
        self.constitution = constitution

    def apply_measurement_cost(self, state: WorldState, action: dict[str, Any]) -> WorldState:
        instrument_id = instrument_name(action.get("instrument", "hplc"))
        instrument = self.constitution.instruments.get(instrument_id)
        contract = instrument_contracts().get(instrument_id)
        if instrument is None or contract is None:
            raise ValueError(f"unsupported instrument: {instrument_id!r}")
        if instrument_id == "final_assay" and instrument_completed(state.equipment, "final_assay"):
            raise ValueError("final assay cannot be repeated")
        if not all(
            isfinite(value) and value >= 0.0
            for value in (state.volume_L, instrument.sample_volume_L, instrument.cost)
        ):
            raise ValueError("instrument cost and sampling domain must be finite and nonnegative")
        volume = float(instrument.sample_volume_L)
        if state.volume_L < volume:
            raise ValueError(
                f"insufficient sample volume for {instrument_id}: "
                f"required={volume}, available={state.volume_L}"
            )
        fraction = 0.0 if state.volume_L <= 0 else volume / state.volume_L
        species = {key: value * (1.0 - fraction) for key, value in state.species_amounts.items()}
        ledger = state.ledger.with_updates(
            cost=state.ledger.cost + instrument.cost,
            sample_consumed_L=state.ledger.sample_consumed_L + volume,
        )
        equipment_id = instrument_equipment_id(instrument_id)
        previous_settings = equipment_settings(state.equipment, equipment_id)
        use_count = int(previous_settings.get("use_count", 0)) + 1
        execution = {
            "measurement_index": use_count,
            "model_id": INSTRUMENT_RUNTIME_MODEL_ID,
            "provider_path": INSTRUMENT_RUNTIME_PROVIDER_PATH,
            "provider_contract_hash": instrument_runtime_contract_hash(),
            "maturity": "reference_validated",
            "role": "runtime",
            "provenance": list(INSTRUMENT_RUNTIME_PROVENANCE),
            "diagnostics": {
                "instrument_contract_loaded": True,
                "instrument_id": instrument_id,
                "sample_volume_sufficient": True,
                "sample_volume_exact": True,
                "final_assay_repeat_guard": instrument_id == "final_assay",
                "calibration_profile": contract.calibration_profile,
                "detection_contract": dict(contract.detection_contract),
                "saturation_contract": dict(contract.saturation_contract),
                "missingness_contract": dict(contract.missingness_contract),
            },
        }
        execution_history = list(previous_settings.get("execution_history", ()))
        execution_history.append(execution)
        equipment = upsert_equipment_record(
            state.equipment,
            equipment_id=equipment_id,
            equipment_type="instrument",
            attached_vessel_id=state.vessel_id,
            status="completed" if instrument_id == "final_assay" else "used",
            settings={
                "instrument_id": instrument_id,
                "last_time_s": state.ledger.time_s,
                "last_cost": instrument.cost,
                "last_sample_consumed_L": volume,
                "use_count": use_count,
                "model_id": INSTRUMENT_RUNTIME_MODEL_ID,
                "provider_path": INSTRUMENT_RUNTIME_PROVIDER_PATH,
                "provider_contract_hash": execution["provider_contract_hash"],
                "provenance": list(INSTRUMENT_RUNTIME_PROVENANCE),
                "diagnostics": execution["diagnostics"],
                "execution_history": execution_history,
            },
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
            equipment=equipment,
        )


__all__ = ["ChemWorldInstrumentCostServices"]
