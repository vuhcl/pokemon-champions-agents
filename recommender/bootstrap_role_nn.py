"""Bootstrap-only movepool-family-gated nearest-neighbor role transfer.

Used when classify + kit-role mapping leave no TargetRoleDecision. Not a
global classify_anchor_role path — lazy in-process cache only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
from recommender.contingent_value import REDIRECT_MOVES
from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot, resolve_learnset
from recommender.usage_data import featured_or_common_set

_STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")
_STANDARD = frozenset(
    {
        "standard_physical_attacker",
        "standard_special_attacker",
        "standard_mixed_attacker",
    }
)
_SKIP_ROLES = _STANDARD | {"unresolved"}

_FAMILY_MOVES: dict[str, frozenset[str]] = {
    "swords_dance": frozenset({"swordsdance"}),
    "dragon_dance": frozenset({"dragondance"}),
    "nasty_plot": frozenset({"nastyplot"}),
    "calm_mind": frozenset({"calmmind"}),
    "bulk_up": frozenset({"bulkup"}),
    "pivot": frozenset({"uturn", "voltswitch", "flipturn", "partingshot"}),
    "screens": frozenset({"lightscreen", "reflect", "auroraveil"}),
    "redirection": frozenset(to_id(m) for m in REDIRECT_MOVES),
    "tailwind": frozenset({"tailwind"}),
    "trick_room": frozenset({"trickroom"}),
}
_FAMILY_ROLES: dict[str, frozenset[str]] = {
    "swords_dance": frozenset({"swords_dance_attacker"}),
    "dragon_dance": frozenset({"dragon_dance_attacker"}),
    "nasty_plot": frozenset({"nasty_plot_attacker"}),
    "calm_mind": frozenset({"setup_attacker"}),
    "bulk_up": frozenset({"bulk_up_attacker"}),
    "pivot": frozenset({"bulky_pivot", "fast_pivot"}),
    "screens": frozenset({"screens_support"}),
    "redirection": frozenset({"redirection"}),
    "tailwind": frozenset({"tailwind_setter"}),
    "trick_room": frozenset({"trick_room_setter"}),
}
_SOFT_PAIRS = frozenset(
    {
        frozenset({"swords_dance", "dragon_dance"}),
        frozenset({"nasty_plot", "calm_mind"}),
    }
)
_SETUP_FAMILIES = frozenset(
    {"swords_dance", "dragon_dance", "nasty_plot", "calm_mind", "bulk_up"}
)
_PHYS_SETUP_ROLES = frozenset(
    {"swords_dance_attacker", "dragon_dance_attacker", "bulk_up_attacker"}
)
_SPEC_SETUP_ROLES = frozenset({"nasty_plot_attacker", "setup_attacker"})
_MIN_POOL = 5

_cache: dict[tuple[str, str], list[tuple[str, str, tuple[float, ...]]]] = {}


@dataclass(frozen=True)
class NnRoleTransfer:
    role_id: str
    neighbor: str
    family_label: str
    evidence: tuple[str, ...]


def _snapshot_identity(snap: dict[str, Any]) -> str:
    meta = snap.get("meta") or {}
    if isinstance(meta, dict) and meta:
        return str(
            meta.get("extracted_at")
            or meta.get("generated_at")
            or meta.get("version")
            or meta
        )
    return str(id(snap))


def _base_stat_vec(
    snap: dict[str, Any], species: str
) -> tuple[float, ...] | None:
    entry = (snap.get("species") or {}).get(to_id(species)) or {}
    bs = entry.get("base_stats") or {}
    try:
        return tuple(float(bs[k]) / 255.0 for k in _STAT_KEYS)
    except (KeyError, TypeError, ValueError):
        return None


def _atk_spa(snap: dict[str, Any], species: str) -> tuple[int, int]:
    entry = (snap.get("species") or {}).get(to_id(species)) or {}
    bs = entry.get("base_stats") or {}
    return int(bs.get("atk") or 0), int(bs.get("spa") or 0)


def _is_confident(decision, build) -> bool:
    if decision.role_id in _SKIP_ROLES:
        return False
    if featured_or_common_set(build.species or "", regulation=build.regulation):
        return True
    if any(
        p.source
        in {
            "champions_native_writeup",
            "analogous_format_writeup",
            "usage_derived",
        }
        for p in build.provenance
    ):
        return True
    if any(
        m.present and m.importance in ("needed", "wanted")
        for m in decision.mechanisms
    ):
        return True
    if decision.compendium.exact:
        return True
    return False


def _confident_refs(
    regulation: str, snap: dict[str, Any]
) -> list[tuple[str, str, tuple[float, ...]]]:
    key = (regulation, _snapshot_identity(snap))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    rows: list[tuple[str, str, tuple[float, ...]]] = []
    for sid, entry in (snap.get("species") or {}).items():
        if entry.get("is_nonstandard") is not None:
            continue
        name = str(entry.get("name") or sid)
        if not is_species_legal(snap, name):
            continue
        build = resolve_anchor_build(name, regulation=regulation)
        decision = classify_anchor_role(build)
        if not _is_confident(decision, build):
            continue
        vec = _base_stat_vec(snap, name)
        if vec is None:
            continue
        rows.append((name, decision.role_id, vec))
    _cache[key] = rows
    return rows


def learnset_families(snap: dict[str, Any], species: str) -> frozenset[str]:
    learnset = set(resolve_learnset(snap, species) or [])
    fams = {
        fam for fam, moves in _FAMILY_MOVES.items() if learnset & moves
    }
    if fams & _SETUP_FAMILIES:
        atk, spa = _atk_spa(snap, species)
        if atk > spa:
            fams -= {"nasty_plot", "calm_mind"}
        elif spa > atk:
            fams -= {"swords_dance", "dragon_dance", "bulk_up"}
    return frozenset(fams)


def _l2(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def first_listed_ability(species: str, snap: dict[str, Any] | None = None) -> str | None:
    snap = snap or load_snapshot()
    entry = (snap.get("species") or {}).get(to_id(species)) or {}
    for raw in (entry.get("abilities") or {}).values():
        if isinstance(raw, str) and raw.strip():
            return raw
    return None


def pad_role_moves(
    species: str,
    moves: list[str],
    *,
    snap: dict[str, Any] | None = None,
) -> list[str]:
    """Pad a short role-assembled moveset to 4 using learnset damaging moves."""
    snap = snap or load_snapshot()
    out = [str(m) for m in moves if m]
    if len(out) >= 4:
        return out[:4]
    learnset = resolve_learnset(snap, species) or []
    moves_table = snap.get("moves") or {}
    have = {to_id(m) for m in out}
    if "protect" in learnset and "protect" not in have:
        out.append("protect")
        have.add("protect")
    for mid in learnset:
        if len(out) >= 4:
            break
        tid = to_id(mid)
        if tid in have:
            continue
        entry = moves_table.get(tid) or {}
        if entry.get("category") not in ("Physical", "Special"):
            continue
        if int(entry.get("basePower") or 0) <= 0:
            continue
        out.append(str(entry.get("name") or mid))
        have.add(tid)
    return out[:4]


def transfer_bootstrap_role(
    species: str,
    *,
    regulation: str = "champions-reg-mb",
) -> NnRoleTransfer | None:
    """Return a transferred role when gate + NN + shape checks succeed."""
    snap = load_snapshot()
    fams = learnset_families(snap, species)
    if not fams:
        return None
    soft = fams in _SOFT_PAIRS
    if len(fams) >= 2 and not soft:
        return None  # hard-multi → Tier 3
    role_ids: set[str] = set()
    for fam in fams:
        role_ids |= _FAMILY_ROLES[fam]
    refs = _confident_refs(regulation, snap)
    pool = [row for row in refs if row[1] in role_ids]
    if len(pool) < _MIN_POOL:
        return None  # thin → Tier 3
    vec = _base_stat_vec(snap, species)
    if vec is None:
        return None
    ranked = sorted(
        ((_l2(vec, row[2]), row[0], row[1]) for row in pool),
        key=lambda item: item[0],
    )
    top3 = ranked[:3]
    if soft and len({item[2] for item in top3}) != 1:
        return None
    role_id = top3[0][2]
    neighbor = top3[0][1]
    atk, spa = _atk_spa(snap, species)
    if role_id in _PHYS_SETUP_ROLES and atk < spa:
        return None
    if role_id in _SPEC_SETUP_ROLES and spa < atk:
        return None
    family_label = "+".join(sorted(fams))
    return NnRoleTransfer(
        role_id=role_id,
        neighbor=neighbor,
        family_label=family_label,
        evidence=(
            f"nn_similar:{neighbor}:{family_label}",
            f"nn_family:{family_label}",
        ),
    )
