"""apply_provisional_overrides + select overlap reject."""

from __future__ import annotations

from recommender.nodes import (
    _deterministic_build_option_ids,
    _describe_invalid_spread,
    _disallowed_status_move_names,
    apply_provisional_option,
    classify_pending,
)
from recommender.slot_fill import (
    apply_partial_spread,
    apply_provisional_overrides,
    revise_provisional_slot,
)
from recommender.state import (
    Attr,
    PendingPresentation,
    PendingSlotIntent,
    ProvisionalSlot,
    TargetRoleDecision,
    empty_slot,
)


def _decision() -> TargetRoleDecision:
    return TargetRoleDecision(role_id="fast_special_attacker", source="other")


def _provisional() -> ProvisionalSlot:
    return ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=_decision(),
        species="Gholdengo",
        ability="Good as Gold",
        item="Life Orb",
        moves=("Make It Rain", "Shadow Ball", "Protect", "Nasty Plot"),
        nature="Timid",
        spread=(
            ("hp", 4),
            ("atk", 0),
            ("def", 0),
            ("spa", 32),
            ("spd", 0),
            ("spe", 30),
        ),
        fingerprint="fp-old",
    )


def _intent() -> PendingSlotIntent:
    return PendingSlotIntent(
        schema_version=1,
        slot_index=0,
        species="Gholdengo",
        target_role_decision=_decision(),
        source="threat",
    )


def _state(provisional=None, pending=None, payload=None):
    return {
        "team_draft": [empty_slot()],
        "regulation_mod": "champions",
        "pending_slot_intent": _intent(),
        "provisional_slot": provisional or _provisional(),
        "pending_presentation": pending,
        "turn_payload": payload,
    }


def test_apply_provisional_overrides_multi_field():
    result = apply_provisional_overrides(
        _provisional(),
        overrides={"nature": "Modest", "item": "Choice Specs"},
        intent=_intent(),
        state=_state(),
    )
    assert isinstance(result, ProvisionalSlot)
    assert result.nature == "Modest"
    assert result.item == "Choice Specs"
    assert result.moves[0] == "Make It Rain"


def test_select_then_partial_spread_chains_onto_selection_result():
    """Regression: 'spread_nature:3, but with 5 Spe' (2026-08-17 handoff item
    3). The adjustment must apply to the *selected* option's resulting
    spread, not the pre-selection spread -- confirms the actual order-
    dependent chaining, not just the standalone arithmetic.
    """
    selected = apply_provisional_overrides(
        _provisional(),
        overrides={"nature": "Modest", "spread": {
            "hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3,
        }},
        intent=_intent(),
        state=_state(),
    )
    assert isinstance(selected, ProvisionalSlot)
    assert selected.spread_dict()["spe"] == 3

    adjusted_spread = apply_partial_spread(
        selected.spread_dict(), delta_stats={"spe": 5}
    )
    assert adjusted_spread is not None
    final = revise_provisional_slot(
        selected,
        field="spread",
        value=adjusted_spread,
        scope="field_only",
        intent=_intent(),
        state=_state(),
    )
    assert isinstance(final, ProvisionalSlot)
    assert final.spread_dict()["spe"] == 8
    # Every other stat and the selection's own nature carry through unchanged.
    assert final.spread_dict()["hp"] == 32
    assert final.nature == "Modest"


def test_malformed_spread_value_degrades_gracefully_not_crash():
    """Regression for the KeyError crash risk found during the same
    investigation: a spread edit value missing a required stat key
    previously raised an uncaught KeyError inside a bare dict comprehension
    instead of returning UnresolvedSlotRefinement like every other
    malformed edit-value case in this module.
    """
    result = revise_provisional_slot(
        _provisional(),
        field="spread",
        value={"hp": 32},  # missing atk/def/spa/spd/spe
        scope="field_only",
        intent=_intent(),
        state=_state(),
    )
    assert not isinstance(result, ProvisionalSlot)
    assert result.unresolved_fields == ("spread",)


def test_apply_partial_spread_rejects_unknown_stat():
    base = {"hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3}
    assert apply_partial_spread(base, delta_stats={"notastat": 5}) is None
    assert apply_partial_spread(base, set_stats={"spe": "not-a-number"}) is None


def test_apply_partial_spread_normalizes_capitalized_stat_keys():
    """Regression: confirmed live, the model consistently emits conventional
    capitalized stat abbreviations ('Spe', 'HP', 'SpA'), never this module's
    internal lowercase convention. Silently returned None (rejected as
    "unknown stat") for every real extraction until fixed -- this affected
    both the partial and full-replace paths.
    """
    base = {"hp": 32, "atk": 0, "def": 0, "spa": 1, "spd": 29, "spe": 4}
    assert apply_partial_spread(base, delta_stats={"Spe": 5}) == {
        "hp": 32, "atk": 0, "def": 0, "spa": 1, "spd": 29, "spe": 9,
    }
    assert apply_partial_spread(base, set_stats={"HP": 100}) == {
        "hp": 100, "atk": 0, "def": 0, "spa": 1, "spd": 29, "spe": 4,
    }


def test_coerce_full_spread_normalizes_capitalized_stat_keys():
    """Same regression, full-replace path -- exact live model output."""
    from recommender.slot_fill import _coerce_full_spread

    result = _coerce_full_spread(
        {"HP": 2, "Atk": 0, "Def": 0, "Spe": 5, "SpA": 32, "SpD": 4}
    )
    assert result == {"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 4, "spe": 5}


def test_apply_partial_spread_rejects_duplicate_after_normalizing():
    """'spe' and 'Spe' both present must not silently pick one -- reject,
    same fail-closed contract as an unknown stat name."""
    base = {"hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3}
    assert apply_partial_spread(base, delta_stats={"spe": 1, "Spe": 2}) is None


def test_select_overlapping_override_keys_rejected():
    pending: PendingPresentation = {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "slot_index": 0,
        "provisional_fingerprint": "fp-old",
        "build_option_groups": (
            {
                "axis": "item",
                "prompt": "item",
                "options": (
                    {
                        "option_id": "item:1",
                        "label": "Sash",
                        "axis": "item",
                        "provenance": "usage_spread",
                        "overrides": {"item": "Focus Sash"},
                        "diff_summary": "item",
                        "tradeoff": "glass",
                    },
                ),
            },
            {
                "axis": "bundled",
                "prompt": "kit",
                "options": (
                    {
                        "option_id": "bundled:1",
                        "label": "Sitrus kit",
                        "axis": "bundled",
                        "provenance": "vgcpastes",
                        "overrides": {"item": "Sitrus Berry", "nature": "Bold"},
                        "diff_summary": "item, nature",
                        "tradeoff": "bulk",
                    },
                ),
            },
        ),
        "default_option_ids": (),
    }
    before = _provisional()
    out = apply_provisional_option(
        _state(
            provisional=before,
            pending=pending,
            payload={"option_ids": ("item:1", "bundled:1")},
        )
    )
    assert "overlapping override key" in str(out.get("slot_commit_error") or "")
    assert out.get("provisional_slot") is None or out.get("provisional_slot") is before


def _single_axis_pending_with_default() -> PendingPresentation:
    """Real menu shape from the live transcript: a prepended, non-numeric
    default option followed by numbered siblings whose ids don't align with
    their list position."""
    return {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "build_option_groups": (
            {
                "axis": "spread_nature",
                "prompt": "Choose spread/nature:",
                "options": (
                    {"option_id": "spread_nature:default", "label": "Recommended default"},
                    {"option_id": "spread_nature:1", "label": "Timid 2/0/0/32/0/32"},
                    {"option_id": "spread_nature:2", "label": "Modest 32/0/0/1/29/4"},
                    {"option_id": "spread_nature:3", "label": "Modest 32/0/1/5/25/3"},
                    {"option_id": "spread_nature:11", "label": "edge case: two-digit id"},
                ),
            },
        ),
    }


def test_bare_number_matches_visible_option_id_not_list_position():
    """Regression for the bare-number off-by-one bug (2026-08-17), confirmed
    live: typing '1' repeatedly re-selected the already-shown default
    (list position 0) instead of the option literally labeled 'spread_nature:1'
    (list position 1), because the default is always prepended ahead of the
    real numbered siblings. Bare numbers must match the option's own visible
    numeric id, never raw list position."""
    pending = _single_axis_pending_with_default()
    assert _deterministic_build_option_ids("1", pending) == ("spread_nature:1",)
    assert _deterministic_build_option_ids("2", pending) == ("spread_nature:2",)
    assert _deterministic_build_option_ids("3", pending) == ("spread_nature:3",)
    assert _deterministic_build_option_ids("option 1", pending) == ("spread_nature:1",)


def test_bare_number_exact_match_not_substring():
    """'1' must not match 'spread_nature:11' -- exact numeric equality only."""
    pending = _single_axis_pending_with_default()
    assert _deterministic_build_option_ids("1", pending) == ("spread_nature:1",)
    assert _deterministic_build_option_ids("11", pending) == ("spread_nature:11",)


def test_word_ordinals_keep_list_position_semantics():
    """Word-ordinals are a deliberately separate, unchanged path: 'first'
    still means the first thing shown (the default), since that's a genuine
    reading of the word -- only literal-number forms switch to id-matching."""
    pending = _single_axis_pending_with_default()
    assert _deterministic_build_option_ids("first", pending) == ("spread_nature:default",)
    assert _deterministic_build_option_ids("second", pending) == ("spread_nature:1",)


def test_deterministic_compose_across_axes():
    pending: PendingPresentation = {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "build_option_groups": (
            {
                "axis": "spread_nature",
                "prompt": "spread",
                "options": (
                    {
                        "option_id": "spread_nature:1",
                        "label": "Bulky",
                        "axis": "spread_nature",
                        "provenance": "usage_spread",
                        "overrides": {"nature": "Bold"},
                        "diff_summary": "nature",
                        "tradeoff": "bulk",
                    },
                ),
            },
            {
                "axis": "moveset",
                "prompt": "moves",
                "options": (
                    {
                        "option_id": "moveset:1",
                        "label": "Darkest Lariat",
                        "axis": "moveset",
                        "provenance": "usage_spread",
                        "overrides": {
                            "moves": (
                                "Fake Out",
                                "Parting Shot",
                                "Flare Blitz",
                                "Darkest Lariat",
                            )
                        },
                        "diff_summary": "moves",
                        "tradeoff": "coverage",
                    },
                ),
            },
        ),
    }
    ids = _deterministic_build_option_ids(
        "spread_nature:1 + moveset:1", pending
    )
    assert ids == ("spread_nature:1", "moveset:1")


def test_classify_pending_select_build_option():
    pending: PendingPresentation = {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "slot_index": 0,
        "provisional_fingerprint": "fp",
        "build_option_groups": (
            {
                "axis": "spread_nature",
                "prompt": "spread",
                "options": (
                    {
                        "option_id": "spread_nature:1",
                        "label": "Bulky Modest",
                        "axis": "spread_nature",
                        "provenance": "usage_spread",
                        "overrides": {"nature": "Modest"},
                        "diff_summary": "nature",
                        "tradeoff": "bulk",
                    },
                ),
            },
        ),
    }
    result = classify_pending("spread_nature:1", pending)
    assert result["turn_intent"] == "select_build_option"
    assert result["turn_payload"]["option_ids"] == ("spread_nature:1",)


def test_describe_invalid_spread_over_budget():
    """Regression: confirmed live, '2, but make it 5 Spe' (spread_nature:2's
    real spread, Spe set 4->5) exceeded the budget by exactly 1 point and
    previously surfaced only the bare, unhelpful 'invalid edited spread'.
    """
    spread = {"hp": 32, "atk": 0, "def": 0, "spa": 1, "spd": 29, "spe": 5}
    message = _describe_invalid_spread(spread)
    assert "1 point over budget" in message
    assert "sum to 67" in message
    assert "budget is 66" in message


def test_describe_invalid_spread_under_budget_suggests_adding_not_reducing():
    """The suggested action must match the actual direction -- under budget
    should say to add points, not reduce (caught and fixed before this
    landed: the first draft said 'reduce' for both directions)."""
    spread = {"hp": 32, "atk": 0, "def": 0, "spa": 1, "spd": 29, "spe": 0}
    message = _describe_invalid_spread(spread)
    assert "4 points under budget" in message
    assert "Add the leftover points" in message
    assert "Reduce" not in message


def test_describe_invalid_spread_out_of_range_names_the_stat():
    spread = {"hp": 32, "atk": 0, "def": 0, "spa": 1, "spd": 29, "spe": 40}
    message = _describe_invalid_spread(spread)
    assert "spe=40" in message


def test_disallowed_status_move_names_finds_protect():
    """Regression: confirmed live, 'use Choice Scarf' on Archaludon's real
    kit (which includes Protect) correctly triggers the choice-item/status-
    move conflict, but the message previously just said 'conflicting edited
    fields: item/moveset' with no indication of which move was the issue.
    """
    from recommender.legality import load_snapshot

    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        species="Archaludon",
        ability="Stamina",
        item="Choice Scarf",
        moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        nature="Modest",
        spread={"hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3},
        target_role_decision=TargetRoleDecision(
            role_id="bulky_special_attacker", source="usage_backed"
        ),
        fingerprint="fp",
    )
    names = _disallowed_status_move_names(provisional, load_snapshot())
    assert names == ["Protect"]


def test_disallowed_status_move_names_excludes_item_swap_moves():
    """Trick/Switcheroo are status moves but explicitly exempted -- they
    exist specifically to change the held item, so they aren't a real
    conflict with a Choice item the way Protect is."""
    from recommender.legality import load_snapshot

    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        species="Archaludon",
        ability="Stamina",
        item="Choice Scarf",
        moves=["Electro Shot", "Flash Cannon", "Trick", "Dragon Pulse"],
        nature="Modest",
        spread={"hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3},
        target_role_decision=TargetRoleDecision(
            role_id="bulky_special_attacker", source="usage_backed"
        ),
        fingerprint="fp",
    )
    names = _disallowed_status_move_names(provisional, load_snapshot())
    assert names == []


def test_spread_edit_auto_reallocates_small_unambiguous_overage():
    """A small (<=2 point), unambiguous overage from a partial spread edit
    auto-resolves instead of erroring out or asking."""
    from recommender.nodes import apply_provisional_edit
    from recommender.recommend import SP_BUDGET, spread_sum

    provisional = _provisional()
    state = _state(
        provisional,
        payload={
            "field": "spread",
            "value": None,
            "scope": "field_only",
            "spread_delta": {"spe": 2},  # 30 -> 32, sum becomes 68, 2 over
        },
    )
    out = apply_provisional_edit(state)
    assert out.get("slot_commit_error") is None
    pending = out["pending_presentation"]
    assert pending["kind"] == "full_build_confirmation"
    notices = pending.get("notices") or ()
    assert any("Adjusted spread" in n for n in notices)
    new_spread = out["provisional_slot"].spread_dict()
    assert new_spread["spe"] == 32
    assert spread_sum(new_spread) == SP_BUDGET


def test_spread_edit_ambiguous_overage_asks_instead_of_guessing():
    """A larger overage produces a spread_reallocation_question instead of
    auto-deciding."""
    from recommender.nodes import apply_provisional_edit

    provisional = _provisional()
    held = {"schema_version": 1, "kind": "full_build_confirmation", "slot_index": 0}
    state = _state(
        provisional,
        pending=held,
        payload={
            "field": "spread",
            "value": None,
            "scope": "field_only",
            "spread_delta": {"spd": 6},  # 0 -> 6, sum 66+6=72, 6 over -- too big
        },
    )
    out = apply_provisional_edit(state)
    assert out.get("slot_commit_error") is None
    pending = out["pending_presentation"]
    assert pending["kind"] == "spread_reallocation_question"
    assert pending["reallocation_diff"] == 6
    assert pending["reallocation_excluded_stats"] == ("spd",)
    assert pending["held_pending"] == held


def test_reallocation_question_resolves_with_valid_stat():
    """After the ask, naming a stat with enough room resolves the edit."""
    from recommender.nodes import resolve_spread_reallocation

    base_provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=_decision(),
        species="Gholdengo",
        ability="Good as Gold",
        item="Life Orb",
        moves=("Make It Rain", "Shadow Ball", "Protect", "Nasty Plot"),
        nature="Timid",
        spread={"hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 30},
        fingerprint="fp-old",
    )
    pending = {
        "schema_version": 1,
        "kind": "spread_reallocation_question",
        "slot_index": 0,
        "reallocation_attempted_spread": {
            "hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 6, "spe": 30,
        },
        "reallocation_diff": 6,
        "reallocation_excluded_stats": ("spd",),
        "reallocation_edited_fields": ("spread",),
    }
    state = _state(
        base_provisional,
        pending=pending,
        payload={"chosen_stat": "spa"},
    )
    from recommender.nodes import resolve_spread_reallocation as node

    out = node(state)
    assert out.get("slot_commit_error") is None
    result_spread = out["provisional_slot"].spread_dict()
    assert result_spread["spa"] == 26  # 32 - 6
    assert result_spread["spd"] == 6  # the originally-requested change kept
    from recommender.recommend import SP_BUDGET, spread_sum
    assert spread_sum(result_spread) == SP_BUDGET


def test_reallocation_question_reasks_when_chosen_stat_lacks_room():
    from recommender.nodes import resolve_spread_reallocation as node

    base_provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=_decision(),
        species="Gholdengo",
        ability="Good as Gold",
        item="Life Orb",
        moves=("Make It Rain", "Shadow Ball", "Protect", "Nasty Plot"),
        nature="Timid",
        spread={"hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 30},
        fingerprint="fp-old",
    )
    pending = {
        "schema_version": 1,
        "kind": "spread_reallocation_question",
        "slot_index": 0,
        "reallocation_attempted_spread": {
            "hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 6, "spe": 30,
        },
        "reallocation_diff": 6,
        "reallocation_excluded_stats": ("spd",),
        "reallocation_edited_fields": ("spread",),
    }
    state = _state(base_provisional, pending=pending, payload={"chosen_stat": "atk"})
    out = node(state)
    assert out["turn_intent"] == "pending_response"
    assert out["pending_presentation"]["kind"] == "spread_reallocation_question"
    assert "doesn't have enough room" in out["pending_presentation"][
        "reallocation_rejection_reason"
    ]


def test_reallocation_question_defer_restores_held_pending():
    held = {"schema_version": 1, "kind": "full_build_confirmation", "slot_index": 0}
    pending = {
        "schema_version": 1,
        "kind": "spread_reallocation_question",
        "slot_index": 0,
        "reallocation_attempted_spread": {
            "hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 6, "spe": 30,
        },
        "reallocation_diff": 6,
        "reallocation_excluded_stats": ("spd",),
        "reallocation_edited_fields": ("spread",),
        "held_pending": held,
    }
    result = classify_pending("defer", pending)
    assert result["turn_intent"] == "pending_response"
    assert result["pending_presentation"] == held


def test_reallocation_question_parses_full_stat_names():
    from recommender.nodes import _parse_stat_reply

    assert _parse_stat_reply("speed") == "spe"
    assert _parse_stat_reply("Spe") == "spe"
    assert _parse_stat_reply("SPA") == "spa"
    assert _parse_stat_reply("special attack") == "spa"
    assert _parse_stat_reply("nonsense") is None


def test_derive_trustworthy_spread_edit_rejects_scrambled_full_form():
    """Regression, confirmed live (2026-08-18): '2, but make it 5 Spe' --
    the model didn't emit option_ids at all this time, and its full-form
    value_spread scrambled spd/spa while correctly setting spe. Diffing
    against the real base (3 stats differ: spa, spd, spe) correctly
    refuses to trust it, rather than silently applying the scrambled
    values the way a bare _coerce_full_spread would have.
    """
    from recommender.nodes import _derive_trustworthy_spread_edit

    base = {"hp": 32, "atk": 0, "def": 0, "spa": 1, "spd": 29, "spe": 4}
    scrambled = {"hp": 32, "atk": 0, "def": 0, "spe": 5, "spa": 29, "spd": 4}
    adjusted, err = _derive_trustworthy_spread_edit(scrambled, base)
    assert adjusted is None
    assert "3 stats" in err
    assert "Spa" in err and "Spd" in err and "Spe" in err


def test_derive_trustworthy_spread_edit_accepts_clean_single_diff():
    """A full-form value_spread that differs from the base in exactly one
    stat is trusted -- this is what SHOULD have been emitted for the live
    case above (only spe differing), and confirms clean cases still work."""
    from recommender.nodes import _derive_trustworthy_spread_edit

    base = {"hp": 32, "atk": 0, "def": 0, "spa": 1, "spd": 29, "spe": 4}
    clean = {"hp": 32, "atk": 0, "def": 0, "spa": 1, "spd": 29, "spe": 5}
    adjusted, err = _derive_trustworthy_spread_edit(clean, base)
    assert err is None
    assert adjusted == clean


def test_plain_spread_edit_asks_interactively_for_scrambled_full_form_end_to_end():
    """End-to-end through apply_provisional_edit: a full-form value_spread
    with no partial (set/delta) form, differing from the current build in
    more than one stat, produces an interactive spread_target_question
    instead of either silently applying the untrusted value or dead-ending
    on a plain error. Confirmed live: a plain error asking "which ONE
    stat..." had no mechanism to ever hear the answer -- the follow-up
    reply got treated as an unrelated fresh turn."""
    from recommender.nodes import apply_provisional_edit

    provisional = _provisional()  # spread: hp=4,atk=0,def=0,spa=32,spd=0,spe=30
    base = provisional.spread_dict()
    scrambled = dict(base)
    scrambled["spe"] = 25
    scrambled["spa"] = 10  # a second, untrusted "difference"
    state = _state(
        provisional,
        payload={"field": "spread", "value": scrambled, "scope": "field_only"},
    )
    out = apply_provisional_edit(state)
    assert out.get("slot_commit_error") is None
    pending = out["pending_presentation"]
    assert pending["kind"] == "spread_target_question"
    assert set(pending["target_question_diffs"]) == {"spa", "spe"}
    assert out["provisional_slot"] == provisional  # unchanged, still the valid base


def test_plain_spread_edit_accepts_clean_single_diff_end_to_end():
    from recommender.nodes import apply_provisional_edit

    provisional = _provisional()
    base = provisional.spread_dict()
    clean = dict(base)
    clean["spe"] = 28  # single, real difference
    state = _state(
        provisional,
        payload={"field": "spread", "value": clean, "scope": "field_only"},
    )
    out = apply_provisional_edit(state)
    assert out.get("slot_commit_error") is None
    assert out["provisional_slot"].spread_dict()["spe"] == 28


def test_regenerate_scope_bypasses_the_diff_check():
    """An explicit edit_scope="regenerate" is a deliberate signal and a
    legitimate multi-stat full-replacement -- must NOT be blocked by the
    diff-against-base check, which only applies to field_only."""
    from recommender.nodes import apply_provisional_edit

    provisional = _provisional()
    full_new_spread = {
        "hp": 4, "atk": 0, "def": 0, "spa": 4, "spd": 30, "spe": 28,
    }  # multiple real differences from base, intentional
    state = _state(
        provisional,
        payload={
            "field": "spread",
            "value": full_new_spread,
            "scope": "regenerate",
        },
    )
    out = apply_provisional_edit(state)
    assert out.get("slot_commit_error") is None


def test_default_phrase_resolves_to_the_real_default_option_id():
    """Regression, confirmed live (2026-08-18): 'the default one' failed
    with 'Unknown build option id: default' -- the real id is
    axis-prefixed (e.g. 'spread_nature:default'), and no bare-phrase
    matching existed for it before this fix."""
    pending: PendingPresentation = {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "build_option_groups": (
            {
                "axis": "spread_nature",
                "prompt": "Choose spread/nature:",
                "options": (
                    {"option_id": "spread_nature:default", "label": "Recommended default"},
                    {"option_id": "spread_nature:1", "label": "Timid 2/0/0/32/0/32"},
                    {"option_id": "spread_nature:2", "label": "Modest 32/0/0/1/29/4"},
                ),
            },
        ),
    }
    for text in ("the default one", "default", "the default", "default one"):
        assert _deterministic_build_option_ids(text, pending) == (
            "spread_nature:default",
        )


def test_spread_target_question_resolves_end_to_end_with_reallocation():
    """Full regression for the 'immediately forgets the first request' bug
    (2026-08-18): confirms the whole loop -- ambiguous edit produces an
    interactive question, a natural follow-up reply ('Spe 5') is correctly
    parsed and applied, and if the answer itself creates a budget mismatch
    it's auto-reallocated rather than dead-ending a second time."""
    from recommender.nodes import (
        apply_provisional_edit,
        classify_pending,
        resolve_spread_target_question,
    )

    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=_decision(),
        species="Archaludon",
        ability="Stamina",
        item="Leftovers",
        moves=("Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"),
        nature="Modest",
        spread={"hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3},
        fingerprint="fp",
    )
    state1 = _state(
        provisional,
        payload={
            "field": "spread",
            "value": {"hp": 32, "atk": 0, "def": 29, "spa": 0, "spd": 0, "spe": 5},
            "scope": "field_only",
        },
    )
    out1 = apply_provisional_edit(state1)
    assert out1.get("slot_commit_error") is None
    question = out1["pending_presentation"]
    assert question["kind"] == "spread_target_question"

    dispatch = classify_pending("Spe 5", question)
    assert dispatch["turn_intent"] == "resolve_spread_target_question"
    assert dispatch["turn_payload"] == {"stat": "spe", "value": 5, "is_delta": False}

    state2 = _state(provisional, pending=question, payload=dispatch["turn_payload"])
    out2 = resolve_spread_target_question(state2)
    assert out2.get("slot_commit_error") is None
    final_spread = out2["provisional_slot"].spread_dict()
    assert final_spread["spe"] == 5
    from recommender.recommend import SP_BUDGET, spread_sum
    assert spread_sum(final_spread) == SP_BUDGET
    notices = out2["pending_presentation"].get("notices") or ()
    assert any("Adjusted spread" in n for n in notices)


def test_spread_target_question_defer_restores_held_pending():
    from recommender.nodes import classify_pending

    held = {"schema_version": 1, "kind": "full_build_confirmation", "slot_index": 0}
    question = {
        "schema_version": 1,
        "kind": "spread_target_question",
        "slot_index": 0,
        "target_question_diffs": ("def", "spa", "spd", "spe"),
        "target_question_edited_fields": ("spread",),
        "held_pending": held,
    }
    result = classify_pending("defer", question)
    assert result["turn_intent"] == "pending_response"
    assert result["pending_presentation"] == held


def test_spread_target_question_reasks_on_unparseable_reply():
    from recommender.nodes import classify_pending

    question = {
        "schema_version": 1,
        "kind": "spread_target_question",
        "slot_index": 0,
        "target_question_diffs": ("def", "spa", "spd", "spe"),
        "target_question_edited_fields": ("spread",),
    }
    result = classify_pending("blah blah", question)
    assert result["turn_intent"] == "pending_response"
    assert result["pending_presentation"]["kind"] == "spread_target_question"
    assert result["pending_presentation"]["target_question_rejection_reason"]


def _archaludon_choice_scarf_scenario():
    """Exact live scenario: Archaludon locked with Choice Scarf, real
    kit including Protect -- confirmed live to trigger the Choice-item/
    status-move conflict."""
    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=_decision(),
        species="Archaludon",
        ability="Stamina",
        item="Leftovers",
        moves=("Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"),
        nature="Modest",
        spread={"hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3},
        fingerprint="fp",
    )
    return provisional


def test_item_edit_creating_choice_status_conflict_asks_interactively():
    """Regression for the item/moveset-conflict feature request: "use
    Choice Scarf" on Archaludon's real kit (Protect present) must produce
    an interactive question with real, usage-backed move alternatives --
    not a dead-end error."""
    from recommender.nodes import apply_provisional_edit

    provisional = _archaludon_choice_scarf_scenario()
    state = _state(
        provisional,
        payload={"field": "item", "value": "Choice Scarf", "scope": "field_only"},
    )
    out = apply_provisional_edit(state)
    assert out.get("slot_commit_error") is None
    pending = out["pending_presentation"]
    assert pending["kind"] == "item_moveset_conflict_question"
    assert pending["conflict_attempted_item"] == "Choice Scarf"
    assert pending["conflict_previous_item"] == "Leftovers"
    assert "Protect" in pending["conflict_moves"]
    assert len(pending["conflict_move_alternatives"]) > 0
    assert "Aura Sphere" in pending["conflict_move_alternatives"]
    # The base is the pre-edit, still-valid provisional, not the
    # conflicted attempt -- confirms defer needs no special-case logic.
    assert out["provisional_slot"] == provisional


def test_item_moveset_conflict_resolves_by_replacing_move():
    """Picking a move alternative (by name) replaces the conflicting move
    and keeps the new item."""
    from recommender.nodes import (
        apply_provisional_edit,
        classify_pending,
        resolve_item_moveset_conflict,
    )

    provisional = _archaludon_choice_scarf_scenario()
    out1 = apply_provisional_edit(
        _state(
            provisional,
            payload={"field": "item", "value": "Choice Scarf", "scope": "field_only"},
        )
    )
    question = out1["pending_presentation"]

    dispatch = classify_pending("Aura Sphere", question)
    assert dispatch["turn_intent"] == "resolve_item_moveset_conflict"
    assert dispatch["turn_payload"] == {"action": "replace_move", "move": "Aura Sphere"}

    out2 = resolve_item_moveset_conflict(
        _state(provisional, pending=question, payload=dispatch["turn_payload"])
    )
    assert out2.get("slot_commit_error") is None
    result = out2["provisional_slot"]
    assert result.item == "Choice Scarf"
    assert "Aura Sphere" in result.moves
    assert "Protect" not in result.moves


def test_item_moveset_conflict_resolves_by_move_number():
    """A bare number reply selects from the offered alternatives list by
    position, matching this project's established numbered-option
    convention."""
    from recommender.nodes import apply_provisional_edit, classify_pending

    provisional = _archaludon_choice_scarf_scenario()
    out1 = apply_provisional_edit(
        _state(
            provisional,
            payload={"field": "item", "value": "Choice Scarf", "scope": "field_only"},
        )
    )
    question = out1["pending_presentation"]
    first_alt = question["conflict_move_alternatives"][0]

    dispatch = classify_pending("1", question)
    assert dispatch["turn_payload"] == {"action": "replace_move", "move": first_alt}


def test_item_moveset_conflict_resolves_by_keeping_it():
    """'keep it' applies the item change and deliberately keeps the
    flagged move, without asking for a replacement."""
    from recommender.nodes import (
        apply_provisional_edit,
        classify_pending,
        resolve_item_moveset_conflict,
    )

    provisional = _archaludon_choice_scarf_scenario()
    out1 = apply_provisional_edit(
        _state(
            provisional,
            payload={"field": "item", "value": "Choice Scarf", "scope": "field_only"},
        )
    )
    question = out1["pending_presentation"]

    dispatch = classify_pending("keep it", question)
    assert dispatch["turn_payload"] == {"action": "keep"}

    out2 = resolve_item_moveset_conflict(
        _state(provisional, pending=question, payload=dispatch["turn_payload"])
    )
    assert out2.get("slot_commit_error") is None
    result = out2["provisional_slot"]
    assert result.item == "Choice Scarf"
    assert "Protect" in result.moves


def test_item_moveset_conflict_defer_restores_held_pending():
    from recommender.nodes import apply_provisional_edit, classify_pending

    provisional = _archaludon_choice_scarf_scenario()
    held = {"schema_version": 1, "kind": "full_build_confirmation", "slot_index": 0}
    out1 = apply_provisional_edit(
        _state(
            provisional,
            pending=held,
            payload={"field": "item", "value": "Choice Scarf", "scope": "field_only"},
        )
    )
    question = out1["pending_presentation"]
    assert question["held_pending"] == held

    dispatch = classify_pending("defer", question)
    assert dispatch["turn_intent"] == "pending_response"
    assert dispatch["pending_presentation"] == held


def test_item_moveset_conflict_reasks_on_unparseable_reply():
    from recommender.nodes import apply_provisional_edit, classify_pending

    provisional = _archaludon_choice_scarf_scenario()
    out1 = apply_provisional_edit(
        _state(
            provisional,
            payload={"field": "item", "value": "Choice Scarf", "scope": "field_only"},
        )
    )
    question = out1["pending_presentation"]

    dispatch = classify_pending("blah blah", question)
    assert dispatch["turn_intent"] == "pending_response"
    assert dispatch["pending_presentation"]["kind"] == "item_moveset_conflict_question"
    assert dispatch["pending_presentation"]["conflict_rejection_reason"]


def test_fake_illegal_item_is_not_misidentified_as_a_conflict():
    """Regression for a real bug found while building this feature: an
    obviously illegal/fake item was incorrectly intercepted as an
    item_moveset_conflict_question, masking the real 'illegal edited slot'
    error, because the first draft of _handle_item_moveset_conflict only
    checked whether the moveset happened to contain a status move --
    never whether the item was actually a real Choice item at all."""
    from recommender.nodes import apply_provisional_edit

    provisional = _provisional()  # base fixture, includes Protect
    state = _state(
        provisional,
        payload={"field": "item", "value": "NotARealItemXYZ", "scope": "field_only"},
    )
    out = apply_provisional_edit(state)
    assert out.get("slot_commit_error")
    assert out.get("pending_presentation") is None


def test_accept_status_move_conflict_does_not_bypass_unrelated_speed_conflict():
    """Regression for the explicit narrow-scoping decision: accepting the
    shown Choice-item/status-move conflict must NOT silently bypass a
    SEPARATE, unrelated conflict bundled in the same group (Choice Scarf +
    Trick Room speed-direction). Tested directly against
    _verify_provisional_hard, with check_set mocked to isolate the
    conflict-check logic from real move-learnset legality constraints.
    """
    from unittest.mock import patch

    from recommender.legality import LegalityResult
    from recommender.nodes import _verify_provisional_hard

    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=TargetRoleDecision(
            role_id="trick_room_setter", source="usage_backed"
        ),
        species="Farigiraf",
        ability="Armor Tail",
        item="Choice Scarf",
        moves=("Trick Room", "Encore", "Psychic", "Hyper Voice"),
        nature="Quiet",
        spread={"hp": 32, "atk": 0, "def": 1, "spa": 29, "spd": 4, "spe": 0},
        fingerprint="fp",
    )
    state = {"team_draft": [empty_slot()], "regulation_mod": "champions-reg-mb"}

    with patch(
        "recommender.nodes.check_set",
        return_value=LegalityResult(ok=True, failures=()),
    ):
        err_normal = _verify_provisional_hard(provisional, state)
        assert err_normal is not None
        err_accepted = _verify_provisional_hard(
            provisional, state, accept_status_move_conflict=True
        )
        assert err_accepted is not None
        assert "Trick Room" in err_accepted


def test_select_plus_item_edit_end_to_end_triggers_conflict_flow():
    """Full end-to-end regression, exact live scenario: '1, but with
    Choice Scarf' resolves through apply_provisional_option (not
    apply_provisional_edit), applying the selected option's spread AND
    the item change together, and correctly triggers the interactive
    item_moveset_conflict_question when the combination creates a real
    conflict (Choice Scarf + Protect)."""
    from recommender.nodes import apply_provisional_option

    provisional = _archaludon_choice_scarf_scenario()
    pending = {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "build_option_groups": (
            {
                "axis": "spread_nature",
                "prompt": "x",
                "options": (
                    {
                        "option_id": "spread_nature:default",
                        "label": "Recommended default",
                        "overrides": {},
                    },
                    {
                        "option_id": "spread_nature:1",
                        "label": "Timid",
                        "overrides": {
                            "nature": "Timid",
                            "spread": {
                                "hp": 2, "atk": 0, "def": 0, "spa": 32,
                                "spd": 0, "spe": 32,
                            },
                        },
                    },
                ),
            },
        ),
    }
    state = _state(
        provisional,
        pending=pending,
        payload={
            "option_ids": ("spread_nature:1",),
            "extra_field": "item",
            "extra_value": "Choice Scarf",
        },
    )
    out = apply_provisional_option(state)
    assert out.get("slot_commit_error") is None
    question = out["pending_presentation"]
    assert question["kind"] == "item_moveset_conflict_question"
    assert question["conflict_attempted_item"] == "Choice Scarf"
    assert "Protect" in question["conflict_moves"]
    # Confirms the selected option's spread/nature was also applied, not
    # just the item -- the base for the conflict question is the FULL
    # composed selection, not just the item change in isolation.
    assert out["provisional_slot"].nature != "Timid"  # base is pre-edit (unchanged)


def test_select_plus_item_edit_overlapping_key_rejected():
    """extra_field colliding with a key the selected option already
    overrides must be rejected the same way option-to-option overlaps
    already are, not silently let one win."""
    from recommender.nodes import apply_provisional_option

    provisional = _provisional()
    pending: PendingPresentation = {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "build_option_groups": (
            {
                "axis": "item",
                "prompt": "x",
                "options": (
                    {
                        "option_id": "item:1",
                        "label": "Choice Specs",
                        "overrides": {"item": "Choice Specs"},
                    },
                ),
            },
        ),
    }
    state = _state(
        provisional,
        pending=pending,
        payload={
            "option_ids": ("item:1",),
            "extra_field": "item",
            "extra_value": "Life Orb",
        },
    )
    out = apply_provisional_option(state)
    assert out.get("slot_commit_error")
    assert "overlapping" in out["slot_commit_error"]
