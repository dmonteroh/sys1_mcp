# T3d — Add streamable-http transport to the first-party server, verify on loopback

## Description

Replaces T3b (superseded — it assumed patching a third-party fork's existing transport
flag; the first-party server T2c builds has no such flag to confirm, because it doesn't
exist yet anywhere). This task adds a real `streamable-http` entrypoint to the same
`FastMCP` app T2c defined, reusing `wsargent/laya-mcp`'s daemon design (one shared app,
`mcp.run(transport="http", host=..., port=...)`, a `/health` readiness route, eager model
load instead of lazy) rather than hand-rolling a JSON-RPC-over-HTTP protocol the way
`devthinker-ai/laya-mcp` would have required (see `tasks/notes/T2a-fork-selection.md`).

Loopback is the whole scope here, same as the original T3b. Binding to the LAN IP and
proving a container can reach it is T3c, which already expects this task's output file
unchanged (`tasks/notes/T3-transport.md`) and needs no edits.

Parent tasks: T3 (superseded by T3a/T3b/T3c originally); this task supersedes T3b within
that split.

## Source material

- `tasks/notes/T2-setup.md` — the first-party server T2c built and verified over stdio;
  this task adds a transport to that same app, not a new one.
- `tasks/notes/T2c-design.md` — the tool surface and package layout decisions this task
  must not re-open.
- `wsargent/laya-mcp`'s `src/laya_mcp/daemon.py` (read directly 2026-09-22, see
  `tasks/T2c-laya-mcp-first-party-server.md`'s Source material for the full citation and
  the no-license caveat) — the reference pattern: import the shared `server` module (not a
  new app instance), attach `/health` (503 until loaded, 200 after) and optionally
  `/predict` (plain-JSON, non-MCP callers) via `@server.mcp.custom_route(...)`, eagerly
  load the agent before `mcp.run(transport="http", host=HOST, port=PORT)` starts.
- `.agent/docs/dev-workflows.md` — the port (`8765`) this node chose. Note: `wsargent`'s
  own default daemon port is `8742` — irrelevant here; this project's own chosen port from
  T3a governs, not the reference repo's default.
- `EbiPenMan/laya-mcp`'s README (cataloged in `.agent/docs/sources.md`, read during T2a) —
  reference only for its bind-address security framing ("do not change the host binding to
  0.0.0.0 without authentication/network controls"); its actual code is CUDA/Windows and
  not otherwise relevant.

## Acceptance Criteria

- Confirm `tasks/notes/T2-setup.md` exists and records a real end-to-end stdio tool call.
  If not, stop and report blocked without changing anything.
- Add an HTTP entrypoint to the same app T2c built (new module or a second script within
  `laya-mcp/`, not a second app instance) that eagerly loads the agent, then calls
  `mcp.run(transport="http", host=..., port=...)`.
- Add a `/health` readiness route (503 before the model loads, 200 after) using `fastmcp`'s
  `custom_route` mechanism, same shape as `wsargent`'s.
- Start the server with `streamable-http` bound to `127.0.0.1` on port `8765` (this node's
  chosen port, `.agent/docs/dev-workflows.md`). Record the exact command and its real
  startup output.
- Confirm the listener with `lsof -nP -iTCP:8765 -sTCP:LISTEN` while the server runs, and
  record the output.
- Confirm `/health` returns 200 once the model is loaded. Record the response.
- Complete one real end-to-end tool call against `http://127.0.0.1:8765/mcp`: a real
  request, and a real response produced by the `laya-mlx` checkpoint through T1's runtime.
  Record the request, the response, and the observed latency.
- Record every command and its real output in `tasks/notes/T3-transport.md` — same
  filename the original T3b would have produced, so T3c's existing Source material
  pointer and verification commands need no changes.

## Implementation Constraints

**The end-to-end call must hit the real runtime.** Same standing constraint as every
other task in this chain: no stub, mock, or canned response.

**Reference vs. reuse.** Same caveat as T2c: `wsargent/laya-mcp` has no license file.
Reimplement the daemon-entrypoint *pattern* (shared app, custom routes, eager load, health
check) in this project's own code; do not copy its files or nontrivial text verbatim.

**Self-containment.** Do not read, cite, list, or depend on any path outside this repo and
this Mac host, beyond the reference repos already cataloged in `.agent/docs/sources.md`.

**Negative scope.**
- No bind to `0.0.0.0` or the LAN IP, and no LAN-reachable listener. T3c owns that.
- No container of any kind, and no cross-boundary test.
- No firewall or Little Snitch rule.
- No `/predict`-style plain-JSON convenience route unless it's already trivial given the
  `/health` work — optional, not required; do not scope-creep into building a second API
  shape if it isn't nearly free.
- No re-opening of T2c's tool surface or package-identity decisions.
- No `.agent/` writes beyond what's listed in Claims below.

**Deployment context.** Runs natively on the Apple Silicon Mac host, outside any
container. The checkpoint is already cached from T2c, so no download is expected.

**Playbook.**
1. Check `tasks/notes/T2-setup.md` records a real stdio tool call. Stop if not.
2. Read `wsargent/laya-mcp`'s `daemon.py` pattern (already fetched this session; re-fetch
   only if this task runs in a later session without it in context) for the shared-app +
   custom-route + eager-load shape.
3. Add the HTTP entrypoint and `/health` route to `laya-mcp/`, reusing the app T2c defined.
4. Start it bound to `127.0.0.1:8765`. Capture the startup output.
5. Run `lsof -nP -iTCP:8765 -sTCP:LISTEN` and capture the output.
6. Request `/health`, capture the response.
7. Invoke `laya_decide` over `http://127.0.0.1:8765/mcp` with a real input. Capture the
   request, response, and latency.
8. Stop the server and confirm the port is released.
9. Write `tasks/notes/T3-transport.md` with every command, its real output, and the
   verified HTTP invocation for T3c.

## Sizing Budget

- Concern axes: 1 — running the existing tool surface over a new transport. Lower than
  the original T3b's 2 (which also had to investigate/patch an unfamiliar fork's CLI);
  here the app and its tools are already this project's own code from T2c.
- Acceptance criteria: 8. within-target.
- Estimated file touch count: 2 — the new entrypoint module in `laya-mcp/`,
  `tasks/notes/T3-transport.md`. within-target.
- Independent failure classes: 1 — the HTTP transport starts but does not serve a real
  tool call (binding and answering are treated together, same reasoning the original T3b
  used: a bind that answers nothing proves nothing).
- Read scope: `tasks/notes/T2-setup.md`, `tasks/notes/T2c-design.md`,
  `.agent/docs/dev-workflows.md`, plus the already-fetched `wsargent/laya-mcp` reference
  source. within-target.

## Execution Gates

- Blocked by: T2c (`tasks/notes/T2-setup.md` recording a real stdio tool call against the
  first-party server).
- Order constraints: after T2c, before T3c. Independent of T3a (already complete).
- Dispatchability: blocked (until T2c's setup note exists).
- Follow-up tasks: T3c (unchanged — already expects `tasks/notes/T3-transport.md` and
  `.agent/docs/dev-workflows.md`'s facts; no edits needed to T3c itself).
- Claims: files — `tasks/T3d-mcp-http-transport-first-party.md`, one new file in
  `laya-mcp/`, `tasks/notes/T3-transport.md`. Non-file — starts a long-lived local daemon
  and an HTTP listener on `127.0.0.1:8765`, loopback only. No credential claims.
- Verification commands:
  - `["test", "-f", "tasks/notes/T2-setup.md"]`
  - `["test", "-f", "tasks/notes/T3-transport.md"]`
  - `["grep", "-q", "streamable-http", "tasks/notes/T3-transport.md"]`
  - `["grep", "-q", "127.0.0.1:8765", "tasks/notes/T3-transport.md"]`
  - `["bash", "-c", "! grep -Eq '0\\.0\\.0\\.0|podman|docker' tasks/notes/T3-transport.md"]`
  - Manual: re-run the recorded HTTP invocation and confirm the server starts, `/health`
    reports ready, and `laya_decide` answers over HTTP.
  - Manual: no listener remains on port `8765` after the task ends
    (`lsof -nP -iTCP:8765 -sTCP:LISTEN`).
