# Local Laya research brief

Research only, nothing executed. Commands below are quoted from search-result summaries of each project's README (not opened/run this session), so verify each one against the actual repo before relying on it — flagged inline where the guidance is inference rather than a quoted source. Laya recap: `convaiinnovations/laya` (Apache 2.0), a non-autoregressive typed-decision model (choice/score/noul, calibrated probabilities), open-source answer to TypeSafe's closed Jev API.

## 1. Setting up Laya on a MacBook

Native Apple Silicon runtimes exist so inference uses Metal/the Neural Engine directly, no PyTorch or Transformers required:

- `laya-mlx` (github.com/mizorewww/laya-mlx, also on PyPI as `laya-mlx`) — MLX runtime, reports 7-14ms P50 per short decision on M3 Max. Requires macOS 14+, Python 3.11+.
  - Install: `pip install laya-mlx`
  - Load: `import laya_mlx as laya; agent = laya.load("aac6fef/laya-mlx")` (checkpoint pulled from Hugging Face on first use).
- `laya-coreml` (github.com/mizorewww/laya-coreml) — Core ML / Neural Engine port, ~5ms on M3 Max. Alternative to `laya-mlx` when Neural Engine (not GPU) execution is preferred; same project author.
- Original upstream checkpoint: `convaiinnovations/laya` on Hugging Face — the source weights both ports convert from.

Both ports are third-party (independent MLX/Core ML conversions), not published by Convai Innovations itself — check each repo's README for the current conversion/checkpoint compatibility before pinning a version.

Requirement to double check before starting: confirm the devcontainer's actual host is Apple Silicon (not Intel) — MLX and the Neural Engine path both need it.

## 2. MCP server for Laya

Yes, several already exist — this is a fragmented ecosystem (same pattern as the Kev/OpenJev forks from the earlier research), not one canonical project. Found on GitHub: `wsargent/laya-mcp`, `andragon3110/laya-mcp`, `NVentimiglia/laya-mcp`, `PerryLink/laya-mcp`, `EbiPenMan/laya-mcp`. No single one is marked official by Convai Innovations.

`wsargent/laya-mcp` looks the most complete from its description and is the one with published setup detail:

- Wraps `laya-mlx` and exposes it over MCP via `fastmcp`, transport is stdio.
- Ships two pieces: `laya-daemon` (persistent process, loads the checkpoint once, keeps one warm model resident) and `laya-cli` / the MCP server itself, which talk to the daemon so multiple consumers share one loaded model instead of each paying cold-start cost.
- Quoted install/run step: `uv run laya-daemon` starts the persistent process.
- First inference call downloads the ~3.4MB `convaiinnovations/laya` checkpoint into `~/.cache/huggingface`; tool listing/startup does not trigger the download (lazy load).

`PerryLink/laya-mcp`'s description ("warm model sidecar, token-budget preflight, persisted calibration, honest confidence") suggests it targets the same daemon-plus-MCP-wrapper shape; not compared in depth here.

Before adopting one: read the actual repo (not just the description), check commit recency/maintainer activity, and check license — this is unaudited third-party code pulling in a Hugging Face checkpoint at runtime.

## 3. Reaching the MCP server from both host-native and devcontainer agents

Two different cases, because a stdio-transport MCP server (what `laya-mcp` uses by default) only works for a client that can spawn it as a local subprocess:

**Host-native agents** (an agent running as a normal macOS process, not inside the devcontainer): stdio works as-is. Point the agent's MCP client config at the `laya-mcp` command directly (e.g. `uv run --project <path-to-laya-mcp> laya-mcp` or whatever the repo's actual entrypoint is — confirm exact invocation in its README) the same way any other local stdio MCP server is configured.

**Devcontainer agents**: stdio does not cross the container boundary — the devcontainer cannot spawn a process that only exists on the macOS host. Two options:

1. **Switch the server to a network transport and reach it by LAN IP.** `fastmcp` (what `laya-mcp` is built on) supports `streamable-http` in addition to stdio — this is a `fastmcp` capability in general, *not confirmed yet as already wired up in `laya-mcp`'s CLI*; check its source/README for an existing `--transport`/`--host`/`--port` flag before assuming it, and patch it in if missing. Run it bound to `0.0.0.0` on a fixed port on the Mac host (outside any container), then have the devcontainer's MCP client point at `http://<host-LAN-IP>:<port>/mcp`.
   - Do **not** use `localhost`/`127.0.0.1` or (unverified in this repo) `host.docker.internal` from inside the devcontainer to reach the Mac host — this project's own docs already flag that `localhost` from the devcontainer does not resolve to the Mac host (`.agent/docs/dev-workflows/gotchas.md:6-7`).
   - Get the host's LAN IP the same way the project's existing LAN-testing flow does: `local_ip.sh` / the `MOBILE_HOST` pattern documented in `.agent/docs/dev-workflows/docker-compose.md:44` for `make local-mobile-qr`/`make local-mobile-url`. Reuse that detection instead of hardcoding an IP.
2. **Run a second `laya-mcp` instance inside the devcontainer**, stdio-only, no cross-boundary networking needed. Not viable here: the devcontainer's Linux VM (Podman on macOS) has no Metal/Neural-Engine passthrough, so `laya-mlx`/`laya-coreml` can't accelerate inside it — it would fall back to slow CPU inference or fail to load, defeating the reason to pick Laya. Only worth it if a CPU-only Laya build turns out to be fast enough in practice (not verified).

Recommendation: option 1 (single host-side instance, HTTP transport, reached by LAN IP), since it matches the network pattern this project already uses for other host-to-devcontainer access and avoids running two separate model instances.

## Open items before implementation

- Confirm `laya-mcp`'s actual CLI/config surface (exact package name, entrypoint, whether an HTTP transport flag already exists) by opening the chosen fork's repo directly.
- Decide which `laya-mcp` fork to use, or whether to fork/patch one for the HTTP-transport requirement.
- Decide a fixed port and whether it needs firewall/Little Snitch allowances on macOS for LAN-bound traffic from the Podman VM.
