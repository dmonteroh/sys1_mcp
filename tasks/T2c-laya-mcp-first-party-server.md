# T2c — Design, implement, and verify a first-party Laya MCP server (stdio)

## Description

Replaces adopting a third-party fork (T2b, superseded) with a first-party `fastmcp`
package this project owns outright, wrapping the `laya-mlx` runtime T1 verified. Operator
direction, 2026-09-22 (`tasks/notes/T2a-fork-selection.md` §7): none of the eight forks
T2a vetted are a clean 1:1 match — the closest architectural fit, `wsargent/laya-mcp`,
was disqualified in T2a only for a missing `LICENSE` file (likely an oversight per the
operator, unconfirmed here), and the fork T2a did select (`devthinker-ai/laya-mcp`) has no
HTTP transport at all, meaning T3b would have meant writing a real protocol implementation
on top of someone else's 3-commit repo anyway. The operator explicitly authorized reading
`wsargent/laya-mcp`'s source (already done, in the same session that produced this task)
and reimplementing whatever is useful from it — not adopting or redistributing that repo,
since its licensing status is unresolved.

This task covers the tool surface, the package skeleton, and the stdio transport only.
`streamable-http` is T3d's job — but the server this task builds is the same server T3d
adds a transport to, per the design decision below, so this task's structure directly
determines how easy T3d is.

## Source material

- `tasks/notes/T1-setup.md` — the verified `laya-mlx` runtime, pinned version, checkpoint,
  and interpreter path this server calls into.
- `tasks/notes/T2a-fork-selection.md` (including its §7 addendum) — why no fork was
  adopted, and what's authorized to reuse.
- `wsargent/laya-mcp` (`github.com/wsargent/laya-mcp`, read directly 2026-09-22, no
  license file — reimplement ideas, do not copy files or vendor code):
  - `src/laya_mcp/server.py` — one shared `FastMCP("laya")` app; tools call a `_predict()`
    helper that is daemon-first (forwards to `LAYA_DAEMON_URL` if set, else lazy-loads
    the agent locally); a module-level `threading.Lock` serializes inference calls.
  - `src/laya_mcp/daemon.py` — imports `server`, attaches `/health` (readiness: 503 until
    the model is loaded, 200 after) and `/predict` (plain-JSON POST) routes via
    `@server.mcp.custom_route(...)`, primes the agent eagerly, then calls
    `server.mcp.run(transport="http", host=HOST, port=PORT)` — the *same* `FastMCP`
    instance the stdio entrypoint runs, just a different `.run()` call.
  - `src/laya_mcp/cli.py` — a `click` CLI driving either transport through `fastmcp`'s own
    `Client`/`StdioTransport`/`StreamableHttpTransport` — reference only, not required
    (see Implementation Constraints; this task does not build a CLI).
  - Its `pyproject.toml` declares `dependencies = ["laya-mlx>=0.1.0", "fastmcp[code-mode]>=4.0.5", "httpx>=0.27", "click>=8.1", "beartype>=0.22.9"]` and two scripts, `laya-mcp` and `laya-daemon`.
- `.agent/docs/sources.md` — the fork rows T2a verified, useful for what *not* to
  reimplement (e.g. PerryLink's CUDA-fallback handling doesn't apply; we only run on MLX).

## Acceptance Criteria

- Decide and record the package's name, location in this repo, and install mechanism —
  see Implementation Constraints (`Package identity`) for the fixed decisions; write the
  reasoning and any deviation into `tasks/notes/T2c-design.md`.
- Design the tool surface for v1: a single generic tool, `laya_decide(state, questions)`,
  matching `laya-mlx`'s own `agent.predict(text, schema_dict)` signature (verified in
  `tasks/notes/T1-setup.md` §3) — one tool, not five. Record in the design note why the
  preset tools wsargent (`laya_triage`/`laya_guard`/`laya_moderate`/`laya_email`) and
  NVentimiglia (`check_guardrails`/`route_task`/`evaluate_pr_diff`/`moderate_content`)
  ship are deferred: no consumer in this project needs them yet, and `laya_decide` already
  expresses every question type (`choice`/`score`/`noul`) they're built from.
- Structure the server as one `fastmcp.FastMCP` app object with the tool(s) registered on
  it, callable via `.run()` for stdio and `.run(transport="http", host=..., port=...)` for
  HTTP — reimplementing `wsargent`'s server/daemon split (shared app, thin entrypoints),
  not devthinker-ai's hand-rolled two-script approach. T3d must be able to add the HTTP
  entrypoint without touching the tool definitions.
- Reimplement the daemon-first inference pattern: an optional `LAYA_DAEMON_URL` env var
  makes the stdio server forward each call to a running daemon's plain-JSON endpoint
  instead of loading its own model copy, falling back to a local lazy load if the daemon
  is unreachable. Record the fallback behavior explicitly (silent fallback vs. logged
  fallback — decide and state which, then implement it).
- Reimplement single-flight inference locking (a lock around every call into the loaded
  agent), since `agent.predict`'s thread-safety is undocumented (per T1's finding).
- Install the package (editable, from this repo's own tree — see Implementation
  Constraints) against T1's verified `laya-mlx==0.1.0` install, and confirm the venv
  resolves both packages together without conflict.
- Start the stdio server and complete at least one real end-to-end tool call: a real
  request, and a real response produced by the `laya-mlx` checkpoint T1 verified, not a
  stub or mock. Record the request, the response, and the observed latency.
- Record every command and its real output, the design decisions, and the verified
  install/entrypoint facts in `tasks/notes/T2-setup.md` (same filename T2b would have
  produced — T3/T3c's existing Source material pointers keep working unchanged) and
  `tasks/notes/T2c-design.md` (the design record specific to this task).
- Update `.agent/docs/sources.md` with one row for this first-party package (source: this
  repo, not an external one — cite the path, not a URL) once it exists.

## Implementation Constraints

**Package identity.** Lives in this repo at `laya-mcp/` (a self-contained Python package,
its own `pyproject.toml`, not a subpackage of anything else this node might add later).
Package name: pick one that is not already claimed on PyPI (`https://pypi.org/pypi/<name>/json`
returning 404 confirms this — check before writing it into `pyproject.toml`, precisely the
check `devthinker-ai/laya-mcp` skipped, per `tasks/notes/T2a-fork-selection.md` §4). This
package is **never published to PyPI**: install it with `uv pip install -e ./laya-mcp` (or
equivalent editable/local install) into the same venv style T1 used, or its own venv if
dependency conflicts require it. This sidesteps the exact namespacing failure mode found in
T2a — there is no README instruction that could resolve to someone else's package, because
there is no PyPI entry to resolve to.

**Boundary note (flag, do not resolve here).** `.agent/purpose.md`'s Boundaries line
currently states this node "documents the local tool wrapper only ... not any application
code that might later live in this repo." This task adds real application code
(`laya-mcp/`). Update that line as part of this task's own `.agent/` bookkeeping once the
package exists — do not leave the boundary statement contradicting the repo's actual
contents.

**Reference vs. reuse.** `wsargent/laya-mcp` carries no license file (verified in T2a and
re-confirmed 2026-09-22: no `license` field in its `pyproject.toml`, nothing in its README,
GitHub's license-detection API returns none). Read it for architecture and reimplement the
*ideas* (shared app object, daemon-first forwarding, custom health/predict routes,
single-flight lock) in this project's own code, in this project's own words. Do not copy
files, docstrings, or nontrivial code fragments verbatim from it.

**The end-to-end call must hit the real runtime.** Same as T2b's original constraint: the
response must come from the `laya-mlx`-loaded checkpoint, not a stub.

**Negative scope.**
- No HTTP/`streamable-http` transport, no port binding — T3d owns that. Structure the code
  so T3d can add it without a rewrite, but do not add it here.
- No CLI (`laya-cli` equivalent) — reference-only from `wsargent/laya-mcp`'s `cli.py`; not
  a requirement. `fastmcp`'s own `Client` is sufficient for verification scripts.
- No Code Mode / meta-tool transform — out of scope, no current consumer need.
- No preset tools (`laya_triage` etc.) — deferred, see Acceptance Criteria.
- No re-evaluation of T1's runtime choice (`laya-mlx`) or T2a's rubric/facts.

**Deployment context.** Runs natively on the Apple Silicon Mac host, outside any
container, same as T1/T2b.

**Playbook.**
1. Read `tasks/notes/T1-setup.md` (runtime, interpreter path, checkpoint) and
   `tasks/notes/T2a-fork-selection.md` (including §7) before designing anything.
2. Check candidate package names against PyPI's JSON API; pick one with a 404 (confirmed
   unclaimed) and record the check.
3. Scaffold `laya-mcp/` with `pyproject.toml` (name, version, `fastmcp` + `laya-mlx`
   dependencies, one console script), reusing wsargent's dependency shape as a starting
   point, adjusted to only what's actually used (no `click`/`beartype` unless something
   here needs them).
4. Write the server module: one `FastMCP` app, one `laya_decide` tool, the daemon-first
   `_predict()` helper with `LAYA_DAEMON_URL` forwarding and local lazy-load fallback, and
   the single-flight lock. Cite `wsargent/laya-mcp`'s files as the design reference in
   code comments only where the *why* isn't obvious (e.g. why the lock exists), never
   copying its text.
5. Install editable into a venv alongside T1's verified `laya-mlx==0.1.0` (reuse T1's venv
   if no conflict, else create a new one and record why).
6. Run the stdio server, list tools, and call `laya_decide` once with a real input.
   Capture the request, response, and latency.
7. Write `tasks/notes/T2c-design.md` (decisions: package name/location, tool surface,
   deferred features, forwarding-fallback behavior) and `tasks/notes/T2-setup.md` (every
   command, real output, the verified stdio invocation for T3d/T3).
8. Update `.agent/docs/sources.md` (new first-party row) and `.agent/purpose.md`
   (Boundaries line).

## Sizing Budget

- Concern axes: 1 — build and verify one first-party stdio server. within-target (matches
  T1's precedent of combining design + install + verify in one task when the work is
  additive/forward-building rather than investigatory-branching).
- Acceptance criteria: 8. within-target.
- Estimated file touch count: 5 — `laya-mcp/pyproject.toml`, the server module,
  `tasks/notes/T2c-design.md`, `tasks/notes/T2-setup.md`, `.agent/docs/sources.md`, plus
  `.agent/purpose.md`'s Boundaries line. Slightly above most prior tasks' count because
  this is the first task that adds real source code to the repo; still one concern axis.
- Independent failure classes: 1 — the server fails to load the runtime or answer a real
  call. within-target.
- Read scope: `tasks/notes/T1-setup.md`, `tasks/notes/T2a-fork-selection.md`, and
  `wsargent/laya-mcp`'s four source files (already fetched this session) — within-target.

## Execution Gates

- Blocked by: T1 (`tasks/notes/T1-setup.md`). T2a is background/reference only — its
  selection was overridden, but its rubric facts and the `wsargent` source excerpts remain
  the design input.
- Order constraints: after T1, before T3d.
- Dispatchability: **ready** (T1's setup note already exists).
- Follow-up tasks: T3d.
- Claims: files — `tasks/T2c-laya-mcp-first-party-server.md`, `laya-mcp/` (new package),
  `tasks/notes/T2c-design.md`, `tasks/notes/T2-setup.md`, `.agent/docs/sources.md`,
  `.agent/purpose.md`. Non-file — installs a first-party editable package into the host
  environment; no port binding, no network listener, no credential claims.
- Verification commands:
  - `["test", "-d", "laya-mcp"]`
  - `["test", "-f", "tasks/notes/T2c-design.md"]`
  - `["test", "-f", "tasks/notes/T2-setup.md"]`
  - `["grep", "-Eq", "laya_decide", "tasks/notes/T2-setup.md"]`
  - Manual: the chosen package name returns 404 on `https://pypi.org/pypi/<name>/json`,
    and the note records that check.
  - Manual: re-run the recorded stdio invocation and confirm the server starts, lists
    `laya_decide`, and one real call returns a real model-produced answer with a latency
    figure.
  - Manual: no file under `laya-mcp/` is a verbatim copy of a `wsargent/laya-mcp` file —
    spot-check against the fetched source in this session's transcript if in doubt.
