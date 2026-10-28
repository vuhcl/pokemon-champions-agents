# Seed-fix note

`cursor_seed_fixes_manifest.md` was **not present** in the worktree (searched repo root, `state/`, `claude/`, Downloads, Desktop, agent transcripts). No seed code changed this round.

Self-check against Part 3 seeds (still load; shas unchanged):

| seed | status |
|---|---|
| cs_pending | loads; 3 options with `source=threat`; option 2 = Toxapex |
| fbc_pending | loads; Garchomp FBC fingerprint consistent |
| mt3 / hc2 | judgment-only constraints as designed |
| hd1_history | history length 2; runner prepends as prior turns |

If Vu attaches the manifest, apply it in a follow-up commit before tool builds.
