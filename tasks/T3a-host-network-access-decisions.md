# T3a — Record this node's host-network access decisions for the Laya MCP server

## Description

Author the LAN-IP, port, bind-address, and firewall decisions that T3b and T3c execute, as this node's own knowledge. `research.md` section 3 cites `.agent/docs/dev-workflows/docker-compose.md:44` and `.agent/docs/dev-workflows/gotchas.md:6-7` for a LAN-IP detection pattern and a `localhost` gotcha. Neither path exists in this node: `.agent/docs/` holds `architecture.md` and `sources.md` only, confirmed by `ls` on 2026-09-22. This node is self-contained and does not borrow those files from anywhere else, so the mechanism is derived and verified here instead.

Parent task: T3 (superseded by T3a, T3b, and T3c).

## Source material

- `research.md` (repo root), section 3 — the two dangling citations this task replaces, and the rejected in-container alternative.
- `.agent/rules/contract.md`, Project guardrails — the docs layout this new file must follow.
- `.agent/docs/architecture.md` — the routing table that gains a row for the new doc.

## Acceptance Criteria

- Create `.agent/docs/dev-workflows.md` with `.agent/scripts/docs.sh new`, carrying its own one-line `<!-- Read when: … -->` hook.
- Record the LAN-IP detection command as a command, not a script. Primary form: `ipconfig getifaddr en0`. Fallback form for a host whose active interface is not `en0`: `ipconfig getifaddr "$(route -n get default | awk '/interface:/{print $2}')"`.
- Mark the LAN-IP technique's provenance as derived and verified on this host, not carried in from any external repository or doc.
- Record the verification observed on 2026-09-22: default interface `en0`, gateway `192.0.2.1`, host address `192.0.2.10`. State that the address is DHCP-assigned and is re-read by command at use time, never hardcoded into a config.
- Record port `8765` as a chosen default with its reason: `fastmcp`'s own default of `8000` collides with ad-hoc dev servers, and `lsof -nP -iTCP:8765 -sTCP:LISTEN` found nothing listening on this host on 2026-09-22.
- Record bind address `0.0.0.0` as a chosen default with its reason: it survives a DHCP lease change, and the client connects by the LAN IP read at use time.
- Record the residual exposure of that bind: an unauthenticated MCP server is reachable by any host on the LAN while it runs. Record the mitigation: start it only for the duration of a session, and do not install it as a `launchd` service.
- Record the firewall posture as reactive: attempt the connection first, and add a macOS firewall or Little Snitch rule only after a connection is refused.
- Record the rejected alternative: a second Laya MCP server running CPU-only inside a container, `research.md` section 3 option 2. Reason: the Podman VM on macOS has no Metal or Neural-Engine passthrough.
- Record the `localhost` constraint as this node's own finding, unverified here: a client inside a container must not reach this host by `localhost`, `127.0.0.1`, or `host.docker.internal`. Mark it `(inferred)` until T3c tests it.
- Add the doc's row to `.agent/docs/architecture.md`, with the hook text matching the doc's own header and a `Sections:` list matching its `## ` headings.
- State in the doc that `research.md` section 3's two cited paths resolve to nothing in this node, and that this doc supersedes them as the source for these decisions. Do not edit or delete the `research.md` text itself.

## Implementation Constraints

**Reference pattern.** Numbers and defaults carry stated provenance (`.agent/rules/contract.md`, Knowledge discipline). Each value above is either measured on this host on 2026-09-22 or labelled a chosen default with its reason.

**Self-containment.** Do not read, cite, list, or depend on any path outside this repository and this Mac host. The LAN-IP command is general macOS system behaviour, attributed to this node's own derivation.

**Negative scope.**
- No script, no `local_ip.sh`, no Makefile, and no executable of any kind. This node has no build surface, and one command does not earn one.
- No server is installed, started, or bound. T3b and T3c own execution.
- No row in `.agent/docs/sources.md`. Nothing external is ingested here.
- No edit to `research.md`, and no deletion of its dangling citations. The contradiction is flagged in the new doc, both versions kept.
- No devcontainer, `Dockerfile`, or compose file added to this repository.

**Deployment context.** Documentation only, on the Apple Silicon Mac host. Nothing runs.

**Playbook.**
1. Re-run `ipconfig getifaddr en0` and `route -n get default` and confirm the recorded interface and address still hold. Record the observed values.
2. Re-run `lsof -nP -iTCP:8765 -sTCP:LISTEN` and confirm nothing is listening.
3. Create the doc with `.agent/scripts/docs.sh new` and write the decisions above, one fact per line.
4. Add the routing row to `.agent/docs/architecture.md` and confirm the hook text matches the doc header.
5. Run `bash .agent/scripts/status.sh` and clear any hook or `Sections:` drift it reports.

## Sizing Budget

- Concern axes: 1 — authoring one knowledge doc and its routing row. within-target.
- Acceptance criteria: 12 (recounted from the Acceptance Criteria list; corrected from an earlier miscount of 13). At the target-8/cap-12 boundary, not over it — kept together because each line is one recorded value in one file, not a separate piece of work.
- Estimated file touch count: 2 — `.agent/docs/dev-workflows.md`, `.agent/docs/architecture.md`. within-target.
- Independent failure classes: 1 — doc and routing-table consistency, which `status.sh` checks. within-target.
- Read scope: 3 local files, largest `research.md` at 53 lines. within-target.

## Execution Gates

- Blocked by: nothing. T2a and T2b do not gate a documentation task.
- Order constraints: before T3c, which reads the recorded port and LAN-IP command. Independent of T3b.
- Dispatchability: dispatchable now.
- Follow-up tasks: T3c, which stamps the verified outcome onto this doc.
- Claims: files — `tasks/T3a-host-network-access-decisions.md`, `.agent/docs/dev-workflows.md`, `.agent/docs/architecture.md`. Non-file — read-only host commands (`ipconfig`, `route`, `lsof`). No process is started, no port is bound, no package is installed. No credential claims.
- Verification commands:
  - `["test", "-f", ".agent/docs/dev-workflows.md"]`
  - `["grep", "-q", "Read when:", ".agent/docs/dev-workflows.md"]`
  - `["grep", "-q", "dev-workflows.md", ".agent/docs/architecture.md"]`
  - `["grep", "-q", "8765", ".agent/docs/dev-workflows.md"]`
  - `["grep", "-q", "0.0.0.0", ".agent/docs/dev-workflows.md"]`
  - `["grep", "-q", "ipconfig getifaddr", ".agent/docs/dev-workflows.md"]`
  - `["bash", "-c", "! ls .agent/docs/dev-workflows/ 2>/dev/null"]`
  - `["bash", "-c", "! grep -rn 'CLIENT' .agent/docs/dev-workflows.md"]`
  - `["bash", "-c", "bash .agent/scripts/status.sh | grep -q 'GROOM:.*dev-workflows' && exit 1 || exit 0"]`
  - `["bash", "-c", "git diff --name-only -- research.md | grep -q . && exit 1 || exit 0"]`
  - Manual: the doc names no path outside this repository and no other repository.
  - Manual: every number in the doc carries a measured date or a chosen-default reason.
