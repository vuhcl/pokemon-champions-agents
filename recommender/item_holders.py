"""Item → holders lookup (observed usage + optional mechanical tier 2).

Read-only. Regulation is a required kwarg (no default). Exact-tag data only —
no regulation_lookup_chain / archive alias. item_mega_forme is unused; mega
lock comes from calc MEGA_STONES via item_conditions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from recommender.ids import regulation_file_tag, to_id
from recommender.item_conditions import (
    TERRAIN_SEEDS,
    chilan_note,
    iter_mechanical_species,
    mega_locked_species_ids,
)
from recommender.legality import is_item_legal, is_species_legal, load_snapshot
from recommender.role_compendium_setup_constants import (
    _SETUP_PRESENCE_SHOWDOWN_WEIGHT_FLOOR,
)
from recommender.usage_data import (
    TEAM_COMP_DIR,
    ingame_species_map,
    showdown_species_map,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RESOLVED_BUILDS_DIR = REPO_ROOT / "data" / "resolved-builds"

COMPLETE_FOOTER = (
    "Condition table is a curated rule set, not a proof of completeness."
)
NEAR_MISS_MSG = (
    "Couldn't resolve that item. Try an exact item name "
    "(examples: Psychic Seed, Life Orb, Venusaurite)."
)

_PHRASE_RE = re.compile(
    r"(?:"
    r"\bwho\s+(?:uses|runs|holds(?:\s+onto)?)\b|"
    r"\bsomeone\s+who\s+(?:uses|runs|holds)\b|"
    r"\b(?:users|holders)\s+of\b|"
    r"\bwhat\s+(?:uses|runs|holds)\b|"
    r"\bgive\s+me\s+(?:a|an|some|someone)\b.{0,40}\b(?:uses|runs|holds)\b"
    r")",
    re.IGNORECASE | re.DOTALL,
)

_OTHER_INTENT_RE = re.compile(
    r"(?:"
    r"\b(?:lock|unlock|reset|restore|reject|avoid|ban|compare|abandon|confirm)\b|"
    r"\bdon'?t\b|\bdo\s+not\b|"
    r"\bchange\s+(?:its|the|my|this)\b|"
    r"\bput\s+.+\s+on\b|"
    r"\bswap\s+(?:it|item|to)\b|"
    r"\breplace\b|"
    r"\binstead\s+of\b"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ObservedHolder:
    species_id: str
    species_display: str
    source: str  # ingame | showdown | vgcpastes | writeup
    pct: float | None = None
    weight: float | None = None
    count: int | None = None


@dataclass(frozen=True)
class MechanicalCandidate:
    species_id: str
    species_display: str
    condition_label: str


@dataclass(frozen=True)
class ItemHoldersResult:
    item_id: str
    item_display: str
    regulation: str
    observed: tuple[ObservedHolder, ...] = ()
    mechanical: tuple[MechanicalCandidate, ...] = ()
    notes: tuple[str, ...] = ()
    error: str | None = None


def ability_ids_from_species(snap: dict[str, Any]) -> set[str]:
    """Union of species[*].abilities values (no top-level abilities key)."""
    out: set[str] = set()
    for entry in (snap.get("species") or {}).values():
        for v in (entry.get("abilities") or {}).values():
            if isinstance(v, str) and v.strip():
                out.add(to_id(v))
    return out


def legal_item_ids(snap: dict[str, Any]) -> set[str]:
    return {
        iid
        for iid, e in (snap.get("items") or {}).items()
        if e.get("is_nonstandard") is None
    }


def _species_display(snap: dict[str, Any], sid: str) -> str:
    e = (snap.get("species") or {}).get(sid) or {}
    return str(e.get("name") or sid)


def _item_display(snap: dict[str, Any], iid: str) -> str:
    e = (snap.get("items") or {}).get(iid) or {}
    return str(e.get("name") or iid)


def _usage_rank_score(sid: str, *, regulation: str) -> float:
    """Higher is better for mechanical ordering (usage_pct)."""
    ig = ingame_species_map(regulation).get(sid) or {}
    sd = showdown_species_map(regulation).get(sid) or {}
    scores: list[float] = []
    for row in (ig, sd):
        pct = row.get("usage_pct")
        if pct is not None:
            try:
                scores.append(float(pct))
            except (TypeError, ValueError):
                pass
    return max(scores) if scores else 0.0


def _observed_ingame(
    iid: str, snap: dict[str, Any], *, regulation: str
) -> list[ObservedHolder]:
    rows: list[ObservedHolder] = []
    for sid, entry in ingame_species_map(regulation).items():
        if not is_species_legal(snap, sid):
            continue
        for it in entry.get("common_items") or []:
            if to_id(str(it.get("name") or "")) != iid:
                continue
            try:
                pct = float(it.get("pct") or 0)
            except (TypeError, ValueError):
                pct = 0.0
            rows.append(
                ObservedHolder(
                    species_id=sid,
                    species_display=str(entry.get("name") or _species_display(snap, sid)),
                    source="ingame",
                    pct=pct,
                )
            )
            break
    rows.sort(key=lambda h: (-(h.pct or 0.0), h.species_id))
    return rows


def _observed_showdown(
    iid: str, snap: dict[str, Any], *, regulation: str
) -> list[ObservedHolder]:
    floor = float(_SETUP_PRESENCE_SHOWDOWN_WEIGHT_FLOOR)
    rows: list[ObservedHolder] = []
    for sid, entry in showdown_species_map(regulation).items():
        if not is_species_legal(snap, sid):
            continue
        for it in entry.get("common_items") or []:
            if to_id(str(it.get("name") or "")) != iid:
                continue
            if "weight" not in it:
                break
            try:
                weight = float(it["weight"])
            except (TypeError, ValueError):
                break
            if weight < floor:
                break
            try:
                pct = float(it.get("pct") or 0)
            except (TypeError, ValueError):
                pct = 0.0
            rows.append(
                ObservedHolder(
                    species_id=sid,
                    species_display=str(entry.get("name") or _species_display(snap, sid)),
                    source="showdown",
                    pct=pct,
                    weight=weight,
                )
            )
            break
    rows.sort(key=lambda h: (-(h.weight or 0.0), h.species_id))
    return rows


def _load_vgcpastes_exact(regulation: str) -> dict[str, Any]:
    tag = regulation_file_tag(regulation)
    path = TEAM_COMP_DIR / f"{tag}.vgcpastes-builds.v1.json"
    if not path.exists():
        return {"teams": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_writeups_exact(regulation: str) -> list[dict[str, Any]]:
    tag = regulation_file_tag(regulation)
    path = RESOLVED_BUILDS_DIR / f"{tag}.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _observed_vgcpastes(
    iid: str, snap: dict[str, Any], *, regulation: str
) -> list[ObservedHolder]:
    counts: dict[str, int] = {}
    for team in _load_vgcpastes_exact(regulation).get("teams") or []:
        for member in team.get("members") or []:
            if to_id(str(member.get("item") or "")) != iid:
                continue
            sid = to_id(str(member.get("species") or ""))
            if not sid or not is_species_legal(snap, sid):
                continue
            counts[sid] = counts.get(sid, 0) + 1
    rows = [
        ObservedHolder(
            species_id=sid,
            species_display=_species_display(snap, sid),
            source="vgcpastes",
            count=n,
        )
        for sid, n in counts.items()
    ]
    rows.sort(key=lambda h: (-(h.count or 0), h.species_id))
    return rows


def _observed_writeups(
    iid: str, snap: dict[str, Any], *, regulation: str
) -> list[ObservedHolder]:
    seen: set[str] = set()
    rows: list[ObservedHolder] = []
    for row in _load_writeups_exact(regulation):
        if to_id(str(row.get("item") or "")) != iid:
            continue
        sid = to_id(str(row.get("species") or ""))
        if not sid or sid in seen or not is_species_legal(snap, sid):
            continue
        seen.add(sid)
        rows.append(
            ObservedHolder(
                species_id=sid,
                species_display=_species_display(snap, sid),
                source="writeup",
            )
        )
    rows.sort(key=lambda h: h.species_id)
    return rows


def _apply_mega_lock_and_top_n(
    rows_by_source: list[list[ObservedHolder]],
    *,
    locked: frozenset[str] | None,
    top_n: int,
) -> list[ObservedHolder]:
    out: list[ObservedHolder] = []
    for rows in rows_by_source:
        filtered = (
            [h for h in rows if h.species_id in locked]
            if locked is not None
            else rows
        )
        out.extend(filtered[:top_n])
    return out


def query_item_holders(
    item: str,
    *,
    regulation: str,
    top_n: int = 5,
    mechanical_top_n: int = 5,
    snap: dict[str, Any] | None = None,
) -> ItemHoldersResult:
    """Return observed holders (+ optional mechanical tier 2). Read-only."""
    snap = snap or load_snapshot()
    iid = to_id(item)
    display = _item_display(snap, iid) if iid in (snap.get("items") or {}) else item
    if iid not in (snap.get("items") or {}):
        return ItemHoldersResult(
            item_id=iid,
            item_display=str(item),
            regulation=regulation,
            error=NEAR_MISS_MSG,
        )
    if not is_item_legal(snap, iid):
        return ItemHoldersResult(
            item_id=iid,
            item_display=display,
            regulation=regulation,
            error=f"{display} isn't legal in the current regulation.",
        )

    locked = mega_locked_species_ids(iid, snap)
    observed = _apply_mega_lock_and_top_n(
        [
            _observed_ingame(iid, snap, regulation=regulation),
            _observed_showdown(iid, snap, regulation=regulation),
            _observed_vgcpastes(iid, snap, regulation=regulation),
            _observed_writeups(iid, snap, regulation=regulation),
        ],
        locked=locked,
        top_n=top_n,
    )
    observed_ids = {h.species_id for h in observed}

    notes: list[str] = []
    if iid in TERRAIN_SEEDS:
        terrain = TERRAIN_SEEDS[iid]
        notes.append(
            f"Note: {display} activates on switch-in or when {terrain} starts. "
            f"Needs {terrain} active."
        )
    if iid == "chilanberry":
        notes.append(chilan_note())

    mechanical: list[MechanicalCandidate] = []
    mech_rows = iter_mechanical_species(iid, snap, exclude=observed_ids)
    mech_rows.sort(
        key=lambda pair: (
            -_usage_rank_score(pair[0], regulation=regulation),
            pair[0],
        )
    )
    for sid, label in mech_rows[:mechanical_top_n]:
        mechanical.append(
            MechanicalCandidate(
                species_id=sid,
                species_display=_species_display(snap, sid),
                condition_label=label,
            )
        )

    notes.append(COMPLETE_FOOTER)
    return ItemHoldersResult(
        item_id=iid,
        item_display=display,
        regulation=regulation,
        observed=tuple(observed),
        mechanical=tuple(mechanical),
        notes=tuple(notes),
    )


def format_item_holders_result(result: ItemHoldersResult) -> str:
    if result.error:
        return result.error
    lines: list[str] = ["Observed holders (current regulation):"]
    by_source: dict[str, list[ObservedHolder]] = {
        "ingame": [],
        "showdown": [],
        "vgcpastes": [],
        "writeup": [],
    }
    for h in result.observed:
        by_source.setdefault(h.source, []).append(h)

    if by_source["ingame"]:
        bits = [
            f"{h.species_display} {h.pct:.1f}%"
            if h.pct is not None
            else h.species_display
            for h in by_source["ingame"]
        ]
        lines.append(
            "In-game usage (held-item share on that species' top-10 list): "
            + ", ".join(bits)
        )
    if by_source["showdown"]:
        bits = [
            f"{h.species_display} {h.pct:.1f}%"
            if h.pct is not None
            else h.species_display
            for h in by_source["showdown"]
        ]
        lines.append(
            "Showdown usage (ranked by item weight; pct = share of that species' sets): "
            + ", ".join(bits)
        )
    if by_source["vgcpastes"]:
        bits = [
            f"{h.species_display} ({h.count} sets)"
            if h.count is not None
            else h.species_display
            for h in by_source["vgcpastes"]
        ]
        lines.append("VGCPastes: " + ", ".join(bits))
    if by_source["writeup"]:
        bits = [h.species_display for h in by_source["writeup"]]
        lines.append("Writeup kits: " + ", ".join(bits))

    if not any(by_source[s] for s in ("ingame", "showdown", "vgcpastes", "writeup")):
        lines.append("None observed in current-regulation data.")

    for note in result.notes:
        if note == COMPLETE_FOOTER:
            continue
        lines.append("")
        lines.append(note)

    if result.mechanical:
        lines.append("")
        lines.append(
            "Also satisfy activation condition (mechanical, not observed; "
            "assumes direct use by the holder):"
        )
        for m in result.mechanical:
            lines.append(f"- {m.species_display} ({m.condition_label})")

    lines.append("")
    lines.append(COMPLETE_FOOTER)
    return "\n".join(lines)


# --- routing helpers (Commit 2 wires these into classify_input) ---


def has_item_holders_phrase(text: str) -> bool:
    return bool(_PHRASE_RE.search(text))


def has_other_intent_words(text: str) -> bool:
    return bool(_OTHER_INTENT_RE.search(text))


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins, delete, sub = cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def _object_blob(text: str) -> str:
    """Strip common phrase scaffolding; remainder is the lookup object."""
    t = text.strip()
    t = re.sub(
        r"^(?:can\s+you\s+)?(?:give\s+me\s+)?(?:a|an|some|someone\s+who\s+)?"
        r"(?:who|what)\s+(?:uses|runs|holds(?:\s+onto)?)\s+",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(
        r"^(?:users|holders)\s+of\s+",
        "",
        t,
        flags=re.IGNORECASE,
    )
    t = re.sub(r"[?!.]+$", "", t).strip()
    return t


def near_miss_legal_item(text: str, snap: dict[str, Any]) -> str | None:
    """Unique closest legal item id within distance rules, or None."""
    blob = to_id(_object_blob(text))
    if not blob:
        return None
    legal = legal_item_ids(snap)
    best: list[tuple[int, str]] = []
    for iid in legal:
        dist = _levenshtein(blob, iid)
        limit = 1 if len(iid) < 8 else 2
        if dist <= limit:
            best.append((dist, iid))
    if not best:
        return None
    best.sort()
    # unique closest
    winners = [iid for d, iid in best if d == best[0][0]]
    if len(winners) != 1:
        return None
    return winners[0]


def _exact_species_move_or_ability(text: str, snap: dict[str, Any]) -> bool:
    blob = to_id(_object_blob(text))
    if not blob:
        return False
    if blob in (snap.get("species") or {}):
        return True
    if blob in (snap.get("moves") or {}):
        return True
    if blob in ability_ids_from_species(snap):
        return True
    # Also allow display-name substring unique match via to_id of full object.
    return False


def item_species_move_overlap_ids(snap: dict[str, Any]) -> set[str]:
    """Ids that are item ids and also move and/or species ids."""
    items = set((snap.get("items") or {}).keys())
    moves = set((snap.get("moves") or {}).keys())
    species = set((snap.get("species") or {}).keys())
    return items & (moves | species)


def try_route_item_holders(
    text: str,
    *,
    regulation: str,
    snap: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Deterministic gate. Returns pending_response-shaped dict, or None to fall through."""
    if not has_item_holders_phrase(text):
        return None
    if has_other_intent_words(text):
        return None
    try:
        regulation_file_tag(regulation)
    except ValueError:
        return None
    snap = snap or load_snapshot()
    from recommender.turn_intent import extract_item_name_target

    exact = extract_item_name_target(text)
    if exact is not None:
        try:
            result = query_item_holders(exact, regulation=regulation, snap=snap)
        except ValueError:
            return None
        return {
            "turn_intent": "pending_response",
            "turn_payload": {"message": format_item_holders_result(result)},
        }
    if _exact_species_move_or_ability(text, snap):
        return None
    if near_miss_legal_item(text, snap) is not None:
        return {
            "turn_intent": "pending_response",
            "turn_payload": {"message": NEAR_MISS_MSG},
        }
    return None
