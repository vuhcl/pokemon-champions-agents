# Mega eev rows — keys recorded before model run

Species: **Kangaskhan-Mega** / stone **Kangaskhanite** (legal; not Salamence/Charizard; not in covered request-set prompts, fixtures, or seeds).

| | sha256 |
|---|---|
| `dev_keys.json` (pre-model) | `896a732846424e4630b62ad610cd6d80336e95fd015055cccb7e82b01f313d5a` |
| `dev_rows.json` | `b7e31f60ae2af645d6275774a518c1abc0a93990663c4603de571dc9e827a311` |
| prompt | `bd2b69cde151fdb4dd2431c294ca46f4fbc251f54cebd82a13844d4eba0aaf86` |
| row count | **44** (was 41) |

## Key text

| row | classes | key_text | tool justification |
|---|---|---|---|
| `dev-mega-bare-hyp` | lookup only | Class lookup only. Must call check_hypothetical; final verdict mega_stone. Message must state the Kangaskhanite requirement from the tool (not a flat refusal, not an invented rule). Team draft and pending unchanged. | check_hypothetical on a bare Mega returns verdict mega_stone naming the mapped stone (fact from tool; draft unchanged). |
| `dev-mega-edit-refuse` | refused | Class refused. Slot 1 remains Kangaskhan-Mega holding Kangaskhanite (no silent species/item change). Tool refusal offers keep-stone or base+Leftovers; model must not invent a different rule. | edit_slot_field item→non-stone on a Mega+stone slot refuses via mega_stone; species and item stay put. |
| `dev-mega-lock-ok` | wrote / wrote | Classes wrote then wrote. After turn 2, slot 1 is species-locked Kangaskhan-Mega with item Kangaskhanite. No mega_stone refusal text on the successful path. | item-first edit_slot_field(Kangaskhanite) then lock_slot(Kangaskhan-Mega) writes both; product allows Mega when the stone is already held. |

Model run: not started when this note was written.
