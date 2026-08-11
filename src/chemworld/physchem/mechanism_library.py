"""Curated mechanism and scenario-card library for ChemWorld."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from chemworld.physchem.reaction_network import ReactionNetworkSpec, load_mechanism

MECHANISM_SCENARIO_SCHEMA_VERSION = "mechanism_scenario_card_v1"


@dataclass(frozen=True)
class MechanismScenarioCard:
    card_id: str
    mechanism_id: str
    mechanism_path: str
    scenario_id: str
    family: str
    recommended_reactor: str
    module_tags: tuple[str, ...]
    initial_amounts_mol: dict[str, float]
    default_conditions: dict[str, float]
    operating_window: dict[str, dict[str, float]]
    target_species: tuple[str, ...]
    impurity_species: tuple[str, ...]
    recommended_tasks: tuple[str, ...]
    expected_qualitative_behavior: tuple[str, ...]
    validation_notes: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MechanismScenarioCard:
        required = (
            "card_id",
            "mechanism_id",
            "mechanism_path",
            "scenario_id",
            "family",
            "recommended_reactor",
            "module_tags",
            "initial_amounts_mol",
            "default_conditions",
            "operating_window",
            "target_species",
            "impurity_species",
            "recommended_tasks",
            "expected_qualitative_behavior",
        )
        missing = [key for key in required if key not in payload]
        if missing:
            raise ValueError(f"Mechanism scenario card is missing fields: {missing}")
        initial_amounts = _float_mapping(payload["initial_amounts_mol"], "initial_amounts_mol")
        if any(value < 0.0 for value in initial_amounts.values()):
            raise ValueError("initial_amounts_mol cannot contain negative values")
        default_conditions = _float_mapping(payload["default_conditions"], "default_conditions")
        operating_window = _window_mapping(payload["operating_window"])
        return cls(
            card_id=str(payload["card_id"]),
            mechanism_id=str(payload["mechanism_id"]),
            mechanism_path=str(payload["mechanism_path"]),
            scenario_id=str(payload["scenario_id"]),
            family=str(payload["family"]),
            recommended_reactor=str(payload["recommended_reactor"]),
            module_tags=_string_tuple(payload["module_tags"], "module_tags"),
            initial_amounts_mol=initial_amounts,
            default_conditions=default_conditions,
            operating_window=operating_window,
            target_species=_string_tuple(payload["target_species"], "target_species"),
            impurity_species=_string_tuple(payload["impurity_species"], "impurity_species"),
            recommended_tasks=_string_tuple(payload["recommended_tasks"], "recommended_tasks"),
            expected_qualitative_behavior=_string_tuple(
                payload["expected_qualitative_behavior"],
                "expected_qualitative_behavior",
            ),
            validation_notes=_string_tuple(
                payload.get("validation_notes", ()),
                "validation_notes",
            ),
        )

    @property
    def resolved_mechanism_path(self) -> Path:
        path = Path(self.mechanism_path)
        if path.is_absolute():
            return path
        if path.parts and path.parts[0] == "configs":
            return configuration_root().joinpath(*path.parts[1:])
        return repository_root() / path

    def to_dict(self) -> dict[str, object]:
        return {
            "card_id": self.card_id,
            "mechanism_id": self.mechanism_id,
            "mechanism_path": self.mechanism_path,
            "scenario_id": self.scenario_id,
            "family": self.family,
            "recommended_reactor": self.recommended_reactor,
            "module_tags": list(self.module_tags),
            "initial_amounts_mol": dict(self.initial_amounts_mol),
            "default_conditions": dict(self.default_conditions),
            "operating_window": {key: dict(value) for key, value in self.operating_window.items()},
            "target_species": list(self.target_species),
            "impurity_species": list(self.impurity_species),
            "recommended_tasks": list(self.recommended_tasks),
            "expected_qualitative_behavior": list(self.expected_qualitative_behavior),
            "validation_notes": list(self.validation_notes),
        }


@dataclass(frozen=True)
class MechanismLibraryValidationReport:
    schema_version: str
    cards_checked: int
    mechanisms_checked: int
    duplicate_card_ids: tuple[str, ...]
    duplicate_mechanism_ids: tuple[str, ...]
    missing_mechanism_files: tuple[str, ...]
    missing_cards_for_files: tuple[str, ...]
    element_balance_failures: tuple[str, ...]
    initial_species_errors: tuple[str, ...]
    target_species_errors: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not (
            self.duplicate_card_ids
            or self.duplicate_mechanism_ids
            or self.missing_mechanism_files
            or self.missing_cards_for_files
            or self.element_balance_failures
            or self.initial_species_errors
            or self.target_species_errors
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "cards_checked": self.cards_checked,
            "mechanisms_checked": self.mechanisms_checked,
            "passed": self.passed,
            "duplicate_card_ids": list(self.duplicate_card_ids),
            "duplicate_mechanism_ids": list(self.duplicate_mechanism_ids),
            "missing_mechanism_files": list(self.missing_mechanism_files),
            "missing_cards_for_files": list(self.missing_cards_for_files),
            "element_balance_failures": list(self.element_balance_failures),
            "initial_species_errors": list(self.initial_species_errors),
            "target_species_errors": list(self.target_species_errors),
        }


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def packaged_configuration_root() -> Path:
    """Return the wheel-installed configuration resource directory."""

    return Path(__file__).resolve().parents[1] / "resources" / "configs"


def configuration_root() -> Path:
    """Resolve packaged resources first, with a source-checkout fallback."""

    packaged = packaged_configuration_root()
    return packaged if packaged.is_dir() else repository_root() / "configs"


def mechanism_library_root() -> Path:
    return configuration_root() / "mechanisms"


def mechanism_scenario_library_path() -> Path:
    return configuration_root() / "scenarios" / "mechanism_scenarios.yaml"


def list_mechanism_paths() -> list[Path]:
    root = mechanism_library_root()
    if not root.exists():
        return []
    suffixes = {".json", ".yaml", ".yml"}
    return sorted(path for path in root.iterdir() if path.suffix.lower() in suffixes)


def list_mechanism_cards(path: str | Path | None = None) -> list[MechanismScenarioCard]:
    source = mechanism_scenario_library_path() if path is None else Path(path)
    payload = yaml.safe_load(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Mechanism scenario library must contain a mapping")
    schema_version = str(payload.get("schema_version", ""))
    if schema_version != MECHANISM_SCENARIO_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported mechanism scenario schema version: "
            f"{schema_version!r}; expected {MECHANISM_SCENARIO_SCHEMA_VERSION!r}"
        )
    cards_payload = payload.get("cards", ())
    if not isinstance(cards_payload, list):
        raise ValueError("Mechanism scenario library 'cards' must be a list")
    return [MechanismScenarioCard.from_dict(item) for item in cards_payload]


def get_mechanism_card(card_or_mechanism_id: str) -> MechanismScenarioCard:
    for card in list_mechanism_cards():
        if card.card_id == card_or_mechanism_id or card.mechanism_id == card_or_mechanism_id:
            return card
    available = ", ".join(card.mechanism_id for card in list_mechanism_cards())
    raise KeyError(
        f"Unknown mechanism card or mechanism_id={card_or_mechanism_id!r}. "
        f"Available mechanisms: {available}"
    )


def load_library_mechanism(
    card_or_mechanism_id: str | MechanismScenarioCard,
) -> ReactionNetworkSpec:
    card = (
        card_or_mechanism_id
        if isinstance(card_or_mechanism_id, MechanismScenarioCard)
        else get_mechanism_card(card_or_mechanism_id)
    )
    mechanism = load_mechanism(card.resolved_mechanism_path)
    if mechanism.network_id != card.mechanism_id:
        raise ValueError(
            f"Card {card.card_id} expects mechanism_id={card.mechanism_id!r}, "
            f"but file contains network_id={mechanism.network_id!r}"
        )
    return mechanism


def validate_mechanism_library() -> MechanismLibraryValidationReport:
    cards = list_mechanism_cards()
    duplicate_card_ids = _duplicates(card.card_id for card in cards)
    duplicate_mechanism_ids = _duplicates(card.mechanism_id for card in cards)
    card_paths = {card.resolved_mechanism_path.resolve() for card in cards}
    known_paths = {path.resolve() for path in list_mechanism_paths()}
    missing_mechanism_files = tuple(
        _relative_to_repo(card.resolved_mechanism_path)
        for card in cards
        if not card.resolved_mechanism_path.exists()
    )
    missing_cards_for_files = tuple(
        _relative_to_repo(path) for path in sorted(known_paths - card_paths)
    )
    element_balance_failures: list[str] = []
    initial_species_errors: list[str] = []
    target_species_errors: list[str] = []
    mechanisms_checked = 0
    for card in cards:
        if not card.resolved_mechanism_path.exists():
            continue
        try:
            mechanism = load_library_mechanism(card)
        except ValueError as exc:
            element_balance_failures.append(f"{card.mechanism_id}: {exc}")
            continue
        mechanisms_checked += 1
        if not mechanism.check_element_balance():
            element_balance_failures.append(card.mechanism_id)
        species = set(mechanism.species_ids)
        unknown_initial = sorted(set(card.initial_amounts_mol) - species)
        if unknown_initial:
            initial_species_errors.append(
                f"{card.mechanism_id}: initial species not in mechanism: {unknown_initial}"
            )
        unknown_scored = sorted((set(card.target_species) | set(card.impurity_species)) - species)
        if unknown_scored:
            target_species_errors.append(
                f"{card.mechanism_id}: scored species not in mechanism: {unknown_scored}"
            )
    return MechanismLibraryValidationReport(
        schema_version=MECHANISM_SCENARIO_SCHEMA_VERSION,
        cards_checked=len(cards),
        mechanisms_checked=mechanisms_checked,
        duplicate_card_ids=duplicate_card_ids,
        duplicate_mechanism_ids=duplicate_mechanism_ids,
        missing_mechanism_files=missing_mechanism_files,
        missing_cards_for_files=missing_cards_for_files,
        element_balance_failures=tuple(element_balance_failures),
        initial_species_errors=tuple(initial_species_errors),
        target_species_errors=tuple(target_species_errors),
    )


def _float_mapping(payload: object, field_name: str) -> dict[str, float]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return {str(key): float(value) for key, value in payload.items()}


def _window_mapping(payload: object) -> dict[str, dict[str, float]]:
    if not isinstance(payload, Mapping):
        raise ValueError("operating_window must be a mapping")
    result: dict[str, dict[str, float]] = {}
    for key, bounds in payload.items():
        if not isinstance(bounds, Mapping):
            raise ValueError(f"operating_window[{key!r}] must contain min/max bounds")
        if "min" not in bounds or "max" not in bounds:
            raise ValueError(f"operating_window[{key!r}] must contain min and max")
        minimum = float(bounds["min"])
        maximum = float(bounds["max"])
        if minimum >= maximum:
            raise ValueError(f"operating_window[{key!r}] min must be below max")
        result[str(key)] = {"min": minimum, "max": maximum}
    return result


def _string_tuple(payload: object, field_name: str) -> tuple[str, ...]:
    if isinstance(payload, str) or not isinstance(payload, Sequence):
        raise ValueError(f"{field_name} must be a sequence of strings")
    values = tuple(str(value) for value in payload)
    optional_fields = {"impurity_species", "validation_notes"}
    if field_name not in optional_fields and not values:
        raise ValueError(f"{field_name} cannot be empty")
    return values


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(str(value))
        seen.add(str(value))
    return tuple(sorted(duplicates))


def _relative_to_repo(path: Path) -> str:
    try:
        return path.resolve().relative_to(repository_root()).as_posix()
    except ValueError:
        return str(path)


__all__ = [
    "MECHANISM_SCENARIO_SCHEMA_VERSION",
    "MechanismLibraryValidationReport",
    "MechanismScenarioCard",
    "configuration_root",
    "get_mechanism_card",
    "list_mechanism_cards",
    "list_mechanism_paths",
    "load_library_mechanism",
    "mechanism_library_root",
    "mechanism_scenario_library_path",
    "packaged_configuration_root",
    "repository_root",
    "validate_mechanism_library",
]
