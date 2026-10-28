"""Build Prankster ∩ weather-setting-move key (script FIRST; sha before model eev).

Weather list source: recommender.move_narrowing.WEATHER_SETTING_MOVES
(= _WEATHER_MANUAL). Snapshot / static.v1.json have no weather field.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from recommender.arm_teammates import is_mega_forme
from recommender.ids import to_id
from recommender.legality import legal_moves_for, load_snapshot
from recommender.move_narrowing import WEATHER_SETTING_MOVES
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.tools import find_species

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
        # e.g. Meowstic vs Meowstic-F — display name with hyphen may still be base id
        return "named_form"
    return "base"


def build() -> dict:
    snap = load_snapshot()
    st = empty_team()
    weather_moves = []
    per_move: dict[str, list[str]] = {}
    union: dict[str, list[str]] = {}
    for mid, weather_label in WEATHER_SETTING_MOVES.items():
        display = _move_display(snap, mid)
        entry = (snap.get("moves") or {}).get(mid) or {}
        weather_moves.append(
            {
                "id": mid,
                "name": display,
                "weather_label": weather_label,
                "category": entry.get("category"),
                "conditional": False,
            }
        )
        result = find_species(st, ability="Prankster", learns_move=display)
        species = list(result.get("species") or [])
        per_move[mid] = species
        for name in species:
            union.setdefault(name, []).append(mid)

    species_rows = []
    for name in sorted(union, key=str.casefold):
        legal = {to_id(m) for m in legal_moves_for(name, snap)}
        learned = [m for m in WEATHER_SETTING_MOVES if m in legal]
        species_rows.append(
            {
                "species": name,
                "forme_label": _forme_label(name, snap),
                "weather_moves": learned,
            }
        )

    n = len(species_rows)
    if n == 0 or n > 25:
        raise SystemExit(f"key set size {n} out of band (empty or >25) — stop for Vu")

    doc = {
        "row_id": "dev-fs-prankster-weather",
        "user_text": "Which Pokemon can have Prankster and learn a move that sets weather?",
        "weather_list_source": {
            "path": "recommender/move_narrowing.py",
            "symbol": "WEATHER_SETTING_MOVES",
            "alias_of": "_WEATHER_MANUAL",
            "note": (
                "Python constant, not a JSON pin field. Snapshot moves and "
                "data/moves/static.v1.json have no weather field."
            ),
            "scope": "all entries in WEATHER_SETTING_MOVES (sets weather when used)",
            "status_only": True,
            "conditional_setters_included": False,
            "excluded_examples": ["Aurora Veil (requires Snow; does not set weather)"],
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
    }
    return doc


def main() -> None:
    doc = build()
    text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    OUT.write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode()).hexdigest()
    print(f"wrote {OUT} count={doc['count']} sha256={sha}")
    print("species:", ", ".join(doc["species_set"]))


if __name__ == "__main__":
    main()
