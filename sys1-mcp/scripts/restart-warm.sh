#!/usr/bin/env bash
# Restart the sys1-mcp-http LaunchAgent and warm it with one call of every
# question type. See README.md "Restarting and warming" and skills/sys1-mcp/SKILL.md.
set -euo pipefail

LABEL=com.sys1-mcp.http
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
BASE_URL=${SYS1_MCP_URL:-https://localhost:8765}
HEALTH_TIMEOUT=${SYS1_MCP_HEALTH_TIMEOUT:-120}
do_restart=1
do_reload=0

usage() {
	cat <<'USAGE'
Usage: restart-warm.sh [--warm-only] [--url URL] [--timeout SECONDS]

  --warm-only       skip the restart; only wait for health and warm the model
  --reload          bootout and bootstrap instead of kickstart, so plist edits
                    take effect; a plain restart does NOT re-read the plist
  --url URL         server base URL (default https://localhost:8765, or $SYS1_MCP_URL)
  --timeout SECONDS how long to wait for /health to return 200 (default 120)

Warms every model in $SYS1_MCP_MODELS (default: every model /health lists), because
on laya-mlx the Metal-kernel compile is per checkpoint as well as per schema shape.
USAGE
}

while [ $# -gt 0 ]; do
	case "$1" in
		--warm-only) do_restart=0; shift ;;
		--reload) do_reload=1; shift ;;
		--url) BASE_URL=$2; shift 2 ;;
		--timeout) HEALTH_TIMEOUT=$2; shift 2 ;;
		-h|--help) usage; exit 0 ;;
		*) printf 'unknown argument: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
	esac
done

BASE_URL=${BASE_URL%/}
uid=$(id -u)

# Models to warm. Override with SYS1_MCP_MODELS to warm a subset. Use the
# canonical model names, not aliases: the check below compares against the
# `model` the server reports back, which is always canonical. Unset, the list is
# read from /health once the server is up.
MODELS=${SYS1_MCP_MODELS:-}

restart() {
	# kickstart restarts the process but launchd keeps the job definition it
	# bootstrapped, so an edited plist -- EnvironmentVariables included -- is NOT
	# picked up. --reload bounces the job itself, the only way to apply one.
	if [ "$do_reload" -eq 1 ] && [ -f "$PLIST" ]; then
		printf 'reloading %s from %s\n' "$LABEL" "$PLIST"
		launchctl bootout "gui/${uid}/${LABEL}" 2>/dev/null || true
		# bootout is not synchronous; bootstrapping too early fails with EIO (5).
		for _ in 1 2 3 4 5 6 7 8 9 10; do
			launchctl print "gui/${uid}/${LABEL}" >/dev/null 2>&1 || break
			sleep 1
		done
		launchctl bootstrap "gui/${uid}" "$PLIST"
	elif launchctl print "gui/${uid}/${LABEL}" >/dev/null 2>&1; then
		printf 'restarting %s (plist edits need --reload)\n' "$LABEL"
		launchctl kickstart -k "gui/${uid}/${LABEL}"
	elif [ -f "$PLIST" ]; then
		printf '%s is not loaded; bootstrapping from %s\n' "$LABEL" "$PLIST"
		launchctl bootstrap "gui/${uid}" "$PLIST"
	else
		printf '%s is not loaded and %s does not exist.\n' "$LABEL" "$PLIST" >&2
		printf 'Install it from sys1-mcp/deploy/%s.plist, or start the server by hand\n' "$LABEL" >&2
		printf 'and re-run with --warm-only. See README.md.\n' >&2
		exit 1
	fi
}

wait_for_health() {
	# The agent loads eagerly before the listener binds, so the usual failure
	# here is connection-refused (000), not 503.
	local deadline code
	deadline=$(( $(date +%s) + HEALTH_TIMEOUT ))
	printf 'waiting for %s/health' "$BASE_URL"
	while :; do
		code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' "${BASE_URL}/health" || true)
		if [ "$code" = "200" ]; then
			printf ' ok\n'
			return 0
		fi
		if [ "$(date +%s)" -ge "$deadline" ]; then
			printf ' timed out after %ss (last status %s)\n' "$HEALTH_TIMEOUT" "$code" >&2
			return 1
		fi
		printf '.'
		sleep 1
	done
}

hdr_file=$(mktemp -t sys1-warm-hdr)
body_file=$(mktemp -t sys1-warm-body)
trap 'rm -f "$hdr_file" "$body_file"' EXIT

session_id=""

mcp_post() {
	# $1 = JSON-RPC payload. Prints the SSE body; sets nothing else.
	local extra=()
	if [ -n "$session_id" ]; then extra=(-H "mcp-session-id: ${session_id}"); fi
	curl -s -m 120 -D "$hdr_file" -X POST "${BASE_URL}/mcp" \
		-H 'Content-Type: application/json' \
		-H 'Accept: application/json, text/event-stream' \
		${extra[@]+"${extra[@]}"} -d "$1"
}

handshake() {
	mcp_post '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"restart-warm","version":"1"}}}' >/dev/null
	session_id=$(tr -d '\r' < "$hdr_file" | awk 'tolower($1)=="mcp-session-id:"{print $2}')
	if [ -z "$session_id" ]; then
		printf 'MCP initialize returned no mcp-session-id; is %s/mcp serving?\n' "$BASE_URL" >&2
		exit 1
	fi
	mcp_post '{"jsonrpc":"2.0","method":"notifications/initialized"}' >/dev/null
}

warm_call() {
	# The state and the NOUL question below are sys1_mcp.server WARM_STATE / WARM_NOUL,
	# which sys1_health probes with; keep them identical or its latency includes a compile.
	# $1 = label for the report, $2 = the `questions` object as JSON,
	# $3 = the model to warm.
	local label=$1 questions=$2 route=$3 payload started elapsed
	payload=$(printf '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"sys1_ask","arguments":{"state":"A customer writes: I was billed twice this month. Please refund the duplicate charge.","questions":%s,"model":"%s"}}}' "$questions" "$route")
	started=$(date +%s)
	mcp_post "$payload" > "$body_file"
	elapsed=$(( $(date +%s) - started ))
	if grep -q '"isError":true' "$body_file" || ! grep -q '"answers"' "$body_file"; then
		printf '  %-18s %-16s FAILED after %ss\n' "$label" "$route" "$elapsed" >&2
		sed -n 's/^data: //p' "$body_file" >&2
		return 1
	fi
	# Confirm the answer came from the model we asked for, not a silent fallback.
	if ! grep -q "\"model\":\"${route}\"" "$body_file"; then
		printf '  %-18s %-16s WRONG MODEL after %ss\n' "$label" "$route" "$elapsed" >&2
		sed -n 's/^data: //p' "$body_file" >&2
		return 1
	fi
	printf '  %-18s %-16s ok (%ss)\n' "$label" "$route" "$elapsed"
}

warm_tool() {
	# $1 = label, $2 = tool name, $3 = arguments as JSON, $4 = a key the answer must hold.
	local label=$1 tool=$2 arguments=$3 key=$4 payload started elapsed
	payload=$(printf '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"%s","arguments":%s}}' "$tool" "$arguments")
	started=$(date +%s)
	mcp_post "$payload" > "$body_file"
	elapsed=$(( $(date +%s) - started ))
	if grep -q '"isError":true' "$body_file" || ! grep -q "\"${key}\"" "$body_file"; then
		printf '  %-18s %-16s FAILED after %ss\n' "$label" "$tool" "$elapsed" >&2
		sed -n 's/^data: //p' "$body_file" >&2
		return 1
	fi
	printf '  %-18s %-16s ok (%ss)\n' "$label" "$tool" "$elapsed"
}

if [ "$do_restart" -eq 1 ]; then restart; fi
wait_for_health
if [ -z "$MODELS" ]; then
	MODELS=$(curl -s -m 10 "${BASE_URL}/health" | python3 -c 'import sys, json; print(" ".join(json.load(sys.stdin)["models"]))')
fi
handshake

# One call per question type, then one batched call — each distinct schema shape
# pays its own one-time Metal-kernel compile on laya-mlx (skills/sys1-mcp/SKILL.md).
# Repeated per model: the compile is per checkpoint too, so warming only the
# default leaves the other model paying it on its first real call.
CHOICE='{"department":{"type":"choice","instructions":"Who should handle this?","criteria":["billing","technical","sales"]}}'
SCORE='{"severity":{"type":"score","instructions":"How severe is this for the customer?","criteria":["trivial","minor","major","critical"]}}'
NOUL='{"refund":{"type":"noul","instructions":"Does the customer ask for money back?"}}'
ALL='{"department":{"type":"choice","instructions":"Who should handle this?","criteria":["billing","technical","sales"]},"severity":{"type":"score","instructions":"How severe is this for the customer?","criteria":["trivial","minor","major","critical"]},"refund":{"type":"noul","instructions":"Does the customer ask for money back?"}}'

status=0
for route in $MODELS; do
	printf 'warming schema shapes on %s\n' "$route"
	warm_call 'choice' "$CHOICE" "$route" || status=1
	warm_call 'score' "$SCORE" "$route" || status=1
	warm_call 'noul' "$NOUL" "$route" || status=1
	warm_call 'choice+score+noul' "$ALL" "$route" || status=1
done

# The batched tools build batches of a different shape from any single call, and
# sys1_screen always runs its own four-question schema on the content-role model.
printf 'warming batched tools\n'
warm_tool 'screen' sys1_screen '{"text":"## Setup\n\nRun npm install, then npm start."}' per_chunk || status=1
for route in $MODELS; do
	warm_tool "classify ${route}" sys1_classify "{\"items\":[\"I was billed twice.\",\"The app crashes on start.\",\"Can I get a quote?\"],\"questions\":${ALL},\"model\":\"${route}\"}" items || status=1
done
# sys1_relevant always uses the trace-role model, regardless of $MODELS.
warm_tool 'relevant' sys1_relevant '{"task":"Fix the off-by-one in the pagination cursor","context":"This module also defines the CSV export helper, unrelated to pagination."}' answers || status=1
warm_tool 'select tests' sys1_select_tests '{"diff_chunks":["Changed pagination cursor calculation"],"tests":[{"id":"pagination","path":"tests/pagination.spec.ts","title":"opens page two"}],"changed_files":[]}' mode || status=1
warm_tool 'verify outcome' sys1_verify_outcome '{"goal":"A report exists","tool_result":"The report job completed","evidence":"The report file is present","checks":[{"name":"file exists","passed":true}]}' status || status=1
warm_tool 'cache fit' sys1_cache_fit '{"new_request":"Show April totals","cached_request":"Show April totals","cached_answer":"April total is 12","new_scope":{"tenant":"demo","month":"April"},"cached_scope":{"tenant":"demo","month":"April"},"expires_at":"2099-01-01T00:00:00Z"}' action || status=1
warm_tool 'pack context' sys1_pack_context '{"task":"Fix pagination","candidates":[{"id":"constraint","text":"Keep the public API stable","tokens":6},{"id":"trace","text":"Page two starts at the wrong cursor","tokens":7}],"pinned_ids":["constraint"],"budget_tokens":20}' selected_ids || status=1
warm_tool 'health' sys1_health '{}' probe_ms || status=1

if [ "$status" -ne 0 ]; then
	printf 'one or more warm-up calls failed; the server is up but not fully warmed\n' >&2
	exit 1
fi
# A restart is when a backend, checkpoint, config or runtime change takes effect,
# so check the served identity against the lock here. The server stays up either way.
SYS1_MCP_URL=$BASE_URL python3 "$(dirname "$0")/check-identity.py" || exit 1
printf 'sys1-mcp is up and warm at %s/mcp\n' "$BASE_URL"
