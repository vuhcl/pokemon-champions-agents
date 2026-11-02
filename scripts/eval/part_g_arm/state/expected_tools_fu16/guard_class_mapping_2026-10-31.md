# Guard class mapping, consolidated (PROPOSAL for Vu's approval, 2026-10-31)

Status: proposal; supersedes `guard_class_mapping_2026-10-30.md` (kept for history). Nothing is built from it until Vu approves. Tool names and token counts are from Cursor's table: flags `tool_fields + wrapper + draft`, tiktoken cl100k_base, **40 tools, 4,668 tokens** (flags-off 3,731). The `guard` rung is cumulative on `draft`, so only draft-rung tool names appear: `lock_slot`, `edit_slot_field` and `commit_full_slot` are hidden there; `lock_fields` and `unlock_fields` are the lock surface. The guard class comes from the parser reading the user message; it is never read from the key. Key classes appear only to show what each expected outcome needs.

## 1. Key class to guard class
| Key class | Guard class | What the guard allows |
|---|---|---|
| SERVED | LOOKUP (facts, rules, legality, numbers) or READ_STATE (what is in my team) | read-only tools |
| ASSUME-STATE, PARTIAL | LOOKUP | read-only tools; the judge checks the stated assumption and coverage |
| MUTATION-OK, MUTATION-REFUSED | WRITE | the write tool the parsed action names, plus build-support lookups and read tools. A refusal row must allow the attempt so the validator produces the refusal |
| NO-MUTATION (hypotheticals) | HYPOTHETICAL | lookup, read, check_hypothetical; no write tool |
| ASK (missing or ambiguous argument) | ASK | read tools only; the reply is a question; the guard stores the asked action |
| FAIL-CLOSED | READ_ONLY_REFUSE | read tools only; the reply declines or states the limit |
| answer to the previous question ("Garchomp.", "Yes, replace it.") | PENDING_ANSWER | the stored asked action becomes the intent and runs as WRITE with the new argument |
| claim checking | stays with the judge | not a guard class |

## 2. Tool bundles (tokens)
| Bundle | Tools | Tokens |
|---|---|---|
| CORE (facts, legality) | get_typing 68, get_abilities 67, check_species_ability 101, check_species_legal 63, check_item_legal 64, get_move_static 79, check_learnset 104, find_species 221 | 767 |
| USAGE | get_usage_items 105, get_usage_teammates 95, get_usage_spreads 88, get_usage_stats 118, get_common_speeds 84, get_meta_threats 95 | 585 |
| NUMBERS | calc_damage 227, get_speed 187, solve_spread 431 | 845 |
| EXTRAS | describe 195, no_lookup_needed 124 | 319 |
| READ | read_team 53, read_pending 55, read_constraints 67, read_archetype 54, read_rejected 55 | 284 |
| HYPO | check_hypothetical | 118 |
| WRITE tools | set_slot 329, lock_fields 114, unlock_fields 96, unlock_slot 90, select_option 102, commit_slot 50, confirm_build 61, reject_pending 63, reject_option 89, reject_all 96, add_constraint 274, restore_constraint 66, change_archetype 119, reset_team 43 | 1,592 |
| show_candidates | state-aware (section 4) | 158 |

Sum: 4,668.

## 3. Guard class to bound tools
| Guard class | Bound | Tokens | vs 4,668 |
|---|---|---|---|
| READ_STATE | READ | 284 | -94% |
| ASK, READ_ONLY_REFUSE | READ + no_lookup_needed | 408 | -91% |
| LOOKUP | CORE + USAGE + NUMBERS + EXTRAS + READ | 2,800 | -40% |
| LOOKUP with a locked anchor (suggest/build) | + show_candidates | 2,958 | -37% |
| HYPOTHETICAL | LOOKUP set + check_hypothetical, no write tool | 2,918 | -37% |
| WRITE: build/draft | CORE + USAGE + READ + set_slot | 1,965 | -58% |
| WRITE: lock | + lock_fields | 1,750 | -63% |
| WRITE: set and lock in one message | + set_slot + lock_fields | 2,079 | -55% |
| WRITE: unlock/clear | + unlock_fields and/or unlock_slot | 1,726 to 1,822 | -61% to -63% |
| WRITE: commit | + commit_slot, confirm_build | 1,747 | -63% |
| WRITE: pick from list | + select_option | 1,738 | -63% |
| WRITE: reject | + 3 reject tools | 1,884 | -60% |
| WRITE: constraint | + add_constraint, restore_constraint | 1,976 | -58% |
| WRITE: archetype / reset | + change_archetype / reset_team | 1,755 / 1,679 | -62% / -64% |
| WRITE + numeric sub-request | + NUMBERS | add 845 | e.g. build + calc 2,810 |
| PENDING_ANSWER | the stored action's row | same | same |

WRITE binds CORE + USAGE only. NUMBERS, describe and no_lookup_needed bind in a write turn only when the parser emits a numeric or explain sub-request. A mixed message is split into sub-requests and the allowed set is their union; a write tool binds only if a sub-request is WRITE.

Estimate on the 113 rows with current proposed classes (69 LOOKUP, 23 WRITE, 9 ASK, 8 HYPOTHETICAL, 4 REFUSE; WRITE averaged at about 2,100): about 2,400 tokens per turn, roughly half of 4,668. An estimate; the run records the real per-turn tool count.

## 4. State-aware availability and rules
- `set_slot`: bound on a build/fill/set request; writes drafts only. A build request never binds `lock_fields`.
- `lock_fields`: only on a lock or confirm request, or a PENDING_ANSWER whose stored action is a lock; not bound if no slot has a valued attribute.
- `unlock_fields`: only on an unlock request for named attributes.
- `unlock_slot`: only on an unlock/clear request or a PENDING_ANSWER confirming a replacement. A lock or set request never binds it.
- Within WRITE only the tool matching the parsed action is bound.
- `replace=true` is a parameter and cannot be unbound. The execution-time check allows it only in a turn where the user just confirmed the replacement. It covers a `set_slot` species swap on a drafted or locked slot and `unlock_slot` on a slot with draft or partly locked values. The refusal names the draft contents, which produces the ASK.
- `show_candidates`: only with a fully locked anchor (all seven attributes) and for the first blank slot. A drafted anchor does not qualify (H18b is a known failure).
- `select_option` and the reject tools: only with a pending screen. `select_option` only if the pending's fingerprint matches the current team (OL10a, option 1); a stale list is unbound and the arm is told to re-run `show_candidates`. Enforced again at execution.
- `commit_slot`, `confirm_build`: only on an explicit commit request. `reset_team`: only on an explicit reset request, never from a hypothetical (MU6).
- A drafted slot is not open for the default-first-open-slot rule.
- Uncertain class: ASK or read-only, never write.

## 5. Execution-time check, pending action, reporting
- The tool node re-checks every call against the turn's allowed set and current state. A call outside the set is not executed; the arm gets a refusal naming the class. A per-turn call cap and a terminal node guarantee a reply.
- On an ASK the guard stores {action, missing argument, slot context}. The next turn is parsed against it; a bare argument is a PENDING_ANSWER. Cleared when executed, refused or contradicted.
- The arm is reported as a harness-constrained agent. Parser accuracy is reported as agreement between parser class and key class (tuning on dev rows, process metric on graded runs, never tuned on). Outcome and process stay separate.

## 6. Decisions for Vu
1. Approve the tables and rules above, including the narrowed WRITE binding (risk: a parser miss on a numeric sub-request removes `calc_damage` from a write turn).
2. LOOKUP stays at 2,800 for now (69 of 113 rows). Option: parser emits a topic (facts / usage / numbers) and LOOKUP binds one bundle, about 1,636 to 2,400 tokens, at the cost of more parser error surface. Recommendation: measure parser agreement on dev rows first.
3. `no_lookup_needed` is bound in LOOKUP, HYPOTHETICAL, ASK, and READ_ONLY_REFUSE (so `enforce_first_turn_tool` can be satisfied by the stub on a first-turn ASK/refusal). It is left out of WRITE, PENDING_ANSWER, and READ_STATE (FU22).
4. Parser implementation (carried over): one structured-output call to the same model per turn, thinking off.
5. The expected-tools CSV has 2 of 113 rows filled (DM1, DM2, draft). `check_expected_tools.py` matches this mapping; the re-audit runs when the lists are filled.
