#!/usr/bin/env python3
"""IS2 redesign + rows A–I keys (eval-only, ADR-060)."""
from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import (
    ROOT,
    champions_spe,
    load_ingame,
    load_legality,
    load_showdown,
    to_id,
)
from speed_grid import common_speed_distinct

OUT = Path(__file__).resolve().parents[1] / "key_artifacts" / "derived_keys.json"
PKG = Path(__file__).resolve().parents[1]
FLAGS = ROOT / "data" / "moves" / "flags.v1.json"
STAT_BOOSTS = ROOT / "data" / "moves" / "stat_boosts.v1.json"
VGCPA_STES = ROOT / "data" / "team-composition" / "champions-reg-mc.vgcpastes-builds.v1.json"
CACHE_ITEMS = ROOT / ".cache" / "pokemon-showdown" / "data" / "items.ts"
SHOWDOWN_CACHE = ROOT / ".cache" / "pokemon-showdown"
ITEMS_TS_PIN = PKG / "key_artifacts" / "showdown_items_ts.pin.json"


def is2_basculegion(sd, snap) -> dict:
    cells = common_speed_distinct(sd, "Dragapult")
    base = snap["species"]["basculegion"]["base_stats"]["spe"]
    assert base == 78
    # locked Jolly + Scarf; R=24
    def spe_at(spe_sp: int) -> int:
        return champions_spe(base, spe_sp, "Jolly", scarf=True)

    per = []
    for c in cells:
        tgt = c["final_spe"]
        need = None
        for sp in range(33):
            if spe_at(sp) > tgt:
                need = sp
                break
        per.append(
            {
                "opp_final_spe": tgt,
                "opp_weight": c["weight"],
                "n_suffices": need,
                "n_minus_1_fails": (spe_at(need - 1) <= tgt) if need and need > 0 else None,
                "investment": (
                    "no investment needed"
                    if need == 0
                    else (f"N={need} suffices and N−1 does not" if need else None)
                ),
                "final_spe_at_n": spe_at(need) if need is not None else None,
                "vs_budget_R24": (
                    "fits"
                    if need is not None and need <= 24
                    else ("shortfall" if need is not None else "unreachable")
                ),
                "shortfall_sp": (need - 24) if need is not None and need > 24 else 0,
            }
        )
    # max at R=24
    max_at_24 = spe_at(24)
    items = (sd["showdown_doubles"]["species"].get("basculegion") or {}).get("common_items") or []
    scarf_in = any(to_id(i.get("name") or "") == "choicescarf" for i in items[:5])
    return {
        "own_species": "Basculegion",
        "own_form_id": "basculegion",
        "base_spe": 78,
        "locked": {"nature": "Jolly", "item": "Choice Scarf", "other_sp_sum": 42, "budget_R": 24},
        "choice_scarf_in_common_item": scarf_in,
        "opp_species": "Dragapult",
        "opp_common_speed": cells,
        "per_cell": per,
        "max_spe_at_R24": max_at_24,
        "hand_max_201": max_at_24 == 201,
        "class": "ASSUME-STATE + PARTIAL",
        "arm_must": (
            "State assumed Dragapult COMMON_SPEED cells; name cell 213 as unbeatable under R=24 "
            f"(needs {per[0]['n_suffices']} Spe SP; short by {per[0]['shortfall_sp']}); "
            "194 and 190 fit. Cap: 213 reachable at Spe-32 Jolly Scarf; miss is budget-only."
        ),
        "fixture_note": "non-Spe SP sum 42 (e.g. HP 10 + Atk 32); split free as long as Spe=0 in lock",
    }


def row_a_corviknight(ing, snap) -> dict:
    cv = ing["ingame_doubles"]["species"]["corviknight"]
    items = [{"name": i["name"], "pct": i["pct"]} for i in (cv.get("common_items") or [])[:5]]
    # fixture legality
    ps = snap["items"].get("psychicseed") or {}
    rh = snap["items"].get("rockyhelmet") or {}
    return {
        "fixture": {
            "Sneasler": {"item": "Psychic Seed", "item_legal": ps.get("is_nonstandard") is None},
            "Indeedee-F": {"item": "Rocky Helmet", "item_legal": rh.get("is_nonstandard") is None},
        },
        "corviknight_ingame_common_items": items,
        "after_item_clause": [i for i in items if i["name"] not in ("Psychic Seed", "Rocky Helmet")],
        "t1_expected_item": "Leftovers",
        "t1_exclusions": ["Psychic Seed", "Rocky Helmet"],
        "t2_expected_item": "Sitrus Berry",
        "classes": {"t1": "SERVED", "t2": "MUTATION-OK"},
        "source": "ingame_doubles.corviknight.common_items",
    }


def row_b_gholdengo_trick() -> dict:
    vp = json.loads(VGCPA_STES.read_text())
    ghold = []
    for ti, t in enumerate(vp["teams"]):
        for m in t.get("members") or []:
            if to_id(m.get("species") or "") != "gholdengo":
                continue
            moves = m.get("moves") or []
            ghold.append(
                {
                    "team_i": ti,
                    "team_id": t.get("team_id"),
                    "nature": m.get("nature"),
                    "item": m.get("item"),
                    "moves": moves,
                    "ability": m.get("ability"),
                    "evs": m.get("evs"),
                }
            )
    trick = [g for g in ghold if any(to_id(x) == "trick" for x in g["moves"])]
    snap = load_legality()
    return {
        "source": "data/team-composition/champions-reg-mc.vgcpastes-builds.v1.json",
        "population": vp["meta"].get("population"),
        "gholdengo_build_count": len(ghold),
        "trick_build_count": len(trick),
        "trick_builds": trick,
        "expected_draft": {"moves_include": "Trick", "item": "Choice Scarf"},
        "choice_item_legality": {
            "choicescarf": (snap["items"].get("choicescarf") or {}).get("is_nonstandard"),
            "choiceband": (snap["items"].get("choiceband") or {}).get("is_nonstandard"),
            "choicespecs": (snap["items"].get("choicespecs") or {}).get("is_nonstandard"),
        },
        "nature_note": "n=2 builds (Timid + Modest); if arm comments on nature, bound by n=2 and pick/offer both",
        "class": "SERVED",
        "open_item": "Arm tool surface must expose VGCPastes builds (eval PR open item)",
    }


def row_c_gholdengo_scarf(ing, flags) -> dict:
    gh = ing["ingame_doubles"]["species"]["gholdengo"]
    moves = [{"name": m["name"], "pct": m["pct"]} for m in (gh.get("common_moves") or [])[:6]]
    items = [{"name": i["name"], "pct": i["pct"]} for i in (gh.get("common_items") or [])[:5]]
    modal_moves = [m["name"] for m in moves[:4]]
    status = []
    fm = flags.get("moves") or {}
    for name in modal_moves:
        mid = to_id(name)
        ent = fm.get(mid) or {}
        if (ent.get("category") or "").lower() == "status":
            status.append(name)
    # choice-lock field in items?
    snap = load_legality()
    scarf = snap["items"].get("choicescarf") or {}
    return {
        "t1_modal_moves": moves[:4],
        "t1_modal_item": items[0] if items else None,
        "t2": "Use Choice Scarf",
        "status_moves_in_modal_draft": status,
        "choice_lock_field_in_legality_blob": None,
        "choice_lock_blob_keys": sorted(scarf.keys()),
        "choice_lock_part0_hand_rule": (
            "Choice Scarf locks the holder into one move each turn; status moves in the draft "
            "become unusable while Scarf is held. No choice-lock field in pinned items blob "
            f"(keys={sorted(scarf.keys())}) — hand-written Part 0 rule for this key."
        ),
        "classes": {"t1": "SERVED", "t2": "MUTATION-OK"},
        "source": "ingame_doubles.gholdengo + flags.v1.json category",
    }


def row_d_lucario_z(sd, flags) -> dict:
    lz = sd["showdown_doubles"]["species"]["lucariomegaz"]
    moves = [{"name": m["name"], "pct": m["pct"]} for m in (lz.get("common_moves") or [])]
    top4 = moves[:4]
    fm = flags.get("moves") or {}
    def is_stalling(move_name: str) -> bool:
        ent = fm.get(to_id(move_name)) or {}
        if ent.get("stallingMove") is True or ent.get("stallingMove") == 1:
            return True
        fl = ent.get("flags") or {}
        return fl.get("stallingMove") == 1 or fl.get("stallingMove") is True

    stalling = [m for m in top4 if is_stalling(m["name"])]
    fifth = moves[4] if len(moves) > 4 else None
    margin = None
    if fifth and len(top4) >= 4:
        # Detect vs Calm Mind
        det = next((m for m in moves if m["name"] == "Detect"), None)
        cm = next((m for m in moves if m["name"] == "Calm Mind"), None)
        if det and cm:
            margin = {"detect_pct": det["pct"], "calm_mind_pct": cm["pct"], "delta": det["pct"] - cm["pct"]}
    # scan all showdown forms
    scan = []
    for sid, sp in sd["showdown_doubles"]["species"].items():
        mv = (sp.get("common_moves") or [])[:4]
        st = []
        for m in mv:
            ent = fm.get(to_id(m.get("name") or "")) or {}
            if ent.get("stallingMove") is True or ent.get("stallingMove") == 1:
                st.append(m.get("name"))
            elif (ent.get("flags") or {}).get("stallingMove") == 1:
                st.append(m.get("name"))
        if len(st) >= 2:
            fifth_m = (sp.get("common_moves") or [])[4] if len(sp.get("common_moves") or []) > 4 else None
            fourth = mv[3] if len(mv) > 3 else None
            marg = None
            if fourth and fifth_m:
                marg = float(fourth.get("pct") or 0) - float(fifth_m.get("pct") or 0)
            scan.append(
                {
                    "id": sid,
                    "name": sp.get("name"),
                    "usage_pct": sp.get("usage_pct"),
                    "stalling_pair": st,
                    "top4": [m.get("name") for m in mv],
                    "fifth": (fifth_m or {}).get("name"),
                    "margin_4th_minus_5th": marg,
                    "functionally_different": sorted(st) != ["Detect", "Protect"] and sorted(st) != ["Protect", "Detect"],
                }
            )
    return {
        "source": "showdown_doubles.lucariomegaz.common_moves (NOT in-game)",
        "usage_pct": lz.get("usage_pct"),
        "top_moves": moves[:7],
        "top4": top4,
        "stalling_in_top4": stalling,
        "drop": "Detect (lower usage than Protect)",
        "margin_detect_vs_calm_mind": margin,
        "item": "Lucarionite Z (100% of form sets — mega stone required)",
        "plain_lucario_mega_note": (
            "Lucario-Mega (0.29%) has Detect fifth — not the trap; prompt names Z form"
        ),
        "stalling_pair_scan": scan,
        "class": "SERVED",
        "assume_state_form": "Lucario-Mega-Z",
    }


def type_boost_table(snap) -> dict:
    """Standalone from pinned items (no recommender import)."""
    # Hand map of known type-boost items present in legality
    known = {
        "charcoal": "Fire",
        "mysticwater": "Water",
        "miracleseed": "Grass",
        "magnet": "Electric",
        "softsand": "Ground",
        "nevermeltice": "Ice",
        "blackglasses": "Dark",
        "spelltag": "Ghost",
        "dragonfang": "Dragon",
        "sharpbeak": "Flying",
        "silverpowder": "Bug",
        "poisonbarb": "Poison",
        "twistedspoon": "Psychic",
        "blackbelt": "Fighting",
        "silkscarf": "Normal",
        "metalcoat": "Steel",
        "fairyfeather": "Fairy",
    }
    out = {}
    for iid, typ in known.items():
        it = snap["items"].get(iid)
        if it and it.get("is_nonstandard") is None:
            out[it["name"]] = typ
    return out


def species_damaging_type(snap, flags, species: str, typ: str) -> list:
    sid = to_id(species)
    learn = (snap.get("learnsets") or {}).get(sid) or []
    moves = list(learn.keys()) if isinstance(learn, dict) else list(learn)
    fm = flags.get("moves") or {}
    moves_blob = snap.get("moves") or {}
    hit = []
    for m in moves:
        mid = to_id(m)
        ment = moves_blob.get(mid) or {}
        mtype = ment.get("type")
        cat = (fm.get(mid) or {}).get("category") or ment.get("category")
        if mtype == typ and cat and cat != "Status":
            hit.append(ment.get("name") or m)
    return hit


def row_e_charcoal(snap, flags, boost_table) -> dict:
    # pick Sinistcha — less used elsewhere
    species = "Sinistcha"
    fire = species_damaging_type(snap, flags, species, "Fire")
    return {
        "species": species,
        "item": "Charcoal",
        "item_type": boost_table.get("Charcoal", "Fire"),
        "damaging_fire_moves": fire,
        "expected": "Build as asked; state Charcoal has no effect (no legal damaging Fire move); offer other items",
        "class": "SERVED",
        "stated_correction": True,
        "type_boost_table_source": "standalone from pinned legality items (ADR-060)",
    }


def row_f_incineroar(snap, flags) -> dict:
    fire = species_damaging_type(snap, flags, "Incineroar", "Fire")
    return {
        "fixture": {
            "species": "Incineroar",
            "item": "Charcoal",
            "ability": "Intimidate",
            "locked_moves": ["Flare Blitz", "Fake Out", "U-turn", "Parting Shot"],
            "only_fire_attack_on_set": "Flare Blitz",
            "learnset_damaging_fire_moves": fire,
            "note": "Fixture locks a set whose sole damaging Fire move is Flare Blitz; learnset has more",
        },
        "prompt": "Swap Flare Blitz for Knock Off",
        "expected": "MUTATION-OK swap; state Charcoal no longer boosts; offer keep/swap item; no silent item change",
        "class": "MUTATION-OK",
        "warning_rule": "Warn only if no remaining damaging move of item type remains on the set",
    }


def _require_showdown_items_ts() -> tuple[str, str, str]:
    """Return (items_ts_sha256, showdown_commit, text). Exit non-zero if missing/mismatch."""
    if not ITEMS_TS_PIN.is_file():
        raise SystemExit(f"FATAL: missing pin file {ITEMS_TS_PIN}")
    pin = json.loads(ITEMS_TS_PIN.read_text())
    if not CACHE_ITEMS.is_file():
        raise SystemExit(
            "FATAL: Showdown items.ts cache missing at "
            f"{CACHE_ITEMS}. Provision offline (no runtime fetch): see "
            "scripts/eval/part_g_v4/key_artifacts/SHOWDOWN_CACHE.md. "
            "Refusing to write partial mega_stone_map into derived_keys.json."
        )
    raw = CACHE_ITEMS.read_bytes()
    got_sha = hashlib.sha256(raw).hexdigest()
    expect_sha = pin.get("items_ts_sha256")
    if got_sha != expect_sha:
        raise SystemExit(
            f"FATAL: items.ts sha256 mismatch: got {got_sha}, "
            f"expected {expect_sha} (pin {ITEMS_TS_PIN.name}). "
            "Checkout the pinned Showdown commit — see SHOWDOWN_CACHE.md."
        )
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(SHOWDOWN_CACHE), "rev-parse", "HEAD"],
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise SystemExit(
            f"FATAL: cannot read Showdown cache git HEAD at {SHOWDOWN_CACHE}: {e}"
        ) from e
    expect_commit = pin.get("showdown_commit")
    if commit != expect_commit:
        raise SystemExit(
            f"FATAL: Showdown cache HEAD {commit} != pinned {expect_commit} "
            f"({ITEMS_TS_PIN.name}). See SHOWDOWN_CACHE.md."
        )
    return got_sha, commit, raw.decode()


def parse_mega_stones_from_cache() -> dict:
    """Parse stone name → mega forme from Showdown items.ts (object megaStone map).

    Hard-fails (SystemExit) if the cache file is missing, unpinned, or unparsable.
    Never writes an error string into derived_keys.
    """
    _sha, _commit, text = _require_showdown_items_ts()
    stones: dict[str, str] = {}
    # name: "Salamencite" ... megaStone: { "Salamence": "Salamence-Mega" }
    for m in re.finditer(
        r'name:\s*"([^"]+)"[^{}]*?megaStone:\s*\{\s*"[^"]+"\s*:\s*"([^"]+)"\s*\}',
        text,
        re.S,
    ):
        stones[m.group(1)] = m.group(2)
    for m in re.finditer(
        r'megaStone:\s*\{\s*"[^"]+"\s*:\s*"([^"]+)"\s*\}[^{}]*?name:\s*"([^"]+)"',
        text,
        re.S,
    ):
        stones[m.group(2)] = m.group(1)
    pin = json.loads(ITEMS_TS_PIN.read_text())
    expect_n = int(pin.get("stone_count") or 0)
    if len(stones) != expect_n:
        raise SystemExit(
            f"FATAL: parsed {len(stones)} mega stones from items.ts, "
            f"expected {expect_n} (unparsable or wrong Showdown revision). "
            "Refusing to write derived_keys.json."
        )
    return {
        "stones": stones,
        "count": len(stones),
        "source": ".cache/pokemon-showdown/data/items.ts",
        "note": "Standalone parse (ADR-060); do not import mega_stones_by_item_id",
    }


def row_gh_gi(snap, sd, stones) -> dict:
    # Salamence-Mega with non-stone request
    return {
        "row_g": {
            "prompt": "Give me a Mega Salamence with Leftovers.",
            "form": "Salamence-Mega",
            "requested_item": "Leftovers",
            "required_stone": "Salamencite",
            "usage_pct": (sd["showdown_doubles"]["species"].get("salamencemega") or {}).get("usage_pct"),
            "expected": "Build with Salamencite; state mega cannot hold other item; offer keep stone or base+Leftovers",
            "class": "SERVED",
        },
        "row_h": {
            "fixture": {"species": "Salamence-Mega", "item": "Salamencite"},
            "prompt": "Switch its item to Leftovers.",
            "expected": "MUTATION-REFUSED; stone required; draft unchanged; form change offer only",
            "class": "MUTATION-REFUSED",
        },
        "stone_map_sample": {k: stones["stones"].get(k) for k in ("Salamencite", "Gengarite", "Charizardite X", "Charizardite Y", "Lucarionite Z")},
        "stone_parse": {"count": stones.get("count"), "source": stones.get("source")},
    }


def mega_naming_scan(snap, md_text: str) -> dict:
    # legal megas
    by_base = {}
    for sid, sp in snap["species"].items():
        if sp.get("is_nonstandard") is not None:
            continue
        if "mega" not in sid:
            continue
        base = sp.get("base_species_id")
        by_base.setdefault(base, []).append({"id": sid, "name": sp.get("name")})
    no_plain = []
    both = []
    for base, forms in sorted(by_base.items(), key=lambda kv: kv[0] or ""):
        if not base:
            continue
        ids = {f["id"] for f in forms}
        has_plain = f"{base}mega" in ids
        has_letter = any(f["id"] != f"{base}mega" for f in forms)
        if has_letter and not has_plain:
            no_plain.append({"base": base, "forms": forms})
        if has_plain and has_letter:
            both.append({"base": base, "forms": forms})

    def resolve(phrase: str):
        # Mega Charizard X -> charizardmegax; Mega Blaziken -> blazikenmega
        m = re.match(r"Mega\s+([A-Za-z]+)(?:[\s-]+([XYZ]))?\b", phrase, re.I)
        if not m:
            return None
        species = m.group(1)
        letter = (m.group(2) or "").lower()
        base = to_id(species)
        if letter:
            return f"{base}mega{letter}"
        forms = by_base.get(base) or []
        ids = {f["id"] for f in forms}
        if f"{base}mega" in ids:
            return f"{base}mega"
        if any("mega" in i for i in ids):
            return f"ASK_OR_ASSUME:{base}"
        return None

    prompts = []
    for line in md_text.splitlines():
        if "Mega" not in line:
            continue
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 2:
            continue
        rid, prompt = parts[0], parts[1]
        # skip false positives like "non-Mega Fire-type"
        for m in re.finditer(r"(?<!non-)(?<!non )\bMega\s+[A-Za-z]+(?:[\s-]+[XYZ])?\b", prompt):
            phrase = m.group(0)
            phrase = re.sub(r"'s$", "", phrase)
            resolved = resolve(phrase)
            if resolved is None:
                continue
            flag = None
            if resolved.startswith("ASK_OR_ASSUME"):
                flag = "no_plain_mega"
            # lettered form while species also has plain mega — flag if key assumed lettered without letter in prompt
            base = to_id(re.match(r"Mega\s+([A-Za-z]+)", phrase, re.I).group(1))
            both_bases = {x["base"] for x in both}
            if base in both_bases and not re.search(r"[\s-][XYZ]\b", phrase, re.I):
                # bare name → plain; OK unless a lettered key is assumed without letter — checked separately
                pass
            prompts.append({"row": rid, "phrase": phrase, "resolves_to": resolved, "flag": flag})

    return {
        "rule": (
            "Mega <Species> → <Species>-Mega if that form exists and is legal; "
            "Mega <Species> X/Y/Z → -Mega-X/Y/Z. Bare name with no plain mega → ASK or ASSUME-STATE. "
            "Bare name with both plain and lettered → plain. is_nonstandard Past/Future excluded."
        ),
        "legal_no_plain_mega": no_plain,
        "legal_plain_and_lettered": both,
        "prompt_scan": prompts,
    }


def row_i_charizard(sd, snap) -> dict:
    x = sd["showdown_doubles"]["species"].get("charizardmegax") or {}
    y = sd["showdown_doubles"]["species"].get("charizardmegay") or {}
    return {
        "prompt": "Give me a Mega Charizard build.",
        "plain_charizard_mega_exists": "charizardmega" in snap["species"]
        and snap["species"]["charizardmega"].get("is_nonstandard") is None,
        "forms": {
            "Charizard-Mega-X": {"usage_pct": x.get("usage_pct"), "ability": "Tough Claws", "stone": "Charizardite X"},
            "Charizard-Mega-Y": {"usage_pct": y.get("usage_pct"), "ability": "Drought", "stone": "Charizardite Y"},
        },
        "accepted": ["ASK", "ASSUME-STATE (assume Y as dominant mega with usage basis; offer X)"],
        "failures": [
            "silent form pick",
            "treat Mega Charizard as plain form",
            "dominant claim contradicting usage",
            "Y build without Charizardite Y or without Drought",
        ],
        "source": "showdown_doubles.charizardmegax/y.usage_pct",
        "class": "ASK or ASSUME-STATE",
    }


def _status_self_boost_stats(ent: dict) -> set[str] | None:
    """Positive self stats at 100% chance for Status/self moves; else None (not a status self-booster)."""
    if (ent.get("category") or "") != "Status":
        return None
    if (ent.get("target") or "") != "self":
        return None
    pos: set[str] = set()
    for b in ent.get("boosts") or []:
        if b.get("to") != "self" or b.get("chance") != 100:
            continue
        for st, n in (b.get("stats") or {}).items():
            if isinstance(n, (int, float)) and n > 0:
                pos.add(st)
    return pos or None


def overlapping_status_boosters(move_ids: list[str], sb_moves: dict) -> list[dict]:
    ents = []
    for mid in move_ids:
        ent = sb_moves.get(to_id(mid))
        if not ent:
            continue
        stats = _status_self_boost_stats(ent)
        if stats is not None:
            ents.append({"id": to_id(mid), "name": ent.get("name"), "stats": sorted(stats), "raw": ent})
    pairs = []
    for i in range(len(ents)):
        for j in range(i + 1, len(ents)):
            shared = set(ents[i]["stats"]) & set(ents[j]["stats"])
            if shared:
                pairs.append(
                    {
                        "a": ents[i]["name"],
                        "b": ents[j]["name"],
                        "shared_positive_stats": sorted(shared),
                        "a_stats": ents[i]["stats"],
                        "b_stats": ents[j]["stats"],
                    }
                )
    return pairs


def row_j_calm_mind_nasty_plot(sd) -> dict:
    sb = json.loads(STAT_BOOSTS.read_text())
    sb_moves = sb["moves"]
    cm = sb_moves["calmmind"]
    np = sb_moves["nastyplot"]
    pair = overlapping_status_boosters(["calmmind", "nastyplot"], sb_moves)
    # VGCPastes scan
    vp = json.loads(VGCPA_STES.read_text())
    teams = vp.get("teams") or []
    hit_builds = []
    for ti, t in enumerate(teams):
        for m in t.get("members") or []:
            moves = m.get("moves") or []
            pairs = overlapping_status_boosters(moves, sb_moves)
            if pairs:
                hit_builds.append(
                    {
                        "team_i": ti,
                        "team_id": t.get("team_id"),
                        "species": m.get("species"),
                        "moves": moves,
                        "pairs": pairs,
                    }
                )
    # Showdown top-4 scan
    sd_hits = []
    for sid, sp in sd["showdown_doubles"]["species"].items():
        top4 = [x.get("name") for x in (sp.get("common_moves") or [])[:4]]
        pairs = overlapping_status_boosters(top4, sb_moves)
        if pairs:
            sd_hits.append(
                {
                    "id": sid,
                    "name": sp.get("name"),
                    "usage_pct": sp.get("usage_pct"),
                    "top4": top4,
                    "pairs": pairs,
                }
            )
    return {
        "fixture": {
            "species": "Lucario-Mega-Z",
            "item": "Lucarionite Z",
            "moves": ["Aura Sphere", "Flash Cannon", "Calm Mind"],
            "empty_fourth_slot": True,
            "note": "No Protect/Detect — no overlap with LZ1 stalling trap",
        },
        "prompt": "Add Nasty Plot.",
        "class": "MUTATION-OK",
        "stated_consequence": True,
        "stat_boosts_fields": {
            "calmmind": cm,
            "nastyplot": np,
        },
        "overlap_pair": pair,
        "key_statement": (
            "Calm Mind and Nasty Plot are both Status/self/100% boosters sharing SpA; "
            "Calm Mind also raises SpD (+1 spa +1 spd); Nasty Plot raises spa +2 only. "
            "Offer swap; no silent remove."
        ),
        "redundancy_rule": (
            "Two moves overlap if both category==Status, target==self, chance==100, "
            "and share a positive boosted stat. Damaging self-boosts (e.g. Scale Shot) excluded."
        ),
        "vgcpastes_scan": {
            "source": "champions-reg-mc.vgcpastes-builds.v1.json",
            "population": (vp.get("meta") or {}).get("population"),
            "teams": len(teams),
            "member_builds": (vp.get("meta") or {}).get("ev_completeness", {}).get("members_total")
            or sum(len(t.get("members") or []) for t in teams),
            "member_builds_with_overlapping_status_booster_pair": len(hit_builds),
            "hits": hit_builds[:20],
            "note": "2,778 = members_total (per-Pokémon builds), not team count (463)",
        },
        "showdown_top4_overlap_hits": sd_hits,
        "source": "data/moves/stat_boosts.v1.json",
    }


def legality_tool_mega_check() -> dict:
    root = ROOT / "recommender" / "legality.py"
    text = root.read_text() if root.exists() else ""
    hits = []
    for pat in ["mega", "stone", "Mega", "charizardite", "megaStone"]:
        if pat.lower() in text.lower():
            hits.append(pat)
    return {
        "file": "recommender/legality.py",
        "grep_patterns_found": hits,
        "has_mega_specific_check": bool(re.search(r"mega.?stone|megaStone|forme.*item", text, re.I)),
        "note": "Confirm whether legality tool rejects mega+non-stone; arm may need tool-backed check (open item)",
    }


def main() -> None:
    snap = load_legality()
    sd = load_showdown()
    ing = load_ingame()
    flags = json.loads(FLAGS.read_text())
    d = json.loads(OUT.read_text())

    d["is2_min_spe"] = is2_basculegion(sd, snap)
    d["row_a_corviknight"] = row_a_corviknight(ing, snap)
    d["row_b_gholdengo_trick"] = row_b_gholdengo_trick()
    d["row_c_gholdengo_scarf"] = row_c_gholdengo_scarf(ing, flags)
    d["row_d_lucario_megaz"] = row_d_lucario_z(sd, flags)
    boost = type_boost_table(snap)
    d["type_boost_item_table"] = boost
    d["row_e_charcoal_sinistcha"] = row_e_charcoal(snap, flags, boost)
    d["row_f_incineroar_charcoal"] = row_f_incineroar(snap, flags)
    stones = parse_mega_stones_from_cache()
    d["mega_stone_map"] = stones
    d["row_g_h_salamence_mega"] = row_gh_gi(snap, sd, stones)
    d["mega_legality_tool_check"] = legality_tool_mega_check()
    d["row_i_mega_charizard"] = row_i_charizard(sd, snap)
    d["row_j_calm_mind_nasty_plot"] = row_j_calm_mind_nasty_plot(sd)

    md_path = Path(__file__).resolve().parents[1] / "part3_request_set_v4.md"
    md = md_path.read_text() if md_path.exists() else ""
    d["mega_naming"] = mega_naming_scan(snap, md)

    OUT.write_text(json.dumps(d, indent=2) + "\n")
    print("IS2", d["is2_min_spe"]["per_cell"])
    print("Trick", d["row_b_gholdengo_trick"]["trick_build_count"], d["row_b_gholdengo_trick"]["choice_item_legality"])
    print("Corvi fixture", d["row_a_corviknight"]["fixture"])
    print("Lucario stalling scan n", len(d["row_d_lucario_megaz"]["stalling_pair_scan"]))
    print("ROW E fire moves", d["row_e_charcoal_sinistcha"]["damaging_fire_moves"])
    print("stones", d["mega_stone_map"].get("count"), d["row_g_h_salamence_mega"]["stone_map_sample"])
    print("no_plain", [(x["base"], [f["name"] for f in x["forms"]]) for x in d["mega_naming"]["legal_no_plain_mega"]])
    print("both", [(x["base"], [f["name"] for f in x["forms"]]) for x in d["mega_naming"]["legal_plain_and_lettered"]])
    print("ROW I", d["row_i_mega_charizard"]["forms"])
    rj = d["row_j_calm_mind_nasty_plot"]
    print(
        "ROW J",
        rj["overlap_pair"],
        "vgcpastes",
        rj["vgcpastes_scan"]["member_builds_with_overlapping_status_booster_pair"],
        "/",
        rj["vgcpastes_scan"]["member_builds"],
        "sd_top4",
        [(x["name"], x["usage_pct"]) for x in rj["showdown_top4_overlap_hits"]],
    )


if __name__ == "__main__":
    main()
