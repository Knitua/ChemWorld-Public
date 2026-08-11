"""Memory-bounded subprocess vectorization for Windows RL training."""

from __future__ import annotations

import multiprocessing as mp
from collections.abc import Callable, Sequence
from typing import Any, cast

import gymnasium as gym
import numpy as np
from stable_baselines3.common.vec_env.base_vec_env import (
    CloudpickleWrapper,
    VecEnv,
    VecEnvIndices,
    VecEnvObs,
    VecEnvStepReturn,
)


def _batched_worker(
    remote: Any,
    parent_remote: Any,
    env_fns_wrapper: CloudpickleWrapper,
) -> None:
    """Host every vector slot in one spawned worker and expose the VecEnv RPC surface."""

    from stable_baselines3.common.vec_env import DummyVecEnv

    parent_remote.close()
    env = DummyVecEnv(env_fns_wrapper.var)
    try:
        while True:
            command, data = remote.recv()
            if command == "step":
                env.step_async(data)
                remote.send(env.step_wait())
            elif command == "reset":
                seeds, options = data
                env._seeds = list(seeds)
                env._options = list(options)
                observation = env.reset()
                remote.send((observation, env.reset_infos))
            elif command == "get_spaces":
                remote.send((env.observation_space, env.action_space, env.num_envs))
            elif command == "get_attr":
                attribute, indices = data
                remote.send(env.get_attr(attribute, indices=indices))
            elif command == "set_attr":
                attribute, value, indices = data
                env.set_attr(attribute, value, indices=indices)
                remote.send(None)
            elif command == "env_method":
                method, args, kwargs, indices = data
                remote.send(env.env_method(method, *args, indices=indices, **kwargs))
            elif command == "is_wrapped":
                wrapper, indices = data
                remote.send(env.env_is_wrapped(wrapper, indices=indices))
            elif command == "render":
                remote.send(env.get_images())
            elif command == "close":
                break
            else:
                raise NotImplementedError(f"unsupported batched VecEnv command: {command}")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        env.close()
        remote.close()


class BatchedSubprocVecEnv(VecEnv):
    """Expose many vector slots through one spawned environment worker.

    Stable-Baselines3 still observes the preregistered number and ordering of
    environments. Only the operating-system process layout changes, avoiding
    one SciPy/PyTorch DLL address space per vector slot on Windows.
    """

    def __init__(
        self,
        env_fns: list[Callable[[], gym.Env[Any, Any]]],
        *,
        start_method: str = "spawn",
    ) -> None:
        if not env_fns:
            raise ValueError("batched subprocess vectorization requires environments")
        self.waiting = False
        self.closed = False
        context = mp.get_context(start_method)
        self.remote, work_remote = context.Pipe()
        process_factory: Any = cast(Any, context).Process
        self.process = process_factory(
            target=_batched_worker,
            args=(work_remote, self.remote, CloudpickleWrapper(env_fns)),
            daemon=True,
        )
        self.processes = [self.process]
        try:
            self.process.start()
            work_remote.close()
            self.remote.send(("get_spaces", None))
            observation_space, action_space, environment_count = self.remote.recv()
            if environment_count != len(env_fns):
                raise RuntimeError("batched worker environment count changed during startup")
            super().__init__(environment_count, observation_space, action_space)
        except BaseException:
            work_remote.close()
            self.remote.close()
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=5.0)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=5.0)
            raise

    def _indices(self, indices: VecEnvIndices) -> list[int]:
        return list(self._get_indices(indices))

    def step_async(self, actions: np.ndarray) -> None:
        self.remote.send(("step", actions))
        self.waiting = True

    def step_wait(self) -> VecEnvStepReturn:
        result = self.remote.recv()
        self.waiting = False
        return result

    def reset(self) -> VecEnvObs:
        self.remote.send(("reset", (self._seeds, self._options)))
        observation, self.reset_infos = self.remote.recv()
        self._reset_seeds()
        self._reset_options()
        return observation

    def close(self) -> None:
        if self.closed:
            return
        if self.waiting:
            self.remote.recv()
            self.waiting = False
        if self.process.is_alive():
            self.remote.send(("close", None))
        self.process.join(timeout=30.0)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(timeout=5.0)
        self.remote.close()
        self.closed = True

    def get_images(self) -> Sequence[np.ndarray | None]:
        self.remote.send(("render", None))
        return self.remote.recv()

    def get_attr(self, attr_name: str, indices: VecEnvIndices = None) -> list[Any]:
        self.remote.send(("get_attr", (attr_name, self._indices(indices))))
        return self.remote.recv()

    def set_attr(self, attr_name: str, value: Any, indices: VecEnvIndices = None) -> None:
        self.remote.send(("set_attr", (attr_name, value, self._indices(indices))))
        self.remote.recv()

    def env_method(
        self,
        method_name: str,
        *method_args: Any,
        indices: VecEnvIndices = None,
        **method_kwargs: Any,
    ) -> list[Any]:
        self.remote.send(
            (
                "env_method",
                (method_name, method_args, method_kwargs, self._indices(indices)),
            )
        )
        return self.remote.recv()

    def env_is_wrapped(
        self,
        wrapper_class: type[gym.Wrapper[Any, Any, Any, Any]],
        indices: VecEnvIndices = None,
    ) -> list[bool]:
        self.remote.send(("is_wrapped", (wrapper_class, self._indices(indices))))
        return self.remote.recv()


__all__ = ["BatchedSubprocVecEnv"]
