#!/usr/bin/env python3
"""Compare the weights the daemon serves against laya-mcp/deploy/identity.lock.json.

The lock pins, per route, the checkpoint, the Hugging Face snapshot, the sha256 of
its rl_agent_config.json (every calibration temperature) and the token limits, plus
the laya_mlx version and the default route. Any figure measured against this server
(tmp/tasks/notes/T11-calibration.md §6) holds only while these match. The response's
`model` field is a runtime constant, so it is never compared.

  check-identity.py            exit 1 and name every field that differs
  check-identity.py --write    record what is served now, after an intended change

Stdlib only, so it runs under any python3. Reads the daemon's `laya_health` through
`/predict`; set LAYA_MCP_URL for a non-default base URL.
"""
import json
import os
import ssl
import sys
import urllib.request

LOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "deploy", "identity.lock.json")
BASE_URL = os.environ.get("LAYA_MCP_URL", "https://localhost:8765").rstrip("/")
CA = os.path.expanduser("~/Library/Application Support/mkcert/rootCA.pem")
ROUTE_FIELDS = ("checkpoint", "snapshot", "config_sha256", "limits")


def served() -> dict:
    context = ssl.create_default_context(cafile=CA if os.path.isfile(CA) else None)
    request = urllib.request.Request(
        f"{BASE_URL}/predict",
        data=json.dumps({"tool": "laya_health", "arguments": {}}).encode(),
        headers={"Content-Type": "application/json"},
    )
    health = json.loads(urllib.request.urlopen(request, context=context, timeout=60).read())
    return {
        "default_route": health["default_route"],
        "runtime": health["runtime"],
        "routes": {
            name: {field: route.get(field) for field in ROUTE_FIELDS}
            for name, route in sorted(health["routes"].items())
        },
    }


def differences(locked: dict, current: dict) -> list[str]:
    found = []
    for key in ("default_route", "runtime"):
        if locked.get(key) != current.get(key):
            found.append(f"{key}: locked {locked.get(key)!r}, served {current.get(key)!r}")
    for name in sorted(set(locked["routes"]) | set(current["routes"])):
        if name not in current["routes"]:
            found.append(f"route {name}: locked but not served")
            continue
        if name not in locked["routes"]:
            found.append(f"route {name}: served but not locked")
            continue
        for field in ROUTE_FIELDS:
            was, now = locked["routes"][name].get(field), current["routes"][name].get(field)
            if was != now:
                found.append(f"route {name} {field}: locked {was!r}, served {now!r}")
    return found


def main() -> int:
    try:
        current = served()
    except OSError as exc:
        print(f"identity: could not read laya_health from {BASE_URL}: {exc}", file=sys.stderr)
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
        print("identity: DRIFT — the served weights or config differ from the lock:", file=sys.stderr)
        for line in found:
            print(f"  {line}", file=sys.stderr)
        print(
            "Measurements taken against the locked identity no longer apply. If the change "
            "was intended, re-measure what depends on it, then run with --write.",
            file=sys.stderr,
        )
        return 1
    print("identity: served weights and config match the lock")
    return 0


if __name__ == "__main__":
    sys.exit(main())
