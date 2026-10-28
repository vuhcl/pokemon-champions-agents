# Part 1 — seed fixes (2026-10-27)

No covered row run to a model. Seeds regenerated via `write_seed_manifests()`.

## 1. MT3 / HC2 history

**Before:** `read_team` returns empty slots only; `read_pending` / `read_rejected` empty; **no tool surfaces `constraints`**. The model on t2 onward never saw t1.

**After:** both seeds carry `_message_history` (same pattern as `hd1_history`):

| seed | user t1 (row text) | assistant ack (Vu wording) |
|---|---|---|
| mt3_after_t1 | `No Intimidate.` | `Noted: no Intimidate on this team.` |
| hc2_after_t1 | `No weather.` | `Noted: no weather abilities on this team.` |

Wording chosen from the request-set t1 cells only; ack states the constraint and makes no other claim.

## 2. Constraint representation

| seed | predicate | groundedness | mechanical |
|---|---|---|---|
| MT3 | `no_intimidate` | judgment-only | null |
| HC2 | `no_weather_ability` | judgment-only | null |

**Real path:** `mechanical_kind=ability` means **must-have** that ability. There is **no ban-ability / ban-weather kind**. Recording “No Intimidate.” / “No weather.” through `record_constraint` is therefore also **judgment-only**; predicate text may differ (`no Intimidate` vs hand-written `no_intimidate`). `no_weather_ability` matches the H18b fixture tag family.

Loader fact recorded in `errata.json` `notes`.

## 3. cs_pending evidence

`read_pending` returns only `{number, id, label, species}` — **evidence is not shown** to the model via that tool. Raw pending still held hand-written `usage_rank` / `verified_score` / `threats_countered:seed` strings.

**Fix:** builder clears `evidence` to `()` on each option and clears role kit evidence/provenance on `target_role_decision`. `present_candidates` accepts empty evidence. Species kept: Pelipper, Toxapex, Corviknight (option 2 = Toxapex). Garchomp remains in the threat-counter input pool but is not required among the three presented options.

## 4. Reachability (no model)

**fbc_pending → `commit_slot`:**
- Pending fields: Garchomp / Sand Veil / Sitrus Berry / four moves / Jolly / spread hp4 atk32 spe30.
- After commit: `read_team` slot 1 matches those fields; pending cleared; `slot_commit_error` absent.
- **Fingerprint:** `commit_full_slot` **compares** `pending.provisional_fingerprint` to `provisional.fingerprint` as stored strings (`seed-fbc-garchomp-v1`). It does **not** recompute the fingerprint from slot fields. Separately compares `base_slot_fingerprint` to `slot_fingerprint(current)`.

**cs_pending:**
- `select_option(2)` → class `bound`; intent species Toxapex; pending becomes FBC.
- `reject_option(2)` → class `recorded`; `read_rejected` = Toxapex / user_reject.
- Both succeed → seed usable.

## 5. sha256

```
49d760e40cc7b2e2dc4a4051a96f89cef421211d23cd0586916fca2f071dbaac  cs_pending.json
4337ddd0dc15d319bbef0bc1ea8cbc9f978c45fa9de1768534b291df3de50af6  fbc_pending.json
9d67bd3b7cc38cc7ad5c41fde9be130cdafdaceeb85bcb2f3dff8b34bbfab4f9  hc2_after_t1.json
331da9c022897b7294549b01643ee7f6201cc82ad2ba4a8c74cde670606dd7c7  hd1_history.json
0f6d61eb95dd6678301bdc91a3a746af2c8096f196e85b813f381e7d3f7720b2  mt3_after_t1.json
```

(fbc + hd1 unchanged.)
