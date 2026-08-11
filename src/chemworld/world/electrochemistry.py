"""Electrochemistry process module for the shared ChemWorld law."""

from __future__ import annotations

from dataclasses import dataclass

from chemworld.world.operations import ELECTROCHEMISTRY_OPERATIONS


@dataclass(frozen=True)
class ElectrochemistryModuleSpec:
    module_id: str = "electrochemistry"
    version: str = "0.3"
    operations: tuple[str, ...] = ELECTROCHEMISTRY_OPERATIONS
    laws: tuple[str, ...] = (
        "nernst_equilibrium_potential",
        "butler_volmer_current",
        "faradaic_charge_to_extent",
        "electrical_work_accounting",
        "diffusion_layer_limiting_current",
        "randles_double_layer_transient",
        "aqueous_activity_charge_balance",
        "solubility_product_hooks",
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            "version": self.version,
            "operations": list(self.operations),
            "laws": list(self.laws),
            "tracked_metrics": [
                "electrochemical_selectivity",
                "faradaic_efficiency",
                "energy_efficiency",
                "charge_C",
                "capacitive_charge_C",
                "charge_balance_residual_C",
                "material_balance_residual_mol",
                "energy_balance_residual_J",
                "electrolyte_pH",
                "electrolyte_ionic_strength_mol_kg",
                "yield",
            ],
        }


__all__ = ["ElectrochemistryModuleSpec"]
