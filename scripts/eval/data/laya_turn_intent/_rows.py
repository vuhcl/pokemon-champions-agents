"""Hand-authored utterance→gold-intent rows for the Laya turn_intent spike.

Labels come from ADR / TurnIntentName definitions and classify_pending rules —
never from a classifier. Run write_jsonl.py to emit split files.
"""

from __future__ import annotations

from typing import Any

GRASS_CLAIM = (
    "kind=type; subject=Heliolisk; asserted=Grass; "
    "excerpt=Heliolisk is a Grass-type option"
)
ABILITY_CLAIM = (
    "kind=ability; subject=Incineroar; asserted=Intimidate; "
    "excerpt=Incineroar has Intimidate"
)
ITEM_CLAIM = (
    "kind=item; subject=Pelipper; asserted=Leftovers; "
    "excerpt=Pelipper holds Leftovers"
)
FBC_CTX = (
    "full build confirmation for Pelipper; options: "
    "spread_nature:1[spread_nature]=Modest bulky; "
    "spread_nature:2[spread_nature]=Timid max Spe; "
    "item:1[item]=Damp Rock; item:2[item]=Focus Sash; "
    "moveset:1[moveset]=Hurricane / Weather Ball / Protect / Tailwind"
)
CAND_CTX = "candidate options: Heliolisk, Abomasnow, Whimsicott"
PREF_CTX = "preference options: attacker, support, balanced"
ROSTER_LOCKED = "slot1 Pelipper locked; slot5 Sinistcha locked"


def _r(
    *,
    id: str,
    split: str,
    user_text: str,
    gold_intent: str,
    pending_kind: str = "none",
    pending_context: str = "",
    roster_summary: str = "",
    last_system_claim: str = "",
    deterministic_preempt: bool = False,
    pair_id: str | None = None,
    probe_id: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": id,
        "split": split,
        "user_text": user_text,
        "pending_kind": pending_kind,
        "pending_context": pending_context,
        "roster_summary": roster_summary,
        "last_system_claim": last_system_claim,
        "gold_intent": gold_intent,
        "deterministic_preempt": deterministic_preempt,
        "pair_id": pair_id,
        "probe_id": probe_id,
        "tags": tags or [],
    }


def build_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    # --- Negation shapes (≥3 each; ≥2 held_out) ---
    # type is not (deterministic preempt when claim present)
    for i, (split, text) in enumerate(
        [
            ("held_out", "heliolisk is not grass type"),
            ("held_out", "Heliolisk is not a Grass-type Pokémon"),
            ("dev", "That Heliolisk is not Grass type at all"),
        ],
        start=1,
    ):
        rows.append(
            _r(
                id=f"{split}_neg_type_is_not_{i}",
                split=split,
                user_text=text,
                gold_intent="claim_correction",
                last_system_claim=GRASS_CLAIM,
                deterministic_preempt=True,
                probe_id="neg:type_is_not",
                tags=["negation", "gate_a"],
            )
        )

    for i, (split, text) in enumerate(
        [
            ("held_out", "Heliolisk is not a Grass type"),
            ("held_out", "not a Grass type — Heliolisk isn't that"),
            ("dev", "Heliolisk: not a grass type"),
        ],
        start=1,
    ):
        rows.append(
            _r(
                id=f"{split}_neg_type_not_a_{i}",
                split=split,
                user_text=text,
                gold_intent="claim_correction",
                last_system_claim=GRASS_CLAIM,
                deterministic_preempt=True,
                probe_id="neg:type_not_a",
                tags=["negation", "gate_a"],
            )
        )

    for i, (split, text) in enumerate(
        [
            ("held_out", "Incineroar doesn't have Intimidate"),
            ("held_out", "Incineroar does not have the ability Intimidate"),
            ("dev", "Incineroar don't have Intimidate"),
        ],
        start=1,
    ):
        rows.append(
            _r(
                id=f"{split}_neg_ability_{i}",
                split=split,
                user_text=text,
                gold_intent="claim_correction",
                last_system_claim=ABILITY_CLAIM,
                deterministic_preempt=True,
                probe_id="neg:ability_doesnt_have",
                tags=["negation", "gate_a"],
            )
        )

    for i, (split, text) in enumerate(
        [
            ("held_out", "Pelipper doesn't hold Leftovers"),
            ("held_out", "Pelipper's item isn't Leftovers"),
            ("dev", "Pelipper does not have Leftovers"),
        ],
        start=1,
    ):
        rows.append(
            _r(
                id=f"{split}_neg_item_{i}",
                split=split,
                user_text=text,
                gold_intent="claim_correction",
                last_system_claim=ITEM_CLAIM,
                deterministic_preempt=True,
                probe_id="neg:item_doesnt_hold",
                tags=["negation", "gate_a"],
            )
        )

    # ban shapes: rejection, must not be claim_correction (residual; preempt false)
    for i, (split, text) in enumerate(
        [
            ("held_out", "I don't want Heliolisk"),
            ("held_out", "no Heliolisk"),
            ("dev", "reject Heliolisk"),
        ],
        start=1,
    ):
        rows.append(
            _r(
                id=f"{split}_neg_ban_{i}",
                split=split,
                user_text=text,
                gold_intent="rejection",
                last_system_claim=GRASS_CLAIM,
                deterministic_preempt=False,
                probe_id="neg:ban_not_claim",
                pair_id="pair:claim_correction<->rejection",
                tags=["negation", "dangerous_inversion", "gate_a"],
            )
        )

    # soft dispute residual (isn't / soft phrasing — deterministic often misses)
    for i, (split, text) in enumerate(
        [
            ("held_out", "Heliolisk isn't a Grass type"),
            ("held_out", "that's wrong — Heliolisk isn't Grass"),
            ("dev", "that claim is incorrect"),
        ],
        start=1,
    ):
        rows.append(
            _r(
                id=f"{split}_neg_soft_{i}",
                split=split,
                user_text=text,
                gold_intent="claim_correction",
                last_system_claim=GRASS_CLAIM,
                deterministic_preempt=False,
                probe_id="neg:soft_dispute",
                pair_id="pair:claim_correction<->rejection",
                tags=["negation", "dangerous_inversion", "gate_a"],
            )
        )

    # --- Dangerous pairs (≥3, both directions, ≥2 held_out) ---

    # lock <-> rejection
    rows += [
        _r(
            id="held_out_pair_lock_1",
            split="held_out",
            user_text="lock Pelipper as the rain setter in slot 1",
            gold_intent="lock",
            roster_summary="slot0 empty; slot1 empty",
            pair_id="pair:lock<->rejection",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="held_out_pair_lock_2",
            split="held_out",
            user_text="put Pelipper in slot 1 and lock the species",
            gold_intent="lock",
            roster_summary="slot1 empty",
            pair_id="pair:lock<->rejection",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="dev_pair_rej_vs_lock_1",
            split="dev",
            user_text="I don't want Pelipper on this team",
            gold_intent="rejection",
            pair_id="pair:lock<->rejection",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="held_out_pair_rej_vs_lock_2",
            split="held_out",
            user_text="reject Pelipper, do not lock it",
            gold_intent="rejection",
            pair_id="pair:lock<->rejection",
            tags=["dangerous_inversion", "gate_a"],
        ),
    ]

    # claim_correction <-> rejection (extra both-dir beyond ban/soft above)
    rows += [
        _r(
            id="held_out_pair_cc_1",
            split="held_out",
            user_text="you got Heliolisk's typing wrong",
            gold_intent="claim_correction",
            last_system_claim=GRASS_CLAIM,
            pair_id="pair:claim_correction<->rejection",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="dev_pair_cc_2",
            split="dev",
            user_text="Heliolisk is not Electric either — that claim is false",
            gold_intent="claim_correction",
            last_system_claim=GRASS_CLAIM,
            pair_id="pair:claim_correction<->rejection",
            tags=["dangerous_inversion", "gate_a"],
        ),
    ]

    # restore <-> reset
    rows += [
        _r(
            id="held_out_pair_restore_1",
            split="held_out",
            user_text="restore slot 1's previous item",
            gold_intent="restore",
            roster_summary=ROSTER_LOCKED,
            pair_id="pair:restore<->reset",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="held_out_pair_restore_2",
            split="held_out",
            user_text="put back the old species on slot 5",
            gold_intent="restore",
            roster_summary=ROSTER_LOCKED,
            pair_id="pair:restore<->reset",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="dev_pair_reset_1",
            split="dev",
            user_text="reset everything and start the team over",
            gold_intent="reset",
            pair_id="pair:restore<->reset",
            tags=["dangerous_inversion", "gate_a", "payload_free"],
        ),
        _r(
            id="held_out_pair_reset_2",
            split="held_out",
            user_text="wipe the draft and reset from scratch",
            gold_intent="reset",
            pair_id="pair:restore<->reset",
            tags=["dangerous_inversion", "gate_a", "payload_free"],
        ),
    ]

    # restore <-> restore_constraint
    rows += [
        _r(
            id="held_out_pair_rest_attr_1",
            split="held_out",
            user_text="undo the last species change on slot 1",
            gold_intent="restore",
            roster_summary=ROSTER_LOCKED,
            pair_id="pair:restore<->restore_constraint",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="dev_pair_rest_attr_2",
            split="dev",
            user_text="restore the previous item on slot 1",
            gold_intent="restore",
            roster_summary=ROSTER_LOCKED,
            pair_id="pair:restore<->restore_constraint",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="held_out_pair_rest_con_1",
            split="held_out",
            user_text="restore the previous hard constraint",
            gold_intent="restore_constraint",
            pair_id="pair:restore<->restore_constraint",
            tags=["dangerous_inversion", "gate_a", "payload_free"],
        ),
        _r(
            id="held_out_pair_rest_con_2",
            split="held_out",
            user_text="bring back the constraint we just superseded",
            gold_intent="restore_constraint",
            pair_id="pair:restore<->restore_constraint",
            tags=["dangerous_inversion", "gate_a", "payload_free"],
        ),
        _r(
            id="dev_pair_rest_con_3",
            split="dev",
            user_text="undo the newest-wins constraint change",
            gold_intent="restore_constraint",
            pair_id="pair:restore<->restore_constraint",
            tags=["dangerous_inversion", "gate_a", "payload_free"],
        ),
    ]

    # revise_locked_slot <-> repick_locked_slot
    rows += [
        _r(
            id="held_out_pair_revise_1",
            split="held_out",
            user_text="change slot 1's item to Focus Sash only",
            gold_intent="revise_locked_slot",
            roster_summary=ROSTER_LOCKED,
            pair_id="pair:revise_locked_slot<->repick_locked_slot",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="held_out_pair_revise_2",
            split="held_out",
            user_text="set Pelipper's nature to Modest on the locked slot",
            gold_intent="revise_locked_slot",
            roster_summary=ROSTER_LOCKED,
            pair_id="pair:revise_locked_slot<->repick_locked_slot",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="dev_pair_repick_1",
            split="dev",
            user_text="swap out Sinistcha in slot 5 for something else",
            gold_intent="repick_locked_slot",
            roster_summary=ROSTER_LOCKED,
            pair_id="pair:revise_locked_slot<->repick_locked_slot",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="held_out_pair_repick_2",
            split="held_out",
            user_text="replace the species in slot 5, different Pokémon",
            gold_intent="repick_locked_slot",
            roster_summary=ROSTER_LOCKED,
            pair_id="pair:revise_locked_slot<->repick_locked_slot",
            tags=["dangerous_inversion", "gate_a"],
        ),
    ]

    # revise_locked_slot <-> edit
    rows += [
        _r(
            id="held_out_pair_revise_idle_1",
            split="held_out",
            user_text="on the locked Pelipper, change ability to Drizzle only",
            gold_intent="revise_locked_slot",
            roster_summary=ROSTER_LOCKED,
            pair_id="pair:revise_locked_slot<->edit",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="dev_pair_revise_idle_2",
            split="dev",
            user_text="revise slot 1 item to Damp Rock, field only",
            gold_intent="revise_locked_slot",
            roster_summary=ROSTER_LOCKED,
            pair_id="pair:revise_locked_slot<->edit",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="held_out_pair_edit_fbc_1",
            split="held_out",
            user_text="run Modest, just the nature",
            gold_intent="edit",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:revise_locked_slot<->edit",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="held_out_pair_edit_fbc_2",
            split="held_out",
            user_text="swap item to Leftovers only",
            gold_intent="edit",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:revise_locked_slot<->edit",
            tags=["dangerous_inversion", "gate_a"],
        ),
    ]

    # edit <-> rejection (species swap on full_build = rejection)
    rows += [
        _r(
            id="held_out_pair_edit_ok_1",
            split="held_out",
            user_text="change the moves to Hurricane, Weather Ball, Tailwind, Protect",
            gold_intent="edit",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:edit<->rejection",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="dev_pair_edit_ok_2",
            split="dev",
            user_text="use Choice Specs as the item, field only",
            gold_intent="edit",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:edit<->rejection",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="held_out_pair_rej_fbc_1",
            split="held_out",
            user_text="actually I don't want Pelipper, swap the species",
            gold_intent="rejection",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:edit<->rejection",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="held_out_pair_rej_fbc_2",
            split="held_out",
            user_text="reject this species and show other candidates",
            gold_intent="rejection",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:edit<->rejection",
            tags=["dangerous_inversion", "gate_a"],
        ),
    ]

    # select_build_option <-> compare
    rows += [
        _r(
            id="held_out_pair_select_1",
            split="held_out",
            user_text="spread_nature:1",
            gold_intent="select_build_option",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:select_build_option<->compare",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="held_out_pair_select_2",
            split="held_out",
            user_text="pick item:2",
            gold_intent="select_build_option",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:select_build_option<->compare",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="dev_pair_compare_1",
            split="dev",
            user_text="compare item:1 and item:2",
            gold_intent="compare",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:select_build_option<->compare",
            tags=["dangerous_inversion", "gate_a"],
        ),
        _r(
            id="held_out_pair_compare_2",
            split="held_out",
            user_text="show me how spread_nature:1 stacks up against spread_nature:2",
            gold_intent="compare",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:select_build_option<->compare",
            tags=["dangerous_inversion", "gate_a"],
        ),
    ]

    # continue (abandon-bound) <-> pending_response
    rows += [
        _r(
            id="held_out_pair_continue_1",
            split="held_out",
            user_text="continue to the next slot",
            gold_intent="continue",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:continue<->pending_response",
            tags=["dangerous_inversion", "gate_a", "payload_free"],
        ),
        _r(
            id="held_out_pair_continue_2",
            split="held_out",
            user_text="I'm done here, move on",
            gold_intent="continue",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:continue<->pending_response",
            tags=["dangerous_inversion", "gate_a", "payload_free"],
        ),
        _r(
            id="dev_pair_pr_1",
            split="dev",
            user_text="no",
            gold_intent="pending_response",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:continue<->pending_response",
            tags=["dangerous_inversion", "gate_a", "ambiguous"],
        ),
        _r(
            id="held_out_pair_pr_2",
            split="held_out",
            user_text="wait, what are my options again?",
            gold_intent="pending_response",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:continue<->pending_response",
            tags=["dangerous_inversion", "gate_a", "ambiguous"],
        ),
    ]

    # residual affirm <-> defer paraphrases (outside frozensets)
    rows += [
        _r(
            id="held_out_pair_aff_1",
            split="held_out",
            user_text="looks good to me, ship it",
            gold_intent="continue",  # soft accept → often continue/confirm path; residual gold: treat as continue-shaped accept intent on candidate? 
            # On full_build residual affirm paraphrase without being in frozenset → typically pending_response or continue.
            # Plan: affirm-shaped vs defer-shaped. For full_build, bare affirm→full_slot_confirmed is preempt.
            # Residual affirm paraphrase gold: we treat as wanting to confirm build → but that's full_slot_confirmed which isn't TurnIntentName.
            # Safer gold for residual affirm on full_build: the LLM residual often maps soft accept to continue or pending_response.
            # Per ADR: residual paraphrases outside frozenset hit gap-fill. Soft "looks good" on full_build is closest to wanting confirmation —
            # but parser TurnIntentName has no full_slot_confirmed. Live LLM often emits continue (then abandon gate) or pending_response.
            # Use pending_kind=candidate_selection where affirm→select first is preempt; residual soft affirm on candidate is continue? No.
            # Best: pending_kind=none idle "looks good, keep going" → continue; defer paraphrase → pending_response or a soft-exit.
            pending_kind="none",
            pair_id="pair:affirm<->defer",
            tags=["dangerous_inversion", "gate_a", "payload_free"],
        ),
    ]
    # Fix affirm/defer properly:
    rows = [r for r in rows if r["id"] != "held_out_pair_aff_1"]
    rows += [
        _r(
            id="held_out_pair_aff_1",
            split="held_out",
            user_text="looks good to me, keep going",
            gold_intent="continue",
            pending_kind="none",
            pair_id="pair:affirm<->defer",
            tags=["dangerous_inversion", "gate_a", "payload_free"],
        ),
        _r(
            id="held_out_pair_aff_2",
            split="held_out",
            user_text="that works, proceed",
            gold_intent="continue",
            pending_kind="none",
            pair_id="pair:affirm<->defer",
            tags=["dangerous_inversion", "gate_a", "payload_free"],
        ),
        _r(
            id="dev_pair_def_1",
            split="dev",
            user_text="park this for later",
            gold_intent="pending_response",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:affirm<->defer",
            tags=["dangerous_inversion", "gate_a", "ambiguous"],
        ),
        _r(
            id="held_out_pair_def_2",
            split="held_out",
            user_text="let's shelve this build discussion for now",
            gold_intent="pending_response",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            pair_id="pair:affirm<->defer",
            tags=["dangerous_inversion", "gate_a", "ambiguous"],
        ),
    ]

    # --- Deterministic smokes (not Laya gate-a floors) ---
    rows += [
        _r(
            id="held_out_smoke_yes",
            split="held_out",
            user_text="yes",
            gold_intent="full_slot_confirmed",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            deterministic_preempt=True,
            tags=["deterministic_smoke"],
        ),
        _r(
            id="held_out_smoke_defer",
            split="held_out",
            user_text="defer",
            gold_intent="build_abandoned",
            pending_kind="full_build_confirmation",
            pending_context=FBC_CTX,
            deterministic_preempt=True,
            tags=["deterministic_smoke"],
        ),
        _r(
            id="held_out_smoke_abandon_yes",
            split="held_out",
            user_text="yes",
            gold_intent="continue",
            pending_kind="confirm_abandon_build",
            deterministic_preempt=True,
            tags=["deterministic_smoke"],
        ),
        _r(
            id="held_out_smoke_abandon_no",
            split="held_out",
            user_text="no",
            gold_intent="pending_response",
            pending_kind="confirm_abandon_build",
            deterministic_preempt=True,
            tags=["deterministic_smoke"],
        ),
    ]

    # --- Residual coverage for remaining intents / kinds ---
    coverage = [
        ("held_out", "must be Grass type", "constraint", "none", "", "", False, ["coverage"]),
        ("held_out", "no duplicate items", "constraint", "none", "", "", False, ["coverage"]),
        ("dev", "prefer tailwind support", "constraint", "none", "", "", False, ["coverage"]),
        ("held_out", "switch to trick room", "archetype_change", "none", "", "", False, ["coverage"]),
        ("dev", "pivot to sun instead", "archetype_change", "none", "", "", False, ["coverage"]),
        ("held_out", "show me the current team review", "team_review", "none", "", "", False, ["coverage", "payload_free"]),
        ("dev", "what's on the roster right now", "team_review", "none", "", "", False, ["coverage", "payload_free"]),
        ("held_out", "continue", "continue", "none", "", "", False, ["coverage", "payload_free"]),
        ("held_out", "reset the whole draft", "reset", "none", "", "", False, ["coverage", "payload_free"]),
        ("held_out", "I want a grass type", "constraint", "candidate_selection", CAND_CTX, "", False, ["coverage"]),
        ("held_out", "tell me each option's typing before I choose", "pending_response", "candidate_selection", CAND_CTX, "", False, ["coverage", "ambiguous"]),
        ("dev", "none of these — need something with Intimidate", "constraint", "candidate_selection", CAND_CTX, "", False, ["coverage"]),
        ("held_out", "whatever covers grass types best", "constraint", "completion_preference", PREF_CTX, "", False, ["coverage"]),
        ("dev", "lean toward electric coverage", "constraint", "completion_preference", PREF_CTX, "", False, ["coverage"]),
        ("held_out", "what type is this species again?", "pending_response", "full_build_confirmation", FBC_CTX, "", False, ["coverage", "ambiguous"]),
        ("held_out", "item:1 and spread_nature:2", "select_build_option", "full_build_confirmation", FBC_CTX, "", False, ["coverage"]),
        ("dev", "compare spread_nature:1 and spread_nature:2 before I pick", "compare", "full_build_confirmation", FBC_CTX, "", False, ["coverage"]),
        ("held_out", "bare number is unclear across axes — clarify", "pending_response", "full_build_confirmation", FBC_CTX, "", False, ["coverage", "ambiguous"]),
        ("held_out", "use Incineroar instead of Sinistcha in slot 5", "repick_locked_slot", "none", "", ROSTER_LOCKED, False, ["coverage"]),
        ("dev", "lock Abomasnow species into slot 2", "lock", "none", "", "slot2 empty", False, ["coverage"]),
        ("held_out", "restore_constraint please", "restore_constraint", "none", "", "", False, ["coverage", "payload_free"]),
        ("held_out", "start over from an empty team", "reset", "candidate_selection", CAND_CTX, "", False, ["coverage", "payload_free"]),
        ("dev", "keep building, next mon", "continue", "completion_preference", PREF_CTX, "", False, ["coverage", "payload_free"]),
        ("held_out", "team overview please", "team_review", "full_build_confirmation", FBC_CTX, ROSTER_LOCKED, False, ["coverage", "payload_free"]),
        ("held_out", "different spread", "pending_response", "full_build_confirmation", FBC_CTX, "", False, ["coverage", "ambiguous"]),
        ("dev", "make Spe 252 on this set", "edit", "full_build_confirmation", FBC_CTX, "", False, ["coverage"]),
        ("held_out", "I want intimidate support preference", "constraint", "completion_preference", PREF_CTX, "", False, ["coverage"]),
        ("held_out", "reject Abomasnow because TR", "rejection", "candidate_selection", CAND_CTX, "", False, ["coverage"]),
        ("dev", "something with Levitate next", "constraint", "none", "", ROSTER_LOCKED, False, ["coverage"]),
        ("held_out", "suggest a fire type for the next slot", "constraint", "none", "", ROSTER_LOCKED, False, ["coverage"]),
        ("held_out", "rebuild the set around Life Orb", "edit", "full_build_confirmation", FBC_CTX, "", False, ["coverage"]),
        ("dev", "put the prior constraint back", "restore_constraint", "none", "", "", False, ["coverage", "payload_free"]),
        ("held_out", "archetype: rain", "archetype_change", "none", "", "", False, ["coverage"]),
        ("held_out", "which of these is steel type?", "pending_response", "candidate_selection", CAND_CTX, "", False, ["coverage", "ambiguous"]),
        ("dev", "balanced preference please", "continue", "completion_preference", PREF_CTX, "", True, ["deterministic_smoke"]),
        ("held_out", "2", "slot_candidate_selected", "candidate_selection", CAND_CTX, "", True, ["deterministic_smoke"]),
        ("held_out", "attacker", "continue", "completion_preference", PREF_CTX, "", True, ["deterministic_smoke"]),
    ]
    for i, (split, text, gold, kind, ctx, roster, preempt, tags) in enumerate(coverage, start=1):
        rows.append(
            _r(
                id=f"{split}_cov_{i}",
                split=split,
                user_text=text,
                gold_intent=gold,
                pending_kind=kind,
                pending_context=ctx,
                roster_summary=roster,
                deterministic_preempt=preempt,
                tags=tags,
            )
        )

    return rows
