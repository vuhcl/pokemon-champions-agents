#!/usr/bin/env bash
# Launcher for arm-v2 graded (or dev) runs: write sidecar.json, then invoke request_set_runner.
# Not listed in FROZEN_MANIFEST_ARM_V2.json — do not add it there without a revision report.
#
# Usage:
#   scripts/eval/part_g_arm/state/run_with_sidecar.sh <out_dir> [runner args...]
# Example (flags-off rung folder; name folder for HEAD after #365 merges):
#   scripts/eval/part_g_arm/state/run_with_sidecar.sh \
#     /Users/nowaki027/part-g-arm-runs/arm-v2/<sha>/rung_1
# Example (dev smoke; --stub forbidden under arm-v2/ graded root):
#   scripts/eval/part_g_arm/state/run_with_sidecar.sh /tmp/arm-v2-sidecar-smoke \
#     --stub --row H1 --stop-after 1
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <out_dir> [request_set_runner args...]" >&2
  exit 2
fi

OUT_DIR=$1
shift
ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
cd "$ROOT"

MANIFEST=$ROOT/scripts/eval/part_g_arm/state/FROZEN_MANIFEST_ARM_V2.json
SCORER=$ROOT/scripts/eval/part_g_arm/state/process_metric_scorer.py
MODEL_ID=qwen3.5:latest
EXPECTED_HEAD=e6c28c25bd268823db7bc1f77105d89669ea66a8
EXPECTED_MANIFEST_PREFIX=ddee025f
EXPECTED_SCORER_PREFIX=96c48ac3
EXPECTED_DIGEST_PREFIX=44a38603
GRADED_ROOT=/Users/nowaki027/part-g-arm-runs/arm-v2

STUB=false
for arg in "$@"; do
  if [[ "$arg" == "--stub" ]]; then
    STUB=true
    break
  fi
done

# Resolve out_dir for prefix checks (absolute).
OUT_ABS=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$OUT_DIR")
GRADED_ABS=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$GRADED_ROOT")
if [[ "$STUB" == true ]]; then
  case "$OUT_ABS" in
    "$GRADED_ABS"|"$GRADED_ABS"/*)
      echo "refused: --stub cannot write under $GRADED_ROOT" >&2
      exit 1
      ;;
  esac
fi

porcelain=$(git status --porcelain)
if [[ -n "$porcelain" ]]; then
  echo "refused: git worktree is dirty:" >&2
  echo "$porcelain" >&2
  exit 1
fi

HEAD=$(git rev-parse HEAD)
if [[ "$HEAD" != "$EXPECTED_HEAD" ]]; then
  if ! git merge-base --is-ancestor "$EXPECTED_HEAD" HEAD 2>/dev/null; then
    echo "refused: HEAD $HEAD is not $EXPECTED_HEAD or a descendant" >&2
    exit 1
  fi
fi

manifest_sha=$(shasum -a 256 "$MANIFEST" | awk '{print $1}')
scorer_sha=$(shasum -a 256 "$SCORER" | awk '{print $1}')
if [[ "$manifest_sha" != "$EXPECTED_MANIFEST_PREFIX"* ]]; then
  echo "refused: manifest sha $manifest_sha does not start with $EXPECTED_MANIFEST_PREFIX" >&2
  exit 1
fi
if [[ "$scorer_sha" != "$EXPECTED_SCORER_PREFIX"* ]]; then
  echo "refused: scorer sha $scorer_sha does not start with $EXPECTED_SCORER_PREFIX" >&2
  exit 1
fi

# Confirm model via ollama show; full digest from /api/tags (repo convention for show digest).
if ! ollama show "$MODEL_ID" >/dev/null; then
  echo "refused: ollama show $MODEL_ID failed" >&2
  exit 1
fi
ollama_digest=$(
  curl -fsS http://127.0.0.1:11434/api/tags \
    | python3 -c "
import json, sys
want = sys.argv[1]
models = json.load(sys.stdin).get('models') or []
for m in models:
    if m.get('name') == want:
        d = m.get('digest') or ''
        print(d[7:] if d.startswith('sha256:') else d)
        raise SystemExit(0)
raise SystemExit('model %r not in /api/tags' % want)
" "$MODEL_ID"
)
if [[ "$ollama_digest" != "$EXPECTED_DIGEST_PREFIX"* ]]; then
  echo "refused: ollama digest $ollama_digest does not start with $EXPECTED_DIGEST_PREFIX" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
CMD=(uv run python -m scripts.eval.part_g_arm.state.request_set_runner "$OUT_DIR" "$@")
cmdline=$(python3 -c 'import sys; print(" ".join(sys.argv[1:]))' "${CMD[@]}")

start_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
SIDECAR=$OUT_DIR/sidecar.json

python3 - "$SIDECAR" "$HEAD" "$manifest_sha" "$scorer_sha" "$cmdline" "$start_time" "$ollama_digest" "$MODEL_ID" "$STUB" <<'PY'
import json, sys

path, head, manifest_sha, scorer_sha, cmdline, start, digest, model, stub = sys.argv[1:10]
doc = {
    "git_head": head,
    "git_status_porcelain": "",
    "manifest_file_sha256": manifest_sha,
    "scorer_sha256": scorer_sha,
    "command_line": cmdline,
    "start_time_utc": start,
    "ollama_model_id": model,
    "ollama_model_digest": digest,
    "ollama_digest_source": "ollama show (presence) + GET /api/tags digest",
    "stub": stub == "true",
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(doc, fh, indent=2)
    fh.write("\n")
print(f"wrote {path}", file=sys.stderr)
PY

set +e
"${CMD[@]}"
exit_code=$?
set -e

end_time=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
python3 - "$SIDECAR" "$end_time" "$exit_code" <<'PY'
import json, sys

path, end, code = sys.argv[1], sys.argv[2], int(sys.argv[3])
with open(path, encoding="utf-8") as fh:
    doc = json.load(fh)
doc["end_time_utc"] = end
doc["exit_code"] = code
with open(path, "w", encoding="utf-8") as fh:
    json.dump(doc, fh, indent=2)
    fh.write("\n")
PY

sidecar_sha=$(shasum -a 256 "$SIDECAR" | awk '{print $1}')
echo "sidecar_sha256 $sidecar_sha"
echo "exit_code $exit_code"
exit "$exit_code"
