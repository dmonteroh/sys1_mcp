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
from typing import Annotated, Any

import httpx
from fastmcp import FastMCP
from pydantic import Field

logger = logging.getLogger("laya_mcp")

DAEMON_TIMEOUT_SECONDS = 10.0

# Two checkpoints, held resident together, because measurement says neither wins
# outright. `laya_mlx.Router`'s own slot names are reused rather than invented, so
# `Router(models=...)` takes this mapping directly; the values are the MLX ports of
# the checkpoints its DEFAULT_MODELS names in PyTorch form.
ROUTES: dict[str, str] = {
    "english": "aac6fef/laya-mlx",
    "typed-decisions": "aac6fef/laya-typed-decisions-mlx",
}

# Which checkpoint answers a call that names none.
#
# `typed-decisions`, on an asymmetry in what forgetting the argument costs. Omitting
# it on a screening call costs some confidence on a question `english` answers better.
# Omitting it on an agent-trace call costs half the input: a transcript passes 512
# tokens immediately, and the operator measured a ~900-token state answered at 0.113
# — confidently wrong — on the 512-token route, against 0.500 on the 1024-token one,
# because both lost the tail that held the answer (2026-09-22).
#
# A confidently wrong answer on truncated input is the worst outcome for a gate, so
# the default is the route with the larger budget. Screening callers name `base`,
# and the truncation report below makes the remaining risk visible rather than silent.
DEFAULT_ROUTE = "typed-decisions"

# Deprecated: named one checkpoint when the server served exactly one.
LEGACY_CHECKPOINT_VAR = "LAYA_CHECKPOINT"

app = FastMCP("laya")

# Single-flight: agent.predict()'s thread-safety is undocumented, and the same
# lock also serializes the lazy load so two concurrent calls can't race to
# construct two agent instances. One lock covers both checkpoints: they share
# one Metal device, so serializing across them is the honest granularity.
_inference_lock = threading.Lock()
_router: Any = None


def _routes() -> dict[str, str]:
    """The slot-to-repo mapping, after env overrides.

    `LAYA_CHECKPOINT` is honoured for back-compatibility but cannot say which slot
    it means, so it is applied to the default route and logged. Prefer the
    per-slot variables.
    """
    routes = dict(ROUTES)
    for slot in routes:
        var = "LAYA_CHECKPOINT_" + slot.upper().replace("-", "_")
        override = os.environ.get(var)
        if override:
            routes[slot] = override
    legacy = os.environ.get(LEGACY_CHECKPOINT_VAR)
    if legacy:
        logger.warning(
            "%s=%s is deprecated and names no route; applying it to %r. "
            "Set LAYA_CHECKPOINT_ENGLISH or LAYA_CHECKPOINT_TYPED_DECISIONS instead.",
            LEGACY_CHECKPOINT_VAR,
            legacy,
            _default_route(),
        )
        routes[_default_route()] = legacy
    return routes


def _default_route() -> str:
    requested = os.environ.get("LAYA_ROUTE_DEFAULT", DEFAULT_ROUTE)
    if requested not in ROUTES:
        raise SystemExit(
            f"LAYA_ROUTE_DEFAULT={requested!r} is not a route; choose one of {sorted(ROUTES)}"
        )
    return requested


def resolve_route(checkpoint: str | None) -> str:
    """Map a caller's `checkpoint` argument to a route name, or raise."""
    if checkpoint is None:
        return _default_route()
    key = str(checkpoint).strip().lower()
    # `base` is this project's own word for the unspecialized checkpoint; every
    # other accepted spelling is one laya_mlx.Router already understands.
    if key in ("base", "default"):
        return "english"
    import laya_mlx.router as _router_mod

    try:
        resolved = _router_mod.normalise_name(key)
    except ValueError as exc:
        raise ValueError(
            f"checkpoint={checkpoint!r} is not served here; choose one of {sorted(ROUTES)} "
            "(or 'base' for 'english')"
        ) from exc
    if resolved not in ROUTES:
        raise ValueError(
            f"checkpoint={checkpoint!r} resolves to {resolved!r}, which this server does not "
            f"load; choose one of {sorted(ROUTES)}"
        )
    return resolved


def _local_router() -> Any:
    """The shared Router, built on first use.

    `preload` is what makes two checkpoints worth having: Router defaults to
    `max_loaded=1`, so without it every alternation between routes would evict and
    rebuild the other one (`laya_mlx/router.py` `Router.preload`).
    """
    global _router
    if _router is None:
        import laya_mlx

        routes = _routes()
        preload = os.environ.get("LAYA_PRELOAD", "1") != "0"
        _router = laya_mlx.Router(models=routes, default=_default_route(), dtype="float16")
        if preload:
            _router.preload(list(routes))
        else:
            _router.load(_default_route())
    return _router


def _local_agent(route: str | None = None) -> Any:
    """The Agent for one route. Loads it if the Router has not built it yet."""
    return _local_router().load(route or _default_route())


def describe(agent: Any, route: str | None = None) -> dict[str, Any]:
    """Which weights answered, and the token budget those weights impose.

    `agent.predict()` reports `"model": "laya-rl-agent"`, a constant hardcoded in
    `laya_mlx/agent.py` `system_one` — it names the runtime, never the loaded
    checkpoint, so it cannot tell two sets of weights apart. `max_len` comes from
    the checkpoint's own `rl_agent_config.json` (512 on `aac6fef/laya-mlx`, 1024
    on the typed-decisions port), so it is read here rather than written into a
    docstring that a checkpoint swap would silently falsify.
    """
    described: dict[str, Any] = {
        "checkpoint": agent.model_id,
        "limits": {
            "max_len": agent.cfg.get("max_len", 512),
            "head_max_len": agent.cfg.get("head_max_len", 192),
        },
    }
    if route is not None:
        described["route"] = route
    return described


def _truncation_report(agent: Any, state: str, questions: dict[str, Any]) -> dict[str, Any]:
    """Which questions lost the tail of `state`, and how much.

    `usage.input_tokens` cannot answer this: `system_one` sums it across items, one
    per question (`laya_mlx/agent.py`), so on a three-question call it routinely
    exceeds `max_len` with nothing truncated. Truncation is per item — `build_sequence`
    returns `ids[:max_len]` — so the check has to be per item too.

    `agent.prepare()` is pure and builds exactly those items, so it is called here and
    again inside `predict()`. That is one extra tokenizer pass over at most `max_len`
    tokens, which is negligible against the forward pass, and it is the only way to
    report this without reimplementing `system_one`.
    """
    from laya_mlx.common import serialize_state

    max_len = agent.cfg.get("max_len", 512)
    items, _ = agent.prepare(state, questions)
    hit = [qid for qid, item in zip(questions, items) if len(item["ids"]) >= max_len]
    if not hit:
        return {"truncated": False}

    full = len(agent.tok(serialize_state(state).replace(agent.tok.mask_token, " "),
                         add_special_tokens=False)["input_ids"])
    report: dict[str, Any] = {
        "truncated": True,
        "questions": hit,
        "state_tokens": full,
        "max_len": max_len,
        "message": (
            f"`state` is {full} tokens and was cut from the end to fit this checkpoint's "
            f"{max_len}-token budget, for: {', '.join(hit)}. Whatever was at the end was "
            "not read. Put what matters first, or split the input."
        ),
    }
    # Only suggest a route that is actually bigger and actually loaded.
    bigger = [
        name
        for name in _local_router().loaded
        if _local_agent(name).cfg.get("max_len", 512) > max_len
    ]
    if bigger:
        report["message"] += (
            f" A larger budget is available on checkpoint={bigger[0]!r}."
        )
        report["larger_route_available"] = bigger[0]
    return report


def predict_locally(
    state: str, questions: dict[str, Any], checkpoint: str | None = None
) -> dict[str, Any]:
    route = resolve_route(checkpoint)
    with _inference_lock:
        agent = _local_agent(route)
        result = {
            **agent.predict(state, questions),
            **describe(agent, route),
            "route_reason": (
                "caller asked for it" if checkpoint is not None else "server default"
            ),
            "truncation": _truncation_report(agent, state, questions),
        }
    if checkpoint is None:
        # A caller reading only `route_reason` cannot tell "I omitted the argument"
        # from "my client dropped it" — a stale cached tool list produces the second
        # and looks like the first. Naming the alternative makes both visible.
        result["route_note"] = (
            f"No `checkpoint` was given, so the server default ({route}) answered. "
            f"Pass checkpoint='base' for content screening, or {sorted(ROUTES)!r}."
        )
    return result


def _predict_via_daemon(
    daemon_url: str, state: str, questions: dict[str, Any], checkpoint: str | None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"text": state, "schema": questions}
    if checkpoint is not None:
        payload["checkpoint"] = checkpoint
    response = httpx.post(
        f"{daemon_url.rstrip('/')}/predict",
        json=payload,
        timeout=DAEMON_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def _predict(
    state: str, questions: dict[str, Any], checkpoint: str | None = None
) -> dict[str, Any]:
    # Validate before forwarding, so a bad route name fails the same way on both
    # transports instead of surfacing as an opaque 400 from the daemon.
    resolve_route(checkpoint)
    daemon_url = os.environ.get("LAYA_DAEMON_URL")
    if daemon_url:
        try:
            forwarded = _predict_via_daemon(daemon_url, state, questions, checkpoint)
            return {**forwarded, "served_by": "daemon"}
        except (httpx.HTTPError, ValueError) as exc:
            # The fallback below loads this process's own checkpoint, which need
            # not be the daemon's. A log line is invisible to the caller, so the
            # divergence is reported in-band too, on the answer itself.
            logger.warning(
                "LAYA_DAEMON_URL=%s unreachable (%s); falling back to a local agent load",
                daemon_url,
                exc,
            )
            result = predict_locally(state, questions, checkpoint)
            result["served_by"] = "local-fallback"
            result["warning"] = (
                f"LAYA_DAEMON_URL={daemon_url} was unreachable ({type(exc).__name__}); "
                f"this answer came from a local load of {result['checkpoint']}, "
                "which may not be the checkpoint the daemon serves"
            )
            return result

    return {**predict_locally(state, questions, checkpoint), "served_by": "local"}


@app.tool
def laya_decide(
    state: Annotated[
        str,
        Field(description="The text to judge, as plain natural language."),
    ],
    questions: Annotated[
        dict[str, Any],
        Field(
            description=(
                "Field name to question spec. Each spec needs `type` "
                '("choice", "score" or "noul") and `instructions`. '
                "`choice` and `score` also need `criteria`. See this tool's "
                "full description for each type's `criteria` and answer shape."
            )
        ),
    ],
    checkpoint: Annotated[
        str | None,
        Field(
            description=(
                "Which checkpoint answers. `base` for screening and any judgment "
                "about the content of a text; `typed-decisions` for judgments about "
                "an agent's own state or trace, and for input over 512 tokens. "
                "Omit to use the server default. See this tool's full description."
            )
        ),
    ] = None,
) -> dict[str, Any]:
    """Answer typed questions about a piece of text with the local Laya decision model.

    Laya classifies text against options you supply. It generates no prose and
    invents no labels. Use it for a closed decision about `state`: pick one
    label, rate a level, or test whether a statement holds. Every answer carries
    a probability distribution, so a caller can gate on it or abstain. Put every
    question you need in one call, because they are batched.

    `state` is the text to judge, as plain natural language.

    `questions` maps a field name you choose to one question spec. Each spec
    needs `type` and `instructions`. Write `instructions` as the question itself,
    in a short phrase.

    `type: "choice"` picks exactly one label. `criteria` is required: a list of
    unique label strings, or an object mapping each label to a description the
    model reads. The answer holds `choice`, the winning label, and
    `probabilities`, every label mapped to its probability.

    `type: "score"` rates the text on an ordered scale you define. `criteria` is
    required: a list of level labels, lowest level first. The answer holds
    `score`, the expected level index as a fraction from 0 to len(criteria) - 1.
    It also holds `legend`, index to label, and `probabilities`, index to
    probability.

    `type: "noul"` tests whether one statement holds. `criteria` is optional: an
    object with `false` and `true` descriptions. The answer holds `noul`, the
    probability the statement is true.

    `confidence` is not the winning option's probability. For `choice` and
    `score` it is normalized entropy over the whole distribution, so an even
    spread reads low even when one option leads clearly. For `noul` it is
    `max(noul, 1 - noul)` and adds nothing. Read `probabilities` whenever the
    decision matters.

    Worked call:

        state: "I was billed twice this month. Please refund the duplicate charge."
        questions: {
          "department": {"type": "choice",
                         "instructions": "Who should handle this?",
                         "criteria": ["billing", "technical", "sales"]},
          "severity":   {"type": "score",
                         "instructions": "How severe is this for the customer?",
                         "criteria": ["trivial", "minor", "major", "critical"]},
          "refund":     {"type": "noul",
                         "instructions": "Does the customer ask for money back?"}
        }

    Limits, and how to know you hit them. The whole input is capped at the loaded
    checkpoint's token budget — 512 on some checkpoints, 1024 on others. Never
    assume one: every answer reports the live figures as `limits.max_len` and
    `limits.head_max_len`. Instructions plus rendered options take up to
    `head_max_len`, and `state` gets whatever is left.

    A longer `state` is cut from the end by the runtime, with no error. **Read
    `truncation` on every answer.** When `truncation.truncated` is true the model
    never saw the end of your text, and an answer about something that was at the
    end is meaningless — `truncation.questions` names which questions lost input,
    and `truncation.larger_route_available` names a checkpoint with more room if
    one is loaded. Do not read a confident answer over truncated input as a
    confident answer.

    Do not infer truncation from `usage.input_tokens` yourself. That figure is
    summed across questions, so on a multi-question call it exceeds `max_len`
    routinely with nothing truncated.

    A malformed spec raises `ValueError`. Omitting `criteria` on `choice` or
    `score` is the usual cause.

    Choosing a checkpoint. Two are held resident, and measurement says neither
    wins outright. Pick by what the question is about, not by what sounds better:

    - `base` — judging the *content* of a text. Screening fetched or untrusted
      input, detecting injection or directed instructions, classifying or
      routing a message. Budget 512 tokens.
    - `typed-decisions` — judging an *agent's own state*: a trace, a turn, a
      readiness or approval or risk call, anything about work already done.
      Budget 1024 tokens, so use it for input the base checkpoint would truncate.

    If the question does not clearly fall in either class, omit `checkpoint` and
    read `route` in the answer to see which one served it. `typed-decisions` is
    the default, because forgetting the argument on an agent trace costs half the
    input while forgetting it on a screening call costs only some confidence.

    Do not send screening to `typed-decisions`. On this project's probe set it
    moved a correct 0.862 to an incorrect 0.486 on a credential-theft question,
    and injection classification fell from 0.988 to 0.674 (2026-09-22).

    Those figures are single calls, not a benchmark. They are enough to choose a
    default and not enough to set a threshold on.

    Provenance of the answer. `model` is always the string `laya-rl-agent`, a
    runtime constant that identifies no checkpoint. Read `checkpoint` for the
    weights that actually answered, `route` for the slot they were chosen under,
    `route_reason` for whether you asked or the server defaulted, and `served_by`
    for where they ran: `daemon` (a warm shared process), `local` (this process),
    or `local-fallback` (the configured daemon was unreachable, so these weights
    may differ from the daemon's — a `warning` field says so).
    """
    return _predict(state, questions, checkpoint)
