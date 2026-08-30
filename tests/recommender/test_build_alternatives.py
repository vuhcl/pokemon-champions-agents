"""Build alternatives generator + provisional_for_confirmation."""

from __future__ import annotations

from recommender.build_alternatives import (
    ally_support_investment_notes,
    draft_has_complete_build,
    generate_build_option_groups,
    provisional_for_confirmation,
)
from recommender.state import (
    Attr,
    PendingSlotIntent,
    ProvisionalSlot,
    TargetRoleDecision,
    empty_slot,
)


def _decision(role_id: str = "rain_setter") -> TargetRoleDecision:
    return TargetRoleDecision(role_id=role_id, source="other")


def _provisional(**kwargs) -> ProvisionalSlot:
    decision = _decision()
    base = dict(
        schema_version=1,
        slot_index=0,
        target_role_decision=decision,
        species="Pelipper",
        ability="Drizzle",
        item="Focus Sash",
        moves=("Hurricane", "Weather Ball", "Tailwind", "Wide Guard"),
        nature="Timid",
        spread=(
            ("hp", 2),
            ("atk", 0),
            ("def", 0),
            ("spa", 32),
            ("spd", 0),
            ("spe", 32),
        ),
        base_slot_fingerprint="base",
        fingerprint="fp-usage",
    )
    base.update(kwargs)
    return ProvisionalSlot(**base)  # type: ignore[arg-type]


def _state(draft=None):
    return {
        "team_draft": draft if draft is not None else [empty_slot()],
        "regulation_mod": "champions-reg-mb",
        "game_type": "doubles",
    }


def test_draft_has_complete_build():
    slot = empty_slot()
    assert not draft_has_complete_build(slot)
    slot.species = Attr("Pelipper", True)
    slot.ability = Attr("Drizzle", True)
    slot.item = Attr("Focus Sash", True)
    slot.moveset = Attr(
        ["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"], True
    )
    slot.nature = Attr("Timid", True)
    slot.spread = Attr(
        {"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32}, True
    )
    assert draft_has_complete_build(slot)


def test_provisional_for_confirmation_skips_sync_when_base_matches_draft():
    slot = empty_slot()
    slot.role = Attr("fast_special_attacker", True)
    slot.species = Attr("Gholdengo", True)
    slot.ability = Attr("Good as Gold", True)
    slot.item = Attr("Life Orb", True)
    slot.moveset = Attr(
        ["Make It Rain", "Shadow Ball", "Protect", "Nasty Plot"], True
    )
    slot.nature = Attr("Timid", True)
    slot.spread = Attr(
        {"hp": 4, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 30}, True
    )
    from recommender.state import slot_fingerprint

    fp = slot_fingerprint(slot)
    edited = _provisional(nature="Modest", fingerprint="fp-edited")
    edited = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=_decision("fast_special_attacker"),
        species="Gholdengo",
        ability="Good as Gold",
        item="Life Orb",
        moves=("Make It Rain", "Shadow Ball", "Protect", "Nasty Plot"),
        nature="Modest",
        spread=edited.spread,
        base_slot_fingerprint=fp,
        fingerprint="fp-edited",
    )
    aligned = provisional_for_confirmation(edited, _state([slot]))
    assert aligned.nature == "Modest"


def test_provisional_for_confirmation_replaces_draft_on_refine():
    slot = empty_slot()
    slot.species = Attr("Pelipper", True)
    slot.ability = Attr("Drizzle", True)
    slot.item = Attr("Sitrus Berry", True)
    slot.moveset = Attr(
        ["Hurricane", "Weather Ball", "Tailwind", "Protect"], True
    )
    slot.nature = Attr("Bold", True)
    slot.spread = Attr(
        {"hp": 32, "atk": 0, "def": 32, "spa": 0, "spd": 2, "spe": 0}, True
    )
    slot.role = Attr("rain_setter", True)
    usage = _provisional(item="Focus Sash", nature="Timid", fingerprint="fp-usage")
    aligned = provisional_for_confirmation(usage, _state([slot]))
    assert aligned.item == "Sitrus Berry"
    assert aligned.nature == "Bold"
    assert aligned.fingerprint != "fp-usage"


def test_provisional_for_confirmation_greenfield_identity():
    usage = _provisional()
    aligned = provisional_for_confirmation(usage, _state([empty_slot()]))
    assert aligned is usage or aligned.fingerprint == usage.fingerprint


def test_ally_light_screen_note():
    ally = empty_slot()
    ally.species = Attr("Grimmsnarl", True)
    ally.moveset = Attr(
        ["Light Screen", "Reflect", "Parting Shot", "Spirit Break"], True
    )
    notes = ally_support_investment_notes(
        _provisional(slot_index=1),
        _state([ally, empty_slot()]),
    )
    assert any("SpD" in n or "screens" in n.lower() for n in notes)


def test_generate_build_option_groups_never_raises():
    groups, defaults = generate_build_option_groups(_provisional(), _state())
    assert isinstance(groups, tuple)
    assert isinstance(defaults, tuple)
