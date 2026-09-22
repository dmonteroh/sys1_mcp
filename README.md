# laya-mcp — manual run instructions

`ld_mcp` wraps the Laya typed-decision model and the MCP servers that expose it, on one operator's machine.
This file covers only how to start, check, and stop this project's first-party `laya-mcp` server by hand.
For the original research brief, see `research.md`.
For accumulated setup knowledge, verified facts, and network decisions, see `.agent/`.

## Prerequisites

- Venv: `/Users/USERNAME/.venvs/laya-mlx-t1`.
- Editable install: `uv pip install --python /Users/USERNAME/.venvs/laya-mlx-t1 -e ./laya-mcp`.
- Console-script check:

```
$ ls -la /Users/USERNAME/.venvs/laya-mlx-t1/bin/laya-mcp /Users/USERNAME/.venvs/laya-mlx-t1/bin/laya-mcp-http
-rwxr-xr-x@ 1 USERNAME  staff  325 Sep 22 05:49 /Users/USERNAME/.venvs/laya-mlx-t1/bin/laya-mcp
-rwxr-xr-x@ 1 USERNAME  staff  332 Sep 22 05:49 /Users/USERNAME/.venvs/laya-mlx-t1/bin/laya-mcp-http
```

This covers manual, on-demand runs only. For the agent-facing tool contract, worked call, and traps, see `skills/laya-mcp/SKILL.md`.

## Running over stdio

Entrypoint: `/Users/USERNAME/.venvs/laya-mlx-t1/bin/laya-mcp`, no flags.
It is meant to be spawned as a subprocess by an MCP client, not driven by hand at a prompt.
A single `initialize` handshake, piped in over stdin, confirms it starts and speaks stdio:

```
$ printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t5a-check","version":"0.0.1"}}}\n' | /Users/USERNAME/.venvs/laya-mlx-t1/bin/laya-mcp
[09/22/26 15:10:42] INFO     Starting MCP server 'laya' with transport 'stdio'
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","capabilities":{"logging":{},"prompts":{"listChanged":false},"resources":{"subscribe":false,"listChanged":false},"tools":{"listChanged":true}},"serverInfo":{"name":"laya","version":"4.0.5"}}}
```

## Running over HTTP

Start command:

```
$ nohup /Users/USERNAME/.venvs/laya-mlx-t1/bin/laya-mcp-http > /tmp/laya-mcp-http.log 2>&1 &
started pid 8557
```

MCP endpoint: `http://127.0.0.1:8765/mcp`.

Env vars, with their code defaults (`laya-mcp/src/laya_mcp/server.py`, `laya-mcp/src/laya_mcp/daemon.py`):

| Var | Default | Meaning |
|---|---|---|
| `LAYA_CHECKPOINT` | `aac6fef/laya-mlx` | checkpoint id passed to `laya_mlx.load()` |
| `LAYA_DAEMON_URL` | unset | when set, forward each call to `<url>/predict` before falling back to a local load on failure |
| `LAYA_MCP_HOST` | `127.0.0.1` | bind host for the HTTP listener |
| `LAYA_MCP_PORT` | `8765` | bind port for the HTTP listener |

For LAN IP, port choice, bind address, and firewall posture, see `.agent/docs/dev-workflows.md` — this file always uses the loopback defaults above.

## Checking it is up

`/health` reports 503 while the model is still loading, and 200 once it is ready.
The agent load happens eagerly, before the listener accepts connections, so an immediate probe right after the `nohup` start command above returned `HTTP_STATUS:000` (connection refused — nothing bound yet):

```
$ curl -s -w '\nHTTP_STATUS:%{http_code}\n' http://127.0.0.1:8765/health

HTTP_STATUS:000
```

Once the listener is up, `/health` is already `ok` — the 503-loading window closes before the port binds, so it was not caught live this run either:

```
$ curl -s -m 60 -w '\nHTTP_STATUS:%{http_code}\n' http://127.0.0.1:8765/health
{"status":"ok"}
HTTP_STATUS:200
```

Confirm the listener directly:

```
$ lsof -nP -iTCP:8765 -sTCP:LISTEN
COMMAND  PID           USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
Python  8557 USERNAME   11u  IPv4 0x3fb703db907f5662      0t0  TCP 127.0.0.1:8765 (LISTEN)
```

## Stopping it

Kill the pid recorded at start, then confirm the port is released:

```
$ kill 8557
$ sleep 2
$ lsof -nP -iTCP:8765 -sTCP:LISTEN
(no output)
```

If the pid was not recorded, find it first with `lsof -nP -iTCP:8765 -sTCP:LISTEN` (the `PID` column), then `kill` that value and re-run the same `lsof` command to confirm it prints nothing.

Note: a persistent instance may already be running as a `launchd` LaunchAgent — check
`launchctl print gui/$(id -u)/com.ld-mcp.laya-mcp-http | grep -E 'state|pid'` before starting
a second one. See `laya-mcp/deploy/com.ld-mcp.laya-mcp-http.plist` and
`.agent/docs/dev-workflows.md`'s Bind address section for how that instance is configured and
stopped (`launchctl bootout gui/$(id -u)/com.ld-mcp.laya-mcp-http`).

## Resource cost

Every figure below is one host's single-sample observation, not a benchmark
(`tmp/tasks/notes/T5-resource-profile.md`):

- ~38 MiB (39008 KiB) — idle `ps` RSS, persistent LaunchAgent, after a 67 s idle wait (`tmp/tasks/notes/T5-resource-profile.md` §3).
- 0.1 — idle `ps` `%CPU` (lifetime average, not a short-interval sample) (`tmp/tasks/notes/T5-resource-profile.md` §3).
- ~107 MiB (109920 KiB) — `ps` RSS immediately after one `laya_decide` call, a delta of +69.25 MiB over idle (`tmp/tasks/notes/T5-resource-profile.md` §4).
- ~41 MiB (42192 KiB) — post-load idle re-sample RSS after another 67 s wait, only +3.11 MiB above the original idle figure (`tmp/tasks/notes/T5-resource-profile.md` §5).
- `top -l 1`'s `MEM`/`rsize` reads far higher than `ps`'s `rss` at every sample (923M idle, 1002M after the call) — the two tools disagree by design, `ps`'s `%cpu` is a lifetime average while `top -l 1`'s is a short-interval sample (`tmp/tasks/notes/T5-resource-profile.md` §3, §6, §7).
- `laya-mlx` runs on Metal via unified memory, so some model memory may sit outside the measured `rss`/`rsize` figures entirely — these are a lower bound, not a full accounting (`tmp/tasks/notes/T5-resource-profile.md` §7).
- Full commands and verbatim `ps`/`top` output live in `tmp/tasks/notes/T5-resource-profile.md`.

## Registering with an MCP client

The server exposes a single MCP endpoint over `streamable-http` at `/mcp` (suggested name `laya-mcp`, URL shape `http://<LAN-IP or 127.0.0.1>:8765/mcp`), with no auth of any kind implemented.
Read the current LAN IP live before filling in either block below — see `.agent/docs/dev-workflows.md` for the `ipconfig getifaddr en0` command and the accepted-unauthenticated-exposure decision; do not hardcode an IP here or anywhere else.

### Claude Code

Project-scoped MCP servers go in a `.mcp.json` file (or via `claude mcp add --transport http laya-mcp <url>`):

```json
{
  "mcpServers": {
    "laya-mcp": {
      "type": "http",
      "url": "http://<LAN-IP>:8765/mcp"
    }
  }
}
```

### Codex CLI

Codex reads `~/.codex/config.toml`, under an `[mcp_servers.<name>]` table with a `url` key for `streamable_http` servers:

```toml
[mcp_servers.laya-mcp]
url = "http://<LAN-IP>:8765/mcp"
```

Neither block above needs a bearer token or auth header — this server has no auth, so there is nothing to configure for either client.
These are the documented config shapes for each client; registering a live third client against this server end-to-end is out of scope here.

## Pointers

- `skills/laya-mcp/SKILL.md` — the agent-facing doc: tool contract, transport choice, worked call, latency, traps.
- `.agent/docs/dev-workflows.md` — LAN IP, port, bind address, and firewall decisions.
- `laya-mcp/deploy/com.ld-mcp.laya-mcp-http.plist` — the persistent LaunchAgent configuration.
- `research.md` — the original research brief this setup was built from.
