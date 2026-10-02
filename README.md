# sys1-mcp

A model-agnostic MCP server for System One decision models, run on one operator's machine. A System One model takes a state and typed questions (`noul`, `choice`, `score`) and returns probabilities instead of text. Laya, Jev and Clef are System One models. The server's tools never name a model family. Every answer comes from one configured **backend**:

- `systemone` (default) posts to any `/v1/systemone`-shaped HTTP endpoint: Jev, Clef on Workers AI, a local open server, or this project's own daemon.
- `laya-mlx` runs Laya checkpoints in-process on Apple Silicon. It needs the `[laya]` extra.

This host runs `systemone` against Jev-Style-0.8B-v3 (`chaoliangUNSW/Jev-Style-0.8B-Decision-v3-MLX`, bf16, MLX). Why that model: `.agent/docs/system-one-models.md`. Two LaunchAgents run:

| LaunchAgent | Serves | Listens | Config |
|---|---|---|---|
| `com.sys1-mcp.jev-style` | the model: `jev-style serve --release 0.8b-v3 --backend mlx --precision bf16` from `~/.venvs/jev-style` | `127.0.0.1:8766`, plain HTTP, loopback only | `sys1-mcp/deploy/com.sys1-mcp.jev-style.plist` |
| `com.sys1-mcp.http` | the MCP server, pointed at the model | `0.0.0.0:8765`, HTTPS | `sys1-mcp/deploy/com.sys1-mcp.http.plist` |

For the agent-facing tool contract, see `skills/sys1-mcp/SKILL.md`. For setup knowledge, network decisions and measurements, see `.agent/`.

## Install

The server runs from `~/.venvs/sys1-mcp`, built from `sys1-mcp/uv.lock` with the project installed editable, so it runs this repository's code at the locked dependency versions. Build it, or update it after a dependency change, then restart the daemon:

```
$ UV_PROJECT_ENVIRONMENT=$HOME/.venvs/sys1-mcp uv sync --project sys1-mcp --frozen
$ ./sys1-mcp/scripts/restart-warm.sh
```

Add `--extra laya` to the `uv sync` to use the `laya-mlx` backend. Tests: `~/.venvs/sys1-mcp/bin/python -m unittest discover -s sys1-mcp/tests`.

## Configuring the backend

Environment variables, read once at startup and validated before any model loads (`sys1-mcp/src/sys1_mcp/backends/`).

Each backend serves one or more named **models**, which callers pass as `model`. Tools with a fixed purpose ask for a **role** instead:

- `content`: judgments about what a text says. `sys1_screen` and call-log redaction use it.
- `trace`: judgments about an agent's own task state. `sys1_relevant` and the workflow tools use it.

| Var | Default | Meaning |
|---|---|---|
| `SYS1_BACKEND` | `systemone` | `systemone` or `laya-mlx` |
| `SYS1_MODEL_DEFAULT` | backend's own | the model a call without `model` gets |
| `SYS1_MODEL_CONTENT` | backend's own | the model the `content` role uses |
| `SYS1_MODEL_TRACE` | backend's own | the model the `trace` role uses |

### `systemone`

Posts `{"state", "questions", "model"?}` to one endpoint and reads `{"model", "answers", "usage"}` back. That is the Jev API contract (jev-agent.com/api-reference), which Clef also claims. Truncation, limits and `checkpoint` are passed through when the endpoint reports them. An endpoint that reports no truncation gets `truncation.checked: false` and `truncated: null`, meaning unknown, unless `SYS1_REFUSES_OVERLONG=1` says it never cuts. A `choice` whose `criteria` is a bare label list is sent as `{label: null}`, the contract's object form, because strict endpoints reject the list.

| Var | Default | Meaning |
|---|---|---|
| `SYS1_ENDPOINT` | required | URL to POST to. A literal `{model}` is replaced by the model name. Without it the server stops at startup. |
| `SYS1_API_KEY` | unset | sent as `Authorization: Bearer <key>` |
| `SYS1_MODELS` | unset | comma-separated model names, each sent as `model`. Unset serves one model named `default` and sends none. |
| `SYS1_CONTEXT_TOKENS` | `8192` | assumed context window, used only to size screening chunks (chosen default, below Jev's 32k and Clef's 64k) |
| `SYS1_TIMEOUT` | `30` | seconds per request |
| `SYS1_CONCURRENCY` | `8` | parallel requests for `sys1_classify` and `sys1_screen`. `1` for an endpoint that cannot take parallel requests. |
| `SYS1_REFUSES_OVERLONG` | `0` | `1` when the endpoint rejects over-limit input instead of cutting it, so answers report `truncated: false` instead of unknown |

```sh
# This host: Jev-Style, what com.sys1-mcp.http runs
SYS1_BACKEND=systemone SYS1_ENDPOINT=http://127.0.0.1:8766/v1/systemone \
SYS1_MODELS=jev-style-0.8b-v3 SYS1_CONTEXT_TOKENS=25600 SYS1_REFUSES_OVERLONG=1

# Jev (unverified)
SYS1_BACKEND=systemone SYS1_ENDPOINT=https://jev-agent.com/v1/systemone SYS1_API_KEY=jv_live_...

# Clef on Workers AI, model in the path (unverified; URL shape from Cloudflare's model page, read 2026-10-02)
SYS1_BACKEND=systemone SYS1_MODELS=clef,clef-flash SYS1_CONTEXT_TOKENS=65536 \
SYS1_ENDPOINT='https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/run/@cf/cloudflare/{model}' \
SYS1_API_KEY=<workers-ai-token>
```

A remote endpoint receives every state, screened page and redaction probe. Every figure measured against this server holds only for the model it was measured on.

### `laya-mlx`

Models are `english` (alias `base`, 512-token budget) and `typed-decisions` (1024-token budget). The default and the `trace` role are `typed-decisions`, and the `content` role is `english`. Only this backend reports exact per-question truncation, batches texts into shared forward passes, chunks screening text with the real tokenizer, and pins a snapshot and calibration-config hash for the identity lock. The first start downloads the checkpoints, about 1.7 GB. Memory and startup figures: `.agent/docs/system-one-models.md`.

| Var | Default | Meaning |
|---|---|---|
| `LAYA_CHECKPOINT_ENGLISH` | `aac6fef/laya-mlx` | repo for the `english` model |
| `LAYA_CHECKPOINT_TYPED_DECISIONS` | `aac6fef/laya-typed-decisions-mlx` | repo for the `typed-decisions` model |
| `LAYA_PRELOAD` | `1` | build every model at startup. `0` builds only the default. |

## Running

### Over HTTP

The LaunchAgent is the normal way to run it. By hand, with the backend variables from `sys1-mcp/deploy/com.sys1-mcp.http.plist` set:

```
$ nohup ~/.venvs/sys1-mcp/bin/sys1-mcp-http > /tmp/sys1-mcp-http.log 2>&1 &
```

MCP endpoint: `https://localhost:8765/mcp`. Two more routes run on the same backend, outside MCP. Both return 503 while the backend loads and 400 on a malformed body.

- `POST /predict` takes `{"tool", "arguments", "caller"?}` and runs any tool. A stdio `sys1-mcp` with `SYS1_DAEMON_URL` set posts every call here (`daemon.py` `predict`).
- `POST /v1/systemone` takes `{"state", "questions", "model"?}`, the System One wire contract, and runs `sys1_ask`. Any System One client can use it, including a Playwright test or another `sys1-mcp`.

`GET /health` returns 503 with `{"status": "loading"}` until the backend is ready, then the backend, the models it serves, the role mapping, and every tool's argument and response keys. A client holding a stale cached tool list shows up there.

### Over stdio

`~/.venvs/sys1-mcp/bin/sys1-mcp`, no flags, with the backend variables set. An MCP client spawns it as a subprocess. Check that it starts:

```
$ printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"readme-check","version":"0.0.1"}}}\n' \
  | SYS1_ENDPOINT=http://127.0.0.1:8766/v1/systemone ~/.venvs/sys1-mcp/bin/sys1-mcp
```

It answers with a `result` naming `serverInfo` `sys1`.

## Tools

| Tool | For |
|---|---|
| `sys1_ask` | any closed question about one text |
| `sys1_classify` | one schema over up to 256 texts, batched |
| `sys1_screen` | untrusted text, chunked so nothing is truncated, on the `content` model |
| `sys1_health` | backend, models, identity, roles, and a timed probe |
| `sys1_relevant` | one candidate piece of context against one task, on the `trace` model, answered as a `noul` |
| `sys1_select_tests` | rank Playwright tests against diff chunks, with a full-suite fallback |
| `sys1_verify_outcome` | compare a claimed result with independent evidence and exact checks |
| `sys1_cache_fit` | check exact cache scope and expiry before semantic answer reuse |
| `sys1_pack_context` | pin obligations, then fill a caller-counted context budget |

The last four are workflow tools, off unless `SYS1_WORKFLOW_TOOLS=1`. Off, they are left out of the tool list and `/health`, and `/predict` refuses them. Their contracts are in `skills/sys1-mcp/references/agent-workflows.md`.

`sys1_relevant` asks a neutral two-option `choice` (A relevant, B not) and returns the probability of A as `noul`. On `laya-mlx` it asks a plain `noul` instead. Each wording is the one measured best on that model (`.agent/docs/usage-findings.md`). `SYS1_RELEVANCE_WORDING` overrides it. The answer's `question` field holds the exact question, for callers batching candidates through `sys1_classify`.

Every answer carries its provenance: `backend` and `model`, `checkpoint` and `limits` when known, `model_reason` (plus `model_note` when the default answered), and `served_by` (`daemon`, `local`, or `local-fallback`).

### Server settings

| Var | Default | Meaning |
|---|---|---|
| `SYS1_DAEMON_URL` | unset | forward each call to `<url>/predict`. This process's own backend answers only if the daemon is unreachable. |
| `SYS1_MCP_HOST` | `127.0.0.1` | bind host for the HTTP listener |
| `SYS1_MCP_PORT` | `8765` | bind port for the HTTP listener |
| `SYS1_MCP_TLS_CERT` | unset | PEM certificate. With `SYS1_MCP_TLS_KEY`, serves HTTPS. |
| `SYS1_MCP_TLS_KEY` | unset | PEM private key, set together with `SYS1_MCP_TLS_CERT` |
| `SYS1_WORKFLOW_TOOLS` | `0` | `1` serves the four workflow tools |
| `SYS1_RELEVANCE_WORDING` | `noul` on `laya-mlx`, `choice` otherwise | the question `sys1_relevant` asks |
| `SYS1_ACCESS_LOG` | `quiet` | `all` keeps every access-log line, including OAuth discovery probes and stale-session 404s |
| `SYS1_CALL_LOG` | `1` | `0` disables the call log |
| `SYS1_CALL_LOG_PATH` | `~/Library/Logs/sys1-mcp/calls.jsonl` | call-log location |
| `SYS1_CALL_LOG_MAX_BYTES` | `10485760` (10 MiB) | size of one call-log file before it rotates |
| `SYS1_CALL_LOG_BACKUPS` | `2` | rotated call-log files kept beyond the active one |
| `SYS1_CALL_LOG_REDACT_THRESHOLD` | `0.5` | `sensitive_data` probability at or above which a logged text argument is redacted |

LAN IP, port, bind address and firewall decisions: `.agent/docs/dev-workflows.md`.

### Call logging

Every completed call is one JSON line in `~/Library/Logs/sys1-mcp/calls.jsonl` (`server.py` `_log_call`), rotated at 3 files of 10 MiB by default. A line holds:

- timestamp and tool
- `route`: `mcp`, `predict` or `systemone`
- `caller`: the MCP client's `name` and `version`, its `session` and `transport`, and `user_agent` on the HTTP routes. A stdio `sys1-mcp` forwarding to the daemon passes its client's identity in the `/predict` body, and only the daemon logs the call.
- the arguments, redacted as below
- backend, model, checkpoint, `served_by`, truncation flags and timing
- the answer. `sys1_classify` logs item counts instead, and the workflow tools log input sizes and their high-level result.

Free-text arguments are scored with `sys1_screen`'s `sensitive_data` question on the `content` model: `sys1_ask`'s `state`, `sys1_relevant`'s `task` and `context`, and the joined text of `sys1_classify`'s `items`. `sys1_screen` reuses its own answer. Scoring runs on a background thread after the caller has its answer, one batched call per record. A value at or above the threshold is written as `{"redacted": true, "sensitive_data_noul": <score>, "chars": <len>}`. If scoring fails or the queue is full, the text is withheld unscored, with a `reason`. This is a heuristic, not a security boundary.

### TLS

The daemon terminates TLS itself. `FastMCP.run()` passes `uvicorn_config` through to uvicorn (`daemon.py` `_tls_config`). HTTPS is required because Claude Desktop rejects an `http://` MCP URL.

- Cert and key: `~/.config/sys1-mcp/tls/sys1-mcp.pem` and `sys1-mcp-key.pem`, outside the repo.
- Issued by `mkcert`, whose root CA is in this host's System keychain, so anything using the macOS trust store verifies it with no `-k`.
- Names: `localhost`, `my-mac.local`, `host.containers.internal`, `host.docker.internal`, `127.0.0.1`, `::1`, `192.0.2.10`, `198.51.100.6`, `192.168.127.254`. Expires 2028-12-29. Use `my-mac.local` rather than the LAN IP, which is DHCP-assigned.
- Re-mint with `tools/scripts/mint-cert.sh` (`--help` for options). It mints into `tmp/certificate/` by default. `--install` backs up the served pair, installs the new one, restarts, runs `check-mcp.sh`, and restores the backup if the check fails. To keep this host's current names: `tools/scripts/mint-cert.sh --force --install --name my-mac.local --name 198.51.100.6`.
- A half-set cert/key pair or a missing file stops the server at startup. Unset both for plain HTTP.

## Checking, stopping, restarting

```
$ curl -s -o /dev/null -w '%{http_code}\n' https://localhost:8765/health     # 200 when ready
$ launchctl print gui/$(id -u)/com.sys1-mcp.http | grep -E 'state|pid'
$ ./tools/scripts/check-mcp.sh                                               # health, initialize, tools/list, one call
```

The backend loads before the listener binds, so a probe right after start gets connection refused, not 503. `check-mcp.sh` needs only bash and curl and runs from a devcontainer too: `--url https://host.docker.internal:8765`.

Stop the server with `launchctl bootout gui/$(id -u)/com.sys1-mcp.http`. The model server is its own agent: `launchctl kickstart -k gui/$(id -u)/com.sys1-mcp.jev-style` restarts it.

`sys1-mcp/scripts/restart-warm.sh` restarts `com.sys1-mcp.http`, waits for `/health`, then warms every question type on each served model and every tool the server serves. It ends with the identity check below.

| Flag | Env var | Default | Meaning |
|---|---|---|---|
| `--warm-only` | | off | skip the restart |
| `--reload` | | off | boot out and bootstrap, so plist edits take effect |
| `--url URL` | `SYS1_MCP_URL` | `https://localhost:8765` | server base URL |
| `--timeout SECONDS` | `SYS1_MCP_HEALTH_TIMEOUT` | `120` | how long to wait for `/health` |
| | `SYS1_MCP_MODELS` | every model `/health` lists | models to warm |

A plain restart does not re-read the plist. After editing it:

```
$ cp sys1-mcp/deploy/com.sys1-mcp.http.plist ~/Library/LaunchAgents/
$ ./sys1-mcp/scripts/restart-warm.sh --reload
```

### Identity check

`sys1-mcp/scripts/check-identity.py` compares what the daemon serves with `sys1-mcp/deploy/identity.lock.json`: the backend, default model, role mapping, runtime, and each model's identity (on `systemone` the upstream model name and endpoint, on `laya-mlx` the checkpoint, snapshot, calibration-config hash and token limits). A difference names the field and exits 1, and the server stays up. After an intended model change, re-measure what depends on it, then record the new identity with `check-identity.py --write`.

## Resource cost

On this host the MCP daemon's `phys_footprint` is 83 MB, and the Jev-Style model server's is 5,074 MB (read with `footprint` on 2026-10-02, both warm). The daemon holds no model on the `systemone` backend.

## Registering with an MCP client

The endpoint is `https://<name>:8765/mcp`, `streamable-http`, registered as `sys1-mcp`, with no auth. Use a name the certificate covers, or TLS verification fails.

### Claude Code

```
$ claude mcp add --scope user --transport http sys1-mcp https://localhost:8765/mcp
```

The skill is linked at user scope: `~/.claude/skills/sys1-mcp` → `skills/sys1-mcp`.

### Codex CLI

In `~/.codex/config.toml`:

```toml
[mcp_servers.sys1-mcp]
url = "https://localhost:8765/mcp"
default_tools_approval_mode = "approve"
```

Without `default_tools_approval_mode`, Codex asks before every call, and `codex exec` fails the call outright. Approving is safe here because the backend is a loopback endpoint on this host. On a remote backend it also approves sending tool input off the machine. The skill is linked as `~/.codex/skills/sys1-mcp` → `skills/sys1-mcp`.

### Claude Desktop

Claude Desktop cannot reach this server by URL: its custom connectors connect from Anthropic's side, so `localhost` never arrives here. Register a local stdio server in `~/Library/Application Support/Claude/claude_desktop_config.json`, then quit and reopen the app:

```json
{
  "mcpServers": {
    "sys1-mcp": {
      "command": "/Users/USERNAME/.venvs/sys1-mcp/bin/sys1-mcp",
      "env": {
        "SYS1_DAEMON_URL": "https://localhost:8765",
        "SSL_CERT_FILE": "/Users/USERNAME/Library/Application Support/mkcert/rootCA.pem",
        "SYS1_BACKEND": "systemone",
        "SYS1_ENDPOINT": "http://127.0.0.1:8766/v1/systemone",
        "SYS1_MODELS": "jev-style-0.8b-v3",
        "SYS1_CONTEXT_TOKENS": "25600",
        "SYS1_REFUSES_OVERLONG": "1"
      }
    }
  }
}
```

`SYS1_DAEMON_URL` forwards every call to the daemon, so the app uses the daemon's backend and its call log. `SSL_CERT_FILE` is required with it, because the forwarding client (`httpx`) verifies against certifi's bundle, not the macOS keychain. The backend variables are the fallback: if the daemon is unreachable, this process asks Jev-Style directly and marks the answer `served_by: local-fallback` with a `warning`.

## Pointers

- `skills/sys1-mcp/SKILL.md`: the agent-facing doc: which tool to use, the question contract, how to write questions, screening, pitfalls.
- `sys1-mcp/src/sys1_mcp/`: `server.py` (tools, logging), `daemon.py` (HTTP routes, TLS), `workflows.py`, `backends/`.
- `sys1-mcp/deploy/`: the LaunchAgent plists and the identity lock.
- `sys1-mcp/scripts/`: `restart-warm.sh`, `check-identity.py`.
- `tools/scripts/`: `check-mcp.sh`, `mint-cert.sh`.
- `.agent/docs/`: model choice, usage findings, network decisions.
- `research.md`: the research brief this setup started from.
