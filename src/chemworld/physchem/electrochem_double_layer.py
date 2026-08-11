"""Randles-style double-layer RC transients and current traces."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, exp, isfinite
from typing import Literal

DoubleLayerControlMode = Literal["potential_step", "current_step"]


@dataclass(frozen=True)
class DoubleLayerRCSpec:
    model_id: str
    double_layer_capacitance_F_m2: float
    electrode_area_m2: float
    series_resistance_ohm: float
    charge_transfer_resistance_ohm: float
    provenance_id: str

    def __post_init__(self) -> None:
        for name, value in (
            ("double_layer_capacitance_F_m2", self.double_layer_capacitance_F_m2),
            ("electrode_area_m2", self.electrode_area_m2),
            ("series_resistance_ohm", self.series_resistance_ohm),
            ("charge_transfer_resistance_ohm", self.charge_transfer_resistance_ohm),
        ):
            _positive(value, name)
        if not self.model_id or not self.provenance_id:
            raise ValueError("model_id and provenance_id cannot be empty")

    @property
    def total_capacitance_f(self) -> float:
        return self.double_layer_capacitance_F_m2 * self.electrode_area_m2

    @property
    def potential_step_time_constant_s(self) -> float:
        parallel_resistance = (
            self.series_resistance_ohm
            * self.charge_transfer_resistance_ohm
            / (self.series_resistance_ohm + self.charge_transfer_resistance_ohm)
        )
        return parallel_resistance * self.total_capacitance_f

    @property
    def current_step_time_constant_s(self) -> float:
        return self.charge_transfer_resistance_ohm * self.total_capacitance_f

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "double_layer_capacitance_F_m2": self.double_layer_capacitance_F_m2,
            "electrode_area_m2": self.electrode_area_m2,
            "total_capacitance_F": self.total_capacitance_f,
            "series_resistance_ohm": self.series_resistance_ohm,
            "charge_transfer_resistance_ohm": self.charge_transfer_resistance_ohm,
            "potential_step_time_constant_s": self.potential_step_time_constant_s,
            "current_step_time_constant_s": self.current_step_time_constant_s,
            "provenance_id": self.provenance_id,
        }


@dataclass(frozen=True)
class DoubleLayerTracePoint:
    time_s: float
    terminal_potential_V: float
    interfacial_overpotential_V: float
    total_current_A: float
    faradaic_current_A: float
    capacitive_current_A: float

    def to_dict(self) -> dict[str, float]:
        return {
            "time_s": self.time_s,
            "terminal_potential_V": self.terminal_potential_V,
            "interfacial_overpotential_V": self.interfacial_overpotential_V,
            "total_current_A": self.total_current_A,
            "faradaic_current_A": self.faradaic_current_A,
            "capacitive_current_A": self.capacitive_current_A,
        }


@dataclass(frozen=True)
class DoubleLayerTransientResult:
    model_id: str
    control_mode: DoubleLayerControlMode
    command_value: float
    duration_s: float
    time_constant_s: float
    total_charge_C: float
    faradaic_charge_C: float
    capacitive_charge_C: float
    charge_balance_residual_C: float
    startup_capacitive_fraction: float
    final_capacitive_fraction: float
    trace: tuple[DoubleLayerTracePoint, ...]
    warnings: tuple[str, ...]
    provenance_id: str

    def observation(self) -> dict[str, object]:
        return {
            "time_s": [point.time_s for point in self.trace],
            "terminal_potential_V": [point.terminal_potential_V for point in self.trace],
            "interfacial_overpotential_V": [
                point.interfacial_overpotential_V for point in self.trace
            ],
            "total_current_A": [point.total_current_A for point in self.trace],
            "faradaic_current_A": [point.faradaic_current_A for point in self.trace],
            "capacitive_current_A": [point.capacitive_current_A for point in self.trace],
            "startup_capacitive_fraction": self.startup_capacitive_fraction,
            "final_capacitive_fraction": self.final_capacitive_fraction,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "model_id": self.model_id,
            "control_mode": self.control_mode,
            "command_value": self.command_value,
            "duration_s": self.duration_s,
            "time_constant_s": self.time_constant_s,
            "total_charge_C": self.total_charge_C,
            "faradaic_charge_C": self.faradaic_charge_C,
            "capacitive_charge_C": self.capacitive_charge_C,
            "charge_balance_residual_C": self.charge_balance_residual_C,
            "startup_capacitive_fraction": self.startup_capacitive_fraction,
            "final_capacitive_fraction": self.final_capacitive_fraction,
            "trace": [point.to_dict() for point in self.trace],
            "observation": self.observation(),
            "warnings": list(self.warnings),
            "provenance_id": self.provenance_id,
        }


def simulate_double_layer_potential_step(
    spec: DoubleLayerRCSpec,
    *,
    potential_step_V: float,
    duration_s: float,
    sample_interval_s: float,
) -> DoubleLayerTransientResult:
    _finite(potential_step_V, "potential_step_V")
    _positive(duration_s, "duration_s")
    _positive(sample_interval_s, "sample_interval_s")
    tau = spec.potential_step_time_constant_s
    steady_current = potential_step_V / (
        spec.series_resistance_ohm + spec.charge_transfer_resistance_ohm
    )
    point_count = max(1, ceil(duration_s / sample_interval_s))
    trace: list[DoubleLayerTracePoint] = []
    for index in range(point_count + 1):
        time_s = duration_s * index / point_count
        decay = exp(-time_s / tau)
        interfacial = (
            potential_step_V
            * spec.charge_transfer_resistance_ohm
            / (spec.series_resistance_ohm + spec.charge_transfer_resistance_ohm)
            * (1.0 - decay)
        )
        faradaic = interfacial / spec.charge_transfer_resistance_ohm
        capacitive = potential_step_V / spec.series_resistance_ohm * decay
        trace.append(
            DoubleLayerTracePoint(
                time_s=time_s,
                terminal_potential_V=potential_step_V,
                interfacial_overpotential_V=interfacial,
                total_current_A=faradaic + capacitive,
                faradaic_current_A=faradaic,
                capacitive_current_A=capacitive,
            )
        )
    decay_final = exp(-duration_s / tau)
    faradaic_charge = steady_current * (duration_s - tau * (1.0 - decay_final))
    capacitive_charge = potential_step_V / spec.series_resistance_ohm * tau * (1.0 - decay_final)
    return _result(
        spec,
        control_mode="potential_step",
        command_value=potential_step_V,
        duration_s=duration_s,
        time_constant_s=tau,
        faradaic_charge_C=faradaic_charge,
        capacitive_charge_C=capacitive_charge,
        trace=trace,
    )


def simulate_double_layer_current_step(
    spec: DoubleLayerRCSpec,
    *,
    current_step_A: float,
    duration_s: float,
    sample_interval_s: float,
) -> DoubleLayerTransientResult:
    _finite(current_step_A, "current_step_A")
    _positive(duration_s, "duration_s")
    _positive(sample_interval_s, "sample_interval_s")
    tau = spec.current_step_time_constant_s
    point_count = max(1, ceil(duration_s / sample_interval_s))
    trace: list[DoubleLayerTracePoint] = []
    for index in range(point_count + 1):
        time_s = duration_s * index / point_count
        decay = exp(-time_s / tau)
        interfacial = current_step_A * spec.charge_transfer_resistance_ohm * (1.0 - decay)
        faradaic = current_step_A * (1.0 - decay)
        capacitive = current_step_A * decay
        terminal = interfacial + current_step_A * spec.series_resistance_ohm
        trace.append(
            DoubleLayerTracePoint(
                time_s=time_s,
                terminal_potential_V=terminal,
                interfacial_overpotential_V=interfacial,
                total_current_A=current_step_A,
                faradaic_current_A=faradaic,
                capacitive_current_A=capacitive,
            )
        )
    decay_final = exp(-duration_s / tau)
    capacitive_charge = current_step_A * tau * (1.0 - decay_final)
    total_charge = current_step_A * duration_s
    faradaic_charge = total_charge - capacitive_charge
    return _result(
        spec,
        control_mode="current_step",
        command_value=current_step_A,
        duration_s=duration_s,
        time_constant_s=tau,
        faradaic_charge_C=faradaic_charge,
        capacitive_charge_C=capacitive_charge,
        trace=trace,
    )


def _result(
    spec: DoubleLayerRCSpec,
    *,
    control_mode: DoubleLayerControlMode,
    command_value: float,
    duration_s: float,
    time_constant_s: float,
    faradaic_charge_C: float,
    capacitive_charge_C: float,
    trace: list[DoubleLayerTracePoint],
) -> DoubleLayerTransientResult:
    total_charge = faradaic_charge_C + capacitive_charge_C
    initial_total = abs(trace[0].total_current_A)
    final_total = abs(trace[-1].total_current_A)
    startup_fraction = (
        0.0 if initial_total <= 0.0 else abs(trace[0].capacitive_current_A) / initial_total
    )
    final_fraction = (
        0.0 if final_total <= 0.0 else abs(trace[-1].capacitive_current_A) / final_total
    )
    warnings: list[str] = []
    if duration_s < 5.0 * time_constant_s:
        warnings.append("trace_ends_before_five_time_constants")
    if startup_fraction > 0.5:
        warnings.append("startup_current_dominated_by_non_faradaic_charging")
    return DoubleLayerTransientResult(
        model_id="randles_double_layer_transient_v1",
        control_mode=control_mode,
        command_value=command_value,
        duration_s=duration_s,
        time_constant_s=time_constant_s,
        total_charge_C=total_charge,
        faradaic_charge_C=faradaic_charge_C,
        capacitive_charge_C=capacitive_charge_C,
        charge_balance_residual_C=(total_charge - faradaic_charge_C - capacitive_charge_C),
        startup_capacitive_fraction=startup_fraction,
        final_capacitive_fraction=final_fraction,
        trace=tuple(trace),
        warnings=tuple(warnings),
        provenance_id=spec.provenance_id,
    )


def _positive(value: float, field_name: str) -> None:
    if value <= 0.0 or not isfinite(value):
        raise ValueError(f"{field_name} must be positive and finite")


def _finite(value: float, field_name: str) -> None:
    if not isfinite(value):
        raise ValueError(f"{field_name} must be finite")


__all__ = [
    "DoubleLayerRCSpec",
    "DoubleLayerTracePoint",
    "DoubleLayerTransientResult",
    "simulate_double_layer_current_step",
    "simulate_double_layer_potential_step",
]
