"""Chemical ontology primitives used by ChemWorld environments."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Substance:
    id: str
    name: str
    formula: dict[str, int]
    phase: str = "liquid"
    role: str = "species"

    def to_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class Phase:
    id: str
    name: str

    def to_dict(self) -> dict[str, str]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class Vessel:
    id: str
    name: str
    max_volume_L: float
    max_temperature_K: float
    max_pressure_Pa: float

    def to_dict(self) -> dict[str, float | str]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class Instrument:
    id: str
    name: str
    observable_keys: tuple[str, ...]
    cost: float
    sample_volume_L: float
    noise_std: dict[str, float]
    requires_terminated: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "observable_keys": list(self.observable_keys),
            "cost": self.cost,
            "sample_volume_L": self.sample_volume_L,
            "noise_std": self.noise_std,
            "requires_terminated": self.requires_terminated,
        }


@dataclass(frozen=True)
class Operation:
    id: str
    name: str
    required_fields: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "required_fields": list(self.required_fields),
            "preconditions": list(self.preconditions),
        }


@dataclass(frozen=True)
class Reaction:
    id: str
    name: str
    stoichiometry: dict[str, float]
    delta_h_J_per_mol: float

    def to_dict(self) -> dict[str, object]:
        return self.__dict__.copy()


@dataclass(frozen=True)
class StateVariable:
    id: str
    unit: str
    hidden: bool = True
    description: str = ""
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "unit": self.unit,
            "hidden": self.hidden,
            "description": self.description,
            "metadata": self.metadata,
        }

