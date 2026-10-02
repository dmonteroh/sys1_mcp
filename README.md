# sys1-mcp — manual run instructions

`sys1_mcp` is a model-agnostic MCP server for System One decision models, run on one operator's machine. A System One model takes a state and typed questions (`noul`, `choice`, `score`) and returns probabilities instead of text. Laya, Jev and Clef are all System One models. The server's tools never name a model family. Every answer comes from one configured **backend**:

- `laya-mlx` (the default, and what this host runs) holds Laya checkpoints in-process on Apple Silicon.
- `systemone` posts to any `/v1/systemone`-shaped HTTP endpoint: Jev, Clef on Workers AI, a local open server, or this project's own daemon.

This file covers how to configure, start, check, and stop the server by hand.
For the original research brief, see `research.md`.
For accumulated setup knowledge, verified facts, and network decisions, see `.agent/`.

## Prerequisites

- Venv: `/Users/USERNAME/.venvs/laya-mlx-t1`.
- Editable install, with the Laya backend: `uv pip install --python /Users/USERNAME/.venvs/laya-mlx-t1 -e './sys1-mcp[laya]'`. Without `[laya]` only the `systemone` backend is available.
- Console-script check:

```
$ ls -la /Users/USERNAME/.venvs/laya-mlx-t1/bin/sys1-mcp /Users/USERNAME/.venvs/laya-mlx-t1/bin/sys1-mcp-http
-rwxr-xr-x@ 1 USERNAME  staff  325 Oct  2 09:08 /Users/USERNAME/.venvs/laya-mlx-t1/bin/sys1-mcp
-rwxr-xr-x@ 1 USERNAME  staff  332 Oct  2 09:08 /Users/USERNAME/.venvs/laya-mlx-t1/bin/sys1-mcp-http
```

For the agent-facing tool contract, worked call, and traps, see `skills/sys1-mcp/SKILL.md`.

## Choosing a backend

The backend and its models are set by environment variables, read once at startup and validated before any model loads (`sys1-mcp/src/sys1_mcp/backends/`).

Each backend serves one or more named **models**, which callers pass as `model`. Tools with a fixed purpose ask for a **role** instead:

- `content`: judgments about what a text says. `sys1_screen` and call-log redaction use it.
- `trace`: judgments about an agent's own task state. `sys1_relevant` and the four workflow tools use it.

| Var | Default | Meaning |
|---|---|---|
| `SYS1_BACKEND` | `laya-mlx` | `laya-mlx` or `systemone` |
| `SYS1_MODEL_DEFAULT` | backend's own | the model a call without `model` gets |
| `SYS1_MODEL_CONTENT` | backend's own | the model the `content` role uses |
| `SYS1_MODEL_TRACE` | backend's own | the model the `trace` role uses |

### `laya-mlx`

Models are `english` (alias `base`; 512-token budget) and `typed-decisions` (1024-token budget). The default and the `trace` role are `typed-decisions`, and the `content` role is `english`. The measurement behind that split is in `tmp/tasks/notes/T13-dual-checkpoint-routing.md`. Only this backend reports exact per-question truncation, batches many texts into shared forward passes, chunks screening text with the real tokenizer, and pins a snapshot and calibration-config hash for the identity lock.

| Var | Default | Meaning |
|---|---|---|
| `LAYA_CHECKPOINT_ENGLISH` | `aac6fef/laya-mlx` | repo for the `english` model |
| `LAYA_CHECKPOINT_TYPED_DECISIONS` | `aac6fef/laya-typed-decisions-mlx` | repo for the `typed-decisions` model |
| `LAYA_PRELOAD` | `1` | build every model at startup; `0` builds only the default |

### `systemone`

Posts `{"state", "questions", "model"?}` to one endpoint and reads `{"model", "answers", "usage"}` back. That is the Jev API contract (jev-agent.com/api-reference), which Clef also claims. Truncation, limits and `checkpoint` are passed through when the endpoint reports them. This project's daemon reports all three. An endpoint that reports no truncation gets `truncation.checked: false` and `truncated: null`, meaning unknown.

| Var | Default | Meaning |
|---|---|---|
| `SYS1_ENDPOINT` | required | URL to POST to; a literal `{model}` is replaced by the model name |
| `SYS1_API_KEY` | unset | sent as `Authorization: Bearer <key>` |
| `SYS1_MODELS` | unset | comma-separated model names, each sent as `model`; unset serves one model named `default` and sends none |
| `SYS1_CONTEXT_TOKENS` | `8192` | assumed context window, used only to size screening chunks (chosen default, below Jev's 32k and Clef's 64k) |
| `SYS1_TIMEOUT` | `30` | seconds per request |
| `SYS1_CONCURRENCY` | `8` | parallel requests for `sys1_classify` and `sys1_screen` (one request per text) |

Examples. These are unverified until run with real credentials. The Workers AI URL shape is from Cloudflare's model page, read 2026-10-02.

```sh
# Jev
SYS1_BACKEND=systemone SYS1_ENDPOINT=https://jev-agent.com/v1/systemone SYS1_API_KEY=jv_live_...

# Clef on Workers AI: the model is part of the path
SYS1_BACKEND=systemone SYS1_MODELS=clef,clef-flash SYS1_CONTEXT_TOKENS=65536 \
SYS1_ENDPOINT='https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/run/@cf/cloudflare/{model}' \
SYS1_API_KEY=<workers-ai-token>

# This host's own Laya daemon, as a System One endpoint (verified 2026-10-02)
SYS1_BACKEND=systemone SYS1_ENDPOINT=https://localhost:8765/v1/systemone \
SYS1_MODELS=typed-decisions,english SYS1_MODEL_CONTENT=english SYS1_CONTEXT_TOKENS=512
```

Data leaves the machine on a remote backend: every state, screened page and logged-text redaction probe is sent to the endpoint. Swapping backends also invalidates every figure measured here. The screening AUCs, the 11-label calibration warning and the default thresholds were all measured on Laya.

## Running over stdio

Entrypoint: `/Users/USERNAME/.venvs/laya-mlx-t1/bin/sys1-mcp`, no flags.
It is meant to be spawned as a subprocess by an MCP client, not driven by hand at a prompt.
A single `initialize` handshake, piped in over stdin, confirms it starts and speaks stdio (banner trimmed):

```
$ printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"readme-check","version":"0.0.1"}}}\n' | /Users/USERNAME/.venvs/laya-mlx-t1/bin/sys1-mcp
[10/02/26 09:13:09] INFO     Starting MCP server 'sys1' with transport 'stdio'
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","capabilities":{"logging":{},"prompts":{"listChanged":false},"resources":{"subscribe":false,"listChanged":false},"tools":{"listChanged":true}},"serverInfo":{"name":"sys1","version":"4.0.5"}}}
```

## Running over HTTP

Start command:

```
$ nohup /Users/USERNAME/.venvs/laya-mlx-t1/bin/sys1-mcp-http > /tmp/sys1-mcp-http.log 2>&1 &
```

MCP endpoint: `https://localhost:8765/mcp` (see TLS below).

The daemon also serves two routes outside the MCP protocol, on the same warm backend. Both return 503 while the backend loads and 400 on a malformed body.

- `POST /predict` takes `{"tool": "<tool name>", "arguments": {...}}` and runs any tool. A stdio `sys1-mcp` process pointed at `SYS1_DAEMON_URL` posts every call here, so it reuses this warm backend rather than loading its own (`sys1-mcp/src/sys1_mcp/daemon.py` `predict`).
- `POST /v1/systemone` takes `{"state", "questions", "model"?}`, the System One wire contract, and runs `sys1_ask`. Any System One client can use it, including a Playwright test or another `sys1-mcp` on the `systemone` backend. The response adds `checkpoint`, `limits` and `truncation` to the standard `model`/`answers`/`usage`.

`GET /health` names the backend and the models it serves, so a swap is confirmed with one request instead of by reading source (verified 2026-10-02, `tools` trimmed):

```
$ curl -s https://localhost:8765/health
{"status": "ok", "backend": "laya-mlx", "default_model": "typed-decisions",
 "roles": {"content": "english", "trace": "typed-decisions"},
 "models": {"typed-decisions": {"checkpoint": "aac6fef/laya-typed-decisions-mlx", "limits": {"max_len": 1024, "head_max_len": 256}},
            "english": {"checkpoint": "aac6fef/laya-mlx", "limits": {"max_len": 512, "head_max_len": 192}}},
 "tools": {"sys1_ask": …}}
```

`tools` lists every tool's argument and response keys. A client holding a stale cached tool list can be diagnosed with one request, rather than looking like a routing bug. Until the eager load finishes, `/health` reports `{"status":"loading", ...}` with 503.

### Tools

| Tool | For | Design record |
|---|---|---|
| `sys1_ask` | any closed question about one text | `tmp/tasks/notes/T2c-design.md` |
| `sys1_classify` | one schema over up to 256 texts, batched | `tmp/tasks/notes/T10-classify-batching.md` |
| `sys1_screen` | untrusted text, chunked so nothing is truncated, on the `content` model | `tmp/tasks/notes/T9-screen-calibration.md` |
| `sys1_health` | backend, models, identity, roles, and a timed probe | `tmp/tasks/notes/T8-health-tool-verification.log` |
| `sys1_relevant` | one candidate piece of context against one task, fixed `noul` on the `trace` model | `sys1-mcp/src/sys1_mcp/server.py` `RELEVANCE_QUESTIONS` |
| `sys1_select_tests` | rank discovered Playwright tests against diff chunks; full-suite fallback | `sys1-mcp/src/sys1_mcp/workflows.py` `select_tests` |
| `sys1_verify_outcome` | compare a claimed result with independent evidence and exact checks | `sys1-mcp/src/sys1_mcp/workflows.py` `verify_outcome` |
| `sys1_cache_fit` | check exact cache scope and expiry before semantic answer reuse | `sys1-mcp/src/sys1_mcp/workflows.py` `cache_fit` |
| `sys1_pack_context` | pin obligations, then fill a caller-counted context budget | `sys1-mcp/src/sys1_mcp/workflows.py` `pack_context` |

The four workflow tools adapt the proposals in `temp/expansion/laya-agent-use-cases.md`. Their input and fallback contracts are in `skills/sys1-mcp/references/agent-workflows.md`.

Every answer carries its provenance:

- `backend` and `model`: what answered, as a caller would name it.
- `checkpoint`: the weights or upstream model, when known.
- `limits`: token budgets, when known.
- `model_reason`, plus `model_note` when the default answered.
- `served_by`: `daemon`, `local`, or `local-fallback`.

Server env vars, with their code defaults (`sys1-mcp/src/sys1_mcp/server.py`, `sys1-mcp/src/sys1_mcp/daemon.py`):

| Var | Default | Meaning |
|---|---|---|
| `SYS1_DAEMON_URL` | unset | when set, forward each call to `<url>/predict`, falling back to this process's own backend only if the daemon is unreachable |
| `SYS1_MCP_HOST` | `127.0.0.1` | bind host for the HTTP listener |
| `SYS1_MCP_PORT` | `8765` | bind port for the HTTP listener |
| `SYS1_MCP_TLS_CERT` | unset | PEM certificate; with `SYS1_MCP_TLS_KEY`, serves HTTPS instead of HTTP |
| `SYS1_MCP_TLS_KEY` | unset | PEM private key; must be set together with `SYS1_MCP_TLS_CERT` |
| `SYS1_CALL_LOG` | `1` | `0` disables per-call JSONL logging entirely |
| `SYS1_CALL_LOG_PATH` | `~/Library/Logs/sys1-mcp/calls.jsonl` | where the rotated call log is written |
| `SYS1_CALL_LOG_MAX_BYTES` | `10485760` (10 MiB) | size of one call-log file before it rotates |
| `SYS1_CALL_LOG_BACKUPS` | `2` | rotated call-log files kept, beyond the active one |
| `SYS1_CALL_LOG_REDACT_THRESHOLD` | `0.5` | `sensitive_data` `noul` at/above which a logged text argument is redacted |

For LAN IP, port choice, bind address, and firewall posture, see `.agent/docs/dev-workflows.md`. This file always uses the loopback defaults above.

### Call logging

Every completed tool call is appended as one JSON line to `~/Library/Logs/sys1-mcp/calls.jsonl` (`sys1_mcp.server._log_call`). The line holds:

- timestamp and tool
- arguments
- backend, model, checkpoint and `served_by`
- truncation flags and timing
- the answer

`sys1_classify` logs its item count and truncated-item count instead of every per-item answer, so one large batch call doesn't dominate the file. History written before the rename stays in `~/Library/Logs/laya-mcp/calls.jsonl`. This server is single-user and local-only, so the tradeoff being managed is disk growth and secrets sitting at rest, not a second party reading it.

- **Rotated:** `RotatingFileHandler`, 3 files of 10 MiB by default (`SYS1_CALL_LOG_MAX_BYTES`, `SYS1_CALL_LOG_BACKUPS`). A logged call runs 1-3 KB, so that ceiling holds low thousands of calls before the oldest file rotates out.
- **Redacted, not skipped:** free-text arguments are scored before they are written: `sys1_ask`'s `state`, `sys1_screen`'s `text`, `sys1_relevant`'s `task`/`context`, and the joined text of `sys1_classify`'s `items`. Each gets the same `sensitive_data` question `sys1_screen` asks, as one unchunked call on the `content` model. `sys1_screen` reuses its own answer instead of paying for a second one. At or above `SYS1_CALL_LOG_REDACT_THRESHOLD` (default `0.5`), the value is replaced by `{"redacted": true, "sensitive_data_noul": <score>, "chars": <len>}`. Everything else in the record is kept (model, timing, the answer, `questions`/`criteria`), because those aren't where a secret would be. This is a heuristic, not a security boundary, the same caveat as `sys1_screen` itself. On a remote backend, the scoring call is one more request carrying the same text.
- `SYS1_CALL_LOG=0` disables logging entirely; `SYS1_CALL_LOG_PATH` moves the file.
- The four workflow tools log input counts, lengths, budget, and high-level result only. Their free-text arguments and selected context never enter the call log.

### TLS

The installed LaunchAgent serves HTTPS, not HTTP, because Claude Desktop rejects an `http://` MCP URL.
There is no reverse proxy. `FastMCP.run()` forwards `uvicorn_config` into `uvicorn.Config` (fastmcp 4.0.5, `run_http_async`), which takes `ssl_certfile` and `ssl_keyfile`, so the daemon terminates TLS itself (`sys1-mcp/src/sys1_mcp/daemon.py` `_tls_config`).

- Cert and key: `~/.config/sys1-mcp/tls/sys1-mcp.pem` and `sys1-mcp-key.pem`, outside the repo. They were copied from `~/.config/laya-mcp/tls/` on 2026-10-02, and that copy is still in place. The key is never committed.
- Issued by `mkcert`. Its root CA was already in this host's System keychain (`~/Library/Application Support/mkcert`, dated Oct 2024), so anything using the macOS trust store trusts it with no `-k` and no per-app configuration.
- Names on the cert: `localhost`, `127.0.0.1`, `::1`, `my-mac.local`, `192.0.2.10`. It expires 2028-12-22.
- Prefer `my-mac.local` over the IP for LAN clients: the IP is DHCP-assigned, and re-minting the cert is the only way to follow a lease change.
- Re-mint with `mkcert -cert-file sys1-mcp.pem -key-file sys1-mcp-key.pem localhost 127.0.0.1 ::1 my-mac.local <LAN-IP>` from that directory.
- Both variables must be set together. A half-set pair or a missing file exits with a message rather than silently falling back to plain HTTP. The whole environment is validated before the model load, so a typo fails in under a second.
- Unset both to go back to plain HTTP.

Verified on this host on 2026-09-22, under the earlier `laya-mcp` name with the same cert: `curl` without `-k` returned 200 from `/health` at `https://localhost:8765`, `https://my-mac.local:8765` and `https://192.0.2.10:8765`. Plain `http://localhost:8765/health` returned `000`. So there is one listener, and it is HTTPS only. Re-verified over `localhost` on 2026-10-02.

## Checking it is up

`/health` reports 503 while the backend is still loading, and 200 once it is ready.
The load happens eagerly, before the listener accepts connections. So an immediate probe right after starting usually gets `HTTP_STATUS:000` (connection refused, nothing bound yet) rather than 503. Once the listener is up, `/health` is already `ok`.

```
$ curl -s -o /dev/null -w 'HTTP_STATUS:%{http_code}\n' https://localhost:8765/health
HTTP_STATUS:200
```

No `-k` and no `--cacert`: the mkcert root CA is in the System keychain, so `curl` verifies the chain on its own.

Confirm the listener directly (2026-10-02):

```
$ lsof -nP -iTCP:8765 -sTCP:LISTEN
COMMAND   PID           USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
Python  75021 USERNAME   11u  IPv4 0xf3f088c564f33691      0t0  TCP *:8765 (LISTEN)
```

## Stopping it

Kill the pid recorded at start, then confirm the port is released with `lsof -nP -iTCP:8765 -sTCP:LISTEN`, which should print nothing. If the pid was not recorded, read it from that same `lsof` command's `PID` column first.

A persistent instance normally runs as a `launchd` LaunchAgent. Check `launchctl print gui/$(id -u)/com.sys1-mcp.http | grep -E 'state|pid'` before starting a second one. Its configuration is `sys1-mcp/deploy/com.sys1-mcp.http.plist`, and it stops with `launchctl bootout gui/$(id -u)/com.sys1-mcp.http`. The earlier `com.ld-mcp.laya-mcp-http` agent was booted out and removed from `~/Library/LaunchAgents` on 2026-10-02.

## Restarting and warming

`sys1-mcp/scripts/restart-warm.sh` restarts the LaunchAgent and waits for `/health` to return 200. It then exercises every question type on each served model and every specialized tool, including the four agent workflows. This warms their schema shapes before the first real call (see `skills/sys1-mcp/SKILL.md`'s Common pitfalls).

```
$ ./sys1-mcp/scripts/restart-warm.sh
com.sys1-mcp.http is not loaded; bootstrapping from /Users/USERNAME/Library/LaunchAgents/com.sys1-mcp.http.plist
waiting for https://localhost:8765/health... ok
warming schema shapes on english
  choice             english          ok (1s)
  ...
warming batched tools
  screen             sys1_screen      ok (0s)
  ...
  health             sys1_health      ok (0s)
identity: served backend, models and config match the lock
sys1-mcp is up and warm at https://localhost:8765/mcp
```

The output above is abridged from the first run on 2026-10-02. Its identity line comes from the re-check after `--write`; see below.

Flags and env vars:

| Flag | Env var | Default | Meaning |
|---|---|---|---|
| `--warm-only` | — | off | skip the restart; only wait for health and warm a server that is already up |
| `--reload` | — | off | boot out and bootstrap instead of kickstart, so plist edits take effect |
| `--url URL` | `SYS1_MCP_URL` | `https://localhost:8765` | server base URL |
| `--timeout SECONDS` | `SYS1_MCP_HEALTH_TIMEOUT` | `120` | how long to wait for `/health` to return 200 |
| — | `SYS1_MCP_MODELS` | every model `/health` lists | models to warm, space-separated |

How it restarts:

- When the agent is loaded, it runs `launchctl kickstart -k gui/$(id -u)/com.sys1-mcp.http`.
- When it is not loaded, it falls back to `launchctl bootstrap` from `~/Library/LaunchAgents/com.sys1-mcp.http.plist`.
- When neither applies, it exits 1 with instructions.

It also exits 1 on a health timeout or a failed warm-up call, printing the server's own error.

### Identity check

After warming, the script runs `sys1-mcp/scripts/check-identity.py`, which compares what the daemon serves against `sys1-mcp/deploy/identity.lock.json`. The lock pins:

- the backend, the default model, and the role mapping
- the runtime
- per model, whatever identity the backend reports. On `laya-mlx` that is the checkpoint, the Hugging Face snapshot, the sha256 of `rl_agent_config.json` (every calibration temperature) and the token limits. On `systemone` it is the upstream model name and endpoint.

On any difference it names the field and exits 1, and the server stays up. Every figure measured against this server, in the skill and in `tmp/tasks/notes/`, holds only for the locked identity. After an intended backend, checkpoint, config or runtime change, re-measure what depends on it, then record the new identity:

```
$ python3 sys1-mcp/scripts/check-identity.py --write
```

The lock moved to this format on 2026-10-02. Before rewriting it, every pinned field in the old lock was confirmed identical on the new server: each route's checkpoint, snapshot, config hash and limits, plus the runtime and the default. Design: `tmp/tasks/notes/T11-calibration.md` §6.

To restart by hand without the script:

```
$ launchctl kickstart -k gui/$(id -u)/com.sys1-mcp.http
```

## Resource cost

Every figure here was measured under the earlier `laya-mcp` name. The `laya-mlx` backend runs the same inference code path, unchanged in the 2026-10-02 refactor (parity below), so they carry over to it. They do not describe the `systemone` backend, which holds no model in memory. Each figure is one host's single-sample observation, not a benchmark.

Measured 2026-09-22 on `aac6fef/laya-typed-decisions-mlx`, against the live LaunchAgent, sampling the pid `launchctl print` reports:

| Point | `ps` `rss` | `footprint` `phys_footprint` |
|---|---|---|
| idle, agent loaded, no calls served | 976 MB | 920 MB |
| after 14 warm calls across all three question types | 992 MB | 1389 MB |
| peak during the first-ever start (download plus load) | 1051 MB | 1368 MB |

An earlier T5c sample reported ~38-41 MiB idle `rss` for the same service (`tmp/tasks/notes/T5-resource-profile.md`). Per the contradiction-handling rule, both are kept as observed rather than one overwriting the other. The T5c number cannot be a loaded 421M-parameter model in memory, and the daemon loads eagerly before it listens. The likely explanation is that T5c sampled a different pid, but that was not re-derived, so it is inference, not a finding. Prefer the figures above and re-verify the pid before trusting either.

Holding both checkpoints resident, measured 2026-09-22 against the live LaunchAgent:

| | One checkpoint | Both resident |
|---|---|---|
| cold start to `/health` 200, cached | 3379 ms | 4202 ms |
| idle `rss` | 976 MB | 1788 MB |
| idle `phys_footprint` | 920 MB | 1735 MB |

The second checkpoint costs about 815 MB and 820 ms.

MLX keeps freed Metal buffers in a cache that is unbounded by default, and every batch shape leaves its own. Before a cap existed, measured 2026-09-23, the footprint reached 8,457 MB after a round of mixed calls and 11 GB after one 256-item classify. The backend now caps the cache at 512 MiB (`sys1-mcp/src/sys1_mcp/backends/laya_mlx.py` `MLX_CACHE_LIMIT_BYTES`). With the cap, the footprint was 2,341 MB after restart and warm-up and 2,348 MB after two 256-item batches, with no change in speed (`tmp/tasks/notes/T10-classify-batching.md`). Set `LAYA_PRELOAD=0` to build only the default model and pay the other one's load on first use instead.

Startup cost, single-checkpoint run:

- 3379 ms: restart to `/health` 200 with the checkpoint already cached.
- 409 s: first-ever start, dominated by downloading `model.safetensors` (842,609,225 bytes) at roughly 2-3 MB/s. This is paid once per checkpoint per machine, not per restart.
- 33-41 ms (median 36): warm loopback HTTPS MCP `tools/call`, same schema shape, 10 consecutive runs.

### Refactor parity

On 2026-10-02 the old `laya-mcp` daemon and the refactored `sys1-mcp` daemon received identical calls. All 11 call types returned answers identical to the last digit, and so did the truncation reports, screening chunk boundaries and the four workflow results. The calls covered `ask` on both models, a truncated `ask`, `classify` on both models, `screen`, `relevant`, and the four workflows. The scripts are `tmp/probes/tools/sys1_refactor_parity.py` and `tmp/probes/tools/sys1_systemone_backend.py`; the second runs a `systemone`-backend server against the daemon's `/v1/systemone` and matched it on every answer.

## Applying a plist change

`launchctl kickstart -k` restarts the process, but launchd keeps the job definition it bootstrapped. An edited `EnvironmentVariables` block is therefore not picked up, and the server keeps serving the old configuration while the file on disk says otherwise.

```
$ cp sys1-mcp/deploy/com.sys1-mcp.http.plist ~/Library/LaunchAgents/
$ ./sys1-mcp/scripts/restart-warm.sh --reload
```

`--reload` boots the job out and back in, waits for `/health`, then warms every model. Confirm the change landed by reading it back rather than trusting the file:

```
$ curl -s https://localhost:8765/health | python3 -c 'import sys,json;d=json.load(sys.stdin);print(d["backend"], d["default_model"])'
```

## Registering with an MCP client

The server exposes a single MCP endpoint over `streamable-http` at `/mcp`, registered as `sys1-mcp`, with the URL shape `https://<hostname or LAN name>:8765/mcp`. It has no auth of any kind.
Use a name the certificate covers (`localhost` on this host, `my-mac.local` from the LAN), or TLS verification fails. The cert also covers the current LAN IP, but that IP is DHCP-assigned; see TLS above before hardcoding it anywhere.

### Claude Desktop

Claude Desktop cannot reach this server by URL at all. Its "Add custom connector" flow is for remote MCP servers: the connection is made from Anthropic's side, not from this machine. So `localhost`, `127.0.0.1`, and `0.0.0.0` there resolve on Anthropic's host and never arrive here, which is also why it insists on HTTPS. Verified on 2026-09-22: across several attempts at all three addresses, the daemon's access log recorded zero inbound requests.

Register it as a local stdio server instead, in `~/Library/Application Support/Claude/claude_desktop_config.json`, then quit and reopen the app:

```json
{
  "mcpServers": {
    "sys1-mcp": {
      "command": "/Users/USERNAME/.venvs/laya-mlx-t1/bin/sys1-mcp",
      "env": {
        "SYS1_DAEMON_URL": "https://localhost:8765",
        "SSL_CERT_FILE": "/Users/USERNAME/Library/Application Support/mkcert/rootCA.pem"
      }
    }
  }
}
```

`SYS1_DAEMON_URL` makes that stdio process forward each call to the running daemon's `/predict` route. It borrows the daemon's warm backend instead of loading a second copy into RAM.
`SSL_CERT_FILE` is required with it. The forwarding client is `httpx`, which verifies against certifi's bundle and not the macOS keychain. Without it, every call fails TLS and falls back to a local load, reported as `served_by: local-fallback` with a `warning` (`sys1-mcp/src/sys1_mcp/server.py` `_dispatch`).

Verified 2026-10-02 by spawning this exact command and env as a stdio client: `sys1_ask` answered with `served_by: daemon` from `aac6fef/laya-typed-decisions-mlx`. The config file was rewritten the same day; the running app picks it up only after a restart.

### Claude Code

Registered at user scope, so every repo on this machine sees the tool:

```
$ claude mcp add --scope user --transport http sys1-mcp https://localhost:8765/mcp
$ claude mcp list | grep sys1
sys1-mcp: https://localhost:8765/mcp (HTTP) - ✔ Connected
```

The agent skill is linked at user scope too, as `~/.claude/skills/sys1-mcp` → `skills/sys1-mcp`. Verified 2026-10-02. The earlier `laya-mcp` registration and skill link were removed the same day.

### Codex CLI

Codex reads `~/.codex/config.toml`, under an `[mcp_servers.<name>]` table with a `url` key for `streamable_http` servers:

```toml
[mcp_servers.sys1-mcp]
url = "https://localhost:8765/mcp"
default_tools_approval_mode = "approve"
```

Without `default_tools_approval_mode`, Codex asks before every call, and `codex exec` fails the call outright ("MCP tool call requires approval, but approval policy is never"). With the `laya-mlx` backend every tool is local and read-only, so auto-approving this one server is safe. On a remote backend, approving it also approves sending tool input off the machine. The key was found in the Codex 0.155.1 binary's config schema; accepted values are `auto`, `prompt`, `writes`, `approve`. `codex mcp list` shows `sys1-mcp` enabled (2026-10-02). Its skill is linked as `~/.codex/skills/sys1-mcp` → `skills/sys1-mcp`.

No block above needs a bearer token or auth header. This server has no auth, so there is nothing to configure for any client. A remote backend's `SYS1_API_KEY` is the server's own credential, never a client's.

## Pointers

- `skills/sys1-mcp/SKILL.md`: the agent-facing doc. It covers which tool to use, the question contract, how to write questions, screening, and pitfalls.
- `sys1-mcp/src/sys1_mcp/backends/`: the backend interface, `laya_mlx.py`, and `systemone.py`.
- `.agent/docs/dev-workflows.md`: LAN IP, port, bind address, and firewall decisions.
- `sys1-mcp/deploy/com.sys1-mcp.http.plist`: the persistent LaunchAgent configuration.
- `sys1-mcp/scripts/restart-warm.sh`: restarts the LaunchAgent and warms every question type.
- `sys1-mcp/scripts/check-identity.py` and `sys1-mcp/deploy/identity.lock.json`: the served-identity lock and its check.
- `research.md`: the original research brief this setup was built from.
