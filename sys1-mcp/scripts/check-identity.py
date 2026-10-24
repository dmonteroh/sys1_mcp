#!/usr/bin/env python3
"""Compare what the daemon serves against sys1-mcp/deploy/identity.lock.json.

The lock pins the backend, the default model, which model each role uses, the
runtime, and per model whatever identity the backend reports: on laya-mlx the
checkpoint, the Hugging Face snapshot, the sha256 of its rl_agent_config.json
(every calibration temperature) and the token limits; on systemone the upstream
model name and endpoint. Any figure measured against this server
(tmp/tasks/notes/T11-calibration.md §6) holds only while these match.

  check-identity.py            exit 1 and name every field that differs
  check-identity.py --write    record what is served now, after an intended change

Stdlib only, so it runs under any python3. Reads the daemon's `sys1_health`
through `/predict`; set SYS1_MCP_URL for a non-default base URL.
"""
import json
import os
import ssl
import sys
import urllib.request

LOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "deploy", "identity.lock.json")
BASE_URL = os.environ.get("SYS1_MCP_URL", "https://localhost:8765").rstrip("/")
CA = os.path.expanduser("~/Library/Application Support/mkcert/rootCA.pem")
TOP_FIELDS = ("backend", "default_model", "roles", "runtime")
MODEL_FIELDS = ("checkpoint", "snapshot", "config_sha256", "limits", "endpoint")


def served() -> dict:
    context = ssl.create_default_context(cafile=CA if os.path.isfile(CA) else None)
    request = urllib.request.Request(
        f"{BASE_URL}/predict",
        data=json.dumps({"tool": "sys1_health", "arguments": {}}).encode(),
        headers={"Content-Type": "application/json"},
    )
    health = json.loads(urllib.request.urlopen(request, context=context, timeout=60).read())
    return {
        **{key: health[key] for key in TOP_FIELDS},
        "models": {
            name: {field: model[field] for field in MODEL_FIELDS if field in model}
            for name, model in sorted(health["models"].items())
        },
    }


def differences(locked: dict, current: dict) -> list[str]:
    found = []
    for key in TOP_FIELDS:
        if locked.get(key) != current.get(key):
            found.append(f"{key}: locked {locked.get(key)!r}, served {current.get(key)!r}")
    locked_models, current_models = locked.get("models", {}), current["models"]
    for name in sorted(set(locked_models) | set(current_models)):
        if name not in current_models:
            found.append(f"model {name}: locked but not served")
            continue
        if name not in locked_models:
            found.append(f"model {name}: served but not locked")
            continue
        for field in MODEL_FIELDS:
            was, now = locked_models[name].get(field), current_models[name].get(field)
            if was != now:
                found.append(f"model {name} {field}: locked {was!r}, served {now!r}")
    return found


def main() -> int:
    try:
        current = served()
    except OSError as exc:
        print(f"identity: could not read sys1_health from {BASE_URL}: {exc}", file=sys.stderr)
        return 1
    if sys.argv[1:] == ["--write"]:
        with open(LOCK, "w") as handle:
            json.dump(current, handle, indent=2)
            handle.write("\n")
        print(f"identity: wrote {os.path.normpath(LOCK)}")
        return 0
    if sys.argv[1:]:
        print(__doc__, file=sys.stderr)
        return 2
    if not os.path.isfile(LOCK):
        print(f"identity: no lock at {os.path.normpath(LOCK)}; run with --write to create it", file=sys.stderr)
        return 1
    with open(LOCK) as handle:
        found = differences(json.load(handle), current)
    if found:
        print("identity: DRIFT — the served backend, models or config differ from the lock:", file=sys.stderr)
        for line in found:
            print(f"  {line}", file=sys.stderr)
        print(
            "Measurements taken against the locked identity no longer apply. If the change "
            "was intended, re-measure what depends on it, then run with --write.",
            file=sys.stderr,
        )
        return 1
    print("identity: served backend, models and config match the lock")
    return 0


if __name__ == "__main__":
    sys.exit(main())
