# T3a — Follow-ups

Append-only. One entry per minor finding, dated.

- 2026-09-22 | code-quality-reviewer | `.agent/docs/dev-workflows.md` ~line 27 ("Firewall posture") | "Reactive" is stated as the chosen posture but, unlike the port/bind sections, doesn't carry an explicit one-clause reason for choosing reactive over proactive. | Suggested fix: add a clause such as "chosen because no inbound rule is needed until T3c actually needs the connection."
- 2026-09-22 | code-quality-reviewer | `.agent/docs/dev-workflows.md`, "localhost constraint" section vs. "Gotchas" section | Slight duplication — the Gotchas section restates the localhost constraint with a back-reference rather than adding new information. | Suggested fix: fold into one section in a future edit.
