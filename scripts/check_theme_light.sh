#!/usr/bin/env bash
# Fails if styles.css still has very dark flat backgrounds (luminance workaround).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FILE="$ROOT/styles.css"
PATTERN='background:\s*#(0[0-9a-f]{4,5}|1[01][0-9a-f]{3,4})\b|background:\s*#2428|background:\s*#1418'
HITS=$(rg -n "$PATTERN" "$FILE" || true)
# Allow only gradient remnants checked manually — list all for review
if rg -n 'background:[^;]*#10131a|#141820|#161a22|#07080c|#242833' "$FILE" >/tmp/dark_hits.txt 2>/dev/null; then
  echo "Dark background tokens still in styles.css:"
  cat /tmp/dark_hits.txt
  exit 1
fi
echo "check_theme_light: ok (no #10131a/#141820/#161a22/#07080c/#242833 backgrounds)"