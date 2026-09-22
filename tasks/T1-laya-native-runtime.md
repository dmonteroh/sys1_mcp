# T1 — Set up native Laya runtime on the Mac host

## Description

Get a working native (Apple Silicon) Laya inference runtime installed and verified on this machine, outside any container, so later tasks (MCP server wrapper, devcontainer networking) have a real model to wrap. `convaiinnovations/laya` is a non-autoregressive typed-decision model (choice/score/noul, calibrated probabilities). Research (research.md, section 1) identifies two third-party Apple Silicon ports: `laya-mlx` (MLX runtime, PyPI package `laya-mlx`) and `laya-coreml` (Core ML/Neural Engine port), both by `mizorewww`, both unaudited third-party conversions of the upstream `convaiinnovations/laya` checkpoint.

## Source material

- `research.md` (repo root), section "1. Setting up Laya on a MacBook" — full context, quoted install commands, and explicit caveats that the commands are unverified quotes from README summaries, not run this session.

## Acceptance Criteria

- Confirm the actual host this will run on is Apple Silicon (not Intel); record how this was checked.
- Choose one runtime (`laya-mlx` or `laya-coreml`) with a stated reason, or document why both are needed.
- Verify the chosen package's real install/load instructions against its actual repo/PyPI page (not just the quoted README summary in research.md) before running anything.
- Install the chosen runtime and successfully load the `convaiinnovations/laya` checkpoint at least once.
- Run at least one real inference call and record the actual latency observed (compare against the claimed 7-14ms/~5ms figures).
- Record exact commands run and their real output in a setup note at `tasks/notes/T1-setup.md` (not the `.agent/` knowledge base, which is reserved for durable project knowledge per this repo's `CLAUDE.md`/`.agent/rules/contract.md`).
- `tasks/notes/T1-setup.md` is the artifact T2 reads to avoid re-deriving the verified runtime steps; no further discoverability mechanism is needed.
- Record in the setup note the three reproducibility anchors: the exact pinned package version installed, the Hugging Face checkpoint revision/commit hash actually resolved at load time, and the absolute path of the Python interpreter/venv the runtime lives in (T2 needs that path to invoke the runtime).

## Open items flagged by research (not yet resolved)

- Which runtime to standardize on (`laya-mlx` vs `laya-coreml`) is currently undecided.
- Neither port is published by Convai Innovations itself; current maintenance/version compatibility is unverified.

## Decisions (architect pass, 2026-09-22)

- Python-version handling is the implementer's call, not an operator question: if the chosen package does not support the host's Python 3.14.7, create an isolated venv with `uv` (already present, v0.12.1) pinned to the newest Python the package actually supports, and continue. An unsupported-3.14 finding is not a blocker and does not return QUESTIONS.
- Install into a dedicated `uv` venv by default even when 3.14 turns out to be supported. Rationale: it keeps an unaudited third-party package and its transitive deps out of the Homebrew site-packages, makes the runtime reproducible for T2, and is trivially reversible (delete the directory).
- Pin the package to an exact version (`==<version>`) once verified working. No `latest`, no unpinned install recorded as the working setup.
- Deeper security auditing (reading the package's source before install, checksum verification of the Hugging Face checkpoint) is explicitly out of scope for T1. Rationale: `.agent/purpose.md` frames this node as Daniel's solo, single-machine wrapper for third-party tooling, and its stated constraint is provenance ("a source and a date"), not an audit gate. Reproducibility of the exact artifact used is the bar here; cryptographic verification is not.
- Lightweight provenance is in scope and satisfies that bar: record repo URL, license, latest release/commit date, and stated Python/macOS support for the chosen package alongside the install commands.

## Implementation Constraints

- Verify the chosen package's real PyPI page / repo for supported Python versions and the actual install command *before* any install runs. research.md's "Requires macOS 14+, Python 3.11+" is an unverified README quote and must not be trusted as the support ceiling.
- Use `uv` for environment creation and installs. The venv lives outside the repo tree or in a gitignored path — do not commit an environment.
- Exactly one runtime is installed (`laya-mlx` or `laya-coreml`), with the reason recorded. Installing both is allowed only with a written justification in the setup note.
- No writes to `.agent/` in this task. Durable Laya knowledge is promoted separately; `tasks/notes/T1-setup.md` is the only artifact T1 produces.
- Commands are recorded verbatim with their real output. Nothing is written as verified until it has actually been run (`.agent/rules/contract.md`, Project guardrails).
- Latency is measured wall-clock on a real inference call and compared against the claimed 7-14ms / ~5ms figures; a mismatch is a finding to record, not a failure to hide.

## Sizing Budget

- Read scope: 6 files — `tasks/T1-laya-native-runtime.md`, `research.md` (53 lines, section 1 load-bearing), `tasks/T2-laya-mcp-server.md`, `tasks/T3-devcontainer-mcp-reachability.md`, `.agent/docs/architecture.md`, `.agent/docs/sources.md`. Plus the chosen package's live PyPI/repo page (external, not a repo file).
- Concern axes: 1 (install and verify one native runtime) — target 1, cap 2 — within target.
- Acceptance criteria: 8 — target 8, cap 12 — within target.
- Files created/modified: 2 (`tasks/notes/T1-setup.md` created; `tasks/T1-laya-native-runtime.md` appended, this refinement pass only) — target 6, cap 10 — within target.
- Independent failure classes: 1 (package/Python-version compatibility of the chosen port) — target 1, cap 2 — within target.
- Files in read set: 6 — target 10, cap 20 — within target.
- Verdict: within target on every measure; no cap breached; no split needed.

## Execution Gates

- Blocked by: none. T1 has no upstream task dependency.
- Order constraints: T1 must complete before T2 starts — T2 hard-depends on `tasks/notes/T1-setup.md` existing and on the interpreter path it records.
- Dispatchability: dispatchable.
- Follow-up tasks: none.
- Claims (files): `tasks/notes/T1-setup.md` (create, plus `tasks/notes/` directory), `tasks/T1-laya-native-runtime.md` (append — this refinement pass only, not the implementer's).
- Claims (non-file write surfaces, outside the repo, on the user's machine): installs one PyPI package (`laya-mlx` or `laya-coreml`) and its transitive dependencies into a `uv`-managed venv; may install an additional CPython version via `uv python install`; downloads the `convaiinnovations/laya` checkpoint into `~/.cache/huggingface`.
- Verification commands (argument arrays; `<pkg>`, `<version>`, `<pyver>` filled in from the step-2 verification):
  - `["uname", "-m"]` — expect `arm64`
  - `["sw_vers"]` — record `ProductVersion`
  - `["uv", "venv", "--python", "<pyver>", "<venv-path>"]`
  - `["uv", "pip", "install", "--python", "<venv-path>", "<pkg>==<version>"]`
  - `["uv", "pip", "freeze", "--python", "<venv-path>"]` — captures the exact resolved dependency set
  - `["<venv-path>/bin/python", "-c", "import time, laya_mlx as laya; a = laya.load('<checkpoint>'); t = time.perf_counter(); r = a.choice('<probe prompt>', ['yes', 'no']); print('latency_ms', (time.perf_counter() - t) * 1000); print('result', r)"]` — real load plus one real inference call with wall-clock latency; adjust the import/API to the verified surface of the chosen package
  - `["find", "~/.cache/huggingface", "-name", "*.json", "-path", "*laya*"]` or the package's own revision accessor — resolve and record the checkpoint revision/commit hash actually loaded
- Done when: all 8 acceptance criteria hold and `tasks/notes/T1-setup.md` contains the commands, their real output, the chosen runtime and reason, the pinned version, the HF revision, the interpreter path, and the observed latency.
