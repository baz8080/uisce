#!/usr/bin/env bash
# Publish DB as a release of its own, tagged with the build's UTC date and time.
# gh creates the release as a draft, uploads, then publishes it, so the latest
# release always holds a complete uisce.db. usage: scripts/publish-db.sh [DB]
set -euo pipefail

db="${1:-out/uisce.db}"
tag="$(date -u +%Y-%m-%d-%H%M)"
# the asset takes the file's name, and fetch-db.sh asks for uisce.db
if [ "$(basename "$db")" != uisce.db ]; then
  staged="$(mktemp -d)/uisce.db"
  cp "$db" "$staged"
  db="$staged"
fi
gh release create "$tag" "$db" --title "$tag" --notes "Data refresh" --latest
