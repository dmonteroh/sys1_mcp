# sys1_mcp

`sys1-mcp` is a model-agnostic MCP server for System One decision models, run on one operator's machine. A System One model takes a state and typed questions (`noul`, `choice`, `score`) and returns probabilities instead of text. Laya, Jev and Clef are System One models. The server's tools never name a model family. Every answer comes from one configured **backend**:

- `systemone` (default) posts to any `/v1/systemone`-shaped HTTP endpoint: Jev, Clef on Workers AI, a local open server, or this project's own daemon.
- `laya-mlx` runs Laya checkpoints in-process on Apple Silicon. It needs the `[laya]` extra.

This host runs `systemone` against Jev-Style-0.8B-v3 (`chaoliangUNSW/Jev-Style-0.8B-Decision-v3-MLX`, bf16, MLX). Why that model: [Choosing the model](#choosing-the-model). Two LaunchAgents run:

| LaunchAgent | Serves | Listens | Config |
|---|---|---|---|
| `com.sys1-mcp.jev-style` | the model: `sys1-mcp/scripts/jev-style-serve.py serve --release 0.8b-v3 --backend mlx --precision bf16` on `~/.venvs/jev-style`'s Python | `127.0.0.1:8766`, plain HTTP, loopback only | `sys1-mcp/deploy/com.sys1-mcp.jev-style.plist` |
| `com.sys1-mcp.http` | the MCP server, pointed at the model | `0.0.0.0:8765`, HTTPS | `sys1-mcp/deploy/com.sys1-mcp.http.plist` |

`jev-style-serve.py` runs jev-style's own CLI with the MLX buffer cache capped, which jev-style has no option for. The cap defaults to 0 bytes; `SYS1_MLX_CACHE_LIMIT_BYTES` overrides it.

For the agent-facing tool contract, see `skills/sys1-mcp/SKILL.md`.

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

Models are `english` (alias `base`, 512-token budget) and `typed-decisions` (1024-token budget). The default and the `trace` role are `typed-decisions`, and the `content` role is `english`. Only this backend reports exact per-question truncation, batches texts into shared forward passes, chunks screening text with the real tokenizer, and pins a snapshot and calibration-config hash for the identity lock. The first start downloads the checkpoints, about 1.7 GB. Memory and startup figures: [Resource cost](#resource-cost).

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

`sys1_relevant` asks a neutral two-option `choice` (A relevant, B not) and returns the probability of A as `noul`. On `laya-mlx` it asks a plain `noul` instead. Each wording is the one measured best on that model ([Relevance wording](#relevance-wording)). `SYS1_RELEVANCE_WORDING` overrides it. The answer's `question` field holds the exact question, for callers batching candidates through `sys1_classify`.

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

### Network

- Port `8765`, because fastmcp's default `8000` collides with ad-hoc dev servers.
- `com.sys1-mcp.http` binds `0.0.0.0`, so the server runs continuously and any host on the LAN can reach it, with no authentication. That exposure is an accepted choice for a trusted LAN. Stop the agent, or set `SYS1_MCP_HOST=127.0.0.1`, to close it.
- The model server listens on loopback only. Containers and LAN clients reach the model through the daemon.
- From a container, `localhost` and `127.0.0.1` do not reach this host. Use `host.docker.internal`, which also works under Podman, with the mkcert root CA in the container's trust store.
- LAN clients should use `my-mac.local` rather than the LAN IP, which is DHCP-assigned. Read the IP at use time with `ipconfig getifaddr en0`.
- Firewall rules are added only after a connection is refused. The macOS Application Firewall needed none for this daemon.

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

A plain restart does not re-read the plist. The plists in `sys1-mcp/deploy/` write the home folder as `/Users/USERNAME`, because launchd does not expand `~` or `$HOME`, so install them with the placeholder replaced. After editing one:

```
$ sed "s|/Users/USERNAME|$HOME|g" sys1-mcp/deploy/com.sys1-mcp.http.plist > ~/Library/LaunchAgents/com.sys1-mcp.http.plist
$ ./sys1-mcp/scripts/restart-warm.sh --reload
```

### Identity check

`sys1-mcp/scripts/check-identity.py` compares what the daemon serves with `sys1-mcp/deploy/identity.lock.json`: the backend, default model, role mapping, runtime, and each model's identity (on `systemone` the upstream model name and endpoint, on `laya-mlx` the checkpoint, snapshot, calibration-config hash and token limits). A difference names the field and exits 1, and the server stays up. After an intended model change, re-measure what depends on it, then record the new identity with `check-identity.py --write`.

## Resource cost

`phys_footprint` on this host, read with `footprint`:

- MCP daemon: 83 MB warm (2026-10-02). It holds no model on the `systemone` backend.
- Jev-Style model server, MLX cache capped at 0: 3,160 MB warm after restart. Replaying 368 real gate calls held it at 4.2-6.5 GB, peaking at 8.1 GB on 6,000-20,000-token inputs, and it fell back to 3.0-3.3 GB once idle (2026-10-14). Uncapped it sat at 5,074 MB warm (2026-10-02). The cap changed no answer in that replay.
- Laya on `laya-mlx`: the first start took 409 s, mostly downloading the checkpoint. With the MLX cache capped at 512 MiB (`MLX_CACHE_LIMIT_BYTES` in `laya_mlx.py`) the process held 2,341 MB after warm-up, against 11 GB uncapped after one 256-item classify (2026-09-23). A warm loopback HTTPS `tools/call` took 33-41 ms.

## Choosing the model

Nine System One models were run through this server's own `systemone` backend on 2026-10-02, with the same data, question wording and client for all of them. Accuracy is on 116-160 items per task, so gaps under about 5 points are noise. The typed-decisions column is in-domain for Laya typed-decisions and very likely for Jev-Style.

| model | size | injection AUC | AG News acc | BoolQ acc | SST-5 acc | typed-decisions acc | latency |
|---|---|---|---|---|---|---|---|
| Laya English (`aac6fef/laya-mlx`) | 0.42B | 0.829 | 0.950 | 0.850 | 0.281 | 0.337 | 54 ms |
| Laya typed-decisions (`aac6fef/laya-typed-decisions-mlx`) | 0.42B | 0.926 | 0.944 | 0.831 | 0.438 | 0.783 | 54 ms |
| **Jev-Style-0.8B-v3** (`chaoliangUNSW/Jev-Style-0.8B-Decision-v3-MLX`) | 0.75B | 0.952 | 0.950 | 0.875 | 0.556 | 0.800 | 49 ms |
| Kev-0.8B (`jaredpalmer/kev-0.8b`) | 0.8B | 0.732 | 0.894 | 0.863 | 0.456 | 0.407 | 46 ms |
| OpenThai-SystemOne (`iapp/OpenThai-SystemOne`) | 0.75B | 0.959 | 0.956 | 0.825 | 0.431 | 0.483 | 135 ms |
| open-jev-deberta-v3-large | 0.43B | 0.544 | 0.787 | 0.894 | 0.613 | 0.387 | 56 ms |
| Jev-Style-2B-v3 | 2B | 0.945 | 0.856 | 0.906 | 0.406 | 0.610 | 94 ms |
| decider-2b v11 (`Mapika/decider-2b`) | 1.9B | 0.942 | 0.881 | 0.875 | 0.531 | 0.643 | 117 ms |
| Kev-4B (`jaredpalmer/kev-4b`) | 4.2B | 0.922 | 0.919 | 0.919 | 0.544 | 0.663 | 217 ms |

Jev-Style-0.8B-v3 matched or beat Laya on every task at about the same latency, and it reads up to 25,600 tokens where Laya cuts at 1,024. On `sys1_screen`'s own schema it scored `directed` AUC 0.949 and `injection` AUC 0.930 on the deepset prompt-injection test set. Switching gave up three Laya-only features: exact per-question truncation reports, batched forward passes across `sys1_classify` items, and tokenizer-exact screening chunks.

OpenDecider-nano (`manjunathshiva/opendecider-nano`) was tried on 2026-10-14 against 368 real gate calls and rejected. Its 2,048-token limit truncated 85% of the questions, and it then chose the permissive option almost every time.

### Relevance wording

177 real `(task, context)` pairs from the call log, labelled blind by an independent judge (170 relevant, 6 not), on Jev-Style:

| `sys1_relevant` wording | relevant at ≥ 0.5 | negatives below 0.5 |
|---|---|---|
| earlier wording | 87 of 170 | 5 of 6 |
| `noul` with true/false descriptions | 110 of 170 | 5 of 6 |
| neutral two-option `choice` (current default) | 152 of 170 | 5 of 6 |

On Laya the logged plain `noul` kept 137 of 170 and all 6 negatives, and the neutral-choice rewrite was reverted there on 2026-09-27, so `laya-mlx` keeps the `noul`.

## Registering with an MCP client

The endpoint is `https://<name>:8765/mcp`, `streamable-http`, registered as `sys1-mcp`, with no auth. Use a name the certificate covers, or TLS verification fails.

### Claude Code

```
$ claude mcp add --scope user --transport http sys1-mcp https://localhost:8765/mcp
```

Install the skill at user scope by copying `skills/sys1-mcp` to `~/.claude/skills/sys1-mcp`.

### Codex CLI

In `~/.codex/config.toml`:

```toml
[mcp_servers.sys1-mcp]
url = "https://localhost:8765/mcp"
default_tools_approval_mode = "approve"
```

Without `default_tools_approval_mode`, Codex asks before every call, and `codex exec` fails the call outright. Approving is safe here because the backend is a loopback endpoint on this host. On a remote backend it also approves sending tool input off the machine. Install the skill by copying `skills/sys1-mcp` to `~/.codex/skills/sys1-mcp`.

### Claude Desktop

Claude Desktop cannot reach this server by URL: its custom connectors connect from Anthropic's side, so `localhost` never arrives here. Register a local stdio server in `~/Library/Application Support/Claude/claude_desktop_config.json`, with `USERNAME` replaced by your user name, then quit and reopen the app:

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
