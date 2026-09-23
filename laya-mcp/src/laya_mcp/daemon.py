"""HTTP entrypoint for the shared `laya_mcp.server.app` FastMCP instance.

Runs the same tool surface `laya_mcp.__init__.main()` serves over stdio, but
over `streamable-http`, with a `/health` route that reports 503 until the local
agents have loaded and 200 after, and names the checkpoints it serves either way.
Loading happens eagerly here (before the listener accepts traffic) so a
readiness probe never races the first inference call.

Also serves `/predict`, the non-MCP shape a stdio `laya-mcp` process posts to
when `LAYA_DAEMON_URL` points here, so that process reuses these warm models
instead of loading its own. It takes an optional `checkpoint` naming a route.

Serves HTTPS when `LAYA_MCP_TLS_CERT` and `LAYA_MCP_TLS_KEY` both name readable
files, and plain HTTP otherwise. See README.md.
"""

from __future__ import annotations

import os

from starlette.requests import Request
from starlette.responses import JSONResponse

from .server import (
    TOOL_SURFACE,
    _default_route,
    _local_agent,
    _local_router,
    _routes,
    app,
    describe,
    predict_locally,
    run_tool_locally,
)

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

_ready = False


@app.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    if not _ready:
        # `describe()` needs a loaded agent; the configured ids are all that is
        # knowable this early, and they are what an operator checks a swap against.
        return JSONResponse(
            {"status": "loading", "routes": _routes(), "default_route": _default_route()},
            status_code=503,
        )
    default = _default_route()
    resident = {name: describe(_local_agent(name), name) for name in _local_router().loaded}
    return JSONResponse(
        {
            "status": "ok",
            "default_route": default,
            "routes": resident,
            # The tool surface, so a client holding a stale cached tool list is
            # diagnosable with one request. A caller that cannot pass `checkpoint`
            # while this lists it is looking at a cached schema, not a server that
            # ignored the argument.
            "tools": {
                name: {"arguments": spec["arguments"], "response_keys": spec["response_keys"]}
                for name, spec in TOOL_SURFACE.items()
            },
            # The default route's own figures, flat, so probes written against the
            # single-checkpoint shape keep working.
            **describe(_local_agent(default), default),
        }
    )


@app.custom_route("/predict", methods=["POST"])
async def predict(request: Request) -> JSONResponse:
    """Run one inference on the already-loaded agent, outside the MCP protocol.

    This is the `/predict` shape `laya_mcp.server._predict` posts to when
    `LAYA_DAEMON_URL` is set, so a stdio `laya-mcp` process can borrow this
    daemon's warm model instead of loading a second copy. Clients that cannot
    use an MCP URL at all — Claude Desktop, which only spawns local stdio
    servers — reach the warm model this way.
    """
    if not _ready:
        return JSONResponse({"error": "agent still loading"}, status_code=503)
    try:
        payload = await request.json()
    except ValueError as exc:
        return JSONResponse({"error": f"body is not JSON: {exc}"}, status_code=400)
    if isinstance(payload, dict) and "tool" in payload:
        # Every tool besides `laya_ask` travels this way, so a stdio process
        # reaches all of them on the warm models without a route per tool. A
        # model failure is not caught here: it must surface as a 500, never as an
        # answer (`laya_screen` fails closed on it).
        try:
            return JSONResponse(
                run_tool_locally(str(payload["tool"]), dict(payload.get("arguments") or {}))
            )
        except (TypeError, ValueError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
    try:
        state = payload["text"]
        questions = payload["schema"]
        checkpoint = payload.get("checkpoint")
    except (KeyError, TypeError, ValueError) as exc:
        return JSONResponse({"error": f"expected {{text, schema}}: {exc}"}, status_code=400)
    try:
        return JSONResponse(predict_locally(state, questions, checkpoint))
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


def _tls_config() -> dict[str, str]:
    """Read the cert/key pair, or return {} to serve plain HTTP.

    Both variables must be set together and both files must exist: a half-set
    pair is a misconfiguration, and silently falling back to HTTP would hand a
    client an unencrypted listener it did not ask for.
    """
    cert = os.environ.get("LAYA_MCP_TLS_CERT")
    key = os.environ.get("LAYA_MCP_TLS_KEY")
    if not cert and not key:
        return {}
    if not cert or not key:
        raise SystemExit(
            "LAYA_MCP_TLS_CERT and LAYA_MCP_TLS_KEY must be set together; "
            f"got cert={cert!r} key={key!r}"
        )
    for label, path in (("LAYA_MCP_TLS_CERT", cert), ("LAYA_MCP_TLS_KEY", key)):
        if not os.path.isfile(path):
            raise SystemExit(f"{label}={path} is not a readable file")
    return {"ssl_certfile": cert, "ssl_keyfile": key}


def main() -> None:
    global _ready
    # Order matters: every env read must precede _local_agent(), or a typo
    # fails only after a full model load.
    tls = _tls_config()
    host = os.environ.get("LAYA_MCP_HOST", DEFAULT_HOST)
    raw_port = os.environ.get("LAYA_MCP_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw_port)
    except ValueError:
        raise SystemExit(f"LAYA_MCP_PORT={raw_port!r} is not an integer") from None
    # Builds every preloaded route, not just the default, so no request pays a
    # model load and the LRU never evicts one route to serve another.
    _local_router()
    _ready = True
    app.run(
        transport="streamable-http",
        host=host,
        port=port,
        uvicorn_config=tls or None,
    )


__all__ = ["app", "main"]
