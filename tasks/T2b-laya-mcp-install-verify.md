> **Status: superseded.** Operator override, 2026-09-22 (`tasks/notes/T2a-fork-selection.md` §7) —
> after T2a selected `devthinker-ai/laya-mcp`, the operator decided to build a first-party
> server instead, reusing design ideas from `wsargent/laya-mcp` (T2a's best architectural
> match, disqualified there only on a missing license). Replaced by
> [T2c](T2c-laya-mcp-first-party-server.md). This file is retained for background only and
> is not dispatchable.

# T2b — Install and verify the selected Laya MCP server over stdio

## Description

Install the Laya MCP server fork that T2a selected, run it against the native runtime T1 verified, and prove one real end-to-end tool call over stdio. The fork choice, its pinned commit, and its entrypoint names are already decided and recorded — this task executes them, it does not re-litigate them.

Parent task: T2 (superseded by T2a and this task).

## Source material

- `tasks/notes/T2a-fork-selection.md` — the chosen fork, pinned commit SHA, install commands, and entrypoints, each with its source.
- `tasks/notes/T1-setup.md` — the verified native runtime this wraps, and the commands that made it work.
- `research.md` (repo root), section 2 — background only; `tasks/notes/T2a-fork-selection.md` overrides it wherever they disagree.

## Acceptance Criteria

- Confirm `tasks/notes/T1-setup.md` exists and records a successful real inference run. If not, stop and report blocked without installing anything.
- Read `tasks/notes/T2a-fork-selection.md` and use the fork, commit SHA, and entrypoints it names. Do not reopen the fork decision.
- Read the selected fork's daemon and MCP-server entrypoint source before executing it, and record anything it does beyond loading the model and serving MCP.
- Install the selected fork at the pinned commit SHA. Record the exact commands and their real output, including the resolved SHA.
- Start the daemon/model-loading process against T1's verified runtime and confirm the checkpoint loads. Record the checkpoint source and its cache location.
- Start the MCP server over stdio and complete at least one real end-to-end tool call: a real request, and a real response produced by the Laya model through T1's runtime. Record the request, the response, and the observed latency.
- Record every command and its real output in `tasks/notes/T2-setup.md`, including the pinned SHA, and state that this note is the artifact T3 reads for the verified entrypoint and invocation.
- Do not implement or configure HTTP/network transport and do not bind a port.

## Implementation Constraints

**The end-to-end call must hit the real runtime.** A stub, mock, fixture, or canned response does not satisfy the end-to-end criterion: the response must come from the `convaiinnovations/laya` checkpoint loaded through T1's runtime. If the runtime cannot be reached, report blocked rather than passing with a substitute.

**Reference pattern.** No command is presented as verified until it has actually been run and its output checked (`.agent/rules/contract.md`, Output conventions). The note records real output, not paraphrase.

**Third-party code handling.** Install at the exact commit SHA T2a pinned, never at a floating tag or branch head. Read the daemon and MCP-server entrypoints before running them. Run the daemon with no credentials or secrets in its environment.

**Negative scope.**
- No HTTP, `streamable-http`, `--host`, or `--port` work, and no port binding. T3 owns network transport.
- No patching of the fork beyond configuration or entrypoint wiring that T2a explicitly recorded as required, and never more than a single file. Anything larger returns blocked.
- No second MCP server instance inside a devcontainer (research.md section 3, option 2 — out of scope).
- No re-evaluation of the fork choice or of T1's runtime choice.
- No writes under `.agent/`.

**Deployment context.** Runs natively on the Apple Silicon Mac host, outside any container. First inference downloads the checkpoint into `~/.cache/huggingface`, so network access is needed on the first call.

**Playbook.**
1. Check `tasks/notes/T1-setup.md` exists and shows a successful inference. Stop if not.
2. Read `tasks/notes/T2a-fork-selection.md` for the fork, SHA, install commands, and entrypoint names.
3. Open the fork's daemon and MCP-server entrypoint source; note anything beyond model loading and MCP serving.
4. Run the recorded install commands at the pinned SHA; capture the output and the resolved SHA.
5. Start the daemon; capture the output and confirm the checkpoint loads. Record its source and cache path.
6. Start the MCP server over stdio, list its tools, and invoke one with a real input. Capture the request, the response, and the latency.
7. Write `tasks/notes/T2-setup.md` with every command and its real output, the pinned SHA, the verified stdio invocation for T3, and anything noticed in step 3.

## Sizing Budget

- Concern axes: 1 — install, run, and verify one already-chosen package. within-target.
- Acceptance criteria: 8. within-target.
- Estimated file touch count: 1 — `tasks/notes/T2-setup.md`. within-target.
- Independent failure classes: 2 — dependency acquisition (install, checkpoint download) and daemon-plus-MCP stdio end-to-end. At cap, not over: a daemon that starts but serves nothing proves nothing, so splitting these would push a live process across a task boundary.
- Read scope: 4 local files, largest `research.md` at 53 lines. within-target. Non-file addendum: the fork's daemon and MCP-server entrypoint source is read before execution.

## Execution Gates

- Blocked by: T1 (`tasks/notes/T1-setup.md` recording a successful inference) and T2a (`tasks/notes/T2a-fork-selection.md` naming a fork and a commit SHA). If T2a concluded that no fork qualifies, this task does not start.
- Order constraints: after T1 and T2a, before T3.
- Dispatchability: blocked.
- Follow-up tasks: T3.
- Claims: files — `tasks/T2b-laya-mcp-install-verify.md`, `tasks/notes/T2-setup.md`. Non-file — installs a third-party Python package at a pinned commit into the host environment; starts a long-lived local daemon process; writes the checkpoint into `~/.cache/huggingface`; stdio subprocess only, no port binding and no network listener. No credential claims.
- Verification commands:
  - `["test", "-f", "tasks/notes/T1-setup.md"]`
  - `["test", "-f", "tasks/notes/T2a-fork-selection.md"]`
  - `["test", "-f", "tasks/notes/T2-setup.md"]`
  - `["grep", "-Eq", "[0-9a-f]{7,40}", "tasks/notes/T2-setup.md"]`
  - `["bash", "-c", "! grep -Eiq 'streamable-http|--host|--port|0\\.0\\.0\\.0' tasks/notes/T2-setup.md || echo 'WARN: transport material present — confirm it is a recorded observation, not work done'"]`
  - Manual: re-run the stdio invocation exactly as the note records it and confirm the server starts and lists at least one tool.
  - Manual: the note contains a real request and a real model-produced response with an observed latency figure — not a stub, mock, or placeholder.
  - Manual: the checkpoint's source and cache location are recorded, and the cache path actually exists on disk.
  - Manual: no port is bound by the verified invocation (confirm with lsof/netstat while the server runs).
