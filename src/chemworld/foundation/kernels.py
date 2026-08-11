"""Transition and observation kernel protocols."""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from chemworld.foundation.state import Observation, OperationRecord, WorldState


class TransitionKernel(Protocol):
    def transition(
        self,
        state: WorldState,
        action: dict[str, Any],
        rng: np.random.Generator,
    ) -> tuple[WorldState, OperationRecord]:
        """Apply one operation and return the next hidden state plus ledger record."""


class ObservationKernel(Protocol):
    def observe(
        self,
        state: WorldState,
        action: dict[str, Any],
        rng: np.random.Generator,
    ) -> Observation:
        """Generate a noisy, costly public observation from hidden state."""

