#!/usr/bin/env bash
# Fail if frozen-zone paths change without override label on PR.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FROZEN_FILE="$ROOT/docs/frozen-zone-paths.txt"

if [[ ! -f "$FROZEN_FILE" ]]; then
  echo "Missing $FROZEN_FILE"
  exit 1
fi

BASE="${GITHUB_BASE_REF:-main}"
if git rev-parse --verify "origin/$BASE" >/dev/null 2>&1; then
  DIFF_RANGE="origin/$BASE...HEAD"
elif git rev-parse --verify "$BASE" >/dev/null 2>&1; then
  DIFF_RANGE="$BASE...HEAD"
else
  DIFF_RANGE="HEAD~1...HEAD"
fi

CHANGED="$(git diff --name-only "$DIFF_RANGE" 2>/dev/null || true)"
if [[ -z "$CHANGED" ]]; then
  echo "frozen-zone-guard: no changed files in range $DIFF_RANGE"
  exit 0
fi

VIOLATIONS=()
while IFS= read -r frozen_line; do
  [[ -z "$frozen_line" || "$frozen_line" =~ ^# ]] && continue
  pattern="${frozen_line%/}"
  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    if [[ "$file" == "$pattern"* ]] || [[ "$file" == "$pattern" ]]; then
      VIOLATIONS+=("$file")
    fi
  done <<< "$CHANGED"
done < "$FROZEN_FILE"

if [[ ${#VIOLATIONS[@]} -eq 0 ]]; then
  echo "frozen-zone-guard: OK (no frozen paths touched)"
  exit 0
fi

if echo "${GITHUB_EVENT_PULL_REQUEST_LABELS:-}" | grep -q "frozen-zone-override"; then
  echo "frozen-zone-guard: override label present — allowing frozen path changes:"
  printf '  %s\n' "${VIOLATIONS[@]}"
  exit 0
fi

echo "frozen-zone-guard: FAIL — frozen paths modified without frozen-zone-override label:"
printf '  %s\n' "${VIOLATIONS[@]}"
exit 1
