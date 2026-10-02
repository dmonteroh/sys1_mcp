#!/usr/bin/env bash
# Mint the TLS certificate the sys1-mcp daemon serves, with mkcert, covering every
# name a client reaches it by: loopback, the current LAN IP, and the names and
# address a Podman or Docker container uses for the host.
# Writes sys1-mcp.pem and sys1-mcp-key.pem; installs them only with --install.
set -euo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
OUT=${SYS1_CERT_OUT:-$REPO_ROOT/tmp/certificate}
FORCE=0
INSTALL=0
TLS_DIR=${SYS1_TLS_DIR:-$HOME/.config/sys1-mcp/tls}
DEFAULTS=1
PODMAN=1
EXTRA=()

usage() {
	cat <<'USAGE'
Usage: mint-cert.sh [--out DIR] [--name NAME]... [--no-defaults] [--no-podman]
                    [--force] [--install] [NAME...]

  --out DIR      where to write sys1-mcp.pem and sys1-mcp-key.pem
                 (default <repo>/tmp/certificate, or $SYS1_CERT_OUT)
  --name NAME    add a DNS name or IP to the certificate; repeatable, and bare
                 positional arguments are added the same way
  --no-defaults  use only the names given, not the default set below
  --no-podman    do not ask a running Podman container for the host address
  --force        overwrite an existing certificate in DIR
  --install      after minting, serve it: back up the pair in the server's TLS
                 directory (~/.config/sys1-mcp/tls, or $SYS1_TLS_DIR), copy the new
                 pair in, restart with sys1-mcp/scripts/restart-warm.sh, and check
                 with tools/scripts/check-mcp.sh. A failed check restores the
                 backup and restarts again. Keep every name current clients use:
                 a name dropped from the certificate stops verifying

Default names: localhost, 127.0.0.1, ::1, host.docker.internal,
host.containers.internal, the current LAN IP, and the address Podman gives
containers for the host. Both addresses are read at run time: the LAN IP from the
default interface, the Podman one from a running container's /etc/hosts (skipped
with a note when none runs). Re-mint when either changes. Add this machine's own
names, such as its .local name, with --name.

Without --install nothing is served: the server reads the pair from its TLS
directory, so copy both files there and run sys1-mcp/scripts/restart-warm.sh.
USAGE
}

while [ $# -gt 0 ]; do
	case "$1" in
		--out) OUT=$2; shift 2 ;;
		--name) EXTRA+=("$2"); shift 2 ;;
		--no-defaults) DEFAULTS=0; shift ;;
		--no-podman) PODMAN=0; shift ;;
		--force) FORCE=1; shift ;;
		--install) INSTALL=1; shift ;;
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

if [ "$INSTALL" -eq 0 ]; then
	printf 'Not served yet. To serve it: %s --force --install (with the same names), or copy\n' "$0"
	printf 'both files to %s and run sys1-mcp/scripts/restart-warm.sh.\n' "$TLS_DIR"
	exit 0
fi

live_cert=$TLS_DIR/sys1-mcp.pem
live_key=$TLS_DIR/sys1-mcp-key.pem
restart=$REPO_ROOT/sys1-mcp/scripts/restart-warm.sh
check=$REPO_ROOT/tools/scripts/check-mcp.sh

printf '\n== install into %s\n' "$TLS_DIR"
mkdir -p "$TLS_DIR"
chmod 700 "$TLS_DIR"
backup=""
if [ -e "$live_cert" ] || [ -e "$live_key" ]; then
	backup=$TLS_DIR/backup-$(date +%Y%m%d-%H%M%S)
	mkdir -p "$backup"
	chmod 700 "$backup"
	for f in "$live_cert" "$live_key"; do
		if [ -e "$f" ]; then cp -p "$f" "$backup/"; fi
	done
	printf 'backed up the served pair to %s\n' "$backup"
fi
install -m 644 "$cert" "$live_cert"
install -m 600 "$key" "$live_key"
printf 'copied the new pair in\n'

printf '\n== restart\n'
restart_status=0
"$restart" || restart_status=$?

printf '\n== check\n'
if "$check"; then
	if [ "$restart_status" -ne 0 ]; then
		printf '\nThe new certificate is served and the check passed, but restart-warm.sh exited %s; see its output above.\n' "$restart_status" >&2
		exit 1
	fi
	printf '\nInstalled and serving.%s\n' "${backup:+ Previous pair kept in $backup.}"
	exit 0
fi

# The check failed: put the previous pair back so a bad certificate never stays live.
printf '\n== rollback\n' >&2
if [ -z "$backup" ]; then
	printf 'The check failed and there was no previous pair to restore; the new one is still in %s.\n' "$TLS_DIR" >&2
	exit 1
fi
if [ -e "$backup/sys1-mcp.pem" ]; then install -m 644 "$backup/sys1-mcp.pem" "$live_cert"; fi
if [ -e "$backup/sys1-mcp-key.pem" ]; then install -m 600 "$backup/sys1-mcp-key.pem" "$live_key"; fi
printf 'restored the previous pair from %s\n' "$backup" >&2
if "$restart" && "$check"; then
	printf '\nRolled back: the previous certificate is served again. The new one is still in %s.\n' "$OUT" >&2
else
	printf '\nRolled back, but the server still fails its check; investigate before relying on it.\n' >&2
fi
exit 1
