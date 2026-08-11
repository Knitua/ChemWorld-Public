"""Native masked-operation, conditional-parameter PPO distribution.

The environment retains a fixed Box carrier for Stable-Baselines3 rollout
storage, but the policy probability law is not diagonal Gaussian: operation
selection is categorical under the public affordance mask and parameter log
probabilities are included only when required by the selected operation.
"""

from __future__ import annotations

from functools import partial
from typing import Any, Self

import numpy as np
import torch as th
from stable_baselines3.common.distributions import Distribution
from stable_baselines3.common.policies import ActorCriticPolicy
from stable_baselines3.common.type_aliases import PyTorchObs, Schedule
from torch import nn
from torch.distributions import Categorical, Normal

from chemworld.rl.hybrid_actions import (
    POLICY_DISTRIBUTION_SCHEMA_VERSION,
    policy_distribution_contract,
)
from chemworld.world.operations import OPERATION_TYPES, operation_contracts


class ConditionalHybridDistribution(Distribution):
    """Categorical operation plus selected-operation Gaussian parameters."""

    def __init__(self, parameter_keys: tuple[str, ...]) -> None:
        super().__init__()
        self.parameter_keys = parameter_keys
        contracts = operation_contracts()
        self._active = th.tensor(
            [
                [field in contracts[operation].required_fields for field in parameter_keys]
                for operation in OPERATION_TYPES
            ],
            dtype=th.float32,
        )
        self.operation_distribution: Categorical
        self.parameter_distribution: Normal

    def proba_distribution_net(self, *args: Any, **kwargs: Any) -> nn.Module:
        raise NotImplementedError("the hybrid policy builds its joint output head directly")

    def proba_distribution(
        self,
        operation_logits: th.Tensor,
        parameter_means: th.Tensor,
        parameter_log_std: th.Tensor,
        operation_mask: th.Tensor,
    ) -> Self:
        mask = operation_mask.to(dtype=th.bool)
        any_valid = mask.any(dim=1, keepdim=True)
        effective_mask = th.where(any_valid, mask, th.ones_like(mask))
        masked_logits = operation_logits.masked_fill(~effective_mask, -1.0e9)
        self.operation_distribution = Categorical(logits=masked_logits)
        std = parameter_log_std.exp().expand_as(parameter_means)
        self.parameter_distribution = Normal(parameter_means, std)
        self.distribution = [self.operation_distribution, self.parameter_distribution]
        return self

    def _operation_indices(self, actions: th.Tensor) -> th.Tensor:
        return actions[:, : len(OPERATION_TYPES)].argmax(dim=1)

    def _pack(self, operation: th.Tensor, parameters: th.Tensor) -> th.Tensor:
        logits_carrier = th.full(
            (operation.shape[0], len(OPERATION_TYPES)),
            -1.0,
            dtype=parameters.dtype,
            device=parameters.device,
        )
        logits_carrier.scatter_(1, operation.unsqueeze(1), 1.0)
        return th.cat((logits_carrier, parameters), dim=1)

    def log_prob(self, actions: th.Tensor) -> th.Tensor:
        operation = self._operation_indices(actions)
        parameter_actions = actions[:, len(OPERATION_TYPES) :]
        active = self._active.to(actions.device)[operation]
        parameter_log_prob = self.parameter_distribution.log_prob(parameter_actions)
        return self.operation_distribution.log_prob(operation) + (parameter_log_prob * active).sum(
            dim=1
        )

    def entropy(self) -> th.Tensor:
        active = self._active.to(self.parameter_distribution.loc.device)
        conditional_parameter_entropy = self.parameter_distribution.entropy() @ active.T
        expected_parameter_entropy = (
            self.operation_distribution.probs * conditional_parameter_entropy
        ).sum(dim=1)
        return self.operation_distribution.entropy() + expected_parameter_entropy

    def sample(self) -> th.Tensor:
        operation = self.operation_distribution.sample()
        return self._pack(operation, self.parameter_distribution.rsample())

    def mode(self) -> th.Tensor:
        operation = self.operation_distribution.probs.argmax(dim=1)
        return self._pack(operation, self.parameter_distribution.mean)

    def actions_from_params(
        self,
        operation_logits: th.Tensor,
        parameter_means: th.Tensor,
        parameter_log_std: th.Tensor,
        operation_mask: th.Tensor,
        deterministic: bool = False,
    ) -> th.Tensor:
        self.proba_distribution(
            operation_logits,
            parameter_means,
            parameter_log_std,
            operation_mask,
        )
        return self.get_actions(deterministic=deterministic)

    def log_prob_from_params(
        self,
        operation_logits: th.Tensor,
        parameter_means: th.Tensor,
        parameter_log_std: th.Tensor,
        operation_mask: th.Tensor,
    ) -> tuple[th.Tensor, th.Tensor]:
        actions = self.actions_from_params(
            operation_logits,
            parameter_means,
            parameter_log_std,
            operation_mask,
        )
        return actions, self.log_prob(actions)


class ConditionalHybridActorCriticPolicy(ActorCriticPolicy):
    """Actor-critic policy whose probability law matches the hybrid contract."""

    def __init__(
        self,
        *args: Any,
        parameter_keys: tuple[str, ...] | list[str],
        **kwargs: Any,
    ) -> None:
        self.parameter_keys = tuple(parameter_keys)
        if not self.parameter_keys:
            raise ValueError("conditional hybrid policy requires parameter keys")
        super().__init__(*args, **kwargs)

    def _build(self, lr_schedule: Schedule) -> None:
        self._build_mlp_extractor()
        latent_dim_pi = self.mlp_extractor.latent_dim_pi
        self.hybrid_action_dist = ConditionalHybridDistribution(self.parameter_keys)
        self.action_dist = self.hybrid_action_dist
        self.action_net = nn.Linear(
            latent_dim_pi, len(OPERATION_TYPES) + len(self.parameter_keys)
        )
        self.log_std = nn.Parameter(
            th.ones(len(self.parameter_keys)) * self.log_std_init,
            requires_grad=True,
        )
        self.value_net = nn.Linear(self.mlp_extractor.latent_dim_vf, 1)
        if self.ortho_init:
            module_gains = {
                self.features_extractor: np.sqrt(2),
                self.mlp_extractor: np.sqrt(2),
                self.action_net: 0.01,
                self.value_net: 1,
            }
            if not self.share_features_extractor:
                del module_gains[self.features_extractor]
                module_gains[self.pi_features_extractor] = np.sqrt(2)
                module_gains[self.vf_features_extractor] = np.sqrt(2)
            for module, gain in module_gains.items():
                module.apply(partial(self.init_weights, gain=gain))
        self.optimizer = self.optimizer_class(  # type: ignore[call-arg, unused-ignore]
            self.parameters(), lr=lr_schedule(1), **self.optimizer_kwargs
        )

    def _joint_distribution(
        self, obs: th.Tensor, latent_pi: th.Tensor
    ) -> ConditionalHybridDistribution:
        output = self.action_net(latent_pi)
        operation_logits = output[:, : len(OPERATION_TYPES)]
        parameter_means = output[:, len(OPERATION_TYPES) :]
        operation_mask = obs[:, -(len(OPERATION_TYPES) + 3) : -3] > 0.5
        return self.hybrid_action_dist.proba_distribution(
            operation_logits,
            parameter_means,
            self.log_std,
            operation_mask,
        )

    def forward(
        self, obs: th.Tensor, deterministic: bool = False
    ) -> tuple[th.Tensor, th.Tensor, th.Tensor]:
        features = self.extract_features(obs)
        if self.share_features_extractor:
            latent_pi, latent_vf = self.mlp_extractor(features)
        else:
            pi_features, vf_features = features
            latent_pi = self.mlp_extractor.forward_actor(pi_features)
            latent_vf = self.mlp_extractor.forward_critic(vf_features)
        values = self.value_net(latent_vf)
        distribution = self._joint_distribution(obs, latent_pi)
        actions = distribution.get_actions(deterministic=deterministic)
        log_prob = distribution.log_prob(actions)
        action_shape = tuple(self.action_space.shape or ())
        return actions.reshape((-1, *action_shape)), values, log_prob

    def evaluate_actions(
        self, obs: PyTorchObs, actions: th.Tensor
    ) -> tuple[th.Tensor, th.Tensor, th.Tensor]:
        if not isinstance(obs, th.Tensor):
            raise TypeError("conditional hybrid policy requires tensor observations")
        features = self.extract_features(obs)
        if self.share_features_extractor:
            latent_pi, latent_vf = self.mlp_extractor(features)
        else:
            pi_features, vf_features = features
            latent_pi = self.mlp_extractor.forward_actor(pi_features)
            latent_vf = self.mlp_extractor.forward_critic(vf_features)
        distribution = self._joint_distribution(obs, latent_pi)
        return self.value_net(latent_vf), distribution.log_prob(actions), distribution.entropy()

    def get_distribution(self, obs: PyTorchObs) -> Distribution:
        if not isinstance(obs, th.Tensor):
            raise TypeError("conditional hybrid policy requires tensor observations")
        features = super().extract_features(obs, self.pi_features_extractor)
        if isinstance(features, tuple):
            features = features[0]
        latent_pi = self.mlp_extractor.forward_actor(features)
        return self._joint_distribution(obs, latent_pi)

    def _get_constructor_parameters(self) -> dict[str, Any]:
        payload = super()._get_constructor_parameters()
        payload["parameter_keys"] = list(self.parameter_keys)
        return payload


__all__ = [
    "POLICY_DISTRIBUTION_SCHEMA_VERSION",
    "ConditionalHybridActorCriticPolicy",
    "ConditionalHybridDistribution",
    "policy_distribution_contract",
]
