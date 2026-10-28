# Part 2 — manifest gaps and judge disclosures (proposal only; NO freeze)

## Manifest extensions

See updated `STATE_MANIFEST_PROPOSAL.json` (`frozen: false`).

| field | value |
|---|---|
| arm `num_predict` | **2048** — equals Part G arm `config.py` default (same value; does not differ) |
| judge digest | `sha256:c7597fc90b86aff6965317f37dd5465402284e26382d9b4bf2dfe3ef1491f4b6` |
| judge quantization | nvfp4 |
| judge think | false (`reasoning=False`) |
| judge num_ctx / num_predict | **not set** in `hand_audit_judge.py` (library defaults); recorded as null |
| judge prompt | `89b99005…` — **not tuned** |
| Showdown joint blob | `63bcefe4512a202d75b62e79f2ccc5436527b46e` (`champions-reg-mc.showdown_doubles.v1.json`) |
| in-game blob | `31af0801235dc4158c6206363c70ae8cc2b6417b` |
| legality | `ca5bb8181448765875396ce3b02561923c3e4694` |
| calc | `@smogon/calc` `0.11.0-champions.5d5bf43` (`vendor/smogon-calc`, commit `5d5bf43…`) |
| loader/helpers | listed under `loader_and_helpers.paths`; clean-tree git sha at freeze pins the rest |

## Judge calibration (prompt unchanged)

False passes: **cal-05**, **cal-15**.

| id | planted kind | what was planted |
|---|---|---|
| cal-05 | `planted_unlabeled_assumption` | ASSUME-STATE answer with Spe 80 / “Modest is better” **without stating nature+SP** |
| cal-15 | `planted_reject_all` | User asked to dismiss/clear screen; answer claims **reject_all** of named species |

### By planted kind (n planted → n caught)

| planted kind | n planted | n caught | false_pass |
|---|---|---|---|
| planted_wrong_type | 3 | 3 | 0 |
| planted_unlabeled_assumption | 1 | 0 | 1 (cal-05) |
| planted_flat_yes_no | 2 | 2 | 0 |
| planted_wrong_number | 1 | 1 | 0 |
| planted_fabricated_joint | 1 | 1 | 0 |
| planted_wrong_slot | 1 | 1 | 0 |
| planted_claim_legal | 1 | 1 | 0 |
| planted_reject_all | 1 | 0 | 1 (cal-15) |
| planted_item_clause_trap | 1 | 1 | 0 |
| **total planted** | **12** | **10** | **2** |

**Rubric source:** judge user payload is `{rubric, user_turns, final_text, tool_results}` from the row key / calibration item only — never another model’s verdict.
