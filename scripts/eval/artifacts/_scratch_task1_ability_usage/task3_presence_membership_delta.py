"""Scratch: setup presence weight floor membership delta vs percent-only."""

from __future__ import annotations

import json
from pathlib import Path

from recommender.ids import to_id
from recommender.legality import load_snapshot, resolve_learnset
from recommender.role_compendium import (
    BULK_UP_ATTACKER_CRITERIA,
    CALM_MIND_ATTACKER_CRITERIA,
    IRON_DEFENSE_BODY_PRESS_CRITERIA,
    NASTY_PLOT_ATTACKER_CRITERIA,
    SWORDS_DANCE_ATTACKER_CRITERIA,
    _UsageCtx,
    legal_species_pool,
    _pool_index,
)
from recommender.role_compendium_usage import (
    _best_move_set_pct,
    _hits_clear_setup_presence,
    _same_row_both_moves,
)

REG = "champions-reg-mc"
OUT = Path(__file__).resolve().parent / "presence_weight_delta.json"

EXPECTED_DROP = {
    "Pinsir-Mega",
    "Zoroark",
    "Infernape",
    "Lucario",
    "Medicham",
    "Diggersby",
    "Lycanroc-Dusk",
}
EXPECTED_KEEP = {"Rillaboom", "Raichu-Mega-Y", "Incineroar"}


def _members_for_setup(move_id: str, *, weight_mode: bool) -> set[str]:
    snap = load_snapshot()
    pool = _pool_index(legal_species_pool(snap), snap, regulation=REG)
    uctx = _UsageCtx(live_fetch=None, showdown_fetch=None, regulation=REG)
    sd_cache: dict = {}
    out: set[str] = set()
    for sid, name in pool.items():
        if move_id not in set(resolve_learnset(snap, sid) or []):
            continue
        if not uctx.delivers(name, move_id):
            continue
        if weight_mode:
            ok = _hits_clear_setup_presence(
                name,
                {move_id},
                uctx=uctx,
                sd_cache=sd_cache,
                showdown_fetch=None,
            )
        else:
            ok = (
                _best_move_set_pct(
                    name,
                    move_id,
                    uctx=uctx,
                    sd_cache=sd_cache,
                    showdown_fetch=None,
                )
                >= 0.1
            )
        if ok:
            out.add(name)
    return out


def main() -> None:
    cats = [
        ("swords_dance", "swordsdance"),
        ("nasty_plot", "nastyplot"),
        ("calm_mind", "calmmind"),
        ("bulk_up", "bulkup"),
    ]
    dropped: set[str] = set()
    kept_check: dict[str, bool] = {}
    before_all: set[str] = set()
    after_all: set[str] = set()
    per_cat = {}
    for label, mid in cats:
        before = _members_for_setup(mid, weight_mode=False)
        after = _members_for_setup(mid, weight_mode=True)
        before_all |= before
        after_all |= after
        per_cat[label] = {
            "dropped": sorted(before - after),
            "added": sorted(after - before),
            "before_n": len(before),
            "after_n": len(after),
        }
        dropped |= before - after

    # IG-only mid-band observational count across SD setup cats.
    snap = load_snapshot()
    pool = _pool_index(legal_species_pool(snap), snap, regulation=REG)
    uctx = _UsageCtx(live_fetch=None, showdown_fetch=None, regulation=REG)
    sd_cache: dict = {}
    from recommender.usage_data import ingame_species_map, showdown_species_map
    from recommender.forme_identity import canonical_usage_species_id
    from recommender.role_compendium_usage import _move_pct, _move_weight, _showdown_entry

    midband: list[str] = []
    for sid, name in pool.items():
        canon = canonical_usage_species_id(snap, sid, regulation=REG)
        ig = ingame_species_map(REG).get(canon)
        sd = _showdown_entry(
            name, cache=sd_cache, showdown_fetch=None, regulation=REG, snap=snap
        )
        # any setup move?
        for mid in ("swordsdance", "nastyplot", "calmmind", "bulkup"):
            if mid not in set(resolve_learnset(snap, sid) or []):
                continue
            ig_pct = _move_pct(ig if isinstance(ig, dict) else None, mid)
            wt = _move_weight(sd, mid)
            if 0.1 <= ig_pct < 1.0 and (wt is None or wt < 20):
                midband.append(f"{name}/{mid}")
                break

    for name in EXPECTED_KEEP:
        kept_check[name] = name in after_all

    payload = {
        "dropped_union": sorted(dropped),
        "expected_drop_hit": sorted(EXPECTED_DROP & dropped),
        "expected_drop_missed": sorted(EXPECTED_DROP - dropped),
        "expected_keep": kept_check,
        "unexpected_keep_missing": sorted(
            n for n in EXPECTED_KEEP if n not in after_all
        ),
        "ig_only_midband_0_1_to_1": {"count": len(midband), "sample": midband[:40]},
        "per_cat": per_cat,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
