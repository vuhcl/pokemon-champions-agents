#!/usr/bin/env python3
"""Recompute under-66 sv/* resolved-build spreads via fixed evs_to_sp.

Track F skips species that already have non-thin Champions-native writeups,
so a naive fetch_smogon_writeups.py re-run will not touch most of these rows.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from recommender.ids import to_id  # noqa: E402
from recommender.legality import load_snapshot  # noqa: E402
from recommender.recommend import is_valid_spread  # noqa: E402
from recommender.resolved_builds import (  # noqa: E402
    DEFAULT_DIR,
    _load,
    _path,
    put_resolved_build,
)
from scripts.extract_usage.fetch_smogon_writeups import (  # noqa: E402
    PAUSE,
    base_page_name,
    dump_pokemon,
    enumerate_sv_formats,
    iter_movesets,
    smogon_alias,
)

REGULATION = "champions-reg-mb"
_STATS = ("hp", "atk", "def", "spa", "spd", "spe")


def _spread_sum(spread: dict[str, Any] | None) -> int:
    if not isinstance(spread, dict):
        return 0
    return sum(int(spread.get(k, 0) or 0) for k in _STATS)


def _move_key(moves: list[Any]) -> frozenset[str]:
    return frozenset(to_id(m) for m in moves)


def _display_name(species_id: str, snap: dict[str, Any]) -> str:
    entry = (snap.get("species") or {}).get(to_id(species_id)) or {}
    return str(entry.get("name") or species_id)


def _format_alias(source_format: str) -> str:
    # "sv/vgc" → "vgc"; "sv/battle-stadium-singles" → "battle-stadium-singles"
    return source_format.split("/", 1)[1]


def _match_moveset(
    poke: dict[str, Any],
    *,
    species_id: str,
    moves: list[str],
    item: str,
    source_format: str,
    page_name: str,
    sv_formats: list[dict[str, Any]],
) -> dict[str, Any] | None:
    alias = _format_alias(source_format)
    format_names = {f["name"] for f in sv_formats if f["alias"] == alias}
    if not format_names:
        format_names = {f["name"] for f in sv_formats}
    rows = iter_movesets(poke, format_names, page_name)
    want_moves = _move_key(moves)
    want_item = to_id(item)
    want_species = to_id(species_id)
    exact = [
        r
        for r in rows
        if to_id(r["species"]) == want_species
        and _move_key(r["moves"]) == want_moves
        and to_id(r["item"]) == want_item
    ]
    if exact:
        return exact[0]

    # Fallback: same format-priority ranking Track F uses, then first row for species.
    name_to_meta = {f["name"]: f for f in sv_formats}

    def row_pri(r: dict[str, Any]) -> int:
        meta = name_to_meta.get(r["format"])
        if not meta:
            return 9
        if meta["alias"] == "vgc":
            return 0
        if meta["alias"] == "battle-stadium-singles":
            return 1
        if meta["alias"].startswith("vgc"):
            return 2
        return 3

    same_species = [r for r in rows if to_id(r["species"]) == want_species]
    same_species.sort(key=row_pri)
    return same_species[0] if same_species else None


def refresh(root: Path = DEFAULT_DIR) -> int:
    path = _path(REGULATION, root=root)
    rows = _load(path)
    targets = [
        r
        for r in rows
        if str(r.get("source_format") or "").startswith("sv/")
        and _spread_sum(r.get("spread")) != 66
    ]
    if not targets:
        print("no under-66 sv/* rows", file=sys.stderr)
        return 0

    sv_formats = enumerate_sv_formats()
    snap = load_snapshot()
    failures: list[str] = []

    for row in targets:
        species = str(row["species"])
        display = _display_name(species, snap)
        alias = smogon_alias(display)
        page = base_page_name(display)
        print(f"refresh {species} ({row.get('source_format')})", file=sys.stderr)
        time.sleep(PAUSE)
        poke = dump_pokemon("sv", alias)
        if not poke:
            failures.append(f"{species}: dump failed")
            continue
        matched = _match_moveset(
            poke,
            species_id=species,
            moves=list(row.get("moves") or []),
            item=str(row.get("item") or ""),
            source_format=str(row.get("source_format") or ""),
            page_name=page,
            sv_formats=sv_formats,
        )
        if matched is None:
            failures.append(f"{species}: no matching moveset")
            continue
        # iter_movesets → spread_and_variants → evs_to_sp (fixed completion).
        spread = matched["spread"]
        variants = matched["variants"]
        if not is_valid_spread(spread) or _spread_sum(spread) != 66:
            failures.append(
                f"{species}: recomputed spread sum={_spread_sum(spread)} invalid"
            )
            continue
        ability_kw: dict[str, Any] = {}
        if row.get("ability"):
            ability_kw = {
                "ability": row.get("ability"),
                "ability_candidates": row.get("ability_candidates"),
                "ability_pick_index": row.get("ability_pick_index"),
                "ability_pick_policy": row.get("ability_pick_policy"),
            }
        ok = put_resolved_build(
            species,
            list(row.get("moves") or []),
            str(row.get("item") or ""),
            REGULATION,
            spread,
            str(row.get("source_tier") or "analogous_format_writeup"),
            False,
            row.get("verification_context") or {},
            variants=variants,
            root=root,
            rationale=row.get("rationale"),
            source_format=row.get("source_format"),
            **{k: v for k, v in ability_kw.items() if v is not None},
        )
        if not ok:
            failures.append(f"{species}: put_resolved_build refused")
            continue
        print(f"  ok sum={_spread_sum(spread)} {spread}", file=sys.stderr)

    # Final audit
    refreshed = _load(path)
    still_bad = [
        r
        for r in refreshed
        if str(r.get("source_format") or "").startswith("sv/")
        and _spread_sum(r.get("spread")) != 66
    ]
    if still_bad or failures:
        for msg in failures:
            print(f"FAIL {msg}", file=sys.stderr)
        for r in still_bad:
            print(
                f"FAIL still under-66 {r.get('species')} "
                f"{r.get('source_format')} sum={_spread_sum(r.get('spread'))}",
                file=sys.stderr,
            )
        return 1
    print(f"refreshed {len(targets)} sv/* rows to sum 66", file=sys.stderr)
    return 0


def main() -> int:
    return refresh()


if __name__ == "__main__":
    raise SystemExit(main())
