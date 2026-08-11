"""Distillation and evaporation process module for the shared ChemWorld law."""

from __future__ import annotations

from dataclasses import dataclass

from chemworld.world.operations import DISTILLATION_OPERATIONS


@dataclass(frozen=True)
class DistillationModuleSpec:
    module_id: str = "distillation"
    version: str = "0.1"
    operations: tuple[str, ...] = DISTILLATION_OPERATIONS
    laws: tuple[str, ...] = (
        "raoult_activity_vle_k_values",
        "constant_relative_volatility_shortcut",
        "fenske_distribution_ratio_identity",
        "thermal_risk_and_energy_cost",
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            "version": self.version,
            "operations": list(self.operations),
            "laws": list(self.laws),
            "tracked_metrics": ["distillate_purity", "distillate_recovery", "solvent_loss"],
        }


__all__ = ["DistillationModuleSpec"]
