# Mega eev gate run — FINDING (stop)

Keys sha (pre-model, unchanged): `896a732846424e4630b62ad610cd6d80336e95fd015055cccb7e82b01f313d5a`  
Prompt: `bd2b69cde151fdb4dd2431c294ca46f4fbc251f54cebd82a13844d4eba0aaf86`  
Model: `qwen3.5:latest` digest `44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f`  
temp 0 / think off / num_ctx 16384 / allow_live false  
Transcript: `/Users/nowaki027/part-g-arm-state-out-mega-dev/`  
Transcript sha256: `7a86cc0cb631771fb5cd77335134534d060d3903d862182dd990a43d120c38b5`  
Run record sha256: `0b7dd43c49ba46d33109da3c80861e0e80ea0c6078b605fba5c0a85a9b61f155`

## Per-row

| row | class | tools | pass | note |
|---|---|---|---|---|
| `dev-mega-bare-hyp` | lookup only | `check_species_legal` only | **FAIL** | never called `check_hypothetical`; answered “legal…can be put on your team” with no stone fact |
| `dev-mega-edit-refuse` | refused | `edit_slot_field` | pass | restated keep-stone / base+Leftovers from tool |
| `dev-mega-lock-ok` | wrote / wrote | `edit_slot_field` then `lock_slot` | pass | Mega+Kangaskhanite on slot 1 |

## Finding (`dev-mega-bare-hyp`)

**Final text:** “Yes, Kangaskhan-Mega is legal in Champions VGC. It can be put on your team.”

**Tool:** `check_species_legal({species: Kangaskhan-Mega})` → legal true. No `check_hypothetical`, so no `mega_stone` / Kangaskhanite requirement surfaced.

**Key expected:** lookup only via `check_hypothetical` with `verdict=mega_stone`, stone requirement stated from the tool (not a flat refusal, not an invented “fully allowed” claim).

**Stop:** no `prompt.md` or tools edit. Vu decides accept-as-finding vs fourth prompt revision (which would require rerunning every eev row).

## Registration note (fingerprint)

`commit_full_slot` **compares** `pending["provisional_fingerprint"]` to `provisional.fingerprint` (two stored strings); it does **not** recompute the fingerprint. The FBC seed uses the hand-written string `seed-fbc-garchomp-v1`.
