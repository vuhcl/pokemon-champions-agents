#!/usr/bin/env python3
"""Extract Champions Reg M-B usage snap: in-game doubles ranks (CBD) + Showdown@1500 (MunchStats).

ADR-014 offline prep. Attribution: Champions Battle Data + MunchStats/Smogon stats.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

from recommender.teammates import (
    TEAMMATE_LIMIT,
    normalize_munch_teammates,
    without_snapshot_teammates,
)
from recommender.usage_cbd import (
    CBD_API,
    fetch_ingame_doubles_species,
    fetch_json,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "usage" / "champions-reg-mb.v1.json"

# Smogon convention: 1500+ = high-level ladder filter (casual play stripped).
# Confirmed 2026-06 gen9championsvgc2026regmb: 1_163_315 battles at 1500 — adequate.
SHOWDOWN_USAGE_RATING = 1500
SHOWDOWN_FORMAT = "gen9championsvgc2026regmb"
SHOWDOWN_MONTH = "2026-06"
MUNCH_BASE = (
    f"https://raw.githubusercontent.com/PizzaTimeJoshua/munchstats/main/"
    f"stats/{SHOWDOWN_MONTH}/{SHOWDOWN_FORMAT}/{SHOWDOWN_USAGE_RATING}"
)
TEAM_LADDER_N = 50  # matches TEAM_THREAT_N inclusion scale


def to_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def extract_ingame(top_n: int = TEAM_LADDER_N) -> dict[str, dict]:
    idx = fetch_json(f"{CBD_API}/api/index")
    if not isinstance(idx, dict):
        raise SystemExit("CBD /api/index failed")
    ranked: list[tuple[int, str, str]] = []
    for p in idx.get("pokemon") or []:
        bs = ((p.get("summary") or {}).get("battleSummary") or {}).get("Current") or {}
        doubles = bs.get("Doubles") or {}
        pos = doubles.get("position")
        if pos is None:
            continue
        name = p.get("showdownName") or p.get("name")
        sid = to_id(p.get("showdownId") or p.get("slug") or name)
        ranked.append((int(pos), name, sid))
    ranked.sort()
    species: dict[str, dict] = {}
    for pos, name, sid in ranked[:top_n]:
        entry = fetch_ingame_doubles_species(name)
        if entry is None:
            print(f"  ingame #{pos} {sid} SKIP (fetch failed)", file=sys.stderr)
            continue
        entry["usage_rank"] = pos
        # Keep ladder sid if battle omitted showdownId
        if not entry.get("id"):
            entry["id"] = sid
        species[str(entry["id"])] = entry
        print(f"  ingame #{pos} {entry['id']}", file=sys.stderr)
    return species


def _munch_to_common(d: dict, key: str, *, resolve) -> list[dict]:
    raw = d.get(key) or {}
    if not isinstance(raw, dict):
        return []
    # chaos weights are not always 0-100; keep relative pct if sum>0
    items = []
    for name, w in raw.items():
        try:
            weight = float(w)
        except (TypeError, ValueError):
            continue
        items.append((name, weight))
    items.sort(key=lambda x: -x[1])
    total = sum(w for _, w in items) or 1.0
    out = []
    for name, w in items[:12]:
        out.append({"name": resolve(name), "pct": round(100.0 * w / total, 3)})
    return out


def _name_resolvers(legality: dict) -> tuple:
    items = legality.get("items") or {}
    moves = legality.get("moves") or {}
    abilities: dict[str, str] = {}
    for ent in (legality.get("species") or {}).values():
        for name in (ent.get("abilities") or {}).values():
            if isinstance(name, str) and name:
                abilities[to_id(name)] = name

    def item(raw: str) -> str:
        ent = items.get(to_id(raw))
        return (ent or {}).get("name") or raw

    def move(raw: str) -> str:
        ent = moves.get(to_id(raw))
        return (ent or {}).get("name") or raw

    def ability(raw: str) -> str:
        return abilities.get(to_id(raw), raw)

    return item, move, ability


def _munch_spreads(d: dict) -> list[dict]:
    raw = d.get("Spreads") or {}
    if not isinstance(raw, dict):
        return []
    items = sorted(raw.items(), key=lambda kv: -float(kv[1]))
    out = []
    for label, w in items[:8]:
        # "Modest:24/0/14/11/0/17"
        if ":" not in label:
            continue
        nature, rest = label.split(":", 1)
        parts = rest.split("/")
        if len(parts) != 6:
            continue
        hp, atk, df, spa, spd, spe = (int(float(x)) for x in parts)
        out.append(
            {
                "nature": nature,
                "evs": {"hp": hp, "atk": atk, "def": df, "spa": spa, "spd": spd, "spe": spe},
                "pct": float(w),
            }
        )
    return out


def extract_showdown(needed_ids: set[str]) -> tuple[dict[str, dict], dict]:
    index = fetch_json(f"{MUNCH_BASE}/_index.json")
    if not isinstance(index, dict):
        raise SystemExit("MunchStats _index.json failed")
    source_info = index.get("info") if isinstance(index.get("info"), dict) else {}
    poke = index.get("pokemon") or {}
    # Map display name -> usage
    by_id: dict[str, tuple[str, float]] = {}
    for name, meta in poke.items():
        sid = to_id(name)
        by_id[sid] = (name, float((meta or {}).get("usage") or 0.0))

    # Also pull mega/base siblings for any needed base
    legality = json.loads((ROOT / "data" / "legality" / "champions.v1.json").read_text())
    resolve_item, resolve_move, resolve_ability = _name_resolvers(legality)
    species_tbl = legality.get("species") or {}
    expand = set(needed_ids)
    for sid in list(needed_ids):
        for kid, ent in species_tbl.items():
            if ent.get("base_species_id") == sid:
                expand.add(kid)
        # if sid is a mega, include base
        base = (species_tbl.get(sid) or {}).get("base_species_id")
        if base:
            expand.add(base)

    out: dict[str, dict] = {}
    for sid in sorted(expand):
        if sid not in by_id:
            continue
        name, usage = by_id[sid]
        detail = fetch_json(f"{MUNCH_BASE}/{urllib.parse.quote(name)}.json")
        teammates = normalize_munch_teammates(
            detail if isinstance(detail, dict) else None
        )
        if not isinstance(detail, dict):
            # rank-only stub
            out[sid] = {
                "name": name,
                "id": sid,
                "usage_pct": usage * 100.0,
                "common_moves": [],
                "common_abilities": [],
                "common_items": [],
                "top_spreads": [],
                "featured_sets": [],
                "teammates": teammates.snapshot_rows(),
                "teammates_meta": teammates.snapshot_meta(),
                "source": "munchstats-showdown",
            }
            continue
        moves = _munch_to_common(detail, "Moves", resolve=resolve_move)
        items = _munch_to_common(detail, "Items", resolve=resolve_item)
        abilities = _munch_to_common(detail, "Abilities", resolve=resolve_ability)
        spreads = _munch_spreads(detail)
        featured = []
        if moves and items:
            fs: dict = {
                "item": items[0]["name"],
                "moves": [m["name"] for m in moves[:4]],
            }
            if abilities:
                fs["ability"] = abilities[0]["name"]
            if spreads and spreads[0].get("nature"):
                fs["nature"] = spreads[0]["nature"]
            featured.append(fs)
        out[sid] = {
            "name": name,
            "id": sid,
            "usage_pct": usage * 100.0,
            "common_moves": moves,
            "common_abilities": abilities,
            "common_items": items,
            "top_spreads": spreads,
            "featured_sets": featured,
            "teammates": teammates.snapshot_rows(),
            "teammates_meta": teammates.snapshot_meta(),
            "source": "munchstats-showdown",
        }
        print(f"  showdown {sid} usage={usage*100:.2f}%", file=sys.stderr)
    return out, dict(source_info)


def _merge_species_flat(ingame: dict[str, dict], showdown: dict[str, dict]) -> dict[str, dict]:
    """Backward-compat flat map: prefer Showdown builds when present, else in-game."""
    flat: dict[str, dict] = {}
    for sid, e in ingame.items():
        flat[sid] = dict(e)
    for sid, e in showdown.items():
        if sid in flat:
            # keep usage_rank from ingame; prefer showdown build fields
            merged = dict(flat[sid])
            for k in (
                "common_moves",
                "common_abilities",
                "common_items",
                "top_spreads",
                "featured_sets",
                "usage_pct",
                "name",
            ):
                if e.get(k):
                    merged[k] = e[k]
            merged["source"] = "merged"
            flat[sid] = merged
        else:
            flat[sid] = without_snapshot_teammates(e)
    return flat


def build_snapshot(
    ingame: dict[str, dict],
    showdown: dict[str, dict],
    showdown_info: dict,
    *,
    base_meta: dict | None = None,
) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = dict(base_meta or {})
    meta.update(
        {
            "schema_version": 3,
            "regulation": "champions-reg-mb",
            "showdown_rating": SHOWDOWN_USAGE_RATING,
            "showdown_format": SHOWDOWN_FORMAT,
            "showdown_month": SHOWDOWN_MONTH,
            "showdown_battles": showdown_info.get("number of battles"),
            "showdown_teammates_extracted_at": now,
            "showdown_teammates": {
                "source_field": "Teammates",
                "weight_kind": "chaos_weight",
                "percentage_kind": "conditional_probability",
                "denominator_rule": (
                    "max(sum(valid Abilities), sum(valid Teammates) / 6, 1)"
                ),
                "limit": TEAMMATE_LIMIT,
                "caveats": [
                    "weighted ladder estimate, not independent sample count",
                    "not curated tournament data",
                    "retained top-10 rows only",
                ],
            },
            "attribution": (
                "In-game doubles: championsbattledata.com. "
                "Showdown VGC M-B: MunchStats mirror of Smogon chaos stats."
            ),
            "sources": ["championsbattledata", "munchstats-showdown"],
        }
    )
    if not base_meta:
        meta["extracted_at"] = now
    return {
        "meta": meta,
        "ingame_doubles": {"species": ingame},
        "showdown_vgc_mb": {"species": showdown},
        "species": _merge_species_flat(ingame, showdown),
    }


def main() -> int:
    print("extracting in-game doubles ladder...", file=sys.stderr)
    ingame = extract_ingame(TEAM_LADDER_N)
    print(f"extracting showdown@{SHOWDOWN_USAGE_RATING} for lineage of {len(ingame)}...", file=sys.stderr)
    showdown, showdown_info = extract_showdown(set(ingame))
    snap = build_snapshot(ingame, showdown, showdown_info)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, indent=2) + "\n")
    print(
        f"Wrote {OUT} ingame={len(ingame)} showdown={len(showdown)} "
        f"flat={len(snap['species'])}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
