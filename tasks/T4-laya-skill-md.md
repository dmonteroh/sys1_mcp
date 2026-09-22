> **Status: queued, not yet refined.** Hard-blocked until T1, T2b, and T3's children are all complete and verified — this task needs real, verified facts to write from, not the unverified claims in research.md or in third-party skill files. Do not dispatch task-refinement on this until that gate clears.

# T4 — Write a project-specific SKILL.md for using Laya

## Description

Write our own `SKILL.md` (or equivalent agent-skill file) teaching coding agents how to use this project's verified Laya setup: the real API shape, real observed latencies, real calibration/confidence behavior, and any "traps" found while standing it up. Grounded entirely in what T1/T2/T3 actually verified on this machine, not in unverified upstream claims.

## Why not adopt an existing one

Two third-party candidates were found and explicitly rejected as a source to trust directly (operator decision, 2026-09-22):

- `wangmiaozero/laya-router-skill` — bundles a `SKILL.md` + small local MCP runtime, but scoped to task-routing (classifying request complexity/domain/risk), not general Laya usage. Apache-2.0, only 2 commits visible, explicitly disclaims affiliation with Convai Innovations.
- `wdobry/laya-playground` (`skills/laya-integration/SKILL.md`) — closer in shape (covers API, thresholds, calibration, "traps"), but third-party, unrelated to Laya's actual author, unverified against this project's own setup. MIT.

Neither is official — Laya's own README/HF page (`convaiinnovations/laya`) does not reference any agent skill file. A `SKILL.md` is instructions fed directly to agent behavior, a higher trust bar than a library dependency, so neither is adopted unvetted.

## Source material (once unblocked)

- `tasks/notes/T1-setup.md` — verified runtime, pinned version, observed latency.
- `tasks/notes/T2-setup.md` — verified MCP server entrypoint/invocation, real request/response example.
- `tasks/notes/` outputs from T3's children — verified transport/reachability facts.
- `wdobry/laya-playground`'s `skills/laya-integration/SKILL.md` — may be read for structural ideas only (how it organizes API/thresholds/calibration/traps sections), cited and dated like any other external source per `.agent/rules/contract.md`; its factual claims are not trusted without independent verification against this project's own setup.
- The `typesafe-ai/skills` `SKILL.md` (`typesafe-ai/skills` repo) as a structural reference point for what a good agent-facing skill file looks like (programming model, documentation navigation, worked patterns, composition/verification) — structure only, not content, since it documents a different product.

## Acceptance Criteria (draft — to be refined once unblocked)

- `SKILL.md` documents only verified facts from this project's own T1/T2/T3 setup notes, each traceable to the note that verified it.
- Covers: how to invoke the verified MCP server (real tool names/shapes), real observed latency, how confidence/calibration values actually behaved in the real test calls, and any setup "traps" found across T1-T3.
- Explicitly marks anything carried from a third-party skill's structure (not content) as such.
- Does not restate unverified research.md claims as fact.

## Open items

- Exact target location/format (`.claude/skills/`, a repo-root `SKILL.md`, or another convention) is undecided and should be resolved during this task's own refinement pass, not now.
