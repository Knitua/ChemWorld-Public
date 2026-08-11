"""Immutable trial receipts and missing-only resume for confirmatory execution."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from chemworld.eval.provenance import canonical_json_sha256

TRIAL_RECEIPT_VERSION = "chemworld-confirmatory-trial-receipt-0.1"
TRIAL_MANIFEST_VERSION = "chemworld-confirmatory-trial-manifest-0.1"


@dataclass(frozen=True)
class ConfirmatoryTrialKey:
    """Canonical ``task x truth x world x changepoint x arm`` identity."""

    task_id: str
    truth_family: str
    world_cluster: str
    changepoint: int | str
    arm: str

    def __post_init__(self) -> None:
        for name in ("task_id", "truth_family", "world_cluster", "arm"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.changepoint, bool) or not isinstance(
            self.changepoint,
            int | str,
        ):
            raise ValueError("changepoint must be an integer or declared string")
        if isinstance(self.changepoint, int) and self.changepoint < 0:
            raise ValueError("numeric changepoint must be non-negative")
        if isinstance(self.changepoint, str) and not self.changepoint.strip():
            raise ValueError("string changepoint must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def sha256(self) -> str:
        return canonical_json_sha256(self.to_dict())


class DuplicateTrialKeyError(RuntimeError):
    """A trial key appeared twice or a terminal receipt would be replaced."""


class TrialBatchInfrastructureError(RuntimeError):
    """One or more retryable runner failures left missing terminal receipts."""

    def __init__(self, failure_count: int) -> None:
        super().__init__(
            f"{failure_count} trial infrastructure failure(s); "
            "successful receipts were retained and --resume will run only missing units"
        )
        self.failure_count = failure_count


def _is_retryable_infrastructure_failure(error: BaseException) -> bool:
    return isinstance(
        error,
        (
            BrokenProcessPool,
            ConnectionError,
            OSError,
            TimeoutError,
        ),
    )


def _write_json_once(path: Path, payload: Mapping[str, Any]) -> None:
    """Publish a fully flushed file atomically without replacement."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temp = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temp = Path(raw_temp)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temp, path)
        except FileExistsError as error:
            raise DuplicateTrialKeyError(
                f"immutable trial artifact already exists: {path}"
            ) from error
    finally:
        temp.unlink(missing_ok=True)


class ConfirmatoryTrialStore:
    """Write-once scientific results plus append-only infrastructure attempts."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.receipts = self.root / "receipts"
        self.infrastructure_attempts = self.root / "infrastructure_attempts"

    def receipt_path(self, key: ConfirmatoryTrialKey) -> Path:
        return self.receipts / f"{key.sha256}.json"

    def has_result(self, key: ConfirmatoryTrialKey) -> bool:
        return self.receipt_path(key).is_file()

    def load_result(self, key: ConfirmatoryTrialKey) -> Any:
        payload = json.loads(self.receipt_path(key).read_text(encoding="utf-8"))
        self._validate_receipt(payload, expected_key=key)
        return payload["result"]

    def write_result(
        self,
        key: ConfirmatoryTrialKey,
        result: Any,
        *,
        reason_code: str = "scientific_completed",
    ) -> Path:
        if not reason_code.startswith("scientific_"):
            raise ValueError("terminal result reason code must be scientific")
        payload = {
            "schema_version": TRIAL_RECEIPT_VERSION,
            "trial_key": key.to_dict(),
            "trial_key_sha256": key.sha256,
            "status": "completed",
            "reason_domain": "scientific",
            "reason_code": reason_code,
            "result": result,
            "result_sha256": canonical_json_sha256(result),
        }
        target = self.receipt_path(key)
        _write_json_once(target, payload)
        return target

    def record_infrastructure_failure(
        self,
        key: ConfirmatoryTrialKey,
        error: BaseException,
        *,
        log_reference: str | None = None,
        log_sha256: str | None = None,
    ) -> Path:
        if (log_reference is None) != (log_sha256 is None):
            raise ValueError("log reference and digest must be supplied together")
        payload = {
            "schema_version": TRIAL_RECEIPT_VERSION,
            "trial_key": key.to_dict(),
            "trial_key_sha256": key.sha256,
            "status": "retryable_infrastructure_failure",
            "reason_domain": "infrastructure",
            "reason_code": "infrastructure_worker_failure",
            "error_type": type(error).__name__,
            "error_message": str(error),
            "log_reference": log_reference,
            "log_sha256": log_sha256,
        }
        target = (
            self.infrastructure_attempts
            / key.sha256
            / f"{uuid4().hex}.json"
        )
        _write_json_once(target, payload)
        return target

    def audit(
        self,
        expected_keys: Sequence[ConfirmatoryTrialKey],
    ) -> dict[str, Any]:
        expected = _unique_keys(expected_keys)
        observed: dict[str, Mapping[str, Any]] = {}
        invalid: list[str] = []
        for path in sorted(self.receipts.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                digest = str(payload["trial_key_sha256"])
                self._validate_receipt(payload)
                if path.stem != digest or digest in observed:
                    raise ValueError("receipt path or uniqueness invariant failed")
                observed[digest] = payload
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                invalid.append(path.as_posix())
        failure_count = 0
        recovered: set[str] = set()
        for path in sorted(self.infrastructure_attempts.glob("*/*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                digest = str(payload["trial_key_sha256"])
                if (
                    payload.get("schema_version") != TRIAL_RECEIPT_VERSION
                    or payload.get("status") != "retryable_infrastructure_failure"
                    or payload.get("reason_domain") != "infrastructure"
                    or canonical_json_sha256(payload.get("trial_key")) != digest
                ):
                    raise ValueError("infrastructure attempt invariant failed")
                failure_count += 1
                if digest in observed:
                    recovered.add(digest)
            except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
                invalid.append(path.as_posix())
        expected_ids = set(expected)
        observed_ids = set(observed)
        missing = sorted(expected_ids - observed_ids)
        unexpected = sorted(observed_ids - expected_ids)
        manifest = {
            "schema_version": TRIAL_MANIFEST_VERSION,
            "expected_count": len(expected_ids),
            "completed_count": len(expected_ids & observed_ids),
            "missing_trial_key_sha256": missing,
            "unexpected_trial_key_sha256": unexpected,
            "duplicate_count": 0,
            "invalid_receipts": invalid,
            "infrastructure_attempt_count": failure_count,
            "recovered_infrastructure_failure_count": len(recovered),
            "complete": not missing and not unexpected and not invalid,
        }
        manifest["manifest_sha256"] = canonical_json_sha256(manifest)
        return manifest

    @staticmethod
    def _validate_receipt(
        payload: Mapping[str, Any],
        *,
        expected_key: ConfirmatoryTrialKey | None = None,
    ) -> None:
        digest = payload.get("trial_key_sha256")
        if (
            payload.get("schema_version") != TRIAL_RECEIPT_VERSION
            or payload.get("status") != "completed"
            or payload.get("reason_domain") != "scientific"
            or not str(payload.get("reason_code", "")).startswith("scientific_")
            or not isinstance(digest, str)
            or canonical_json_sha256(payload.get("trial_key")) != digest
            or canonical_json_sha256(payload.get("result"))
            != payload.get("result_sha256")
        ):
            raise ValueError("invalid terminal trial receipt")
        if expected_key is not None and digest != expected_key.sha256:
            raise ValueError("terminal receipt does not match expected trial key")


def execute_jobs_resumable(
    function: Callable[[Mapping[str, Any]], Any],
    jobs: Sequence[Mapping[str, Any]],
    keys: Sequence[ConfirmatoryTrialKey],
    *,
    workers: int,
    store: ConfirmatoryTrialStore,
    resume: bool,
) -> tuple[list[Any], dict[str, Any]]:
    """Execute missing jobs and durably publish each successful result."""

    if workers <= 0:
        raise ValueError("execution workers must be positive")
    if len(jobs) != len(keys):
        raise ValueError("every job must have exactly one trial key")
    _unique_keys(keys)
    results: dict[int, Any] = {}
    pending: list[tuple[int, Mapping[str, Any], ConfirmatoryTrialKey]] = []
    for index, (job, key) in enumerate(zip(jobs, keys, strict=True)):
        if store.has_result(key):
            if not resume:
                raise DuplicateTrialKeyError(
                    f"trial receipt already exists without --resume: {key.sha256}"
                )
            results[index] = store.load_result(key)
        else:
            pending.append((index, job, key))

    failures = 0
    if workers == 1:
        for index, job, key in pending:
            try:
                result = function(job)
            except BaseException as error:
                if not _is_retryable_infrastructure_failure(error):
                    raise
                store.record_infrastructure_failure(key, error)
                failures += 1
                continue
            store.write_result(key, result)
            results[index] = result
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(function, job): (index, key)
                for index, job, key in pending
            }
            for future in as_completed(future_map):
                index, key = future_map[future]
                try:
                    result = future.result()
                except BaseException as error:
                    if not _is_retryable_infrastructure_failure(error):
                        raise
                    store.record_infrastructure_failure(key, error)
                    failures += 1
                    continue
                store.write_result(key, result)
                results[index] = result
    if failures:
        raise TrialBatchInfrastructureError(failures)
    audit = store.audit(keys)
    if not audit["complete"]:
        raise RuntimeError("trial manifest is incomplete after execution")
    return [results[index] for index in range(len(jobs))], audit


def _unique_keys(
    keys: Sequence[ConfirmatoryTrialKey],
) -> dict[str, ConfirmatoryTrialKey]:
    unique: dict[str, ConfirmatoryTrialKey] = {}
    for key in keys:
        if key.sha256 in unique:
            raise DuplicateTrialKeyError(
                f"duplicate key in trial manifest: {key.sha256}"
            )
        unique[key.sha256] = key
    return unique


__all__ = [
    "TRIAL_MANIFEST_VERSION",
    "TRIAL_RECEIPT_VERSION",
    "ConfirmatoryTrialKey",
    "ConfirmatoryTrialStore",
    "DuplicateTrialKeyError",
    "TrialBatchInfrastructureError",
    "execute_jobs_resumable",
]
