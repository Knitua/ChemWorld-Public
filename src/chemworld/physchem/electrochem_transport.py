"""Diffusion-layer limiting current and finite-reservoir depletion."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, isfinite

from chemworld.physchem.electrochemistry import FARADAY_C_PER_MOL


@dataclass(frozen=True)
class DiffusionLayerSpec:
    model_id: str
    electrons_transferred: float
    electrode_area_m2: float
    diffusivity_m2_s: float
    diffusion_layer_thickness_m: float
    electrolyte_volume_m3: float
    provenance_id: str

    def __post_init__(self) -> None:
        for name, value in (
            ("electrons_transferred", self.electrons_transferred),
            ("electrode_area_m2", self.electrode_area_m2),
            ("diffusivity_m2_s", self.diffusivity_m2_s),
            ("diffusion_layer_thickness_m", self.diffusion_layer_thickness_m),
            ("electrolyte_volume_m3", self.electrolyte_volume_m3),
        ):
            _positive(value, name)
        if not self.model_id or not self.provenance_id:
            raise ValueError("model_id and provenance_id cannot be empty")

    @property
    def mass_transfer_rate_m3_s(self) -> float:
        return self.electrode_area_m2 * self.diffusivity_m2_s / self.diffusion_layer_thickness_m

    def limiting_current_a(self, bulk_concentration_mol_m3: float) -> float:
        _nonnegative(bulk_concentration_mol_m3, "bulk_concentration_mol_m3")
        return (
            self.electrons_transferred
            * FARADAY_C_PER_MOL
            * self.mass_transfer_rate_m3_s
            * bulk_concentration_mol_m3
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "electrons_transferred": self.electrons_transferred,
            "electrode_area_m2": self.electrode_area_m2,
            "diffusivity_m2_s": self.diffusivity_m2_s,
            "diffusion_layer_thickness_m": self.diffusion_layer_thickness_m,
            "electrolyte_volume_m3": self.electrolyte_volume_m3,
            "mass_transfer_rate_m3_s": self.mass_transfer_rate_m3_s,
            "provenance_id": self.provenance_id,
        }


@dataclass(frozen=True)
class MassTransferLimitedCurrentResult:
    model_id: str
    initial_bulk_concentration_mol_m3: float
    final_bulk_concentration_mol_m3: float
    final_surface_concentration_mol_m3: float
    initial_limiting_current_A: float
    final_limiting_current_A: float
    applied_current_A: float
    kinetic_current_A: float | None
    initial_useful_current_A: float
    average_useful_current_A: float
    applied_charge_C: float
    useful_charge_C: float
    side_reaction_charge_C: float
    charge_balance_residual_C: float
    material_balance_residual_mol: float
    current_efficiency: float
    depletion_fraction: float
    transition_to_limiting_time_s: float | None
    mass_transfer_limited_initially: bool
    duration_s: float
    warnings: tuple[str, ...]
    provenance_id: str

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "initial_bulk_concentration_mol_m3": (self.initial_bulk_concentration_mol_m3),
            "final_bulk_concentration_mol_m3": (self.final_bulk_concentration_mol_m3),
            "final_surface_concentration_mol_m3": (self.final_surface_concentration_mol_m3),
            "initial_limiting_current_A": self.initial_limiting_current_A,
            "final_limiting_current_A": self.final_limiting_current_A,
            "applied_current_A": self.applied_current_A,
            "kinetic_current_A": self.kinetic_current_A,
            "initial_useful_current_A": self.initial_useful_current_A,
            "average_useful_current_A": self.average_useful_current_A,
            "applied_charge_C": self.applied_charge_C,
            "useful_charge_C": self.useful_charge_C,
            "side_reaction_charge_C": self.side_reaction_charge_C,
            "charge_balance_residual_C": self.charge_balance_residual_C,
            "material_balance_residual_mol": self.material_balance_residual_mol,
            "current_efficiency": self.current_efficiency,
            "depletion_fraction": self.depletion_fraction,
            "transition_to_limiting_time_s": self.transition_to_limiting_time_s,
            "mass_transfer_limited_initially": self.mass_transfer_limited_initially,
            "duration_s": self.duration_s,
            "warnings": list(self.warnings),
            "provenance_id": self.provenance_id,
        }


def diffusion_layer_current_response(
    spec: DiffusionLayerSpec,
    *,
    bulk_concentration_mol_m3: float,
    applied_current_A: float,
    duration_s: float,
    kinetic_current_A: float | None = None,
) -> MassTransferLimitedCurrentResult:
    """Apply kinetic/diffusion current caps and integrate bulk depletion analytically."""

    _nonnegative(bulk_concentration_mol_m3, "bulk_concentration_mol_m3")
    _finite(applied_current_A, "applied_current_A")
    _nonnegative(duration_s, "duration_s")
    if kinetic_current_A is not None:
        _finite(kinetic_current_A, "kinetic_current_A")
    sign = -1.0 if applied_current_A < 0.0 else 1.0
    applied_magnitude = abs(applied_current_A)
    target_magnitude = applied_magnitude
    if kinetic_current_A is not None:
        target_magnitude = min(target_magnitude, abs(kinetic_current_A))
    initial_limiting = spec.limiting_current_a(bulk_concentration_mol_m3)
    initial_useful_magnitude = min(target_magnitude, initial_limiting)
    mass_transfer_limited_initially = target_magnitude > initial_limiting
    transition_time: float | None = None
    final_concentration = bulk_concentration_mol_m3
    if duration_s > 0.0 and target_magnitude > 0.0 and bulk_concentration_mol_m3 > 0.0:
        threshold_concentration = target_magnitude / (
            spec.electrons_transferred * FARADAY_C_PER_MOL * spec.mass_transfer_rate_m3_s
        )
        if threshold_concentration >= bulk_concentration_mol_m3:
            final_concentration = bulk_concentration_mol_m3 * exp(
                -spec.mass_transfer_rate_m3_s * duration_s / spec.electrolyte_volume_m3
            )
            transition_time = 0.0
        else:
            concentration_rate = target_magnitude / (
                spec.electrons_transferred * FARADAY_C_PER_MOL * spec.electrolyte_volume_m3
            )
            time_to_threshold = (
                bulk_concentration_mol_m3 - threshold_concentration
            ) / concentration_rate
            if duration_s <= time_to_threshold:
                final_concentration = max(
                    bulk_concentration_mol_m3 - concentration_rate * duration_s,
                    0.0,
                )
            else:
                final_concentration = threshold_concentration * exp(
                    -spec.mass_transfer_rate_m3_s
                    * (duration_s - time_to_threshold)
                    / spec.electrolyte_volume_m3
                )
                transition_time = time_to_threshold
    final_limiting = spec.limiting_current_a(final_concentration)
    useful_charge = (
        spec.electrons_transferred
        * FARADAY_C_PER_MOL
        * spec.electrolyte_volume_m3
        * (bulk_concentration_mol_m3 - final_concentration)
    )
    applied_charge = applied_magnitude * duration_s
    useful_charge = min(useful_charge, applied_charge)
    average_useful_magnitude = 0.0 if duration_s <= 0.0 else useful_charge / duration_s
    current_efficiency = 1.0 if applied_charge <= 0.0 else useful_charge / applied_charge
    side_reaction_charge = max(applied_charge - useful_charge, 0.0)
    charge_balance_residual = applied_charge - useful_charge - side_reaction_charge
    depleted_mol = spec.electrolyte_volume_m3 * (bulk_concentration_mol_m3 - final_concentration)
    charge_implied_mol = useful_charge / (spec.electrons_transferred * FARADAY_C_PER_MOL)
    material_balance_residual = depleted_mol - charge_implied_mol
    final_surface = final_concentration
    if final_limiting > 0.0:
        final_surface *= max(1.0 - target_magnitude / final_limiting, 0.0)
    depletion_fraction = (
        0.0
        if bulk_concentration_mol_m3 <= 0.0
        else 1.0 - final_concentration / bulk_concentration_mol_m3
    )
    warnings: list[str] = []
    if mass_transfer_limited_initially:
        warnings.append("mass_transfer_limited_initially")
    elif transition_time is not None:
        warnings.append("transitioned_to_mass_transfer_limit")
    if current_efficiency < 0.95:
        warnings.append("current_efficiency_loss_from_transport_or_kinetic_limit")
    if depletion_fraction > 0.90:
        warnings.append("bulk_reactant_depletion_above_ninety_percent")
    return MassTransferLimitedCurrentResult(
        model_id="diffusion_layer_limiting_current_v1",
        initial_bulk_concentration_mol_m3=bulk_concentration_mol_m3,
        final_bulk_concentration_mol_m3=final_concentration,
        final_surface_concentration_mol_m3=final_surface,
        initial_limiting_current_A=initial_limiting,
        final_limiting_current_A=final_limiting,
        applied_current_A=applied_current_A,
        kinetic_current_A=kinetic_current_A,
        initial_useful_current_A=sign * initial_useful_magnitude,
        average_useful_current_A=sign * average_useful_magnitude,
        applied_charge_C=applied_charge,
        useful_charge_C=useful_charge,
        side_reaction_charge_C=side_reaction_charge,
        charge_balance_residual_C=charge_balance_residual,
        material_balance_residual_mol=material_balance_residual,
        current_efficiency=current_efficiency,
        depletion_fraction=depletion_fraction,
        transition_to_limiting_time_s=transition_time,
        mass_transfer_limited_initially=mass_transfer_limited_initially,
        duration_s=duration_s,
        warnings=tuple(warnings),
        provenance_id=spec.provenance_id,
    )


def _positive(value: float, field_name: str) -> None:
    if value <= 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be positive and finite")


def _nonnegative(value: float, field_name: str) -> None:
    if value < 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be nonnegative and finite")


def _finite(value: float, field_name: str) -> None:
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite")


__all__ = [
    "DiffusionLayerSpec",
    "MassTransferLimitedCurrentResult",
    "diffusion_layer_current_response",
]
