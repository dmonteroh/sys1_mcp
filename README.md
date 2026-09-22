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

## Pointers

- `skills/laya-mcp/SKILL.md` — the agent-facing doc: tool contract, transport choice, worked call, latency, traps.
- `.agent/docs/dev-workflows.md` — LAN IP, port, bind address, and firewall decisions.
- `research.md` — the original research brief this setup was built from.
