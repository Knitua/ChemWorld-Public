"""Continuous stirred-tank reactor models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import isclose, isfinite
from typing import Literal

import numpy as np

from chemworld.physchem.reaction_network import ReactionNetworkSpec
from chemworld.physchem.reactor_shared import (
    FeedStreamSpec,
    HeatTransferSpec,
    PressureBoundarySpec,
    ReactorResult,
    ReactorValidityDomain,
)
from chemworld.physchem.reactor_solvers import (
    _amount_vector,
    _amounts_from_vector,
    _integrate_result,
    _reaction_heat_w,
)

CSTRFlowInterpolationMode = Literal["step", "linear"]


@dataclass(frozen=True)
class CSTRFlowProgram:
    """Time-dependent common scale for a constant-volume CSTR inlet and outlet."""

    setpoints: tuple[tuple[float, float], ...]
    mode: CSTRFlowInterpolationMode = "step"

    def __post_init__(self) -> None:
        if not self.setpoints:
            raise ValueError("CSTR flow-program setpoints cannot be empty")
        previous_time = -1.0
        for time_s, flow_scale in self.setpoints:
            if time_s < 0.0 or not isfinite(time_s):
                raise ValueError("CSTR flow-program times must be finite and nonnegative")
            if time_s < previous_time:
                raise ValueError("CSTR flow-program setpoints must be sorted by time")
            if flow_scale < 0.0 or not isfinite(flow_scale):
                raise ValueError("CSTR flow scale must be finite and nonnegative")
            previous_time = time_s
        if self.mode not in {"step", "linear"}:
            raise ValueError("CSTR flow-program mode must be 'step' or 'linear'")

    def scale_at(self, time_s: float) -> float:
        if time_s <= self.setpoints[0][0]:
            return float(self.setpoints[0][1])
        for (left_time, left_scale), (right_time, right_scale) in zip(
            self.setpoints,
            self.setpoints[1:],
            strict=False,
        ):
            if left_time <= time_s <= right_time:
                if self.mode == "step" or right_time == left_time:
                    return float(left_scale)
                fraction = (time_s - left_time) / (right_time - left_time)
                return float(left_scale + fraction * (right_scale - left_scale))
        return float(self.setpoints[-1][1])

    @property
    def operation_mode(self) -> str:
        initial = self.setpoints[0][1]
        final = self.setpoints[-1][1]
        if initial == 0.0 and final > 0.0:
            return "startup"
        if initial > 0.0 and final == 0.0:
            return "shutdown"
        if any(scale != initial for _, scale in self.setpoints[1:]):
            return "variable_flow"
        return "steady_flow"

    def to_dict(self) -> dict[str, object]:
        return {
            "setpoints": [
                {"time_s": time_s, "flow_scale": flow_scale}
                for time_s, flow_scale in self.setpoints
            ],
            "mode": self.mode,
            "operation_mode": self.operation_mode,
        }


@dataclass(frozen=True)
class CSTRModel:
    network: ReactionNetworkSpec
    inlet: FeedStreamSpec
    volume_L: float
    outlet_volumetric_flow_L_s: float | None = None
    reactor_id: str = "cstr"

    def __post_init__(self) -> None:
        if self.volume_L <= 0:
            raise ValueError("volume_L must be positive")
        if self.outlet_volumetric_flow_L_s is not None and self.outlet_volumetric_flow_L_s < 0:
            raise ValueError("outlet_volumetric_flow_L_s cannot be negative")
        if self.outlet_volumetric_flow_L_s is not None and not isclose(
            self.outlet_volumetric_flow_L_s,
            self.inlet.volumetric_flow_L_s,
            rel_tol=1.0e-12,
            abs_tol=1.0e-12,
        ):
            raise ValueError(
                "constant-volume CSTR requires equal inlet and outlet volumetric flow"
            )

    @property
    def outlet_flow_l_s(self) -> float:
        if self.outlet_volumetric_flow_L_s is None:
            return self.inlet.volumetric_flow_L_s
        return self.outlet_volumetric_flow_L_s

    def simulate_dynamic(
        self,
        initial_amounts_mol: Mapping[str, float],
        *,
        temperature_K: float,
        duration_s: float,
        heat_transfer: HeatTransferSpec | None = None,
        flow_program: CSTRFlowProgram | None = None,
        pressure_boundary: PressureBoundarySpec | None = None,
        validity_domain: ReactorValidityDomain | None = None,
        evaluation_times_s: Sequence[float] | None = None,
    ) -> ReactorResult:
        if duration_s < 0:
            raise ValueError("duration_s cannot be negative")
        if temperature_K <= 0:
            raise ValueError("temperature_K must be positive")
        thermal = HeatTransferSpec() if heat_transfer is None else heat_transfer
        n_species = len(self.network.species_ids)
        y0 = np.array(
            [
                *_amount_vector(self.network, initial_amounts_mol),
                temperature_K,
                0.0,
                0.0,
                0.0,
                *(0.0 for _ in range(n_species)),
                *(0.0 for _ in range(n_species)),
            ],
            dtype=float,
        )

        def rhs(time_s: float, y: np.ndarray) -> np.ndarray:
            amounts = _amounts_from_vector(self.network, y[:n_species])
            temperature = max(float(y[n_species]), 1.0)
            flow_scale = 1.0 if flow_program is None else flow_program.scale_at(time_s)
            reaction_derivatives = self.network.amount_derivatives(
                amounts,
                volume_L=self.volume_L,
                temperature_K=temperature,
            )
            outlet = {
                species_id: max(amounts[species_id], 0.0)
                / self.volume_L
                * self.outlet_flow_l_s
                * flow_scale
                for species_id in self.network.species_ids
            }
            inlet = {
                species_id: self.inlet.flow_for(species_id) * flow_scale
                for species_id in self.network.species_ids
            }
            heat_reaction_W = _reaction_heat_w(
                self.network,
                amounts,
                volume_L=self.volume_L,
                temperature_K=temperature,
            )
            q_jacket_W = thermal.jacket_heat_w(temperature)
            q_loss_W = thermal.heat_loss_w(temperature)
            inlet_heat_W = (
                thermal.rho_cp_J_per_L_K
                * self.inlet.volumetric_flow_L_s
                * flow_scale
                * (self.inlet.temperature_K - temperature)
            )
            heat_capacity = thermal.rho_cp_J_per_L_K * self.volume_L
            dtemperature = (q_jacket_W + inlet_heat_W - q_loss_W - heat_reaction_W) / heat_capacity
            return np.array(
                [
                    *(
                        reaction_derivatives[species_id] + inlet[species_id] - outlet[species_id]
                        for species_id in self.network.species_ids
                    ),
                    dtemperature,
                    q_jacket_W,
                    heat_reaction_W,
                    q_loss_W,
                    *(inlet[species_id] for species_id in self.network.species_ids),
                    *(outlet[species_id] for species_id in self.network.species_ids),
                ],
                dtype=float,
            )

        result = _integrate_result(
            model_id="cstr_dynamic",
            reactor_id=self.reactor_id,
            network=self.network,
            initial_amounts_mol=initial_amounts_mol,
            initial_volume_L=self.volume_L,
            initial_temperature_K=temperature_K,
            y0=y0,
            duration_s=duration_s,
            rhs=rhs,
            volume_getter=lambda _time_s, _y: self.volume_L,
            evaluation_times_s=evaluation_times_s,
            temperature_index=n_species,
            energy_jacket_index=n_species + 1,
            heat_reaction_index=n_species + 2,
            heat_loss_index=n_species + 3,
            material_in_slice=slice(n_species + 4, n_species + 4 + n_species),
            material_out_slice=slice(n_species + 4 + n_species, n_species + 4 + 2 * n_species),
            pressure_boundary=pressure_boundary,
            validity_domain=validity_domain,
        )
        resolved_program = flow_program or CSTRFlowProgram(((0.0, 1.0),))
        return replace(
            result,
            metadata={
                **result.metadata,
                "residence_time_s": (
                    None
                    if self.inlet.volumetric_flow_L_s <= 0.0
                    else self.volume_L / self.inlet.volumetric_flow_L_s
                ),
                "flow_program": resolved_program.to_dict(),
                "flow_scale_timeseries": tuple(
                    resolved_program.scale_at(time_s) for time_s in result.times_s
                ),
            },
        )

    def simulate_to_steady_state(
        self,
        *,
        temperature_K: float,
        heat_transfer: HeatTransferSpec | None = None,
        residence_times: float = 12.0,
        convergence_tolerance_mol_s: float = 1.0e-8,
        pressure_boundary: PressureBoundarySpec | None = None,
        validity_domain: ReactorValidityDomain | None = None,
    ) -> ReactorResult:
        if self.inlet.volumetric_flow_L_s <= 0:
            raise ValueError("CSTR steady state requires positive inlet volumetric flow")
        if residence_times <= 0:
            raise ValueError("residence_times must be positive")
        if convergence_tolerance_mol_s <= 0:
            raise ValueError("convergence_tolerance_mol_s must be positive")
        duration_s = residence_times * self.volume_L / self.inlet.volumetric_flow_L_s
        initial = {
            species_id: self.inlet.flow_for(species_id)
            / self.inlet.volumetric_flow_L_s
            * self.volume_L
            for species_id in self.network.species_ids
        }
        result = self.simulate_dynamic(
            initial,
            temperature_K=temperature_K,
            duration_s=duration_s,
            heat_transfer=heat_transfer,
            pressure_boundary=pressure_boundary,
            validity_domain=validity_domain,
            evaluation_times_s=(0.0, duration_s / 2.0, duration_s),
        )
        final = result.final_state
        derivatives = self.network.amount_derivatives(
            final.amounts_mol,
            volume_L=self.volume_L,
            temperature_K=final.temperature_K,
        )
        residuals = {
            species_id: derivatives[species_id]
            + self.inlet.flow_for(species_id)
            - final.concentrations_mol_L[species_id] * self.outlet_flow_l_s
            for species_id in self.network.species_ids
        }
        maximum_residual = max((abs(value) for value in residuals.values()), default=0.0)
        converged = maximum_residual <= convergence_tolerance_mol_s
        resolved = replace(
            result,
            metadata={
                **result.metadata,
                "steady_state": {
                    "converged": converged,
                    "species_residuals_mol_s": residuals,
                    "maximum_species_residual_mol_s": maximum_residual,
                    "tolerance_mol_s": convergence_tolerance_mol_s,
                    "residence_times_integrated": residence_times,
                },
            },
        )
        if not converged:
            raise RuntimeError(
                "CSTR steady-state convergence failed: "
                f"residual={maximum_residual:.6g} mol/s, "
                f"tolerance={convergence_tolerance_mol_s:.6g} mol/s"
            )
        return resolved


__all__ = ["CSTRFlowInterpolationMode", "CSTRFlowProgram", "CSTRModel"]
