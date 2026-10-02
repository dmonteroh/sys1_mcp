#!/usr/bin/env bash
# Mint the TLS certificate the sys1-mcp daemon serves, with mkcert, covering every
# name a client reaches it by: loopback, the current LAN IP, and the names and
# address a Podman or Docker container uses for the host.
# Writes sys1-mcp.pem and sys1-mcp-key.pem; installs nothing.
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${SYS1_CERT_OUT:-$REPO_ROOT/tmp/certificate}
FORCE=0
DEFAULTS=1
PODMAN=1
EXTRA=()

usage() {
	cat <<'USAGE'
Usage: mint-cert.sh [--out DIR] [--name NAME]... [--no-defaults] [--no-podman]
                    [--force] [NAME...]

  --out DIR      where to write sys1-mcp.pem and sys1-mcp-key.pem
                 (default <repo>/tmp/certificate, or $SYS1_CERT_OUT)
  --name NAME    add a DNS name or IP to the certificate; repeatable, and bare
                 positional arguments are added the same way
  --no-defaults  use only the names given, not the default set below
  --no-podman    do not ask a running Podman container for the host address
  --force        overwrite an existing certificate in DIR

Default names: localhost, 127.0.0.1, ::1, host.docker.internal,
host.containers.internal, the current LAN IP, and the address Podman gives
containers for the host. Both addresses are read at run time: the LAN IP from the
default interface, the Podman one from a running container's /etc/hosts (skipped
with a note when none runs). Re-mint when either changes. Add this machine's own
names, such as its .local name, with --name.

To serve the result, copy both files to ~/.config/sys1-mcp/tls/ and restart:
  sys1-mcp/scripts/restart-warm.sh
USAGE
}

while [ $# -gt 0 ]; do
	case "$1" in
		--out) OUT=$2; shift 2 ;;
		--name) EXTRA+=("$2"); shift 2 ;;
		--no-defaults) DEFAULTS=0; shift ;;
		--no-podman) PODMAN=0; shift ;;
		--force) FORCE=1; shift ;;
		-h|--help) usage; exit 0 ;;
		-*) printf 'unknown argument: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
		*) EXTRA+=("$1"); shift ;;
	esac
done

command -v mkcert >/dev/null || { printf 'mkcert is not installed (brew install mkcert)\n' >&2; exit 1; }

lan_ip() {
	local iface
	iface=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
	[ -n "$iface" ] && ipconfig getifaddr "$iface" 2>/dev/null || true
}

# The address host.containers.internal resolves to inside a container. Podman sets
# it per machine, and neither `podman machine inspect` nor `podman info` reports it,
# so it is read from a running container's /etc/hosts.
podman_host_ip() {
	command -v podman >/dev/null || return 0
	local id ip
	for id in $(podman ps -q 2>/dev/null); do
		ip=$(podman exec "$id" cat /etc/hosts 2>/dev/null | awk '/host\.containers\.internal/ { print $1; exit }')
		if [ -n "$ip" ]; then printf '%s\n' "$ip"; return 0; fi
	done
}

names=()
if [ "$DEFAULTS" -eq 1 ]; then
	names+=(localhost 127.0.0.1 ::1 host.docker.internal host.containers.internal)
	ip=$(lan_ip)
	if [ -n "$ip" ]; then
		names+=("$ip")
	else
		printf 'note: no LAN IP found on the default interface; the certificate will not name one\n' >&2
	fi
	if [ "$PODMAN" -eq 1 ]; then
		ip=$(podman_host_ip)
		if [ -n "$ip" ]; then
			names+=("$ip")
		else
			printf 'note: no running Podman container to read the host address from; containers must use host.docker.internal or host.containers.internal by name\n' >&2
		fi
	fi
fi
names+=(${EXTRA[@]+"${EXTRA[@]}"})
[ ${#names[@]} -gt 0 ] || { printf 'no names to put on the certificate\n' >&2; exit 2; }

# Drop duplicates, keeping the first occurrence's order.
unique=()
for name in "${names[@]}"; do
	case " ${unique[*]-} " in *" $name "*) ;; *) unique+=("$name") ;; esac
done

cert=$OUT/sys1-mcp.pem
key=$OUT/sys1-mcp-key.pem
if [ "$FORCE" -eq 0 ] && { [ -e "$cert" ] || [ -e "$key" ]; }; then
	printf '%s already holds a certificate; pass --force to replace it\n' "$OUT" >&2
	exit 1
fi

mkdir -p "$OUT"
chmod 700 "$OUT"
mkcert -cert-file "$cert" -key-file "$key" "${unique[@]}"
chmod 600 "$key"

ca=$(mkcert -CAROOT)/rootCA.pem
printf '\ncertificate  %s\nkey          %s\nnames        %s\n' "$cert" "$key" "${unique[*]}"
if command -v openssl >/dev/null; then
	printf 'expires      %s\n' "$(openssl x509 -in "$cert" -noout -enddate | cut -d= -f2)"
	openssl verify -CAfile "$ca" "$cert" >/dev/null && printf 'chain        verifies against %s\n' "$ca"
fi
printf '\nContainers verify it with that root CA; copy it in, e.g. to /tmp/mkcert-rootCA.pem.\n'
printf 'To serve it: cp %s %s ~/.config/sys1-mcp/tls/ && sys1-mcp/scripts/restart-warm.sh\n' "$cert" "$key"
