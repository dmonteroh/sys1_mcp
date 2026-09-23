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

MCP endpoint: `https://localhost:8765/mcp` (see TLS below).

The daemon also serves `POST /predict`, outside the MCP protocol, taking `{"text": ..., "schema": ...}` and returning the raw answer. It exists so a stdio `laya-mcp` process pointed at `LAYA_DAEMON_URL` reuses this warm model rather than loading its own (`laya-mcp/src/laya_mcp/daemon.py` `predict`). It returns 503 while the agent loads and 400 on a malformed body.

`GET /health` names the checkpoint it serves, so a swap is confirmed with one request instead of by reading source:

```
$ curl -s https://localhost:8765/health
{"status":"ok","default_route":"english",
 "routes":{"english":{"checkpoint":"aac6fef/laya-mlx","limits":{"max_len":512,"head_max_len":192},"route":"english"},
           "typed-decisions":{"checkpoint":"aac6fef/laya-typed-decisions-mlx","limits":{"max_len":1024,"head_max_len":256},"route":"typed-decisions"}},
 "checkpoint":"aac6fef/laya-mlx","limits":{"max_len":512,"head_max_len":192},"route":"english"}
```

`routes` lists every resident checkpoint; the flat `checkpoint` / `limits` / `route` keys repeat the default route's figures so a probe written against the single-checkpoint shape keeps working. It reports `{"status":"loading","routes":...}` with 503 until the eager load finishes.

### Two checkpoints, chosen per call

The daemon holds both resident and `laya_ask` takes an optional `checkpoint`: `base` for judging the content of a text (screening, injection detection, classification), `typed-decisions` — the default — for judging an agent's own state and for input over 512 tokens. `/health` also lists the tool's argument and response keys, so a client holding a stale cached tool list is diagnosable with one request rather than looking like a routing bug. Measurement behind the split is in `tmp/tasks/notes/T13-dual-checkpoint-routing.md`.

### Tools

| Tool | For | Design record |
|---|---|---|
| `laya_ask` | any closed question about one text | `tmp/tasks/notes/T2c-design.md` |
| `laya_classify` | one schema over up to 256 texts, batched | `tmp/tasks/notes/T10-classify-batching.md` |
| `laya_screen` | untrusted text, chunked so nothing is truncated, on the `english` route | `tmp/tasks/notes/T9-screen-calibration.md` |
| `laya_health` | loaded checkpoints, snapshots, budgets, and a timed probe | `tmp/tasks/notes/T8-health-tool-verification.log` |

When a new tool is justified is set in `tmp/tasks/notes/T7-tool-surface.md`. Every tool besides `laya_ask` reaches the daemon over the existing `/predict` route as `{"tool", "arguments"}`, so a stdio client gets all four on the warm models.

Env vars, with their code defaults (`laya-mcp/src/laya_mcp/server.py`, `laya-mcp/src/laya_mcp/daemon.py`):

| Var | Default | Meaning |
|---|---|---|
| `LAYA_CHECKPOINT_ENGLISH` | `aac6fef/laya-mlx` | repo for the `english` route |
| `LAYA_CHECKPOINT_TYPED_DECISIONS` | `aac6fef/laya-typed-decisions-mlx` | repo for the `typed-decisions` route |
| `LAYA_ROUTE_DEFAULT` | `typed-decisions` | which route answers a call that names none |
| `LAYA_PRELOAD` | `1` | build every route at startup; `0` builds only the default |
| `LAYA_CHECKPOINT` | unset | **deprecated** — it names no route, so it is applied to the default route and logged as a warning |
| `LAYA_DAEMON_URL` | unset | when set, forward each call to `<url>/predict` before falling back to a local load on failure |
| `LAYA_MCP_HOST` | `127.0.0.1` | bind host for the HTTP listener |
| `LAYA_MCP_PORT` | `8765` | bind port for the HTTP listener |
| `LAYA_MCP_TLS_CERT` | unset | PEM certificate; with `LAYA_MCP_TLS_KEY`, serves HTTPS instead of HTTP |
| `LAYA_MCP_TLS_KEY` | unset | PEM private key; must be set together with `LAYA_MCP_TLS_CERT` |

For LAN IP, port choice, bind address, and firewall posture, see `.agent/docs/dev-workflows.md` — this file always uses the loopback defaults above.

### TLS

The installed LaunchAgent serves HTTPS, not HTTP, because Claude Desktop rejects an `http://` MCP URL.
There is no reverse proxy: `FastMCP.run()` forwards `uvicorn_config` into `uvicorn.Config` (fastmcp 4.0.5, `run_http_async`), which takes `ssl_certfile` and `ssl_keyfile`, so the daemon terminates TLS itself (`laya-mcp/src/laya_mcp/daemon.py` `_tls_config`).

- Cert and key: `~/.config/laya-mcp/tls/laya-mcp.pem` and `laya-mcp-key.pem`, outside the repo. The key is never committed.
- Issued by `mkcert`, whose root CA was already installed in this host's System keychain (`~/Library/Application Support/mkcert`, dated Oct 2024), so anything using the macOS trust store trusts it with no `-k` and no per-app configuration.
- Names on the cert: `localhost`, `127.0.0.1`, `::1`, `my-mac.local`, `192.0.2.10`. It expires 2028-12-22.
- Prefer `my-mac.local` over the IP for LAN clients: the IP is DHCP-assigned and re-minting the cert is the only way to follow a lease change.
- Re-mint with `mkcert -cert-file laya-mcp.pem -key-file laya-mcp-key.pem localhost 127.0.0.1 ::1 my-mac.local <LAN-IP>` from that directory.
- Both variables must be set together. A half-set pair or a missing file exits with a message rather than silently falling back to plain HTTP, and the whole environment is validated before the model load, so a typo fails in under a second.
- Unset both to go back to plain HTTP.

Verified on this host on 2026-09-22: `curl` without `-k` returned `{"status":"ok"}` and 200 from `https://localhost:8765/health`, `https://my-mac.local:8765/health`, and `https://192.0.2.10:8765/health`, and plain `http://localhost:8765/health` returned `000` — one listener, HTTPS only.

## Checking it is up

`/health` reports 503 while the model is still loading, and 200 once it is ready.
The agent load happens eagerly, before the listener accepts connections, so an immediate probe right after the `nohup` start command above returned `HTTP_STATUS:000` (connection refused — nothing bound yet):

```
$ curl -s -w '\nHTTP_STATUS:%{http_code}\n' https://localhost:8765/health

HTTP_STATUS:000
```

Once the listener is up, `/health` is already `ok` — the 503-loading window closes before the port binds, so it was not caught live this run either:

```
$ curl -s -m 60 -w '\nHTTP_STATUS:%{http_code}\n' https://localhost:8765/health
{"status":"ok"}
HTTP_STATUS:200
```

No `-k` and no `--cacert`: the mkcert root CA is in the System keychain, so `curl` verifies the chain on its own (verified 2026-09-22).

Confirm the listener directly:

```
$ lsof -nP -iTCP:8765 -sTCP:LISTEN
COMMAND   PID           USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
Python  46379 USERNAME   11u  IPv4 0x309240abe5654af8      0t0  TCP *:8765 (LISTEN)
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

## Restarting and warming

`laya-mcp/scripts/restart-warm.sh` restarts the LaunchAgent, waits for `/health` to return 200, then sends one `laya_ask` call per question type (`choice`, `score`, `noul`) plus one batched call of all three on each route, then one `laya_screen`, one `laya_classify` per route and one `laya_health`, so the first real call does not pay a Metal-kernel compile (see `skills/laya-mcp/SKILL.md`'s Traps, where each distinct schema shape pays its own one-time compile).

```
$ ./laya-mcp/scripts/restart-warm.sh
restarting com.ld-mcp.laya-mcp-http
waiting for https://localhost:8765/health... ok
warming schema shapes
  choice                 ok (0s)
  score                  ok (0s)
  noul                   ok (0s)
  choice+score+noul      ok (0s)
laya-mcp is up and warm at https://localhost:8765/mcp
```

Observed on this host on 2026-09-22: 4.0 s wall clock end to end, of which about 3 s is the restart and eager model load.

Flags and env vars:

| Flag | Env var | Default | Meaning |
|---|---|---|---|
| `--warm-only` | — | off | skip the restart; only wait for health and warm a server that is already up |
| `--url URL` | `LAYA_MCP_URL` | `https://localhost:8765` | server base URL |
| `--timeout SECONDS` | `LAYA_MCP_HEALTH_TIMEOUT` | `120` | how long to wait for `/health` to return 200 |

Restart behaviour: it runs `launchctl kickstart -k gui/$(id -u)/com.ld-mcp.laya-mcp-http` when the agent is loaded, falls back to `launchctl bootstrap` from `~/Library/LaunchAgents/com.ld-mcp.laya-mcp-http.plist` when it is not, and exits 1 with instructions when neither applies. It exits 1 on a health timeout or a failed warm-up call, printing the server's own error.

### Identity check

After warming, the script runs `laya-mcp/scripts/check-identity.py`. It compares what the daemon serves against `laya-mcp/deploy/identity.lock.json`: per route, the checkpoint, the Hugging Face snapshot, the sha256 of `rl_agent_config.json` (every calibration temperature) and the token limits, plus the `laya_mlx` version and the default route. On any difference it names the field and exits 1, and the server stays up. Every figure measured against this server, in the skill and in `tmp/tasks/notes/`, holds only for the locked identity. After an intended checkpoint, config or runtime change, re-measure what depends on it, then record the new identity:

```
$ python3 laya-mcp/scripts/check-identity.py --write
```

The response's `model` field is a runtime constant (`laya-rl-agent`) on every checkpoint, so the check never reads it. Design: `tmp/tasks/notes/T11-calibration.md` §6.

To restart by hand without the script:

```
$ launchctl kickstart -k gui/$(id -u)/com.ld-mcp.laya-mcp-http
```

## Resource cost

Every figure below is one host's single-sample observation, not a benchmark
(`tmp/tasks/notes/T5-resource-profile.md`):

- ~38 MiB (39008 KiB) — idle `ps` RSS, persistent LaunchAgent, after a 67 s idle wait (`tmp/tasks/notes/T5-resource-profile.md` §3).
- 0.1 — idle `ps` `%CPU` (lifetime average, not a short-interval sample) (`tmp/tasks/notes/T5-resource-profile.md` §3).
- ~107 MiB (109920 KiB) — `ps` RSS immediately after one `laya_ask` call, a delta of +69.25 MiB over idle (`tmp/tasks/notes/T5-resource-profile.md` §4).
- ~41 MiB (42192 KiB) — post-load idle re-sample RSS after another 67 s wait, only +3.11 MiB above the original idle figure (`tmp/tasks/notes/T5-resource-profile.md` §5).
- `top -l 1`'s `MEM`/`rsize` reads far higher than `ps`'s `rss` at every sample (923M idle, 1002M after the call) — the two tools disagree by design, `ps`'s `%cpu` is a lifetime average while `top -l 1`'s is a short-interval sample (`tmp/tasks/notes/T5-resource-profile.md` §3, §6, §7).
- `laya-mlx` runs on Metal via unified memory, so some model memory may sit outside the measured `rss`/`rsize` figures entirely — these are a lower bound, not a full accounting (`tmp/tasks/notes/T5-resource-profile.md` §7).
- Full commands and verbatim `ps`/`top` output live in `tmp/tasks/notes/T5-resource-profile.md`.

Re-measured 2026-09-22 on `aac6fef/laya-typed-decisions-mlx`, against the live LaunchAgent, sampling the pid `launchctl print` reports:

| Point | `ps` `rss` | `footprint` `phys_footprint` |
|---|---|---|
| idle, agent loaded, no calls served | 976 MB | 920 MB |
| after 14 warm calls across all three question types | 992 MB | 1389 MB |
| peak during the first-ever start (download plus load) | 1051 MB | 1368 MB |

Contradiction, kept per the contradiction-handling rule rather than overwritten: the T5c figures above report ~38-41 MiB idle `rss` for the same service, and these report ~976 MB. Both are recorded as observed. The T5c number cannot be a loaded 421M-parameter model in memory, and the daemon loads eagerly before it listens, so the likely explanation is that T5c sampled a different pid — but that was not re-derived here, so it is inference, not a finding. Prefer these figures and re-verify the pid before trusting either.

Holding both checkpoints resident, measured 2026-09-22 against the live LaunchAgent:

| | One checkpoint | Both resident |
|---|---|---|
| cold start to `/health` 200, cached | 3379 ms | 4202 ms |
| idle `rss` | 976 MB | 1788 MB |
| idle `phys_footprint` | 920 MB | 1735 MB |

The second checkpoint costs about 815 MB and 820 ms.

MLX keeps freed Metal buffers in a cache that is unbounded by default, and every batch shape leaves its own. Before a cap existed, measured 2026-09-23: 8,457 MB `phys_footprint` after a round of mixed calls, and 11 GB after one 256-item `laya_classify`. The server now caps the cache at 512 MiB (`laya-mcp/src/laya_mcp/server.py` `MLX_CACHE_LIMIT_BYTES`). With the cap, the footprint was 2,341 MB after restart and warm-up and 2,348 MB after two 256-item batches, with no change in speed (`tmp/tasks/notes/T10-classify-batching.md`). Set `LAYA_PRELOAD=0` to build only the default route and pay the other one's load on first use instead.

Startup cost, single-checkpoint run:

- 3379 ms — restart to `/health` 200 with the checkpoint already cached.
- 409 s — first-ever start, dominated by downloading `model.safetensors` (842,609,225 bytes) at roughly 2-3 MB/s. Paid once per checkpoint per machine, not per restart.
- 33-41 ms (median 36) — warm loopback HTTPS MCP `tools/call`, same schema shape, 10 consecutive runs.

## Applying a plist change

`launchctl kickstart -k` restarts the process but launchd keeps the job definition it bootstrapped, so an edited `EnvironmentVariables` block is not picked up and the server keeps serving the old configuration while the file on disk says otherwise.

```
$ ./laya-mcp/scripts/restart-warm.sh --reload
```

`--reload` boots the job out and back in, waits for `/health`, then warms every route. Confirm the change landed by reading it back rather than trusting the file:

```
$ curl -s https://localhost:8765/health | python3 -c 'import sys,json;print(json.load(sys.stdin)["default_route"])'
```

## Registering with an MCP client

The server exposes a single MCP endpoint over `streamable-http` at `/mcp` (suggested name `laya-mcp`, URL shape `https://<hostname or LAN name>:8765/mcp`), with no auth of any kind implemented.
Use a name the certificate covers — `localhost` on this host, `my-mac.local` from the LAN — or TLS verification fails. The cert also covers the current LAN IP, but that IP is DHCP-assigned; see TLS above before hardcoding it anywhere.

### Claude Desktop

Claude Desktop cannot reach this server by URL at all. Its "Add custom connector" flow is for remote MCP servers: the connection is made from Anthropic's side, not from this machine, so `localhost`, `127.0.0.1`, and `0.0.0.0` there resolve on their host and never arrive here — which is also why it insists on HTTPS. Verified on 2026-09-22: across several attempts at all three addresses, the daemon's access log recorded zero inbound requests and Claude Desktop's own logs never mention port 8765. The app reports "No server responded at this URL", or later "Couldn't reach laya-mcp" with an `ofid_…` support reference.

Register it as a local stdio server instead, in `~/Library/Application Support/Claude/claude_desktop_config.json`, then quit and reopen the app:

```json
{
  "mcpServers": {
    "laya-mcp": {
      "command": "/Users/USERNAME/.venvs/laya-mlx-t1/bin/laya-mcp",
      "env": {
        "LAYA_DAEMON_URL": "https://localhost:8765",
        "SSL_CERT_FILE": "/Users/USERNAME/Library/Application Support/mkcert/rootCA.pem"
      }
    }
  }
}
```

`LAYA_DAEMON_URL` makes that stdio process forward each call to the running daemon's `/predict` route, so it borrows the warm model instead of loading a second copy into RAM.
`SSL_CERT_FILE` is required with it: the forwarding client is `httpx`, which verifies against certifi's bundle and not the macOS keychain, so without it every call fails TLS and silently falls back to a local load — visible only as a `logging.warning` (`laya-mcp/src/laya_mcp/server.py` `_predict`).

Verified on this host on 2026-09-22, two calls through a stdio client with both variables set: 0.32 s then 0.03 s, two matching `POST /predict` 200s in the daemon's log, and no fallback warning. The same client without `SSL_CERT_FILE` logged `CERTIFICATE_VERIFY_FAILED`, hit the daemon zero times, and took 1.42 s. Without `LAYA_DAEMON_URL` at all it loads its own model: 0.94 s then 0.02 s.

### Claude Code

Project-scoped MCP servers go in a `.mcp.json` file (or via `claude mcp add --transport http laya-mcp <url>`):

```json
{
  "mcpServers": {
    "laya-mcp": {
      "type": "http",
      "url": "https://localhost:8765/mcp"
    }
  }
}
```

### Codex CLI

Codex reads `~/.codex/config.toml`, under an `[mcp_servers.<name>]` table with a `url` key for `streamable_http` servers:

```toml
[mcp_servers.laya-mcp]
url = "https://localhost:8765/mcp"
default_tools_approval_mode = "approve"
```

Without `default_tools_approval_mode`, Codex asks before every call, and `codex exec` fails the call outright ("MCP tool call requires approval, but approval policy is never"). Every Laya tool is local and read-only, so auto-approving this one server is safe. Key found in the Codex 0.155.1 binary's config schema; accepted values are `auto`, `prompt`, `writes`, `approve`.

No block above needs a bearer token or auth header — this server has no auth, so there is nothing to configure for any client.
These are the documented config shapes for each client. Claude Code is registered at user scope, so every repo on this machine sees the tool: `claude mcp add --scope user --transport http laya-mcp https://localhost:8765/mcp`, and `claude mcp list` reports it connected with no extra CA configuration (verified 2026-09-23). The agent skill is linked at user scope as well, as `~/.claude/skills/laya-mcp` → `skills/laya-mcp`. Codex is registered too, with `codex mcp add laya-mcp --url https://localhost:8765/mcp` plus the approval key above, and its skill is linked as `~/.codex/skills/laya-mcp` → `skills/laya-mcp`. Verified 2026-09-23: a `codex exec` run called `laya_ask` and got `served_by: local` from `aac6fef/laya-typed-decisions-mlx`, with no extra CA configuration. No `.mcp.json` exists.

## Pointers

- `skills/laya-mcp/SKILL.md` — the agent-facing doc: which tool to use, the question contract, how to write questions, screening, and pitfalls.
- `.agent/docs/dev-workflows.md` — LAN IP, port, bind address, and firewall decisions.
- `laya-mcp/deploy/com.ld-mcp.laya-mcp-http.plist` — the persistent LaunchAgent configuration.
- `laya-mcp/scripts/restart-warm.sh` — restart the LaunchAgent and warm every question type.
- `laya-mcp/scripts/check-identity.py` and `laya-mcp/deploy/identity.lock.json` — the served-identity lock and its check.
- `research.md` — the original research brief this setup was built from.
