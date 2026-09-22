"""Shared MCP app for laya-mcp.

Defines one `FastMCP` instance and the `laya_decide` tool. This module holds no
transport choice of its own: `laya_mcp.__main__` runs it over stdio, and a later
task may run the same `app` over `streamable-http` without changing anything
in this file.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import httpx
from fastmcp import FastMCP

logger = logging.getLogger("laya_mcp")

DEFAULT_CHECKPOINT = "aac6fef/laya-mlx"
DAEMON_TIMEOUT_SECONDS = 10.0

app = FastMCP("laya")

# Single-flight: agent.predict()'s thread-safety is undocumented, and the same
# lock also serializes the lazy load so two concurrent calls can't race to
# construct two agent instances.
_inference_lock = threading.Lock()
_agent: Any = None


def _checkpoint_id() -> str:
    return os.environ.get("LAYA_CHECKPOINT", DEFAULT_CHECKPOINT)


def _local_agent() -> Any:
    global _agent
    if _agent is None:
        import laya_mlx

        _agent = laya_mlx.load(_checkpoint_id())
    return _agent


def _predict_via_daemon(daemon_url: str, state: str, questions: dict[str, Any]) -> dict[str, Any]:
    response = httpx.post(
        f"{daemon_url.rstrip('/')}/predict",
        json={"text": state, "schema": questions},
        timeout=DAEMON_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _predict(state: str, questions: dict[str, Any]) -> dict[str, Any]:
    daemon_url = os.environ.get("LAYA_DAEMON_URL")
    if daemon_url:
        try:
            return _predict_via_daemon(daemon_url, state, questions)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "LAYA_DAEMON_URL=%s unreachable (%s); falling back to a local agent load",
                daemon_url,
                exc,
            )

    with _inference_lock:
        agent = _local_agent()
        return agent.predict(state, questions)


@app.tool
def laya_decide(state: str, questions: dict[str, Any]) -> dict[str, Any]:
    """Answer one or more typed questions about `state` using the Laya decision model.

    `questions` mirrors `laya-mlx`'s own `agent.predict` schema: a mapping of
    field name to a question spec with a `type` of `choice`, `score`, or
    `noul`, plus that type's own keys (`instructions`, and `criteria` for
    `choice`).
    """
    return _predict(state, questions)
