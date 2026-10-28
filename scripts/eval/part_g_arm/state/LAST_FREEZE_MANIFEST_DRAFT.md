# Freeze preparation item 3 — FROZEN manifest draft

**Not frozen.** `status: draft` in `FROZEN_MANIFEST_ARM_STATE.json`. Vu approves before any freeze commit.

## Commands

```bash
# regenerate draft table from FILES
uv run python -m scripts.eval.part_g_arm.state.freeze_manifest_arm_state write

# on a CLEAN tree only:
uv run python -m scripts.eval.part_g_arm.state.freeze_manifest_arm_state verify
```

## Dirty-tree check (shown)

Verify with untracked/modified files → **FAIL** (`dirty git tree (clean tree required)`), exit 1.  
After this commit lands and the tree is clean, the same `verify` must **PASS** (or fail only on sha drift).

## Draft contents

- schema `part_g_arm_state_frozen_manifest_v0`
- 27 listed paths (prompt, tools, covered_list, errata, runner/scorer/compare/audit/judge, seeds, eev keys, clopper_pearson, freeze script, config, run_params)
- keys_sha256 `e7067254…` (Part G keys pin, not rewritten)
- model digest / num_predict 2048 recorded beside file table
