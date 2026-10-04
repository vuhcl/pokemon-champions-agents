# Gate 0 — UX cost (relabeled, Step0 addendum)

## Sampling caveat

All llm_authored rows in this corpus have pending_presentation kind None (idle) at message time. There is no mid-flow evidence in this corpus. Mid-flow assurance rests entirely on the passthrough-test inventory, the per-kind template table, and hostile tests over idle plus every PendingPresentation.kind.

**unique_UX_count:** 0
**stop_for_vu:** False
**pending_kind_counts:** `{'None': 19}`
**all_llm_authored_rows_idle:** True

## S2 / S8 recorded outcomes

- S2 qwen2.5: `MISROUTED` (`S2__qwen2.5_7b__merged_usage_dir__r0.json`) — Not in llm_authored table (turn0 intent was not free-text pending_response).
- S2 qwen3.5: `FAIL-CLOSED` (`S2__qwen3.5_latest__merged_usage_dir__r0.json`)
- S8 qwen2.5: `FAIL-CLOSED` (`S8__qwen2.5_7b__merged_usage_dir__r0.json`)
- S8 qwen3.5: `FAIL-CLOSED` (`S8__qwen3.5_latest__merged_usage_dir__r0.json`)

## D1 under-A check (report-only)

- pending_kind: `None` (idle)
- user: Should I run max Def, max Sp. Def, or something in between for Sinistcha?
- under A idle: Unmatched line: UNMATCHED_REPLY_PREFIX ('Didn't catch that.') + format_turn idle body (empty roster / no review). Loses the model's Def/SpD/balanced clarify.
- under A full_build: Unmatched line: CLASSIFY_FAIL_USER_MSG (name field/value/scope) + _format_full_build body + full_build footer (yes / option ids / compare / edit / defer). Spread-axis options in the body can absorb a Def/SpD preference ask better than idle refuse; still not the model's tailored three-way question. UX loss vs model prose: modest on full_build (footer/body carry actions); larger on idle. Log as accepted Approach A tradeoff — do not change plan.
- verdict: Acceptable under A for full_build (generic field ask + build UI); idle is a clear UX loss vs this model clarify — worth logging, not unique_UX (no pending state to rebuild from).

## Full llm_authored table

| request_id | model | pending_kind | bucket | outcome | reason | message |
|---|---|---|---|---|---|---|
| S4 | qwen2.5_7b | None | unactionable_offer | FAIL-CLOSED | Asks which locked pick to swap for a Kingambit threat; unmatched path does not execute a swap or bind to candidate_selection. Recorded outcome=FAIL-CLOSED (transcript `S4__qwen2.5_7b__merged_usage_dir__r0.json`). | Which of your picks do you want to swap for something that threatens Kingambit? |
| S6 | qwen2.5_7b | None | echo_soft_refuse | FAIL-CLOSED | Echoes the Farigiraf-vs-Hatterene comparison as a bare question. (transcript `S6__qwen2.5_7b__merged_usage_dir__r0.json`, outcome=FAIL-CLOSED). | Why did you pick Farigiraf over Hatterene? |
| S8 | qwen2.5_7b | None | echo_soft_refuse | FAIL-CLOSED | Echoes the 'best criteria for evaluating a team' ask without a team-review action. (transcript `S8__qwen2.5_7b__merged_usage_dir__r0.json`, outcome=FAIL-CLOSED). | What do you consider the best criteria for evaluating a team in Reg M-C? |
| i7 | qwen2.5_7b | None | echo_soft_refuse | FAIL-CLOSED | Echoes the Torkoal+Scovillain pairing question. (transcript `i7__qwen2.5_7b__merged_usage_dir__r0.json`, outcome=FAIL-CLOSED). | Which Pokémon pairs with both Torkoal and Scovillain? |
| i8L | qwen2.5_7b | None | echo_soft_refuse | FAIL-CLOSED | Echoes the Hatterene support question. (transcript `i8L__qwen2.5_7b__merged_usage_dir__r0.json`, outcome=FAIL-CLOSED). | What support does Hatterene need? |
| C2 | qwen2.5_7b | None | echo_soft_refuse | FAIL-CLOSED | Echoes Jolly-vs-Adamant outspeed question; no calc on unmatched. (transcript `C2__qwen2.5_7b__merged_usage_dir__r0.json`, outcome=FAIL-CLOSED). | Does Jolly vs Adamant change which threats your Garchomp outspeeds? |
| C3 | qwen2.5_7b | None | echo_soft_refuse | FAIL-CLOSED | Echoes max-Attack Kingambit OHKO question; no calc on unmatched. (transcript `C3__qwen2.5_7b__merged_usage_dir__r0.json`, outcome=FAIL-CLOSED). | Does max Attack on Kingambit change what it OHKOs? |
| S2 | qwen3.5_latest | None | unactionable_offer | FAIL-CLOSED | Offers to find a bulky Fire-type for slot 4 and asks roster status; idle unmatched cannot open candidate discovery for that ask. Recorded outcome=FAIL-CLOSED (transcript `S2__qwen3.5_latest__merged_usage_dir__r0.json`). | I'd be happy to help you find a bulky Fire-type Pokémon for slot 4! However, I don't have visibility into your curren... |
| S4 | qwen3.5_latest | None | unactionable_offer | FAIL-CLOSED | Claims no roster visibility and asks which slot to swap; idle unmatched does not open a swap/candidate screen. Recorded outcome=FAIL-CLOSED (transcript `S4__qwen3.5_latest__merged_usage_dir__r0.json`). | I don't have visibility into your current roster state to identify which pick is weakest. Could you specify which slo... |
| S7 | qwen3.5_latest | None | defect_prose | FAIL-CLOSED | Asserts no restriction on duplicate Choice Scarf / Item Clause — false for Reg M-C (logged defect). Recorded outcome=FAIL-CLOSED (transcript `S7__qwen3.5_latest__merged_usage_dir__r0.json`). | Yes, you can run two Choice Scarf users on your team - there's no restriction against duplicate items in standard com... |
| S8 | qwen3.5_latest | None | unactionable_offer | FAIL-CLOSED | Offers to find strong Reg M-C teams/archetypes; idle unmatched cannot run team search or archetype browse. Recorded outcome=FAIL-CLOSED (transcript `S8__qwen3.5_latest__merged_usage_dir__r0.json`). | I can help you find strong Reg M-C teams! Could you tell me more about what you're looking for? Are you interested in... |
| i6L | qwen3.5_latest | None | unactionable_offer | FAIL-CLOSED | Offers to place Garchomp+Scarf in a slot with build details; idle unmatched does not lock that set. Recorded outcome=FAIL-CLOSED (transcript `i6L__qwen3.5_latest__merged_usage_dir__r0.json`). | Could you clarify which roster slot you'd like to use Garchomp with Scarf in? Also, are there any other build details... |
| i7 | qwen3.5_latest | None | echo_soft_refuse | FAIL-CLOSED | Soft pairing help restating Torkoal/Scovillain ask. (transcript `i7__qwen3.5_latest__merged_usage_dir__r0.json`, outcome=FAIL-CLOSED). | I'd be happy to help with pairing suggestions! Could you clarify what you're looking for? Are Torkoal and Scovillain ... |
| C1 | qwen3.5_latest | None | unactionable_offer | FAIL-CLOSED | Offers outspeed analysis if threats are named; idle unmatched does not invoke @smogon/calc. Recorded outcome=FAIL-CLOSED (transcript `C1__qwen3.5_latest__merged_usage_dir__r0.json`). | I can help you analyze that! To give you a useful answer, I'd need to know which opponents you're most concerned abou... |
| C4 | qwen3.5_latest | None | unactionable_offer | FAIL-CLOSED | Offers Modest-vs-Timid Pelipper advice needing team strategy; idle unmatched has no provisional/build screen. Recorded outcome=FAIL-CLOSED (transcript `C4__qwen3.5_latest__merged_usage_dir__r0.json`). | To help you decide between Modest and Timid on Pelipper, I'd need to know more about your team composition and strate... |
| D1 | qwen3.5_latest | None | unactionable_offer | FAIL-CLOSED | Offers Max Def / Max SpD / balanced spread choices for Sinistcha with no pending spread or full_build screen to bind the answer to. Recorded outcome=FAIL-CLOSED (transcript `D1__qwen3.5_latest__merged_usage_dir__r0.json`). | Which spread would you prefer? Max Defense, max Special Defense, or a balanced EV distribution? |
| P1 | qwen3.5_latest | None | defect_prose | FAIL-CLOSED | Treats illegal Chi-Yu + Choice Specs as a usable OHKO line (logged defect). Recorded outcome=FAIL-CLOSED (transcript `P1__qwen3.5_latest__merged_usage_dir__r0.json`). | I can help with that! Specs Chi-Yu (Choice Specs) has strong STAB Fire moves that could potentially OHKO Kingambit de... |
| P2 | qwen3.5_latest | None | defect_prose | FAIL-CLOSED | Treats illegal Miraidon as slottable with Scarf (logged defect). Recorded outcome=FAIL-CLOSED (transcript `P2__qwen3.5_latest__merged_usage_dir__r0.json`). | Which slot would you like to use Miraidon with Scarf on? Also, are you looking to edit an existing locked slot or add... |
| P3 | qwen3.5_latest | None | defect_prose | FAIL-CLOSED | Offers to add illegal Walking Wake / support for it (logged defect). Recorded outcome=FAIL-CLOSED (transcript `P3__qwen3.5_latest__merged_usage_dir__r0.json`). | I can help with that! Are you looking to add Walking Wake to your team, or are you asking about what kind of support ... |

## Hostile-test scope

Idle plus EVERY PendingPresentation.kind (state.py PendingPresentation.kind). Do not narrow to gap-fill-reachable only. Kinds that do not call _gap_fill today still parametrize; prove with file:line and assert user-visible output lacks hostile prose.

