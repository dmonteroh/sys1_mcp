# T1 — Native Laya runtime setup note

Produced by the T1 implementer pass, 2026-09-22. This is the artifact T2 reads for the
verified runtime steps and interpreter path — see `tasks/T1-laya-native-runtime.md` for
the acceptance criteria this satisfies.

## 1. Host check — Apple Silicon confirmation

Ran directly on the target Mac (not a devcontainer):

```
$ uname -m
arm64

$ sw_vers
ProductName:    macOS
ProductVersion: 26.7
BuildVersion:   25G229
```

Host is Apple Silicon (`arm64`), macOS 26.7. Both candidate runtimes' minimum macOS
requirement (14+ for `laya-mlx`, 15+ for `laya-coreml`) is satisfied.

## 2. Runtime choice: `laya-mlx`

Chosen over `laya-coreml`. Reason:

- Verified on PyPI's JSON API (`https://pypi.org/pypi/<pkg>/json`, not the research.md
  README quotes) that `laya-coreml==0.1.0` declares `requires_python: "<3.14,>=3.11"` —
  an explicit upper bound that excludes this host's system Python (3.14.7, and 3.15.0b4
  also present via `uv python list`). `laya-mlx==0.1.0` declares `requires_python: ">=3.11"`
  with no upper bound in its metadata.
- Both packages are equally third-party/unaudited ports of `convaiinnovations/laya` by
  the same author (`mizorewww`), both Apache-2.0, both released within the last few days
  (2026-09-19 and 2026-09-20 per PyPI). Neither has an obvious maturity edge, so the
  Python-version constraint was the deciding factor.
- Only one runtime is installed, per the Implementation Constraints (installing both
  would need a written justification, which doesn't apply here).

Not installing `laya-coreml` in this pass; a venv pinned to a laya-coreml-supported
Python (3.11-3.13) would be needed if it's ever wanted, since the host's default
Python (3.14.7) is outside its declared range.

## 3. Pre-install verification (against real PyPI/repo pages, not research.md quotes)

research.md flags its "Requires macOS 14+, Python 3.11+" line as an unverified README
quote. Checked directly before installing anything:

**PyPI JSON API** (`curl -s https://pypi.org/pypi/laya-mlx/json`):
```
name laya-mlx
version 0.1.0
requires_python >=3.11
license None
project_urls {'Benchmarks': 'https://github.com/mizorewww/laya-mlx/blob/main/BENCHMARKS.md',
  'Documentation': 'https://github.com/mizorewww/laya-mlx#readme',
  'Issues': 'https://github.com/mizorewww/laya-mlx/issues',
  'Repository': 'https://github.com/mizorewww/laya-mlx',
  'Upstream': 'https://github.com/NandhaKishorM/laya'}
classifiers:
  Development Status :: 4 - Beta
  Intended Audience :: Developers
  Operating System :: MacOS
  Programming Language :: Python :: 3
  Topic :: Scientific/Engineering :: Artificial Intelligence
```

Note: the PyPI `Upstream` project URL points to `github.com/NandhaKishorM/laya`, not
`github.com/convaiinnovations/laya` as research.md's recap implied. Not resolved further
in this pass (out of T1's scope — provenance is recorded, not audited), but flagged here
since it's a discrepancy from the task brief's framing of the upstream project.

**GitHub repo README** (`github.com/mizorewww/laya-mlx`, fetched directly, not the
research.md summary):
- Install: `pip install laya-mlx`
- Quickstart:
  ```python
  import laya_mlx as laya
  agent = laya.load("aac6fef/laya-mlx")
  result = agent.predict(
      "I was billed twice. Please refund the duplicate.",
      {"department": {"type": "choice", "instructions": "Who should handle this?",
                       "criteria": ["billing", "technical", "sales"]}},
  )
  print(result["answers"]["department"])
  ```
- Stated support: Python 3.11+ (tested on 3.12.13), macOS 14+ (tested on macOS 27.2).
- Checkpoint identifiers: `aac6fef/laya-mlx` (421M, English, used here),
  `aac6fef/laya-multilingual-mlx` (322M), `aac6fef/laya-typed-decisions-mlx` (421M).
- License: Apache-2.0.
- API surface actually verified: `laya.load(checkpoint_id)` returns an agent object with a
  `.predict(text, schema_dict)` method — **not** the `.choice(prompt, options)` placeholder
  API sketched in the task brief's Execution Gates verification-command template. The
  brief's own gate section says to "adjust the import/API to the verified surface of the
  chosen package," which is what was done below.

**Deviation from the brief's literal verification command**: the brief's template command
uses `laya.choice('<probe prompt>', ['yes', 'no'])`. The real, verified API is
`agent.predict(text, {field_name: {"type": "choice"|"score"|"noul", ...}})`. Ran the real
API instead of the placeholder, as instructed by the brief.

## 4. Environment creation (`uv`)

Venv created outside the repo tree, at `/Users/USERNAME/.venvs/laya-mlx-t1`
(the repo's `.gitignore` was checked first — no need to add an entry since the venv
lives entirely outside the working tree).

Python version choice: pinned to 3.12, matching `laya-mlx`'s own stated tested version
(3.12.13) rather than the host's default 3.14.7/3.15.0b4, since the package's only
concretely tested Python version is 3.12.x and its PyPI metadata upper bound is
unspecified/unverified beyond that.

```
$ uv venv --python 3.12 /Users/USERNAME/.venvs/laya-mlx-t1
Using CPython 3.12.12 interpreter at: /opt/homebrew/opt/python@3.12/bin/python3.12
Creating virtual environment at: /Users/USERNAME/.venvs/laya-mlx-t1
Activate with: source /Users/USERNAME/.venvs/laya-mlx-t1/bin/activate
```

Resolved interpreter: **`/Users/USERNAME/.venvs/laya-mlx-t1/bin/python`**
(CPython 3.12.12, `/opt/homebrew/opt/python@3.12/bin/python3.12` as the base
interpreter uv built the venv from).

## 5. Install (pinned version)

```
$ uv pip install --python /Users/USERNAME/.venvs/laya-mlx-t1 'laya-mlx==0.1.0'
Using Python 3.12.12 environment at: /Users/USERNAME/.venvs/laya-mlx-t1
Resolved 20 packages in 1.53s
Downloading tokenizers (3.0MiB)
Downloading numpy (5.2MiB)
Downloading mlx-metal (61.4MiB)
Downloading hf-xet (3.7MiB)
 Downloaded tokenizers
 Downloaded hf-xet
 Downloaded numpy
 Downloaded mlx-metal
Prepared 11 packages in 23.70s
Installed 20 packages in 29ms
 + anyio==4.15.1
 + certifi==2026.7.22
 + click==8.5.0
 + filelock==4.0.1
 + fsspec==2026.9.0
 + h11==0.16.0
 + hf-xet==1.6.0
 + httpcore==1.0.9
 + httpx==0.28.1
 + huggingface-hub==1.32.0
 + idna==3.20
 + laya-mlx==0.1.0
 + mlx==0.32.2
 + mlx-metal==0.32.2
 + numpy==2.5.3
 + packaging==26.3
 + pyyaml==6.0.3
 + tokenizers==0.23.2
 + tqdm==4.70.1
 + typing-extensions==4.16.0
```

**Pinned package version: `laya-mlx==0.1.0`.**

```
$ uv pip freeze --python /Users/USERNAME/.venvs/laya-mlx-t1
anyio==4.15.1
certifi==2026.7.22
click==8.5.0
filelock==4.0.1
fsspec==2026.9.0
h11==0.16.0
hf-xet==1.6.0
httpcore==1.0.9
httpx==0.28.1
huggingface-hub==1.32.0
idna==3.20
laya-mlx==0.1.0
mlx==0.32.2
mlx-metal==0.32.2
numpy==2.5.3
packaging==26.3
pyyaml==6.0.3
tokenizers==0.23.2
tqdm==4.70.1
typing-extensions==4.16.0
```

## 6. Checkpoint load + real inference (run 1: cold, includes first-time HF download)

```
$ /Users/USERNAME/.venvs/laya-mlx-t1/bin/python -c "
import time
import laya_mlx as laya

t_load_start = time.perf_counter()
agent = laya.load('aac6fef/laya-mlx')
t_load = (time.perf_counter() - t_load_start) * 1000
print('load_ms', t_load)

t0 = time.perf_counter()
result = agent.predict(
    'I was billed twice this month. Please refund the duplicate charge.',
    {
        'department': {
            'type': 'choice',
            'instructions': 'Who should handle this?',
            'criteria': ['billing', 'technical', 'sales'],
        }
    },
)
latency_ms = (time.perf_counter() - t0) * 1000
print('latency_ms', latency_ms)
print('result', result)
"

Fetching 6 files:   0%|          | 0/6 [00:00<?, ?it/s]Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
Fetching 6 files:  17%|#7        | 1/6 [00:00<00:01,  2.89it/s]
Fetching 6 files:  33%|###3      | 2/6 [00:01<00:03,  1.23it/s]
Fetching 6 files:  83%|########3 | 5/6 [00:01<00:00,  3.27it/s]
Fetching 6 files: 100%|##########| 6/6 [04:43<00:00, 71.92s/it]
load_ms 286545.64395800116
latency_ms 1364.7689999779686
result {'model': 'laya-rl-agent', 'answers': {'department': {'type': 'choice', 'confidence': 0.7563, 'action': {'act_probability': 1.0}, 'choice': 'billing', 'probabilities': {'billing': 0.9375, 'technical': 0.0478, 'sales': 0.0147}}}, 'usage': {'input_tokens': 31, 'output_tokens': 0}}
[exited with code 0]
```

`load_ms` (286,545 ms ≈ 4m47s) is dominated by the one-time, unauthenticated (no
`HF_TOKEN` set) checkpoint download from Hugging Face into `~/.cache/huggingface`, not
model-loading compute. `latency_ms` for this very first `predict()` call (1,364.8 ms)
is also inflated by first-call MLX/Metal kernel JIT compilation for that schema shape,
not steady-state inference. Re-ran a second, cleaner measurement below to separate these.

## 7. Checkpoint load + inference (run 2: checkpoint cached, load time and warm-call latency isolated)

```
$ /Users/USERNAME/.venvs/laya-mlx-t1/bin/python -c "
import time
import laya_mlx as laya

t_load_start = time.perf_counter()
agent = laya.load('aac6fef/laya-mlx')
t_load = (time.perf_counter() - t_load_start) * 1000
print('load_ms (checkpoint cached)', t_load)

# First (cold-compile) call
t0 = time.perf_counter()
result1 = agent.predict(
    'I was billed twice this month. Please refund the duplicate charge.',
    {'department': {'type': 'choice', 'instructions': 'Who should handle this?',
                     'criteria': ['billing', 'technical', 'sales']}},
)
latency1_ms = (time.perf_counter() - t0) * 1000
print('latency_ms call_1 (post-load, first call)', latency1_ms)
print('result_1', result1)

# Second (warm) call - same process, same schema shape, kernels already compiled
t1 = time.perf_counter()
result2 = agent.predict(
    'The customer wants to cancel their subscription immediately.',
    {'department': {'type': 'choice', 'instructions': 'Who should handle this?',
                     'criteria': ['billing', 'technical', 'sales']}},
)
latency2_ms = (time.perf_counter() - t1) * 1000
print('latency_ms call_2 (warm)', latency2_ms)
print('result_2', result2)

# Third call, different schema type (noul) - new kernel shape
t2 = time.perf_counter()
result3 = agent.predict(
    'Is the customer asking for a refund?',
    {'refund': {'type': 'noul', 'instructions': 'Does the customer ask for money back?'}},
)
latency3_ms = (time.perf_counter() - t2) * 1000
print('latency_ms call_3 (warm, noul type)', latency3_ms)
print('result_3', result3)
"

Fetching 6 files:   0%|          | 0/6 [00:00<?, ?it/s]
Fetching 6 files: 100%|##########| 6/6 [00:00<00:00, 1494.05it/s]
load_ms (checkpoint cached) 2115.5579590122215
latency_ms call_1 (post-load, first call) 141.9217080110684
result_1 {'model': 'laya-rl-agent', 'answers': {'department': {'type': 'choice', 'confidence': 0.7563, 'action': {'act_probability': 1.0}, 'choice': 'billing', 'probabilities': {'billing': 0.9375, 'technical': 0.0478, 'sales': 0.0147}}}, 'usage': {'input_tokens': 31, 'output_tokens': 0}}
latency_ms call_2 (warm) 22.054417000617832
result_2 {'model': 'laya-rl-agent', 'answers': {'department': {'type': 'choice', 'confidence': 0.3989, 'action': {'act_probability': 1.0}, 'choice': 'billing', 'probabilities': {'billing': 0.7875, 'technical': 0.0855, 'sales': 0.1269}}}, 'usage': {'input_tokens': 27, 'output_tokens': 0}}
latency_ms call_3 (warm, noul type) 88.97145799710415
result_3 {'model': 'laya-rl-agent', 'answers': {'refund': {'type': 'noul', 'confidence': 0.6303, 'action': {'act_probability': 1.0}, 'noul': 0.6303}}, 'usage': {'input_tokens': 42, 'output_tokens': 0}}
[exited with code 0]
```

### Latency finding vs. claimed figures

research.md quotes "7-14ms P50 on M3 Max" for `laya-mlx`; the GitHub README quotes
"13.42 ms median... on M3 Max." Observed on this host:

- Cold, first-ever call (includes HF download + first Metal-kernel JIT compile):
  ~1,365 ms — not comparable to the steady-state claim, expected to be an outlier.
- First call after a **warm** load (checkpoint already cached, but no prior kernel
  compile for this schema shape in-process): ~142 ms — this is the more realistic
  "first call of a session" cost and is **~10-20x higher** than the claimed 7-14ms.
- Second call, same schema shape, same process (fully warm, kernels already
  compiled): ~22 ms — same order of magnitude as the claim but still roughly
  **1.5-3x higher** than the 7-14ms / 13.42ms figures.
- Third call, a *different* schema type (`noul` vs `choice`) in the same warm
  process: ~89 ms — confirms each distinct schema/type shape pays its own one-time
  compilation cost that isn't captured by a single steady-state benchmark number.

**Conclusion**: the claimed 7-14ms figure is roughly reproducible only for a fully
warmed-up model repeatedly answering the *same* schema shape; it understates real
first-call and per-schema-shape latency by an order of magnitude or more. This is
recorded as a finding, not treated as a failed acceptance criterion — the brief asks
for a real observed comparison, not for meeting the vendor's number.

This machine has no hardware other than what's listed in section 1 (single Mac,
Apple Silicon, no dedicated benchmarking rig), so this is one host's single-run
numbers, not a statistically robust benchmark.

## 8. Reproducibility anchors

- **Pinned package version**: `laya-mlx==0.1.0` (installed from PyPI, resolved deps
  captured in full in section 5's `uv pip freeze` output).
- **Hugging Face checkpoint revision resolved at load time**: `aac6fef/laya-mlx`,
  revision `main` -> commit **`20aed815fc6acde75733882e7ec0e3f28aeb9717`**, resolved via:
  ```
  $ find ~/.cache/huggingface -name "*.json" -path "*laya*"
  /Users/USERNAME/.cache/huggingface/hub/models--aac6fef--laya-mlx/trees/20aed815fc6acde75733882e7ec0e3f28aeb9717.json
  /Users/USERNAME/.cache/huggingface/hub/models--aac6fef--laya-mlx/snapshots/20aed815fc6acde75733882e7ec0e3f28aeb9717/mlx_config.json
  /Users/USERNAME/.cache/huggingface/hub/models--aac6fef--laya-mlx/snapshots/20aed815fc6acde75733882e7ec0e3f28aeb9717/rl_agent_config.json
  /Users/USERNAME/.cache/huggingface/hub/models--aac6fef--laya-mlx/snapshots/20aed815fc6acde75733882e7ec0e3f28aeb9717/encoder/config.json
  /Users/USERNAME/.cache/huggingface/hub/models--aac6fef--laya-mlx/snapshots/20aed815fc6acde75733882e7ec0e3f28aeb9717/tokenizer/tokenizer_config.json
  /Users/USERNAME/.cache/huggingface/hub/models--aac6fef--laya-mlx/snapshots/20aed815fc6acde75733882e7ec0e3f28aeb9717/tokenizer/tokenizer.json
  ```
  (`refs/main` in the same hub cache directory contains the literal string
  `20aed815fc6acde75733882e7ec0e3f28aeb9717`, confirming this is what `laya.load()`
  actually resolved for the `main` revision.)
- **Absolute interpreter/venv path**: `/Users/USERNAME/.venvs/laya-mlx-t1`
  (interpreter: `/Users/USERNAME/.venvs/laya-mlx-t1/bin/python`, CPython 3.12.12).
  T2 should invoke Laya via this interpreter.

## 9. Lightweight provenance (per the brief's "provenance, not audit" stance)

- **Repo**: `github.com/mizorewww/laya-mlx`
- **License**: Apache-2.0
- **Latest PyPI release**: `0.1.0`, released 2026-09-19 (per PyPI JSON API)
- **Stated Python/macOS support (verified against PyPI JSON + GitHub README, not
  research.md's quote)**: Python `>=3.11` (README says tested on 3.12.13); macOS 14+
  (README says tested on macOS 27.2)
- **Upstream checkpoint**: Hugging Face `aac6fef/laya-mlx`, resolved commit
  `20aed815fc6acde75733882e7ec0e3f28aeb9717` (section 8). Note: the PyPI package's own
  `Upstream` project URL points to `github.com/NandhaKishorM/laya`, which does not match
  `convaiinnovations/laya` as named in the task brief and research.md — flagged as a
  discrepancy, not resolved further (out of scope for T1; no checksum/audit performed
  per the brief's Decisions section).
- No security audit of package source or checkpoint integrity was performed, per the
  brief's explicit scope decision.

## 10. Self-review against Acceptance Criteria

1. "Confirm the actual host this will run on is Apple Silicon... record how this was
   checked" — done, section 1 (`uname -m` -> `arm64`, `sw_vers` -> macOS 26.7).
2. "Choose one runtime... with a stated reason" — done, section 2 (`laya-mlx`, chosen
   over `laya-coreml` because `laya-coreml`'s PyPI metadata excludes this host's
   available Python versions above 3.13, while `laya-mlx` has no upper bound).
3. "Verify the chosen package's real install/load instructions against its actual
   repo/PyPI page... before running anything" — done, section 3 (PyPI JSON API +
   GitHub README fetched and quoted, before any `uv pip install` ran).
4. "Install the chosen runtime and successfully load the checkpoint at least once" —
   done, sections 5-7 (`laya-mlx==0.1.0` installed; `laya.load('aac6fef/laya-mlx')`
   succeeded twice, cold and cached).
5. "Run at least one real inference call and record the actual latency observed...
   compare against the claimed 7-14ms/~5ms figures" — done, sections 6-7 (four real
   `predict()` calls with wall-clock timing; comparison against the claim written up
   in section 7's "Latency finding" subsection, including where it holds up and where
   it doesn't).
6. "Record exact commands run and their real output... at `tasks/notes/T1-setup.md`"
   — this file, sections 1, 3, 5, 6, 7 quote every command and its real terminal
   output verbatim.
7. "`tasks/notes/T1-setup.md` is the artifact T2 reads..." — satisfied by this file's
   existence and self-contained content (interpreter path, pinned version, checkpoint
   revision, chosen-runtime rationale all present without needing another file).
8. "Record... the three reproducibility anchors" — done, section 8 (pinned version,
   HF commit hash, absolute venv/interpreter path).

All 8 acceptance criteria hold as recorded above.

## Deviations / risks worth flagging to T2 and beyond

- The Execution Gates' literal verification command template
  (`laya.choice('<probe prompt>', ['yes', 'no'])`) does not match the real API
  (`agent.predict(text, schema_dict)`); this note uses the real, verified API per the
  brief's own instruction to adjust for the verified surface.
- `laya-coreml` was not installed (single-runtime choice, per constraint); if a future
  task wants the Neural Engine path, it needs its own `uv` venv pinned to Python
  3.11-3.13 (not 3.14+), since `laya-coreml==0.1.0`'s PyPI metadata explicitly excludes
  Python 3.14 and above.
- The PyPI package's `Upstream` link (`github.com/NandhaKishorM/laya`) doesn't match
  `convaiinnovations/laya` as referenced in the task brief/research.md — worth a look
  before any downstream task treats "convaiinnovations/laya" and the HF checkpoint
  `aac6fef/laya-mlx` as definitely the same lineage; not resolved in this pass.
- No `HF_TOKEN` was configured; the first download hit HF's unauthenticated rate limit
  warning (not an error, just slower/potentially throttled on a busier day).
- Claimed latency figures (7-14ms / 13.42ms) were only reproduced within ~1.5-3x on a
  fully warm, same-schema-shape call (~22ms observed); first-call-per-process and
  first-call-per-schema-shape costs are substantially higher (~142ms, ~89ms) and are not
  disclosed by the vendor's single benchmark number. Anything downstream (e.g. T2's MCP
  wrapper) that assumes single-digit-millisecond latency per call should account for
  this, especially for the very first call after the daemon/process starts or when a
  new schema shape is used for the first time.
