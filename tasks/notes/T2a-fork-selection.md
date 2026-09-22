# T2a — Fork selection note

Produced 2026-09-22. Runtime T1 standardized on: `laya-mlx==0.1.0` (`tasks/notes/T1-setup.md`).

> **§4's selection below is overridden — see §7.** This note's rubric picked
> `devthinker-ai/laya-mcp` as the only fork passing all five criteria. The operator then
> overrode that: build a first-party server, reusing `wsargent/laya-mcp`'s design (§7). No
> fork from this note is adopted. Current tasks: `tasks/T2c-laya-mcp-first-party-server.md`,
> `tasks/T3d-mcp-http-transport-first-party.md`.

## 1. Fresh search (beyond the five named candidates)

Searched GitHub via `gh search repos` for `laya-mcp`, `laya mcp server`, `laya-mlx mcp`,
with particular attention to Apple Silicon/`laya-mlx`/`laya-coreml`-specific forks, on
2026-09-22.

`laya mcp server` and `laya-mlx mcp` as literal `gh search repos` queries returned zero
results (GitHub's search API does not do free-text README search this way); the plain
`laya-mcp` query surfaced the real field. Found beyond the five in `research.md`:

- `devthinker-ai/laya-mcp` — wraps `laya-mlx` directly (Apple-Silicon-specific, matches T1's runtime exactly).
- `jerepaira/laya-mcp` — wraps upstream `laya` (PyTorch/CUDA), 1 commit.
- `rdutra/laya-mcp` — wraps `laya-coreml` (the runtime T1 did *not* pick), Apple-Silicon-specific but wrong backend.
- Several out-of-scope name collisions/adjacent projects, excluded as not being a generic Laya-MCP wrapper fork: `layabox/LayaAir-mcp-plugin` (unrelated game-engine project, false-positive name match, archived), `neko233-com/laya-go` (independent Go reimplementation, not a fork of the Python/MCP lineage), `ChenneyZhuang/laya-browser-agent` (browser-automation agent, "MCP-friendly" but not itself an MCP server), `F0Rextasy/omp-laya-judge` and `Pidbid/laya-deploy` (scoped to specific third-party harnesses/bridges, not general-purpose wrappers), `PerryLink/laya-mcp-npm` (a Node stdio passthrough shim for PerryLink's own `laya-mcp`, not a separate fork).

All eight real candidates (five named + three new) opened directly below.

## 2. Per-fork facts (opened directly, 2026-09-22)

| Fork | Archived | License file | Latest commit (date, sha) | Package / entrypoints | Runtime wrapped |
|---|---|---|---|---|---|
| `wsargent/laya-mcp` | no | **none** (checked `contents/LICENSE`, 404) | 2026-09-21, `ea1fab1` | not evaluated further — fails criterion 1 | laya-mlx (per repo description) |
| `andragon3110/laya-mcp` | no | LICENSE present, MIT | 2026-09-21, `cb70301` (14 commits) | Python+Node hybrid, 11 MCP tools (Laya + GLiNER2.5), package name not confirmed from README excerpt | generic HF-backed Laya usage, no MLX mention found; not confirmed to wrap `laya-mlx` |
| `NVentimiglia/laya-mcp` | no | LICENSE present, MIT | 2026-09-19, `fcd0046` (3 commits) | `pip install laya-mcp`, 5 tools (`evaluate_decision`, `check_guardrails`, `route_task`, `evaluate_pr_diff`, `moderate_content`) | PyTorch/CUDA (README documents an RTX-50-series/cu128-nightly GPU path) — not `laya-mlx` |
| `PerryLink/laya-mcp` | no | LICENSE present, Apache-2.0 | 2026-09-21, `1f8fe2f` | `pip install 'laya-mcp[mcp]'`, entrypoint `laya-mcp serve` (binds `127.0.0.1:8787` itself), on PyPI as `laya-mcp` v0.2.1 (`requires_dist`: `laya`, `fastapi`/`uvicorn` under `server` extra, `mcp` under `mcp` extra) | PyTorch, with a documented CUDA-OOM→CPU-fp32 fallback path — not `laya-mlx` |
| `EbiPenMan/laya-mcp` | no | **none** (checked `contents/LICENSE`, 404) | 2026-09-20, `b2be956` (1 commit, message `init`) | not evaluated further — fails criterion 1 | unknown |
| `devthinker-ai/laya-mcp` | no | LICENSE present, MIT | 2026-09-21, `20136b3` (3 commits) | PyPI/`pyproject.toml` name `laya-mcp` v0.2.0; scripts `laya-mcp = laya_mcp_server:main`, `laya-http = laya_http_server:main`; `dependencies = ["laya-mlx"]` | **`laya-mlx`** — direct dependency, matches T1 exactly |
| `jerepaira/laya-mcp` | no | LICENSE present, MIT | 2026-09-21, `26db041` (1 commit) | `pip install git+https://github.com/jerepaira/laya-mcp.git`, stdio command `laya-mcp`; `dependencies = ["laya>=0.3.4", "mcp>=2.0"]` | upstream `laya` (pulls `torch`, CUDA-capable) — not `laya-mlx` |
| `rdutra/laya-mcp` | no | LICENSE present, Apache-2.0 | 2026-09-21, `5704feb` (5 commits) | venv install, entrypoint `laya-mcp`; `dependencies = ["laya-coreml>=0.1.0,<0.2", "mcp>=2.2.0,<3"]` | `laya-coreml` — the runtime T1 evaluated but did **not** pick (Python-version constraint, see `tasks/notes/T1-setup.md` §2) |

Sources: each repo's own GitHub API contents (`LICENSE`, `pyproject.toml`), its README via
`repos/<fork>/readme`, and its commit list via `repos/<fork>/commits`, all fetched directly
on 2026-09-22 — not research.md's summaries and not search-result text.

## 3. Rubric table (pass/fail per criterion)

Criteria: 1=license, 2=not archived + real commits, 3=commit ≥2025-09-22, 4=documented package/entrypoints, 5=wraps T1's runtime (`laya-mlx`) or single-file-swappable.

| Fork | 1 | 2 | 3 | 4 | 5 | Qualifies |
|---|---|---|---|---|---|---|
| `wsargent/laya-mcp` | FAIL (no license file) | — | — | — | — | no |
| `andragon3110/laya-mcp` | pass | pass | pass | partial (11-tool surface, name unconfirmed) | FAIL (not confirmed laya-mlx; broad multi-tool architecture) | no |
| `NVentimiglia/laya-mcp` | pass | pass | pass | pass | FAIL (PyTorch/CUDA, not laya-mlx) | no |
| `PerryLink/laya-mcp` | pass | pass | pass | pass | FAIL (PyTorch, CUDA-OOM/CPU fallback, not laya-mlx) | no |
| `EbiPenMan/laya-mcp` | FAIL (no license file) | — | — | — | — | no |
| **`devthinker-ai/laya-mcp`** | **pass** | **pass** | **pass** | **pass** | **pass** | **yes** |
| `jerepaira/laya-mcp` | pass | pass (1 commit; not archived, no fork-point ancestry visible via API to check "beyond fork point" literally, but repo is original, not a GitHub fork object) | pass | pass | FAIL (upstream `laya`/torch, not laya-mlx) | no |
| `rdutra/laya-mcp` | pass | pass | pass | pass | FAIL (wraps `laya-coreml`, the runtime T1 explicitly did not choose; Core ML API differs enough from MLX's `agent.predict()` surface that a swap is not a single-file config change) | no |

## 4. Decision (this task's rubric outcome — overridden by the operator, see §7)

**Selected by this task's rubric: `devthinker-ai/laya-mcp`**, pinned at commit `20136b3f3a0bf16270895ff27f982b0e83aea45c` — the only candidate that passes all five rubric criteria, chiefly because it is the only fork whose own `pyproject.toml` declares a direct dependency on `laya-mlx`, the exact runtime T1 verified. **Not adopted** — the operator overrode this in favor of a first-party build referencing `wsargent/laya-mcp` instead (§7). The facts below (install commands, transport finding) are kept as the verified record of what T2a found, not as instructions for T2b (superseded).

### Install commands, entrypoints, and their sources

- **Repo**: `https://github.com/devthinker-ai/laya-mcp`, pinned commit `20136b3f3a0bf16270895ff27f982b0e83aea45c` (`main`, 2026-09-21T22:37:54Z).
- **Package name**: `laya-mcp`, version `0.2.0` — per its own `pyproject.toml` (`[project] name = "laya-mcp"`, fetched via `repos/devthinker-ai/laya-mcp/contents/pyproject.toml`).
- **MCP-server entrypoint**: console script `laya-mcp = "laya_mcp_server:main"` (stdio, newline-delimited JSON-RPC 2.0) — per the same `pyproject.toml`, `[project.scripts]`.
- **Companion HTTP entrypoint**: console script `laya-http = "laya_http_server:main"` — a **plain REST API** (`/decide`, `/score`, `/is_true`, `/health`), not an MCP transport. Recorded for T3b's awareness, not as an MCP transport candidate (see §5).
- **⚠ Do not use the README's own quoted install command as written.** Its README says `uvx --from laya-mcp laya-mcp`, but PyPI's `laya-mcp` name is already registered by a different, unrelated project — `PerryLink/laya-mcp` v0.2.1 (verified via `https://pypi.org/pypi/laya-mcp/json`, `project_urls.Homepage` = `github.com/PerryLink/laya-mcp`). Running devthinker-ai's own README command as written would silently install PerryLink's package (different tools, different entrypoint shape), not devthinker-ai's code. **T2b must install from git at the pinned commit instead**: `pip install git+https://github.com/devthinker-ai/laya-mcp.git@20136b3f3a0bf16270895ff27f982b0e83aea45c`.

### Transport-flag finding (fact for T3, not acted on here)

`laya_mcp_server.py` (read directly, pinned SHA) is a hand-rolled stdio JSON-RPC loop — it does not use `fastmcp` and has **no `--transport`, `--host`, or `--port` flag of any kind**. It is stdio-only, fixed. The separate `laya_http_server.py` binds `127.0.0.1:8901` by default (`LAYA_ADDR` env var) but speaks plain REST JSON, not MCP's `streamable-http`/JSON-RPC-over-HTTP wire format — it cannot stand in for an MCP HTTP transport without a protocol rewrite, not a flag. T3b will need to **add** `streamable-http` support to `laya_mcp_server.py` itself (a real patch, not flipping an existing flag) if this fork stays selected; there is no existing flag to "confirm."

## 5. Notes for T2b/T3b

- No separate daemon process exists in this fork — `laya_mcp_server.py` lazily loads the model itself, singleton in-process (`AGENT` global). "Daemon" and "MCP server" are the same process here, unlike the `wsargent`-style daemon+CLI split `research.md` originally described (and `wsargent` is disqualified anyway, see §3).
- This fork is 3 commits old, single-author (`Parham Abbasi`), created within the same 2026-09-19–2026-09-22 window as every other candidate found in this search — this whole ecosystem is very new and largely unvetted beyond what's checked here (license/commit-recency/entrypoint facts only, no code-quality or security audit, per this task's explicit scope).
- Model default in this fork is `aac6fef/laya-multilingual-mlx`, not the `aac6fef/laya-mlx` (English) checkpoint T1 verified. T2b should set `LAYA_MODEL=aac6fef/laya-mlx` to match T1's verified checkpoint, or explicitly decide to use the multilingual one and note the deviation.

## 6. Sources.md update

Applied in the same change: `.agent/docs/sources.md`'s combined four-fork row is split into
per-fork rows, all eight candidates opened above are marked `verified` with today's date,
and the three newly found candidates are added.

## 7. Addendum, 2026-09-22 (operator override — decision reversed)

The operator directed a different path after reviewing this note: build a first-party
wrapper instead of adopting `devthinker-ai/laya-mcp`, once it became clear that (a) the
architecturally closest match, `wsargent/laya-mcp`, was disqualified only on a missing
`LICENSE` file, likely an oversight rather than an intentional all-rights-reserved choice
(operator's own assessment; unconfirmed here — re-checked directly on 2026-09-22 and found
no `license` field in its `pyproject.toml`, no license text in its README, and GitHub's own
license-detection API returns none either, so this remains the operator's inference, not a
verified fact), and (b) `devthinker-ai/laya-mcp` has no HTTP transport at all — T3b would
have meant writing real `streamable-http` support on top of a ~200-line, 3-commit,
single-author repo, which is most of the work of a first-party build anyway.

**This section does not change the rubric or the per-fork facts above** — those still hold
as the verified record of what was checked. It records that the operator's decision, for
this project, is to proceed differently: study `wsargent/laya-mcp`'s design directly
(operator-authorized investigation of its source, 2026-09-22, reimplementing what's useful
rather than adopting or redistributing it) and build a first-party MCP server. Superseding
tasks: `tasks/T2c-laya-mcp-first-party-server.md` (replaces T2b) and
`tasks/T3d-mcp-http-transport-first-party.md` (replaces T3b).
