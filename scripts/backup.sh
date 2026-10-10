#!/usr/bin/env bash
#
# Back up the entire application volume (database, encryption key, encrypted
# secrets and every workspace) into a single timestamped archive.
#
# Usage: ./scripts/backup.sh [destination-directory]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${1:-$ROOT_DIR/backups}"
VOLUME_NAME="solo-data"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="solo-backup-${STAMP}.tar.gz"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "Docker is not installed."
docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1 \
  || die "Volume '${VOLUME_NAME}' does not exist. Has the app been installed?"

mkdir -p "$DEST"

log "Writing ${DEST}/${ARCHIVE}"
# --rm + a throwaway alpine container keeps the host clean.
docker run --rm \
  -v "${VOLUME_NAME}:/data:ro" \
  -v "${DEST}:/backup" \
  alpine:3.20 \
  tar czf "/backup/${ARCHIVE}" -C /data .

chmod 600 "${DEST}/${ARCHIVE}"
log "Done. Restore with: ./scripts/restore.sh ${DEST}/${ARCHIVE}"
