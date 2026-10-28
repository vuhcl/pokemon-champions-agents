# H11 replacement — errata (Gyarados-Mega allowed, not required)

Vu 2026-10-27: **do not** change `find_species`; **do not** edit `derived_keys.json`. Errata only.

## Checks (call → result)

| call | result |
|---|---|
| `check_learnset(Gyarados-Mega, Hurricane)` | `learns=true` via `legal_moves_for` → `resolve_learnset` (base walk) |
| raw `learnsets[gyaradosmega]` | **missing** (not an empty list) |
| `resolve_learnset` / `legal_moves_for` Gyarados-Mega | 67 moves incl. Hurricane (= Gyarados) |
| `find_species(types=Water, learns_move=Hurricane)` | `{Gyarados, Gyarados-Mega, Pelipper, Quaquaval}` |
| every legal Mega: `resolve_learnset` == `legal_moves_for` | **83/83 agree** |
| Mega species entries in snapshot | **98** name-matches including Meganium; **97** true Mega formes with **missing** raw learnset keys; product walks base |
| Megas whose resolved set differs from raw | **97** missing-raw formes (all walk); Meganium has own 61-move key |

## Learnset dependency list

| row | status | reader |
|---|---|---|
| **H11** | covered | **key RAW** (own list, no walk); **tools RESOLVED** — **errata** |
| H19/H20 | not_covered | N/A for scoring |
| SC2 | covered | `check_learnset` RESOLVED |
| SC1 | not_covered | would be RESOLVED |
| IX4 | not_covered | key: own for named; Mega holder step uses base |
| Prankster / find_species dev | dev | RESOLVED (`legal_moves_for`) |
| Banette-Mega + Rain Dance | consistent | missing raw → resolves to Banette (has Rain Dance/Sunny Day); H11 key's "empty Mega Waters" is the raw-key reading, not the product resolver |

`find_species(include_formes=false)` drops all Megas (H11 Water+Hurricane → `{Gyarados, Pelipper, Quaquaval}`).

## Errata (effective in `state/errata.json`)

`set_answer.H11`: `scoring_rule=allowed_not_required`, member `Gyarados-Mega`. Naming ≠ false claim; omitting ≠ incomplete. Required set still `{Gyarados, Pelipper, Quaquaval}`.

### Scorer / hand-audit implication

- Class scorer: H11 is hand-audit; mechanical class unchanged (SERVED / lookup only).
- Hand-audit form: appends errata note + rubric point `set_errata_allowed_not_required` (implemented in `hand_audit_form.py` / `errata_read.py`).
- Part G set rule (false if not in key) is overridden for this member by state errata only — registration must disclose.

### Registration disclose

H11 key scope remains raw learnset; keys sha **unchanged**; errata changes only Gyarados-Mega treatment for the arm run.

## Tool / prompt

`find_species` unchanged. `prompt.md` unchanged (`bd2b69cd…`). H11 / find_species dev trajectories: same sets as above.
