"""The `systemone` backend: any HTTP endpoint that speaks `POST /v1/systemone`.

Request `{"state", "questions", "model"?}`; response `{"model", "answers",
"usage"}` (Jev API reference, jev-agent.com/api-reference, read 2026-10-02).
That covers TypeSafe's Jev, Cloudflare's Clef on Workers AI, open servers such
as jev-local, and this project's own daemon (`sys1_mcp.daemon`), whose answers
also carry `checkpoint`, `limits` and `truncation`, passed through when present.

Configuration, all read once at startup:

- `SYS1_ENDPOINT` (required): the URL to POST to. A literal `{model}` in it is
  replaced by the model name, for providers that put the model in the path.
- `SYS1_API_KEY`: sent as `Authorization: Bearer <key>` when set.
- `SYS1_MODELS`: comma-separated model names. Each is sent as the body's
  `model`. Unset, one model named `default` is served and no `model` is sent,
  so the endpoint picks its own.
- `SYS1_CONTEXT_TOKENS`, `SYS1_TIMEOUT`, `SYS1_CONCURRENCY`: see below.
- `SYS1_REFUSES_OVERLONG=1`: the endpoint rejects input over its limit instead of
  cutting it (Jev-Style answers 422 "Nothing was truncated"; Kev the same), so an
  answer it returns was read whole and is reported as `truncated: false`.

What this backend cannot know, it says so: an endpoint that does not report
truncation gets `truncation.checked: false` on every answer, never a claim
that nothing was cut.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlsplit

import httpx

from . import Backend

# Chosen default, not measured: the context window assumed when sizing screening
# chunks. Lower than any System One model this project has a figure for (Jev 32k
# and Clef 64k per Cloudflare's Clef launch post, 2026-10-01), so the default
# errs toward more, smaller chunks. Set it to the model's real window.
DEFAULT_CONTEXT_TOKENS = 8192
# Chosen default: characters per token when sizing chunks without a tokenizer.
# English prose runs near 4; PerryLink/laya-mcp measured character estimates
# under-counting JSON tokens 1.45x (about 2.8), so 2.5 leaves margin for both.
CHARS_PER_TOKEN = 2.5
# Share of the window kept back for the question prefix when sizing chunks.
QUESTION_RESERVE = 0.25
DEFAULT_TIMEOUT_SECONDS = 30.0
# Chosen default: parallel requests for a many-state call. Each state is one
# request, since `/v1/systemone` takes one state.
DEFAULT_CONCURRENCY = 8

# For an endpoint that refuses over-limit input: anything it answered, it read whole.
READ_WHOLE = {
    "truncated": False,
    "checked": True,
    "message": "This endpoint refuses input over its limit instead of cutting it, so the whole state was read.",
}

UNREPORTED = {
    "truncated": None,
    "checked": False,
    "message": (
        "This endpoint does not report truncation, so whether the end of `state` "
        "was read is unknown. Keep input well under the model's context window."
    ),
}


def _env_number(name: str, default: float, kind: type) -> Any:
    raw = os.environ.get(name)
    if not raw:
        return kind(default)
    try:
        value = kind(raw)
    except ValueError:
        raise SystemExit(f"{name}={raw!r} is not a number") from None
    if value <= 0:
        raise SystemExit(f"{name}={raw!r} must be positive")
    return value


class SystemOneBackend(Backend):
    name = "systemone"

    def __init__(self) -> None:
        endpoint = os.environ.get("SYS1_ENDPOINT", "").strip()
        if not endpoint:
            raise SystemExit("SYS1_BACKEND=systemone needs SYS1_ENDPOINT, the URL to POST questions to")
        self.endpoint = endpoint
        names = [name.strip() for name in os.environ.get("SYS1_MODELS", "").split(",") if name.strip()]
        self._send_model = bool(names)
        self._models = names or ["default"]
        if "{model}" in endpoint and not self._send_model:
            raise SystemExit("SYS1_ENDPOINT has a {model} placeholder, so SYS1_MODELS must name the models")
        self.context_tokens = _env_number("SYS1_CONTEXT_TOKENS", DEFAULT_CONTEXT_TOKENS, int)
        self.timeout = _env_number("SYS1_TIMEOUT", DEFAULT_TIMEOUT_SECONDS, float)
        self.concurrency = _env_number("SYS1_CONCURRENCY", DEFAULT_CONCURRENCY, int)
        self.refuses_overlong = os.environ.get("SYS1_REFUSES_OVERLONG", "0") == "1"
        headers = {"Content-Type": "application/json"}
        key = os.environ.get("SYS1_API_KEY")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        self._client = httpx.Client(headers=headers, timeout=self.timeout)

    # -- naming -------------------------------------------------------------

    def models(self) -> list[str]:
        return list(self._models)

    def resolve(self, model: str | None) -> str:
        if model is None:
            return self.default_model()
        name = str(model).strip()
        if name not in self._models:
            raise ValueError(f"model={model!r} is not served here; choose one of {self._models}")
        return name

    def _where(self) -> str:
        """The endpoint without query string or credentials, for provenance."""
        parts = urlsplit(self.endpoint)
        return f"{parts.scheme}://{parts.hostname}{f':{parts.port}' if parts.port else ''}{parts.path}"

    def configured(self) -> dict[str, Any]:
        return {**super().configured(), "endpoint": self._where()}

    def describe(self, model: str) -> dict[str, Any]:
        return {"endpoint": self._where()}

    # -- inference ----------------------------------------------------------

    @staticmethod
    def _wire_questions(questions: dict[str, Any]) -> dict[str, Any]:
        """Questions in the wire contract's own shape.

        The Jev contract gives `choice` criteria as an object of option -> description;
        Laya also accepts a bare label list, so callers write both. A list is sent as
        `{label: null}`, which strict endpoints accept (Jev-Style rejects a list with
        422 `invalid_question`), and the answer's keys are the same labels either way.
        """
        out = {}
        for qid, spec in questions.items():
            if isinstance(spec, dict) and spec.get("type") == "choice" and isinstance(spec.get("criteria"), list):
                spec = {**spec, "criteria": {str(label): None for label in spec["criteria"]}}
            out[qid] = spec
        return out

    def predict(self, state: Any, questions: dict[str, Any], model: str) -> dict[str, Any]:
        body: dict[str, Any] = {"state": state, "questions": self._wire_questions(questions)}
        if self._send_model:
            body["model"] = model
        response = self._client.post(self.endpoint.replace("{model}", model), json=body)
        if response.status_code in (400, 422):
            # The endpoint rejected the input itself: a malformed spec, not an outage.
            raise ValueError(
                f"the System One endpoint rejected the request (HTTP {response.status_code}): "
                f"{response.text[:500]}"
            )
        response.raise_for_status()
        data = response.json()
        # Cloudflare's REST API wraps every result as {"result": ..., "success": ...}
        # (inferred from its v4 API convention; not yet seen on a Clef response).
        if isinstance(data, dict) and isinstance(data.get("result"), dict) and "answers" in data["result"]:
            data = data["result"]
        if not isinstance(data, dict) or not isinstance(data.get("answers"), dict):
            raise RuntimeError("the System One endpoint returned no `answers` object; no answer is returned")
        missing = [qid for qid in questions if qid not in data["answers"]]
        if missing:
            raise RuntimeError(f"the System One endpoint returned no answer for: {', '.join(missing)}")
        result: dict[str, Any] = {
            "answers": data["answers"],
            "usage": data.get("usage") or {},
            # This project's daemon names its weights in `checkpoint`; any other
            # endpoint names its model in `model`.
            "checkpoint": data.get("checkpoint") or data.get("model"),
            "truncation": data.get("truncation") or dict(READ_WHOLE if self.refuses_overlong else UNREPORTED),
        }
        if isinstance(data.get("limits"), dict):
            result["limits"] = data["limits"]
        return result

    def predict_many(
        self, states: list[Any], questions: dict[str, Any], model: str
    ) -> dict[str, Any]:
        with ThreadPoolExecutor(max_workers=min(self.concurrency, len(states))) as pool:
            results = list(pool.map(lambda state: self.predict(state, questions, model), states))
        truncated: list[list[str] | None] = []
        for result in results:
            report = result["truncation"]
            if report.get("truncated") is None:
                truncated.append(None)
            else:
                truncated.append(list(report.get("questions") or []) if report["truncated"] else [])
        prefix: dict[str, Any] = {}
        cut = next((r["truncation"] for r in results if r["truncation"].get("prefix_truncated")), None)
        if cut is not None:
            prefix = {key: cut[key] for key in ("prefix_truncated", "prefix_cuts", "prefix_message") if key in cut}
        elif any("prefix_truncated" in r["truncation"] for r in results):
            prefix = {"prefix_truncated": False}
        first = results[0]
        out: dict[str, Any] = {
            "answers": [result["answers"] for result in results],
            "truncated": truncated,
            "usage": {
                "input_tokens": sum(int(r["usage"].get("input_tokens") or 0) for r in results),
                "output_tokens": sum(int(r["usage"].get("output_tokens") or 0) for r in results),
                "requests": len(results),
            },
            "checkpoint": first["checkpoint"],
            "prefix": prefix,
        }
        if "limits" in first:
            out["limits"] = first["limits"]
        return out

    def screen_spans(
        self, text: str, questions: dict[str, Any], model: str,
        overlap_tokens: int, max_chunks: int,
    ) -> list[tuple[int, int]]:
        """Character windows sized from `SYS1_CONTEXT_TOKENS`, with no tokenizer.

        An estimate, so an endpoint that reports truncation still gets the server's
        fail-closed check; one that does not is screened on the estimate alone.
        """
        room_tokens = int(self.context_tokens * (1 - QUESTION_RESERVE))
        room = int(room_tokens * CHARS_PER_TOKEN)
        overlap = int(overlap_tokens * CHARS_PER_TOKEN)
        if len(text) <= room:
            return [(0, len(text))]
        step = room - overlap
        needed = -(-(len(text) - overlap) // step)
        if needed > max_chunks:
            raise ValueError(
                f"`text` is {len(text)} characters, which needs {needed} chunks at "
                f"SYS1_CONTEXT_TOKENS={self.context_tokens}; the limit is {max_chunks} per call. "
                "Split it and screen each part."
            )
        spans = []
        for start in range(0, len(text), step):
            end = min(start + room, len(text))
            spans.append((start, end))
            if end == len(text):
                break
        return spans

    def health(self, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        qid = next(iter(questions))
        models: dict[str, Any] = {}
        for name in self._models:
            started = time.perf_counter()
            result = self.predict(state, questions, name)
            models[name] = {
                "checkpoint": result["checkpoint"],
                **({"limits": result["limits"]} if "limits" in result else {}),
                "endpoint": self._where(),
                "context_tokens": self.context_tokens,
                "probe_ms": round((time.perf_counter() - started) * 1000, 1),
                "probe_noul": result["answers"][qid].get("noul"),
            }
        return {"runtime": {"endpoint": self._where()}, "models": models}
