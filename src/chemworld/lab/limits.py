"""Shared capacity errors for the public Lab service boundary."""

from __future__ import annotations


class LabCapacityError(RuntimeError):
    """Raised when a bounded public Lab resource pool is full."""


__all__ = ["LabCapacityError"]
