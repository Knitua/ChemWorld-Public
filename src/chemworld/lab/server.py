"""Local HTTP server for the provider-free ChemWorld Lab."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import signal
import threading
import webbrowser
from collections import deque
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from time import monotonic
from typing import Any
from urllib.parse import urlparse

from chemworld.lab.agent_run import AgentRunManager, agent_catalog
from chemworld.lab.limits import LabCapacityError
from chemworld.lab.session import LabSessionManager, task_catalog

MAX_REQUEST_BYTES = 64 * 1024


@dataclass(frozen=True)
class LabLimits:
    """Fail-closed in-memory limits for an explicitly public Lab process."""

    max_sessions: int = 64
    max_agent_runs: int = 64
    max_concurrent_agent_runs: int = 4
    session_ttl_s: float = 30 * 60
    run_ttl_s: float = 30 * 60
    post_rate_per_minute: int = 90

    def __post_init__(self) -> None:
        for name, value in (
            ("max_sessions", self.max_sessions),
            ("max_agent_runs", self.max_agent_runs),
            ("max_concurrent_agent_runs", self.max_concurrent_agent_runs),
            ("post_rate_per_minute", self.post_rate_per_minute),
        ):
            if value < 1:
                raise ValueError(f"{name} must be positive")
        if self.session_ttl_s <= 0 or self.run_ttl_s <= 0:
            raise ValueError("Lab TTL values must be positive")


class PostRateLimiter:
    """Small per-client sliding-window limiter for state-changing requests."""

    def __init__(self, requests_per_minute: int) -> None:
        self._limit = requests_per_minute
        self._requests: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, client: str) -> bool:
        now = monotonic()
        cutoff = now - 60.0
        with self._lock:
            entries = self._requests.setdefault(client, deque())
            while entries and entries[0] <= cutoff:
                entries.popleft()
            if len(entries) >= self._limit:
                return False
            entries.append(now)
            return True


class LabServer(ThreadingHTTPServer):
    """Loopback-first server that owns in-memory Gym sessions."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        public: bool = False,
        limits: LabLimits | None = None,
    ) -> None:
        super().__init__(address, LabHandler)
        self.public_mode = public
        self.limits = limits or LabLimits()
        if public:
            self.sessions = LabSessionManager(
                max_sessions=self.limits.max_sessions,
                session_ttl_s=self.limits.session_ttl_s,
            )
            self.agent_runs = AgentRunManager(
                max_runs=self.limits.max_agent_runs,
                max_concurrent_runs=self.limits.max_concurrent_agent_runs,
                run_ttl_s=self.limits.run_ttl_s,
            )
        else:
            self.sessions = LabSessionManager()
            self.agent_runs = AgentRunManager()
        self.post_limiter = PostRateLimiter(self.limits.post_rate_per_minute)

    def server_close(self) -> None:
        self.sessions.close_all()
        self.agent_runs.close_all()
        super().server_close()


class LabHandler(BaseHTTPRequestHandler):
    server: LabServer
    server_version = "ChemWorldLab/0.4"
    sys_version = ""

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self._json(
                {
                    "status": "ok",
                    "provider_required": False,
                    "public_mode": self.server.public_mode,
                    "release": "0.4.0",
                }
            )
            return
        if path == "/api/tasks":
            self._json({"tasks": task_catalog(), "default_task": "reaction-to-assay"})
            return
        if path == "/api/agents":
            self._json(
                {
                    "agents": agent_catalog(),
                    "default_agent": "scripted_chemistry",
                    "online_providers_enabled": False,
                }
            )
            return
        if path.startswith("/api/agent-runs/"):
            try:
                self._json(self.server.agent_runs.get(path.split("/")[3]).state())
            except KeyError as exc:
                self._error(HTTPStatus.NOT_FOUND, str(exc))
            return
        if path.startswith("/api/agent-comparisons/"):
            try:
                self._json(self.server.agent_runs.comparison_state(path.split("/")[3]))
            except KeyError as exc:
                self._error(HTTPStatus.NOT_FOUND, str(exc))
            return
        if path.startswith("/api/sessions/"):
            try:
                self._json(self.server.sessions.get(path.split("/")[3]).state())
            except KeyError as exc:
                self._error(HTTPStatus.NOT_FOUND, str(exc))
            return
        self._static(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if self.server.public_mode and not self.server.post_limiter.allow(self.client_address[0]):
            self._error(HTTPStatus.TOO_MANY_REQUESTS, "request rate limit exceeded")
            return
        try:
            body = self._request_json()
            if path == "/api/sessions":
                task_id = str(body.get("task_id") or "reaction-to-assay")
                seed = int(body["seed"]) if body.get("seed") is not None else None
                session = self.server.sessions.create(task_id, seed)
                self._json(session.state(), status=HTTPStatus.CREATED)
                return
            if path == "/api/agent-runs":
                run = self.server.agent_runs.create(
                    str(body.get("task_id") or "reaction-to-assay"),
                    str(body.get("agent_id") or "scripted_chemistry"),
                    int(body.get("seed", 0)),
                )
                self._json(run.state(), status=HTTPStatus.CREATED)
                return
            if path.startswith("/api/agent-runs/") and path.endswith("/commands"):
                command = str(body.get("command") or "")
                run = self.server.agent_runs.command(path.split("/")[3], command)
                self._json(run.state())
                return
            if path == "/api/agent-comparisons":
                raw_agents = body.get("agent_ids")
                if not isinstance(raw_agents, list):
                    raise ValueError("agent_ids must be a list")
                comparison = self.server.agent_runs.compare(
                    str(body.get("task_id") or "reaction-to-assay"),
                    [str(item) for item in raw_agents],
                    int(body.get("seed", 0)),
                )
                self._json(
                    self.server.agent_runs.comparison_state(comparison.comparison_id),
                    status=HTTPStatus.CREATED,
                )
                return
            if path.startswith("/api/sessions/") and path.endswith("/actions"):
                action = body.get("action")
                if not isinstance(action, dict):
                    raise ValueError("request must contain an action object")
                session_id = path.split("/")[3]
                self._json(self.server.sessions.get(session_id).step(action))
                return
            self._error(HTTPStatus.NOT_FOUND, "unknown endpoint")
        except KeyError as exc:
            self._error(HTTPStatus.NOT_FOUND, str(exc))
        except LabCapacityError as exc:
            self._error(HTTPStatus.TOO_MANY_REQUESTS, str(exc))
        except (TypeError, ValueError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:  # pragma: no cover - fail closed at the HTTP boundary
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def _request_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0 or length > MAX_REQUEST_BYTES:
            raise ValueError("request body is too large")
        if length == 0:
            return {}
        content_type = self.headers.get("Content-Type", "").partition(";")[0].strip().lower()
        if content_type != "application/json":
            raise ValueError("Content-Type must be application/json")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _static(self, path: str) -> None:
        route = {
            "": "index.html",
            "/": "index.html",
            "/student": "index.html",
            "/student/": "index.html",
            "/agent": "agent.html",
            "/agent/": "agent.html",
        }.get(path, path.lstrip("/"))
        if not route or "/" in route or route.startswith("."):
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        target = files("chemworld.lab").joinpath("static", route)
        if not target.is_file():
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
        }.get("." + route.rsplit(".", 1)[-1], "application/octet-stream")
        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:",
        )
        self.end_headers()
        self.wfile.write(content)

    def _json(self, payload: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(content)

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._json({"error": message}, status=status)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        if self.server.public_mode:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    def log_message(self, format: str, *args: Any) -> None:
        del format, args


def serve(
    host: str = "127.0.0.1",
    port: int = 8876,
    *,
    open_browser: bool = True,
    public: bool = False,
    limits: LabLimits | None = None,
) -> None:
    """Serve until interrupted; public binding requires an explicit bounded mode."""

    loopback = host == "localhost"
    if not loopback:
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError as exc:
            if not public:
                raise ValueError(
                    "ChemWorld Lab host must be localhost or a loopback address"
                ) from exc
    if not loopback and not public:
        raise ValueError("ChemWorld Lab only binds to loopback addresses")
    server = LabServer((host, port), public=public, limits=limits)
    actual_port = int(server.server_address[1])
    url = f"http://{host}:{actual_port}/"
    print(f"ChemWorld Lab: {url}")
    print("Provider-free mode: no API key, model, or external service is used.")
    if public:
        print("Public mode: bounded in-memory sessions and provider-free policies only.")
    previous_sigterm: Any = None
    if threading.current_thread() is threading.main_thread():
        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def request_shutdown(signum: int, frame: Any) -> None:
            del signum, frame
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, request_shutdown)
    if open_browser:
        threading.Timer(0.2, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        if previous_sigterm is not None:
            signal.signal(signal.SIGTERM, previous_sigterm)
        server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8876")))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--public",
        action="store_true",
        help="Explicitly allow non-loopback binding with bounded, provider-free resources.",
    )
    parser.add_argument("--max-sessions", type=int, default=64)
    parser.add_argument("--max-agent-runs", type=int, default=64)
    parser.add_argument("--max-concurrent-agent-runs", type=int, default=4)
    parser.add_argument("--session-ttl-seconds", type=float, default=1800.0)
    parser.add_argument("--run-ttl-seconds", type=float, default=1800.0)
    parser.add_argument("--post-rate-per-minute", type=int, default=90)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    limits = LabLimits(
        max_sessions=args.max_sessions,
        max_agent_runs=args.max_agent_runs,
        max_concurrent_agent_runs=args.max_concurrent_agent_runs,
        session_ttl_s=args.session_ttl_seconds,
        run_ttl_s=args.run_ttl_seconds,
        post_rate_per_minute=args.post_rate_per_minute,
    )
    serve(
        args.host,
        args.port,
        open_browser=not args.no_browser,
        public=args.public,
        limits=limits,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
