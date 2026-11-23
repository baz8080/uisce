#!/usr/bin/env bash
# Open one issue per finding uisce-check wrote, unless one with that title
# already exists, open or closed: each occurrence is raised once.
# usage: scripts/open-check-issues.sh [DIR]
set -euo pipefail

dir="${1:-out/checks}"
shopt -s nullglob
files=("$dir"/*.md)
if [ ${#files[@]} -eq 0 ]; then
  echo "no data check tripped"
  exit 0
fi

gh label create data-check --description "Raised by the data build" --color D93F0B 2>/dev/null || true
existing="$(gh issue list --state all --label data-check --limit 1000 --json title --jq '.[].title')"

for file in "${files[@]}"; do
  title="$(head -n 1 "$file")"
  if grep -Fxq -- "$title" <<<"$existing"; then
    echo "already raised: $title"
    continue
  fi
  # the repository's owner is assigned, so the issue reaches a person
  tail -n +3 "$file" | gh issue create --title "$title" --label data-check \
    ${GITHUB_REPOSITORY_OWNER:+--assignee "$GITHUB_REPOSITORY_OWNER"} --body-file -
done
