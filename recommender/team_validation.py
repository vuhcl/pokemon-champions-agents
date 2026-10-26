"""Team-level validation for every writer that puts a species or item into team_draft.

``check_set`` judges one slot's contents. This module adds what needs the whole
team: legality of a bare species/item value, the Species Clause and the Item
Clause, all against the *other* slots only. Species identity is the snapshot's
``base_species_id`` (any two forms of one dex entry clash; evolution relatives
are different species). Not enforced here: the Mega Stone rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from recommender.ids import to_id
from recommender.slot_index import display_slot
from recommender.legality import is_item_legal, is_species_legal, load_snapshot, team_item_ids
from recommender.species_resolve import lookup_species_id
from recommender.state import Slot

TeamAttr = Literal["species", "item"]
TEAM_ATTRS: tuple[str, ...] = ("species", "item")
RefusalKind = Literal[
    "unknown_species",
    "illegal_species",
    "unknown_item",
    "illegal_item",
    "species_clause",
    "item_clause",
    "bad_slot_index",
    "bad_value",
]


@dataclass(frozen=True)
class TeamRefusal:
    kind: RefusalKind
    attr: str
    value: str
    conflicts_with_slot: int | None
    message: str


@dataclass(frozen=True)
class TeamValueVerdict:
    refusal: TeamRefusal | None
    canonical: str | None = None


def dex_id(species: str, snap: dict[str, Any]) -> str:
    """Same-dex identity: snapshot base species id, else the species' own id."""
    sid = lookup_species_id(species, snap) or to_id(species)
    entry = (snap.get("species") or {}).get(sid) or {}
    return entry.get("base_species_id") or sid


def _refuse(kind: RefusalKind, attr: str, value: object, message: str, other: int | None = None) -> TeamValueVerdict:
    return TeamValueVerdict(TeamRefusal(kind, attr, str(value), other, message))


def validate_team_value(
    attr: str,
    value: object,
    *,
    slot_index: object,
    team_draft: list[Slot],
    snap: dict[str, Any] | None = None,
) -> TeamValueVerdict:
    """Accept (with the canonical display name) or refuse one species/item value."""
    snap = snap or load_snapshot()
    where = "this format"  # not the internal regulation id; it is not user-facing
    if attr not in TEAM_ATTRS:
        raise ValueError(f"validate_team_value only handles species/item, got {attr!r}")
    if (
        isinstance(slot_index, bool)
        or not isinstance(slot_index, int)
        or not 0 <= slot_index < len(team_draft)
    ):
        return _refuse("bad_slot_index", attr, value, "I couldn't tell which slot to lock.")
    if not isinstance(value, str) or not value.strip():
        return _refuse("bad_value", attr, value, f"I couldn't tell which {attr} to lock.")

    if attr == "species":
        sid = lookup_species_id(value, snap)
        if sid is None:
            return _refuse(
                "unknown_species", attr, value,
                f"I don't recognize '{value}' as a Pokémon, so I can't lock it.",
            )
        name = str(snap["species"][sid].get("name") or value)
        if not is_species_legal(snap, sid):
            return _refuse(
                "illegal_species", attr, value,
                f"{name} is not legal in {where}, so I can't lock it.",
            )
        # Assumes every species value in team_draft is locked: the only writers are
        # lock single/batch, restore and commit, all locked=True (test_team_validation).
        mine = dex_id(sid, snap)
        for i, slot in enumerate(team_draft):
            other = slot.species.value
            if i == slot_index or not other:
                continue
            if dex_id(str(other), snap) == mine:
                return _refuse(
                    "species_clause", attr, value,
                    f"Species Clause: {name} clashes with {other} in slot {display_slot(i)}. "
                    "One of each Pokémon, forms included.",
                    i,
                )
        return TeamValueVerdict(None, name)

    iid = to_id(value)
    entry = (snap.get("items") or {}).get(iid)
    if entry is None:
        return _refuse(
            "unknown_item", attr, value,
            f"I don't recognize '{value}' as an item, so I can't lock it.",
        )
    name = str(entry.get("name") or value)
    if not is_item_legal(snap, iid):
        return _refuse(
            "illegal_item", attr, value,
            f"{name} is not legal in {where}, so I can't lock it.",
        )
    if iid in team_item_ids(team_draft, exclude_slot=slot_index):
        holder = next(
            i for i, s in enumerate(team_draft)
            if i != slot_index and s.item.value and to_id(s.item.value) == iid
        )
        return _refuse(
            "item_clause", attr, value,
            f"Item Clause: {name} is already held in slot {display_slot(holder)}. "
            "Each item can be used only once.",
            holder,
        )
    return TeamValueVerdict(None, name)
