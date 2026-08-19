#!/bin/sh
# Refresh the vendored shared UI from ../statusui (see src/uisce/ui/UPSTREAM).
set -eu
here="$(cd "$(dirname "$0")/.." && pwd)"
exec "$here/../statusui/sync.sh" "$here/src/uisce/ui"
