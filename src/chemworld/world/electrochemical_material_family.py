"""Versioned electrochemical material families for static optimization."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

HISTORICAL_ELECTROCHEMICAL_MATERIAL_FAMILY = "legacy-electrochemical-materials-v0.1"
LEGACY_ELECTROCHEMICAL_MATERIAL_FAMILY = HISTORICAL_ELECTROCHEMICAL_MATERIAL_FAMILY
NOMINAL_PRIOR_MATERIAL_FAMILY = "nominal-prior-latent-v2"
DEFAULT_ELECTROCHEMICAL_MATERIAL_FAMILY = HISTORICAL_ELECTROCHEMICAL_MATERIAL_FAMILY


@dataclass(frozen=True)
class ElectrochemicalResidualGeneratorContract:
    """Complete, serializable contract for hidden material residual generation."""

    contract_version: str
    latent_factor_names: tuple[str, ...]
    property_names: tuple[str, ...]
    electrolyte_loadings: tuple[tuple[float, ...], ...]
    solvent_loadings: tuple[tuple[float, ...], ...]
    potential_loadings: tuple[float, ...]
    latent_sigma: tuple[float, ...]
    independent_property_sigma: float
    multiplier_bounds: tuple[float, float]
    potential_noise_sigma_V: float
    potential_bounds_V: tuple[float, float]
    seed_namespace: str
    exchange_current_reference_A_m2: float
    exchange_current_log_sigma: float
    exchange_current_bounds_A_m2: tuple[float, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "latent_factor_names": list(self.latent_factor_names),
            "property_names": list(self.property_names),
            "electrolyte_loadings": [list(row) for row in self.electrolyte_loadings],
            "solvent_loadings": [list(row) for row in self.solvent_loadings],
            "potential_loadings": list(self.potential_loadings),
            "latent_sigma": list(self.latent_sigma),
            "independent_property_sigma": self.independent_property_sigma,
            "multiplier_bounds": list(self.multiplier_bounds),
            "potential_noise_sigma_V": self.potential_noise_sigma_V,
            "potential_bounds_V": list(self.potential_bounds_V),
            "seed_namespace": self.seed_namespace,
            "exchange_current_reference_A_m2": self.exchange_current_reference_A_m2,
            "exchange_current_log_sigma": self.exchange_current_log_sigma,
            "exchange_current_bounds_A_m2": list(self.exchange_current_bounds_A_m2),
        }


@dataclass(frozen=True)
class ElectrochemicalCellGeometryBounds:
    electrode_gap_m: tuple[float, float]
    electrode_area_m2: tuple[float, float]
    base_contact_resistance_ohm: tuple[float, float]

    def __post_init__(self) -> None:
        for field_name in (
            "electrode_gap_m",
            "electrode_area_m2",
            "base_contact_resistance_ohm",
        ):
            low, high = getattr(self, field_name)
            if low <= 0.0 or high < low:
                raise ValueError(f"{field_name} bounds must be positive and ordered")

    def to_dict(self) -> dict[str, list[float]]:
        return {
            "electrode_gap_m": list(self.electrode_gap_m),
            "electrode_area_m2": list(self.electrode_area_m2),
            "base_contact_resistance_ohm": list(self.base_contact_resistance_ohm),
        }


@dataclass(frozen=True)
class ElectrochemicalMaterialFamily:
    family_id: str
    contract_version: str
    cell_geometry_policy: str
    world_fixed_cell_geometry_bounds: ElectrochemicalCellGeometryBounds | None
    residual_policy: str
    runtime_coupling_version: str
    electrolyte_profiles: tuple[Mapping[str, float], ...]
    solvent_profiles: tuple[Mapping[str, float], ...]
    residual_generator: ElectrochemicalResidualGeneratorContract | None = None

    def __post_init__(self) -> None:
        # Freeze nested profile rows as well as the outer dataclass. This prevents
        # a global family registry object from being mutated between campaigns.
        object.__setattr__(
            self,
            "electrolyte_profiles",
            tuple(MappingProxyType(dict(row)) for row in self.electrolyte_profiles),
        )
        object.__setattr__(
            self,
            "solvent_profiles",
            tuple(MappingProxyType(dict(row)) for row in self.solvent_profiles),
        )

    @property
    def family_sha256(self) -> str:
        payload = self.to_dict(include_hash=False)
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self, *, include_hash: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "family_id": self.family_id,
            "contract_version": self.contract_version,
            "cell_geometry_policy": self.cell_geometry_policy,
            "world_fixed_cell_geometry_bounds": (
                None
                if self.world_fixed_cell_geometry_bounds is None
                else self.world_fixed_cell_geometry_bounds.to_dict()
            ),
            "residual_policy": self.residual_policy,
            "runtime_coupling_version": self.runtime_coupling_version,
            "electrolyte_profiles": [dict(row) for row in self.electrolyte_profiles],
            "solvent_profiles": [dict(row) for row in self.solvent_profiles],
            "residual_generator": (
                None if self.residual_generator is None else self.residual_generator.to_dict()
            ),
        }
        if include_hash:
            payload["family_sha256"] = self.family_sha256
        return payload


_LEGACY_ELECTROLYTES = (
    {
        "electrolyte_conductivity_S_m": 0.8,
        "electrode_gap_m": 0.006,
        "electrode_area_m2": 0.004,
        "contact_resistance_ohm": 0.50,
        "diffusivity_m2_s": 3.0e-10,
        "diffusion_layer_thickness_m": 2.5e-3,
        "double_layer_capacitance_F_m2": 0.25,
        "acid_concentration_mol_L": 0.015,
        "supporting_electrolyte_concentration_mol_L": 0.003,
        "precipitating_salt_concentration_mol_L": 0.001,
        "electrolyte_acid_pka": 4.76,
        "electrolyte_ksp": 1.0e-7,
        "standard_potential_shift_V": -0.18,
        "faradaic_efficiency_multiplier": 0.72,
        "product_selectivity_multiplier": 0.68,
    },
    {
        "electrolyte_conductivity_S_m": 12.0,
        "electrode_gap_m": 0.003,
        "electrode_area_m2": 0.004,
        "contact_resistance_ohm": 0.12,
        "diffusivity_m2_s": 1.2e-9,
        "diffusion_layer_thickness_m": 8.0e-4,
        "double_layer_capacitance_F_m2": 0.20,
        "acid_concentration_mol_L": 0.010,
        "supporting_electrolyte_concentration_mol_L": 0.080,
        "precipitating_salt_concentration_mol_L": 0.001,
        "electrolyte_acid_pka": 4.76,
        "electrolyte_ksp": 1.0e-8,
        "standard_potential_shift_V": 0.00,
        "faradaic_efficiency_multiplier": 1.00,
        "product_selectivity_multiplier": 1.00,
    },
    {
        "electrolyte_conductivity_S_m": 6.0,
        "electrode_gap_m": 0.004,
        "electrode_area_m2": 0.004,
        "contact_resistance_ohm": 0.20,
        "diffusivity_m2_s": 8.0e-10,
        "diffusion_layer_thickness_m": 1.2e-3,
        "double_layer_capacitance_F_m2": 0.18,
        "acid_concentration_mol_L": 0.050,
        "supporting_electrolyte_concentration_mol_L": 0.040,
        "precipitating_salt_concentration_mol_L": 5.0e-4,
        "electrolyte_acid_pka": 3.20,
        "electrolyte_ksp": 1.0e-6,
        "standard_potential_shift_V": 0.20,
        "faradaic_efficiency_multiplier": 0.88,
        "product_selectivity_multiplier": 0.82,
    },
    {
        "electrolyte_conductivity_S_m": 2.0,
        "electrode_gap_m": 0.005,
        "electrode_area_m2": 0.004,
        "contact_resistance_ohm": 0.35,
        "diffusivity_m2_s": 2.0e-10,
        "diffusion_layer_thickness_m": 3.0e-3,
        "double_layer_capacitance_F_m2": 0.30,
        "acid_concentration_mol_L": 0.005,
        "supporting_electrolyte_concentration_mol_L": 0.015,
        "precipitating_salt_concentration_mol_L": 0.050,
        "electrolyte_acid_pka": 6.20,
        "electrolyte_ksp": 1.0e-12,
        "standard_potential_shift_V": -0.35,
        "faradaic_efficiency_multiplier": 0.58,
        "product_selectivity_multiplier": 0.50,
    },
)

_LEGACY_SOLVENTS = (
    {
        "conductivity_multiplier": 1.00,
        "diffusivity_multiplier": 1.00,
        "capacitance_multiplier": 1.00,
        "proton_activity_multiplier": 1.00,
        "ksp_multiplier": 1.00,
        "standard_potential_shift_V": 0.00,
        "faradaic_efficiency_multiplier": 1.00,
        "product_selectivity_multiplier": 1.00,
    },
    {
        "conductivity_multiplier": 0.45,
        "diffusivity_multiplier": 0.62,
        "capacitance_multiplier": 0.70,
        "proton_activity_multiplier": 0.55,
        "ksp_multiplier": 4.00,
        "standard_potential_shift_V": -0.16,
        "faradaic_efficiency_multiplier": 0.78,
        "product_selectivity_multiplier": 0.72,
    },
    {
        "conductivity_multiplier": 0.72,
        "diffusivity_multiplier": 0.82,
        "capacitance_multiplier": 0.48,
        "proton_activity_multiplier": 0.20,
        "ksp_multiplier": 12.0,
        "standard_potential_shift_V": 0.35,
        "faradaic_efficiency_multiplier": 0.55,
        "product_selectivity_multiplier": 0.58,
    },
    {
        "conductivity_multiplier": 0.035,
        "diffusivity_multiplier": 0.18,
        "capacitance_multiplier": 0.16,
        "proton_activity_multiplier": 0.025,
        "ksp_multiplier": 80.0,
        "standard_potential_shift_V": -0.42,
        "faradaic_efficiency_multiplier": 0.42,
        "product_selectivity_multiplier": 0.45,
    },
)

_NOMINAL_PRIOR_ELECTROLYTES = (
    {
        "electrolyte_conductivity_S_m": 10.5,
        "diffusivity_m2_s": 4.5e-10,
        "diffusion_layer_thickness_m": 1.65e-3,
        "double_layer_capacitance_F_m2": 0.24,
        "acid_concentration_mol_L": 0.014,
        "supporting_electrolyte_concentration_mol_L": 0.075,
        "precipitating_salt_concentration_mol_L": 0.012,
        "electrolyte_acid_pka": 4.70,
        "electrolyte_ksp": 3.0e-9,
        "standard_potential_shift_V": -0.12,
    },
    {
        "electrolyte_conductivity_S_m": 5.8,
        "diffusivity_m2_s": 1.25e-9,
        "diffusion_layer_thickness_m": 9.5e-4,
        "double_layer_capacitance_F_m2": 0.18,
        "acid_concentration_mol_L": 0.020,
        "supporting_electrolyte_concentration_mol_L": 0.042,
        "precipitating_salt_concentration_mol_L": 0.003,
        "electrolyte_acid_pka": 4.10,
        "electrolyte_ksp": 2.0e-7,
        "standard_potential_shift_V": 0.00,
    },
    {
        "electrolyte_conductivity_S_m": 3.8,
        "diffusivity_m2_s": 7.5e-10,
        "diffusion_layer_thickness_m": 4.8e-4,
        "double_layer_capacitance_F_m2": 0.22,
        "acid_concentration_mol_L": 0.048,
        "supporting_electrolyte_concentration_mol_L": 0.030,
        "precipitating_salt_concentration_mol_L": 0.001,
        "electrolyte_acid_pka": 3.05,
        "electrolyte_ksp": 2.0e-6,
        "standard_potential_shift_V": 0.18,
    },
    {
        "electrolyte_conductivity_S_m": 15.0,
        "diffusivity_m2_s": 6.5e-10,
        "diffusion_layer_thickness_m": 2.80e-3,
        "double_layer_capacitance_F_m2": 0.05,
        "acid_concentration_mol_L": 0.008,
        "supporting_electrolyte_concentration_mol_L": 0.060,
        "precipitating_salt_concentration_mol_L": 2.0e-4,
        "electrolyte_acid_pka": 5.70,
        "electrolyte_ksp": 2.0e-5,
        "standard_potential_shift_V": 0.28,
    },
)

_NOMINAL_PRIOR_SOLVENTS = (
    {
        "conductivity_multiplier": 1.20,
        "diffusivity_multiplier": 0.78,
        "capacitance_multiplier": 0.85,
        "proton_activity_multiplier": 1.00,
        "ksp_multiplier": 1.00,
        "standard_potential_shift_V": -0.08,
        "relative_cost_index": 0.03,
    },
    {
        "conductivity_multiplier": 0.70,
        "diffusivity_multiplier": 1.25,
        "capacitance_multiplier": 0.65,
        "proton_activity_multiplier": 0.72,
        "ksp_multiplier": 4.0,
        "standard_potential_shift_V": 0.02,
        "relative_cost_index": 0.08,
    },
    {
        "conductivity_multiplier": 0.50,
        "diffusivity_multiplier": 0.85,
        "capacitance_multiplier": 0.38,
        "proton_activity_multiplier": 0.28,
        "ksp_multiplier": 10.0,
        "standard_potential_shift_V": 0.20,
        "relative_cost_index": 0.16,
    },
    {
        "conductivity_multiplier": 0.92,
        "diffusivity_multiplier": 0.65,
        "capacitance_multiplier": 0.22,
        "proton_activity_multiplier": 0.45,
        "ksp_multiplier": 8.0,
        "standard_potential_shift_V": 0.10,
        "relative_cost_index": 0.11,
    },
)

_NOMINAL_PRIOR_RESIDUAL_GENERATOR = ElectrochemicalResidualGeneratorContract(
    contract_version="chemworld-electrochemical-residual-generator-2.0",
    latent_factor_names=("transport", "solvation", "interface_kinetics"),
    property_names=(
        "conductivity",
        "diffusivity",
        "capacitance",
        "proton_activity",
        "solubility_product",
        "faradaic_efficiency",
        "selectivity",
    ),
    electrolyte_loadings=(
        (0.85, 0.00, 0.15),
        (0.75, 0.10, 0.00),
        (-0.10, 0.00, 0.80),
        (0.00, 0.85, 0.00),
        (0.00, -0.70, 0.00),
        (0.20, 0.00, 0.70),
        (0.00, -0.10, 0.80),
    ),
    solvent_loadings=(
        (0.80, 0.00, 0.15),
        (0.70, 0.10, 0.00),
        (-0.10, 0.00, 0.75),
        (0.00, 0.80, 0.00),
        (0.00, -0.65, 0.00),
        (0.20, 0.00, 0.65),
        (0.00, -0.10, 0.75),
    ),
    potential_loadings=(0.00, 0.65, 0.35),
    latent_sigma=(0.16, 0.13, 0.12),
    independent_property_sigma=0.025,
    multiplier_bounds=(0.72, 1.40),
    potential_noise_sigma_V=0.008,
    potential_bounds_V=(-0.08, 0.08),
    seed_namespace="nominal-prior-latent-v2-residuals",
    exchange_current_reference_A_m2=28.0,
    exchange_current_log_sigma=0.12,
    exchange_current_bounds_A_m2=(20.0, 40.0),
)

_FAMILIES = {
    HISTORICAL_ELECTROCHEMICAL_MATERIAL_FAMILY: ElectrochemicalMaterialFamily(
        family_id=HISTORICAL_ELECTROCHEMICAL_MATERIAL_FAMILY,
        contract_version="chemworld-electrochemical-material-family-0.1",
        cell_geometry_policy="legacy_material_specific_geometry",
        world_fixed_cell_geometry_bounds=None,
        residual_policy="legacy_seeded_solvent_effects",
        runtime_coupling_version="chemworld-electrochemical-runtime-coupling-legacy-0.1",
        electrolyte_profiles=_LEGACY_ELECTROLYTES,
        solvent_profiles=_LEGACY_SOLVENTS,
    ),
    NOMINAL_PRIOR_MATERIAL_FAMILY: ElectrochemicalMaterialFamily(
        family_id=NOMINAL_PRIOR_MATERIAL_FAMILY,
        contract_version="chemworld-electrochemical-material-family-2.0",
        cell_geometry_policy="seeded_once_per_world_fixed_for_campaign_v2",
        world_fixed_cell_geometry_bounds=ElectrochemicalCellGeometryBounds(
            electrode_gap_m=(0.0034, 0.0046),
            electrode_area_m2=(0.0034, 0.0046),
            base_contact_resistance_ohm=(0.14, 0.26),
        ),
        residual_policy="world_fixed_latent_transport_solvation_interface_residuals_v2",
        runtime_coupling_version="chemworld-electrochemical-runtime-coupling-2.0",
        electrolyte_profiles=_NOMINAL_PRIOR_ELECTROLYTES,
        solvent_profiles=_NOMINAL_PRIOR_SOLVENTS,
        residual_generator=_NOMINAL_PRIOR_RESIDUAL_GENERATOR,
    ),
}


def normalize_electrochemical_material_family(value: object | None) -> str:
    family_id = DEFAULT_ELECTROCHEMICAL_MATERIAL_FAMILY if value is None else str(value)
    if family_id not in _FAMILIES:
        raise ValueError(f"electrochemical material family must be one of {sorted(_FAMILIES)}")
    return family_id


def electrochemical_material_family(value: object | None) -> ElectrochemicalMaterialFamily:
    return _FAMILIES[normalize_electrochemical_material_family(value)]


def apply_electrochemical_material_family(instance: Any, value: object | None) -> Any:
    """Bind one material family to a fixed electrochemical world instance."""

    family = electrochemical_material_family(value)
    if family.family_id == HISTORICAL_ELECTROCHEMICAL_MATERIAL_FAMILY:
        return instance
    if instance.spec.scenario_id != "electrochemical-conversion":
        raise ValueError(
            "non-legacy electrochemical material families require the "
            "electrochemical-conversion task"
        )
    material_instance_sha256 = electrochemical_material_instance_sha256(
        instance.parameters,
        family,
    )
    initial_state = instance.initial_state.replace(
        metadata={
            **instance.initial_state.metadata,
            "electrochemical_material_family_id": family.family_id,
            "electrochemical_material_family_sha256": family.family_sha256,
            "electrochemical_material_family_contract_version": (family.contract_version),
            "electrochemical_material_instance_sha256": material_instance_sha256,
        }
    )
    parameters = replace(
        instance.parameters,
        world_id=(
            f"{instance.parameters.world_id}:materials-{family.family_sha256[:12]}:"
            f"instance-{material_instance_sha256[:12]}"
        ),
        provider=f"{instance.parameters.provider}+electrochemical-material-family",
    )
    return replace(instance, parameters=parameters, initial_state=initial_state)


def electrochemical_material_instance_sha256(
    parameters: Any,
    family: ElectrochemicalMaterialFamily,
) -> str:
    """Fingerprint the actual hidden world instance, not only the family schema."""

    def _value(value: Any) -> Any:
        return value.tolist() if hasattr(value, "tolist") else value

    payload = {
        "family_sha256": family.family_sha256,
        "world_id": parameters.world_id,
        "geometry": {
            "electrode_gap_m": parameters.electrochemical_electrode_gap_m,
            "electrode_area_m2": parameters.electrochemical_electrode_area_m2,
            "base_contact_resistance_ohm": parameters.electrochemical_base_contact_resistance_ohm,
        },
        "electrolyte_effects": _value(parameters.electrochemical_electrolyte_effects),
        "solvent_effects": _value(parameters.electrochemical_solvent_effects),
        "electrolyte_potential_residual_V": _value(
            parameters.electrochemical_electrolyte_potential_residual_V
        ),
        "solvent_potential_residual_V": _value(
            parameters.electrochemical_solvent_potential_residual_V
        ),
        "exchange_current_density_A_m2": parameters.electrochemical_exchange_current_density_A_m2,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "DEFAULT_ELECTROCHEMICAL_MATERIAL_FAMILY",
    "HISTORICAL_ELECTROCHEMICAL_MATERIAL_FAMILY",
    "LEGACY_ELECTROCHEMICAL_MATERIAL_FAMILY",
    "NOMINAL_PRIOR_MATERIAL_FAMILY",
    "ElectrochemicalCellGeometryBounds",
    "ElectrochemicalMaterialFamily",
    "ElectrochemicalResidualGeneratorContract",
    "apply_electrochemical_material_family",
    "electrochemical_material_family",
    "electrochemical_material_instance_sha256",
    "normalize_electrochemical_material_family",
]
