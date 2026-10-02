"""HTTP entrypoint for the shared `sys1_mcp.server.app` FastMCP instance.

Runs the same tool surface `sys1_mcp.__init__.main()` serves over stdio, but
over `streamable-http`, with a `/health` route that reports 503 until the
backend has loaded and 200 after, and names the models it serves either way.
Loading happens eagerly here (before the listener accepts traffic) so a
readiness probe never races the first inference call.

Two non-MCP routes share the warm backend:

- `POST /predict` takes `{"tool", "arguments"}`. A stdio `sys1-mcp` process
  pointed here by `SYS1_DAEMON_URL` posts every tool call to it, so that process
  reuses this backend instead of loading its own.
- `POST /v1/systemone` takes `{"state", "questions", "model"?}`, the System One
  wire contract, so any System One client — a Playwright test, another
  `sys1-mcp` on the `systemone` backend — can use whatever model this daemon serves.

Serves HTTPS when `SYS1_MCP_TLS_CERT` and `SYS1_MCP_TLS_KEY` both name readable
files, and plain HTTP otherwise. See README.md.
"""

from __future__ import annotations

import os
import time
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

from .server import BACKEND, TOOL_SURFACE, _log_call, app, run_tool_locally

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

_ready = False


@app.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    if not _ready:
        # `describe()` may need a loaded model; the configured names are all that
        # is knowable this early, and they are what an operator checks a swap against.
        return JSONResponse(
            {"status": "loading", "backend": BACKEND.name, **BACKEND.configured()},
            status_code=503,
        )
    return JSONResponse(
        {
            "status": "ok",
            "backend": BACKEND.name,
            "default_model": BACKEND.default_model(),
            "roles": BACKEND.roles(),
            "models": {name: BACKEND.describe(name) for name in BACKEND.loaded_models()},
            # The tool surface, so a client holding a stale cached tool list is
            # diagnosable with one request. A caller that cannot pass `model`
            # while this lists it is looking at a cached schema, not a server that
            # ignored the argument.
            "tools": {
                name: {"arguments": spec["arguments"], "response_keys": spec["response_keys"]}
                for name, spec in TOOL_SURFACE.items()
            },
        }
    )


async def _json_body(request: Request) -> tuple[Any, JSONResponse | None]:
    if not _ready:
        return None, JSONResponse({"error": "backend still loading"}, status_code=503)
    try:
        return await request.json(), None
    except ValueError as exc:
        return None, JSONResponse({"error": f"body is not JSON: {exc}"}, status_code=400)


def _run_logged(tool: str, arguments: dict[str, Any]) -> JSONResponse:
    """Run one tool and log it like an MCP call. A model failure is not caught
    here: it must surface as a 500, never as an answer (`sys1_screen` fails
    closed on it)."""
    started = time.perf_counter()
    try:
        result = run_tool_locally(tool, arguments)
    except (TypeError, ValueError) as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    _log_call(tool, arguments, result, (time.perf_counter() - started) * 1000)
    return JSONResponse(result)


@app.custom_route("/predict", methods=["POST"])
async def predict(request: Request) -> JSONResponse:
    """Run any tool on this daemon's backend, outside the MCP protocol.

    This is the shape `sys1_mcp.server._dispatch` posts when `SYS1_DAEMON_URL` is
    set. Clients that cannot use an MCP URL at all — Claude Desktop, which only
    spawns local stdio servers — reach the warm backend this way.
    """
    payload, error = await _json_body(request)
    if error is not None:
        return error
    if not isinstance(payload, dict) or "tool" not in payload:
        return JSONResponse({"error": 'expected {"tool": ..., "arguments": {...}}'}, status_code=400)
    return _run_logged(str(payload["tool"]), dict(payload.get("arguments") or {}))


@app.custom_route("/v1/systemone", methods=["POST"])
async def systemone(request: Request) -> JSONResponse:
    """Answer one System One request with `sys1_ask` on this daemon's backend.

    The response is the System One shape — `model`, `answers`, `usage` — plus
    this server's provenance and `truncation`, which the `systemone` backend
    passes through when it is pointed here.
    """
    payload, error = await _json_body(request)
    if error is not None:
        return error
    if not isinstance(payload, dict) or "state" not in payload or not isinstance(payload.get("questions"), dict):
        return JSONResponse({"error": 'expected {"state": ..., "questions": {...}}'}, status_code=400)
    return _run_logged(
        "sys1_ask",
        {"state": payload["state"], "questions": payload["questions"], "model": payload.get("model")},
    )


def _tls_config() -> dict[str, str]:
    """Read the cert/key pair, or return {} to serve plain HTTP.

    Both variables must be set together and both files must exist: a half-set
    pair is a misconfiguration, and silently falling back to HTTP would hand a
    client an unencrypted listener it did not ask for.
    """
    cert = os.environ.get("SYS1_MCP_TLS_CERT")
    key = os.environ.get("SYS1_MCP_TLS_KEY")
    if not cert and not key:
        return {}
    if not cert or not key:
        raise SystemExit(
            "SYS1_MCP_TLS_CERT and SYS1_MCP_TLS_KEY must be set together; "
            f"got cert={cert!r} key={key!r}"
        )
    for label, path in (("SYS1_MCP_TLS_CERT", cert), ("SYS1_MCP_TLS_KEY", key)):
        if not os.path.isfile(path):
            raise SystemExit(f"{label}={path} is not a readable file")
    return {"ssl_certfile": cert, "ssl_keyfile": key}


def main() -> None:
    global _ready
    # Order matters: every env read must precede BACKEND.load(), or a typo
    # fails only after a full model load. The backend validated its own
    # configuration when `sys1_mcp.server` was imported.
    tls = _tls_config()
    host = os.environ.get("SYS1_MCP_HOST", DEFAULT_HOST)
    raw_port = os.environ.get("SYS1_MCP_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw_port)
    except ValueError:
        raise SystemExit(f"SYS1_MCP_PORT={raw_port!r} is not an integer") from None
    # On laya-mlx this builds every preloaded model, not just the default, so no
    # request pays a model load and the LRU never evicts one to serve another.
    BACKEND.load()
    _ready = True
    app.run(
        transport="streamable-http",
        host=host,
        port=port,
        uvicorn_config=tls or None,
    )


__all__ = ["app", "main"]
