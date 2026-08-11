"""Stable-Baselines3 training entry point with checkpoint provenance."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from time import perf_counter, process_time
from typing import Any, Literal

from chemworld.rl.batched_vec_env import BatchedSubprocVecEnv
from chemworld.rl.checkpoint_contract import (
    RL_CHECKPOINT_MANIFEST_SCHEMA_VERSION,
    RL_CHECKPOINT_SIDECAR_SCHEMA_VERSION,
)
from chemworld.rl.environment import RLWorldAllocation, build_rl_environment
from chemworld.rl.hybrid_actions import policy_distribution_contract
from chemworld.rl.hybrid_policy import (
    ConditionalHybridActorCriticPolicy,
)
from chemworld.rl.observation_contract import rl_observation_contract

AlgorithmName = Literal["ppo", "sac"]
TrainingDevice = Literal["cpu", "cuda"]
VectorizationBackend = Literal["dummy", "subprocess"]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _children_cpu_time_s() -> float:
    times = os.times()
    return float(times.children_user + times.children_system)


def _windows_process_cpu_time_s(process: Any) -> float:
    """Read user+kernel CPU from a retained multiprocessing process handle."""

    import ctypes
    from ctypes import wintypes

    popen = getattr(process, "_popen", None)
    handle = getattr(popen, "_handle", None)
    if handle is None:
        raise RuntimeError("subprocess CPU accounting is missing a Windows process handle")
    creation = wintypes.FILETIME()
    exit_time = wintypes.FILETIME()
    kernel = wintypes.FILETIME()
    user = wintypes.FILETIME()
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        raise RuntimeError("Windows ctypes loader is unavailable")
    get_process_times = windll.kernel32.GetProcessTimes
    get_process_times.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME),
    ]
    get_process_times.restype = wintypes.BOOL
    if not get_process_times(
        int(handle),
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel),
        ctypes.byref(user),
    ):
        raise RuntimeError("GetProcessTimes failed for an RL environment worker")

    def seconds(value: Any) -> float:
        ticks = (int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime)
        return ticks / 10_000_000.0

    return seconds(kernel) + seconds(user)


def _worker_cpu_time_s(processes: list[Any], *, children_started: float) -> tuple[float, str]:
    if not processes:
        return 0.0, "not_applicable_in_process_vectorization"
    if os.name == "nt":
        return (
            sum(_windows_process_cpu_time_s(process) for process in processes),
            "windows_GetProcessTimes_retained_worker_handles",
        )
    elapsed = _children_cpu_time_s() - children_started
    if elapsed < 0.0:
        raise RuntimeError("subprocess child CPU accounting moved backwards")
    return elapsed, "os_times_children_user_plus_system_delta"


def _action_contract(env: Any) -> dict[str, Any]:
    current = env
    while current is not None:
        factory = getattr(current, "action_contract", None)
        if callable(factory):
            return dict(factory())
        current = getattr(current, "env", None)
    raise RuntimeError("RL environment is missing its continuous action contract")


def _optional_wrapper_payload(env: Any, method: str) -> dict[str, Any] | None:
    current = env
    while current is not None:
        factory = getattr(current, method, None)
        if callable(factory):
            return dict(factory())
        current = getattr(current, "env", None)
    return None


def _aggregate_training_diagnostics(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        raise RuntimeError("vectorized RL training returned no environment diagnostics")
    count_keys = {
        "step_count",
        "episode_count",
        "invalid_action_count",
        "transaction_rollback_count",
        "constitution_failure_count",
        "runtime_domain_failure_count",
        "observation_domain_failure_count",
        "measurement_count",
        "completed_experiment_count",
        "behavior_complete_experiment_count",
        "quick_close_count",
        "core_requirement_satisfied_count",
        "newly_unlocked_operation_count",
        "unsafe_step_count",
        "high_cost_step_count",
    }
    sum_keys = {"raw_reward_sum", "shaped_reward_sum"}
    payload: dict[str, Any] = {
        key: sum(int(item.get(key, 0)) for item in items) for key in count_keys
    }
    payload.update({key: sum(float(item.get(key, 0.0)) for item in items) for key in sum_keys})
    core_counts: dict[str, int] = {}
    for item in items:
        for operation, count in dict(item.get("core_operation_counts", {})).items():
            core_counts[str(operation)] = core_counts.get(str(operation), 0) + int(count)
    payload["core_operation_counts"] = dict(sorted(core_counts.items()))
    steps = max(int(payload["step_count"]), 1)
    completed = max(int(payload["completed_experiment_count"]), 1)
    payload["invalid_action_rate"] = payload["invalid_action_count"] / steps
    payload["completed_experiments_per_1000_steps"] = (
        1000.0 * payload["completed_experiment_count"] / steps
    )
    payload["quick_close_rate"] = payload["quick_close_count"] / completed
    payload["environment_count"] = len(items)
    return payload


def train_sb3_baseline(
    *,
    algorithm: AlgorithmName,
    task_id: str,
    allocation: RLWorldAllocation,
    total_timesteps: int,
    model_seed: int,
    output_dir: str | Path,
    algorithm_kwargs: dict[str, Any] | None = None,
    operation_budget: int | None = None,
    checkpoint_interval_steps: int | None = None,
    checkpoint_steps: Sequence[int] | None = None,
    save_replay_buffer: bool = False,
    parallel_environments: int = 1,
    vectorization_backend: VectorizationBackend = "dummy",
    device: TrainingDevice = "cpu",
    torch_num_threads: int | None = None,
    progress_interval_steps: int | None = None,
) -> dict[str, Any]:
    """Train one baseline and retain the model plus a complete compute manifest."""

    if algorithm not in {"ppo", "sac"}:
        raise ValueError("algorithm must be ppo or sac")
    if total_timesteps <= 0:
        raise ValueError("total_timesteps must be positive")
    if checkpoint_interval_steps is not None and checkpoint_interval_steps <= 0:
        raise ValueError("checkpoint_interval_steps must be positive")
    exact_checkpoint_steps = tuple(int(step) for step in (checkpoint_steps or ()))
    if checkpoint_interval_steps is not None and exact_checkpoint_steps:
        raise ValueError("checkpoint_interval_steps and checkpoint_steps are mutually exclusive")
    if exact_checkpoint_steps and (
        any(step <= 0 for step in exact_checkpoint_steps)
        or tuple(sorted(set(exact_checkpoint_steps))) != exact_checkpoint_steps
        or exact_checkpoint_steps[-1] > total_timesteps
    ):
        raise ValueError(
            "checkpoint_steps must be unique, increasing, positive, and within total_timesteps"
        )
    if allocation.name != "train":
        raise ValueError("formal RL training accepts only the train allocation")
    if parallel_environments <= 0:
        raise ValueError("parallel_environments must be positive")
    if torch_num_threads is not None and torch_num_threads <= 0:
        raise ValueError("torch_num_threads must be positive")
    if progress_interval_steps is not None and progress_interval_steps <= 0:
        raise ValueError("progress_interval_steps must be positive")
    if vectorization_backend not in {"dummy", "subprocess"}:
        raise ValueError("vectorization_backend must be dummy or subprocess")
    if parallel_environments == 1 and vectorization_backend == "subprocess":
        raise ValueError("subprocess vectorization requires at least two environments")
    if checkpoint_interval_steps is not None and (
        checkpoint_interval_steps % parallel_environments
    ):
        raise ValueError("checkpoint_interval_steps must be divisible by parallel_environments")
    if any(step % parallel_environments for step in exact_checkpoint_steps):
        raise ValueError("every checkpoint_steps value must be divisible by parallel_environments")
    if progress_interval_steps is not None and (progress_interval_steps % parallel_environments):
        raise ValueError("progress_interval_steps must be divisible by parallel_environments")
    try:
        import stable_baselines3 as sb3
        import torch
        from stable_baselines3.common.callbacks import BaseCallback, CheckpointCallback
        from stable_baselines3.common.vec_env import DummyVecEnv
    except ImportError as exc:
        raise RuntimeError("install ChemWorld with the 'rl' extra to train PPO or SAC") from exc

    algorithm_class = sb3.PPO if algorithm == "ppo" else sb3.SAC
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA training was requested but this PyTorch runtime has no CUDA")
    initial_torch_num_threads = int(torch.get_num_threads())
    if torch_num_threads is not None:
        torch.set_num_threads(torch_num_threads)
    resolved_torch_num_threads = int(torch.get_num_threads())
    requested_device = device
    probe_env = build_rl_environment(
        task_id=task_id,
        allocation=allocation,
        sampler_seed=model_seed,
        operation_budget=operation_budget,
        training_reward=True,
    )
    try:
        action_contract = _action_contract(probe_env)
        training_reward_contract = _optional_wrapper_payload(probe_env, "reward_contract")
        observation_shape = list(probe_env.observation_space.shape or ())
    finally:
        probe_env.close()
    observation_contract = rl_observation_contract(task_id)
    if observation_shape != observation_contract["shape"]:
        raise RuntimeError("RL environment observation shape does not match its published contract")
    observation_contract_hash = str(observation_contract.get("contract_hash", ""))
    if len(observation_contract_hash) != 64:
        raise RuntimeError("RL observation contract is missing its compatibility hash")
    env_factories: list[Callable[[], Any]] = [
        partial(
            build_rl_environment,
            task_id=task_id,
            allocation=allocation,
            sampler_seed=model_seed + rank,
            operation_budget=operation_budget,
            training_reward=True,
        )
        for rank in range(parallel_environments)
    ]
    children_cpu_started = _children_cpu_time_s()
    if vectorization_backend == "subprocess":
        env: Any = BatchedSubprocVecEnv(env_factories, start_method="spawn")
        subprocess_start_strategy = "spawn_single_batched_environment_worker"
    else:
        env = DummyVecEnv(env_factories)
        subprocess_start_strategy = "not_applicable_in_process_vectorization"
    worker_processes = list(getattr(env, "processes", ()))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    checkpoint_stem = output / f"{algorithm}-{task_id}-seed{model_seed}"
    periodic_dir = output / "checkpoints"
    action_contract_hash = str(action_contract.get("contract_hash", ""))
    if len(action_contract_hash) != 64:
        raise RuntimeError("RL action contract is missing its compatibility hash")
    if (
        training_reward_contract is None
        or len(str(training_reward_contract.get("contract_hash", ""))) != 64
    ):
        raise RuntimeError("RL training reward contract is missing its compatibility hash")
    parameter_keys = tuple(
        str(item) for item in action_contract["training_adapter"]["parameter_coordinate_keys"]
    )
    if algorithm == "ppo":
        policy: Any = ConditionalHybridActorCriticPolicy
        policy_kwargs = dict((algorithm_kwargs or {}).get("policy_kwargs", {}))
        policy_kwargs["parameter_keys"] = parameter_keys
        resolved_algorithm_kwargs = dict(algorithm_kwargs or {})
        resolved_algorithm_kwargs.pop("policy_kwargs", None)
        distribution_contract = policy_distribution_contract(parameter_keys)
    else:
        policy = "MlpPolicy"
        policy_kwargs = dict((algorithm_kwargs or {}).get("policy_kwargs", {}))
        resolved_algorithm_kwargs = dict(algorithm_kwargs or {})
        resolved_algorithm_kwargs.pop("policy_kwargs", None)
        distribution_contract = {
            "schema_version": "chemworld-sac-box-gaussian-diagnostic-0.1",
            "native_hybrid_distribution": False,
            "contract_hash": None,
        }
    wall_started = perf_counter()
    cpu_started = process_time()
    try:
        callback: BaseCallback | None = None
        if exact_checkpoint_steps or progress_interval_steps is not None:
            periodic_dir.mkdir(parents=True, exist_ok=True)

            class _ExactCheckpointCallback(BaseCallback):
                def __init__(self) -> None:
                    super().__init__(verbose=0)
                    self._targets = set(exact_checkpoint_steps)
                    self._saved: set[int] = set()

                def _on_step(self) -> bool:
                    step = int(self.num_timesteps)
                    if progress_interval_steps is not None and (
                        step % progress_interval_steps == 0 or step == total_timesteps
                    ):
                        progress_path = output / "training-progress.json"
                        progress_path.write_text(
                            json.dumps(
                                {
                                    "schema_version": "chemworld-rl-training-progress-0.1",
                                    "algorithm": algorithm,
                                    "task_id": task_id,
                                    "model_seed": model_seed,
                                    "training_environment_step_count": step,
                                    "requested_training_environment_step_count": total_timesteps,
                                    "progress_fraction": step / total_timesteps,
                                },
                                indent=2,
                                sort_keys=True,
                            )
                            + "\n",
                            encoding="utf-8",
                        )
                    if step not in self._targets or step in self._saved:
                        return True
                    checkpoint_path = periodic_dir / f"{checkpoint_stem.name}_{step}_steps"
                    self.model.save(checkpoint_path)
                    if save_replay_buffer:
                        save_buffer = getattr(self.model, "save_replay_buffer", None)
                        if not callable(save_buffer):
                            raise RuntimeError(
                                "replay-buffer checkpointing requested for an unsupported algorithm"
                            )
                        save_buffer(
                            periodic_dir / f"{checkpoint_stem.name}_replay_buffer_{step}_steps.pkl"
                        )
                    self._saved.add(step)
                    return True

            callback = _ExactCheckpointCallback()
        elif checkpoint_interval_steps is not None:
            periodic_dir.mkdir(parents=True, exist_ok=True)
            callback = CheckpointCallback(
                save_freq=checkpoint_interval_steps // parallel_environments,
                save_path=str(periodic_dir),
                name_prefix=checkpoint_stem.name,
                save_replay_buffer=save_replay_buffer,
                save_vecnormalize=False,
            )
        model = algorithm_class(
            policy,
            env,
            seed=model_seed,
            verbose=0,
            device=device,
            policy_kwargs=policy_kwargs,
            **resolved_algorithm_kwargs,
        )
        model.learn(
            total_timesteps=total_timesteps,
            progress_bar=False,
            callback=callback,
        )
        model.save(checkpoint_stem)
        actual_timesteps = int(model.num_timesteps)
        resolved_device = str(model.device)
        training_diagnostics = _aggregate_training_diagnostics(
            [dict(item) for item in env.env_method("training_diagnostics")]
        )
    finally:
        env.close()
    wall_time_s = perf_counter() - wall_started
    parent_cpu_time_s = process_time() - cpu_started
    worker_cpu_time_s, worker_cpu_accounting_method = _worker_cpu_time_s(
        worker_processes, children_started=children_cpu_started
    )
    cpu_time_s = parent_cpu_time_s + worker_cpu_time_s
    checkpoint = checkpoint_stem.with_suffix(".zip")
    if (
        training_diagnostics is not None
        and int(training_diagnostics.get("step_count", -1)) != actual_timesteps
    ):
        raise RuntimeError("SB3 and environment training-step ledgers disagree")
    periodic_artifacts = [
        {
            "path": str(path.relative_to(output)),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
            "artifact_type": ("replay_buffer" if "_replay_buffer_" in path.name else "checkpoint"),
        }
        for path in sorted(periodic_dir.glob("*"))
        if path.is_file()
    ]
    periodic_contract_manifests: list[dict[str, Any]] = []
    for artifact in periodic_artifacts:
        if artifact["artifact_type"] != "checkpoint":
            continue
        periodic_checkpoint = output / str(artifact["path"])
        match = re.search(r"_(\d+)_steps$", periodic_checkpoint.stem)
        sidecar = {
            "schema_version": RL_CHECKPOINT_SIDECAR_SCHEMA_VERSION,
            "algorithm": algorithm,
            "task_id": task_id,
            "training_environment_step_count": int(match.group(1)) if match else None,
            "checkpoint": periodic_checkpoint.name,
            "checkpoint_sha256": artifact["sha256"],
            "observation_contract_hash": observation_contract_hash,
            "action_contract_hash": action_contract_hash,
            "training_reward_contract_hash": training_reward_contract["contract_hash"],
            "policy_distribution_contract_hash": distribution_contract.get("contract_hash"),
            "shape_only_compatible": False,
            "legacy_checkpoint_compatible": False,
        }
        sidecar_path = periodic_checkpoint.with_suffix(".manifest.json")
        sidecar_path.write_text(
            json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        periodic_contract_manifests.append(
            {
                "path": str(sidecar_path.relative_to(output)),
                "sha256": _sha256(sidecar_path),
            }
        )
    manifest = {
        "schema_version": RL_CHECKPOINT_MANIFEST_SCHEMA_VERSION,
        "formal_evidence": False,
        "algorithm": algorithm,
        "task_id": task_id,
        "model_seed": model_seed,
        "allocation": allocation.public_manifest(),
        "action_contract": action_contract,
        "action_contract_hash": action_contract_hash,
        "training_reward_contract": training_reward_contract,
        "training_reward_contract_hash": training_reward_contract["contract_hash"],
        "policy_distribution_contract": distribution_contract,
        "policy_distribution_contract_hash": distribution_contract.get("contract_hash"),
        "observation_contract": observation_contract,
        "observation_contract_hash": observation_contract_hash,
        "checkpoint_compatibility": {
            "policy": "exact_contract_hash_match",
            "shape_only_compatible": False,
            "legacy_checkpoint_compatible": False,
        },
        "training_diagnostics": training_diagnostics,
        "observation_shape": observation_shape,
        "requested_training_environment_step_count": total_timesteps,
        "training_environment_step_count": actual_timesteps,
        "step_budget_exact": actual_timesteps == total_timesteps,
        "checkpoint_interval_steps": checkpoint_interval_steps,
        "checkpoint_steps": list(exact_checkpoint_steps),
        "periodic_checkpoint_artifacts": periodic_artifacts,
        "periodic_checkpoint_contract_manifests": periodic_contract_manifests,
        "replay_buffer_checkpointed": bool(save_replay_buffer),
        "operation_budget": operation_budget,
        "bench_finetuning_used": False,
        "training_infrastructure": {
            "parallel_environments": parallel_environments,
            "vectorization_backend": vectorization_backend,
            "subprocess_start_strategy": subprocess_start_strategy,
            "subprocess_worker_process_count": len(worker_processes),
            "environments_per_worker_process": (
                parallel_environments // len(worker_processes) if worker_processes else None
            ),
            "requested_device": requested_device,
            "resolved_device": resolved_device,
            "logical_cpu_count": os.cpu_count(),
            "initial_torch_num_threads": initial_torch_num_threads,
            "requested_torch_num_threads": torch_num_threads,
            "torch_num_threads": resolved_torch_num_threads,
            "cuda_available": torch.cuda.is_available(),
            "torch_cuda_version": torch.version.cuda,
            "cuda_device_name": (
                torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
            ),
            "environment_steps_per_wall_second": actual_timesteps / max(wall_time_s, 1e-12),
            "average_process_cpu_cores": cpu_time_s / max(wall_time_s, 1e-12),
            "parent_process_cpu_time_s": parent_cpu_time_s,
            "worker_process_cpu_time_s": worker_cpu_time_s,
            "worker_process_cpu_accounting_method": worker_cpu_accounting_method,
        },
        "wall_time_s": wall_time_s,
        "cpu_time_s": cpu_time_s,
        "gpu_time_s": 0.0,
        "device": resolved_device,
        "progress_interval_steps": progress_interval_steps,
        "checkpoint": checkpoint.name,
        "checkpoint_sha256": _sha256(checkpoint),
        "versions": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "stable_baselines3": sb3.__version__,
            "torch": torch.__version__,
        },
        "limitations": [
            "This checkpoint is diagnostic until the full frozen training budget is consumed.",
            (
                "Formal eligibility also requires replay-verified Bench evaluation "
                "and paired statistics."
            ),
        ],
    }
    manifest_path = checkpoint_stem.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


__all__ = ["train_sb3_baseline"]
