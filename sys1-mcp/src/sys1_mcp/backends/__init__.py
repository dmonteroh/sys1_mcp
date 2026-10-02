"""System One backends: whatever answers a typed question.

Every tool in `sys1_mcp.server` speaks one contract: a `state`, a dict of typed
questions (`noul`, `choice`, `score`), and one answer per question carrying
probabilities. That is the `POST /v1/systemone` shape of TypeSafe's Jev API
(jev-agent.com/api-reference, read 2026-10-02), which Laya's `system_one`
(`laya_mlx/agent.py`), Cloudflare's Clef, and several open servers also speak.
A backend is one way of getting those answers. The tools never name a model
family, only a backend's model names and the two roles below.

Selected by `SYS1_BACKEND`: `laya-mlx` (default) runs Laya in this process;
`systemone` posts to any `/v1/systemone`-shaped HTTP endpoint.
"""

from __future__ import annotations

import os
from typing import Any

# What a tool with a fixed purpose asks for, instead of naming a model.
# `content`: a judgment about what a text says (screening, sensitive data).
# `trace`: a judgment about an agent's own task state (relevance, workflows).
ROLES = ("content", "trace")

ROLE_VARS = {"content": "SYS1_MODEL_CONTENT", "trace": "SYS1_MODEL_TRACE"}
DEFAULT_VAR = "SYS1_MODEL_DEFAULT"


class Backend:
    """The interface every backend implements.

    `predict` returns `answers`, `usage`, `checkpoint` (the weights or upstream
    model that answered, when known), optional `limits`, and `truncation`.
    `predict_many` answers one schema for many states and returns per-state
    `answers` and `truncated` (question ids cut, or `None` when the backend
    cannot tell), plus `usage`, `checkpoint`, optional `limits`, and `prefix`.
    """

    name = "abstract"

    def models(self) -> list[str]:
        raise NotImplementedError

    def loaded_models(self) -> list[str]:
        return self.models()

    def resolve(self, model: str | None) -> str:
        """Map a caller's `model` argument to a served model name, or raise ValueError."""
        raise NotImplementedError

    def builtin_default(self) -> str:
        return self.models()[0]

    def builtin_role(self, role: str) -> str:
        return self.default_model()

    def default_model(self) -> str:
        return self._env_model(DEFAULT_VAR, self.builtin_default)

    def role_model(self, role: str) -> str:
        if role not in ROLES:
            raise ValueError(f"unknown role {role!r}; choose one of {ROLES}")
        return self._env_model(ROLE_VARS[role], lambda: self.builtin_role(role))

    def _env_model(self, var: str, fallback: Any) -> str:
        value = os.environ.get(var)
        # `default` would resolve back to this lookup on a backend that aliases it.
        if not value or value.strip().lower() == "default" and "default" not in self.models():
            return fallback()
        try:
            return self.resolve(value)
        except ValueError as exc:
            raise SystemExit(f"{var}={value!r}: {exc}") from None

    def roles(self) -> dict[str, str]:
        return {role: self.role_model(role) for role in ROLES}

    def model_help(self) -> str:
        """One sentence for tool descriptions: what to pass as `model`."""
        return (
            f"Served models: {', '.join(self.models())}. Omit for the default "
            f"({self.default_model()})."
        )

    def configured(self) -> dict[str, Any]:
        """What is knowable before `load()`, for a readiness probe."""
        return {"models": self.models(), "default_model": self.default_model()}

    def load(self) -> None:
        """Build whatever must be resident before the first call. Optional."""

    def describe(self, model: str) -> dict[str, Any]:
        raise NotImplementedError

    def predict(self, state: Any, questions: dict[str, Any], model: str) -> dict[str, Any]:
        raise NotImplementedError

    def predict_many(
        self, states: list[Any], questions: dict[str, Any], model: str
    ) -> dict[str, Any]:
        raise NotImplementedError

    def screen_spans(
        self, text: str, questions: dict[str, Any], model: str,
        overlap_tokens: int, max_chunks: int,
    ) -> list[tuple[int, int]]:
        """Character spans covering `text`, each short enough to be read whole."""
        raise NotImplementedError

    def health(self, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        """`runtime` and per-model `models`, each with one timed probe of `questions`."""
        raise NotImplementedError


def from_env() -> Backend:
    kind = os.environ.get("SYS1_BACKEND", "laya-mlx")
    if kind == "laya-mlx":
        from .laya_mlx import LayaMlxBackend

        return LayaMlxBackend()
    if kind == "systemone":
        from .systemone import SystemOneBackend

        return SystemOneBackend()
    raise SystemExit(f"SYS1_BACKEND={kind!r} is not a backend; choose 'laya-mlx' or 'systemone'")


__all__ = ["Backend", "ROLES", "from_env"]
