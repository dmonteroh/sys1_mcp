"""HTTP entrypoint for the shared `laya_mcp.server.app` FastMCP instance.

Runs the same tool surface `laya_mcp.__init__.main()` serves over stdio, but
over `streamable-http` on loopback, with a `/health` route that reports 503
until the local agent has loaded and 200 after. Loading happens eagerly here
(before the listener accepts traffic) so a readiness probe never races the
first inference call.
"""

from __future__ import annotations

import os

from starlette.requests import Request
from starlette.responses import JSONResponse

from .server import _local_agent, app

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

_ready = False


@app.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    if not _ready:
        return JSONResponse({"status": "loading"}, status_code=503)
    return JSONResponse({"status": "ok"})


def main() -> None:
    global _ready
    _local_agent()
    _ready = True
    host = os.environ.get("LAYA_MCP_HOST", DEFAULT_HOST)
    port = int(os.environ.get("LAYA_MCP_PORT", str(DEFAULT_PORT)))
    app.run(transport="streamable-http", host=host, port=port)


__all__ = ["app", "main"]
