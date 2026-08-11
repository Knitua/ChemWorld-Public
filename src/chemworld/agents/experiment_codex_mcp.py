"""Host-owned STDIO MCP bridge for one interactive ChemWorld experiment.

The process is launched by Codex as a configured MCP server, outside the
model-generated shell-command path.  It exposes only bounded public state and
file-IPC requests; the authoritative environment remains in the parent runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

MCP_SERVER_VERSION = "chemworld-experiment-codex-mcp-0.2"
IPC_VERSION = "chemworld-experiment-codex-ipc-0.2"
SERVER_NAME = "chemworld_lab"
SUPPORTED_TOOLS = (
    "material_information",
    "status",
    "history",
    "inspect_artifact",
    "step",
)


def _encode(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} is not a JSON object")
    return value


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(_encode(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(_encode(value) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())


class ChemWorldMCPServer:
    """Minimal, dependency-free MCP server with a deliberately narrow surface."""

    def __init__(self, workspace: Path) -> None:
        self.root = workspace.resolve(strict=True)
        self.agent = (self.root / "agent").resolve(strict=True)
        self.public = (self.root / "public").resolve(strict=True)
        self.reference = (self.root / "reference").resolve(strict=True)
        self.ipc = (self.root / ".ipc").resolve(strict=True)
        self._terminal_outcome: dict[str, Any] | None = None
        for path in (self.agent, self.public, self.reference, self.ipc):
            path.relative_to(self.root)

    def run(self) -> int:
        for raw_line in sys.stdin.buffer:
            if not raw_line.strip():
                continue
            try:
                request = json.loads(raw_line)
                if not isinstance(request, dict):
                    raise ValueError("JSON-RPC request must be an object")
                response = self._dispatch(request)
            except Exception as error:
                response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32603,
                        "message": type(error).__name__,
                    },
                }
            if response is not None:
                sys.stdout.buffer.write(_encode(response) + b"\n")
                sys.stdout.buffer.flush()
        return 0

    def _dispatch(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        if method == "notifications/initialized" or str(method).startswith("notifications/"):
            return None
        if method == "initialize":
            params = request.get("params")
            protocol = (
                params.get("protocolVersion")
                if isinstance(params, dict)
                else "2025-06-18"
            )
            return self._result(
                request_id,
                {
                    "protocolVersion": protocol,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": MCP_SERVER_VERSION},
                    "instructions": (
                        "Use chemworld_lab.step for every physical operation. First call "
                        "material_information once. Use status, history, and inspect_artifact "
                        "only for bounded public evidence. Never fabricate an outcome. After "
                        "a step returns experiment_ended=true, call no more tools and submit "
                        "the final response for that experiment."
                    ),
                },
            )
        if method == "ping":
            return self._result(request_id, {})
        if method == "logging/setLevel":
            return self._result(request_id, {})
        if method == "tools/list":
            return self._result(request_id, {"tools": self._tool_definitions()})
        if method == "tools/call":
            params = request.get("params")
            if not isinstance(params, dict):
                return self._error(request_id, -32602, "invalid tools/call params")
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return self._error(request_id, -32602, "invalid tools/call params")
            return self._result(request_id, self._call_tool(name, arguments))
        return self._error(request_id, -32601, "method not found")

    @staticmethod
    def _result(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }

    def _descriptor(self) -> dict[str, Any]:
        descriptor = _read_object(self.ipc / "active_session.json")
        if descriptor.get("schema_version") != IPC_VERSION:
            raise ValueError("unsupported active experiment session")
        return descriptor

    def _audit(self, descriptor: dict[str, Any], tool: str, arguments: Any) -> None:
        session_id = self._leaf(str(descriptor["session_id"]), label="session_id")
        digest = hashlib.sha256(_encode(arguments)).hexdigest()
        _append_jsonl(
            self.ipc / "sessions" / session_id / "mcp_tool_calls.jsonl",
            {
                "schema_version": MCP_SERVER_VERSION,
                "tool": tool,
                "arguments_sha256": digest,
                "argument_keys": sorted(arguments) if isinstance(arguments, dict) else [],
            },
        )

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in SUPPORTED_TOOLS:
            return self._tool_error("unsupported_tool")
        descriptor = self._descriptor()
        self._audit(descriptor, name, arguments)
        try:
            if name == "material_information":
                payload = _read_object(self.reference / "material_information.json")
            elif name == "status":
                payload = self._status()
            elif name == "history":
                payload = self._history(arguments)
            elif name == "inspect_artifact":
                payload = self._inspect(descriptor, arguments)
            else:
                payload = self._step(descriptor, arguments)
            cap = int(descriptor["max_tool_output_bytes"])
            encoded = _encode(payload)
            if len(encoded) > cap:
                raise ValueError("tool output exceeds configured byte cap")
            return {
                "content": [{"type": "text", "text": encoded.decode("utf-8")}],
                "isError": False,
            }
        except Exception as error:
            return self._tool_error(type(error).__name__)

    @staticmethod
    def _tool_error(error_type: str) -> dict[str, Any]:
        text = _encode({"ok": False, "error": error_type}).decode("utf-8")
        return {"content": [{"type": "text", "text": text}], "isError": True}

    def _history(self, arguments: dict[str, Any]) -> dict[str, Any]:
        raw_limit = arguments.get("limit", 5)
        if isinstance(raw_limit, bool) or not isinstance(raw_limit, int):
            raise ValueError("limit must be an integer")
        limit = max(1, min(raw_limit, 10))
        rows: list[dict[str, Any]] = []
        path = self.public / "history.jsonl"
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        rows.append(value)
        return {
            "schema_version": MCP_SERVER_VERSION,
            "authoritative": False,
            "events": rows[-limit:],
        }

    def _status(self) -> dict[str, Any]:
        if self._terminal_outcome is None:
            return _read_object(self.public / "current.json")
        return {
            "schema_version": MCP_SERVER_VERSION,
            "experiment_ended": True,
            "terminal_outcome": self._terminal_outcome,
            "instruction": "Submit the final response now; do not call step again.",
        }

    def _inspect(
        self,
        descriptor: dict[str, Any],
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        artifact_id = self._leaf(str(arguments.get("artifact_id", "")), label="artifact_id")
        offset = max(self._integer(arguments.get("offset", 0), label="offset"), 0)
        cap = int(descriptor["max_tool_output_bytes"])
        requested = self._integer(arguments.get("limit", 4096), label="limit")
        limit = max(1, min(requested, max(256, cap // 2)))
        path = self.public / "artifacts" / f"{artifact_id}.json"
        text = path.read_text(encoding="utf-8")
        fragment = text[offset : offset + limit]
        session_id = self._leaf(str(descriptor["session_id"]), label="session_id")
        _append_jsonl(
            self.ipc / "sessions" / session_id / "artifact_access.jsonl",
            {
                "artifact_id": artifact_id,
                "offset": offset,
                "limit": limit,
                "returned_character_count": len(fragment),
                "total_character_count": len(text),
            },
        )
        return {
            "schema_version": MCP_SERVER_VERSION,
            "artifact_id": artifact_id,
            "offset": offset,
            "next_offset": offset + len(fragment),
            "total_character_count": len(text),
            "complete": offset + len(fragment) >= len(text),
            "encoding": "utf-8-json-text-fragment",
            "data": fragment,
        }

    def _step(
        self,
        descriptor: dict[str, Any],
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        if self._terminal_outcome is not None:
            raise RuntimeError(
                "experiment_already_ended_submit_final_response"
            )
        expected_step = self._integer(arguments.get("expected_step"), label="expected_step")
        if expected_step < 1:
            raise ValueError("expected_step must be positive")
        action = arguments.get("action")
        if not isinstance(action, dict) or not isinstance(action.get("operation"), str):
            raise ValueError("action.operation is required")
        session_id = self._leaf(str(descriptor["session_id"]), label="session_id")
        request_id_value = arguments.get("request_id")
        if request_id_value is None:
            request_id = hashlib.sha256(
                session_id.encode("utf-8")
                + b"|"
                + str(expected_step).encode("ascii")
                + b"|"
                + _encode(action)
            ).hexdigest()[:32]
        else:
            request_id = self._leaf(str(request_id_value), label="request_id")
        envelope = {
            "schema_version": IPC_VERSION,
            "session_id": session_id,
            "request_id": request_id,
            "expected_step": expected_step,
            "action": action,
        }
        session_root = self.ipc / "sessions" / session_id
        request_path = session_root / "mcp_requests" / f"{request_id}.json"
        response_path = session_root / "responses" / f"{request_id}.json"
        if request_path.exists():
            if _encode(_read_object(request_path)) != _encode(envelope):
                raise ValueError("request_id was reused with another payload")
        else:
            _atomic_json(request_path, envelope)
        deadline = time.monotonic() + float(descriptor["response_timeout_s"])
        while time.monotonic() < deadline:
            if response_path.exists():
                outcome = _read_object(response_path)
                if outcome.get("experiment_ended") is True:
                    self._terminal_outcome = outcome
                return outcome
            current = self._descriptor()
            if current.get("session_id") != session_id:
                raise RuntimeError("session changed before the operation completed")
            time.sleep(0.05)
        raise TimeoutError("runner did not return an operation outcome")

    @staticmethod
    def _leaf(value: str, *, label: str) -> str:
        if not value or value in {".", ".."} or "/" in value or "\\" in value:
            raise ValueError(f"{label} must be a non-path string")
        return value

    @staticmethod
    def _integer(value: Any, *, label: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{label} must be an integer")
        return value

    @staticmethod
    def _tool_definitions() -> list[dict[str, Any]]:
        read_annotations = {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
        return [
            {
                "name": "material_information",
                "description": "Read the bounded material information assigned to this cell once.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                "annotations": read_annotations,
            },
            {
                "name": "status",
                "description": "Read the latest bounded public experiment and campaign state.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
                "annotations": read_annotations,
            },
            {
                "name": "history",
                "description": "Read a bounded non-authoritative cache of recent public outcomes.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 10}},
                    "additionalProperties": False,
                },
                "annotations": read_annotations,
            },
            {
                "name": "inspect_artifact",
                "description": (
                    "Read one bounded fragment of a referenced public "
                    "characterization artifact."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "artifact_id": {"type": "string", "minLength": 1},
                        "offset": {"type": "integer", "minimum": 0},
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "required": ["artifact_id"],
                    "additionalProperties": False,
                },
                "annotations": read_annotations,
            },
            {
                "name": "step",
                "description": (
                    "Submit exactly one operation to the authoritative ChemWorld "
                    "runner and wait for its public outcome. This tool is permanently "
                    "closed after an outcome reports experiment_ended=true."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "expected_step": {"type": "integer", "minimum": 1},
                        "action": {
                            "type": "object",
                            "properties": {"operation": {"type": "string", "minLength": 1}},
                            "required": ["operation"],
                            "additionalProperties": True,
                        },
                        "request_id": {"type": "string", "minLength": 1},
                    },
                    "required": ["expected_step", "action"],
                    "additionalProperties": False,
                },
                "annotations": {
                    "readOnlyHint": False,
                    "destructiveHint": False,
                    "idempotentHint": False,
                    "openWorldHint": False,
                },
            },
        ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args(argv)
    return ChemWorldMCPServer(args.workspace).run()


if __name__ == "__main__":
    raise SystemExit(main())
