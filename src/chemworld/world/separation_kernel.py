"""Downstream separation-law module for ChemWorld."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from chemworld.foundation import WorldState
from chemworld.foundation.state import selected_phase_id
from chemworld.world.species_roles import PHASE_PRODUCT_AMOUNT_KEY


def _typed_phase_ledger_entries(
    state: WorldState,
    *,
    target_species: tuple[str, ...] = (),
    impurity_species: tuple[str, ...] = (),
) -> dict[str, dict[str, float]]:
    if state.phases is None:
        return {}
    entries: dict[str, dict[str, float]] = {}
    for phase_id, phase in state.phases.phases.items():
        product_amount = (
            sum(
                float(phase.species_amounts_mol.get(species_id, 0.0))
                for species_id in target_species
            )
            if target_species
            else 0.0
        )
        impurity_amount = (
            sum(
                float(phase.species_amounts_mol.get(species_id, 0.0))
                for species_id in impurity_species
            )
            if impurity_species
            else 0.0
        )
        entries[phase_id] = {
            "volume_L": float(phase.volume_L),
            PHASE_PRODUCT_AMOUNT_KEY: product_amount,
            "impurity_mol": impurity_amount,
            "solvent_loss": 0.0,
        }
    return entries


def downstream_truth_values(
    state: WorldState,
    phase_ledger: dict[str, dict[str, float]] | None = None,
    *,
    product_amount_mol: float | None = None,
    impurity_amount_mol: float | None = None,
    initial_product_mol: float | None = None,
    target_species: tuple[str, ...] = (),
    impurity_species: tuple[str, ...] = (),
) -> dict[str, float]:
    phase_ledger = phase_ledger or _typed_phase_ledger_entries(
        state,
        target_species=target_species,
        impurity_species=impurity_species,
    )
    phase_product_total = sum(
        float(entry.get(PHASE_PRODUCT_AMOUNT_KEY, 0.0)) for entry in phase_ledger.values()
    )
    phase_impurity_total = sum(
        float(entry.get("impurity_mol", 0.0)) for entry in phase_ledger.values()
    )
    product_amount = (
        float(product_amount_mol) if product_amount_mol is not None else phase_product_total
    )
    impurity_amount = (
        float(impurity_amount_mol) if impurity_amount_mol is not None else phase_impurity_total
    )
    process_metrics = {} if state.process is None else state.process.metrics
    initial_p = max(
        (
            float(initial_product_mol)
            if initial_product_mol is not None
            else float(process_metrics.get("pre_separation_product_mol", product_amount))
        ),
        product_amount,
        1.0e-12,
    )
    organic = phase_ledger.get("organic", {})
    aqueous = phase_ledger.get("aqueous", {})
    selected_phase = selected_phase_id(state.phases) or "organic"
    selected = phase_ledger.get(selected_phase, organic or aqueous or {})
    product_in_organic = float(organic.get(PHASE_PRODUCT_AMOUNT_KEY, 0.0))
    product_in_aqueous = float(aqueous.get(PHASE_PRODUCT_AMOUNT_KEY, 0.0))
    selected_product = float(
        selected.get(
            PHASE_PRODUCT_AMOUNT_KEY,
            product_amount,
        )
    )
    selected_impurity = float(
        selected.get(
            "impurity_mol",
            impurity_amount,
        )
    )
    organic_volume = float(organic.get("volume_L", 0.0))
    aqueous_volume = float(aqueous.get("volume_L", max(state.volume_L - organic_volume, 0.0)))
    # Numerical closure is a control-volume property of every typed phase,
    # including waste, condensate, spent sorbent, source heel, and line hold-up.
    # Restricting this sum to the two contact phases turns explicit downstream
    # inventories into a fictitious mass-balance error.
    total_phase_product = phase_product_total
    purity = selected_product / max(selected_product + selected_impurity, 1.0e-12)
    recovery = selected_product / initial_p
    phase_ratio = organic_volume / max(organic_volume + aqueous_volume, 1.0e-12)
    solvent_loss = float(process_metrics.get("solvent_loss", 0.0))
    mass_balance_error = abs(total_phase_product - product_amount) / initial_p
    return {
        "purity": float(np.clip(purity, 0.0, 1.0)),
        "recovery": float(np.clip(recovery, 0.0, 1.0)),
        "phase_ratio": float(np.clip(phase_ratio, 0.0, 1.0)),
        "product_in_organic": float(np.clip(product_in_organic / initial_p, 0.0, 1.0)),
        "product_in_aqueous": float(np.clip(product_in_aqueous / initial_p, 0.0, 1.0)),
        "impurity_signal": float(np.clip(selected_impurity / initial_p, 0.0, 1.0)),
        "solvent_loss": float(np.clip(solvent_loss, 0.0, 1.0)),
        "process_mass_balance_error": float(np.clip(mass_balance_error, 0.0, 1.0)),
        "crystal_yield": float(np.clip(float(process_metrics.get("crystal_yield", 0.0)), 0.0, 1.0)),
        "crystal_purity": float(
            np.clip(float(process_metrics.get("crystal_purity", 0.0)), 0.0, 1.0)
        ),
        "crystal_size": float(np.clip(float(process_metrics.get("crystal_size", 0.0)), 0.0, 1.0)),
        "crystal_csd_quality": float(
            np.clip(float(process_metrics.get("crystal_csd_quality", 0.0)), 0.0, 1.0)
        ),
        "crystal_fines_fraction": float(
            np.clip(float(process_metrics.get("crystal_fines_fraction", 0.0)), 0.0, 1.0)
        ),
        "distillate_purity": float(
            np.clip(float(process_metrics.get("distillate_purity", 0.0)), 0.0, 1.0)
        ),
        "distillate_recovery": float(
            np.clip(float(process_metrics.get("distillate_recovery", 0.0)), 0.0, 1.0)
        ),
        "flow_conversion": float(
            np.clip(float(process_metrics.get("flow_conversion", 0.0)), 0.0, 1.0)
        ),
        "electrochemical_selectivity": float(
            np.clip(
                float(process_metrics.get("electrochemical_selectivity", 0.0)),
                0.0,
                1.0,
            )
        ),
        "selective_product_yield": float(
            np.clip(float(process_metrics.get("selective_product_yield", 0.0)), 0.0, 1.0)
        ),
        "electrochemical_conversion": float(
            np.clip(float(process_metrics.get("electrochemical_conversion", 0.0)), 0.0, 1.0)
        ),
        "faradaic_efficiency": float(
            np.clip(float(process_metrics.get("faradaic_efficiency", 0.0)), 0.0, 1.0)
        ),
        "transport_efficiency": float(
            np.clip(float(process_metrics.get("transport_efficiency", 0.0)), 0.0, 1.0)
        ),
        "ohmic_efficiency": float(
            np.clip(float(process_metrics.get("ohmic_efficiency", 0.0)), 0.0, 1.0)
        ),
        "energy_efficiency": float(
            np.clip(float(process_metrics.get("energy_efficiency", 0.0)), 0.0, 1.0)
        ),
    }


@dataclass(frozen=True)
class SeparationModuleSpec:
    module_id: str = "separation"
    version: str = "0.4"
    operations: tuple[str, ...] = (
        "add_phase",
        "add_extractant",
        "mix",
        "settle",
        "separate_phase",
        "wash",
        "dry",
        "concentrate",
        "transfer",
    )
    laws: tuple[str, ...] = (
        "activity_corrected_extraction_and_wash",
        "explicit_entrainment_and_material_balance",
        "selected_phase_recovery_and_purity",
        "bounded_dry_concentrate_transfer_fallbacks",
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            "version": self.version,
            "operations": list(self.operations),
            "laws": list(self.laws),
            "tracked_metrics": [
                "purity",
                "recovery",
                "phase_ratio",
                "process_mass_balance_error",
            ],
        }


__all__ = ["SeparationModuleSpec", "downstream_truth_values"]
