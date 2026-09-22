# Task board

Index over `tasks/*.md`, built to the `subagent-orchestrator` skill's Task Board schema
(step 2: ID/outcome, claim set, non-file surfaces, depends_on, verification, status). This
project runs one task at a time, not concurrent workers, so the claim-set columns exist
for the disjointness check that skill requires *before* any future parallel dispatch, not
because anything here runs concurrently today. This file is a thin index — full acceptance
criteria, playbooks, and verification commands stay in each task's own file; this table
never restates them, only points at them.

Status values follow the skill's vocab (`queued | running | needs-info | needs-fix | ready
| integrated`), extended with `superseded` for this project's own retired-by-split state
(recorded in each superseded file's own banner, not invented here).

Regenerate this table by hand from each task file's own `Blocked by:` / `Order
constraints:` / `Dispatchability:` / `Claims:` lines whenever a task's state changes —
there is no script backing it.

| ID | Outcome | Status | depends_on | Claim set (files) | Non-file surfaces | Source |
|---|---|---|---|---|---|---|
| T1 | Verify and install the native `laya-mlx` runtime on Apple Silicon | integrated | none | `tasks/notes/T1-setup.md` | installs `laya-mlx` + deps into a `uv` venv; downloads the HF checkpoint | [T1-laya-native-runtime.md](T1-laya-native-runtime.md) |
| T2 | Stand up an MCP server backed by T1's runtime | superseded-by-children → T2a, T2b | — | — | — | [T2-laya-mcp-server.md](T2-laya-mcp-server.md) |
| T2a | Vet third-party `laya-mcp` forks and select one | integrated (selection later overridden — see note) | T1 | `tasks/notes/T2a-fork-selection.md`, `.agent/docs/sources.md` | read-only GitHub access | [T2a-laya-mcp-fork-selection.md](T2a-laya-mcp-fork-selection.md) |
| T2b | Install and verify the T2a-selected fork over stdio | **superseded** → T2c | T1, T2a | `tasks/notes/T2-setup.md` | installs a third-party package; local stdio subprocess only | [T2b-laya-mcp-install-verify.md](T2b-laya-mcp-install-verify.md) |
| T2c | Design, implement, and verify a first-party stdio MCP server | **ready** | T1 | `laya-mcp/`, `tasks/notes/T2c-design.md`, `tasks/notes/T2-setup.md`, `.agent/docs/sources.md`, `.agent/purpose.md` | installs a first-party editable package; no port, no listener | [T2c-laya-mcp-first-party-server.md](T2c-laya-mcp-first-party-server.md) |
| T3 | Make the MCP server reachable from devcontainer agents | superseded-by-children → T3a, T3b/T3d, T3c | — | — | — | [T3-devcontainer-mcp-reachability.md](T3-devcontainer-mcp-reachability.md) |
| T3a | Record LAN-IP / port / bind / firewall decisions | integrated | none | `.agent/docs/dev-workflows.md`, `.agent/docs/architecture.md` | read-only host commands only | [T3a-host-network-access-decisions.md](T3a-host-network-access-decisions.md) |
| T3b | Confirm/patch the fork's HTTP transport, verify on loopback | **superseded** → T3d | T2b | `tasks/notes/T3-transport.md` | HTTP listener on `127.0.0.1:8765` | [T3b-mcp-http-transport-loopback.md](T3b-mcp-http-transport-loopback.md) |
| T3d | Add `streamable-http` to the first-party server, verify on loopback | queued | T2c | `laya-mcp/`, `tasks/notes/T3-transport.md` | HTTP listener on `127.0.0.1:8765` | [T3d-mcp-http-transport-first-party.md](T3d-mcp-http-transport-first-party.md) |
| T3c | Bind on the LAN IP, prove a disposable container reaches it | queued | T3a, T3d | `tasks/notes/T3-reachability.md`, `.agent/docs/dev-workflows.md` | LAN-bound listener `0.0.0.0:8765`; one throwaway Podman container; possible firewall rule | [T3c-lan-bind-container-reachability.md](T3c-lan-bind-container-reachability.md) |
| T4 | Write a project-specific `SKILL.md` for using Laya | queued, not yet refined | T2c/T3d/T3c (needs verified facts from all of T1-T3's live children) | undecided (task not yet refined) | undecided | [T4-laya-skill-md.md](T4-laya-skill-md.md) |

## Notes

- T2a's row says "integrated (selection later overridden)": the task itself completed and
  its rubric/facts stand as verified record, but the operator overrode its fork choice —
  see `tasks/notes/T2a-fork-selection.md`'s banner and §7. Downstream work follows the
  override (T2c/T3d), not T2a's original selection.
- `depends_on` here mirrors each task's own `Blocked by:` line; where a task lists
  candidate blockers that were later superseded (e.g. T3c originally listed T3b), this
  table reflects the live successor (T3d) instead, since T3d produces the same artifact
  path T3c already expects.
- Follow-up logs (`T1-laya-native-runtime-follow-ups.md`,
  `T3a-host-network-access-decisions-follow-ups.md`) are append-only finding records
  attached to their parent task, not separate board entries.
