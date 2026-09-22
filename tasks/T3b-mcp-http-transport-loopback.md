> **Status: superseded.** Operator override, 2026-09-22 (`tasks/notes/T2a-fork-selection.md` §7) —
> T2 no longer installs a third-party fork, so there is no fork CLI to confirm a flag on.
> Replaced by [T3d](T3d-mcp-http-transport-first-party.md), which adds `streamable-http`
> directly to the first-party server T2c builds. This file is retained for background only
> and is not dispatchable.

# T3b — Confirm the fork's HTTP transport flag and serve MCP over loopback

## Description

Establish that the Laya MCP server T2b installed can serve `streamable-http`, and prove it on loopback before any LAN address is involved. `research.md` section 3 states that `fastmcp` supports `streamable-http` in general but does not confirm the flag is wired into the fork's own CLI. This task reads the fork's source to settle that, patches the flag in only if it is genuinely absent, and completes one real tool call over `http://127.0.0.1:8765/mcp`.

Loopback is the whole scope here. Binding to the LAN IP and reaching the server across a container boundary belong to T3c.

Parent task: T3 (superseded by T3a, T3b, and T3c).

## Source material

- `tasks/notes/T2-setup.md` — the verified fork, pinned commit SHA, entrypoint, and stdio invocation T2b recorded.
- `tasks/notes/T2a-fork-selection.md` — the fork choice and its source, background only. Do not reopen it.
- `.agent/docs/dev-workflows.md` — the port this node chose, if T3a has run. Use `8765` regardless.
- `research.md` (repo root), section 3 — background only.

## Acceptance Criteria

- Confirm `tasks/notes/T2-setup.md` exists and records a real end-to-end stdio tool call. If not, stop and report blocked without changing anything.
- Read the fork's CLI entrypoint source and record whether a `--transport`, `--host`, or `--port` flag already exists, quoting the source path and the pinned SHA it was read at.
- If the flag exists, use it unchanged. Record that no patch was needed.
- If the flag is absent, add it in a single file, scoped to selecting the `fastmcp` transport and its host and port. Record the diff. A change larger than one file returns blocked.
- Start the server with `streamable-http` bound to `127.0.0.1` on port `8765`. Record the exact command and its real startup output.
- Confirm the listener with `lsof -nP -iTCP:8765 -sTCP:LISTEN` while the server runs, and record the output.
- Complete one real end-to-end tool call against `http://127.0.0.1:8765/mcp`: a real request, and a real response produced by the Laya model through T1's runtime. Record the request, the response, and the observed latency.
- Record every command and its real output in `tasks/notes/T3-transport.md`, and state that this note is the artifact T3c reads for the verified HTTP invocation.

## Implementation Constraints

**The end-to-end call must hit the real runtime.** A stub, mock, fixture, or canned response does not satisfy the end-to-end criterion. If the runtime cannot be reached, report blocked rather than passing with a substitute.

**Reference pattern.** No command is presented as verified until it has actually been run and its output checked (`.agent/rules/contract.md`, Output conventions). The note records real output, not paraphrase.

**Third-party code handling.** Read the CLI entrypoint before executing it. Stay at the commit SHA T2b pinned. Run the server with no credentials or secrets in its environment.

**Self-containment.** Do not read, cite, list, or depend on any path outside this repository and this Mac host.

**Negative scope.**
- No bind to `0.0.0.0` or to the LAN IP, and no LAN-reachable listener. T3c owns that.
- No container of any kind, and no cross-boundary test.
- No firewall or Little Snitch rule.
- No patch beyond the single-file transport flag, and none at all if the flag already exists.
- No re-evaluation of the fork choice or of T1's runtime choice.
- No writes under `.agent/`.

**Deployment context.** Runs natively on the Apple Silicon Mac host, outside any container. The checkpoint is already cached from T2b, so no download is expected.

**Playbook.**
1. Check `tasks/notes/T2-setup.md` exists and shows a real stdio tool call. Stop if not.
2. Open the fork's CLI entrypoint source and look for a transport, host, or port flag. Record the path and what you found.
3. Add the flag in one file only if it is absent. Record the diff.
4. Start the daemon exactly as `tasks/notes/T2-setup.md` records it.
5. Start the MCP server with `streamable-http` on `127.0.0.1:8765`. Capture the startup output.
6. Run `lsof -nP -iTCP:8765 -sTCP:LISTEN` and capture the output.
7. Invoke one tool over `http://127.0.0.1:8765/mcp` with a real input. Capture the request, the response, and the latency.
8. Stop the server and confirm the port is released.
9. Write `tasks/notes/T3-transport.md` with every command, its real output, the patch decision, and the verified HTTP invocation for T3c.

## Sizing Budget

- Concern axes: 2 — the fork's CLI transport surface, and running that transport on loopback. At cap.
- Acceptance criteria: 8. within-target.
- Estimated file touch count: 2 — `tasks/notes/T3-transport.md`, plus at most one fork source file outside this repository's tree. within-target.
- Independent failure classes: 2 — the transport flag is missing or resists a one-file patch, and the HTTP server starts but does not serve a real tool call. At cap, not over: a server that binds but answers nothing proves nothing, so splitting these would push a live process across a task boundary.
- Read scope: 4 local files plus the fork's CLI entrypoint source. within-target.

## Execution Gates

- Blocked by: T2b (`tasks/notes/T2-setup.md` recording a real stdio tool call at a pinned SHA).
- Order constraints: after T2b, before T3c. Independent of T3a.
- Dispatchability: blocked.
- Follow-up tasks: T3c.
- Claims: files — `tasks/T3b-mcp-http-transport-loopback.md`, `tasks/notes/T3-transport.md`, and at most one file in the installed fork. Non-file — starts a long-lived local daemon and an HTTP listener on `127.0.0.1:8765`, loopback only. No credential claims.
- Verification commands:
  - `["test", "-f", "tasks/notes/T2-setup.md"]`
  - `["test", "-f", "tasks/notes/T3-transport.md"]`
  - `["grep", "-q", "streamable-http", "tasks/notes/T3-transport.md"]`
  - `["grep", "-q", "127.0.0.1:8765", "tasks/notes/T3-transport.md"]`
  - `["grep", "-Eq", "[0-9a-f]{7,40}", "tasks/notes/T3-transport.md"]`
  - `["bash", "-c", "! grep -Eq '0\\.0\\.0\\.0|podman|docker' tasks/notes/T3-transport.md"]`
  - Manual: re-run the recorded HTTP invocation and confirm the server starts and lists at least one tool.
  - Manual: the note contains a real request and a real model-produced response with an observed latency figure.
  - Manual: the note states whether the transport flag pre-existed or was patched, and shows the diff when it was patched.
  - Manual: no listener remains on port `8765` after the task ends. Confirm with `lsof -nP -iTCP:8765 -sTCP:LISTEN`.
