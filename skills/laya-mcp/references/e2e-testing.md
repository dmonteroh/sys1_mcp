# Laya in browser end-to-end tests

Read this when a browser test needs a semantic decision about visible text or a choice among observed controls. The browser driver owns navigation, input, waits, and evidence collection. Laya receives text and typed questions through the local daemon's `/predict` HTTP route. Sources below were opened on 2026-09-27.

## What the Jev projects actually do

| Primary example | Mechanism | Laya adaptation |
| --- | --- | --- |
| [jev-e2e](https://github.com/perixtar/jev-e2e) | Jev selects from observed controls. Playwright executes actions and checks explicit expectations independently. Results include evidence, and saved controls can replay without a model call. | Send a bounded control list to `/predict`. Map the returned label to a Playwright locator. Keep the assertion independent of the control choice. |
| [jevcumber](https://github.com/RubyBrewsday/jevcumber) | Jev resolves a Gherkin step against actual buttons, fields, links, and step literals. A reviewed lockfile replays resolved steps. Missing controls require a new resolution. | Cache reviewed control IDs or locators per step. Treat a changed mapping as a reviewable test change. |
| [Jev Browser semantic verification](https://github.com/tontoko/jev-browser/blob/main/docs/semantic-verification.md) | A semantic matcher compares fresh locator evidence and reports uncertain or changed evidence. Exact properties use native assertions. | Add a narrow semantic assertion for observed text. Re-read the locator before accepting the decision, and report the text, question, checkpoint, and score on failure. |

These are Jev implementations, not measured Laya results. Their architecture transfers because Laya accepts the same three typed question forms. Their thresholds, label capacity, and accuracy do not transfer. In particular, this server warns that `choice` distributions become sharply overconfident at 11 or more labels ([server.py](../../../laya-mcp/src/laya_mcp/server.py)).

## Call the warm daemon from a test

The installed daemon serves `https://localhost:8765` on this host ([README.md](../../../README.md), TLS). Set `LAYA_PREDICT_URL` to the route your test process can reach. The process must trust that server's certificate. Do not bypass certificate verification.

`POST /predict` accepts `{"text": state, "schema": questions, "checkpoint": "base"}`. The route calls the same local prediction function as `laya_ask` ([daemon.py](../../../laya-mcp/src/laya_mcp/daemon.py), `predict`). It is plain HTTP JSON, so a Playwright test needs no MCP client. The server also accepts `{"tool": "laya_relevant", "arguments": {...}}` for the other tool wrappers.

```ts
import { expect, test } from '@playwright/test';

test('records whether the alert explains the email problem', async ({ page }) => {
  const url = process.env.LAYA_PREDICT_URL;
  if (!url) throw new Error('Set LAYA_PREDICT_URL to the daemon /predict URL');

  // The browser supplies observed evidence. Laya never reads the page itself.
  const alert = page.getByRole('alert');
  await expect(alert).toBeVisible();
  const observed = await alert.innerText();

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      text: observed,
      schema: {
        about_email: {
          type: 'noul',
          instructions: 'Does this alert explain a problem with the email field?',
        },
      },
      checkpoint: 'base',
    }),
  });
  if (!response.ok) throw new Error(`Laya /predict returned HTTP ${response.status}`);
  const result = await response.json();
  if (result.truncation?.truncated || result.truncation?.prefix_truncated) {
    throw new Error('Laya did not read the full assertion input');
  }
  const probability = result.answers?.about_email?.noul;
  if (typeof probability !== 'number') throw new Error('Laya returned no noul answer');
  // Playwright records runtime annotations in the test report.
  test.info().annotations.push({
    type: 'laya-observation',
    description: JSON.stringify({ observed, probability, checkpoint: result.checkpoint }),
  });
});
```

This example records a judgment through [Playwright's runtime annotations](https://playwright.dev/docs/test-annotations). It does not turn the score into a pass. Use test data that may appear in reports and the daemon's call log ([README.md](../../../README.md), Call logging). The existing skill has no threshold fitted to browser assertions, and `noul` can misread some yes/no wording. Compare the answer with known pass, fail, and near-miss cases before choosing a pass threshold. Keep `checkpoint` and the exact question fixed once calibrated. A score between accepted pass and fail bands is inconclusive, not success.

## Let Laya choose a control

Build candidates from the current Playwright page or a scoped region. Give each candidate an ID stable within the observation, role, accessible name, and current state. Put the test step and that candidate table in `text`. Ask one `choice` question with candidate IDs and `none` as the criteria. Keep at most ten labels including `none`, because this Laya deployment sharpens distributions at eleven ([server.py](../../../laya-mcp/src/laya_mcp/server.py), `_add_margins`). Narrow a crowded page by region or element type before asking. Never silently omit a plausible control.

```json
{
  "text": "Step: Open the billing settings.\nVisible controls in Settings dialog:\nb1 button Billing\nb2 button Notifications\nb3 button Save",
  "schema": {
    "target": {
      "type": "choice",
      "instructions": "Which visible control carries out the step?",
      "criteria": {
        "b1": "Billing button in Settings dialog",
        "b2": "Notifications button in Settings dialog",
        "b3": "Save button in Settings dialog",
        "none": "No listed control carries out the step"
      }
    }
  },
  "checkpoint": "base"
}
```

Map `answers.target.choice` to a locator in code. Stop on `none`, missing IDs, truncation, or stale evidence. Treat a small margin as inconclusive until a threshold is fitted. Check that the selected locator is still visible and enabled before Playwright clicks it. Keep action preconditions and outcome assertions in Playwright. Do not use Laya's opinion that a flow is complete as the sole completion check.

For repeated tests, store a reviewed step-to-control mapping. Replay it without Laya while the control still matches. If the control disappears, propose a fresh Laya mapping and show the diff for review. This is an adaptation of the lockfile and replay patterns in [jevcumber](https://github.com/RubyBrewsday/jevcumber) and [jev-e2e](https://github.com/perixtar/jev-e2e), not a feature of the current Laya MCP server.

## Make semantic assertions reliable

Use ordinary Playwright assertions for URL, HTTP status, element presence, values, counts, and exact text. Use Laya only for wording whose meaning matters and can vary. Read the target text immediately before the question, then read it again before accepting the verdict. If it changed, mark the result inconclusive and collect a trace.

Create a labeled set with real passing text, broken text, paraphrases, empty evidence, and near misses. Run each candidate question on both `base` and `typed-decisions`, and record each returned checkpoint, distribution, and truncation report. Choose thresholds from that set, then check them on separate cases. The current server's Playwright assertion quality has not been measured. Its `/predict` route was verified from code here, while the daemon was unavailable for a live call during this research.
