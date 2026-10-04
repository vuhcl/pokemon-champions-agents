#!/usr/bin/env bash
# Rebase onto origin/main and push with bounded retries.
# Caller must already have created the local commit(s) to publish.
set -euo pipefail

REMOTE="${PUSH_TO_MAIN_REMOTE:-origin}"
BRANCH="${PUSH_TO_MAIN_BRANCH:-main}"
RETRIES="${PUSH_TO_MAIN_RETRIES:-3}"
BACKOFF_SECS="${PUSH_TO_MAIN_BACKOFF_SECS:-5}"

restore_stash() {
  local stash_ref="$1"
  if [[ -n "$stash_ref" ]]; then
    git stash pop "$stash_ref" || {
      echo "push_to_main: failed to restore stash $stash_ref after error" >&2
      return 1
    }
  fi
}

if git rev-parse --is-shallow-repository 2>/dev/null | grep -qx true; then
  git fetch --unshallow "$REMOTE" "$BRANCH" 2>/dev/null \
    || git fetch --unshallow "$REMOTE" 2>/dev/null \
    || true
fi

attempt=1
while [[ "$attempt" -le "$RETRIES" ]]; do
  stash_ref=""
  git fetch "$REMOTE" "$BRANCH"

  if [[ -n "$(git status --porcelain)" ]]; then
    # Include untracked so rebuild outputs cannot block rebase.
    git stash push --include-untracked -m "push_to_main"
    stash_ref="$(git stash list -1 --format='%gd')"
  fi

  if ! git rebase "$REMOTE/$BRANCH"; then
    git rebase --abort 2>/dev/null || true
    restore_stash "$stash_ref" || true
    echo "::error::conflict rebasing onto ${REMOTE}/${BRANCH}; refusing force-push" >&2
    exit 1
  fi

  if git push "$REMOTE" "HEAD:$BRANCH"; then
    if [[ -n "$stash_ref" ]]; then
      if ! git stash pop "$stash_ref"; then
        echo "::warning::stash pop failed after successful push to ${REMOTE}/${BRANCH}; push already done, dirty files no longer needed" >&2
      fi
    fi
    exit 0
  fi

  # Push rejected (likely non-fast-forward). Restore stash for the next attempt;
  # the next loop iteration fetches and rebases again from current HEAD.
  if [[ -n "$stash_ref" ]]; then
    restore_stash "$stash_ref" || true
  fi

  if [[ "$attempt" -eq "$RETRIES" ]]; then
    break
  fi
  sleep $((BACKOFF_SECS * attempt))
  attempt=$((attempt + 1))
done

echo "::error::push_to_main failed after ${RETRIES} attempts" >&2
exit 1
