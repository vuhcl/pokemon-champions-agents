"""FU72: build versioned arm keys (does not edit frozen a393ae91 artifacts).

Run: uv run python -m scripts.eval.part_g_arm.state.keys_fu72.build_fu72_artifacts
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STATE = HERE.parent
V4 = HERE.parents[2] / "part_g_v4"
REPO = HERE.parents[4]
OUT = HERE

sys.path.insert(0, str(V4 / "builders"))
sys.path.insert(0, str(V4 / "checks"))

from _lib import base_stats, load_legality  # noqa: E402
from speed_grid import final_spe_after_mods  # noqa: E402

BAD_SPLIT_TURNS = [
    ("DM2", 1),
    ("DM6", 1),
    ("GS1", 1),
    ("GS1", 2),
    ("H15", 1),
    ("HN2b", 1),
    ("HU2b", 1),
    ("IS2", 1),
    ("MT3", 1),
    ("MT3", 2),
    ("MT3", 3),
    ("MT6", 1),
    ("MT6", 2),
    ("MT6", 3),
    ("TB1", 1),
]

# Request-text overrides (manifest revision; frozen runner untouched).
REQUEST_TEXT_OVERRIDES = {
    ("MR2", 1): "Lock Choice Specs on Hatterene",
    ("MR3", 1): "Lock Incineroar in slot 2",
    ("MR5", 1): "Lock into slot 2",
    ("MW3", 1): "Lock Incineroar in the slot I mentioned",
    ("HC1", 1): "I want my team to be all water and all fire",
    ("MT6", 1): "I want my team to be all water and all fire",
    ("MT6", 2): "Keep the Water only constraint",
    ("MT1", 1): "limit slot 1 to Water only",
    ("HU3", 1): "Give me some bulky Fire type options for slot 3",
    ("TB2", 1): "Swap Flare Blitz for Darkest Lariat.",
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _point(pid: str, text: str, *, tool_backed: bool = False, conditional: bool = False) -> dict[str, Any]:
    return {
        "id": pid,
        "text": text,
        "tool_backed": tool_backed,
        "conditional": conditional,
    }


def _split_semicolon(acceptance: str) -> tuple[list[dict[str, str]], bool]:
    """Mechanical ';'-split with no wording change. Returns (points, ambiguous)."""
    text = (acceptance or "").strip()
    if not text:
        return [{"id": "acceptance", "text": "(no acceptance text)"}], False
    parts = [p.strip() for p in text.split(";") if p.strip()]
    ambiguous = False
    # Heuristics for bad splits inside a delimiter (R2 60 family).
    if any(len(p) < 12 for p in parts[1:]):
        ambiguous = True
    if any(p[0].islower() for p in parts[1:] if p):
        ambiguous = True
    if "Key from" in text or "derived_keys" in text and len(parts) > 3:
        ambiguous = True
    if len(parts) <= 1:
        return [{"id": "acceptance", "text": text}], False
    return [{"id": f"p{i+1}", "text": p} for i, p in enumerate(parts)], ambiguous


def compute_is_minima() -> dict[str, Any]:
    snap = load_legality()
    dk = json.loads((V4 / "key_artifacts" / "derived_keys.json").read_text())
    cells = [c["opp_final_spe"] for c in dk["is1_min_spe"]["per_cell"]]

    def min_sp(own: int, tgt: int, nature: str, **kw: Any) -> dict[str, Any]:
        for n in range(0, 33):
            spe = final_spe_after_mods(own, n, nature, **kw)
            if spe > tgt:
                return {"min_sp": n, "spe_at_min": spe, "reachable": True}
        return {
            "min_sp": None,
            "spe_at_32": final_spe_after_mods(own, 32, nature, **kw),
            "reachable": False,
        }

    g = base_stats(snap, "Garchomp")["spe"]
    b = base_stats(snap, "Basculegion")["spe"]
    s = base_stats(snap, "Slowbro")["spe"]
    p = base_stats(snap, "Pincurchin")["spe"]
    am = base_stats(snap, "Alakazam-Mega")["spe"]
    alak = final_spe_after_mods(am, 32, "Timid")

    is1: dict[str, Any] = {"cells": cells, "own_base_spe": g, "per_cell": {}}
    for cell in cells:
        row: dict[str, Any] = {}
        for label, nat in (("neutral", "Serious"), ("beneficial", "Jolly")):
            row[label] = {
                "bare": min_sp(g, cell, nat),
                "scarf": min_sp(g, cell, nat, scarf=True),
                "scarf_tw": min_sp(g, cell, nat, scarf=True, tw=True),
            }
        is1["per_cell"][str(cell)] = row

    is2: dict[str, Any] = {"cells": cells, "own_base_spe": b, "nature": "Jolly", "budget_R": 24, "per_cell": {}}
    for cell in cells:
        m = min_sp(b, cell, "Jolly", scarf=True)
        shortfall = None
        fits = False
        if m["reachable"] and m["min_sp"] is not None:
            fits = m["min_sp"] <= 24
            shortfall = None if fits else m["min_sp"] - 24
        is2["per_cell"][str(cell)] = {**m, "fits_R24": fits, "shortfall": shortfall}

    max_cell = max(cells)
    is3 = {
        "max_cell": max_cell,
        "own_base_spe": s,
        "max_stack_scarf_tw_timid": final_spe_after_mods(s, 32, "Timid", scarf=True, tw=True),
        "neutral_serious_scarf_tw": min_sp(s, max_cell, "Serious", scarf=True, tw=True),
        "beneficial_timid_scarf_tw": min_sp(s, max_cell, "Timid", scarf=True, tw=True),
        "scarf_alone_serious": min_sp(s, max_cell, "Serious", scarf=True),
        "scarf_alone_timid": min_sp(s, max_cell, "Timid", scarf=True),
        "recorded_scarf_on_slowbro": False,
        "slowbro_common_items_note": "no Choice Scarf in retained COMMON_ITEM list",
    }

    p_max = final_spe_after_mods(p, 32, "Timid", scarf=True, tw=True)
    is4 = {
        "own_base_spe": p,
        "alakazam_mega_timid_32": alak,
        "pincurchin_max_scarf_tw_timid": p_max,
        "unreachable_even_scarf_tw": p_max <= alak,
        # errata G7 floored stack is 219; offline scan agrees
        "max_stack": p_max,
    }
    return {
        "method": "offline scan of final_spe_after_mods / champions Spe over Spe SP 0..32 (same formula as get_speed path); not solve_spread",
        "dragapult_cells": cells,
        "IS1": is1,
        "IS2": is2,
        "IS3": is3,
        "IS4": is4,
    }


def rebuild_usage_sets() -> dict[str, Any]:
    blob = json.loads(
        (REPO / "data/usage/champions-reg-mc.ingame_doubles.v1.json").read_text()
    )
    species = blob["ingame_doubles"]["species"]
    h6 = list(species["rillaboom"]["teammates"][:5])
    by_rank = sorted(species.values(), key=lambda r: r.get("usage_rank") or 9999)
    top10 = [r["name"] for r in by_rank[:10]]
    snap = load_legality()
    p_spe = final_spe_after_mods(base_stats(snap, "Pelipper")["spe"], 32, "Timid")
    outspeeds = []
    for name in top10:
        if name == "Pelipper":
            continue
        threat = max(
            final_spe_after_mods(base_stats(snap, name)["spe"], 32, "Timid"),
            final_spe_after_mods(base_stats(snap, name)["spe"], 32, "Jolly"),
        )
        if p_spe > threat:
            outspeeds.append(name)
    # MT2: intersection of Pelipper ∩ Whimsicott teammates (worksheet: matched, no change)
    inter = [x for x in species["pelipper"]["teammates"] if x in set(species["whimsicott"]["teammates"])]
    mt2 = [x for x in inter if x in {"Charizard", "Garchomp", "Sneasler"}]
    gh = species["gholdengo"]
    modal_spread = gh["top_spreads"][0]
    modal = {
        "definition": "top joint = first top_spreads entry on re-pinned ingame blob (highest pct)",
        "item": gh["common_items"][0]["name"],
        "ability": gh["common_abilities"][0]["name"],
        "nature": modal_spread["nature"],
        "evs": modal_spread["evs"],
        "moves": [m["name"] for m in gh["common_moves"][:4]],
        "spread_pct": modal_spread["pct"],
    }
    hn3 = species["glimmora"]["common_items"][:3]
    return {
        "pin_blob_content_note": "data/usage/champions-reg-mc.ingame_doubles.v1.json (FU68 re-pin; git blob d60a06e0; commit lineage a50b4dd)",
        "H6_top5_partners_rillaboom": h6,
        "H6_old": ["Incineroar", "Garchomp", "Sneasler", "Gholdengo", "Raichu"],
        "HU2_outspeeds_top10_timid32_pelipper": outspeeds,
        "HU2_old": ["Incineroar", "Kingambit", "Golisopod"],
        "ingame_top10": top10,
        "MT2_t2_partners": mt2,
        "MT2_note": "worksheet: MT2 t2 matched; no change to the three-name set",
        "GS1_modal_gholdengo": modal,
        "HN3_common_items": hn3,
        "HN3_note": "percentages unchanged vs prior key text on this pin",
    }


def featured_seed_payload(species: str) -> dict[str, Any]:
    from recommender.regulation_registry import active_regulation
    from recommender.usage_data import featured_or_common_set

    s = featured_or_common_set(species, regulation=active_regulation())
    if s is None:
        return {"species": species, "error": "no featured_or_common_set"}
    d: dict[str, Any]
    if isinstance(s, dict):
        d = s
    elif is_dataclass(s):
        d = asdict(s)
    else:
        d = dict(s)  # type: ignore[arg-type]
    return {
        "species": species,
        "item": d.get("item"),
        "ability": d.get("ability"),
        "nature": d.get("nature"),
        "moves": list(d.get("moves") or []),
        "evs": d.get("evs") or d.get("spread"),
        "source": "featured_or_common_set (ingame first, else Showdown merge)",
    }


def write_seeds(usage: dict[str, Any]) -> list[str]:
    """Versioned seeds under keys_fu72/seeds/. Does not touch a393ae91 fixtures."""
    seeds_dir = OUT / "seeds"
    seeds_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def dump(name: str, doc: dict[str, Any]) -> None:
        path = seeds_dir / name
        path.write_text(json.dumps(doc, indent=2) + "\n")
        written.append(str(path.relative_to(REPO)))

    # MR4: item unlocked on both; other fields locked.
    inc = featured_seed_payload("Incineroar")
    gar = featured_seed_payload("Garchomp")
    # Force distinct items (Item Clause) and unlock only item.
    if inc.get("item") == gar.get("item"):
        gar["item"] = "Leftovers"
    dump(
        "mr4_incineroar_garchomp_item_unlocked.v1.json",
        {
            "row": "MR4",
            "note": (
                "FU72 / worksheet B6: item Attr unlocked on both mons; all other attrs locked. "
                "First Choice Scarf applies; Item Clause refuses the second. sticky_locks on."
            ),
            "flags": {"sticky_locks": True, "tool_fixes_v2": True},
            "slots": [
                {
                    "user_slot": 1,
                    **{k: inc[k] for k in ("species", "item", "ability", "nature", "moves", "evs")},
                    "locks": {
                        "species": True,
                        "ability": True,
                        "item": False,
                        "moveset": True,
                        "nature": True,
                        "spread": True,
                    },
                },
                {
                    "user_slot": 2,
                    **{k: gar[k] for k in ("species", "item", "ability", "nature", "moves", "evs")},
                    "locks": {
                        "species": True,
                        "ability": True,
                        "item": False,
                        "moveset": True,
                        "nature": True,
                        "spread": True,
                    },
                },
            ],
        },
    )

    # TB2: legal Darkest Lariat swap; Charcoal + Flare Blitz sole Fire attack; moveset unlocked (MR4 parallel).
    dump(
        "tb2_incineroar_charcoal_darkest_lariat.v1.json",
        {
            "row": "TB2",
            "note": (
                "FU72: Knock Off is not in Incineroar's Champions learnset; request/fixture use "
                "Darkest Lariat (check_learnset True). Charcoal + Flare Blitz as sole damaging Fire "
                "move preserved for the consequence. moveset unlocked under sticky_locks so the "
                "swap is not field_locked (same seed pattern as MR4 item unlock)."
            ),
            "flags": {"sticky_locks": True, "tool_fixes_v2": True},
            "request_text": "Swap Flare Blitz for Darkest Lariat.",
            "slots": [
                {
                    "user_slot": 1,
                    "species": "Incineroar",
                    "item": "Charcoal",
                    "ability": "Intimidate",
                    "nature": "Adamant",
                    "moves": ["Flare Blitz", "Fake Out", "U-turn", "Parting Shot"],
                    "evs": {"hp": 32, "atk": 32, "def": 0, "spa": 0, "spd": 2, "spe": 0},
                    "locks": {
                        "species": True,
                        "ability": True,
                        "item": True,
                        "moveset": False,
                        "nature": True,
                        "spread": True,
                    },
                }
            ],
            "check_learnset": {"species": "Incineroar", "move": "Darkest Lariat", "learns": True},
        },
    )

    # RB1: keep Calm Mind fixture content (consequence only if write allowed); sticky expects field_locked.
    rb1_src = json.loads((V4 / "fixtures" / "rb1_lucario_megaz_calmmind.json").read_text())
    dump(
        "rb1_lucario_megaz_calmmind.v1.json",
        {
            "row": "RB1",
            "note": (
                "FU72 / sticky_locks on: key expects atomic field_locked refusal; value unchanged. "
                "Calm Mind / Nasty Plot consequence only if a write is allowed. Copied from "
                "part_g_v4 fixture (not a featured build — featured Lucario is Scarf/CC and would "
                "remove the Calm Mind overlap the old key graded)."
            ),
            "flags": {"sticky_locks": True},
            "source_fixture": "scripts/eval/part_g_v4/fixtures/rb1_lucario_megaz_calmmind.json",
            "payload": rb1_src,
            "locks": "all fields locked (sticky refusal path)",
        },
    )

    # Remaining eight-fixture recheck: featured where the key does not need an inconsistency.
    for row, sp, extra in [
        ("DM2", "Incineroar", {"note": "locked attacker for Flare Blitz vs Hatterene"}),
        ("MS2", "Incineroar", {"note": "unlock_keeps_values: values stay, locks cleared"}),
        ("MS3", "Incineroar", {"pair": "Garchomp"}),
        ("MR3", "Incineroar", {"note": "Species Clause target already on team when locking Incineroar@2 — pair seed"}),
        ("MW2", "Incineroar", {"pair": "Garchomp"}),
        ("H18b", None, {"source_fixture": "scripts/eval/part_g_v4/fixtures/h18b_hyper_offense.json"}),
    ]:
        if row == "H18b":
            src = json.loads((REPO / extra["source_fixture"]).read_text())
            dump(
                f"{row.lower()}_seed.v1.json",
                {
                    "row": row,
                    "note": "Rechecked for FU72; fixture kept (judgment-only HO definition). Not synthesized.",
                    "source_fixture": extra["source_fixture"],
                    "payload": src,
                },
            )
            continue
        doc: dict[str, Any] = {
            "row": row,
            "flags": {"sticky_locks": True, "unlock_keeps_values": True, "tool_fixes_v2": True},
            "note": extra.get("note") or "featured_or_common_set; no planted inconsistency",
            "primary": featured_seed_payload(sp),
        }
        if extra.get("pair"):
            doc["secondary"] = featured_seed_payload(extra["pair"])
            if doc["primary"].get("item") == doc["secondary"].get("item"):
                doc["secondary"]["item"] = "Leftovers"
                doc["secondary"]["item_note"] = "distinct from primary for Item Clause"
        dump(f"{row.lower()}_seed.v1.json", doc)

    # Seed index
    dump(
        "SEED_INDEX.json",
        {
            "schema": "keys_fu72_seeds_v1",
            "files": sorted(p.name for p in seeds_dir.glob("*.json") if p.name != "SEED_INDEX.json"),
            "a393ae91_fixtures_untouched": True,
        },
    )
    return written


def build_hand_keys(is_min: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    import check_request_set as c

    rows = {r["id"]: r for r in c.parse_rows((V4 / "part3_request_set_v4.md").read_text())}
    csv_rows = list(
        csv.DictReader(
            (STATE / "expected_tools_fu16" / "expected_tools_rev3_2026-11-02.csv").open()
        )
    )
    csv_by = {(r["row_id"], int(r["turn"])): r for r in csv_rows}

    turns: dict[str, Any] = {}
    ambiguous: list[dict[str, Any]] = []

    def add_turn(
        rid: str,
        turn: int,
        *,
        points: list[dict[str, Any]],
        rewrite: bool,
        pass_criteria_changed: bool,
        tools: dict[str, str] | None = None,
        unreachable: str | None = None,
        request_text: str | None = None,
        notes: str = "",
        flags: list[str] | None = None,
    ) -> None:
        key = f"{rid}__t{turn}"
        base = csv_by.get((rid, turn), {})
        req = request_text or REQUEST_TEXT_OVERRIDES.get((rid, turn)) or base.get("user_turn_text") or ""
        tools = tools or {}
        turns[key] = {
            "row_id": rid,
            "turn": turn,
            "request_text": req,
            "points": points,
            "rewrite": rewrite,
            "pass_criteria_changed": pass_criteria_changed,
            "unreachable_reason": unreachable,
            "flags_required": flags or [],
            "expected_tools_ordered": tools.get(
                "expected", base.get("expected_tools_ordered") or ""
            ),
            "optional_tools": tools.get("optional", base.get("optional_tools") or ""),
            "alternative_path": tools.get("alt", base.get("alternative_path") or ""),
            "notes": notes,
        }

    # --- IS1 ---
    cells = is_min["dragapult_cells"]
    is1_pts = [
        _point("p1", "State which Dragapult COMMON_SPEED cell(s) are assumed, or state that max-speed investment is assumed for the opponent (that assumption is itself a scoring point).", tool_backed=False),
        _point("p2", "If no max-speed assumption is stated, call get_common_speeds (or equivalent) for Dragapult's common cells.", tool_backed=True),
        _point("p3", "For each assumed cell: state whether a bare (no Scarf) Spe investment can outspeed it, or that the cell is unreachable bare. Spe 0 counts as the minimum when it already outspeeds.", tool_backed=True),
        _point("p4", "Give a tool-backed Spe number (solve_spread, or get_speed on the stated spread) that outspeeds the cell under the stated assumption.", tool_backed=True),
        _point("p5", "State the outcome vs budget: fits, shortfall, or unreachable. Scarf and Scarf+Tailwind are reachability notes only.", tool_backed=True),
        _point("p6", "Never say the investment is 'not recommended'.", tool_backed=False),
        _point(
            "p7",
            f"CONDITIONAL (score only if the arm claims a stated SP is the minimum): for each assumed cell, neutral-nature minimum Spe SP is the offline minimum (cells {cells}; see is_minima_fu72.json IS1).",
            tool_backed=True,
            conditional=True,
        ),
        _point(
            "p8",
            "CONDITIONAL: beneficial-nature (Jolly) minimum Spe SP per assumed cell matches the offline minimum.",
            tool_backed=True,
            conditional=True,
        ),
    ]
    add_turn(
        "IS1",
        1,
        points=is1_pts,
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "get_speed|solve_spread", "optional": "get_common_speeds", "alt": ""},
        notes="FU72: hidden 4-part min-SP removed; minimum points conditional on claiming a minimum.",
        flags=["tool_fixes_v2"],
    )

    # --- IS2 ---
    is2_pts = [
        _point("p1", "State the assumed Dragapult cell(s), or state a max-speed assumption for Dragapult.", tool_backed=False),
        _point("p2", "If no assumption, call get_common_speeds for Dragapult.", tool_backed=True),
        _point("p3", "Read the locked Basculegion (Jolly + Choice Scarf, Spe budget R=24) via read_team.", tool_backed=True),
        _point("p4", "Per cell: state the Jolly+Scarf Spe investment that outspeeds (tool-backed), and whether it fits within R=24 or the shortfall.", tool_backed=True),
        _point("p5", "Never say 'not recommended'.", tool_backed=False),
        _point(
            "p6",
            "CONDITIONAL (if a minimum is claimed): the stated Spe SP equals the offline Jolly+Scarf minimum for that cell (is_minima_fu72.json IS2).",
            tool_backed=True,
            conditional=True,
        ),
    ]
    add_turn(
        "IS2",
        1,
        points=is2_pts,
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "read_team;get_speed|solve_spread", "optional": "get_common_speeds"},
        notes="FU72 IS2: one nature (Jolly); per-cell fit/shortfall under R=24.",
    )

    # --- IS3 ---
    is3_pts = [
        _point("p1", "State the assumed Dragapult cell(s) or a max-speed assumption.", tool_backed=False),
        _point("p2", "Tool-backed Spe number that outspeeds under the stated assumption.", tool_backed=True),
        _point("p3", "Max-speed Dragapult cell is reachable only under Scarf + Tailwind; state that reachability.", tool_backed=True),
        _point("p4", "State recorded Scarf usage on Slowbro: none in the retained COMMON_ITEM list.", tool_backed=True),
        _point("p5", "Never say 'not recommended'.", tool_backed=False),
        _point("p6", "CONDITIONAL: claimed neutral-nature minimum matches offline Scarf+TW minimum for the max cell.", tool_backed=True, conditional=True),
        _point("p7", "CONDITIONAL: claimed beneficial-nature minimum matches offline Scarf+TW minimum for the max cell.", tool_backed=True, conditional=True),
    ]
    add_turn("IS3", 1, points=is3_pts, rewrite=True, pass_criteria_changed=True,
             tools={"expected": "get_speed|solve_spread", "optional": "get_common_speeds;get_usage_items"})

    # --- IS4 ---
    is4_pts = [
        _point("p1", "State the Mega Alakazam target cell (Timid Spe-32) or a max-speed assumption.", tool_backed=False),
        _point(
            "p2",
            f"State that Pincurchin's max Spe under Scarf + Tailwind ({is_min['IS4']['pincurchin_max_scarf_tw_timid']}) does not outspeed Mega Alakazam Timid-32 ({is_min['IS4']['alakazam_mega_timid_32']}); unreachable even under Scarf + Tailwind. No invented Spe SP.",
            tool_backed=True,
        ),
        _point("p3", "Never say 'not recommended'.", tool_backed=False),
    ]
    add_turn("IS4", 1, points=is4_pts, rewrite=True, pass_criteria_changed=True,
             tools={"expected": "get_speed|solve_spread", "optional": "get_common_speeds"},
             notes="FU72 IS4: no minimum parts; unreachable point only. Offline max stack 219 (errata G7).")

    # --- Refusal Rule B rows ---
    for rid, prompt_note in [
        ("MR1", "illegal species"),
        ("MR2", "illegal item (Choice Specs on Hatterene)"),
        ("MR3", "Species Clause"),
        ("MR8", "illegal mutation"),
        ("HP3", "illegal mutation"),
    ]:
        add_turn(
            rid,
            1,
            points=[
                _point("p1", f"Rule B: either a lookup that supports the refusal, or a write attempt whose validator refusal the reply recognises and cites ({prompt_note}).", tool_backed=True),
                _point("p2", "Outcome by rubric: the illegal write does not land; team state matches the refusal outcome.", tool_backed=False),
            ],
            rewrite=True,
            pass_criteria_changed=True,
            notes=f"FU72 Rule B refusal. {prompt_note}",
        )

    # MR4 special
    add_turn(
        "MR4",
        1,
        points=[
            _point("p1", "Apply Choice Scarf to the first mon as asked (item field is unlocked in the FU72 seed).", tool_backed=False),
            _point("p2", "Rule B / Item Clause: the second Scarf is refused; the reply recognises and cites the validator refusal (or a clause lookup).", tool_backed=True),
            _point("p3", "No second Scarf applied and no other field touched (rewritten 'state unchanged').", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "set_slot", "alt": "no_lookup_needed|describe"},
        flags=["sticky_locks", "tool_fixes_v2"],
        notes="FU72 MR4 seed: item unlocked both mons. sticky_locks on.",
    )

    # MS2 unlock_keeps_values
    add_turn(
        "MS2",
        1,
        points=[
            _point("p1", "Call unlock_slot (or equivalent) on slot 1.", tool_backed=True),
            _point("p2", "Under unlock_keeps_values: attribute values remain; locks are cleared. The old 'empty slot' expectation does not apply.", tool_backed=False),
            _point("p3", "Read-back states slot 1 unlocked with prior values kept.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        flags=["unlock_keeps_values"],
        notes="FU72 MS2 rewritten for unlock_keeps_values on.",
    )

    # RB1 sticky
    add_turn(
        "RB1",
        1,
        points=[
            _point("p1", "read_team first (current moveset / room).", tool_backed=True),
            _point("p2", "Under sticky_locks: the write is refused with atomic field_locked; Nasty Plot is not applied; existing values unchanged.", tool_backed=False),
            _point("p3", "Calm Mind / Nasty Plot boost-overlap consequence is scored only if a write is allowed; under sticky refusal it is not required.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "read_team;set_slot", "optional": "describe;get_move_static"},
        flags=["sticky_locks"],
        notes="FU72 RB1 sticky_locks on: field_locked refusal.",
    )

    # TB2 legal swap + unlocked moveset
    add_turn(
        "TB2",
        1,
        points=[
            _point("p1", "read_team for the current moveset.", tool_backed=True),
            _point("p2", "Swap Flare Blitz for Darkest Lariat (legal per check_learnset); apply and read back.", tool_backed=True),
            _point("p3", "State that Charcoal no longer boosts (consequence / type-boost vs remaining damaging moves).", tool_backed=False),
            _point("p4", "Offer keep or swap item; no silent item change.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "read_team;set_slot", "optional": "get_move_static;check_learnset"},
        flags=["sticky_locks"],
        request_text="Swap Flare Blitz for Darkest Lariat.",
        notes="FU72: Darkest Lariat replaces illegal Knock Off; moveset unlocked in seed.",
    )

    # MM1
    add_turn(
        "MM1",
        1,
        points=[
            _point("p1", "Build with Salamencite; state a mega cannot hold another item; offer keep stone or base form + Leftovers (form change = offer only).", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"alt": "no_lookup_needed|describe"},
        notes="FU72: no_lookup_needed or validator refusal accepted as alternative to describe.",
    )

    # H8 Q9 — describe required, no no_lookup_needed
    for rid, claim in [("H8", "Item Clause → No"), ("Q9", "Species Clause → No")]:
        add_turn(
            rid,
            1,
            points=[
                _point("p1", f"Outcome: {claim}; no mutation.", tool_backed=False),
                _point("p2", "Required step: describe (or equivalent rules lookup). no_lookup_needed is NOT an alternative; a correct answer from memory can pass outcome and fail the required step.", tool_backed=True),
            ],
            rewrite=True,
            pass_criteria_changed=True,
            tools={"expected": "describe", "alt": ""},
        )

    # MM2 read_team required + optional as alt
    add_turn(
        "MM2",
        1,
        points=[
            _point("p1", "read_team required (name the locked mega / stone referent), or the request must name the referent.", tool_backed=True),
            _point("p2", "Refuse: stone is the required mega item; draft unchanged; form-change offer only.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "read_team", "optional": "", "alt": ""},
        flags=["sticky_locks"],
        notes="FU72 MM2: read_team required; sticky may shift refuse reason to lock.",
    )

    # Optional-as-alternative theme
    for rid in ["MR3", "MR7", "MR8", "MU1", "MU4", "MU8"]:
        base = csv_by.get((rid, 1), {})
        opt = (base.get("optional_tools") or "").strip()
        exp = (base.get("expected_tools_ordered") or "").strip()
        alt = (base.get("alternative_path") or "").strip()
        if opt and opt not in alt:
            alt = "|".join(x for x in [alt, opt] if x)
        pts = [
            _point("p1", (rows.get(rid) or {}).get("acceptance") or "See acceptance.", tool_backed=False),
            _point("p2", "An optional tool call is an alternative path: it does not also require every expected tool.", tool_backed=False),
        ]
        if rid in ("MU1", "MU2"):
            # MU1/MU2 keys UNCHANGED per worksheet B8 — only wire optional-as-alt if already in A theme
            pass
        add_turn(
            rid,
            1,
            points=pts if rid not in ("MU1",) else [
                _point("p1", rows["MU1"]["acceptance"], tool_backed=False),
            ],
            rewrite=rid not in ("MU1",),
            pass_criteria_changed=rid not in ("MU1",),
            tools={"expected": exp, "optional": opt, "alt": alt},
            notes=(
                "FU72: MU1 key text unchanged (tool fixed in #387)."
                if rid == "MU1"
                else "FU72: list optional tool as alternative_path."
            ),
        )

    # MU2 unchanged explicitly
    if "MU2" in rows:
        acc = rows["MU2"]["acceptance"]
        pts, amb = _split_semicolon(acc)
        add_turn("MU2", 1, points=[{"id": p["id"], "text": p["text"], "tool_backed": False, "conditional": False} for p in pts],
                 rewrite=False, pass_criteria_changed=False,
                 notes="FU72: keys UNCHANGED (hypothetical tool fixed in #387).")
        if amb:
            ambiguous.append({"row": "MU2", "turn": 1, "reason": "semicolon split ambiguous", "acceptance": acc})

    # Q10 MV3
    add_turn(
        "Q10",
        1,
        points=[
            _point("p1", "Explains empty unlock; no mutation.", tool_backed=False),
            _point("p2", "read_team is an accepted alternative path when used to explain the empty unlock.", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"alt": "read_team"},
    )
    add_turn(
        "MV3",
        1,
        points=[
            _point("p1", "Required: Rock Slide targets all adjacent foes (both opponents in doubles).", tool_backed=True),
            _point("p2", "Required caveat: accuracy 90% (relaxed from stricter prior wording), so either or both can miss.", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=True,
    )

    # MS5 conflicts field
    add_turn(
        "MS5",
        1,
        points=[
            _point("p1", "Apply archetype change and read back.", tool_backed=True),
            _point("p2", "Audit locked slots; 'flagged' means the conflicts field on the change_archetype result (e.g. control Pelipper).", tool_backed=False),
            _point("p3", "Do not edit locked slots; offers only.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
    )

    # MU6 reset explanation
    add_turn(
        "MU6",
        1,
        points=[
            _point("p1", "Do not call reset_team (hypothetical).", tool_backed=False),
            _point("p2", "Explain what reset_team would clear (counterpart MS3: what would be lost) without writing.", tool_backed=False),
            _point("p3", "State unchanged.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "no_lookup_needed", "optional": "read_team"},
    )

    # MR6 no-op or refusal
    add_turn(
        "MR6",
        1,
        points=[
            _point("p1", "Accept either a no-op (nothing to unlock) or an explicit refusal; state unchanged.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
    )

    # MR5
    add_turn(
        "MR5",
        1,
        points=[
            _point("p1", "Request text is the registered errata: 'Lock into slot 2'. Refuse or ask; state unchanged (occupancy).", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        request_text="Lock into slot 2",
        notes="MR5b remains the clean occupancy test with a named species.",
    )

    # ASK rows
    add_turn(
        "OL4",
        1,
        points=[
            _point("p1", "Ambiguity to resolve: whether the user wants the pending option confirmed/set as draft vs locked in.", tool_backed=False),
            _point("p2", "Accepted: confirm or set a draft. Locking it in is not accepted. Off-topic questions fail.", tool_backed=False),
            _point("p3", "State unchanged until confirmation.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
    )
    add_turn(
        "OL6",
        1,
        points=[
            _point("p1", "Ambiguity to resolve: which referent / action the user means; ask. Off-topic questions fail.", tool_backed=False),
            _point("p2", "State unchanged.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
    )
    add_turn(
        "OL9",
        1,
        points=[
            _point("p1", "Ambiguity: multi-select vs which single option. Off-topic questions fail.", tool_backed=False),
            _point("p2", "Accepted: multi-select or ask which. Not applied until resolved.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
    )
    add_turn(
        "MW3",
        1,
        points=[
            _point("p1", "Ambiguity: which slot 'the slot I mentioned' refers to; ask. Off-topic questions fail.", tool_backed=False),
            _point("p2", "No state change until the slot is resolved.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="Lock Incineroar in the slot I mentioned",
    )
    # OL5 OL7a unchanged meaning — mechanical split only
    for rid in ("OL5", "OL7a"):
        acc = rows[rid]["acceptance"]
        pts, amb = _split_semicolon(acc)
        add_turn(rid, 1, points=[{"id": p["id"], "text": p["text"], "tool_backed": False, "conditional": False} for p in pts],
                 rewrite=False, pass_criteria_changed=False,
                 notes="FU72: wording/behavior unchanged (worksheet).")
        if amb:
            ambiguous.append({"row": rid, "turn": 1, "reason": "semicolon split", "acceptance": acc})

    # HC1 / MT6
    add_turn(
        "HC1",
        1,
        points=[
            _point("p1", "Recognise the two constraints (all Water and all Fire) leave an empty pool (verify with find_species types Water and Fire → count 0).", tool_backed=True),
            _point("p2", "Either record both constraints, or record nothing — both accepted — as long as the empty-pool recognition is clear.", tool_backed=False),
            _point("p3", "Must not silently apply only one constraint or pick a species from an empty pool.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="I want my team to be all water and all fire",
    )

    # MT6 turns
    add_turn(
        "MT6",
        1,
        points=[
            _point("p1", "Same empty-pool recognition as HC1 (Water∧Fire).", tool_backed=True),
            _point("p2", "Either record both constraints or record nothing; both accepted if empty-pool is recognised.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="I want my team to be all water and all fire",
    )
    add_turn(
        "MT6",
        2,
        points=[
            _point("p1", "Resolve to Water only: drop Fire (set_constraint_active / restore / add Water as applicable).", tool_backed=True),
            _point("p2", "Do not stack another Fire constraint.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="Keep the Water only constraint",
    )
    add_turn(
        "MT6",
        3,
        points=[
            _point("p1", "Confirm constraints: Water-only read-back.", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        request_text="Confirm constraints.",
    )

    # MT3
    add_turn(
        "MT3",
        1,
        points=[_point("p1", "Record the No-Intimidate constraint (t1).", tool_backed=True)],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="No Intimidate.",
    )
    add_turn(
        "MT3",
        2,
        points=[
            _point("p1", "Suggest a Fire-typed species for slot 2; tool-backed (find_species or usage path).", tool_backed=True),
            _point("p2", "Asking instead of suggesting Fire is not an accepted path.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="Suggest a Fire type for slot 2.",
    )
    add_turn(
        "MT3",
        3,
        points=[
            _point("p1", "The t3 reply itself answers yes or no for the t2 pick (or picks one of several Fire types / asks which — both accepted).", tool_backed=False),
            _point("p2", "Ability lookup in this turn backs the answer even if t2 already mentioned Intimidate. 'Has Intimidate' = species can have it as a legal ability.", tool_backed=True),
            _point("p3", "If the pick can have Intimidate: flag against the t1 constraint and offer ≥1 tool-backed alternative (different Fire pick, or a non-Intimidate legal ability on the same species). Silent acceptance or flag-with-no-alternative fails.", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="Does it have Intimidate?",
        tools={"expected": "check_species_ability|get_abilities", "alt": ""},
        notes="FU72: no_lookup_needed removed as a free alternative for t3.",
    )

    # Turns that must not be overall N/A: MT2 t1, HC2 t1, MT1 t1/t2, MT5 t1/t2
    add_turn("MT2", 1, points=[_point("p1", "Lock Pelipper into a slot as asked; state reflects the lock.", tool_backed=True)],
             rewrite=True, pass_criteria_changed=True, request_text="Lock Pelipper.")
    add_turn(
        "MT2",
        2,
        points=[
            _point("p1", f"Unordered set {usage['MT2_t2_partners']}; set-scoring; label in-game source.", tool_backed=True),
        ],
        rewrite=False,
        pass_criteria_changed=False,
        notes="MT2 t2 matched after re-pin; no set change.",
    )
    add_turn("MT2", 3, points=[_point("p1", "Confirm slot 1 is Pelipper.", tool_backed=False)],
             rewrite=True, pass_criteria_changed=False, request_text="Confirm slot 1.")

    add_turn(
        "HC2",
        1,
        points=[
            _point("p1", "Separate conflicting requests; ask the user to resolve; no guess; no state change until the user picks.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        request_text="No weather.",
    )
    add_turn("MT1", 1, points=[_point("p1", "Record a Water-only constraint on slot 1.", tool_backed=True)],
             rewrite=True, pass_criteria_changed=True, request_text="limit slot 1 to Water only")
    # MT1 t2 — need prompt
    mt1_turns = []
    import re
    raw = rows["MT1"]["prompt"]
    parts = [p.strip(" .") for p in re.split(r"\(t\d+\)\s*", raw) if p.strip()]
    add_turn("MT1", 2, points=[_point("p1", "Second constraint recorded as the turn requires; both constraints appear in a later read-back.", tool_backed=True)],
             rewrite=True, pass_criteria_changed=True,
             request_text=parts[1] if len(parts) > 1 else "")
    add_turn("MT5", 1, points=[_point("p1", "Record/apply the archetype change asked in t1.", tool_backed=True)],
             rewrite=True, pass_criteria_changed=True)
    add_turn("MT5", 2, points=[_point("p1", "Continue archetype / follow-up for t2; not overall not_applicable.", tool_backed=False)],
             rewrite=True, pass_criteria_changed=True)

    # H6 HU2 GS1 rebuilds
    h6_set = usage["H6_top5_partners_rillaboom"]
    add_turn(
        "H6",
        1,
        points=[
            _point("p1", f"Unordered set {{{', '.join(h6_set)}}}; set-scoring.", tool_backed=True),
            _point("p2", "Must label in-game source.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        notes=f"Rebuilt from re-pin. Old set had Gholdengo; new set replaces it with Kingambit.",
    )
    hu2_set = usage["HU2_outspeeds_top10_timid32_pelipper"]
    add_turn(
        "HU2",
        1,
        points=[
            _point("p1", f"Outspeeds set {{{', '.join(hu2_set)}}} among in-game top-10 at Spe-32 + Spe-boosting nature; set-scoring.", tool_backed=True),
            _point("p2", "Label in-game source.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        notes=f"Rebuilt. Old set included Golisopod (not in current top-10).",
    )

    modal = usage["GS1_modal_gholdengo"]
    add_turn(
        "GS1",
        1,
        points=[
            _point(
                "p1",
                f"SERVED build: either the modal top joint ({modal['moves']}, {modal['item']}, {modal['nature']}, spread pct {modal['spread_pct']}) or any usage-backed build that states its source.",
                tool_backed=True,
            ),
            _point("p2", "Draft via set_slot (or featured path); no lock_fields unless asked.", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=True,
        tools={"expected": "get_usage_items;get_usage_spreads;get_usage_stats;set_slot", "optional": "get_move_static", "alt": "get_featured_builds;set_slot"},
        notes="Modal = top joint of re-pinned blob. get_featured_builds unreachable at current rungs → synthesis alt listed.",
    )
    add_turn(
        "GS1",
        2,
        points=[
            _point("p1", "MUTATION-OK: apply Choice Scarf; Life Orb released; read back.", tool_backed=True),
            _point("p2", "Name every Status move in the actual t1 draft as unusable for damage under Scarf; do not flag status moves that still do something under Scarf (e.g. Trick).", tool_backed=True),
            _point("p3", "Offer attack swaps; no silent move change; no refusal.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        request_text="Use Choice Scarf.",
    )

    # HN3 — percents unchanged
    hn3 = usage["HN3_common_items"]
    add_turn(
        "HN3",
        1,
        points=[
            _point(
                "p1",
                "COMMON_ITEM (ingame): "
                + ", ".join(f"{i['name']} {i['pct']}" for i in hn3)
                + "; cum≥90% cutoff rules unchanged; label in-game.",
                tool_backed=True,
            ),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        notes="Rebuilt from pin; percentages match prior key text.",
    )

    # HU3 reword
    add_turn(
        "HU3",
        1,
        points=[
            _point("p1", "Option list of bulky Fire types for slot 3 (3–5); each option has a bulk reason.", tool_backed=True),
            _point("p2", "Ask which; slot unchanged until selection.", tool_backed=False),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        request_text="Give me some bulky Fire type options for slot 3",
    )

    # IC1 — mark unreachable where featured path missing; keep structure
    add_turn(
        "IC1",
        1,
        points=[
            _point("p1", "SERVED Corviknight with Leftovers (Psychic Seed + Rocky Helmet excluded by Item Clause).", tool_backed=True),
        ],
        rewrite=True,
        pass_criteria_changed=False,
        unreachable="get_featured_builds not bound at current rungs; synthesis path is the alternative",
        tools={"alt": "get_usage_items;get_usage_spreads;get_usage_stats;set_slot"},
    )
    add_turn(
        "IC1",
        2,
        points=[_point("p1", "MUTATION-OK different item (e.g. Sitrus) with read-back; Leftovers released. Trap: Seed/Helmet.", tool_backed=True)],
        rewrite=True,
        pass_criteria_changed=False,
        request_text="Give me a different item.",
    )

    # Unreachable tool-gap rows (keys not frozen as gradable)
    unreachable_specs = {
        "IX1": "#367/#368 effect/priority lookup not shipped",
        "IX5": "#367 effect lookup not shipped",
        "IX7": "#368 type-effectiveness / safe-set lookup not shipped",
        "HU2b": "get_meta_threats returns in-game list, not Showdown ≥4.52% set the key assumes",
        "H18b": "tool-gap / judgment fixture path; mark unreachable where no equivalent at rung",
        "MM1": "partial: describe alt added; featured path may be unreachable at rung",
        "TB1": "get_featured_builds unreachable; synthesis+check_learnset+describe alt listed",
        "MS1": "lock_fields below rung 4",
        "MS8": "lock_fields below rung 4",
        "MT2": "partial: t2 set ok; lock_fields gaps at low rungs if any",
        "GS1": "get_featured_builds unreachable; synthesis alt listed on t1",
    }
    for rid, reason in unreachable_specs.items():
        if f"{rid}__t1" in turns:
            turns[f"{rid}__t1"]["unreachable_reason"] = turns[f"{rid}__t1"].get("unreachable_reason") or reason
        elif rid in rows:
            acc = rows[rid]["acceptance"]
            pts, amb = _split_semicolon(acc)
            add_turn(
                rid,
                1,
                points=[{"id": p["id"], "text": p["text"], "tool_backed": False, "conditional": False} for p in pts],
                rewrite=False,
                pass_criteria_changed=False,
                unreachable=reason,
                notes="FU72: marked unreachable until required tools exist; not graded as arm miss.",
            )
            if amb:
                ambiguous.append({"row": rid, "turn": 1, "reason": "semicolon split on unrewritten unreachable key", "acceptance": acc})

    # Bad-split turns: mechanical split if not already rewritten
    for rid, turn in BAD_SPLIT_TURNS:
        key = f"{rid}__t{turn}"
        if key in turns and turns[key].get("rewrite"):
            continue
        acc = rows.get(rid, {}).get("acceptance") or ""
        # For multi-turn, acceptance is whole-row; flag and attach per-turn note from CSV
        csv_note = (csv_by.get((rid, turn)) or {}).get("notes") or ""
        source = csv_note if csv_note.strip() else acc
        pts, amb = _split_semicolon(source)
        if amb or (acc and ";" in acc and turn > 1):
            ambiguous.append(
                {
                    "row": rid,
                    "turn": turn,
                    "reason": "bad-split turn: mechanical ';'-split on shared row acceptance or terse CSV notes; needs human review of point boundaries",
                    "source_preview": source[:240],
                }
            )
        if key not in turns:
            add_turn(
                rid,
                turn,
                points=[{"id": p["id"], "text": p["text"], "tool_backed": False, "conditional": False} for p in pts],
                rewrite=False,
                pass_criteria_changed=False,
                notes="FU72 first-pass mechanical split (no wording change).",
            )

    # H18b multi-turn structure note
    if "H18b" in rows:
        for t in (1, 2):
            key = f"H18b__t{t}"
            if key not in turns:
                add_turn(
                    "H18b",
                    t,
                    points=[_point("p1", f"Per-turn key for H18b t{t}; see acceptance binary checklist.", tool_backed=False)],
                    rewrite=True,
                    pass_criteria_changed=False,
                    unreachable=unreachable_specs["H18b"],
                    notes="Points per turn, not the same set on every turn.",
                )

    return {
        "schema": "part_g_arm_hand_keys_fu72_v1",
        "config": {
            "sticky_locks": True,
            "unlock_keeps_values": True,
            "tool_fixes_v2": True,
        },
        "turns": turns,
        "ambiguous_splits": ambiguous,
        "request_text_overrides": {f"{a}__t{b}": v for (a, b), v in REQUEST_TEXT_OVERRIDES.items()},
    }


def build_csv_rev4(hand: dict[str, Any]) -> Path:
    src = STATE / "expected_tools_fu16" / "expected_tools_rev3_2026-11-02.csv"
    rows = list(csv.DictReader(src.open()))
    fieldnames = list(rows[0].keys())
    by_turn = hand["turns"]
    out_rows = []
    for r in rows:
        key = f"{r['row_id']}__t{r['turn']}"
        nr = dict(r)
        if key in by_turn:
            t = by_turn[key]
            nr["user_turn_text"] = t["request_text"] or nr["user_turn_text"]
            nr["expected_tools_ordered"] = t["expected_tools_ordered"]
            nr["optional_tools"] = t["optional_tools"]
            nr["alternative_path"] = t["alternative_path"]
            # Encode structured points into notes for humans; extractor uses hand_keys JSON.
            pts = " || ".join(f"{p['id']}: {p['text']}" for p in t["points"])
            prefix = "[FU72] "
            if t.get("unreachable_reason"):
                prefix += f"UNREACHABLE({t['unreachable_reason']}) "
            nr["notes"] = prefix + pts
        out_rows.append(nr)
    dest = OUT / "expected_tools_rev4_2026-11-07.csv"
    with dest.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    return dest


def build_point_diff(hand: dict[str, Any]) -> str:
    import check_request_set as c

    rows = {r["id"]: r for r in c.parse_rows((V4 / "part3_request_set_v4.md").read_text())}
    lines = ["# FU72 point diff (old acceptance ';'-split ↔ new structured points)", ""]
    seen_rows = sorted({t["row_id"] for t in hand["turns"].values()})
    for rid in seen_rows:
        old = rows.get(rid, {}).get("acceptance") or ""
        old_pts, _ = _split_semicolon(old)
        new_turns = sorted(
            [t for t in hand["turns"].values() if t["row_id"] == rid],
            key=lambda x: x["turn"],
        )
        changed = any(t["pass_criteria_changed"] for t in new_turns)
        lines.append(f"## {rid}")
        lines.append(f"- pass_criteria_changed: {changed}")
        lines.append("")
        lines.append("### Old (mechanical ';'-split of request-set acceptance)")
        for p in old_pts:
            lines.append(f"- `{p['id']}`: {p['text']}")
        lines.append("")
        for t in new_turns:
            lines.append(f"### New t{t['turn']} (rewrite={t['rewrite']})")
            if not t["pass_criteria_changed"] and not t["rewrite"]:
                lines.append("- (no intended pass-criteria change; structure-only or unchanged)")
            for p in t["points"]:
                cond = " [conditional]" if p.get("conditional") else ""
                tb = " [tool-backed]" if p.get("tool_backed") else ""
                lines.append(f"- `{p['id']}`{cond}{tb}: {p['text']}")
            lines.append("")
    return "\n".join(lines) + "\n"


def legality_report() -> dict[str, Any]:
    from scripts.eval.part_g_arm.state.fixtures import empty_team
    from scripts.eval.part_g_arm.state.tools import check_learnset
    from recommender.legality import is_item_legal, is_species_legal, load_snapshot

    snap = load_snapshot()
    st = empty_team()
    species = {
        "Garchomp", "Dragapult", "Basculegion", "Slowbro", "Pincurchin", "Alakazam-Mega",
        "Incineroar", "Hatterene", "Gholdengo", "Rillaboom", "Sneasler", "Raichu", "Kingambit",
        "Pelipper", "Whimsicott", "Charizard", "Lucario", "Sinistcha", "Corviknight",
        "Salamence", "Jolteon", "Glimmora", "Primarina", "Annihilape", "Golisopod",
        "Indeedee-F", "Toxapex",
    }
    items = {
        "Choice Scarf", "Choice Specs", "Life Orb", "Sitrus Berry", "Leftovers", "Charcoal",
        "Salamencite", "Galladite", "Glimmoranite", "Focus Sash", "Miracle Seed",
        "Psychic Seed", "Rocky Helmet", "Wide Lens",
    }
    out: dict[str, Any] = {"species": {}, "items": {}, "moves": {}, "failures": []}
    for sp in sorted(species):
        ok = bool(is_species_legal(snap, sp))
        out["species"][sp] = {"ok": ok}
        if not ok:
            out["failures"].append(f"species {sp}")
    # Named in refusal keys on purpose (Champions bans Specs/Band as held items).
    expected_illegal_items = {"Choice Specs", "Choice Band"}
    for it in sorted(items):
        ok = bool(is_item_legal(snap, it))
        out["items"][it] = {
            "ok": ok,
            "expected_illegal": it in expected_illegal_items,
        }
        if not ok and it not in expected_illegal_items:
            out["failures"].append(f"item {it}")
        elif not ok:
            out["items"][it]["note"] = "illegal held item; named by refusal-row keys only"
    pairs = [
        ("Incineroar", "Darkest Lariat", True),
        ("Incineroar", "Knock Off", False),
        ("Incineroar", "Flare Blitz", True),
        ("Lucario", "Nasty Plot", True),
        ("Lucario", "Calm Mind", True),
        ("Gholdengo", "Make It Rain", True),
        ("Gholdengo", "Nasty Plot", True),
    ]
    out["learnset_pairs"] = []
    for sp, mv, expect in pairs:
        r = check_learnset(st, sp, mv)
        learns = bool(r.get("learns"))
        entry = {"species": sp, "move": mv, "learns": learns, "expected": expect, "ok": learns == expect}
        out["learnset_pairs"].append(entry)
        if learns != expect:
            out["failures"].append(f"learnset {sp}/{mv} expected {expect} got {learns}")
    return out


def disagreements() -> list[str]:
    """Worksheet wins; report chat §3 disagreements."""
    return [
        "TB2 seed strategy: worksheet A requires a legal learnable swap; B5 says under sticky_locks the reason shifts to the lock. "
        "Applied MR4-parallel (unlock moveset in seed + Darkest Lariat) so charcoal consequence remains gradable. "
        "Alternate reading (fully locked seed → field_locked refusal only) was not taken; flagged here.",
        "HU2 set: worksheet/§3 both say rebuild from pin; old hard-coded set included Golisopod. "
        "Re-pin top-10 no longer includes Golisopod; new outspeeds set is {Incineroar, Kingambit} only.",
        "H6 set: old key listed Gholdengo; re-pin top-5 partners replace Gholdengo with Kingambit.",
        "IS4 max stack: request-set acceptance still says 218; errata G7 + offline scan = 219. FU72 keys use 219.",
        "Chat §3 said MU1/MU2 keys UNCHANGED — matches worksheet B8. No disagreement.",
        "Chat §3 listed IX1/IX5/IX7 unreachable until #367/#368 — matches worksheet B12.",
    ]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    is_min = compute_is_minima()
    (OUT / "is_minima_fu72.json").write_text(json.dumps(is_min, indent=2) + "\n")
    usage = rebuild_usage_sets()
    (OUT / "usage_rebuild_fu72.json").write_text(json.dumps(usage, indent=2) + "\n")
    write_seeds(usage)
    hand = build_hand_keys(is_min, usage)
    (OUT / "hand_keys_fu72.json").write_text(json.dumps(hand, indent=2) + "\n")
    (OUT / "ambiguous_splits_fu72.md").write_text(
        "# FU72 ambiguous splits\n\n"
        + "\n".join(
            f"- **{a['row']} t{a['turn']}**: {a['reason']}\n  - preview: `{a.get('source_preview') or a.get('acceptance','')[:200]}`"
            for a in hand["ambiguous_splits"]
        )
        + ("\n" if hand["ambiguous_splits"] else "_None flagged beyond per-turn notes._\n")
    )
    (OUT / "point_diff_fu72.md").write_text(build_point_diff(hand))
    build_csv_rev4(hand)
    legal = legality_report()
    (OUT / "legality_report_fu72.json").write_text(json.dumps(legal, indent=2) + "\n")
    (OUT / "legality_report_fu72.md").write_text(
        "# FU72 legality report\n\n"
        + (f"**FAILURES:** {legal['failures']}\n\n" if legal["failures"] else "**No failures.**\n\n")
        + "## Learnset pairs\n"
        + "\n".join(
            f"- {p['species']} / {p['move']}: learns={p['learns']} expected={p['expected']} ok={p['ok']}"
            for p in legal["learnset_pairs"]
        )
        + "\n"
    )
    unreachable = []
    for t in hand["turns"].values():
        if t.get("unreachable_reason"):
            unreachable.append(
                {"row": t["row_id"], "turn": t["turn"], "needs": t["unreachable_reason"]}
            )
    (OUT / "unreachable_fu72.md").write_text(
        "# FU72 unreachable rows\n\n"
        + "\n".join(f"- **{u['row']} t{u['turn']}**: {u['needs']}" for u in unreachable)
        + "\n"
    )
    (OUT / "disagreements_fu72.md").write_text(
        "# Worksheet vs chat §3 disagreements\n\n"
        + "Worksheet wins. Recorded disagreements:\n\n"
        + "\n".join(f"- {d}" for d in disagreements())
        + "\n"
    )
    (OUT / "request_text_overrides_fu72.json").write_text(
        json.dumps(hand["request_text_overrides"], indent=2) + "\n"
    )

    # Manifest + key hash over the new versioned files only
    files = sorted(
        p for p in OUT.rglob("*") if p.is_file() and p.name != "KEYS_MANIFEST_FU72.json"
        and not p.name.startswith("_") and p.suffix in {".json", ".csv", ".md"}
    )
    file_table = {str(p.relative_to(REPO)): _sha(p) for p in files}
    key_hash = hashlib.sha256(
        json.dumps(file_table, sort_keys=True).encode()
    ).hexdigest()
    old_hashes = {
        "expected_tools_rev3_2026-11-02.csv": _sha(
            STATE / "expected_tools_fu16" / "expected_tools_rev3_2026-11-02.csv"
        ),
        "part3_request_set_v4.md": _sha(V4 / "part3_request_set_v4.md"),
        "derived_keys.json": _sha(V4 / "key_artifacts" / "derived_keys.json"),
        "FROZEN_MANIFEST_ARM_V2.json": _sha(STATE / "FROZEN_MANIFEST_ARM_V2.json"),
        "claim_battery_v4.json": _sha(V4 / "battery" / "claim_battery_v4.json"),
    }
    manifest = {
        "schema": "part_g_arm_keys_fu72_manifest_v1",
        "key_hash": key_hash,
        "files": file_table,
        "old_hashes_unchanged": old_hashes,
        "config": hand["config"],
        "note": "New versioned keys only. a393ae91 frozen artifacts not edited.",
    }
    (OUT / "KEYS_MANIFEST_FU72.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # Re-hash including manifest itself for the printed key_hash field update
    file_table[str((OUT / "KEYS_MANIFEST_FU72.json").relative_to(REPO))] = _sha(OUT / "KEYS_MANIFEST_FU72.json")
    manifest["files"] = file_table
    manifest["key_hash"] = hashlib.sha256(json.dumps({k: v for k, v in file_table.items() if not k.endswith("KEYS_MANIFEST_FU72.json")}, sort_keys=True).encode()).hexdigest()
    (OUT / "KEYS_MANIFEST_FU72.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("FU72 artifacts written under", OUT)
    print("key_hash", manifest["key_hash"])
    print("failures", legal["failures"])
    print("unreachable", len(unreachable), "ambiguous", len(hand["ambiguous_splits"]))


if __name__ == "__main__":
    main()
