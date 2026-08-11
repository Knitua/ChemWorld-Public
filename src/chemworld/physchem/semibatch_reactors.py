"""Semi-batch reactor model with explicit feed ledgers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from chemworld.physchem.reaction_network import ReactionNetworkSpec
from chemworld.physchem.reactor_shared import (
    HeatTransferSpec,
    PressureBoundarySpec,
    ReactorResult,
    ReactorValidityDomain,
    SemiBatchFeedSpec,
    WithdrawalSpec,
)
from chemworld.physchem.reactor_solvers import (
    _amount_vector,
    _amounts_from_vector,
    _feed_heat_w,
    _integrate_result,
    _reaction_heat_w,
)


@dataclass(frozen=True)
class SemiBatchReactorModel:
    network: ReactionNetworkSpec
    feeds: tuple[SemiBatchFeedSpec, ...]
    withdrawals: tuple[WithdrawalSpec, ...] = ()
    reactor_id: str = "semi_batch"

    def simulate(
        self,
        initial_amounts_mol: Mapping[str, float],
        *,
        initial_volume_L: float,
        temperature_K: float,
        duration_s: float,
        heat_transfer: HeatTransferSpec | None = None,
        pressure_boundary: PressureBoundarySpec | None = None,
        validity_domain: ReactorValidityDomain | None = None,
        evaluation_times_s: Sequence[float] | None = None,
    ) -> ReactorResult:
        if duration_s < 0:
            raise ValueError("duration_s cannot be negative")
        if initial_volume_L <= 0:
            raise ValueError("initial_volume_L must be positive")
        if temperature_K <= 0:
            raise ValueError("temperature_K must be positive")
        expected_final_volume = initial_volume_L + sum(
            feed.stream.volumetric_flow_L_s
            * _active_duration(feed.start_s, feed.end_s, duration_s)
            for feed in self.feeds
        ) - sum(
            withdrawal.volumetric_flow_L_s
            * _active_duration(withdrawal.start_s, withdrawal.end_s, duration_s)
            for withdrawal in self.withdrawals
        )
        if expected_final_volume <= 0:
            raise ValueError("withdrawals would exhaust the reactor volume")
        thermal = HeatTransferSpec() if heat_transfer is None else heat_transfer
        n_species = len(self.network.species_ids)
        y0 = np.array(
            [
                *_amount_vector(self.network, initial_amounts_mol),
                initial_volume_L,
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
            volume = float(y[n_species])
            if volume <= 1.0e-9:
                raise RuntimeError("semi-batch reactor reached nonpositive volume")
            temperature = max(float(y[n_species + 1]), 1.0)
            reaction_derivatives = self.network.amount_derivatives(
                amounts,
                volume_L=volume,
                temperature_K=temperature,
            )
            feed = {
                species_id: sum(feed.species_flow(species_id, time_s) for feed in self.feeds)
                for species_id in self.network.species_ids
            }
            volume_flow = sum(feed.volumetric_flow(time_s) for feed in self.feeds)
            withdrawal_flow = sum(
                withdrawal.volumetric_flow(time_s) for withdrawal in self.withdrawals
            )
            outlet = {
                species_id: amounts[species_id] / volume * withdrawal_flow
                for species_id in self.network.species_ids
            }
            heat_reaction_W = _reaction_heat_w(
                self.network,
                amounts,
                volume_L=volume,
                temperature_K=temperature,
            )
            q_jacket_W = thermal.jacket_heat_w(temperature)
            q_loss_W = thermal.heat_loss_w(temperature)
            feed_heat_W = _feed_heat_w(self.feeds, time_s, temperature, thermal)
            heat_capacity = thermal.rho_cp_J_per_L_K * volume
            dtemperature = (
                q_jacket_W + feed_heat_W - q_loss_W - heat_reaction_W
            ) / heat_capacity
            return np.array(
                [
                    *(
                        reaction_derivatives[species_id] + feed[species_id] - outlet[species_id]
                        for species_id in self.network.species_ids
                    ),
                    volume_flow - withdrawal_flow,
                    dtemperature,
                    q_jacket_W,
                    heat_reaction_W,
                    q_loss_W,
                    *(feed[species_id] for species_id in self.network.species_ids),
                    *(outlet[species_id] for species_id in self.network.species_ids),
                ],
                dtype=float,
            )

        return _integrate_result(
            model_id="semi_batch",
            reactor_id=self.reactor_id,
            network=self.network,
            initial_amounts_mol=initial_amounts_mol,
            initial_volume_L=initial_volume_L,
            initial_temperature_K=temperature_K,
            y0=y0,
            duration_s=duration_s,
            rhs=rhs,
            volume_getter=lambda _time_s, y: max(float(y[n_species]), 1e-9),
            evaluation_times_s=evaluation_times_s,
            temperature_index=n_species + 1,
            energy_jacket_index=n_species + 2,
            heat_reaction_index=n_species + 3,
            heat_loss_index=n_species + 4,
            material_in_slice=slice(n_species + 5, n_species + 5 + n_species),
            material_out_slice=slice(
                n_species + 5 + n_species,
                n_species + 5 + 2 * n_species,
            ),
            pressure_boundary=pressure_boundary,
            validity_domain=validity_domain,
        )


def _active_duration(start_s: float, end_s: float, duration_s: float) -> float:
    return max(0.0, min(end_s, duration_s) - min(max(start_s, 0.0), duration_s))


__all__ = ["SemiBatchReactorModel"]
