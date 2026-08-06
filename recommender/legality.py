"""Legality checks against offline Champions snapshot (ADR-002)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from recommender.ids import to_id
from recommender.state import PokemonSet, Slot

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = REPO_ROOT / "data" / "legality" / "champions.v1.json"

FailureKind = Literal[
    "species",
    "item",
    "move",
    "ability",
    "item_clause",
    "learnset",
]

ItemSeverity = Literal[
    "universal_swap",
    "type_locked_swap",
    "non_severe_no_substitute",
    "severe_no_substitute",
]


@dataclass
class LegalityFailure:
    kind: FailureKind
    element: str
    detail: str
    item_severity: ItemSeverity | None = None


@dataclass
class LegalityResult:
    ok: bool
    failures: list[LegalityFailure] = field(default_factory=list)


@lru_cache(maxsize=1)
def load_snapshot(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else DEFAULT_SNAPSHOT
    return json.loads(p.read_text())


def _species_entry(snap: dict[str, Any], species: str) -> dict[str, Any] | None:
    return snap["species"].get(to_id(species))


def resolve_learnset(snap: dict[str, Any], species: str) -> list[str] | None:
    """Species learnset, walking base_species_id for megas."""
    learnsets: dict[str, list[str]] = snap.get("learnsets") or {}
    sid = to_id(species)
    seen: set[str] = set()
    while sid and sid not in seen:
        seen.add(sid)
        if sid in learnsets:
            return learnsets[sid]
        entry = snap["species"].get(sid)
        if not entry:
            break
        sid = entry.get("base_species_id") or ""
    return None


def is_species_legal(snap: dict[str, Any], species: str) -> bool:
    e = _species_entry(snap, species)
    if not e:
        return False
    if e.get("is_nonstandard") is not None:
        return False
    if e.get("tier") == "Illegal":
        return False
    ban = set(snap["flat_rules"]["banlist"])
    if ban & set(e.get("effective_tags") or []):
        return False
    return True


def is_item_legal(snap: dict[str, Any], item: str) -> bool:
    e = snap["items"].get(to_id(item))
    if not e:
        return False
    return e.get("is_nonstandard") is None


def is_move_legal(snap: dict[str, Any], move: str) -> bool:
    e = (snap.get("moves") or {}).get(to_id(move))
    if not e:
        return False
    return e.get("is_nonstandard") is None


def species_can_have_ability(snap: dict[str, Any], species: str, ability: str) -> bool:
    e = _species_entry(snap, species)
    if not e:
        return False
    ab = e.get("abilities") or {}
    want = ability.lower()
    return any(isinstance(v, str) and v.lower() == want for v in ab.values())


def classify_item_failure(item: str, moves: list[str], snap: dict[str, Any]) -> ItemSeverity:
    """ADR-015c element-type classification (heuristic)."""
    iid = to_id(item)
    # Non-severe duration extenders
    if iid in {
        "damprock",
        "heatrock",
        "smoothrock",
        "icyrock",
        "lightclay",
        "terrainextender",
    }:
        return "non_severe_no_substitute"
    # Severe unique interactions
    if iid in {"toxicorb", "flameorb", "stickybarb"}:
        return "severe_no_substitute"
    # Type-locked boosters (subset)
    type_locked = {
        "blackglasses": "Dark",
        "charcoal": "Fire",
        "mysticwater": "Water",
        "miracleseed": "Grass",
        "magnet": "Electric",
        "nevermeltice": "Ice",
        "poisonbarb": "Poison",
        "softsand": "Ground",
        "sharpbeak": "Flying",
        "twistedspoon": "Psychic",
        "silverpowder": "Bug",
        "hardstone": "Rock",
        "spelltag": "Ghost",
        "dragonfang": "Dragon",
        "blackbelt": "Fighting",
        "metalcoat": "Steel",
        "fairyfeather": "Fairy",
        "silkscarf": "Normal",
    }
    if iid in type_locked:
        return "type_locked_swap"
    # Life Orb-style universal
    if iid in {"lifeorb", "choicescarf", "choiceband", "choicespecs", "assaultvest", "focussash", "sitrusberry"}:
        return "universal_swap"
    return "universal_swap"


def team_item_ids(team_draft: list[Slot] | None, *, exclude_slot: int | None = None) -> set[str]:
    used: set[str] = set()
    if not team_draft:
        return used
    for i, slot in enumerate(team_draft):
        if exclude_slot is not None and i == exclude_slot:
            continue
        item = slot.item.value
        if item:
            used.add(to_id(item))
    return used


def check_set(
    species: str,
    moves: list[str],
    item: str,
    *,
    ability: str | None = None,
    team_draft: list[Slot] | None = None,
    exclude_slot: int | None = None,
    snap: dict[str, Any] | None = None,
) -> LegalityResult:
    snap = snap or load_snapshot()
    failures: list[LegalityFailure] = []

    if not is_species_legal(snap, species):
        failures.append(LegalityFailure("species", species, "illegal or banned species"))

    if item and not is_item_legal(snap, item):
        failures.append(
            LegalityFailure(
                "item",
                item,
                "item is_nonstandard or unknown",
                item_severity=classify_item_failure(item, moves, snap),
            )
        )

    if item and to_id(item) in team_item_ids(team_draft, exclude_slot=exclude_slot):
        failures.append(
            LegalityFailure(
                "item_clause",
                item,
                "duplicate item on team_draft (Item Clause)",
                item_severity="universal_swap",
            )
        )

    learnset = resolve_learnset(snap, species)
    if learnset is None and moves:
        failures.append(LegalityFailure("learnset", species, "no resolvable learnset"))
    else:
        for mv in moves:
            if not is_move_legal(snap, mv):
                failures.append(LegalityFailure("move", mv, "move illegal or unknown"))
            elif learnset is not None and to_id(mv) not in learnset:
                failures.append(LegalityFailure("learnset", mv, "not in Champions learnset"))

    if ability and not species_can_have_ability(snap, species, ability):
        failures.append(LegalityFailure("ability", ability, "not in species ability pool"))

    return LegalityResult(ok=not failures, failures=failures)


def legal_moves_for(species: str, snap: dict[str, Any] | None = None) -> list[str]:
    snap = snap or load_snapshot()
    ls = resolve_learnset(snap, species) or []
    moves = snap.get("moves") or {}
    return [m for m in ls if m in moves and moves[m].get("is_nonstandard") is None]


def legal_items(snap: dict[str, Any] | None = None) -> list[str]:
    snap = snap or load_snapshot()
    return [iid for iid, e in snap["items"].items() if e.get("is_nonstandard") is None]


def current_availability_gaps(
    species: str,
    moves: list[str],
    item: str,
    ability: str | None = None,
    snap: dict[str, Any] | None = None,
) -> dict[str, list[str]]:
    """Present-tense: legal options not used by the build (ADR-015b)."""
    snap = snap or load_snapshot()
    used_moves = {to_id(m) for m in moves}
    legal_m = set(legal_moves_for(species, snap))
    unused_moves = sorted(legal_m - used_moves)
    # Cap noise — only surface high-signal unused damaging STAB later; return full for now callers filter
    unused_items: list[str] = []
    if item and is_item_legal(snap, item):
        # candidates: same-category not used — leave empty list marker that item is fine
        pass
    e = _species_entry(snap, species)
    unused_abilities: list[str] = []
    if e:
        for v in (e.get("abilities") or {}).values():
            if isinstance(v, str) and (not ability or v.lower() != ability.lower()):
                unused_abilities.append(v)
    return {
        "unused_legal_moves": unused_moves[:20],
        "unused_abilities": unused_abilities,
        "unused_items": unused_items,
    }
