> **Status: superseded-by-children.** Split by architect review (2026-09-22) — agent implementability was blocked (5 independent failure classes vs. cap 2). Replaced by [T2a](T2a-laya-mcp-fork-selection.md) (fork vetting/selection) and [T2b](T2b-laya-mcp-install-verify.md) (install/run/verify), in that order. This file is retained for background only and is not dispatchable.

# T2 — Stand up a Laya MCP server backed by the native runtime

## Description

Pick and stand up one of the existing third-party Laya MCP server forks so Laya can be reached as an MCP tool, using the native runtime T1 verified. Research (research.md, section 2) found five forks (`wsargent/laya-mcp`, `andragon3110/laya-mcp`, `NVentimiglia/laya-mcp`, `PerryLink/laya-mcp`, `EbiPenMan/laya-mcp`); none is marked official. `wsargent/laya-mcp` is the one with published setup detail (daemon + MCP wrapper over `fastmcp`, stdio transport, lazy checkpoint download).

## Source material

- `research.md` (repo root), section "2. MCP server for Laya".
- T1's setup note (once produced) for the verified native runtime this wraps.

## Acceptance Criteria

- Read the actual repo (not just its description) for the chosen fork before adopting it: check commit recency, maintainer activity, license, and real CLI/entrypoint names.
- Decide which fork to use, or whether to fork/patch one, with a stated reason, before any install.
- Install and run the chosen server's daemon/model-loading process against the runtime from T1.
- Confirm the MCP server starts over stdio and exposes at least one working tool call end-to-end (a real request/response, not just process start).
- Record exact commands run and their real output in a setup note at `tasks/notes/T2-setup.md`.
- `tasks/notes/T2-setup.md` is the artifact T3 reads for the verified entrypoint/invocation; no further discoverability mechanism is needed.

## Open items flagged by research (not yet resolved)

- Exact CLI/config surface (package name, entrypoint, whether an HTTP transport flag already exists) is unconfirmed — must be checked in the chosen fork's actual repo, not assumed from research.md's quoted description.
- Fork choice itself is undecided.
