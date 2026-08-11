"""Bounded vessel-to-vessel transfer with heel, line hold-up, and flush slugs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from typing import Any

from chemworld.physchem.maturity import (
    MaturityLevel,
    ModelCard,
    ValidationEvidence,
)

TRANSFER_MODEL_ID = "chemworld_transfer_holdup_vnext"
IDAES_COMMIT = "4275c45bfa76cd5b05926beaa8eee58f7b0b05e8"


def _finite_nonnegative(value: float, label: str) -> float:
    resolved = float(value)
    if not isfinite(resolved) or resolved < 0.0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return resolved


def _amounts(
    values: Mapping[str, float],
    *,
    label: str,
    require_positive_total: bool,
) -> dict[str, float]:
    resolved: dict[str, float] = {}
    for component_id, raw_value in values.items():
        key = str(component_id).strip()
        if not key:
            raise ValueError(f"{label} component ids cannot be empty")
        resolved[key] = _finite_nonnegative(float(raw_value), f"{label}[{key!r}]")
    if require_positive_total and sum(resolved.values()) <= 0.0:
        raise ValueError(f"{label} must contain a positive component amount")
    return resolved


@dataclass(frozen=True)
class TransferEquipmentSpec:
    equipment_id: str = "bounded_batch_transfer_vnext"
    source_heel_L: float = 0.0
    line_holdup_L: float = 0.0
    max_transfer_volume_L: float | None = None
    max_flush_volume_L: float | None = None

    def __post_init__(self) -> None:
        if not self.equipment_id.strip():
            raise ValueError("equipment_id cannot be empty")
        object.__setattr__(
            self,
            "source_heel_L",
            _finite_nonnegative(self.source_heel_L, "source_heel_L"),
        )
        object.__setattr__(
            self,
            "line_holdup_L",
            _finite_nonnegative(self.line_holdup_L, "line_holdup_L"),
        )
        for field_name in ("max_transfer_volume_L", "max_flush_volume_L"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _finite_nonnegative(value, field_name),
                )


@dataclass(frozen=True)
class TransferRequest:
    source_amounts_mol: Mapping[str, float]
    source_volume_L: float
    transfer_fraction: float
    equipment: TransferEquipmentSpec = field(default_factory=TransferEquipmentSpec)
    initial_line_amounts_mol: Mapping[str, float] = field(default_factory=dict)
    initial_line_volume_L: float = 0.0
    flush_amounts_mol: Mapping[str, float] = field(default_factory=dict)
    flush_volume_L: float = 0.0
    balance_tolerance: float = 1.0e-10

    def __post_init__(self) -> None:
        source = _amounts(
            self.source_amounts_mol,
            label="source_amounts_mol",
            require_positive_total=True,
        )
        source_volume = float(self.source_volume_L)
        if not isfinite(source_volume) or source_volume <= 0.0:
            raise ValueError("source_volume_L must be finite and positive")
        fraction = float(self.transfer_fraction)
        if not isfinite(fraction) or not 0.0 <= fraction <= 1.0:
            raise ValueError("transfer_fraction must lie in [0, 1]")
        line_volume = _finite_nonnegative(
            self.initial_line_volume_L,
            "initial_line_volume_L",
        )
        flush_volume = _finite_nonnegative(self.flush_volume_L, "flush_volume_L")
        line = _amounts(
            self.initial_line_amounts_mol,
            label="initial_line_amounts_mol",
            require_positive_total=line_volume > 0.0,
        )
        flush = _amounts(
            self.flush_amounts_mol,
            label="flush_amounts_mol",
            require_positive_total=flush_volume > 0.0,
        )
        tolerance = float(self.balance_tolerance)
        if not isfinite(tolerance) or tolerance <= 0.0:
            raise ValueError("balance_tolerance must be finite and positive")
        if self.equipment.source_heel_L > source_volume + tolerance:
            raise ValueError("source_heel_L cannot exceed source_volume_L")
        if line_volume > self.equipment.line_holdup_L + tolerance:
            raise ValueError("initial line volume exceeds line_holdup_L")
        if line_volume <= tolerance and sum(line.values()) > tolerance:
            raise ValueError("initial line amounts require positive initial_line_volume_L")
        if flush_volume <= tolerance and sum(flush.values()) > tolerance:
            raise ValueError("flush amounts require positive flush_volume_L")
        if (
            self.equipment.max_flush_volume_L is not None
            and flush_volume > self.equipment.max_flush_volume_L + tolerance
        ):
            raise ValueError("flush_volume_L exceeds equipment maximum")
        object.__setattr__(self, "source_amounts_mol", source)
        object.__setattr__(self, "source_volume_L", source_volume)
        object.__setattr__(self, "transfer_fraction", fraction)
        object.__setattr__(self, "initial_line_amounts_mol", line)
        object.__setattr__(self, "initial_line_volume_L", line_volume)
        object.__setattr__(self, "flush_amounts_mol", flush)
        object.__setattr__(self, "flush_volume_L", flush_volume)
        object.__setattr__(self, "balance_tolerance", tolerance)


@dataclass
class _Slug:
    origin: str
    volume_L: float
    amounts_mol: dict[str, float]

    def remove_front(self, volume_L: float) -> _Slug:
        if volume_L <= 0.0 or volume_L > self.volume_L:
            raise ValueError("removed slug volume must lie in (0, slug volume]")
        fraction = volume_L / self.volume_L
        removed_amounts = {
            component_id: amount * fraction
            for component_id, amount in self.amounts_mol.items()
        }
        self.volume_L -= volume_L
        for component_id, amount in removed_amounts.items():
            self.amounts_mol[component_id] -= amount
        return _Slug(self.origin, volume_L, removed_amounts)


def _add_amounts(target: dict[str, float], source: Mapping[str, float]) -> None:
    for component_id, amount in source.items():
        target[component_id] = target.get(component_id, 0.0) + amount


def _scale_amounts(values: Mapping[str, float], fraction: float) -> dict[str, float]:
    return {component_id: amount * fraction for component_id, amount in values.items()}


def _push_slug(
    line: list[_Slug],
    incoming: _Slug,
    *,
    capacity_L: float,
    delivered_by_origin: dict[str, dict[str, Any]],
    tolerance: float,
) -> None:
    if incoming.volume_L <= tolerance:
        return
    line.append(incoming)
    overflow = max(0.0, sum(slug.volume_L for slug in line) - capacity_L)
    while overflow > tolerance:
        front = line[0]
        removed = front.remove_front(min(front.volume_L, overflow))
        record = delivered_by_origin.setdefault(
            removed.origin,
            {"volume_L": 0.0, "amounts_mol": {}},
        )
        record["volume_L"] += removed.volume_L
        _add_amounts(record["amounts_mol"], removed.amounts_mol)
        overflow -= removed.volume_L
        if front.volume_L <= tolerance:
            line.pop(0)


def _amounts_from_slugs(slugs: list[_Slug], *, origin: str | None = None) -> dict[str, float]:
    amounts: dict[str, float] = {}
    for slug in slugs:
        if origin is None or slug.origin == origin:
            _add_amounts(amounts, slug.amounts_mol)
    return amounts


def _volume_from_slugs(slugs: list[_Slug], *, origin: str | None = None) -> float:
    return sum(
        slug.volume_L
        for slug in slugs
        if origin is None or slug.origin == origin
    )


@dataclass(frozen=True)
class TransferUnitResult:
    model_id: str
    equipment_id: str
    source_initial_amounts_mol: dict[str, float]
    source_initial_volume_L: float
    requested_transfer_volume_L: float
    withdrawn_source_amounts_mol: dict[str, float]
    withdrawn_source_volume_L: float
    source_remaining_amounts_mol: dict[str, float]
    source_remaining_volume_L: float
    target_delivered_amounts_mol: dict[str, float]
    target_delivered_volume_L: float
    target_delivered_by_origin: dict[str, dict[str, Any]]
    final_line_amounts_mol: dict[str, float]
    final_line_volume_L: float
    final_line_volume_by_origin_L: dict[str, float]
    source_amounts_delivered_mol: dict[str, float]
    source_amounts_retained_in_line_mol: dict[str, float]
    source_delivery_fraction_of_withdrawn: float
    overall_source_delivery_fraction: float
    component_balance_error_mol: dict[str, float]
    material_balance_error_mol: float
    volume_balance_error_L: float
    warnings: tuple[str, ...]
    provenance: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "equipment_id": self.equipment_id,
            "source_initial_amounts_mol": dict(self.source_initial_amounts_mol),
            "source_initial_volume_L": self.source_initial_volume_L,
            "requested_transfer_volume_L": self.requested_transfer_volume_L,
            "withdrawn_source_amounts_mol": dict(self.withdrawn_source_amounts_mol),
            "withdrawn_source_volume_L": self.withdrawn_source_volume_L,
            "source_remaining_amounts_mol": dict(self.source_remaining_amounts_mol),
            "source_remaining_volume_L": self.source_remaining_volume_L,
            "target_delivered_amounts_mol": dict(self.target_delivered_amounts_mol),
            "target_delivered_volume_L": self.target_delivered_volume_L,
            "target_delivered_by_origin": {
                origin: {
                    "volume_L": float(record["volume_L"]),
                    "amounts_mol": dict(record["amounts_mol"]),
                }
                for origin, record in self.target_delivered_by_origin.items()
            },
            "final_line_amounts_mol": dict(self.final_line_amounts_mol),
            "final_line_volume_L": self.final_line_volume_L,
            "final_line_volume_by_origin_L": dict(self.final_line_volume_by_origin_L),
            "source_amounts_delivered_mol": dict(self.source_amounts_delivered_mol),
            "source_amounts_retained_in_line_mol": dict(
                self.source_amounts_retained_in_line_mol
            ),
            "source_delivery_fraction_of_withdrawn": (
                self.source_delivery_fraction_of_withdrawn
            ),
            "overall_source_delivery_fraction": self.overall_source_delivery_fraction,
            "component_balance_error_mol": dict(self.component_balance_error_mol),
            "material_balance_error_mol": self.material_balance_error_mol,
            "volume_balance_error_L": self.volume_balance_error_L,
            "warnings": list(self.warnings),
            "provenance": list(self.provenance),
        }


def simulate_transfer(request: TransferRequest) -> TransferUnitResult:
    """Transfer a homogeneous source slug through a finite FIFO line inventory."""

    tolerance = request.balance_tolerance
    equipment = request.equipment
    requested_volume = request.source_volume_L * request.transfer_fraction
    available_volume = max(0.0, request.source_volume_L - equipment.source_heel_L)
    withdrawn_volume = min(requested_volume, available_volume)
    if equipment.max_transfer_volume_L is not None:
        withdrawn_volume = min(withdrawn_volume, equipment.max_transfer_volume_L)
    withdrawal_fraction = withdrawn_volume / request.source_volume_L
    withdrawn_amounts = _scale_amounts(request.source_amounts_mol, withdrawal_fraction)
    remaining_amounts = {
        component_id: request.source_amounts_mol[component_id]
        - withdrawn_amounts[component_id]
        for component_id in request.source_amounts_mol
    }
    remaining_volume = request.source_volume_L - withdrawn_volume

    line: list[_Slug] = []
    if request.initial_line_volume_L > tolerance:
        line.append(
            _Slug(
                "initial_line",
                request.initial_line_volume_L,
                dict(request.initial_line_amounts_mol),
            )
        )
    delivered_by_origin: dict[str, dict[str, Any]] = {}
    _push_slug(
        line,
        _Slug("source", withdrawn_volume, dict(withdrawn_amounts)),
        capacity_L=equipment.line_holdup_L,
        delivered_by_origin=delivered_by_origin,
        tolerance=tolerance,
    )
    _push_slug(
        line,
        _Slug("flush", request.flush_volume_L, dict(request.flush_amounts_mol)),
        capacity_L=equipment.line_holdup_L,
        delivered_by_origin=delivered_by_origin,
        tolerance=tolerance,
    )

    target_amounts: dict[str, float] = {}
    for record in delivered_by_origin.values():
        _add_amounts(target_amounts, record["amounts_mol"])
    target_volume = sum(float(record["volume_L"]) for record in delivered_by_origin.values())
    final_line_amounts = _amounts_from_slugs(line)
    final_line_volume = _volume_from_slugs(line)
    source_delivered = dict(
        delivered_by_origin.get("source", {}).get("amounts_mol", {})
    )
    source_retained = _amounts_from_slugs(line, origin="source")

    component_ids = sorted(
        set(request.source_amounts_mol)
        | set(request.initial_line_amounts_mol)
        | set(request.flush_amounts_mol)
        | set(target_amounts)
        | set(final_line_amounts)
    )
    component_errors: dict[str, float] = {}
    for component_id in component_ids:
        incoming = (
            request.source_amounts_mol.get(component_id, 0.0)
            + request.initial_line_amounts_mol.get(component_id, 0.0)
            + request.flush_amounts_mol.get(component_id, 0.0)
        )
        outgoing = (
            remaining_amounts.get(component_id, 0.0)
            + target_amounts.get(component_id, 0.0)
            + final_line_amounts.get(component_id, 0.0)
        )
        component_errors[component_id] = abs(incoming - outgoing)
    material_error = sum(component_errors.values())
    initial_volume = (
        request.source_volume_L
        + request.initial_line_volume_L
        + request.flush_volume_L
    )
    final_volume = remaining_volume + target_volume + final_line_volume
    volume_error = abs(initial_volume - final_volume)
    if material_error > tolerance or volume_error > tolerance:
        raise RuntimeError(
            "transfer control volume failed closure: "
            f"material={material_error}, volume={volume_error}"
        )

    withdrawn_moles = sum(withdrawn_amounts.values())
    delivered_source_moles = sum(source_delivered.values())
    initial_source_moles = sum(request.source_amounts_mol.values())
    warnings: list[str] = []
    if withdrawn_volume + tolerance < requested_volume:
        warnings.append("requested transfer clipped by source heel or equipment capacity")
    if withdrawn_volume > tolerance and delivered_source_moles <= tolerance:
        warnings.append("source slug remains entirely in line hold-up")
    if final_line_volume > tolerance:
        warnings.append("line retains material inventory that must persist between transfers")
    return TransferUnitResult(
        model_id=TRANSFER_MODEL_ID,
        equipment_id=equipment.equipment_id,
        source_initial_amounts_mol=dict(request.source_amounts_mol),
        source_initial_volume_L=request.source_volume_L,
        requested_transfer_volume_L=requested_volume,
        withdrawn_source_amounts_mol=withdrawn_amounts,
        withdrawn_source_volume_L=withdrawn_volume,
        source_remaining_amounts_mol=remaining_amounts,
        source_remaining_volume_L=remaining_volume,
        target_delivered_amounts_mol=target_amounts,
        target_delivered_volume_L=target_volume,
        target_delivered_by_origin=delivered_by_origin,
        final_line_amounts_mol=final_line_amounts,
        final_line_volume_L=final_line_volume,
        final_line_volume_by_origin_L={
            origin: _volume_from_slugs(line, origin=origin)
            for origin in ("initial_line", "source", "flush")
        },
        source_amounts_delivered_mol=source_delivered,
        source_amounts_retained_in_line_mol=source_retained,
        source_delivery_fraction_of_withdrawn=(
            delivered_source_moles / withdrawn_moles if withdrawn_moles > tolerance else 0.0
        ),
        overall_source_delivery_fraction=(
            delivered_source_moles / initial_source_moles
        ),
        component_balance_error_mol=component_errors,
        material_balance_error_mol=material_error,
        volume_balance_error_L=volume_error,
        warnings=tuple(warnings),
        provenance=(
            "finite-volume FIFO slug displacement with explicit line inventory",
            (
                f"IDAES {IDAES_COMMIT}: component material-balance and "
                "control-volume holdup conventions"
            ),
        ),
    )


def transfer_unit_model_card() -> ModelCard:
    return ModelCard(
        model_id=TRANSFER_MODEL_ID,
        module_id="separations",
        title="Bounded Vessel Transfer With Line Hold-up",
        maturity=MaturityLevel.REFERENCE_VALIDATED,
        summary=(
            "A finite-volume FIFO transfer ledger with explicit source heel, line "
            "inventory, equipment capacity, and optional flush displacement."
        ),
        equations=(
            "V_withdrawn = min(f V_source, V_source - V_heel, V_equipment_max)",
            "n_in = n_source_initial + n_line_initial + n_flush",
            "n_out = n_source_remaining + n_target + n_line_final",
            "FIFO segments displaced beyond line hold-up are delivered to the target",
        ),
        assumptions=(
            "source vessel is homogeneous before withdrawal",
            "line behaves as a one-dimensional FIFO dead volume without dispersion",
            "each source or flush slug has uniform composition",
            "isothermal incompressible volume additivity within the declared slice",
        ),
        validity_limits=(
            "single liquid phase with no reaction, evaporation, precipitation, or adsorption",
            "line hold-up is fixed and all component amounts are tracked explicitly",
            "no pump curve, pressure drop, leakage, or flexible-hose deformation model",
            "runtime must persist returned line inventory between sequential transfers",
        ),
        failure_modes=(
            "negative or nonfinite volumes and amounts are rejected",
            "line inventory above equipment hold-up is rejected",
            "flush or transfer above declared equipment capacity is rejected or clipped",
            "material or volume closure outside tolerance raises a hard failure",
        ),
        units={
            "component amount": "mol",
            "source, line, flush, and target volume": "L",
            "transfer fraction": "1",
            "material balance error": "mol",
        },
        reference_reading=(
            (
                f"IDAES {IDAES_COMMIT}: idaes/core/base/unit_model.py component "
                "material-balance conventions"
            ),
            "finite-volume plug displacement and control-volume inventory identities",
        ),
        validation_evidence=(
            ValidationEvidence(
                evidence_id="transfer-fifo-analytic-limits",
                evidence_type="analytic_test",
                description=(
                    "Zero hold-up, full retention, heel clipping, initial-line "
                    "displacement, and complete flush limits are checked exactly."
                ),
                status="implemented",
                reference_backend="analytic finite-volume control balance",
                command_or_path="tests/test_transfer_units.py",
                tolerance="1e-10 mol and L",
            ),
            ValidationEvidence(
                evidence_id="transfer-component-closure",
                evidence_type="invariant_test",
                description="Every component and total liquid volume close across all inventories.",
                status="implemented",
                reference_backend="IDAES control-volume balance convention",
                command_or_path="tests/test_transfer_units.py",
                tolerance="1e-10 mol and L",
            ),
        ),
        model_limit_notes=(
            "Reference validation applies to the bounded transfer ledger, not plant piping design.",
            "This proposal does not replace dry or concentrate and does not alter v0.3.",
        ),
        intended_use=(
            "World Law vNext transfer operation candidate",
            "agent training environments with explicit recoverable line inventory",
            "material-balance and flush-strategy evaluation",
        ),
    )


__all__ = [
    "IDAES_COMMIT",
    "TRANSFER_MODEL_ID",
    "TransferEquipmentSpec",
    "TransferRequest",
    "TransferUnitResult",
    "simulate_transfer",
    "transfer_unit_model_card",
]
