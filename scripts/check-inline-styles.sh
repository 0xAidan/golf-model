#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_SRC="${ROOT}/frontend/src"
MAX_INLINE=120

if command -v rg >/dev/null 2>&1; then
  count="$(rg -c 'style=\{\{' "${FRONTEND_SRC}" 2>/dev/null | awk -F: '{s+=$2} END {print s+0}')"
else
  count="$(grep -r 'style={{' "${FRONTEND_SRC}" --include='*.tsx' --include='*.ts' 2>/dev/null | wc -l | tr -d ' ')"
fi

if [[ "${count}" -gt "${MAX_INLINE}" ]]; then
  echo "FAIL: found ${count} inline style={{ occurrences in ${FRONTEND_SRC} (max ${MAX_INLINE})"
  grep -r 'style={{' "${FRONTEND_SRC}" --include='*.tsx' --include='*.ts' 2>/dev/null | head -30
  exit 1
fi

echo "PASS: ${count} inline style={{ occurrences (max ${MAX_INLINE})"
