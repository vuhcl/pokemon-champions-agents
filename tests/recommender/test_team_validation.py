"""Species/item validation on every lock path (recommender/team_validation.py).

Everything is derived from the pinned snapshot, not hand-picked, except the
named controls (Pikachu/Raichu, Floette). Zero-mutation assertions cover
``team_draft`` and the superseded stack only; pending/presentation state is not
asserted here (a refused lock still routes through route_team_phase).
"""

from __future__ import annotations

import copy
from collections import defaultdict

import pytest

from recommender.ids import to_id
from recommender.legality import is_item_legal, is_species_legal, load_snapshot
from recommender.nodes import (
    LOCK_BAD_SLOT_MSG,
    LOCK_FULLY_LOCKED_SLOT_MSG,
    _clear_rejected_for_newly_locked_species,
    apply_lock,
    commit_full_slot,
    restore_superseded,
)
from recommender.state import (
    Attr,
    PendingSlotIntent,
    ProvisionalSlot,
    Slot,
    TargetRoleDecision,
    empty_slot,
    slot_fingerprint,
)
from recommender.legality import legal_moves_for
from recommender.team_validation import dex_id, validate_team_value
from recommender.usage_data import _display_item, lineage_ids

SNAP = load_snapshot()
SPECIES = SNAP["species"]
LEGAL = sorted(s for s in SPECIES if is_species_legal(SNAP, s))
ILLEGAL_SPECIES = sorted(s for s in SPECIES if not is_species_legal(SNAP, s))
LEGAL_ITEMS = sorted(i for i in SNAP["items"] if is_item_legal(SNAP, i))
ILLEGAL_ITEMS = sorted(i for i in SNAP["items"] if not is_item_legal(SNAP, i))

_groups: dict[str, list[str]] = defaultdict(list)
for _s in LEGAL:
    _groups[SPECIES[_s].get("base_species_id") or _s].append(_s)
PAIRS = [
    (a, b)
    for members in _groups.values()
    if len(members) > 1
    for i, a in enumerate(members)
    for b in members[i + 1 :]
]


def _name(sid: str) -> str:
    return SPECIES[sid]["name"]


def _state(draft: list[Slot], **extra) -> dict:
    return {"team_draft": draft, "turn": 3, "regulation_mod": "champions", **extra}


def _draft_with(index: int, **attrs) -> list[Slot]:
    draft = [empty_slot() for _ in range(6)]
    draft[index] = Slot(**{k: Attr(v, locked=True) for k, v in attrs.items()})
    return draft


def _lock(state: dict, slot_index: int, attr: str, value: object) -> dict:
    return apply_lock({**state, "turn_payload": {"slot_index": slot_index, "attr": attr, "value": value}})


def _lock_batch(state: dict, slot_index: int, locks: list[dict]) -> dict:
    return apply_lock({**state, "turn_payload": {"slot_index": slot_index, "locks": locks}})


def _assert_refused(out: dict, state: dict, before: list[Slot], needle: str) -> None:
    assert "team_draft" not in out
    assert needle in out["slot_commit_error"]
    assert state["team_draft"] == before


# ---- sanity on the derived data ------------------------------------------------

def test_snapshot_has_clashing_groups():
    assert len(PAIRS) > 100
    assert ILLEGAL_SPECIES and ILLEGAL_ITEMS


# ---- Species Clause: every pair, every writer ------------------------------------

@pytest.mark.parametrize("a,b", PAIRS)
def test_validator_rejects_every_same_dex_pair(a, b):
    draft = _draft_with(0, species=_name(a))
    verdict = validate_team_value("species", _name(b), slot_index=1, team_draft=draft)
    assert verdict.refusal is not None and verdict.refusal.kind == "species_clause"
    assert verdict.refusal.conflicts_with_slot == 0


@pytest.mark.parametrize("a,b", PAIRS)
def test_lock_single_and_batch_reject_every_same_dex_pair(a, b):
    state = _state(_draft_with(0, species=_name(a)))
    before = copy.deepcopy(state["team_draft"])
    _assert_refused(_lock(state, 1, "species", _name(b)), state, before, "Species Clause")
    _assert_refused(
        _lock_batch(state, 1, [{"attr": "species", "value": _name(b)}]),
        state, before, "Species Clause",
    )


@pytest.mark.parametrize("a,b", PAIRS)
def test_restore_rejects_every_same_dex_pair_and_keeps_superseded(a, b):
    entry = {"slot_index": 1, "attr": "species", "value": _name(b), "reason": "x", "turn_removed": 1}
    state = _state(_draft_with(0, species=_name(a)), superseded=[entry])
    before = copy.deepcopy(state["team_draft"])
    stack = copy.deepcopy(state["superseded"])
    out = restore_superseded({**state, "turn_payload": {"slot_index": 1, "attr": "species"}})
    _assert_refused(out, state, before, "Species Clause")
    assert state["superseded"] == stack and "superseded" not in out


def _commit_state(draft: list[Slot], index: int, species: str, item: str) -> dict:
    moves = tuple(m for m in legal_moves_for(species)[:4])
    decision = TargetRoleDecision(role_id="trick_room_setter", source="support_need", evidence=("x",))
    base = slot_fingerprint(draft[index])
    ability = next(iter(SPECIES[to_id(species)]["abilities"].values()))
    provisional = ProvisionalSlot(
        schema_version=1, slot_index=index, target_role_decision=decision, species=species,
        ability=ability, item=item, moves=moves, nature="Modest",
        spread=(("hp", 32), ("atk", 0), ("def", 0), ("spa", 32), ("spd", 2), ("spe", 0)),
        base_slot_fingerprint=base, fingerprint="t",
    )
    intent = PendingSlotIntent(
        schema_version=1, slot_index=index, species=species, target_role_decision=decision,
        source="need", base_slot_fingerprint=base,
    )
    return _state(
        draft, constraints=[], pending_slot_intent=intent, provisional_slot=provisional,
        pending_presentation={
            "schema_version": 1, "kind": "full_build_confirmation",
            "slot_index": index, "provisional_fingerprint": "t",
        },
    )


def _committable(sid: str) -> bool:
    return len(legal_moves_for(sid)) >= 4 and bool(SPECIES[sid].get("abilities"))


def test_every_clashing_pair_has_a_committable_member():
    """Commit needs a legal four-move build for the species being committed."""
    missing = [(a, b) for a, b in PAIRS if not (_committable(a) or _committable(b))]
    assert missing == []


@pytest.mark.parametrize("a,b", PAIRS)
def test_commit_rejects_every_same_dex_pair(a, b):
    other, new = (a, b) if _committable(b) else (b, a)
    state = _commit_state(_draft_with(0, species=_name(other)), 1, _name(new), "Sitrus Berry")
    before = copy.deepcopy(state["team_draft"])
    out = commit_full_slot(state)
    _assert_refused(out, state, before, "Species Clause")


# ---- controls: legal pairs and first locks ---------------------------------------

def test_pikachu_with_raichu_accepted_on_every_writer():
    assert dex_id("Pikachu", SNAP) != dex_id("Raichu", SNAP)
    state = _state(_draft_with(0, species="Pikachu"))
    assert _lock(state, 1, "species", "Raichu")["team_draft"][1].species.value == "Raichu"
    out = _lock_batch(state, 1, [{"attr": "species", "value": "Raichu"}])
    assert out["team_draft"][1].species.value == "Raichu"
    entry = {"slot_index": 1, "attr": "species", "value": "Raichu", "reason": "x", "turn_removed": 1}
    out = restore_superseded(
        {**state, "superseded": [entry], "turn_payload": {"slot_index": 1, "attr": "species"}}
    )
    assert out["team_draft"][1].species.value == "Raichu" and out["superseded"] == []
    cstate = _commit_state(_draft_with(0, species="Pikachu"), 1, "Raichu", "Sitrus Berry")
    assert "team_draft" in commit_full_slot(cstate)


def test_floette_forms_with_illegal_base_still_clash():
    a, b = "floetteeternal", "floettemega"
    assert not is_species_legal(SNAP, "floette")
    state = _state(_draft_with(0, species=_name(a)))
    _assert_refused(_lock(state, 1, "species", _name(b)), state, state["team_draft"], "Species Clause")


def test_first_lock_and_same_slot_species_then_item():
    state = _state([empty_slot() for _ in range(6)])
    out = _lock(state, 2, "species", "Incineroar")
    assert out["team_draft"][2].species.value == "Incineroar"
    out2 = _lock({**state, **out}, 2, "item", "Sitrus Berry")
    assert out2["team_draft"][2].item.value == "Sitrus Berry"
    assert out2["team_draft"][2].species.value == "Incineroar"


def test_relocking_same_slot_species_is_not_a_clause_clash():
    state = _state(_draft_with(0, species="Incineroar"))
    # compares against other slots only: the slot being written is excluded
    verdict = validate_team_value("species", "Incineroar", slot_index=0, team_draft=state["team_draft"])
    assert verdict.refusal is None


def test_fully_locked_guard_still_applies():
    full = Slot(
        role=Attr("r", locked=True), species=Attr("Incineroar", locked=True),
        ability=Attr("Intimidate", locked=True), item=Attr("Sitrus Berry", locked=True),
        moveset=Attr(["Fake Out"] * 4, locked=True), spread=Attr({"hp": 32}, locked=True),
        nature=Attr("Adamant", locked=True),
    )
    state = _state([full, *[empty_slot() for _ in range(5)]])
    out = _lock(state, 0, "species", "Garchomp")
    assert out == {"slot_commit_error": LOCK_FULLY_LOCKED_SLOT_MSG}


@pytest.mark.parametrize("bad", [-1, 6, None, "2", True])
def test_bad_slot_index_refused_not_raised(bad):
    state = _state([empty_slot() for _ in range(6)])
    out = apply_lock({**state, "turn_payload": {"slot_index": bad, "attr": "species", "value": "Garchomp"}})
    assert out == {"slot_commit_error": LOCK_BAD_SLOT_MSG}


# ---- legality: unknown vs illegal, snapshot-derived -------------------------------

@pytest.mark.parametrize("sid", ILLEGAL_SPECIES)
def test_every_snapshot_illegal_species_rejected_on_lock_single(sid):
    state = _state([empty_slot() for _ in range(6)])
    out = _lock(state, 0, "species", _name(sid))
    assert "team_draft" not in out and "not legal" in out["slot_commit_error"]


def test_illegal_species_rejected_on_batch_and_named_cases():
    state = _state([empty_slot() for _ in range(6)])
    for sid in ILLEGAL_SPECIES[::40]:
        out = _lock_batch(state, 0, [{"attr": "species", "value": _name(sid)}])
        assert "team_draft" not in out and "not legal" in out["slot_commit_error"]
    for sid in ("fluttermane", "koraidon"):
        assert sid in SPECIES and not is_species_legal(SNAP, sid)
        v = validate_team_value("species", _name(sid), slot_index=0, team_draft=state["team_draft"])
        assert v.refusal.kind == "illegal_species"


def test_unknown_species_and_item_distinguished():
    draft = [empty_slot() for _ in range(6)]
    v = validate_team_value("species", "Notamon", slot_index=0, team_draft=draft)
    assert v.refusal.kind == "unknown_species"
    v = validate_team_value("item", "Notanitem", slot_index=0, team_draft=draft)
    assert v.refusal.kind == "unknown_item"
    for bad in (None, 3, "", "  ", ["Garchomp"], {"species": "Garchomp"}):
        assert validate_team_value("species", bad, slot_index=0, team_draft=draft).refusal.kind == "bad_value"


@pytest.mark.parametrize("iid", ILLEGAL_ITEMS)
def test_every_snapshot_illegal_item_rejected_on_lock_single(iid):
    state = _state([empty_slot() for _ in range(6)])
    out = _lock(state, 0, "item", SNAP["items"][iid]["name"])
    assert "team_draft" not in out and "not legal" in out["slot_commit_error"]
    assert not is_item_legal(SNAP, iid)


def test_illegal_item_rejected_on_batch():
    state = _state([empty_slot() for _ in range(6)])
    for iid in ILLEGAL_ITEMS[::40]:
        out = _lock_batch(state, 0, [{"attr": "item", "value": SNAP["items"][iid]["name"]}])
        assert "team_draft" not in out and "not legal" in out["slot_commit_error"]


# ---- Item Clause -----------------------------------------------------------------

def test_item_clause_on_lock_single_batch_and_commit():
    state = _state(_draft_with(0, item="Choice Scarf"))
    before = copy.deepcopy(state["team_draft"])
    _assert_refused(_lock(state, 1, "item", "choice scarf"), state, before, "Item Clause")
    _assert_refused(
        _lock_batch(state, 1, [{"attr": "item", "value": "Choice Scarf"}]),
        state, before, "Item Clause",
    )
    cstate = _commit_state(_draft_with(0, item="Choice Scarf"), 1, "Incineroar", "Choice Scarf")
    out = commit_full_slot(cstate)
    assert "team_draft" not in out and "item_clause" in out["slot_commit_error"]


# ---- batch atomicity ---------------------------------------------------------------

def test_batch_duplicate_attr_refused_whole():
    state = _state([empty_slot() for _ in range(6)])
    before = copy.deepcopy(state["team_draft"])
    out = _lock_batch(state, 0, [
        {"attr": "species", "value": "Incineroar"},
        {"attr": "species", "value": "Garchomp"},
    ])
    _assert_refused(out, state, before, "species more than once")


def test_batch_illegal_entry_blocks_legal_entry():
    state = _state([empty_slot() for _ in range(6)])
    before = copy.deepcopy(state["team_draft"])
    out = _lock_batch(state, 0, [
        {"attr": "item", "value": "Sitrus Berry"},
        {"attr": "species", "value": "Flutter Mane"},
    ])
    _assert_refused(out, state, before, "not legal")
    assert "pending_flags" not in out


def test_batch_clean_payload_stores_canonical_values():
    state = _state([empty_slot() for _ in range(6)])
    out = _lock_batch(state, 0, [
        {"attr": "species", "value": "garchomp"},
        {"attr": "item", "value": "choice scarf"},
    ])
    slot = out["team_draft"][0]
    assert (slot.species.value, slot.item.value) == ("Garchomp", "Choice Scarf")


# ---- restore: clash appears after a later lock -----------------------------------

def test_restore_refused_when_later_lock_clashes_and_stack_unchanged():
    state = _state([empty_slot() for _ in range(6)])
    # slot 1 held Charizard, was superseded; user then locked Charizard-Mega-X + stone in slot 0
    locked = _lock_batch(
        state,
        0,
        [
            {"attr": "species", "value": "Charizard-Mega-X"},
            {"attr": "item", "value": "Charizardite X"},
        ],
    )
    entry = {"slot_index": 1, "attr": "species", "value": "Charizard", "reason": "x", "turn_removed": 1}
    s2 = {**state, **locked, "superseded": [entry]}
    before = copy.deepcopy(s2["team_draft"])
    out = restore_superseded({**s2, "turn_payload": {"slot_index": 1, "attr": "species"}})
    _assert_refused(out, s2, before, "Species Clause")
    assert s2["superseded"] == [entry] and "superseded" not in out


# ---- canonical form -----------------------------------------------------------------

def test_canonical_storage_for_species_and_item():
    state = _state([empty_slot() for _ in range(6)])
    out = _lock_batch(
        state,
        0,
        [
            {"attr": "species", "value": "charizardmegax"},
            {"attr": "item", "value": "charizarditex"},
        ],
    )
    assert out["team_draft"][0].species.value == "Charizard-Mega-X"
    assert out["team_draft"][0].item.value == "Charizardite X"
    state2 = _state([empty_slot() for _ in range(6)])
    assert _lock(state2, 0, "item", "sitrusberry")["team_draft"][0].item.value == "Sitrus Berry"


@pytest.mark.parametrize("iid", LEGAL_ITEMS)
def test_canonical_item_matches_display_form_used_by_builds(iid):
    """What the lock path stores equals the display form discovery/commit stores."""
    v = validate_team_value("item", iid, slot_index=0, team_draft=[empty_slot()])
    assert v.canonical == _display_item(iid) == SNAP["items"][iid]["name"]


def test_rejection_and_lineage_comparisons_work_on_canonical_values():
    state = _state(
        [empty_slot() for _ in range(6)],
        rejected=[{"species": "charizardmegax", "reason": "", "turn": 1}],
    )
    out = _lock_batch(
        state,
        0,
        [
            {"attr": "species", "value": "charizardmegax"},
            {"attr": "item", "value": "charizarditex"},
        ],
    )
    assert out["team_draft"][0].species.value == "Charizard-Mega-X"
    cleared = _clear_rejected_for_newly_locked_species(state, out)
    assert cleared["rejected"] == []
    assert {"charizard", "charizardmegax", "charizardmegay"} <= set(lineage_ids("Charizard-Mega-X"))


# ---- Mega Stone rule -----------------------------------------------------------------

def test_refuse_mega_species_without_stone():
    state = _state([empty_slot() for _ in range(6)])
    before = copy.deepcopy(state["team_draft"])
    out = _lock(state, 0, "species", "Salamence-Mega")
    _assert_refused(out, state, before, "Salamencite")
    assert "base form" in out["slot_commit_error"].lower() or "Salamence" in out["slot_commit_error"]


def test_refuse_non_stone_item_on_mega():
    state = _state(
        _draft_with(0, species="Salamence-Mega", item="Salamencite")
    )
    before = copy.deepcopy(state["team_draft"])
    out = _lock(state, 0, "item", "Leftovers")
    _assert_refused(out, state, before, "Salamencite")
    assert state["team_draft"][0].item.value == "Salamencite"


def test_batch_mega_with_correct_stone_ok():
    state = _state([empty_slot() for _ in range(6)])
    out = _lock_batch(
        state,
        0,
        [
            {"attr": "species", "value": "Salamence-Mega"},
            {"attr": "item", "value": "Salamencite"},
        ],
    )
    assert out.get("slot_commit_error") is None
    assert out["team_draft"][0].species.value == "Salamence-Mega"
    assert out["team_draft"][0].item.value == "Salamencite"


def test_batch_mega_with_wrong_item_refused():
    state = _state([empty_slot() for _ in range(6)])
    before = copy.deepcopy(state["team_draft"])
    out = _lock_batch(
        state,
        0,
        [
            {"attr": "species", "value": "Salamence-Mega"},
            {"attr": "item", "value": "Leftovers"},
        ],
    )
    _assert_refused(out, state, before, "Salamencite")


# ---- drift: validator grouping == lineage_ids ---------------------------------------

def test_dex_grouping_equals_lineage_ids_for_every_legal_species():
    for sid in LEGAL:
        mine = {x for x in SPECIES if dex_id(x, SNAP) == dex_id(sid, SNAP)}
        assert mine == set(lineage_ids(sid)), sid


# ---- refusal text never leaks the internal regulation id -----------------------------

@pytest.mark.parametrize("reg", ["championsregma", "championsregmb", "champions"])
def test_refusal_text_says_this_format_not_the_regulation_id(reg):
    state = {**_state([empty_slot() for _ in range(6)]), "regulation_mod": reg}
    iid = ILLEGAL_ITEMS[0]
    cases = [
        _lock(state, 0, "species", "Flutter Mane"),
        _lock(state, 0, "item", SNAP["items"][iid]["name"]),
        _lock_batch(state, 0, [{"attr": "species", "value": "Koraidon"}]),
    ]
    for out in cases:
        msg = out["slot_commit_error"]
        assert "this format" in msg and reg not in msg


# ---- every species value reachable in team_draft is locked ---------------------------

def _species_locked(draft: list[Slot]) -> bool:
    return all(s.species.locked for s in draft if s.species.value)


def test_normal_paths_never_leave_an_unlocked_species_in_team_draft():
    """team_validation's Species Clause compares against every slot's species value
    and relies on this: species enters team_draft only locked."""
    from recommender.nodes import record_rejection
    from recommender.propose import fill_team_draft

    state = _state([empty_slot() for _ in range(6)], archetype=Attr(), rejected=[], picked_team_size=4)
    after_lock = {**state, **_lock(state, 0, "species", "Incineroar")}
    after_batch = {**after_lock, **_lock_batch(after_lock, 1, [
        {"attr": "species", "value": "Garchomp"}, {"attr": "item", "value": "Sitrus Berry"},
    ])}
    entry = {"slot_index": 2, "attr": "species", "value": "Rillaboom", "reason": "x", "turn_removed": 1}
    after_restore = {**after_batch, **restore_superseded(
        {**after_batch, "superseded": [entry], "turn_payload": {"slot_index": 2, "attr": "species"}}
    )}
    filled = {**after_restore, **fill_team_draft(after_restore)}
    rejected = {**filled, **record_rejection(
        {**filled, "turn_payload": {"species": "Kingambit", "slot_index": 3, "reason": "x"}}
    )}
    cstate = _commit_state(_draft_with(0, species="Incineroar"), 1, "Rillaboom", "Sitrus Berry")
    committed = {**cstate, **commit_full_slot(cstate)}
    for st in (after_lock, after_batch, after_restore, filled, rejected, committed):
        assert any(s.species.value for s in st["team_draft"])
        assert _species_locked(st["team_draft"])
