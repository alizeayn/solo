#!/usr/bin/env bash
#
# Restore the application volume from an archive produced by backup.sh.
#
# DESTRUCTIVE: replaces the current database, secrets and workspaces.
# Requires an explicit confirmation unless --yes is passed.
#
# Usage: ./scripts/restore.sh <archive.tar.gz> [--yes]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARCHIVE="${1:-}"
ASSUME_YES=0
[[ "${2:-}" == "--yes" ]] && ASSUME_YES=1
VOLUME_NAME="solo-data"

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[warn]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

[[ -n "$ARCHIVE" ]] || die "Usage: ./scripts/restore.sh <archive.tar.gz> [--yes]"
[[ -f "$ARCHIVE" ]] || die "Archive not found: $ARCHIVE"

command -v docker >/dev/null 2>&1 || die "Docker is not installed."
docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1 \
  || die "Volume '${VOLUME_NAME}' does not exist."

ARCHIVE_ABS="$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")"
ARCHIVE_DIR="$(dirname "$ARCHIVE_ABS")"
ARCHIVE_FILE="$(basename "$ARCHIVE_ABS")"

if [[ "$ASSUME_YES" -ne 1 ]]; then
  warn "This will DELETE the current database, secrets and workspaces in volume '${VOLUME_NAME}'."
  read -r -p "Type 'restore' to continue: " reply
  [[ "$reply" == "restore" ]] || die "Aborted."
fi

log "Stopping the service"
(cd "$ROOT_DIR" && docker compose stop) || warn "Could not stop the service; continuing."

log "Restoring ${ARCHIVE_FILE}"
docker run --rm \
  -v "${VOLUME_NAME}:/data" \
  -v "${ARCHIVE_DIR}:/backup:ro" \
  alpine:3.20 \
  sh -c "rm -rf /data/* /data/.[!.]* 2>/dev/null; tar xzf '/backup/${ARCHIVE_FILE}' -C /data"

log "Starting the service"
(cd "$ROOT_DIR" && docker compose start)

log "Restore complete."
