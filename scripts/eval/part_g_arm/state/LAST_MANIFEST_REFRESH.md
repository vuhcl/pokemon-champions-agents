# Item 3 — draft manifests refreshed (2026-10-28)

`frozen:false` / `status:draft`. No freeze commit.

- `STATE_MANIFEST_PROPOSAL.json` — covered 103/31; form 74/232→74/242; covered_list / errata / discovery / class_scorer shas refreshed.
- `FROZEN_MANIFEST_ARM_STATE.json` — regenerated via `freeze_manifest_arm_state write` (27 files).

## Verify (clean tree)

```bash
uv run python -m scripts.eval.part_g_arm.state.freeze_manifest_arm_state verify
```

Expect **PASS** on a clean tree; **FAIL** if dirty.
