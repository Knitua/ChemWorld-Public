#!/usr/bin/env python3
"""Deterministically remove private release metadata from frozen evidence reports."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "evidence" / "reports"
SANITIZER_VERSION = "chemworld-public-evidence-sanitizer-1.0"
RECEIPT_SCHEMA_VERSION = "chemworld-public-evidence-sanitization-receipt-1.0"

REPORT_PROTOCOLS = {
    "composition-qualification.json.gz": "protocols/composition-qualification.md",
    "deterministic-use-cases.json.gz": "protocols/deterministic-use-cases.md",
    "controlled-world-forks.json.gz": "protocols/controlled-world-forks.md",
    "agent-instrument-use.json.gz": "protocols/agent-instrument-use.md",
}

_DROP_KEY_CATEGORIES = {
    "source_binding": "internal_source_binding",
    "source_bindings": "internal_source_binding",
    "task_design_binding": "private_execution_registry",
    "current_registry": "private_execution_registry",
    "session_id": "provider_session_identifier",
    "thread_id": "provider_session_identifier",
    "request_id": "provider_session_identifier",
}
_INTERNAL_WORKSTREAM_PREFIX = "work" + "streams/"
_INTERNAL_TODO_NAME = "FIRST_PAPER" + "_TODOLIST"
_FORBIDDEN_TEXT = re.compile(
    re.escape(_INTERNAL_WORKSTREAM_PREFIX)
    + "|"
    + re.escape(_INTERNAL_TODO_NAME)
    + "|"
    r"/(?:root|home|mnt|Users)/(?:[^\s\"']+)|"
    r"(?:^|[^A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}|"
    r"gh[pousr]_[A-Za-z0-9]{20,}|"
    r"AKIA[0-9A-Z]{16}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    re.IGNORECASE,
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _gzip_bytes(value: bytes) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(value)
    return output.getvalue()


def _sanitize_value(
    value: Any,
    *,
    path: str,
    removed: list[dict[str, Any]],
) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        in_existing_evidence = path == "$.existing_evidence" or path.startswith(
            "$.existing_evidence."
        )
        for key, child in value.items():
            category = _DROP_KEY_CATEGORIES.get(key)
            if key == "binding" and in_existing_evidence:
                category = "internal_source_binding"
            if category is not None:
                removed.append(
                    {
                        "category": category,
                        "field": key,
                        "path_sha256": _sha256_bytes(f"{path}.{key}".encode()),
                        "value_sha256": _sha256_bytes(_canonical_bytes(child)),
                    }
                )
                continue
            result[key] = _sanitize_value(
                child,
                path=f"{path}.{key}",
                removed=removed,
            )
        return result
    if isinstance(value, list):
        return [
            _sanitize_value(child, path=f"{path}[{index}]", removed=removed)
            for index, child in enumerate(value)
        ]
    return value


def _assert_public(value: Any, *, report_name: str) -> None:
    findings: list[str] = []

    def visit(item: Any, path: str) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in {"raw_response", "response_body", "prompt_body", "reasoning_body"}:
                    findings.append(f"{path}.{key}: raw provider payload field")
                visit(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")
        elif isinstance(item, str) and _FORBIDDEN_TEXT.search(item):
            findings.append(f"{path}: forbidden private text")

    visit(value, "$")
    if findings:
        raise RuntimeError(f"{report_name} is not public-safe: " + "; ".join(findings[:20]))


def _sanitize_report(report_name: str, protocol_relative: str) -> dict[str, Any]:
    report_path = REPORT_ROOT / report_name
    protocol_path = ROOT / protocol_relative
    raw_compressed = report_path.read_bytes()
    with gzip.open(io.BytesIO(raw_compressed), "rt", encoding="utf-8") as handle:
        source = json.load(handle)
    if not isinstance(source, dict):
        raise RuntimeError(f"JSON object required: {report_path}")

    existing_receipt = source.pop("release_sanitization", None)
    removed: list[dict[str, Any]] = []
    sanitized = _sanitize_value(source, path="$", removed=removed)
    if not isinstance(sanitized, dict):
        raise AssertionError("sanitized report must remain a JSON object")

    if existing_receipt is not None:
        if not isinstance(existing_receipt, dict):
            raise RuntimeError(f"invalid existing sanitization receipt: {report_name}")
        if existing_receipt.get("sanitizer_version") != SANITIZER_VERSION:
            raise RuntimeError(f"unsupported existing sanitizer version: {report_name}")
        if removed:
            raise RuntimeError(f"new private metadata appeared after sanitization: {report_name}")
        source_report = existing_receipt["source_report"]
        removed_metadata = existing_receipt["removed_metadata"]
    else:
        source_report = {
            "compressed_sha256": _sha256_bytes(raw_compressed),
            "canonical_json_sha256": _sha256_bytes(_canonical_bytes(source)),
        }
        categories = Counter(item["category"] for item in removed)
        removed_metadata = {
            "entry_count": len(removed),
            "categories": dict(sorted(categories.items())),
            "summary_sha256": _sha256_bytes(_canonical_bytes(removed)),
        }

    receipt = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "sanitizer_version": SANITIZER_VERSION,
        "source_report": source_report,
        "removed_metadata": removed_metadata,
        "public_protocol": {
            "path": protocol_relative,
            "sha256": _sha256_path(protocol_path),
        },
        "serialization": {
            "json": "utf-8; sort_keys=true; separators=(',', ':'); trailing_newline=true",
            "gzip_compresslevel": 9,
            "gzip_mtime": 0,
        },
    }
    sanitized["release_sanitization"] = receipt
    _assert_public(sanitized, report_name=report_name)
    encoded = _gzip_bytes(_canonical_bytes(sanitized))
    report_path.write_bytes(encoded)
    return {
        "path": report_path.relative_to(ROOT).as_posix(),
        "bytes": len(encoded),
        "sha256": _sha256_bytes(encoded),
        "removed_metadata_entries": removed_metadata["entry_count"],
    }


def main() -> int:
    rows = [
        _sanitize_report(report_name, protocol)
        for report_name, protocol in REPORT_PROTOCOLS.items()
    ]
    print(json.dumps({"status": "passed", "reports": rows}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
