# T2a — Vet the five laya-mcp forks and select one

## Description

Decide which existing third-party Laya MCP server fork this project adopts, by opening the actual repositories rather than relying on research summaries. Research (research.md, section 2) names five forks — `wsargent/laya-mcp`, `andragon3110/laya-mcp`, `NVentimiglia/laya-mcp`, `PerryLink/laya-mcp`, `EbiPenMan/laya-mcp` — none marked official, and describes all five only from search-result summaries of their READMEs. This task replaces that with verified facts and one recorded decision. It installs nothing and runs nothing.

Parent task: T2 (superseded by this task and T2b).

## Source material

- `research.md` (repo root), section "2. MCP server for Laya" — the candidate list and the unverified descriptions this task checks.
- `tasks/notes/T1-setup.md` — which native runtime T1 standardized on; rubric criterion 5 depends on it.
- `.agent/docs/sources.md` — the existing catalog rows for these forks, which this task updates.

## Acceptance Criteria

- Open each of the five candidate repos directly (the repository itself, not a search-result summary) and record for each: archived state, license, date of the most recent commit, documented package name and entrypoints, and which Laya runtime it wraps.
- Apply the five rubric criteria below and record pass/fail per criterion per fork as a table in the note.
- Select one fork and state the reason in one sentence, or record that none qualify.
- For the selected fork, record the exact install commands, the daemon entrypoint, and the MCP-server entrypoint as stated in its own README or source, each with the URL or file path it came from, plus the commit SHA T2b must pin to.
- Record whether the selected fork's CLI already exposes an HTTP/`streamable-http` transport or host/port flag. This is a fact for T3; do not act on it here.
- Write all of the above to `tasks/notes/T2a-fork-selection.md`.
- Update `.agent/docs/sources.md`: flip every fork row actually opened from `reported` to `verified` with today's date and what was seen, splitting the combined four-fork row into per-fork rows where the facts now differ.
- If no fork qualifies, do not adopt one: record the rubric table, return blocked, and present the three options below with the stated default.

## Implementation Constraints

**Selection rubric.** A fork qualifies only if all five hold:

1. A license file is present and is permissive and compatible with upstream Laya's Apache-2.0 — Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, or ISC. No license file, or GPL/AGPL, fails.
2. The repository is not archived and carries commits of its own beyond the fork point.
3. It has at least one commit on or after 2025-09-22 (12 months back from 2026-09-22). Chosen default, not measured: the ecosystem is new enough that a stricter window would likely disqualify every candidate.
4. Its package name, daemon entrypoint, and MCP-server entrypoint are stated in its own README or source — not inferred from `research.md`.
5. It wraps the runtime T1 standardized on, or its runtime backend is swappable within a patch confined to configuration or entrypoint wiring in a single file.

Tie-break among qualifying forks, in order: most recent commit, then closest match between its documented CLI and its actual source, then fewest external dependencies.

**Reference pattern.** Every recorded fact cites the URL or file path it came from and is marked `(inferred)` when not directly confirmed by opening that source, per `.agent/rules/contract.md` Output conventions.

**Negative scope.**
- Do not install any package, clone any repo for execution, or run any command from any fork.
- Do not start a daemon or an MCP server; that is T2b.
- Do not implement, patch, or configure HTTP/network transport; that is T3.
- Do not patch the selected fork. A fork needing more than single-file configuration or entrypoint wiring fails criterion 5.
- Do not write `tasks/notes/T2-setup.md`; that file belongs to T2b.

**If no fork qualifies.** Do not force-adopt one. Record the full rubric table, return blocked, and present these options to the operator:
- (a) adopt the least-bad fork with each failed criterion named as an accepted exception;
- (b) **stated default** — open a new task to write a minimal first-party `fastmcp` wrapper around T1's runtime;
- (c) drop the MCP-server line of work.

**Deployment context.** Read-only investigation from the Mac host. Network access to github.com is required; if unavailable, the task blocks on the first criterion.

**Playbook.**
1. Read `tasks/notes/T1-setup.md` and note which runtime T1 standardized on.
2. Read `research.md` section 2 and `.agent/docs/sources.md`.
3. For each of the five forks, open the repo page, its README, its license file, and its commit list. Record the five rubric inputs plus the entrypoint names.
4. For each fork, mark pass/fail per criterion.
5. Apply the tie-break to the qualifying set, or take the no-qualifier branch above.
6. For the winner, pull the exact install commands, entrypoints, latest commit SHA, and any existing transport flag from its own README or source.
7. Write `tasks/notes/T2a-fork-selection.md`: the rubric table, the decision with its one-sentence reason, the verified install/entrypoint facts with sources, the pinned SHA, and the transport-flag finding.
8. Update the `laya-mcp` rows in `.agent/docs/sources.md` to `verified` for every repo opened.

## Sizing Budget

- Concern axes: 1 — external-source investigation and a recorded decision. within-target.
- Acceptance criteria: 8. within-target.
- Estimated file touch count: 2 — `tasks/notes/T2a-fork-selection.md`, `.agent/docs/sources.md`. within-target.
- Independent failure classes: 1 — candidate repos unreachable or too sparse to judge. "None qualify" is a defined completion, not a failure. within-target.
- Read scope: 4 local files, largest `research.md` at 53 lines. within-target. Non-file addendum: five external GitHub repos are read; the rubric bounds what must be extracted from each.

## Execution Gates

- Blocked by: T1 — `tasks/notes/T1-setup.md` must record the chosen runtime before the selection is final. Criteria 1-4 may be gathered before T1 lands.
- Order constraints: after T1, before T2b.
- Dispatchability: blocked (until T1's setup note exists).
- Follow-up tasks: T2b.
- Claims: files — `tasks/T2a-laya-mcp-fork-selection.md`, `tasks/notes/T2a-fork-selection.md`, `.agent/docs/sources.md`. Non-file — read-only network access to five public GitHub repositories. No process, port, service, or credential claims.
- Verification commands:
  - `["test", "-f", "tasks/notes/T2a-fork-selection.md"]`
  - `["bash", "-c", "for f in wsargent andragon3110 NVentimiglia PerryLink EbiPenMan; do grep -q \"$f\" tasks/notes/T2a-fork-selection.md || { echo \"missing $f\"; exit 1; }; done"]`
  - `["grep", "-Eiq", "selected|none qualify", "tasks/notes/T2a-fork-selection.md"]`
  - `["bash", "-c", "git diff --name-only -- .agent/docs/sources.md | grep -q sources.md"]`
  - Manual: the note states a commit SHA for the selected fork, and the install command and both entrypoints each cite the URL or file path they came from.
  - Manual: no package was installed and no fork process was started.
  - Manual: the note records whether the selected fork's CLI already exposes a transport/host/port flag.
