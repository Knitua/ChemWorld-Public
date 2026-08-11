"""Plug-flow reactor model."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import pi

import numpy as np

from chemworld.physchem.maturity import MaturityLevel, ModelCard, ValidationEvidence
from chemworld.physchem.reaction_network import ReactionNetworkSpec
from chemworld.physchem.reactor_shared import HeatTransferSpec, ReactorResult, ReactorState
from chemworld.physchem.reactor_solvers import _material_balance_error, _solve
from chemworld.physchem.transport import (
    FlowResult,
    darcy_friction_factor,
    single_phase_tube_hydraulic_ledger,
)


@dataclass(frozen=True)
class PFRGeometrySpec:
    """Incompressible tube geometry, hydraulics, and thermal boundary for a PFR."""

    length_m: float
    inner_diameter_m: float
    roughness_m: float = 1.0e-6
    fluid_density_kg_m3: float = 1000.0
    fluid_viscosity_Pa_s: float = 1.0e-3
    boundary_ua_W_per_m_K: float = 0.0
    boundary_temperature_K: float | None = None
    hydraulic_provenance_id: str = "darcy_weisbach_straight_tube_v1"
    thermal_boundary_provenance_id: str = "unspecified"

    def __post_init__(self) -> None:
        _positive_finite(self.length_m, "PFR length_m")
        _positive_finite(self.inner_diameter_m, "PFR inner_diameter_m")
        _nonnegative_finite(self.roughness_m, "PFR roughness_m")
        _positive_finite(self.fluid_density_kg_m3, "PFR fluid_density_kg_m3")
        _positive_finite(self.fluid_viscosity_Pa_s, "PFR fluid_viscosity_Pa_s")
        _nonnegative_finite(self.boundary_ua_W_per_m_K, "PFR boundary_ua_W_per_m_K")
        if self.boundary_temperature_K is not None:
            _positive_finite(
                self.boundary_temperature_K,
                "PFR boundary_temperature_K",
            )
        if not self.hydraulic_provenance_id.strip():
            raise ValueError("PFR hydraulic_provenance_id cannot be empty")
        if not self.thermal_boundary_provenance_id.strip():
            raise ValueError("PFR thermal_boundary_provenance_id cannot be empty")

    @property
    def cross_section_area_m2(self) -> float:
        return pi * self.inner_diameter_m**2 / 4.0

    @property
    def volume_l(self) -> float:
        return self.cross_section_area_m2 * self.length_m * 1000.0

    def axial_velocity_m_s(self, volumetric_flow_L_s: float) -> float:
        return volumetric_flow_L_s / 1000.0 / self.cross_section_area_m2

    def reynolds_number(self, volumetric_flow_L_s: float) -> float:
        velocity = self.axial_velocity_m_s(volumetric_flow_L_s)
        return (
            self.fluid_density_kg_m3 * velocity * self.inner_diameter_m / self.fluid_viscosity_Pa_s
        )

    def pressure_gradient_pa_m(self, volumetric_flow_L_s: float) -> float:
        velocity = self.axial_velocity_m_s(volumetric_flow_L_s)
        reynolds = self.reynolds_number(volumetric_flow_L_s)
        friction = darcy_friction_factor(
            reynolds=reynolds,
            relative_roughness=self.roughness_m / self.inner_diameter_m,
        )
        return friction * self.fluid_density_kg_m3 * velocity**2 / (2.0 * self.inner_diameter_m)

    def hydraulic_ledger(self, volumetric_flow_L_s: float) -> FlowResult:
        return single_phase_tube_hydraulic_ledger(
            length_m=self.length_m,
            inner_diameter_m=self.inner_diameter_m,
            roughness_m=self.roughness_m,
            fluid_density_kg_m3=self.fluid_density_kg_m3,
            fluid_viscosity_Pa_s=self.fluid_viscosity_Pa_s,
            volumetric_flow_L_s=volumetric_flow_L_s,
            provenance_id=self.hydraulic_provenance_id,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "length_m": self.length_m,
            "inner_diameter_m": self.inner_diameter_m,
            "roughness_m": self.roughness_m,
            "fluid_density_kg_m3": self.fluid_density_kg_m3,
            "fluid_viscosity_Pa_s": self.fluid_viscosity_Pa_s,
            "boundary_ua_W_per_m_K": self.boundary_ua_W_per_m_K,
            "boundary_temperature_K": self.boundary_temperature_K,
            "hydraulic_provenance_id": self.hydraulic_provenance_id,
            "thermal_boundary_provenance_id": self.thermal_boundary_provenance_id,
            "cross_section_area_m2": self.cross_section_area_m2,
            "volume_L": self.volume_l,
        }


@dataclass(frozen=True)
class PFRModel:
    network: ReactionNetworkSpec
    reactor_volume_L: float
    volumetric_flow_L_s: float
    geometry: PFRGeometrySpec | None = None
    inlet_pressure_Pa: float = 101_325.0
    reactor_id: str = "pfr"
    rate_multiplier: float = 1.0

    def __post_init__(self) -> None:
        _positive_finite(self.reactor_volume_L, "reactor_volume_L")
        if self.volumetric_flow_L_s <= 0 or not np.isfinite(
            self.volumetric_flow_L_s
        ):
            raise ValueError("volumetric_flow_L_s must be positive and finite")
        _positive_finite(self.inlet_pressure_Pa, "inlet_pressure_Pa")
        if self.rate_multiplier <= 0.0 or not np.isfinite(self.rate_multiplier):
            raise ValueError("rate_multiplier must be positive and finite")
        if self.geometry is not None and not np.isclose(
            self.geometry.volume_l,
            self.reactor_volume_L,
            rtol=1.0e-6,
            atol=1.0e-12,
        ):
            raise ValueError("PFR geometry volume must match reactor_volume_L")

    @property
    def residence_time_s(self) -> float:
        return self.reactor_volume_L / self.volumetric_flow_L_s

    def simulate(
        self,
        inlet_concentrations_mol_L: Mapping[str, float],
        *,
        temperature_K: float,
        heat_transfer: HeatTransferSpec | None = None,
        evaluation_times_s: Sequence[float] | None = None,
        axial_positions_m: Sequence[float] | None = None,
    ) -> ReactorResult:
        if temperature_K <= 0.0 or not np.isfinite(temperature_K):
            raise ValueError("temperature_K must be finite and positive")
        if evaluation_times_s is not None and axial_positions_m is not None:
            raise ValueError("Specify evaluation_times_s or axial_positions_m, not both")
        if axial_positions_m is not None:
            if self.geometry is None:
                raise ValueError("axial_positions_m requires a PFR geometry")
            positions = tuple(float(value) for value in axial_positions_m)
            if any(
                not np.isfinite(value)
                or value < 0.0
                or value > self.geometry.length_m
                for value in positions
            ):
                raise ValueError("axial_positions_m must lie inside the PFR length")
            evaluation_times_s = tuple(
                float(
                    np.clip(
                        self.residence_time_s * value / self.geometry.length_m,
                        0.0,
                        self.residence_time_s,
                    )
                )
                for value in positions
            )
        unknown_species = sorted(
            set(inlet_concentrations_mol_L) - set(self.network.species_ids)
        )
        if unknown_species:
            raise ValueError(f"unknown inlet species: {unknown_species}")
        for species_id, concentration in inlet_concentrations_mol_L.items():
            value = float(concentration)
            if value < 0.0 or not np.isfinite(value):
                raise ValueError(
                    f"inlet concentration for {species_id} must be finite and nonnegative"
                )
        thermal = HeatTransferSpec() if heat_transfer is None else heat_transfer
        hydraulic = (
            None
            if self.geometry is None
            else self.geometry.hydraulic_ledger(self.volumetric_flow_L_s)
        )
        if hydraulic is not None and hydraulic.pressure_drop_total_Pa >= self.inlet_pressure_Pa:
            raise RuntimeError(
                "PFR hydraulic boundary predicts nonpositive outlet absolute pressure"
            )
        initial_amounts = {
            species_id: float(inlet_concentrations_mol_L.get(species_id, 0.0))
            * self.reactor_volume_L
            for species_id in self.network.species_ids
        }
        y0 = np.array(
            [
                *(
                    float(inlet_concentrations_mol_L.get(species_id, 0.0))
                    for species_id in self.network.species_ids
                ),
                temperature_K,
                self.inlet_pressure_Pa,
                0.0,
                0.0,
                0.0,
            ],
            dtype=float,
        )

        def rhs(_tau_s: float, y: np.ndarray) -> np.ndarray:
            concentrations = {
                species_id: _validated_concentration(float(value), species_id)
                for species_id, value in zip(self.network.species_ids, y, strict=False)
            }
            temperature = float(y[len(self.network.species_ids)])
            if temperature <= 0.0 or not np.isfinite(temperature):
                raise RuntimeError("PFR integration reached a nonphysical temperature")
            rates = self.network.reaction_rates(
                concentrations,
                volume_L=1.0,
                temperature_K=temperature,
            )
            dconcentrations = dict.fromkeys(self.network.species_ids, 0.0)
            for reaction in self.network.reactions:
                rate = rates[reaction.reaction_id] * self.rate_multiplier
                for species_id, coefficient in reaction.stoichiometry.items():
                    dconcentrations[species_id] += coefficient * rate
            heat_reaction_per_L_W = sum(
                reaction.delta_h_J_per_mol * rates[reaction.reaction_id] * self.rate_multiplier
                for reaction in self.network.reactions
            )
            boundary_heat_W = 0.0
            if self.geometry is not None and self.geometry.boundary_temperature_K is not None:
                boundary_heat_W = (
                    self.geometry.boundary_ua_W_per_m_K
                    * self.geometry.length_m
                    * (self.geometry.boundary_temperature_K - temperature)
                )
            q_jacket_W = thermal.jacket_heat_w(temperature) + boundary_heat_W
            q_jacket_per_L_W = q_jacket_W / self.reactor_volume_L
            q_loss_per_L_W = thermal.heat_loss_w(temperature) / self.reactor_volume_L
            dtemperature = (
                q_jacket_per_L_W - q_loss_per_L_W - heat_reaction_per_L_W
            ) / thermal.rho_cp_J_per_L_K
            pressure_gradient = (
                0.0
                if hydraulic is None or self.geometry is None
                else hydraulic.pressure_drop_total_Pa / self.geometry.length_m
            )
            axial_speed = (
                0.0 if self.geometry is None else self.geometry.length_m / self.residence_time_s
            )
            dpressure = -pressure_gradient * axial_speed
            return np.array(
                [
                    *(dconcentrations[species_id] for species_id in self.network.species_ids),
                    dtemperature,
                    dpressure,
                    q_jacket_W,
                    heat_reaction_per_L_W * self.reactor_volume_L,
                    thermal.heat_loss_w(temperature),
                ],
                dtype=float,
            )

        result = _solve(
            rhs,
            y0,
            duration_s=self.residence_time_s,
            evaluation_times_s=evaluation_times_s,
        )
        n_species = len(self.network.species_ids)
        pressure_index = n_species + 1
        amounts = {
            species_id: tuple(
                _validated_concentration(float(value), species_id) * self.reactor_volume_L
                for value in result.y[idx]
            )
            for idx, species_id in enumerate(self.network.species_ids)
        }
        final_amounts = {species_id: values[-1] for species_id, values in amounts.items()}
        final_state = ReactorState(
            amounts_mol=final_amounts,
            volume_L=self.reactor_volume_L,
            temperature_K=float(result.y[n_species, -1]),
            time_s=self.residence_time_s,
            pressure_Pa=float(result.y[pressure_index, -1]),
            energy_jacket_J=float(result.y[n_species + 2, -1]),
            heat_reaction_J=float(result.y[n_species + 3, -1]),
            heat_loss_J=float(result.y[n_species + 4, -1]),
        )
        initial_state = ReactorState(
            amounts_mol=initial_amounts,
            volume_L=self.reactor_volume_L,
            temperature_K=temperature_K,
            time_s=0.0,
            pressure_Pa=self.inlet_pressure_Pa,
        )
        pressures = tuple(float(value) for value in result.y[pressure_index])
        if min(pressures) <= 0.0:
            raise RuntimeError("PFR pressure-drop model reached nonpositive absolute pressure")
        axial_positions: tuple[float, ...]
        geometry_payload: dict[str, object] | None
        if self.geometry is None:
            axial_positions = ()
            pressure_drop = 0.0
            geometry_payload = None
        else:
            axial_positions = tuple(
                self.geometry.length_m * float(value) / self.residence_time_s for value in result.t
            )
            pressure_drop = pressures[0] - pressures[-1]
            geometry_payload = dict[str, object](self.geometry.to_dict())
        material_balance_error = _material_balance_error(
            self.network,
            initial_state,
            final_state,
        )
        if material_balance_error > 1.0e-8:
            raise RuntimeError(
                "PFR material balance failed: "
                f"residual={material_balance_error:.6g} mol"
            )
        times = tuple(float(value) for value in result.t)
        temperatures = tuple(float(value) for value in result.y[n_species])
        sensible_energy_J = (
            thermal.rho_cp_J_per_L_K
            * self.reactor_volume_L
            * (final_state.temperature_K - initial_state.temperature_K)
        )
        expected_sensible_energy_J = (
            final_state.energy_jacket_J
            - final_state.heat_reaction_J
            - final_state.heat_loss_J
        )
        energy_balance_residual_J = sensible_energy_J - expected_sensible_energy_J
        axial_profile = tuple(
            {
                "residence_time_s": times[index],
                "axial_position_m": (
                    None if not axial_positions else axial_positions[index]
                ),
                "temperature_K": temperatures[index],
                "pressure_Pa": pressures[index],
                "concentrations_mol_L": {
                    species_id: amounts[species_id][index] / self.reactor_volume_L
                    for species_id in self.network.species_ids
                },
            }
            for index in range(len(times))
        )
        hydraulic_payload = None if hydraulic is None else hydraulic.to_dict()
        if hydraulic_payload is not None:
            hydraulic_payload["inlet_pressure_Pa"] = self.inlet_pressure_Pa
            hydraulic_payload["outlet_pressure_Pa"] = pressures[-1]
            hydraulic_payload["hydraulic_energy_per_reactor_volume_J"] = (
                pressure_drop * self.reactor_volume_L / 1000.0
            )
        hydraulic_metadata = (
            hydraulic_payload.get("metadata")
            if isinstance(hydraulic_payload, dict)
            else None
        )
        hydraulic_model_id = (
            hydraulic_metadata.get("model_id")
            if isinstance(hydraulic_metadata, dict)
            else None
        )
        return ReactorResult(
            reactor_id=self.reactor_id,
            model_id="pfr",
            network_id=self.network.network_id,
            initial_state=initial_state,
            final_state=final_state,
            times_s=times,
            amounts_mol=amounts,
            temperatures_K=temperatures,
            material_balance_error_mol=material_balance_error,
            volumes_L=tuple(self.reactor_volume_L for _ in times),
            pressures_Pa=pressures,
            metadata={
                "residence_time_s": self.residence_time_s,
                "volumetric_flow_L_s": self.volumetric_flow_L_s,
                "rate_multiplier": self.rate_multiplier,
                "geometry": geometry_payload,
                "axial_positions_m": axial_positions,
                "pressures_Pa": pressures,
                "pressure_drop_Pa": pressure_drop,
                "reynolds_number": (
                    None
                    if self.geometry is None
                    else self.geometry.reynolds_number(self.volumetric_flow_L_s)
                ),
                "solver_diagnostic": result.diagnostic.to_dict(),
                "axial_profile": axial_profile,
                "hydraulic_ledger": hydraulic_payload,
                "thermal_ledger": {
                    "energy_jacket_J": final_state.energy_jacket_J,
                    "heat_reaction_J": final_state.heat_reaction_J,
                    "heat_loss_J": final_state.heat_loss_J,
                    "sensible_energy_J": sensible_energy_J,
                    "energy_balance_residual_J": energy_balance_residual_J,
                    "rho_cp_J_per_L_K": thermal.rho_cp_J_per_L_K,
                },
                "provenance": {
                    "model_id": "geometry_resolved_pfr_v2",
                    "reaction_network_id": self.network.network_id,
                    "hydraulic_model_id": (
                        hydraulic_model_id
                    ),
                    "hydraulic_provenance_id": (
                        None
                        if self.geometry is None
                        else self.geometry.hydraulic_provenance_id
                    ),
                    "thermal_boundary_provenance_id": (
                        None
                        if self.geometry is None
                        else self.geometry.thermal_boundary_provenance_id
                    ),
                },
            },
        )


def _validated_concentration(value: float, species_id: str) -> float:
    if not np.isfinite(value):
        raise RuntimeError(f"PFR concentration became nonfinite for {species_id}")
    if value < -1.0e-8:
        raise RuntimeError(f"PFR concentration became negative for {species_id}: {value}")
    return max(value, 0.0)


def _positive_finite(value: float, name: str) -> None:
    if value <= 0.0 or not np.isfinite(value):
        raise ValueError(f"{name} must be finite and positive")


def _nonnegative_finite(value: float, name: str) -> None:
    if value < 0.0 or not np.isfinite(value):
        raise ValueError(f"{name} must be finite and nonnegative")


def geometry_resolved_pfr_model_card() -> ModelCard:
    """Return the bounded reference card used by the formal flow runtime."""

    return ModelCard(
        model_id="chemworld_geometry_resolved_pfr_v2",
        module_id="continuous_flow",
        title="Geometry-Resolved Single-Phase Tubular PFR Runtime",
        maturity=MaturityLevel.REFERENCE_VALIDATED,
        summary=(
            "A single-phase incompressible tubular plug-flow slice coupling the shared "
            "reaction network to residence time, distributed wall heat transfer, "
            "Darcy-Weisbach pressure loss, and axial diagnostics."
        ),
        equations=(
            "V = Q tau; A_c = pi D^2/4; L = V/A_c",
            "dF_i/dV = r_i; rho Cp Q dT/dV = q_reaction + U P_w (T_wall-T)",
            "Delta P = f (L/D) rho u^2/2",
            "material, thermal, and hydraulic ledgers close on one configured run",
        ),
        assumptions=(
            "The flowing phase is single, incompressible, and radially well mixed.",
            "Axial dispersion, multiphase slip, compressibility, and catalyst aging are absent.",
            "Fluid properties, tube geometry, wall boundary, and feed remain fixed per run.",
        ),
        validity_limits=(
            "Positive bounded flow, residence time, geometry, density, and viscosity are required.",
            "The run duration must span at least one configured residence time.",
            "The configured feed signature must match the feed at execution.",
        ),
        failure_modes=(
            "Stale configuration, invalid pressure, nonfinite or negative species, solver "
            "failure, and material or energy non-closure fail closed with transaction rollback.",
            "Pressure-drop or thermal-boundary values outside the equipment domain are rejected.",
        ),
        units={
            "flow rate": "mL/min",
            "residence time": "s",
            "geometry": "m",
            "temperature": "K",
            "pressure/pressure drop": "Pa",
            "energy": "J",
        },
        reference_reading=(
            "Ideal plug-flow material and energy balances for tubular reactors.",
            "Darcy-Weisbach straight-tube pressure loss with laminar/turbulent friction factors.",
            "Distributed U-times-wetted-perimeter wall heat-transfer boundary.",
        ),
        validation_evidence=(
            ValidationEvidence(
                evidence_id="pfr-analytical-geometry-hydraulic-identities",
                evidence_type="analytical_test",
                description=(
                    "Checks analytical V=Q tau geometry, plug-flow residence response, "
                    "Darcy-Weisbach pressure ordering, and material/energy closure."
                ),
                status="implemented",
                command_or_path="tests/test_flow_coupling.py",
                tolerance="material < 1e-8 mol; relative energy residual < 1e-5",
            ),
            ValidationEvidence(
                evidence_id="pfr-runtime-domain-and-rollback",
                evidence_type="failure_domain_test",
                description=(
                    "Checks invalid and stale configuration, insufficient duration, pressure "
                    "and solver failure domains, fresh-run semantics, provenance, "
                    "and atomic rollback."
                ),
                status="implemented",
                command_or_path="tests/test_flow_coupling.py",
                tolerance="exact transaction rollback and unchanged physical state",
            ),
        ),
        model_limit_notes=(
            "Reference validation is limited to a compact single-phase tubular benchmark slice.",
            "It is not a general continuous-flow platform or an industrial reactor design model.",
        ),
        intended_use=(
            "Agent exploration of residence-time, wall-temperature, flow, and "
            "pressure-drop tradeoffs.",
            "Replayable continuous-flow benchmark trajectories with explicit "
            "ledgers and provenance.",
        ),
    )


__all__ = ["PFRGeometrySpec", "PFRModel", "geometry_resolved_pfr_model_card"]
