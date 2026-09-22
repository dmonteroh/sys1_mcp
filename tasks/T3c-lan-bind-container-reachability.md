# T3c — Bind the MCP server on the LAN IP and prove a container can reach it

## Description

Bind the server T3b proved on loopback to `0.0.0.0:8765`. Then prove a process inside a container reaches it at `http://<host-LAN-IP>:8765/mcp`. The client is a disposable container started by `podman run --rm` from a generic public base image. This task creates it and destroys it. It plays the role T3's original brief gave a devcontainer: a process that cannot use stdio or `localhost` to reach this Mac host.

This node has no devcontainer and does not gain one. The `podman` machine is host-level tooling already installed on this Mac, verified running on 2026-09-22 as `podman-machine-default` on the `applehv` VM type. Using it adds no project infrastructure: no `Dockerfile`, no compose file, no `devcontainer.json`, and no image built or kept.

Parent task: T3 (superseded by T3a, T3b, and T3c).

## Source material

- `tasks/notes/T3-transport.md` — the verified `streamable-http` invocation T3b recorded, and whether the transport flag was patched.
- `.agent/docs/dev-workflows.md` — the LAN-IP command, the port, the bind address, and the firewall posture T3a recorded.
- `tasks/notes/T2-setup.md` — the daemon start command, background only.

## Acceptance Criteria

- Confirm `tasks/notes/T3-transport.md` exists and records a real tool call over `http://127.0.0.1:8765/mcp`. If not, stop and report blocked without binding anything.
- Read the host LAN IP with the command `.agent/docs/dev-workflows.md` records. Record the value observed at run time. Do not hardcode it into any config.
- Start the server with `streamable-http` bound to `0.0.0.0` on port `8765`. Record the exact command and its real startup output.
- Confirm the listener accepts the LAN address with `lsof -nP -iTCP:8765 -sTCP:LISTEN`, and record the output.
- Confirm from the host that `http://<host-LAN-IP>:8765/mcp` answers, using the LAN IP and not `localhost`. Record the response.
- Start a disposable container with `podman run --rm` from a generic public base image on the default bridge network. From inside it, complete one real end-to-end tool call against `http://<host-LAN-IP>:8765/mcp`. Record the full command, the request, the response, and the observed latency.
- Confirm inside that same container that `http://localhost:8765/mcp` and `http://127.0.0.1:8765/mcp` do not reach the host server. Record the observed failure. This converts `.agent/docs/dev-workflows.md`'s `(inferred)` `localhost` constraint into a verified one.
- Confirm the container is gone after the run with `podman ps -a`, and that no image was built and none was left behind by this task.
- Apply the reactive firewall posture: add a macOS firewall or Little Snitch rule only after a connection is actually refused. Record whether a rule was needed, and the exact rule if one was added.
- Stop the server and confirm port `8765` is released.
- Record every command and its real output in `tasks/notes/T3-reachability.md`.
- Update `.agent/docs/dev-workflows.md`: change the chosen-default labels on the port and bind address to verified with this date, and change the `localhost` constraint from `(inferred)` to verified with the observed failure. Change no other content there.

## Implementation Constraints

**The end-to-end call must hit the real runtime.** The response must come from the Laya checkpoint loaded through T1's runtime. A stub, mock, fixture, or canned response does not satisfy the criterion.

**The container must not share the host network.** Do not pass `--network host`. The default bridge network is what makes this a cross-boundary test.

**Container image.** Use `docker.io/library/node:24.20-slim` and Node's built-in `fetch`, which needs no package installed inside the container. If that image is unavailable, use `docker.io/library/debian:bookworm-slim` and install `curl` inside the disposable container. Both are generic public base images and neither belongs to any project.

**Self-containment.** Do not read, cite, list, or depend on any path outside this repository and this Mac host. Do not use, copy, or reference any existing devcontainer on this machine.

**Degraded outcome.** If the disposable container will not start at all, record the host-side LAN-IP check as a partial pass. State the untested residual risk in plain terms: Podman VM routing from a container to this host stays unproven. Report the cross-boundary criterion blocked. Do not report the task passed.

**Reference pattern.** No command is presented as verified until it has actually been run and its output checked (`.agent/rules/contract.md`, Output conventions).

**Negative scope.**
- No `Dockerfile`, compose file, `devcontainer.json`, or built image added to this repository or left on this host.
- No second Laya MCP server inside the container. `research.md` section 3 option 2 stays rejected: the Podman VM has no Metal or Neural-Engine passthrough.
- No `launchd` service, login item, or other persistence for the server. It runs for this task and stops.
- No patch to the fork. T3b settled the transport flag.
- No pre-emptive firewall rule.
- No `.agent/` writes beyond the two labelled updates to `.agent/docs/dev-workflows.md`.

**Deployment context.** The server runs natively on the Apple Silicon Mac host. The client runs inside a throwaway Podman container on the same machine. Binding `0.0.0.0` makes an unauthenticated MCP server reachable by any host on the LAN while it runs, which is why it stops at the end of the task.

**Playbook.**
1. Check `tasks/notes/T3-transport.md` records a real loopback tool call. Stop if not.
2. Read the LAN IP with the recorded command and note the value.
3. Start the daemon, then start the MCP server on `0.0.0.0:8765`. Capture the output.
4. Run `lsof -nP -iTCP:8765 -sTCP:LISTEN` and capture the output.
5. From the host, request `http://<host-LAN-IP>:8765/mcp` and capture the response.
6. Run the disposable container on the default bridge network and make one real tool call to `http://<host-LAN-IP>:8765/mcp`. Capture the request, the response, and the latency.
7. In the same container run, attempt `http://localhost:8765/mcp` and `http://127.0.0.1:8765/mcp` and capture both failures.
8. If any connection was refused, add the narrowest firewall rule that clears it, then repeat the failing step and record the result.
9. Stop the server. Confirm the port is released and `podman ps -a` shows no leftover container.
10. Write `tasks/notes/T3-reachability.md`, then apply the two labelled updates to `.agent/docs/dev-workflows.md`.

## Sizing Budget

- Concern axes: 2 — binding on the LAN address including the firewall posture, and reachability from inside a container. At cap, not over: a bind nothing can reach proves nothing, so splitting them would push a live listener across a task boundary.
- Acceptance criteria: 12. Above the count a two-axis task usually carries, kept together because eight of them are single recorded observations of one live server run.
- Estimated file touch count: 2 — `tasks/notes/T3-reachability.md`, `.agent/docs/dev-workflows.md`. within-target.
- Independent failure classes: 2 — the host side refuses the LAN bind or blocks the port, and the container side cannot route to the host. At cap.
- Read scope: 3 local files, largest `tasks/T3c-lan-bind-container-reachability.md`. within-target.

## Execution Gates

- Blocked by: T3a (`.agent/docs/dev-workflows.md` recording the LAN-IP command, port, and bind address) and T3b (`tasks/notes/T3-transport.md` recording a real loopback tool call).
- Order constraints: last of the T3 children. After T3a and T3b, both of which must be complete.
- Dispatchability: blocked.
- Follow-up tasks: none. This closes T3.
- Claims: files — `tasks/T3c-lan-bind-container-reachability.md`, `tasks/notes/T3-reachability.md`, `.agent/docs/dev-workflows.md`. Non-file — binds a LAN-reachable TCP listener on `0.0.0.0:8765` for the duration of the task, starts a long-lived local daemon, starts and destroys one throwaway Podman container, and may add one macOS firewall rule. No credential claims.
- Claim overlap: `.agent/docs/dev-workflows.md` is also claimed by T3a. The two never run at the same time, because T3a gates this task.
- Verification commands:
  - `["test", "-f", "tasks/notes/T3-transport.md"]`
  - `["test", "-f", "tasks/notes/T3-reachability.md"]`
  - `["grep", "-q", "0.0.0.0:8765", "tasks/notes/T3-reachability.md"]`
  - `["grep", "-Eq", "podman run --rm", "tasks/notes/T3-reachability.md"]`
  - `["bash", "-c", "! grep -q 'network host' tasks/notes/T3-reachability.md"]`
  - `["bash", "-c", "! grep -Eiq 'CLIENT|devcontainer.json|Dockerfile' tasks/notes/T3-reachability.md"]`
  - `["bash", "-c", "! test -e .devcontainer && ! test -e Dockerfile && ! test -e docker-compose.yml"]`
  - `["bash", "-c", "! lsof -nP -iTCP:8765 -sTCP:LISTEN | grep -q LISTEN"]`
  - `["bash", "-c", "! grep -q 'inferred' .agent/docs/dev-workflows.md || echo 'WARN: an inferred label remains — confirm it is not the localhost constraint'"]`
  - Manual: the note shows a real request and a real model-produced response made from inside the container, with an observed latency figure.
  - Manual: the note shows both `localhost` and `127.0.0.1` failing from inside that same container.
  - Manual: `podman ps -a` and `podman images` show no container and no image left by this task.
  - Manual: the LAN IP in the note matches what the recorded command returns now, or the note explains the DHCP change.
