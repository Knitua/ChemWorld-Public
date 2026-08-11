"""Chemical ontology registry for the shared ChemWorld law."""

from __future__ import annotations

from typing import Any

from chemworld.foundation import StateVariable, Substance


def chemworld_substances(compiled_mechanism: Any | None = None) -> dict[str, Substance]:
    """Return a mechanism-owned substance registry.

    ChemWorld's shared ontology defines the kinds of records that exist, while
    concrete species come from the compiled scenario mechanism. Keeping the
    default registry empty prevents the runtime from silently falling back to a
    fixed reaction fixture.
    """

    if compiled_mechanism is None:
        return {}
    substances: dict[str, Substance] = {}
    for species in compiled_mechanism.network.species:
        formula = dict(species.composition)
        role = "catalyst" if species.catalyst else "species"
        substances[species.species_id] = Substance(
            species.species_id,
            species.species_id,
            formula,
            phase=species.phase,
            role=role,
        )
    return substances


def chemworld_state_variables() -> tuple[StateVariable, ...]:
    """Return public and hidden state-variable contracts for ChemWorld."""

    return (
        StateVariable("species_amounts", "mol", hidden=True),
        StateVariable("volume_L", "L", hidden=True),
        StateVariable("temperature_K", "K", hidden=True),
        StateVariable("pressure_Pa", "Pa", hidden=True),
        StateVariable("ledger.cost", "currency", hidden=False),
        StateVariable("ledger.risk", "risk", hidden=False),
        StateVariable("ledger.time_s", "s", hidden=False),
        StateVariable("process.metrics.purity", "dimensionless", hidden=True),
        StateVariable("process.metrics.recovery", "dimensionless", hidden=True),
        StateVariable(
            "process.metrics.process_mass_balance_error",
            "dimensionless",
            hidden=True,
        ),
        StateVariable("process.metrics.crystal_yield", "dimensionless", hidden=True),
        StateVariable("process.metrics.crystal_csd_quality", "dimensionless", hidden=True),
        StateVariable("process.metrics.crystal_fines_fraction", "dimensionless", hidden=True),
        StateVariable("process.metrics.distillate_purity", "dimensionless", hidden=True),
        StateVariable("process.metrics.flow_conversion", "dimensionless", hidden=True),
        StateVariable(
            "process.metrics.electrochemical_selectivity",
            "dimensionless",
            hidden=True,
        ),
        StateVariable("process.metrics.energy_efficiency", "dimensionless", hidden=True),
        StateVariable("process.metrics.faradaic_efficiency", "dimensionless", hidden=True),
        StateVariable("process.metrics.transport_efficiency", "dimensionless", hidden=True),
        StateVariable("process.metrics.ohmic_efficiency", "dimensionless", hidden=True),
    )


__all__ = ["chemworld_state_variables", "chemworld_substances"]
