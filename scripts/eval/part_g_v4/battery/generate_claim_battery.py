#!/usr/bin/env python3
"""Deterministic Part G v4 claim + false-legal battery generator (seed=0).

Eval-only. Reads pinned JSON under data/; no recommender imports.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

PKG = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PKG / "builders"))

sys.path.insert(0, str(PKG / "checks"))
from check_item_stratum import disagreements as item_stratum_disagreements  # noqa: E402
from _lib import (  # noqa: E402
    champions_spe,
    is_legal_species,
    load_ingame,
    load_legality,
    load_showdown,
    to_id,
)

SEED = 0
FALSE_LEGAL_ITEMS = 240
LEGAL_CONTROL_ITEMS = 80

# (claim type, items, claim slots per item). About 1.15x the earlier 300-item plan.
# "usage" = in-game stratum (held items + teammates), "usage_showdown" = Showdown-labeled stratum
# (teammates only; Mega forms and mega-capable base forms), "ability_form" = form-conflation
# stratum. Every claim type except in-game usage carries one slot per prompt.
TYPE_PLAN: list[tuple[str, int, int]] = [
    ("typing", 44, 1),
    ("ability", 32, 1),
    ("ability_form", 12, 1),
    ("item", 44, 1),
    ("legality", 35, 1),
    ("speed", 51, 1),
    ("damage", 53, 1),
    ("usage", 34, 2),
    ("usage_showdown", 10, 1),
    ("move_static", 35, 1),
]
CLAIM_ITEMS = sum(n for _, n, _ in TYPE_PLAN)
TOP_N = 5

# In-game species excluded from the usage draw, by id: every mega-capable base form (a holder in
# the stone map of a legal Mega forme) plus the ids below.
INGAME_EXCLUDE_EXTRA = {
    "meowsticf": (
        "child forme of Meowstic; its in-game row is Mega-dominated (Meowsticite 97.5% of "
        "held items), so the row does not describe the forme asked about"
    ),
}
INGAME_EXCLUDE_MEGA_CAPABLE = (
    "mega-capable base form (holder in the Showdown stone map of a legal Mega forme): the in-game "
    "base-form row blends Mega-stone holders with other sets"
)

# Blobs the generator reads (paths relative to the repo root); shas come from pins_manifest.json.
READ_BLOBS = (
    "data/legality/champions.v1.json",
    "data/usage/champions-reg-mc.ingame_doubles.v1.json",
    "data/usage/champions-reg-mc.showdown_doubles.v1.json",
    "data/moves/static.v1.json",
)
ITEMS_TS_PIN = PKG / "key_artifacts" / "showdown_items_ts.pin.json"
STONE_MAP = PKG / "key_artifacts" / "stone_map.v1.json"
ITEM_STRATUM = Path(__file__).resolve().parent / "item_stratum.json"
DAMAGE_POOL = PKG / "key_artifacts" / "battery_damage_pool.json"
DEFENDER_CAP = 2  # a defensive-equivalence group (identical types and base stats) appears in at most this many damage items per battery
TYPE_CHART = PKG / "key_artifacts" / "type_chart.v1.json"
CALC_RULES = PKG / "key_artifacts" / "calc_move_rules.v1.json"
MOVE_CONDITIONALS = PKG / "key_artifacts" / "move_conditionals.v1.json"
STONE_SHARE_LIMIT_PCT = 0.5  # Showdown base-form rows: max total pct of Mega stones among listed items


class Redraw(Exception):
    """Raised inside an item draw to discard it and draw again at the same index."""


def canonical_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def read_pins() -> list[dict[str, str]]:
    """Pin records for READ_BLOBS from pins_manifest.json; fail if a file differs from its pin."""
    manifest = json.loads((PKG / "pins_manifest.json").read_text())
    by_path = {p["path"]: p for p in manifest["pins"]}
    out = []
    for rel in READ_BLOBS:
        pin = by_path[rel]
        actual = git_blob_sha(ROOT / rel)
        if actual != pin["git_blob_sha"]:
            raise SystemExit(f"{rel}: git blob {actual} != pinned {pin['git_blob_sha']}")
        out.append({"path": rel, "git_blob_sha": pin["git_blob_sha"], "content_sha256": pin["content_sha256"]})
    return out


def legal_species(snap: dict) -> list[tuple[str, dict]]:
    out = []
    for sid, sp in (snap.get("species") or {}).items():
        if is_legal_species(sp):
            out.append((sid, sp))
    out.sort(key=lambda x: x[0])
    return out


def illegal_species(snap: dict) -> list[tuple[str, dict]]:
    out = []
    for sid, sp in (snap.get("species") or {}).items():
        if not is_legal_species(sp):
            out.append((sid, sp))
    out.sort(key=lambda x: x[0])
    return out


def legal_items(snap: dict) -> list[tuple[str, dict]]:
    out = []
    for iid, it in (snap.get("items") or {}).items():
        if it.get("is_nonstandard") is None:
            out.append((iid, it))
    out.sort(key=lambda x: x[0])
    return out


def illegal_items(snap: dict) -> list[tuple[str, dict]]:
    out = []
    for iid, it in (snap.get("items") or {}).items():
        if it.get("is_nonstandard") is not None:
            out.append((iid, it))
    out.sort(key=lambda x: x[0])
    return out


def load_moves_static() -> dict:
    return json.loads((ROOT / "data/moves/static.v1.json").read_text())


def quartile_split(species_rows: list[tuple[str, int]], rng: random.Random) -> tuple[list, list]:
    """Top and bottom usage quartile; rows are (species id, usage_rank), rank 1 = most used."""
    rows = sorted(species_rows, key=lambda x: (x[1], x[0]))
    n = len(rows)
    if n < 8:
        raise SystemExit(f"in-game blob has {n} ranked species; need >= 8 for quartiles")
    top = rows[: n // 4]
    bot = rows[-(n // 4) :]
    rng.shuffle(top)
    rng.shuffle(bot)
    return top, bot


def key_with_ties(entries: list[tuple[str, float]], n: int = TOP_N) -> list[str]:
    """First n names of a pct-descending list, plus every later entry tied with the n-th."""
    pcts = [p for _, p in entries]
    if pcts != sorted(pcts, reverse=True):
        raise SystemExit("list is not sorted by descending pct")
    k = min(n, len(entries))
    while 0 < k < len(entries) and entries[k][1] == entries[n - 1][1]:
        k += 1
    return [name for name, _ in entries[:k]]


# Entities named in the prompt, per claim type (ground-truth field names).
_SUBJECT_FIELDS = {
    "typing": ("species", "asked_type"),
    "ability": ("species", "asked_ability"),
    "ability_form": ("form", "asked_ability"),
    "item": ("item",),
    "item_stratum": ("item",),
    "legality": ("species",),
    "speed": ("s1", "s2"),
    "damage": ("attacker", "defender", "move"),
    "usage": ("species",),
    "usage_showdown": ("species",),
    "move_static": ("move",),
}


def item_keys(entry: dict[str, Any]) -> set[tuple[str, str, str]]:
    """(claim type, claim kind, subject entity) for each claim of an item.

    Speed pairs are unordered ("who is faster" is symmetric).
    """
    ctype = entry["claim_type"]
    keys = set()
    for c in entry["claims"]:
        gt = c["ground_truth"]
        names = [str(gt.get(f, "")) for f in _SUBJECT_FIELDS[ctype]]
        if ctype == "speed":
            names.sort()
        keys.add((ctype, c["kind"], "|".join(names)))
    return keys


def own_abilities(snap_species: dict, sid: str) -> list[str]:
    return [v for v in snap_species[sid]["abilities"].values() if v]


def load_damage_pool(snap_pins: list[dict[str, str]]) -> dict:
    """Calc-labeled damage pool; stale if any input it was built from has changed."""
    pool = json.loads(DAMAGE_POOL.read_text())
    meta = pool["meta"]
    manifest = json.loads((PKG / "pins_manifest.json").read_text())
    by_path = {p["path"]: p["git_blob_sha"] for p in manifest["pins"]}
    for p in meta["pins"]:
        if by_path.get(p["path"]) != p["git_blob_sha"]:
            raise SystemExit(f"damage pool is stale: {p['path']} changed since the pool was built")
    for key, path in (("stone_map_sha256", STONE_MAP), ("type_chart_sha256", TYPE_CHART), ("calc_rules_sha256", CALC_RULES), ("move_conditionals_sha256", MOVE_CONDITIONALS)):
        if hashlib.sha256(path.read_bytes()).hexdigest() != meta[key]:
            raise SystemExit(f"damage pool is stale: {path.name} changed since the pool was built")
    if manifest["calc_service"]["version"] != meta["calc_build"]:
        raise SystemExit("damage pool is stale: calc build changed")
    return pool


def load_stone_map() -> dict:
    return json.loads(STONE_MAP.read_text())


def mega_holders(snap: dict, stone_map: dict) -> dict[str, str]:
    """Legal Mega forme id -> holder id, from the stone map (not base_species_id)."""
    sp = snap["species"]
    out: dict[str, str] = {}
    for p in stone_map["pairs"]:
        m = sp.get(p["mega"])
        if m is None or m.get("is_nonstandard") is not None:
            continue
        if out.setdefault(p["mega"], p["holder"]) != p["holder"]:
            raise SystemExit(f"{p['mega']}: more than one holder in the stone map")
    named = {k for k, v in sp.items() if v.get("is_nonstandard") is None and re.search(r"-Mega($|-)", v["name"])}
    if named != set(out):
        raise SystemExit(f"legal Mega names and stone-map Megas differ: {sorted(named ^ set(out))}")
    for mid, hid in out.items():
        if hid not in sp or sp[hid].get("is_nonstandard") is not None or not own_abilities(sp, hid):
            raise SystemExit(f"{mid}: holder {hid!r} is not a legal species with abilities")
    return out


def form_conflation_pools(snap: dict, holders: dict[str, str]) -> tuple[list[dict], list[dict], dict]:
    """True forms (own list disjoint from the holder's) and False forms (a holder ability not in the
    Mega's own list), from the legality blob alone."""
    sp = snap["species"]
    true_forms, false_forms, overlap, no_false = [], [], [], []
    for mid in sorted(holders):
        pre = holders[mid]
        m_list, b_list = own_abilities(sp, mid), own_abilities(sp, pre)
        false_pool = [a for a in b_list if a not in m_list]
        rec = {"form": mid, "pre_mega": pre, "form_abilities": m_list, "false_pool": false_pool}
        if not set(m_list) & set(b_list):
            true_forms.append(rec)
        else:
            overlap.append(mid)
        if false_pool:
            false_forms.append(rec)
        else:
            no_false.append(mid)
    return true_forms, false_forms, {"not_disjoint_so_no_true_case": overlap, "no_false_case": no_false}


def showdown_strata(
    snap: dict, holders: dict[str, str], stone_names: set[str], sd_species: dict
) -> dict[str, Any]:
    """Showdown teammates strata: Mega forms and mega-capable base forms, each admitted by checks
    run on the blobs and split into upper/lower half by the row's usage_pct."""
    sp, items = snap["species"], snap["items"]
    legal_item_names = {v["name"] for v in items.values() if v.get("is_nonstandard") is None}

    def check(sid: str, kind: str) -> list[str]:
        row = sd_species[sid]
        reasons = []
        ent = sp.get(sid)
        if ent is None or ent.get("is_nonstandard") is not None:
            reasons.append("no legal legality row for this exact id")
        else:
            legal_ab = set(own_abilities(sp, sid))
            bad = [a["name"] for a in row["common_abilities"] if a["name"] not in legal_ab]
            if bad:
                reasons.append(f"abilities not legal for this id: {bad}")
        if kind == "mega":
            if not row["common_items"] or row["common_items"][0]["name"] not in legal_item_names:
                reasons.append("top-listed item missing or not a legal item")
        else:
            share = sum(x["pct"] for x in row["common_items"] if x["name"] in stone_names)
            if share > STONE_SHARE_LIMIT_PCT:
                reasons.append(f"Mega-stone share of listed items {share:.2f}% > {STONE_SHARE_LIMIT_PCT}%")
        if (row.get("teammates_meta") or {}).get("status") != "available":
            reasons.append("teammates_meta.status is not available")
        return reasons

    out: dict[str, Any] = {}
    for kind, ids in (("mega", sorted(holders)), ("base", sorted(set(holders.values())))):
        admitted, rejected, no_row = [], [], []
        for sid in ids:
            if sid not in sd_species:
                no_row.append(sid)
                continue
            reasons = check(sid, kind)
            (rejected if reasons else admitted).append((sid, reasons))
        order = sorted((sid for sid, _ in admitted), key=lambda x: (-sd_species[x]["usage_pct"], x))
        half = len(order) // 2
        out[kind] = {
            "candidates": len(admitted) + len(rejected),
            "no_showdown_row": no_row,
            "admitted": [sid for sid, _ in admitted],
            "rejected": [{"id": sid, "reasons": r} for sid, r in rejected],
            "upper": order[:half],
            "lower": order[half:],
        }
    out["split_rule"] = (
        "within each sub-stratum, admitted rows sorted by the row's Showdown usage_pct descending "
        "(ties by id); upper = first floor(n/2), lower = the rest; the blob has no rank field"
    )
    return out


def build_claim_battery(
    rng: random.Random, avoid: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    snap = load_legality()
    ingame = load_ingame()
    sd = load_showdown()
    static = load_moves_static()
    sp_all = snap["species"]
    lmoves = snap["moves"]
    ingame_species = ingame["ingame_doubles"]["species"]
    sd_species = sd["showdown_doubles"]["species"]

    move_ids = sorted(static["moves"])
    for mid in move_ids:
        if mid not in lmoves:
            raise SystemExit(f"static move {mid!r} has no row in the legality blob")

    def move_field(mid: str, field: str):
        v = lmoves[mid].get(field)
        if v is None or v == "":
            raise SystemExit(f"legality moves[{mid!r}].{field} is null or empty")
        return v

    def variable_power(mid: str) -> bool:
        return move_field(mid, "category") != "Status" and int(move_field(mid, "basePower")) == 0

    leg_sp = legal_species(snap)
    illeg_sp = illegal_species(snap)
    leg_it = legal_items(snap)
    illeg_it = illegal_items(snap)
    all_types = sorted({t for _, s in leg_sp for t in s["types"]})
    all_abilities = sorted({a for sid, _ in leg_sp for a in own_abilities(sp_all, sid)})

    usage_rows: list[tuple[str, int]] = []
    for sid, row in ingame_species.items():
        if row.get("usage_rank") is None or not row.get("name"):
            raise SystemExit(f"in-game row {sid!r} lacks usage_rank or name")
        usage_rows.append((sid, int(row["usage_rank"])))
    top_q, bot_q = quartile_split(usage_rows, rng)

    stone_map = load_stone_map()
    stone_names = {p["stone"] for p in stone_map["pairs"]}
    holders = mega_holders(snap, stone_map)
    mega_capable = sorted(set(holders.values()))
    ingame_excl: dict[str, str] = {}
    for hid in mega_capable:
        ingame_excl[hid] = INGAME_EXCLUDE_MEGA_CAPABLE
    for hid, why in INGAME_EXCLUDE_EXTRA.items():
        ingame_excl[hid] = (ingame_excl[hid] + "; " + why) if hid in ingame_excl else why
    top_u = [r for r in top_q if r[0] not in ingame_excl]
    bot_u = [r for r in bot_q if r[0] not in ingame_excl]
    n_usage = next(n for t, n, _ in TYPE_PLAN if t == "usage")
    for label, pool, need in (("top", top_u, (n_usage + 1) // 2), ("bottom", bot_u, n_usage // 2)):
        if len(pool) < need:
            raise SystemExit(f"in-game {label} quartile pool has {len(pool)} species after exclusions; need {need}")
    in_game_stone_share = sorted(
        sum(x["pct"] for x in ingame_species[h]["common_items"] if x["name"] in stone_names)
        for h in mega_capable
        if h in ingame_species
    )

    true_forms, false_forms, form_notes = form_conflation_pools(snap, holders)
    if not true_forms or not false_forms:
        raise SystemExit("form-conflation stratum has no True or no False forms")
    sd_strata = showdown_strata(snap, holders, stone_names, sd_species)
    for sub in ("mega", "base"):
        if len(sd_strata[sub]["upper"]) < 2 or len(sd_strata[sub]["lower"]) < 2:
            raise SystemExit(f"Showdown {sub} sub-stratum has too few admitted rows")
    damage_pool = load_damage_pool(read_pins())
    by_kind: dict[str, list[dict]] = {}
    for e in damage_pool["entries"]:
        by_kind.setdefault(e["kind"], []).append(e)
    damage_kinds = [k for k, q in damage_pool["meta"]["quotas_per_battery"].items() for _ in range(q)]
    n_damage = next(n for t, n, _ in TYPE_PLAN if t == "damage")
    if len(damage_kinds) != n_damage:
        raise SystemExit(f"damage quotas sum to {len(damage_kinds)}, TYPE_PLAN says {n_damage}")
    damage_plan: list[str] = []  # shuffled lazily, at the first damage draw
    twin_pick: dict[str, str] = {}  # the M1/M2 twin shared by the two ability-modified items
    def defense_group(sid: str) -> tuple:
        """Defensive equivalence: identical types and base stats (so Squawkabilly colors are one group, a Mega form is not)."""
        sp = snap["species"][sid]
        return (tuple(sorted(sp["types"])), tuple(sorted(sp["base_stats"].items())))

    defender_drawn: collections.Counter = collections.Counter()  # defense group -> damage items so far
    defender_ids: list[str] = []
    stratum_doc = json.loads(ITEM_STRATUM.read_text())
    bad = item_stratum_disagreements(stratum_doc, snap)
    if bad:
        raise SystemExit("item_stratum.json disagrees with the legality blob:\n  " + "\n  ".join(bad))

    templates = {
        "typing": ["Is {S} a {T} type?", "Does {S} have {T} typing?"],
        "ability": ["Does {S} have {A}?", "Is {A} legal on {S}?"],
        "ability_form": ["Does {M} have {A}?"],
        "item": ["Is {I} legal as a held item in Champions VGC?"],
        "legality": ["Is {S} legal?", "Can I use {S} in Champions VGC?"],
        "speed": [
            "Does {S1} (Jolly, 32 Spe SP) outspeed {S2} (Timid, 32 Spe SP)?",
            "Who is faster: {S1} (Jolly, 32 Spe SP) or {S2} (Timid, 32 Spe SP)?",
        ],
        "damage": [
            "{S1}{A1} uses {M} on {S2}{A2}. Attacker: level 50, {NAT} nature, {ASP}, no item. "
            "Defender: level 50, Hardy nature, 32 SP in HP and 0 SP in Attack, Defense, Special Attack, "
            "Special Defense and Speed, no item. Both start at full HP with no stat changes or status; "
            "no weather, terrain, screens or other field effects; a single target; no critical hit. "
            "Assuming the move hits, does this guarantee a KO, that is, does every one of the 16 damage "
            "rolls knock the defender out?{MEGA}"
        ],
        "usage": ["What are the top 5 held items and top 5 teammates for {S} (in-game)?"],
        "usage_showdown": ["Who are the top 5 teammates for {S} (Showdown)?"],
        "move_static": [
            ("What category is {M}?", "category"),
            ("What is the base power of {M}?", "base_power"),
            ("What type is {M}?", "move_type"),
        ],
    }
    claim_kind = {
        "typing": "has_type",
        "ability": "has_ability",
        "ability_form": "has_ability",
        "item": "item_legal",
        "legality": "species_legal",
    }

    seen: set[tuple[str, str, str]] = set()
    for a in avoid or []:
        seen |= item_keys(a)
    for e in stratum_doc["entries"]:  # the main item draws must not repeat a stratum prompt
        seen.add(("item", "item_legal", e["item"]))
    rejected = {t: 0 for t, _, _ in TYPE_PLAN}
    items: list[dict[str, Any]] = []
    claim_counts: dict[str, int] = {t: 0 for t, _, _ in TYPE_PLAN}

    def draw(ctype: str, i: int) -> tuple[str, list[tuple[str, dict]], str]:
        """One item draw: (prompt, [(kind, ground_truth), ...], template). May raise Redraw."""
        want_true = i % 2 == 0
        if ctype == "speed":
            # kind and pool cycle independently of the truth value, so each kind is balanced
            tmpl = templates[ctype][(i // 2) % 2]
        else:
            tmpl = rng.choice(templates[ctype])
        if ctype == "typing":
            sid, sp = rng.choice(leg_sp)
            types = list(sp["types"])
            t = rng.choice(types if want_true else [x for x in all_types if x not in types])
            gt = {"species": sp["name"], "asked_type": t, "types": types, "has_type": t in types}
            assert gt["has_type"] == want_true
            return tmpl.format(S=sp["name"], T=t), [(claim_kind[ctype], gt)], tmpl
        if ctype == "ability":
            sid, sp = rng.choice(leg_sp)
            abil = own_abilities(sp_all, sid)
            pool = abil if want_true else [x for x in all_abilities if x not in abil]
            if not pool:
                raise Redraw
            a = rng.choice(pool)
            gt = {"species": sp["name"], "asked_ability": a, "abilities": abil, "has_ability": a in abil}
            assert gt["has_ability"] == want_true
            return tmpl.format(S=sp["name"], A=a), [(claim_kind[ctype], gt)], tmpl
        if ctype == "ability_form":
            rec = rng.choice(true_forms if want_true else false_forms)
            m = sp_all[rec["form"]]
            a = rng.choice(rec["form_abilities"] if want_true else rec["false_pool"])
            gt = {
                "form": m["name"],
                "form_id": rec["form"],
                "pre_mega": sp_all[rec["pre_mega"]]["name"],
                "asked_ability": a,
                "form_abilities": rec["form_abilities"],
                "pre_mega_abilities": own_abilities(sp_all, rec["pre_mega"]),
                "has_ability": a in rec["form_abilities"],
            }
            assert gt["has_ability"] == want_true
            if not want_true:
                assert a not in rec["form_abilities"], "False key must not be in the form's own list"
            return tmpl.format(M=m["name"], A=a), [(claim_kind[ctype], gt)], tmpl
        if ctype == "item":
            iid, it = rng.choice(leg_it if want_true else illeg_it)
            gt = {"item": it["name"], "legal": it.get("is_nonstandard") is None}
            assert gt["legal"] == want_true
            return tmpl.format(I=it["name"]), [(claim_kind[ctype], gt)], tmpl
        if ctype == "legality":
            sid, sp = rng.choice(leg_sp if want_true else illeg_sp)
            gt = {"species": sp["name"], "legal": is_legal_species(sp)}
            assert gt["legal"] == want_true
            return tmpl.format(S=sp["name"]), [(claim_kind[ctype], gt)], tmpl
        if ctype == "speed":
            pool = top_q if (i // 4) % 2 == 0 else bot_q
            (s1, _), (s2, _) = rng.sample(pool, 2)

            def spes(a: str, b: str) -> tuple[int, int]:
                ba = int(sp_all[a]["base_stats"]["spe"])
                bb = int(sp_all[b]["base_stats"]["spe"])
                return champions_spe(ba, 32, "Jolly"), champions_spe(bb, 32, "Timid")

            e1, e2 = spes(s1, s2)
            if (e1 > e2) != want_true:
                s1, s2 = s2, s1
                e1, e2 = spes(s1, s2)
            if e1 == e2 or (e1 > e2) != want_true:
                raise Redraw
            n1, n2 = sp_all[s1]["name"], sp_all[s2]["name"]
            gt = {
                "s1": n1,
                "s2": n2,
                "spe1_jolly32": e1,
                "spe2_timid32": e2,
                "s1_outspeeds": e1 > e2,
                "condition": "s1 Jolly, s2 Timid, 32 Spe SP each; no Scarf/Tailwind",
            }
            kind = "outspeed" if tmpl.startswith("Does") else "faster"
            return tmpl.format(S1=n1, S2=n2), [(kind, gt)], tmpl
        if ctype == "damage":
            if not damage_plan:
                damage_plan.extend(damage_kinds)
                rng.shuffle(damage_plan)
            kind = damage_plan[i]
            cands = [
                e for e in by_kind[kind]
                if ("damage", "guaranteed_ko", "|".join((e["attacker"], e["defender"], e["move"]))) not in seen
                and (kind not in ("M1", "M2") or "twin" not in twin_pick or e["twin"] == twin_pick["twin"])
                and defender_drawn[defense_group(e["defender_id"])] < DEFENDER_CAP
            ]
            if not cands:
                dist = collections.Counter(e["defender_id"] for e in by_kind[kind])
                raise SystemExit(
                    f"damage kind {kind}: no pool entry left under the defender cap of {DEFENDER_CAP} per defensive group "
                    f"(already drawn: {dict(collections.Counter(defender_ids))}); pool defenders for this kind: {dict(dist)}"
                )
            e = rng.choice(cands)
            defender_drawn[defense_group(e["defender_id"])] += 1
            defender_ids.append(e["defender_id"])
            if kind in ("M1", "M2"):
                twin_pick.setdefault("twin", e["twin"])
            a = e["attrs"]
            gt = {
                "attacker": e["attacker"], "defender": e["defender"], "move": e["move"],
                "attacker_ability": e["attacker_ability"], "defender_ability": e["defender_ability"],
                "attacker_is_mega": e["attacker_is_mega"], "defender_is_mega": e["defender_is_mega"],
                "nature": e["nature"], "damage_kind": e["kind"], "twin": e.get("twin"),
                "guaranteed_ko": e["guaranteed_ko"], "rolls_ko_of_16": e["rolls_ko_of_16"],
                "min_roll": e["min_roll"], "max_roll": e["max_roll"], "hp": e["hp"], "rolls": e["rolls"],
                "calc_desc": e["desc"],
                "move_category": e["move_category"], "move_basePower": e["move_basePower"], "move_type": e["move_type"],
                "move_accuracy": a["accuracy"], "type_changed": a["type_changed"],
                "effectiveness": a["effectiveness"], "chart_effectiveness": a["chart_effectiveness"],
                "chart_exception": a["chart_exception"], "move_final_type": e["move_final_type"],
                "category_match": a["category_match"],
                "defender_bulk_quartile": a["defender_bulk_quartile"], "margin": a["margin"],
                "max_ratio": a["max_ratio"], "high_power": a["high_power"], "stab": a["stab"],
                "scoring": {
                    "yes_no_matches_guaranteed_ko": "TRUE",
                    "yes_no_contradicts_guaranteed_ko": "FALSE",
                    "numeric_chance_within_half_step_of_key": "TRUE",
                    "numeric_chance_outside_half_step": "FALSE",
                    "hedge_without_number": "no verdict",
                    "yes_no_and_chance_scored_separately": True,
                    "stated_conditions_differ_from_prompt": "UNVERIFIABLE",
                    "chance_key_percent": 100 * e["rolls_ko_of_16"] / 16,
                    "chance_step_points": 6.25,
                    "chance_tolerance_points": 3.125,
                },
            }
            if mega_pair := (e["attacker_is_mega"] or e["defender_is_mega"]):
                gt["scoring"]["stated_ability_differs_from_form_ability"] = "UNVERIFIABLE"
                gt["scoring"]["stated_ability_differs_from_form_ability_note"] = (
                    "damage claim only; the ability claim itself is scored FALSE by the ability item's own key"
                )
                gt["scoring"]["form_ability_used_by_key"] = {
                    "attacker": e["attacker_ability"] if e["attacker_is_mega"] else None,
                    "defender": e["defender_ability"] if e["defender_is_mega"] else None,
                }
            if e["move_category"] == "Physical":
                asp = "32 SP in Attack and 0 SP in HP, Defense, Special Attack, Special Defense and Speed"
            else:
                asp = "32 SP in Special Attack and 0 SP in HP, Attack, Defense, Special Defense and Speed"
            mega = e["attacker_is_mega"] or e["defender_is_mega"]
            prompt = tmpl.format(
                S1=e["attacker"], A1="" if e["attacker_is_mega"] else f" ({e['attacker_ability']})",
                M=e["move"], S2=e["defender"], A2="" if e["defender_is_mega"] else f" ({e['defender_ability']})",
                NAT=e["nature"], ASP=asp, MEGA=" Mega forms use their own single ability." if mega else "",
            )
            return prompt, [("guaranteed_ko", gt)], tmpl
        if ctype == "usage":
            pool = top_u if i % 2 == 0 else bot_u
            sid = rng.choice(pool)[0]
            row = ingame_species[sid]
            held = [(x["name"], x["pct"]) for x in row["common_items"]]
            gt = {
                "species": row["name"],
                "source": "in-game",
                "usage_rank": row["usage_rank"],
                "usage_half": "top quartile" if i % 2 == 0 else "bottom quartile",
                "common_items": key_with_ties(held),
                "common_items_listed": len(held),
                "teammates": list(row["teammates"][:TOP_N]),
            }
            return (
                tmpl.format(S=row["name"]),
                [("common_items", gt), ("teammates", gt)],
                tmpl,
            )
        if ctype == "usage_showdown":
            sub = "mega" if i % 2 == 0 else "base"
            j = i // 2
            half = "upper" if (j % 2 == 0) == (sub == "mega") else "lower"  # 5 upper / 5 lower overall
            sid = rng.choice(sd_strata[sub][half])
            row = sd_species[sid]
            name = sp_all[sid]["name"]
            mates = sorted(row["teammates"], key=lambda t: (-t["conditional_pct"], t["rank"]))
            gt = {
                "species": name,
                "id": sid,
                "source": "showdown",
                "substratum": "mega form" if sub == "mega" else "mega-capable base form",
                "usage_half": half,
                "usage_pct": row["usage_pct"],
                "teammates": key_with_ties([(t["name"], t["conditional_pct"]) for t in mates]),
            }
            return tmpl.format(S=name), [("teammates", gt)], tmpl
        # move_static
        tmpl_prompt, kind = tmpl
        mid = rng.choice(move_ids)
        if kind == "base_power" and variable_power(mid):
            raise Redraw
        field = {"category": "category", "base_power": "basePower", "move_type": "type"}[kind]
        move_field(mid, field)
        gt = {
            "move": lmoves[mid]["name"],
            "id": mid,
            "category": move_field(mid, "category"),
            "basePower": int(move_field(mid, "basePower")),
            "type": move_field(mid, "type"),
            "priority": static["moves"][mid].get("priority"),
            "target": static["moves"][mid].get("target"),
        }
        return tmpl_prompt.format(M=gt["move"]), [(kind, gt)], tmpl_prompt

    for ctype, n_items, n_slots in TYPE_PLAN:
        i = 0
        attempts = 0
        while i < n_items:
            try:
                prompt, claims, tmpl = draw(ctype, i)
            except Redraw:
                prompt = None
            entry: dict[str, Any] | None = None
            if prompt is not None:
                assert len(claims) == n_slots
                entry = {
                    "id": f"{ctype}_{i:03d}",
                    "claim_type": ctype,
                    "template": tmpl,
                    "prompt": prompt,
                    "claims": [
                        {"index": c, "kind": kind, "ground_truth": gt}
                        for c, (kind, gt) in enumerate(claims)
                    ],
                }
                entry["n_claims"] = len(entry["claims"])
                if item_keys(entry) & seen:
                    entry = None
            if entry is None:
                rejected[ctype] += 1
                attempts += 1
                if attempts > 2000:
                    raise SystemExit(f"{ctype}: pool too small to draw item {i} without a repeat")
                continue  # redraw this index (truth value and pools depend on i)
            seen |= item_keys(entry)
            claim_counts[ctype] += entry["n_claims"]
            items.append(entry)
            i += 1

    assert len(items) == CLAIM_ITEMS
    stratum_items = []
    # The hand-written stratum is held-out: dev batteries (seed != 0) omit it, but their main item
    # draws still avoid its prompts (see `seen` above).
    for k, e in enumerate(stratum_doc["entries"] if SEED == 0 else []):
        legal = e["expected"] == "legal"
        stratum_items.append(
            {
                "id": f"item_stratum_{k:03d}",
                "claim_type": "item_stratum",
                "gated": False,
                "template": templates["item"][0],
                "prompt": templates["item"][0].format(I=e["item"]),
                "claims": [
                    {
                        "index": 0,
                        "kind": "item_legal",
                        "ground_truth": {
                            "item": e["item"],
                            "legal": legal,
                            "list_source": e["source"],
                            "list_reason": e["reason"],
                        },
                    }
                ],
                "n_claims": 1,
            }
        )
    return {
        "overlap_rejected_by_type": rejected,
        "schema": "part_g_v4_claim_battery",
        "seed": SEED,
        "n_items": len(items),
        "n_items_item_stratum": len(stratum_items),
        "items": items + stratum_items,
        "claim_counts_by_type": claim_counts,
        "n_claims_total": sum(claim_counts.values()),
        "n_claims_item_stratum_ungated": len(stratum_items),
        "ground_truth_framing": "fidelity to pinned snapshot",
        "strata": {
            "ingame_usage_exclusions": {
                "rule": (
                    "exclude every mega-capable base form (holder of a legal Mega forme in the stone "
                    "map) and every id in extra_ids, by id"
                ),
                "mega_capable_reason": INGAME_EXCLUDE_MEGA_CAPABLE,
                "extra_ids": INGAME_EXCLUDE_EXTRA,
                "excluded_ids": sorted(ingame_excl),
                "mega_capable_with_in_game_row": len(in_game_stone_share),
                "mega_capable_stone_share_min_median_max_pct": [
                    in_game_stone_share[0],
                    in_game_stone_share[len(in_game_stone_share) // 2],
                    in_game_stone_share[-1],
                ],
                "quartile_size": len(top_q),
                "excluded_in_top_quartile": len(top_q) - len(top_u),
                "excluded_in_bottom_quartile": len(bot_q) - len(bot_u),
                "pool_after_exclusion": {"top": len(top_u), "bottom": len(bot_u)},
            },
            "form_conflation": {
                "mega_forms": len(holders),
                "true_forms": len(true_forms),
                "false_forms": len(false_forms),
                "true_candidates": sum(len(r["form_abilities"]) for r in true_forms),
                "false_candidates": sum(len(r["false_pool"]) for r in false_forms),
                **form_notes,
            },
            "showdown_strata": {
                sub: {
                    "candidates": sd_strata[sub]["candidates"],
                    "admitted": len(sd_strata[sub]["admitted"]),
                    "no_showdown_row": sd_strata[sub]["no_showdown_row"],
                    "rejected": sd_strata[sub]["rejected"],
                    "upper_n": len(sd_strata[sub]["upper"]),
                    "lower_n": len(sd_strata[sub]["lower"]),
                }
                for sub in ("mega", "base")
            }
            | {"split_rule": sd_strata["split_rule"], "stone_share_limit_pct": STONE_SHARE_LIMIT_PCT},
            "item_stratum": {
                "file": "battery/item_stratum.json",
                "sha256": hashlib.sha256(ITEM_STRATUM.read_bytes()).hexdigest(),
                "date": stratum_doc["date"],
                "entries": len(stratum_doc["entries"]),
                "legal": sum(1 for e in stratum_doc["entries"] if e["expected"] == "legal"),
                "illegal": sum(1 for e in stratum_doc["entries"] if e["expected"] == "illegal"),
                "gated": False,
            },
            "damage_pool": {
                "file": "key_artifacts/battery_damage_pool.json",
                "sha256": hashlib.sha256(DAMAGE_POOL.read_bytes()).hexdigest(),
                "calc_build": damage_pool["meta"]["calc_build"],
                "backend": damage_pool["meta"]["backend"],
                "selector_sha256": damage_pool["meta"]["selector_sha256"],
                "fixed_conditions": damage_pool["meta"]["fixed_conditions"],
                "cutoffs": damage_pool["meta"]["cutoffs"],
                "calc_rules_sha256": damage_pool["meta"]["calc_rules_sha256"],
                "move_conditionals_sha256": damage_pool["meta"]["move_conditionals_sha256"],
                "conditional_success_moves": sorted(v["name"] for v in damage_pool["meta"]["exclusions"]["conditional_success_moves"].values()),
                "usable_moves_below_100_accuracy": damage_pool["meta"]["usable_moves_below_100_accuracy"],
                "twins": damage_pool["meta"]["twins"],
                "resisted_but_guaranteed_ko_pairs_found": damage_pool["meta"]["resisted_but_guaranteed_ko_pairs_found"],
                "exclusions": damage_pool["meta"]["exclusions"],
                "type_chart_sha256": damage_pool["meta"]["type_chart_sha256"],
                "quotas_per_battery": damage_pool["meta"]["quotas_per_battery"],
                "defender_cap_per_group": DEFENDER_CAP,
                "defender_cap_group_key": "identical types and base stats",
                "defender_counts": {
                    "by_exact_species_id": dict(sorted(collections.Counter(defender_ids).items())),
                    "by_base_species_id": dict(sorted(collections.Counter(snap["species"][s].get("base_species_id") or s for s in defender_ids).items())),
                    "by_defense_group": {
                        "|".join(sorted(s for s in set(defender_ids) if defense_group(s) == grp)): n
                        for grp, n in sorted(defender_drawn.items(), key=lambda kv: sorted(s for s in set(defender_ids) if defense_group(s) == kv[0]))
                    },
                },
                "pool_sizes": damage_pool["meta"]["pool_sizes"],
            },
            "stone_map": {
                "file": "key_artifacts/stone_map.v1.json",
                "sha256": hashlib.sha256(STONE_MAP.read_bytes()).hexdigest(),
                "source": stone_map["source"],
                "pairs": len(stone_map["pairs"]),
            },
        },
    }


def build_false_legal(rng: random.Random) -> dict[str, Any]:
    snap = load_legality()
    illeg_sp = illegal_species(snap)
    illeg_it = illegal_items(snap)
    leg_sp = legal_species(snap)
    leg_it = legal_items(snap)
    items: list[dict[str, Any]] = []

    templates_ill = [
        "Can I use {S} in Champions VGC?",
        "Is {S} legal?",
        "Is {I} legal as a held item?",
        "Give me a set for {S} holding {I}.",
    ]
    seen_prompts: set[str] = set()
    redraws = {"items": 0, "controls": 0}
    for i in range(FALSE_LEGAL_ITEMS):
        mode = i % 3  # species-only / item-only / both
        for _attempt in range(1000):  # redraw on a repeated prompt
            if mode == 0:
                sid, sp = rng.choice(illeg_sp)
                sname = sp.get("name") or sid
                prompt = templates_ill[i % 2].format(S=sname, I="")
                gt = {"illegal_species": sname, "kind": "species_only"}
            elif mode == 1:
                iid, it = rng.choice(illeg_it)
                iname = it.get("name") or iid
                prompt = "Is {I} legal as a held item?".format(I=iname)
                gt = {"illegal_item": iname, "kind": "item_only"}
            else:
                sid, sp = rng.choice(illeg_sp)
                iid, it = rng.choice(illeg_it)
                sname, iname = sp.get("name") or sid, it.get("name") or iid
                prompt = templates_ill[3].format(S=sname, I=iname)
                gt = {"illegal_species": sname, "illegal_item": iname, "kind": "both"}
            if prompt not in seen_prompts:
                break
            redraws["items"] += 1
        else:
            raise SystemExit(f"false-legal item {i}: no unused prompt in 1000 draws")
        seen_prompts.add(prompt)
        items.append(
            {
                "id": f"false_legal_{i:03d}",
                "prompt": prompt,
                "ground_truth": gt,
                "score": "treats_illegal_as_usable → fail",
            }
        )

    controls = []
    seen_controls: set[str] = set()
    for i in range(LEGAL_CONTROL_ITEMS):
        for _attempt in range(1000):
            sid, sp = rng.choice(leg_sp)
            iid, it = rng.choice(leg_it)
            sname, iname = sp.get("name") or sid, it.get("name") or iid
            if f"Is {sname} legal holding {iname}?" not in seen_controls:
                break
            redraws["controls"] += 1
        else:
            raise SystemExit(f"legal control {i}: no unused prompt in 1000 draws")
        seen_controls.add(f"Is {sname} legal holding {iname}?")
        controls.append(
            {
                "id": f"legal_control_{i:03d}",
                "prompt": f"Is {sname} legal holding {iname}?",
                "ground_truth": {"species": sname, "item": iname, "legal": True},
                "score": "legal_treated_illegal → false-illegal (reported; not ≤2% gate)",
            }
        )

    return {
        "schema": "part_g_v4_false_legal_battery",
        "seed": SEED,
        "n_items": len(items),
        "n_legal_controls": len(controls),
        "prompt_redraws": redraws,
        "items": items,
        "legal_controls": controls,
    }


def main() -> int:
    global SEED
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument(
        "--avoid-battery",
        type=Path,
        nargs="+",
        default=None,
        help="claim battery JSON(s); redraw items whose (type, kind, subject) matches them or an earlier item",
    )
    args = ap.parse_args()
    SEED = args.seed
    if SEED != 0 and args.out_dir is None:
        ap.error("--seed != 0 requires --out-dir (the default dir holds the frozen seed-0 battery)")
    rng = random.Random(SEED)
    avoid = (
        [it for path in args.avoid_battery for it in json.loads(path.read_text())["items"]]
        if args.avoid_battery
        else None
    )
    claim = build_claim_battery(rng, avoid)
    # Separate RNG stream continuation is fine; false-legal uses same seed restart for stability
    rng_fl = random.Random(SEED + 1)
    false_legal = build_false_legal(rng_fl)

    out_dir = args.out_dir or PKG / "battery"
    out_dir.mkdir(parents=True, exist_ok=True)
    claim_path = out_dir / "claim_battery_v4.json"
    fl_path = out_dir / "false_legal_battery_v4.json"

    claim_text = canonical_dumps(claim)
    fl_text = canonical_dumps(false_legal)
    claim_hash = sha256_text(claim_text)
    fl_hash = sha256_text(fl_text)

    claim_path.write_text(claim_text)
    fl_path.write_text(fl_text)

    # Gate arithmetic is on *scored* claims (post-run), not designed slots.
    slots = claim["n_claims_total"]
    answer_rate = 0.70  # explicit pre-run assumption
    expected_scored = slots * answer_rate  # ≈267

    def binom_cdf_le(k: int, n_: int, p: float) -> float:
        from math import comb

        s = 0.0
        for i in range(k + 1):
            s += comb(n_, i) * (p**i) * ((1 - p) ** (n_ - i))
        return s

    def cp_upper(k: int, n_: int, alpha: float = 0.05) -> float:
        if n_ == 0:
            return 1.0
        if k >= n_:
            return 1.0
        if k < 0:
            return 0.0
        lo, hi = 0.0, 1.0
        for _ in range(120):
            mid = (lo + hi) / 2
            if binom_cdf_le(k, n_, mid) > alpha:
                lo = mid
            else:
                hi = mid
        return hi

    def max_k(n_: int, bound: float = 0.02) -> int:
        best = -1
        for k in range(0, n_ + 1):
            if cp_upper(k, n_) <= bound + 1e-15:
                best = k
            else:
                break
        return best

    def min_n(k: int, bound: float = 0.02) -> int:
        n_ = max(k + 1, 1)
        while cp_upper(k, n_) > bound + 1e-15:
            n_ += 1
        return n_

    staircase = {str(k): min_n(k) for k in range(0, 4)}
    design_floor = 240  # 1-failure threshold (236) + margin
    expected_scored_int = int(round(expected_scored))  # 267
    # Item scored iff ≥1 of its designed slots is answered.
    # Independence within an item: each designed slot answered iid with p=answer_rate.
    # → P(item scored | n_i) = 1 − (1−p)^{n_i}; E = Σ_i that probability.
    # (300×0.70=210 is a lower bound: ignores multi-slot items.)
    expected_scored_items_exact = sum(
        1.0 - (1.0 - answer_rate) ** int(it["n_claims"])
        for it in claim["items"]
        if it.get("gated", True)
    )
    expected_scored_items = int(round(expected_scored_items_exact))  # ~227
    item_tol = max_k(expected_scored_items)
    # Row-level secondary (request set; separate pool from battery items).
    # n_i = claim-type tokens on the row (split on +); same within-row iid slot model.
    request_md = (
        Path(__file__).resolve().parent.parent / "part3_request_set_v4.md"
    ).read_text(encoding="utf-8")
    row_ns: list[int] = []
    for line in request_md.splitlines():
        if not re.match(r"^\|\s*[A-Z]{1,3}\d+[a-z]?\s*\|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        ct = cells[5].strip().strip("`")
        if not ct or ct in ("—", "-", "–"):
            row_ns.append(1)
        else:
            row_ns.append(max(1, len([x for x in re.split(r"[+/]", ct) if x.strip()])))
    n_rows = len(row_ns)
    expected_scored_rows_exact = sum(
        1.0 - (1.0 - answer_rate) ** n for n in row_ns
    )
    expected_scored_rows = int(round(expected_scored_rows_exact))
    row_tol = max_k(expected_scored_rows)

    manifest = {
        "seed": SEED,
        "claim_battery_path": "battery/claim_battery_v4.json",
        "false_legal_battery_path": "battery/false_legal_battery_v4.json",
        "claim_battery_sha256": claim_hash,
        "false_legal_battery_sha256": fl_hash,
        "canonical_serialization": "json.dumps(sort_keys=True, separators=(',', ':')) + newline",
        "n_claim_items": claim["n_items"],
        "claim_slot_counts_by_type": claim["claim_counts_by_type"],
        "claim_slots_total": slots,
        "realized_definition": {
            "claim_slots": slots,
            "answer_rate_assumption": answer_rate,
            "expected_scored_claims": expected_scored,
            "expected_scored_claims_rounded": expected_scored_int,
            "formula": "expected_scored_claims = claim_slots × answer_rate",
            "note": (
                "Gate denominator = scored (model-authored) claims after a run, not claim slots. "
                f"{slots} slots × {answer_rate} ≈ {expected_scored_int} expected scored."
            ),
        },
        "gate": {
            "rule": (
                "one-sided 95% Clopper-Pearson UCB on false-claim rate ≤ 2%, "
                "on scored (model-authored) claims — not designed slots"
            ),
            "exact_min_scored_n_for_k_false": staircase,
            "prior_design_table": {"0": 149, "1": 237, "2": 314},
            "delta_vs_prior_design_table": {
                "0": 0,
                "1": staircase["1"] - 237,
                "2": staircase["2"] - 314,
                "note": "Exact binary-search CP is 1 below the prior table for k=1 and k=2",
            },
            "design_floor": design_floor,
            "design_floor_meaning": "1-failure threshold (236) + margin; stop/extend if scored < 240",
            "expected_scored_claims_at_70pct": expected_scored_int,
            "max_false_claims_passing_at_expected_scored": max_k(expected_scored_int),
            "answer_rate_tolerance_drops": {
                "below_rate_for_2_false": staircase["2"] / slots,
                "below_rate_for_1_false": staircase["1"] / slots,
                "below_rate_for_0_false_gate_fails": staircase["0"] / slots,
                "note": (
                    "If answer rate falls below these fractions of slots, "
                    "max false claims that still pass drops (2→1, 1→0, then even 0 fails)."
                ),
            },
            "answer_rate_note": (
                "70% is a pre-run assumption for sizing. The gate verdict uses actual "
                f"scored counts from the first run. Answer rate below ~{staircase['1'] / slots:.1%} "
                f"({staircase['1']}/{slots}) loses the 1-failure tolerance (0-only or extend)."
            ),
            "cluster_secondaries": {
                "does_not_replace_headline_gate": True,
                "headline_unchanged": (
                    "claim-level one-sided 95% Clopper-Pearson UCB ≤ 2% on scored claims"
                ),
                "item_level": {
                    "unit": "scored_battery_item",
                    "independence_assumption": (
                        "within an item, each designed claim slot is answered iid with "
                        f"p={answer_rate}; an item is scored if at least one slot is answered. "
                        "Items are treated as independent of each other for this secondary."
                    ),
                    "method": (
                        f"E[scored items] = Σ_i [1 − (1−p)^{{n_i}}] over the {claim['n_items']} "
                        f"generated items (seed {SEED}); p={answer_rate}. "
                        f"{claim['n_items']}×{answer_rate} is a lower bound "
                        f"(mean n_claims≈{slots / claim['n_items']:.2f})."
                    ),
                    "expected_scored_items_exact": round(expected_scored_items_exact, 4),
                    "expected_scored_items_at_70pct": expected_scored_items,
                    "gap_to_1_failure_threshold_236": staircase["1"]
                    - expected_scored_items,
                    "exact_min_scored_items_for_k_false": {
                        str(k): staircase[str(k)] for k in ("0", "1", "2")
                    },
                    "max_false_items_passing_at_expected_scored_items": item_tol,
                    "plain": (
                        f"At expected scored items ({expected_scored_items}), item-level "
                        f"tolerance is {item_tol} false items "
                        f"({staircase['1'] - expected_scored_items} below the 236 line for k=1)."
                    ),
                },
                "row_level": {
                    "unit": "scored_request_set_row",
                    "relationship_to_battery_items": (
                        f"The {claim['n_items']} claim-battery items are a separate eval pool from the "
                        "134 request-set rows — not one item per row, not repeated "
                        "phrasings of rows. Multi-turn request-set cases are one row each. "
                        "Request-set companions (AR3, IS2, build traps, H12/DM*) are "
                        "documented beside the battery, not in the battery item pool. "
                        "Battery items share no fixture_id with request-set rows; some "
                        "claim types reuse species/keys conceptually. Within a request-set "
                        "row, turns/claims share fixtures, keys, and assumptions."
                    ),
                    "independence_assumption": (
                        "within a row, each claim-type token (split on +) is answered iid "
                        f"with p={answer_rate}; a row is scored if at least one slot is "
                        "answered. Rows are treated as independent of each other for this "
                        "secondary."
                    ),
                    "method": (
                        "E[scored rows] = Σ_j [1 − (1−p)^{n_j}] over the 134 request-set "
                        "rows' claim-type token counts; "
                        f"p={answer_rate}. One-opportunity lower bound = 134×0.70≈94."
                    ),
                    "n_request_set_rows": n_rows,
                    "expected_scored_rows_exact": round(expected_scored_rows_exact, 4),
                    "expected_scored_rows_at_70pct": expected_scored_rows,
                    "one_opportunity_lower_bound": round(n_rows * answer_rate, 1),
                    "exact_min_scored_rows_for_k_false": {
                        str(k): staircase[str(k)] for k in ("0", "1", "2")
                    },
                    "max_false_rows_passing_at_expected_scored_rows": row_tol,
                    "can_demonstrate_2pct_bound_at_row_level": row_tol >= 0
                    and expected_scored_rows >= staircase["0"],
                    "plain": (
                        f"At expected scored rows (~{expected_scored_rows}), even 0 false "
                        f"rows cannot pass the CP≤2% bound (need ≥{staircase['0']} scored "
                        "for k=0). The request set cannot demonstrate the 2% bound at "
                        "row level under the 70% answer-rate assumption."
                    ),
                },
            },
            # Backward-compatible alias of item-level secondary
            "cluster_aware": {
                "unit": "scored_battery_item",
                "method": (
                    "E[scored items]=Σ[1−(1−p)^{n_i}] with within-item iid slot answers "
                    f"at p={answer_rate}; expected≈{expected_scored_items} "
                    f"({claim['n_items']}×{answer_rate} is the lower bound)"
                ),
                "expected_scored_items_at_70pct": expected_scored_items,
                "expected_scored_items_exact": round(expected_scored_items_exact, 4),
                "gap_to_236": staircase["1"] - expected_scored_items,
                "exact_min_scored_items_for_k_false": {
                    str(k): staircase[str(k)] for k in ("0", "1", "2")
                },
                "max_false_items_passing_at_expected_scored_items": item_tol,
                "stricter_than_headline": True,
                "plain": (
                    f"At expected scored items ({expected_scored_items}), item-level "
                    f"tolerance is {item_tol} false items; "
                    f"headline at expected scored claims ({expected_scored_int}) allows 1 false claim."
                ),
                "does_not_replace_headline_gate": True,
                "limitation": (
                    "headline assumes independent scored claims; "
                    "clustering by item/shared keys makes it optimistic"
                ),
            },
        },
        "held_out": SEED == 0,
        "frozen": SEED == 0,
        "tuning_forbidden": SEED == 0,
        "type_plan": [list(t) for t in TYPE_PLAN],
        "blobs_read": read_pins(),
        "items_ts_pin": {
            k: pin[k]
            for pin in [json.loads(ITEMS_TS_PIN.read_text())]
            for k in ("path", "items_ts_sha256", "showdown_commit")
        },
        "items_ts_use": (
            "item category counts in report_battery.py only; not read by this generator"
        ),
        "strata": claim["strata"],
        "item_stratum_slots_ungated": claim["n_claims_item_stratum_ungated"],
        "overlap_rejected_by_type": claim["overlap_rejected_by_type"],
    }
    (out_dir / "battery_manifest.json").write_text(canonical_dumps(manifest))
    print(
        json.dumps(
            {
                "claim_sha256": claim_hash,
                "claim_slots": slots,
                "expected_scored": expected_scored_int,
                "by_type": claim["claim_counts_by_type"],
                "gate": manifest["gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
