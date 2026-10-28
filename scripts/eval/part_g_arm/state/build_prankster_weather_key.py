"""Build Prankster ∩ weather-setting-move key from legality data only.

Does NOT import find_species (the tool under test). Weather list source:
recommender.move_narrowing.WEATHER_SETTING_MOVES (= _WEATHER_MANUAL).
Snapshot / static.v1.json have no weather field.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from recommender.arm_teammates import is_mega_forme
from recommender.ids import to_id
from recommender.legality import (
    is_species_legal,
    legal_moves_for,
    load_snapshot,
    species_can_have_ability,
)
from recommender.move_narrowing import WEATHER_SETTING_MOVES

HERE = Path(__file__).resolve().parent
OUT = HERE / "dev_keys_prankster_weather.json"


def _move_display(snap: dict, mid: str) -> str:
    entry = (snap.get("moves") or {}).get(mid) or {}
    return str(entry.get("name") or mid)


def _forme_label(name: str, snap: dict) -> str:
    from recommender.species_resolve import lookup_species_id

    if is_mega_forme(name):
        return "mega"
    sid = lookup_species_id(name, snap)
    if sid is None:
        return "base"
    entry = (snap.get("species") or {}).get(sid) or {}
    base = entry.get("base_species_id")
    if base and to_id(base) != to_id(sid):
        return "alternate"
    if "-" in name and not name.endswith("-Mega"):
        return "named_form"
    return "base"


def build() -> dict:
    """Derive key set: legal ∩ Prankster ∩ learns ≥1 WEATHER_SETTING_MOVES id."""
    snap = load_snapshot()
    weather_moves = []
    for mid, weather_label in WEATHER_SETTING_MOVES.items():
        entry = (snap.get("moves") or {}).get(mid) or {}
        weather_moves.append(
            {
                "id": mid,
                "name": _move_display(snap, mid),
                "weather_label": weather_label,
                "category": entry.get("category"),
                "conditional": False,
            }
        )

    weather_ids = frozenset(WEATHER_SETTING_MOVES)
    per_move: dict[str, list[str]] = {mid: [] for mid in WEATHER_SETTING_MOVES}
    species_rows: list[dict] = []
    for sid, entry in (snap.get("species") or {}).items():
        name = str(entry.get("name") or sid)
        if not is_species_legal(snap, name):
            continue
        if not species_can_have_ability(snap, name, "Prankster"):
            continue
        legal = {to_id(m) for m in legal_moves_for(name, snap)}
        learned = [m for m in WEATHER_SETTING_MOVES if m in legal]
        if not learned:
            continue
        for mid in learned:
            per_move[mid].append(name)
        species_rows.append(
            {
                "species": name,
                "forme_label": _forme_label(name, snap),
                "weather_moves": learned,
            }
        )

    species_rows.sort(key=lambda r: str(r["species"]).casefold())
    for mid in per_move:
        per_move[mid] = sorted(set(per_move[mid]), key=str.casefold)

    n = len(species_rows)
    if n == 0 or n > 25:
        raise SystemExit(f"key set size {n} out of band (empty or >25) — stop for Vu")

    return {
        "row_id": "dev-fs-prankster-weather",
        "user_text": "Which Pokemon can have Prankster and learn a move that sets weather?",
        "weather_list_source": {
            "path": "recommender/move_narrowing.py",
            "symbol": "WEATHER_SETTING_MOVES",
            "alias_of": "_WEATHER_MANUAL",
            "note": (
                "Python constant, not a JSON pin field. Snapshot moves and "
                "data/moves/static.v1.json have no weather field. "
                "Key species set derived from legality snapshot + ability/learnset "
                "helpers; does not import find_species."
            ),
            "scope": "all entries in WEATHER_SETTING_MOVES (sets weather when used)",
            "status_only": True,
            "conditional_setters_included": False,
            "excluded_examples": ["Aurora Veil (requires Snow; does not set weather)"],
            "weather_ids": sorted(weather_ids),
        },
        "weather_moves": weather_moves,
        "per_move_prankster_counts": {mid: len(names) for mid, names in per_move.items()},
        "per_move_species": per_move,
        "species": species_rows,
        "species_set": [r["species"] for r in species_rows],
        "count": n,
        "class_target": "SERVED",
        "harness_class": "lookup only",
        "scoring": "set-scoring; script-derived; same style as H11",
        "independence": "no find_species import; legality + WEATHER_SETTING_MOVES only",
    }


def main() -> None:
    doc = build()
    text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    OUT.write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode()).hexdigest()
    print(f"wrote {OUT} count={doc['count']} sha256={sha}")
    print("species:", ", ".join(doc["species_set"]))


if __name__ == "__main__":
    main()
