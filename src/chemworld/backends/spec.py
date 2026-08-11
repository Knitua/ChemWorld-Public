"""Backend metadata for physical-chemical transition implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from chemworld.world.parameters import WORLD_FAMILY_VERSION


@dataclass(frozen=True)
class BackendSpec:
    backend_id: str
    fidelity: str
    transition_modules: tuple[str, ...]
    supported_world_laws: tuple[str, ...]
    external_dependencies: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "fidelity": self.fidelity,
            "transition_modules": list(self.transition_modules),
            "supported_world_laws": list(self.supported_world_laws),
            "external_dependencies": list(self.external_dependencies),
            "description": self.description,
        }


def semi_mechanistic_backend_spec() -> BackendSpec:
    return BackendSpec(
        backend_id="semi_mechanistic",
        fidelity="qualitative-semi-mechanistic",
        transition_modules=(
            "reaction_ode",
            "phase_partition",
            "separation",
            "crystallization",
            "distillation",
            "continuous_flow",
            "electrochemistry",
            "instrument_cost",
        ),
        supported_world_laws=(WORLD_FAMILY_VERSION,),
        description=(
            "Default ChemWorld backend using compiled reaction networks, typed "
            "material and energy ledgers, maturity-labeled process modules, and "
            "instrument-cost contracts."
        ),
    )
