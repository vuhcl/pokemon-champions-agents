"""18-cat membership delta: old Raw-denom Showdown vs published (same floors).

Writes rescale_deltas.json under this directory. Offline only (live_fetch=None).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium import construct_role_category, legal_species_pool
from recommender.role_compendium_usage import _move_pct
from recommender.usage_data import ingame_species_map, showdown_species_map
from scripts.ci.compendium_refresh_gate import COMPENDIUM_CATEGORIES
from scripts.eval.b6_denom_scale import patched_showdown_via_loader

OUT_DIR = Path(__file__).resolve().parent
OLD_REF = "origin/main"
REG = "champions-reg-mc"
SD_PATH = "data/usage/champions-reg-mc.showdown_doubles.v1.json"


def _load_old_showdown() -> dict[str, Any]:
    raw = subprocess.check_output(
        ["git", "show", f"{OLD_REF}:{SD_PATH}"],
        cwd=ROOT,
    )
    doc = json.loads(raw.decode())
    return dict((doc.get("showdown_doubles") or {}).get("species") or {})


def _member_ids(draft) -> set[str]:
    from recommender.ids import to_id as _to_id

    out: set[str] = set()
    for names in (draft.tiers or {}).values():
        for name in names or []:
            out.add(_to_id(str(name)))
    return out


def _cat_label(cat: str, sub: dict[str, Any]) -> str:
    cond = str(sub.get("condition") or "").strip()
    if cond:
        return f"{cat}:{cond}"
    mid = sub.get("move_id")
    if mid:
        return f"{cat}:{mid}"
    mids = sub.get("move_ids")
    if mids:
        return f"{cat}:{'+'.join(sorted(to_id(m) for m in mids))}"
    return cat


def _role_move_ids(sub: dict[str, Any]) -> set[str]:
    kind = str(sub.get("kind") or "")
    if kind == "def_payoff_setup":
        out: set[str] = set()
        if sub.get("setup_move_id"):
            out.add(to_id(str(sub["setup_move_id"])))
        if sub.get("payoff_move_id"):
            out.add(to_id(str(sub["payoff_move_id"])))
        return out
    if sub.get("setup_move_id"):
        return {to_id(str(sub["setup_move_id"]))}
    if sub.get("move_id"):
        return {to_id(str(sub["move_id"]))}
    if sub.get("move_ids"):
        mids = {to_id(m) for m in sub["move_ids"]}
        # Sleep constructor also sweeps extended Status sleep moves.
        if kind == "sleep_status_spreader":
            mids |= {
                to_id(m)
                for m in (
                    "sleeppowder",
                    "hypnosis",
                    "yawn",
                    "spore",
                    "darkvoid",
                    "sing",
                    "grasswhistle",
                    "lovelykiss",
                )
            }
        return mids
    return set()


def _best_max_source(
    name: str,
    move_ids: set[str],
    *,
    regulation: str,
    sd_map: dict[str, Any] | None = None,
    require_all: bool = False,
) -> dict[str, Any]:
    """Best max(ingame, showdown) across move_ids; which source wins.

    require_all (Screens dual): both Light Screen and Reflect must clear; report
    each move's max source.
    """
    sid = to_id(name)
    ig = ingame_species_map(regulation).get(sid)
    sd = (sd_map or showdown_species_map(regulation)).get(sid)
    per_move: list[dict[str, Any]] = []
    for mid in sorted(move_ids or set()):
        if not mid:
            continue
        ip = _move_pct(ig if isinstance(ig, dict) else None, mid)
        sp = _move_pct(sd if isinstance(sd, dict) else None, mid)
        mx = max(ip, sp)
        if ip > sp:
            src = "ingame"
        elif sp > ip:
            src = "showdown"
        elif mx > 0:
            src = "tie"
        else:
            src = "neither"
        per_move.append(
            {
                "move": mid,
                "max_pct": round(mx, 3),
                "ingame_pct": round(ip, 3),
                "showdown_pct": round(sp, 3),
                "max_source": src,
            }
        )
    if not per_move:
        return {
            "move": "",
            "max_pct": 0.0,
            "ingame_pct": 0.0,
            "showdown_pct": 0.0,
            "max_source": "neither",
            "showdown_only_clear": False,
        }
    if require_all:
        # Dual path (Screens LS+Reflect, or Iron Defense+Body Press): both required.
        dual_keys = {"lightscreen", "reflect"}
        dual = [m for m in per_move if m["move"] in dual_keys]
        if not dual or len(dual) < 2:
            dual = list(per_move)
        limiting = min(dual, key=lambda m: m["max_pct"])
        sources = {m["max_source"] for m in dual}
        if sources == {"showdown"}:
            agg_src = "showdown"
        elif sources == {"ingame"}:
            agg_src = "ingame"
        elif "neither" in sources and limiting["max_pct"] == 0:
            agg_src = "neither"
        else:
            agg_src = "mixed:" + "+".join(sorted(sources))
        return {
            "move": "+".join(m["move"] for m in dual),
            "max_pct": limiting["max_pct"],
            "ingame_pct": limiting["ingame_pct"],
            "showdown_pct": limiting["showdown_pct"],
            "max_source": agg_src,
            "per_move": dual,
            "showdown_only_clear": all(
                m["showdown_pct"] > 0 and m["ingame_pct"] == 0 for m in dual
            ),
        }
    best = max(per_move, key=lambda m: m["max_pct"])
    return {
        **best,
        "showdown_only_clear": best["showdown_pct"] > best["ingame_pct"]
        and best["ingame_pct"] == 0.0
        and best["showdown_pct"] > 0,
    }


def _construct_all(regulation: str) -> dict[str, set[str]]:
    snap = load_snapshot()
    pool = legal_species_pool(snap)
    out: dict[str, set[str]] = {}
    for cat, sub in COMPENDIUM_CATEGORIES:
        label = _cat_label(cat, sub)
        draft = construct_role_category(
            cat,
            sub,
            pool,
            snap=snap,
            live_fetch=None,
            showdown_fetch=None,
            regulation=regulation,
        )
        out[label] = _member_ids(draft)
    return out


def main() -> None:
    old_sd = _load_old_showdown()
    new_sd = showdown_species_map(REG)

    print("building OLD (raw-denom) membership…", flush=True)
    with patched_showdown_via_loader(old_sd):
        old_members = _construct_all(REG)

    print("building NEW (published) membership…", flush=True)
    # ensure loader sees committed file
    import recommender.usage_data as ud

    ud.load_usage.cache_clear()
    new_members = _construct_all(REG)

    flips: list[dict[str, Any]] = []
    per_cat: dict[str, Any] = {}
    showdown_only_clears: list[dict[str, Any]] = []

    for cat, sub in COMPENDIUM_CATEGORIES:
        label = _cat_label(cat, sub)
        o, n = old_members[label], new_members[label]
        admitted = sorted(n - o)
        dropped = sorted(o - n)
        move_ids = _role_move_ids(sub)
        kind = str(sub.get("kind") or "")
        require_all = kind in {"screens_support", "def_payoff_setup"}
        cat_flips = []
        for sid in admitted:
            name = (new_sd.get(sid) or old_sd.get(sid) or {}).get("name") or sid
            old_src = _best_max_source(
                name,
                move_ids,
                regulation=REG,
                sd_map=old_sd,
                require_all=require_all,
            )
            new_src = _best_max_source(
                name,
                move_ids,
                regulation=REG,
                sd_map=new_sd,
                require_all=require_all,
            )
            row = {
                "species_id": sid,
                "direction": "admitted",
                "old": old_src,
                "new": new_src,
            }
            cat_flips.append(row)
            flips.append({"category": label, **row})
            if new_src.get("showdown_only_clear"):
                showdown_only_clears.append(
                    {"category": label, "species_id": sid, **new_src}
                )
        for sid in dropped:
            name = (new_sd.get(sid) or old_sd.get(sid) or {}).get("name") or sid
            old_src = _best_max_source(
                name,
                move_ids,
                regulation=REG,
                sd_map=old_sd,
                require_all=require_all,
            )
            new_src = _best_max_source(
                name,
                move_ids,
                regulation=REG,
                sd_map=new_sd,
                require_all=require_all,
            )
            row = {
                "species_id": sid,
                "direction": "dropped",
                "old": old_src,
                "new": new_src,
            }
            cat_flips.append(row)
            flips.append({"category": label, **row})
        per_cat[label] = {
            "old_n": len(o),
            "new_n": len(n),
            "admitted": admitted,
            "dropped": dropped,
            "flips": cat_flips,
        }
        print(
            f"  {label}: {len(o)}->{len(n)} +{len(admitted)} -{len(dropped)}",
            flush=True,
        )

    payload = {
        "regulation": REG,
        "old_ref": OLD_REF,
        "floors_unchanged": {
            "_USAGE_SET_PCT_FLOOR": 2.3,
            "_TRICK_ROOM_SET_PCT_FLOOR": 22.5,
            "_SETUP_PRESENCE_SET_PCT_FLOOR": 0.1,
            "_DD_SETUP_PRESENCE_FLOOR": 1.0,
        },
        "per_category": per_cat,
        "all_flips": flips,
        "showdown_only_clears_among_admits": showdown_only_clears,
        "summary": {
            "categories_with_flips": sum(
                1 for v in per_cat.values() if v["admitted"] or v["dropped"]
            ),
            "total_admit_events": sum(len(v["admitted"]) for v in per_cat.values()),
            "total_drop_events": sum(len(v["dropped"]) for v in per_cat.values()),
        },
    }
    out = OUT_DIR / "rescale_deltas.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("wrote", out, payload["summary"], flush=True)


if __name__ == "__main__":
    main()
