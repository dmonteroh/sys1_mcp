> **Status: superseded-by-children.** Split by architect review (2026-09-22) — 5+ independent failure classes vs. cap 2, plus a hard requirement (operator decision, 2026-09-22) that this project stay self-contained and not depend on any other repository. Replaced by [T3a](T3a-host-network-access-decisions.md) (record LAN-IP/port/bind/firewall decisions), [T3b](T3b-mcp-http-transport-loopback.md) (confirm/patch HTTP transport, verify on loopback), and [T3c](T3c-lan-bind-container-reachability.md) (bind on LAN IP, verify from a disposable Podman container — no devcontainer, no other repo). This file is retained for background only and is not dispatchable.

# T3 — Make the Laya MCP server reachable from devcontainer agents

## Description

Host-native agents can already reach a stdio MCP server directly (T2). Devcontainer agents cannot, because stdio does not cross the container boundary. Research (research.md, section 3) recommends switching the T2 server to a network transport (`fastmcp` supports `streamable-http`) bound to the Mac host's LAN IP, reusing this project's existing LAN-IP detection pattern (`local_ip.sh` / `MOBILE_HOST`, referenced at `.agent/docs/dev-workflows/docker-compose.md:44`), and explicitly avoids `localhost`/`127.0.0.1`/unverified `host.docker.internal` per an existing project gotcha (referenced at `.agent/docs/dev-workflows/gotchas.md:6-7`).

## Source material

- `research.md` (repo root), section "3. Reaching the MCP server from both host-native and devcontainer agents".
- T2's setup note for the concrete server/CLI this wires a transport onto.

## Known blocker (surfaced before this task starts)

`research.md` cites `.agent/docs/dev-workflows/docker-compose.md` and `.agent/docs/dev-workflows/gotchas.md` for the LAN-IP detection pattern and the localhost gotcha. Neither file exists in this repository as of bootstrap (2026-09-22) — `.agent/docs/` currently contains only `architecture.md` and `sources.md`. This must be resolved (find the real pattern elsewhere, or confirm it needs to be authored) before this task can rely on it.

## Acceptance Criteria

- Resolve the missing-source-doc blocker above: locate the actual LAN-IP detection mechanism this project uses (if any exists yet) or document that none exists.
- Confirm whether the T2 server's actual CLI already exposes an HTTP/`streamable-http` transport flag; patch it in only if genuinely missing, scoped to that flag alone.
- Run the server bound to the host LAN IP on a fixed port.
- Verify a client from inside the devcontainer can reach it over `http://<host-LAN-IP>:<port>/mcp` and complete a real tool call.
- Confirm the CPU-only in-container alternative (option 2 in research.md) is out of scope for this task per the research recommendation, and do not implement it.

## Open items flagged by research (not yet resolved)

- Fixed port choice, and whether firewall/Little Snitch allowances are needed on macOS for LAN-bound traffic from the Podman VM, are undecided.
