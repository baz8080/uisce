#!/usr/bin/env bash
# Publish DB as today's release asset uisce.db without ever leaving a release
# with neither a uisce.db nor a complete uisce.db.next. `gh release upload
# --clobber` deletes before it uploads, so a second build on the same day
# uploads to uisce.db.next and renames it in only once it has landed;
# fetch-db.sh falls back to it in between. usage: scripts/publish-db.sh [DB]
set -euo pipefail

db="${1:-out/uisce.db}"
tag="$(date -u +%Y-%m-%d)"

# "<name> <REST url>" per asset. `gh release view` finds a draft by its pending
# tag, which GET releases/tags/<tag> does not.
assets() { gh release view "$@" --json assets --jq '.assets[] | "\(.name) \(.apiUrl)"'; }
url() { awk -v n="$1" '$1 == n { print $2 }' <<<"$2"; }
rename_in() { gh api -X PATCH "$1" -f name=uisce.db >/dev/null; }
create() { gh release create "$tag" "$db" --title "$tag" --notes "Data refresh"; }

# A swap an earlier run left half done, on the latest published release: that
# is yesterday's when the run that died was the last of its day.
latest="$(assets || true)"
if [ -z "$(url uisce.db "$latest")" ] && [ -n "$(url uisce.db.next "$latest")" ]; then
  rename_in "$(url uisce.db.next "$latest")"
fi

if ! draft="$(gh release view "$tag" --json isDraft --jq .isDraft 2>&1)"; then
  # anything but a missing release (a 5xx, a rate limit) fails the step
  [[ "$draft" == *"release not found"* ]] || { echo "$draft" >&2; exit 1; }
  create
  exit 0
fi
if [ "$draft" = "true" ]; then
  # a create killed between its draft and its publish; nothing reads a draft
  gh release delete "$tag" --yes
  create
  exit 0
fi

staged="$(dirname "$db")/uisce.db.next"
ln -f "$db" "$staged"
gh release upload "$tag" "$staged" --clobber
list="$(assets "$tag")"
next="$(url uisce.db.next "$list")"
if [ -z "$next" ]; then
  echo "::error::uisce.db.next is not on release $tag after its upload; uisce.db left in place" >&2
  exit 1
fi
old="$(url uisce.db "$list")"
if [ -n "$old" ]; then
  gh api -X DELETE "$old"
fi
rename_in "$next"
