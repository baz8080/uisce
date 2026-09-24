#!/usr/bin/env bash
# Download a release's uisce.db, the latest release unless TAG is given.
# usage: scripts/fetch-db.sh [TAG] [OUT]
set -euo pipefail

tag="${1:-}"
out="${2:-out/uisce.db}"
mkdir -p "$(dirname "$out")"
gh release download ${tag:+"$tag"} --pattern uisce.db -O "$out" --clobber
