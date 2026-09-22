---
name: laya-mcp
description: "Calls this project's first-party Laya MCP server, the `laya_decide` tool, over either the stdio transport or the loopback `streamable-http` daemon. Use when an agent working in this repo needs a real `choice`/`score`/`noul` decision from the Laya runtime, needs to pick a transport, or hits one of this setup's known traps."
metadata:
  category: workflow
---

# Laya decisions over MCP

## When to use it

- An agent in this repo needs one typed decision (`choice`, `score`, or `noul`) from the Laya
  runtime and wants it through MCP rather than importing `laya_mlx` directly
  (`laya-mcp/src/laya_mcp/server.py`).
- Use the stdio transport for a single one-off call from a fresh process.
- Use the `streamable-http` daemon for more than one call in a session, since the daemon
  stays warm between calls (see Latency expectations below).

## When not to use it

- Do not use this for any question outside `choice`/`score`/`noul` typed decisions — there is
  exactly one tool, and it does not do free-form generation (`laya-mcp/src/laya_mcp/server.py`).
- Do not reach for a preset tool name (`laya_triage`, `route_task`, etc.) — none exist in this
  project; every one of those shapes is expressed as a `laya_decide` call with a specific
  `questions` schema instead (`tmp/tasks/notes/T2c-design.md` §2).

## Tool contract

- One tool: `laya_decide(state: str, questions: dict[str, Any]) -> dict[str, Any]`
  (`laya-mcp/src/laya_mcp/server.py`).
- `state` is the free-text input to reason about.
- `questions` maps a field name to a question spec.
- Each spec's `type` is one of `choice`, `score`, or `noul`.
- Every spec carries `instructions`.
- A `choice` spec additionally carries `criteria` (a list of allowed choices).
- `laya_decide` is a thin rename of `laya-mlx`'s own `agent.predict(text, schema_dict)` API —
  `state` is `text`, `questions` is `schema_dict` (`laya-mcp/src/laya_mcp/server.py`,
  `tmp/tasks/notes/T1-setup.md` §3).
- There is no `laya.choice(prompt, options)` API — that shape does not exist on the runtime
  (`tmp/tasks/notes/T1-setup.md` §3).

## Choosing a transport

Both console scripts are installed editable into one venv
(`laya-mcp/pyproject.toml`, `tmp/tasks/notes/T2c-design.md` §1):

- Distribution name: `ld-laya-mcp`. Import package: `laya_mcp`.
- Install command: `uv pip install --python /Users/USERNAME/.venvs/laya-mlx-t1 -e ./laya-mcp`
  (`tmp/tasks/notes/T2-setup.md` §8).

### stdio (one-off call, fresh process each time)

- Command: `/Users/USERNAME/.venvs/laya-mlx-t1/bin/laya-mcp`
  (`laya-mcp/pyproject.toml`, `tmp/tasks/notes/T2-setup.md` §8).
- Spawn it as a subprocess through an MCP stdio client; there is no flag to pass.
- Every call pays a fresh process spawn plus a lazy `laya_mlx.load()` on first use
  (`laya-mcp/src/laya_mcp/server.py` `_local_agent`).

### streamable-http (repeated calls, one warm daemon)

- Start command: `nohup /Users/USERNAME/.venvs/laya-mlx-t1/bin/laya-mcp-http > /tmp/laya-mcp-http.log 2>&1 &`
  (`tmp/tasks/notes/T3-transport.md` §5).
- Loads the agent eagerly, before the listener accepts connections
  (`laya-mcp/src/laya_mcp/daemon.py`).
- MCP endpoint: `http://127.0.0.1:8765/mcp` (`tmp/tasks/notes/T3-transport.md` §7).
- Health probe: `curl -s -w '\nHTTP_STATUS:%{http_code}\n' http://127.0.0.1:8765/health`
  returns `{"status":"loading"}` / 503 before the eager load finishes, then
  `{"status":"ok"}` / 200 after (`laya-mcp/src/laya_mcp/daemon.py`,
  `tmp/tasks/notes/T3-transport.md` §7).
- Stop it with `kill <pid>` and confirm `lsof -nP -iTCP:8765 -sTCP:LISTEN` prints nothing
  (`tmp/tasks/notes/T3-transport.md` §9).

### Env vars, with their code defaults

- `LAYA_CHECKPOINT` — default `aac6fef/laya-mlx` (`laya-mcp/src/laya_mcp/server.py`
  `DEFAULT_CHECKPOINT`).
- `LAYA_DAEMON_URL` — default unset; when set, `laya_decide` forwards to
  `f"{LAYA_DAEMON_URL}/predict"` first (`laya-mcp/src/laya_mcp/server.py` `_predict`).
- `LAYA_MCP_HOST` — default `127.0.0.1` (`laya-mcp/src/laya_mcp/daemon.py` `DEFAULT_HOST`).
- `LAYA_MCP_PORT` — default `8765` (`laya-mcp/src/laya_mcp/daemon.py` `DEFAULT_PORT`).

## One worked call, verbatim

Source: `tmp/tasks/notes/T2-setup.md` §6 (stdio run against the real checkpoint).

Request:

```
tool: laya_decide
state: "I was billed twice this month. Please refund the duplicate charge."
questions: {
  "department": {
    "type": "choice",
    "instructions": "Who should handle this?",
    "criteria": ["billing", "technical", "sales"]
  }
}
```

Response:

```
{
  "model": "laya-rl-agent",
  "answers": {
    "department": {
      "type": "choice",
      "confidence": 0.7563,
      "action": {"act_probability": 1.0},
      "choice": "billing",
      "probabilities": {"billing": 0.9375, "technical": 0.0478, "sales": 0.0147}
    }
  },
  "usage": {"input_tokens": 31, "output_tokens": 0}
}
```

This exact answer/confidence/probabilities pair reproduced identically over stdio
(`tmp/tasks/notes/T2-setup.md` §6), over loopback HTTP (`tmp/tasks/notes/T3-transport.md` §8),
and over a container-to-LAN call (`tmp/tasks/notes/T3-reachability.md` §14.6) — the model is
deterministic for this input.

## Latency expectations

Every figure below is one host's single-run observation, not a benchmark
(`tmp/tasks/notes/T1-setup.md` §7):

- ~1365 ms — first-ever call in the process, includes first-time Metal-kernel JIT compile
  for this schema shape (`tmp/tasks/notes/T1-setup.md` §6).
- ~142 ms — first call in a fresh process, checkpoint already cached, no prior in-process
  compile for this schema shape (`tmp/tasks/notes/T1-setup.md` §7).
- ~22 ms — warm, same process, same schema shape already compiled (`tmp/tasks/notes/T1-setup.md` §7).
- ~89 ms — warm process, first call of a different schema `type` (`noul` vs `choice`), pays
  its own one-time compile (`tmp/tasks/notes/T1-setup.md` §7).
- ~3578 ms — stdio end-to-end: process spawn, stdio handshake, lazy load, first `predict()`
  (`tmp/tasks/notes/T2-setup.md` §6).
- ~218 ms — loopback HTTP against a `laya-mcp-http` already eagerly loaded and warm
  (`tmp/tasks/notes/T3-transport.md` §8).
- ~2376 ms — container-to-LAN call, includes the MCP `initialize` handshake plus the
  container-to-host network hop (`tmp/tasks/notes/T3-reachability.md` §14.6).
- The vendor's 7–14 ms figure reproduces only on a fully warm process repeating the same
  schema shape, and even then this host measured ~1.5–3x higher (`tmp/tasks/notes/T1-setup.md` §7).
- Prefer the HTTP daemon over stdio for any repeated calls in one session.

## Reaching the server from a container

- From inside a container, `http://localhost:8765` and `http://127.0.0.1:8765` never reach
  this host's server: they fail fast (connection-refused-class), not slow
  (`tmp/tasks/notes/T3-reachability.md` §14.7).
- Use the host's LAN IP instead, read at use time with `ipconfig getifaddr en0` — see
  `.agent/docs/dev-workflows.md` for LAN-IP detection, the chosen port, the bind address,
  and the firewall posture. Do not hardcode an IP; it is DHCP-assigned.
- `host.docker.internal` is untested under Podman (`.agent/docs/dev-workflows.md`).

## Traps

- Every distinct schema shape pays its own one-time Metal-kernel compile, and every fresh
  process pays a load: ~22 ms warm same-shape versus ~142 ms first-call-in-process and
  ~89 ms first call of a new `type` (`tmp/tasks/notes/T1-setup.md` §7).
- Round-trip cost is transport-dependent: ~3578 ms for a cold stdio spawn that lazy-loads
  (`tmp/tasks/notes/T2-setup.md` §6), ~218 ms over loopback HTTP to an already-loaded
  `laya-mcp-http` (`tmp/tasks/notes/T3-transport.md` §8), ~2376 ms from a container over the
  LAN including the `initialize` handshake (`tmp/tasks/notes/T3-reachability.md` §14.6).
  Prefer the HTTP daemon for repeated calls.
- From inside a container, `http://localhost:8765` and `http://127.0.0.1:8765` never reach
  this host's server — they fail fast, not slow. Use the LAN IP read at use time;
  `host.docker.internal` is untested under Podman (`.agent/docs/dev-workflows.md`,
  `tmp/tasks/notes/T3-reachability.md` §14.7).
- The macOS Application Firewall blocks non-loopback inbound to the ad-hoc-signed Homebrew
  `python@3.12` `Python.app` until that binary is in the allow list, and the symptom is a
  silent ~6 s timeout, not a connection refusal. It is already allowed on this host; check
  with `/usr/libexec/ApplicationFirewall/socketfilterfw --listapps | grep -i python`
  (`tmp/tasks/notes/T3-reachability.md` §7, §14.8).
- The real runtime API is `agent.predict(text, schema_dict)`, not `laya.choice(prompt, options)`;
  the MCP tool renames that pair to `state`/`questions` (`tmp/tasks/notes/T1-setup.md` §3,
  `laya-mcp/src/laya_mcp/server.py`).
- The PyPI name `laya-mcp` belongs to an unrelated package; this project's distribution is
  `ld-laya-mcp`, editable-install only and never published, so
  `uv pip install -e ./laya-mcp` is the only correct install (`.agent/docs/sources.md`
  `## Gotchas`, `tmp/tasks/notes/T2c-design.md` §1).
- When `LAYA_DAEMON_URL` is set but unreachable, the call silently succeeds via a local load
  and only a `logging.warning` records it — a crashed daemon looks like a working-but-slow
  server (`laya-mcp/src/laya_mcp/server.py` `_predict`, `tmp/tasks/notes/T2c-design.md` §4).
- A non-numeric `LAYA_MCP_PORT` crashes `laya-mcp-http` with a raw `ValueError` traceback
  (`laya-mcp/src/laya_mcp/daemon.py:37`, `tmp/tasks/T3d-mcp-http-transport-first-party-follow-ups.md`).

## Provenance

This file follows the structural convention of `.agent/skills/daemon-lifecycle/SKILL.md`, but lives at `skills/laya-mcp/` in the repo root — maintained alongside the `laya-mcp/` server code, not as general `.agent/` domain knowledge — and is discoverable via a symlink at `.agent/skills/laya-mcp`. No third-party skill file was consulted.
