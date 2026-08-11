"""Crystallization process module for the shared ChemWorld law."""

from __future__ import annotations

from dataclasses import dataclass

from chemworld.world.operations import CRYSTALLIZATION_OPERATIONS


@dataclass(frozen=True)
class CrystallizationModuleSpec:
    module_id: str = "crystallization"
    version: str = "0.3"
    operations: tuple[str, ...] = CRYSTALLIZATION_OPERATIONS
    laws: tuple[str, ...] = (
        "vanthoff_solubility_curve",
        "explicit_seed_mass",
        "primary_nucleation_and_growth_cohorts",
        "impurity_occlusion",
        "crystal_size_distribution",
        "filtration_recovery_ledger",
        "validated_runtime_provider",
        "temperature_and_supersaturation_history",
        "component_and_particle_moment_closure",
        "fail_closed_runtime_domain",
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "module_id": self.module_id,
            "version": self.version,
            "operations": list(self.operations),
            "laws": list(self.laws),
            "tracked_metrics": [
                "crystal_yield",
                "crystal_purity",
                "crystal_size",
                "supersaturation_history",
                "nucleation_history",
                "growth_history",
                "component_balance",
                "particle_size_moments",
            ],
            "runtime_policy": "validated_provider_fail_closed",
        }


__all__ = ["CrystallizationModuleSpec"]
