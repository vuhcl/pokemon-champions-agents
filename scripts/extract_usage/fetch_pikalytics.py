#!/usr/bin/env python3
"""Fetch minimal Pikalytics Champions usage/build snapshot (offline ADR-014 prep)."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FORMAT_CODE = "battledataregmbs3"
REGULATION = "champions-reg-mb"
BASE = f"https://www.pikalytics.com/ai/pokedex/{FORMAT_CODE}"

# Role-diverse seed list (drop on 404).
SPECIES = [
    "Garchomp",
    "Kingambit",
    "Incineroar",
    "Charizard-Mega-Y",
    "Whimsicott",
    "Pelipper",
    "Sinistcha",
    "Basculegion",
    "Farigiraf",
    "Sneasler",
    "Amoonguss",
    "Hatterene",
    "Archaludon",
]

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "usage" / "champions-reg-mb.v1.json"


def to_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers={"User-Agent": "pokemon-champions-agents/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _section(md: str, heading: str) -> str:
    """Text after ## heading until next ## (or end). Absent → empty."""
    pat = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.M)
    m = pat.search(md)
    if not m:
        return ""
    rest = md[m.end() :]
    nxt = re.search(r"^##\s+", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def _bullets_pct(section: str) -> list[dict]:
    out: list[dict] = []
    for m in re.finditer(r"^\s*-\s+\*\*(.+?)\*\*:\s*([\d.]+)%", section, re.M):
        out.append({"name": m.group(1).strip(), "pct": float(m.group(2))})
    return out


def _teammates(section: str) -> list[str]:
    names: list[str] = []
    for m in re.finditer(r"^\s*-\s+\*\*(.+?)\*\*:", section, re.M):
        names.append(m.group(1).strip())
    return names


def _featured_sets(md: str) -> list[dict]:
    """Parse '### Team N' blocks' **Species Set**: ability/item/moves."""
    sets: list[dict] = []
    for block in re.finditer(
        r"\*\*[^*]+ Set\*\*:\s*\n((?:\s*-\s+\*\*[^*]+\*\*:.*\n)+)",
        md,
    ):
        body = block.group(1)
        ability = item = None
        moves: list[str] = []
        am = re.search(r"\*\*Ability\*\*:\s*(.+)", body)
        if am:
            ability = am.group(1).strip()
        im = re.search(r"\*\*Item\*\*:\s*(.+)", body)
        if im:
            item = im.group(1).strip()
        mm = re.search(r"\*\*Moves\*\*:\s*(.+)", body)
        if mm:
            moves = [x.strip() for x in mm.group(1).split(",") if x.strip()]
        sets.append({"ability": ability, "item": item, "moves": moves})
    return sets


def _top_spreads(md: str) -> list[dict]:
    """FAQ line: EV spread of `h/a/d/sa/sd/sp` ... pct%.

    Deferred: this extract is dormant (not a current usage-snapshot source). If
    reactivated, Pikalytics FAQ numbers are mainline-scale EVs — run through
    recommender.sp_convert.evs_to_sp before writing top_spreads, or
    _spread_from_usage will pass unconverted EVs into calc/builds.
    """
    out: list[dict] = []
    for m in re.finditer(
        r"EV spread of `(\d+)/(\d+)/(\d+)/(\d+)/(\d+)/(\d+)`.*?([\d.]+)%\s+of competitive",
        md,
        re.S,
    ):
        hp, atk, df, spa, spd, spe = (int(m.group(i)) for i in range(1, 7))
        out.append(
            {
                "evs": {"hp": hp, "atk": atk, "def": df, "spa": spa, "spd": spd, "spe": spe},
                "pct": float(m.group(7)),
            }
        )
    return out


def parse_species(name: str, md: str) -> dict:
    return {
        "name": name,
        "id": to_id(name),
        "common_moves": _bullets_pct(_section(md, "Common Moves")),
        "common_abilities": _bullets_pct(_section(md, "Common Abilities")),
        "common_items": _bullets_pct(_section(md, "Common Items")),
        "teammates": _teammates(_section(md, "Common Teammates")),
        "featured_sets": _featured_sets(md),
        "top_spreads": _top_spreads(md),
    }


def main() -> int:
    species_out: dict[str, dict] = {}
    for name in SPECIES:
        url = f"{BASE}/{name}"
        print(f"fetch {url}", file=sys.stderr)
        md = fetch(url)
        if md is None:
            print(f"  404 — skip {name}", file=sys.stderr)
            continue
        entry = parse_species(name, md)
        # Absent writeup → empty lists is fine; still store the row.
        species_out[entry["id"]] = entry

    snap = {
        "meta": {
            "schema_version": 1,
            "source": "pikalytics",
            "format_code": FORMAT_CODE,
            "regulation": REGULATION,
            "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "species": species_out,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, indent=2) + "\n")
    print(f"Wrote {OUT} ({len(species_out)} species)", file=sys.stderr)

    # Smoke check: known-complete page
    g = species_out.get("garchomp")
    assert g is not None, "garchomp missing from snapshot"
    item_names = {x["name"] for x in g["common_items"]}
    move_names = {x["name"] for x in g["common_moves"]}
    assert "Life Orb" in item_names, f"Garchomp items={item_names}"
    assert "Earthquake" in move_names, f"Garchomp moves={move_names}"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
