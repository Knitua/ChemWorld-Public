"""Version identities shared by RL checkpoint writers and readers."""

from __future__ import annotations

RL_CHECKPOINT_MANIFEST_SCHEMA_VERSION = "chemworld-rl-checkpoint-0.3"
RL_CHECKPOINT_SIDECAR_SCHEMA_VERSION = "chemworld-rl-checkpoint-contract-sidecar-0.2"
RL_CHECKPOINT_RUNTIME_SCHEMA_VERSIONS = frozenset(
    {
        RL_CHECKPOINT_MANIFEST_SCHEMA_VERSION,
        RL_CHECKPOINT_SIDECAR_SCHEMA_VERSION,
    }
)

__all__ = [
    "RL_CHECKPOINT_MANIFEST_SCHEMA_VERSION",
    "RL_CHECKPOINT_RUNTIME_SCHEMA_VERSIONS",
    "RL_CHECKPOINT_SIDECAR_SCHEMA_VERSION",
]
