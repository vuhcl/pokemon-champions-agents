"""speed_grid.final_spe_after_mods — Scarf×TW floor-once (calc getFinalSpeed)."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_BUILDERS = ROOT / "scripts/eval/part_g_v4/builders"
_KEYS = ROOT / "scripts/eval/part_g_v4/key_artifacts/derived_keys.json"

sys.path.insert(0, str(_BUILDERS))
import speed_grid  # noqa: E402
from _lib import base_stats, champions_spe, load_legality  # noqa: E402


def _mode_flags(mode: str | None) -> tuple[bool, bool]:
    if mode == "scarf_tw":
        return True, True
    if mode == "scarf":
        return True, False
    if mode == "tw":
        return False, True
    return False, False  # bare / unknown


def test_dragonite_vu_examples():
    snap = load_legality()
    base = base_stats(snap, "Dragonite")["spe"]
    assert base == 80
    assert champions_spe(base, 32, "Jolly") == 145
    f = speed_grid.final_spe_after_mods
    assert f(base, 32, "Jolly", scarf=True) == 217
    assert f(base, 32, "Jolly", stage=1, scarf=True) == 325
    assert f(base, 32, "Jolly", stage=1, scarf=True, tw=True) == 651
    assert f(base, 32, "Jolly", scarf=True, tw=True) == 435


def test_dragapult_scarf_tw_differs_from_floor_after_scarf():
    snap = load_legality()
    base = base_stats(snap, "Dragapult")["spe"]
    bare = champions_spe(base, 32, "Timid")
    assert bare == 213
    assert math.floor(bare * 1.5) * 2 == 638
    assert speed_grid.final_spe_after_mods(base, 32, "Timid", scarf=True, tw=True) == 639


def test_committed_spe_at_leaves_unchanged():
    """Every per_cell.*.final_spe_at_n (incl. mode scarf_tw) matches new spe_at.

    Evaluates against current derived_keys.json without writing it.
    """
    keys = json.loads(_KEYS.read_text(encoding="utf-8"))
    snap = load_legality()
    diffs: list[str] = []
    scarf_tw_count = 0

    for label in ("is1_min_spe", "is2_min_spe"):
        block = keys.get(label) or {}
        own = block.get("own_species")
        if not isinstance(own, str):
            continue
        base = base_stats(snap, own)["spe"]
        beneficial = block.get("beneficial_nature") or "Jolly"
        for i, cell in enumerate(block.get("per_cell") or []):
            if not isinstance(cell, dict):
                continue
            for mk, mv in cell.items():
                if not isinstance(mv, dict):
                    continue
                stored = mv.get("final_spe_at_n")
                mode = mv.get("mode")
                n = mv.get("n_suffices")
                if stored is None or mode is None or n is None:
                    continue
                if mode == "scarf_tw":
                    scarf_tw_count += 1
                scarf, tw = _mode_flags(mode)
                nature = (
                    beneficial
                    if ("beneficial" in mk or mk == "beneficial")
                    else "Serious"
                )
                got = speed_grid.final_spe_after_mods(
                    base, int(n), nature, scarf=scarf, tw=tw
                )
                if got != stored:
                    diffs.append(
                        f"{label}.per_cell[{i}].{mk}: stored={stored} new={got} "
                        f"mode={mode} n={n} nature={nature}"
                    )

    assert scarf_tw_count == 0  # latent path; no committed scarf_tw leaves today
    assert not diffs, diffs
