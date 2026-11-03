#!/usr/bin/env bash
# Smoke checks for run_with_sidecar.sh refusals (FU32). Not a graded run.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$ROOT"
LAUNCH=$ROOT/scripts/eval/part_g_arm/state/run_with_sidecar.sh

if [[ -n "$(git status --porcelain)" ]]; then
  echo "refused: test requires a clean tree" >&2
  git status --porcelain >&2
  exit 2
fi

fail=0

# --stub under graded root
out=/Users/nowaki027/part-g-arm-runs/arm-v2/_sidecar_refuse_stub
command rm -rf "$out" 2>/dev/null || true
set +e
"$LAUNCH" "$out" --stub --row H1 --stop-after 1 >/tmp/sidecar_stub_refuse.out 2>/tmp/sidecar_stub_refuse.err
code=$?
set -e
if [[ $code -eq 0 ]]; then
  echo "FAIL: --stub under arm-v2/ exited 0" >&2
  fail=1
elif [[ -e "$out/sidecar.json" || -e "$out/transcript.json" ]]; then
  echo "FAIL: --stub under arm-v2/ wrote artifacts" >&2
  fail=1
else
  echo "PASS: --stub under graded root refused (exit $code)"
  rg -n 'refused: --stub' /tmp/sidecar_stub_refuse.err >/dev/null
fi
command rm -rf "$out" 2>/dev/null || true

if [[ $fail -ne 0 ]]; then
  exit 1
fi
echo "all refusal checks in this script passed"
