"""The `laya-mlx` backend: Laya checkpoints held resident in this process.

Everything that knows `laya_mlx` internals lives here: the Router, the token
budgets, the per-question truncation report, batched forward passes across
states, tokenizer-exact screening chunks, and the identity a lock can pin.
The measurements cited below were all taken on this backend.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import logging
import math
import os
import threading
import time
from typing import Any

from . import Backend

logger = logging.getLogger("sys1_mcp")

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
DEFAULT_ROUTE = "typed-decisions"

# The English root is the content checkpoint: it beat typed-decisions on every
# screening wording tried (tmp/probes/tools/screen_wording.json). Judgments about
# an agent's own task state go to typed-decisions, same reasoning as DEFAULT_ROUTE.
ROLE_ROUTES = {"content": "english", "trace": "typed-decisions"}

# Ceiling on MLX's freed-buffer cache; see `_router`.
MLX_CACHE_LIMIT_BYTES = 512 * 1024 * 1024
# Headroom for re-tokenizing a screening chunk's text differently at its edges.
SCREEN_SAFETY_TOKENS = 8


def _routes() -> dict[str, str]:
    """The slot-to-repo mapping, after `LAYA_CHECKPOINT_<SLOT>` overrides."""
    routes = dict(ROUTES)
    for slot in routes:
        override = os.environ.get("LAYA_CHECKPOINT_" + slot.upper().replace("-", "_"))
        if override:
            routes[slot] = override
    return routes


def _calibration_warnings(answers: dict[str, Any]) -> dict[str, Any]:
    """A `warning` on a choice whose probabilities the calibration table flattens."""
    for answer in answers.values():
        probs = answer.get("probabilities")
        if answer.get("type") == "choice" and isinstance(probs, dict) and len(probs) >= 11:
            # Both checkpoints' `rl_agent_config.json` set `choice:11+` to
            # temperature 0.1006, a tenfold sharpening (`laya_mlx/common.py`
            # `temp_bucket`). Measured: one irrelevant 11th label took a 0.65
            # answer to exactly 1.000 (tmp/tasks/notes/T11-calibration.md).
            answer["warning"] = (
                f"{len(probs)} options: this checkpoint's calibration sharpens every choice "
                "with 11 or more options about tenfold, so these probabilities read near 1/0 "
                "regardless of how clear the text is. Trust the label at most; for a usable "
                "probability ask with 10 or fewer options."
            )
    return answers


def _state_truncated(items: list[dict[str, Any]], qids: list[str], max_len: int) -> list[str]:
    """The question ids whose prepared item lost the tail of the state.

    `build_sequence` returns `ids[:max_len]`, so an item at the cap was cut.
    """
    return [qid for qid, item in zip(qids, items) if len(item["ids"]) >= max_len]


def _prefix_cuts(agent: Any, questions: dict[str, Any]) -> dict[str, Any]:
    """Which questions had their options or question text shortened, silently.

    `build_prefix` fits options into `head_max_len`: once they overflow it, every
    option is cut to `(head_max_len - 16) // n` tokens, and the question text to
    `max(8, budget left)` (`laya_mlx/common.py`). Neither raises. Measured in
    `tmp/tasks/notes/T12-choice-ceiling.md`: described labels are shortened from
    12 options on the 512-token checkpoint, question text cut from ~46.
    """
    from laya_mlx.common import build_prefix, render_options

    tok, head_len = agent.tok, agent.cfg.get("head_max_len", 192)
    cut: dict[str, list[str]] = {}
    for qid, definition in questions.items():
        q = agent._to_internal(definition)
        ids, markers = build_prefix(tok, q, head_len)
        wanted = [
            1 + len(tok(" " + o.replace(tok.mask_token, " "))["input_ids"][:48])
            for o in render_options(q)
        ]
        kept = [b - a for a, b in zip(markers, markers[1:])] + [len(ids) - 1 - markers[-1]]
        head_wanted = len(tok("%s question: %s" % (q["t"], q["ins"].replace(tok.mask_token, " ")))["input_ids"])
        what = []
        if kept != wanted:
            what.append("options")
        if markers[0] - 2 < head_wanted:
            what.append("instructions")
        if what:
            cut[qid] = what
    if not cut:
        return {"prefix_truncated": False}
    return {
        "prefix_truncated": True,
        "prefix_cuts": cut,
        "prefix_message": (
            "Too many or too long options for this checkpoint's "
            f"{head_len}-token question budget, so the model read shortened "
            f"{' and '.join(sorted({w for v in cut.values() for w in v}))} for: "
            f"{', '.join(cut)}. Use fewer labels or shorter descriptions."
        ),
    }


def _answer(agent: Any, q: dict[str, Any], item: dict[str, Any], logits_row: Any, act_row: Any) -> dict[str, Any]:
    """One answer from one row of model output.

    A line-for-line copy of the per-row body of `laya_mlx/agent.py`
    `Agent.system_one` (0.1.0), which has no per-row entry point of its own. Any
    change there must land here too; `tmp/probes/tools/classify_parity.py`
    compares the two paths number for number.
    """
    import numpy as np
    from laya_mlx.common import confidence_from_probs, temp_bucket

    k, qt = len(item["markers"]), item["qtype"]
    scale = agent.temperature_by_options.get(temp_bucket(qt, k), agent.temperature[qt])
    z = logits_row[:k] / max(1e-3, float(scale))
    p = np.exp(z - z.max())
    p /= p.sum()
    answer: dict[str, Any] = {
        "type": q["t"],
        "confidence": round(confidence_from_probs(p, k), 4),
        "action": {"act_probability": round(float(act_row[0]), 4)},
    }
    if q["t"] == "choice":
        labels = list(q["crit"])
        answer.update(
            choice=labels[int(p.argmax())],
            probabilities={label: round(float(v), 4) for label, v in zip(labels, p)},
        )
    elif q["t"] == "score":
        answer.update(
            score=round(float((np.arange(k) * p).sum()), 4),
            legend={str(i): value for i, value in enumerate(q["crit"])},
            probabilities={str(i): round(float(v), 4) for i, v in enumerate(p)},
        )
    else:
        answer.update(
            noul=round(float(p[1]), 4),
            confidence=round(max(float(p[1]), 1.0 - float(p[1])), 4),
        )
    return answer


def _snapshot(agent: Any) -> str | None:
    """The resolved Hugging Face snapshot hash, which pins the weights.

    `agent.revision` is whatever was requested — `None` under `Router.load` — so
    it cannot say which commit is on disk; the snapshot directory name can.
    """
    path = agent.model_dir
    for candidate in (path, *path.parents):
        if candidate.parent.name == "snapshots":
            return candidate.name
    return None


def _config_sha256(agent: Any) -> str | None:
    """Hash of the checkpoint's `rl_agent_config.json`, which holds every
    calibration temperature, so a config-only change is visible too."""
    path = agent.model_dir / "rl_agent_config.json"
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


class LayaMlxBackend(Backend):
    name = "laya-mlx"

    def __init__(self) -> None:
        # Single-flight: agent.predict()'s thread-safety is undocumented, and the
        # same lock also serializes the lazy load so two concurrent calls can't
        # race to construct two agent instances. One lock covers both checkpoints:
        # they share one Metal device, so serializing across them is the honest
        # granularity.
        self._lock = threading.Lock()
        self._router: Any = None

    # -- naming -------------------------------------------------------------

    def models(self) -> list[str]:
        return list(ROUTES)

    def loaded_models(self) -> list[str]:
        return list(self._router.loaded) if self._router is not None else []

    def builtin_default(self) -> str:
        return DEFAULT_ROUTE

    def builtin_role(self, role: str) -> str:
        return ROLE_ROUTES[role]

    def resolve(self, model: str | None) -> str:
        if model is None:
            return self.default_model()
        key = str(model).strip().lower()
        # `base` is this project's own word for the unspecialized checkpoint. Upstream
        # aliases `default` to `english`; here it means the server default, as it
        # does on every backend. Every other spelling is one laya_mlx.Router knows.
        if key == "base":
            return "english"
        if key == "default":
            return self.default_model()
        import laya_mlx.router as _router_mod

        try:
            resolved = _router_mod.normalise_name(key)
        except ValueError as exc:
            raise ValueError(
                f"model={model!r} is not served here; choose one of {sorted(ROUTES)} "
                "(or 'base' for 'english')"
            ) from exc
        if resolved not in ROUTES:
            raise ValueError(
                f"model={model!r} resolves to {resolved!r}, which this server does not "
                f"load; choose one of {sorted(ROUTES)}"
            )
        return resolved

    def model_help(self) -> str:
        return (
            "`base` (or `english`) for the content of a text — what it says or asks "
            "for, routing a message, spotting instructions in it; 512-token budget. "
            "`typed-decisions` for an agent's own state or trace — did it do X, does "
            "the result match the request; 1024-token budget, so also for longer "
            f"input. Omit for the default ({self.default_model()})."
        )

    def configured(self) -> dict[str, Any]:
        return {"models": _routes(), "default_model": self.default_model()}

    # -- loading ------------------------------------------------------------

    def _router_instance(self) -> Any:
        """The shared Router, built on first use.

        `preload` is what makes two checkpoints worth having: Router defaults to
        `max_loaded=1`, so without it every alternation between routes would evict
        and rebuild the other one (`laya_mlx/router.py` `Router.preload`).
        """
        if self._router is None:
            import laya_mlx
            import mlx.core as mx

            # MLX keeps freed Metal buffers in a cache for reuse, unbounded by
            # default, and every distinct batch shape leaves its own. Measured on
            # the daemon: an 8.4 GB footprint after a round of mixed calls, 11 GB
            # after one 256-item classify, against 1.7 GB idle with both
            # checkpoints resident (tmp/tasks/notes/T10-classify-batching.md).
            # The cap releases the excess.
            mx.set_cache_limit(MLX_CACHE_LIMIT_BYTES)
            routes = _routes()
            default = self.default_model()
            preload = os.environ.get("LAYA_PRELOAD", "1") != "0"
            router = laya_mlx.Router(models=routes, default=default, dtype="float16")
            if preload:
                router.preload(list(routes))
            else:
                router.load(default)
            self._router = router
        return self._router

    def _agent(self, model: str) -> Any:
        """The Agent for one route. Loads it if the Router has not built it yet.

        Every agent gets upstream's `PrefixCache`, which `Agent(cache_prompts=True)`
        would build but `Router.load` has no way to pass. The cache keys on the
        question alone — tokenizer ids, head length, type, instructions, rendered
        options, never the state (`laya_mlx/prepared.py` `PrefixCache.prepare`) — so
        one schema asked of many texts builds its prefix once. It produces the same
        items `build_sequence` does, so answers are unchanged.
        """
        agent = self._router_instance().load(model)
        if agent._prefix_cache is None:
            from laya_mlx.prepared import PrefixCache

            agent._prefix_cache = PrefixCache()
        return agent

    def load(self) -> None:
        with self._lock:
            self._router_instance()

    def _describe(self, agent: Any) -> dict[str, Any]:
        """Which weights answered, and the token budget those weights impose.

        `agent.predict()` reports `"model": "laya-rl-agent"`, a constant hardcoded in
        `laya_mlx/agent.py` `system_one` — it names the runtime, never the loaded
        checkpoint, so it cannot tell two sets of weights apart. `max_len` comes from
        the checkpoint's own `rl_agent_config.json` (512 on `aac6fef/laya-mlx`, 1024
        on the typed-decisions port), so it is read here rather than written into a
        docstring that a checkpoint swap would silently falsify.
        """
        return {
            "checkpoint": agent.model_id,
            "limits": {
                "max_len": agent.cfg.get("max_len", 512),
                "head_max_len": agent.cfg.get("head_max_len", 192),
            },
        }

    def describe(self, model: str) -> dict[str, Any]:
        with self._lock:
            return self._describe(self._agent(model))

    # -- inference ----------------------------------------------------------

    def _truncation_report(self, agent: Any, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        """Which questions lost the tail of `state`, and how much.

        `usage.input_tokens` cannot answer this: `system_one` sums it across items,
        one per question (`laya_mlx/agent.py`), so on a three-question call it
        routinely exceeds `max_len` with nothing truncated. Truncation is per item —
        `build_sequence` returns `ids[:max_len]` — so the check has to be per item too.

        `agent.prepare()` is pure and builds exactly those items, so it is called here
        and again inside `predict()`. That is one extra tokenizer pass over at most
        `max_len` tokens, which is negligible against the forward pass, and it is the
        only way to report this without reimplementing `system_one`. Caller holds
        the lock.
        """
        from laya_mlx.common import serialize_state

        max_len = agent.cfg.get("max_len", 512)
        items, _ = agent.prepare(state, questions)
        hit = _state_truncated(items, list(questions), max_len)
        prefix = _prefix_cuts(agent, questions)
        if not hit:
            return {"truncated": False, **prefix}

        full = len(agent.tok(serialize_state(state).replace(agent.tok.mask_token, " "),
                             add_special_tokens=False)["input_ids"])
        report: dict[str, Any] = {
            **prefix,
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
            for name in self._router_instance().loaded
            if self._agent(name).cfg.get("max_len", 512) > max_len
        ]
        if bigger:
            report["message"] += f" A larger budget is available on model={bigger[0]!r}."
            report["larger_model_available"] = bigger[0]
        return report

    def predict(self, state: Any, questions: dict[str, Any], model: str) -> dict[str, Any]:
        with self._lock:
            agent = self._agent(model)
            predicted = agent.predict(state, questions)
            return {
                "answers": _calibration_warnings(predicted["answers"]),
                "usage": predicted["usage"],
                **self._describe(agent),
                "truncation": self._truncation_report(agent, state, questions),
            }

    def predict_many(
        self, states: list[Any], questions: dict[str, Any], model: str
    ) -> dict[str, Any]:
        """Answer one schema for many states in batched forward passes.

        `system_one` batches the questions of one state; this batches across states
        too. Each state is prepared exactly as `system_one` prepares it, the flat
        (state, question) list is cut at `agent.batch_size` — 16 rows of at most
        `max_len` tokens, so peak memory is one ordinary batch however many states
        come in — and every row is mapped back by its own recorded (state, question)
        index, never by position arithmetic.
        """
        import numpy as np
        from laya_mlx.agent import collate_items

        with self._lock:
            agent = self._agent(model)
            qids = list(questions)
            max_len = agent.cfg.get("max_len", 512)
            flat: list[tuple[int, str, dict[str, Any], dict[str, Any]]] = []
            truncated: list[list[str] | None] = []
            for index, state in enumerate(states):
                items, internal = agent.prepare(state, questions)
                truncated.append(_state_truncated(items, qids, max_len))
                flat.extend((index, qid, item, q) for qid, item, q in zip(qids, items, internal))

            answers: list[dict[str, Any]] = [{} for _ in states]
            passes = 0
            for start in range(0, len(flat), agent.batch_size):
                chunk = flat[start : start + agent.batch_size]
                batch = collate_items(
                    [item for _, _, item, _ in chunk],
                    agent.tok.pad_token_id,
                    pad_to_multiple=agent.pad_to_multiple,
                    max_length=max_len,
                )
                logits, act = agent.forward(batch)
                passes += 1
                logits, act = np.asarray(logits), np.asarray(act)
                if not np.isfinite(logits).all() or not np.isfinite(act).all():
                    raise FloatingPointError("Non-finite model outputs; retry with dtype='float32'")
                act = np.exp(act - act.max(axis=-1, keepdims=True))
                act /= act.sum(axis=-1, keepdims=True)
                for row, (index, qid, item, q) in enumerate(chunk):
                    answers[index][qid] = _answer(agent, q, item, logits[row], act[row])
            for per_state in answers:
                _calibration_warnings(per_state)
            tokens = sum(len(item["ids"]) for _, _, item, _ in flat)
            return {
                "answers": answers,
                "truncated": truncated,
                "usage": {"input_tokens": tokens, "output_tokens": 0, "forward_passes": passes},
                **self._describe(agent),
                "prefix": _prefix_cuts(agent, questions),
            }

    def screen_spans(
        self, text: str, questions: dict[str, Any], model: str,
        overlap_tokens: int, max_chunks: int,
    ) -> list[tuple[int, int]]:
        """Overlapping windows sized to the tightest question's state budget, so
        every window is read whole: `build_sequence` drops the end of the state,
        and injected instructions are commonly placed late."""
        from laya_mlx.common import build_prefix

        with self._lock:
            agent = self._agent(model)
            tok = agent.tok
            max_len, head_len = agent.cfg.get("max_len", 512), agent.cfg.get("head_max_len", 192)
            longest_prefix = max(
                len(build_prefix(tok, agent._to_internal(q), head_len)[0]) for q in questions.values()
            )
            room = max_len - longest_prefix - 1 - SCREEN_SAFETY_TOKENS
            encoding = tok.backend.encode(text.replace(tok.mask_token, " "), add_special_tokens=False)
            offsets = encoding.offsets
        if len(offsets) <= room:
            return [(0, len(text))]
        step = room - overlap_tokens
        needed = math.ceil((len(offsets) - overlap_tokens) / step)
        if needed > max_chunks:
            raise ValueError(
                f"`text` is {len(offsets)} tokens, which needs {needed} chunks; the limit is "
                f"{max_chunks} per call. Split it and screen each part."
            )
        spans = []
        for start in range(0, len(offsets), step):
            end = min(start + room, len(offsets))
            spans.append((offsets[start][0], offsets[end - 1][1]))
            if end == len(offsets):
                break
        return spans

    def health(self, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        qid = next(iter(questions))
        models: dict[str, Any] = {}
        with self._lock:
            router = self._router_instance()
            for name in router.loaded:
                agent = self._agent(name)
                started = time.perf_counter()
                answer = agent.predict(state, questions)["answers"][qid]
                models[name] = {
                    **self._describe(agent),
                    "snapshot": _snapshot(agent),
                    "config_sha256": _config_sha256(agent),
                    "dtype": str(agent.dtype).removeprefix("mlx.core."),
                    "batch_size": agent.batch_size,
                    "prefix_cache": agent._prefix_cache is not None,
                    "probe_ms": round((time.perf_counter() - started) * 1000, 1),
                    "probe_noul": answer["noul"],
                }
        return {"runtime": {"laya_mlx": importlib.metadata.version("laya-mlx")}, "models": models}
