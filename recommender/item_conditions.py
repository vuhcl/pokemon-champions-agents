"""Hand-curated item activation conditions for query_item_holders.

Keep TYPE_BOOST_ITEMS in sync with legality.classify_item_failure type_locked.
Mega lock uses vendored calc MEGA_STONES only (classic + Z); not item_mega_forme.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from recommender.counters import _species_types, effective_move_type, type_effectiveness
from recommender.ids import to_id
from recommender.legality import is_species_legal, legal_moves_for

REPO_ROOT = Path(__file__).resolve().parents[1]
_CALC_ITEMS_JS = REPO_ROOT / "vendor" / "smogon-calc" / "dist" / "data" / "items.js"

# Keep in sync with legality.classify_item_failure type_locked.
TYPE_BOOST_ITEMS: dict[str, str] = {
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

# Resist berries: berry id -> attacking type reduced.
RESIST_BERRIES: dict[str, str] = {
    "occaberry": "Fire",
    "passhoberry": "Water",
    "wacanberry": "Electric",
    "rindoberry": "Grass",
    "yacheberry": "Ice",
    "chopleberry": "Fighting",
    "kebiaberry": "Poison",
    "shucaberry": "Ground",
    "cobaberry": "Flying",
    "payapaberry": "Psychic",
    "tangaberry": "Bug",
    "chartiberry": "Rock",
    "kasibberry": "Ghost",
    "habanberry": "Dragon",
    "colburberry": "Dark",
    "babiriberry": "Steel",
    "chilanberry": "Normal",
    "roseliberry": "Fairy",
}

TERRAIN_SEEDS: dict[str, str] = {
    "electricseed": "Electric Terrain",
    "grassyseed": "Grassy Terrain",
    "mistyseed": "Misty Terrain",
    "psychicseed": "Psychic Terrain",
}

_STONE_ENTRY_RE = re.compile(
    r"(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z][A-Za-z0-9 ]*))\s*:\s*\{\s*"
    r"(?:'([^']+)'|\"([^\"]+)\"|([A-Za-z][A-Za-z0-9\- ]*))\s*:\s*'([^']+)'\s*\}"
)


def _slice_block(text: str, start_marker: str, end_marker: str) -> str:
    i = text.find(start_marker)
    if i < 0:
        return ""
    j = text.find(end_marker, i + len(start_marker))
    if j < 0:
        return text[i:]
    return text[i:j]


@lru_cache(maxsize=1)
def mega_stones_by_item_id() -> dict[str, tuple[str, str]]:
    """item to_id -> (base species display, mega forme display) from calc MEGA_STONES."""
    text = _CALC_ITEMS_JS.read_text(encoding="utf-8")
    blocks = (
        _slice_block(text, "var GEN_6_MEGA_STONES", "var XY"),
        _slice_block(text, "var ZA_MEGA_STONES", "var SV"),
    )
    out: dict[str, tuple[str, str]] = {}
    for block in blocks:
        for m in _STONE_ENTRY_RE.finditer(block):
            stone = m.group(1) or m.group(2) or m.group(3)
            base = m.group(4) or m.group(5) or m.group(6)
            forme = m.group(7)
            if not stone or not base or not forme:
                continue
            out[to_id(stone)] = (base.strip(), forme.strip())
    return out


def mega_locked_species_ids(item_id: str, snap: dict[str, Any]) -> frozenset[str] | None:
    """Species ids allowed to hold this mega stone, or None if not a mapped stone."""
    entry = mega_stones_by_item_id().get(to_id(item_id))
    if entry is None:
        return None
    base_display, forme_display = entry
    species = snap.get("species") or {}
    locked: set[str] = set()
    for display in (base_display, forme_display):
        sid = to_id(display)
        if sid in species:
            locked.add(sid)
    return frozenset(locked) if locked else frozenset()


def seed_terrain_note(item_id: str) -> str | None:
    terrain = TERRAIN_SEEDS.get(to_id(item_id))
    if not terrain:
        return None
    # Display name from id: Psychic Seed etc. Caller may pass display; keep generic.
    return (
        f"Note: activates on switch-in or when {terrain} starts. "
        f"Needs {terrain} active."
    )


def species_has_damaging_type_move(
    snap: dict[str, Any], species: str, attack_type: str
) -> bool:
    want = attack_type.title() if attack_type else ""
    for mid in legal_moves_for(species, snap):
        if effective_move_type(snap, mid) == want:
            return True
    return False


def species_weak_to(snap: dict[str, Any], species: str, attack_type: str) -> bool:
    types = _species_types(snap, species)
    if not types:
        return False
    return type_effectiveness(attack_type.title(), types) > 1.0


def mechanical_condition(
    item_id: str, snap: dict[str, Any]
) -> tuple[str, str] | None:
    """Return (kind, label) for tier-2 scanning, or None if no species-level condition.

    kind: type_boost | resist_berry | mega (mega has no additive list — caller skips scan)
    """
    iid = to_id(item_id)
    if iid in TERRAIN_SEEDS:
        return None
    if iid == "chilanberry":
        return None
    if iid in TYPE_BOOST_ITEMS:
        t = TYPE_BOOST_ITEMS[iid]
        return ("type_boost", f"type-boost: {t} move")
    if iid in RESIST_BERRIES:
        t = RESIST_BERRIES[iid]
        return ("resist_berry", f"resist berry: weak to {t}")
    if mega_stones_by_item_id().get(iid) is not None:
        return ("mega", "mega-locked")
    return None


def chilan_note() -> str:
    return (
        "Chilan Berry reduces Normal damage; no species is weak to Normal, "
        "so there is no mechanical weak-to list."
    )


def iter_mechanical_species(
    item_id: str,
    snap: dict[str, Any],
    *,
    exclude: set[str],
) -> list[tuple[str, str]]:
    """(species_id, condition_label) for legal species satisfying the condition."""
    kind_label = mechanical_condition(item_id, snap)
    if kind_label is None:
        return []
    kind, label = kind_label
    if kind == "mega":
        return []
    iid = to_id(item_id)
    out: list[tuple[str, str]] = []
    for sid, entry in (snap.get("species") or {}).items():
        if sid in exclude or not is_species_legal(snap, sid):
            continue
        if kind == "type_boost":
            if not species_has_damaging_type_move(snap, sid, TYPE_BOOST_ITEMS[iid]):
                continue
        elif kind == "resist_berry":
            if not species_weak_to(snap, sid, RESIST_BERRIES[iid]):
                continue
        else:
            continue
        name = str(entry.get("name") or sid)
        out.append((sid, label))
    return out
