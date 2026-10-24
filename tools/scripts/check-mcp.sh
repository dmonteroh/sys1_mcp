#!/usr/bin/env bash
# Check that a sys1-mcp server is reachable and answering, step by step:
# /health, the MCP initialize handshake, tools/list, and one real tool call.
# Needs only bash and curl, so it runs on the host and inside a container.
set -euo pipefail

URL=${SYS1_MCP_URL:-https://localhost:8765}
CACERT=${SYS1_MCP_CACERT:-}
CONNECT_HOST=${SYS1_MCP_CONNECT_HOST:-}
TIMEOUT=${SYS1_MCP_TIMEOUT:-30}
EXPECT_TOOL=${SYS1_MCP_EXPECT_TOOL:-sys1_ask}
INSECURE=0
CALL=1

usage() {
	cat <<'USAGE'
Usage: check-mcp.sh [--url URL] [--cacert FILE] [--connect-host HOST]
                    [--insecure] [--timeout SECONDS] [--expect-tool NAME] [--no-call]

  --url URL           server base URL, without /mcp (default https://localhost:8765,
                      or $SYS1_MCP_URL)
  --cacert FILE       CA bundle to verify the server certificate with ($SYS1_MCP_CACERT).
                      Unset, the first that exists of the macOS mkcert root,
                      /tmp/mkcert-rootCA.pem and $NODE_EXTRA_CA_CERTS is used, else
                      curl's default trust store
  --connect-host HOST connect to HOST but verify TLS against the URL's own name
                      ($SYS1_MCP_CONNECT_HOST), for a route the certificate does
                      not name. From a container, --url https://host.docker.internal:8765
                      works directly, since the certificate names it
  --insecure          skip certificate verification (reported in the output)
  --timeout SECONDS   per-request limit (default 30, or $SYS1_MCP_TIMEOUT)
  --expect-tool NAME  tool that tools/list must include (default sys1_ask)
  --no-call           stop after tools/list; skip the sys1_health call

Exit status: 0 when every step passes, 1 on the first failed step, 2 on bad usage.
USAGE
}

while [ $# -gt 0 ]; do
	case "$1" in
		--url) URL=$2; shift 2 ;;
		--cacert) CACERT=$2; shift 2 ;;
		--connect-host) CONNECT_HOST=$2; shift 2 ;;
		--insecure) INSECURE=1; shift ;;
		--timeout) TIMEOUT=$2; shift 2 ;;
		--expect-tool) EXPECT_TOOL=$2; shift 2 ;;
		--no-call) CALL=0; shift ;;
		-h|--help) usage; exit 0 ;;
		*) printf 'unknown argument: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
	esac
done

command -v curl >/dev/null || { printf 'FAIL  setup: curl is not installed\n' >&2; exit 1; }

URL=${URL%/}
URL=${URL%/mcp}
scheme=${URL%%://*}
hostport=${URL#*://}
hostport=${hostport%%/*}
host=${hostport%:*}
if [ "$host" = "$hostport" ]; then
	if [ "$scheme" = https ]; then port=443; else port=80; fi
else
	port=${hostport##*:}
fi

curl_args=(-sS -m "$TIMEOUT")
tls_note="no TLS"
if [ "$scheme" = https ]; then
	if [ "$INSECURE" -eq 1 ]; then
		curl_args+=(-k)
		tls_note="certificate NOT verified (--insecure)"
	else
		if [ -z "$CACERT" ]; then
			for candidate in "$HOME/Library/Application Support/mkcert/rootCA.pem" /tmp/mkcert-rootCA.pem "${NODE_EXTRA_CA_CERTS:-}"; do
				if [ -n "$candidate" ] && [ -f "$candidate" ]; then CACERT=$candidate; break; fi
			done
		fi
		if [ -n "$CACERT" ]; then
			[ -f "$CACERT" ] || { printf 'FAIL  setup: --cacert %s is not a file\n' "$CACERT" >&2; exit 1; }
			curl_args+=(--cacert "$CACERT")
			tls_note="verified against $CACERT"
		else
			tls_note="verified against curl's default trust store"
		fi
	fi
fi
if [ -n "$CONNECT_HOST" ]; then
	curl_args+=(--connect-to "${host}:${port}:${CONNECT_HOST}:${port}")
fi

tmp=$(mktemp -d "${TMPDIR:-/tmp}/check-mcp.XXXXXX")
trap 'rm -rf "$tmp"' EXIT

printf 'target  %s/mcp%s\n' "$URL" "${CONNECT_HOST:+ (connecting to $CONNECT_HOST:$port)}"
printf 'tls     %s\n' "$tls_note"

pass() { printf 'PASS  %-12s %s\n' "$1" "$2"; }

fail() {
	printf 'FAIL  %-12s %s\n' "$1" "$2" >&2
	if [ -s "$tmp/err" ]; then sed 's/^curl: //; s/^/      curl: /' "$tmp/err" >&2; fi
	if [ -s "$tmp/body" ]; then printf '      body: %s\n' "$(head -c 600 "$tmp/body")" >&2; fi
	exit 1
}

# Explains the curl exit codes that mean "not reachable" rather than "wrong answer".
curl_hint() {
	case "$1" in
		6) echo "host name did not resolve" ;;
		7) echo "connection refused: nothing listening, or a firewall in the way" ;;
		28) echo "timed out after ${TIMEOUT}s" ;;
		35) echo "TLS handshake failed" ;;
		51|60) echo "certificate not trusted or does not name this host: pass --cacert, or --connect-host from a container" ;;
		*) echo "curl exit $1" ;;
	esac
}

# request NAME METHOD PATH [JSON] -> sets $code and $ms; body in $tmp/body, headers in $tmp/hdr.
request() {
	local name=$1 method=$2 path=$3 data=${4:-} status=0 out
	local args=("${curl_args[@]}" -X "$method" -D "$tmp/hdr" -o "$tmp/body" -w '%{http_code} %{time_total}')
	if [ -n "$data" ]; then
		args+=(-H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d "$data")
	fi
	if [ -n "${session:-}" ]; then args+=(-H "mcp-session-id: ${session}"); fi
	out=$(curl "${args[@]}" "${URL}${path}" 2>"$tmp/err") || status=$?
	if [ "$status" -ne 0 ]; then fail "$name" "$(curl_hint "$status")"; fi
	code=${out%% *}
	ms=$(awk -v t="${out##* }" 'BEGIN { printf "%d", t * 1000 }')
}

session=""

request health GET /health
[ "$code" = 200 ] || fail health "HTTP $code (503 means the backend is still loading)"
grep -Eq '"status" *: *"ok"' "$tmp/body" || fail health "HTTP 200 but no \"status\": \"ok\""
backend=$(grep -Eo '"backend" *: *"[^"]*"' "$tmp/body" | head -1 | sed -E 's/.*"([^"]*)"$/\1/')
pass health "HTTP 200, backend ${backend:-unknown} (${ms} ms)"

request initialize POST /mcp '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"check-mcp","version":"1"}}}'
[ "$code" = 200 ] || fail initialize "HTTP $code"
session=$(tr -d '\r' < "$tmp/hdr" | awk 'tolower($1) == "mcp-session-id:" { print $2 }')
[ -n "$session" ] || fail initialize "no mcp-session-id header in the response"
server=$(grep -Eo '"serverInfo" *: *\{ *"name" *: *"[^"]*"' "$tmp/body" | sed -E 's/.*"([^"]*)"$/\1/')
[ -n "$server" ] || fail initialize "no serverInfo in the response"
pass initialize "server '${server}', session ${session:0:8}... (${ms} ms)"

request initialized POST /mcp '{"jsonrpc":"2.0","method":"notifications/initialized"}'
case "$code" in 200|202|204) ;; *) fail initialized "HTTP $code" ;; esac

request tools/list POST /mcp '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
[ "$code" = 200 ] || fail tools/list "HTTP $code"
tools=$(grep -Eo '"name" *: *"[a-z0-9_]+"' "$tmp/body" | sed -E 's/.*"([^"]*)"$/\1/' | grep -v '^properties$' | sort -u | tr '\n' ' ')
case " $tools " in
	*" $EXPECT_TOOL "*) ;;
	*) fail tools/list "'$EXPECT_TOOL' not offered; got: ${tools:-nothing}" ;;
esac
pass tools/list "$(printf '%s' "$tools" | wc -w | tr -d ' ') tools, includes ${EXPECT_TOOL} (${ms} ms)"

if [ "$CALL" -eq 1 ]; then
	request tools/call POST /mcp '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"sys1_health","arguments":{}}}'
	[ "$code" = 200 ] || fail tools/call "HTTP $code"
	if grep -q '"isError" *: *true' "$tmp/body"; then fail tools/call "sys1_health returned an error"; fi
	grep -Eq '"probe_ms"' "$tmp/body" || fail tools/call "sys1_health answered without a timed probe"
	served=$(grep -Eo '"served_by" *: *"[^"]*"' "$tmp/body" | head -1 | sed -E 's/.*"([^"]*)"$/\1/')
	pass tools/call "sys1_health ok, served_by ${served:-unknown} (${ms} ms)"
fi

# Close the session so repeated checks leave nothing behind; a failure here is not a reachability failure.
curl "${curl_args[@]}" -o /dev/null -X DELETE -H "mcp-session-id: ${session}" "${URL}/mcp" 2>/dev/null || true
printf 'OK    %s/mcp is reachable and answering\n' "$URL"
