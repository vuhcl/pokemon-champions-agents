#!/usr/bin/env python3
"""Deterministic Part G v4 claim + false-legal battery generator (seed=0).

Eval-only. Reads pinned JSON under data/; no recommender imports.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

PKG = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PKG / "builders"))

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
# "usage" = in-game stratum, "usage_showdown" = Showdown-labeled Mega stratum, "ability_form" =
# form-conflation stratum. Every claim type except usage carries one slot per prompt.
TYPE_PLAN: list[tuple[str, int, int]] = [
    ("typing", 44, 1),
    ("ability", 32, 1),
    ("ability_form", 12, 1),
    ("item", 44, 1),
    ("legality", 35, 1),
    ("speed", 51, 1),
    ("damage", 51, 1),
    ("usage", 34, 2),
    ("usage_showdown", 10, 2),
    ("move_static", 35, 1),
]
CLAIM_ITEMS = sum(n for _, n, _ in TYPE_PLAN)
TOP_N = 5

# In-game species excluded from the usage draw, by id.
INGAME_USAGE_EXCLUDE = {
    "meowsticf": (
        "child forme of Meowstic; its in-game row is Mega-dominated (Meowsticite 97.5% of "
        "held items), so the row does not describe the forme asked about"
    ),
}

# Blobs the generator reads (paths relative to the repo root); shas come from pins_manifest.json.
READ_BLOBS = (
    "data/legality/champions.v1.json",
    "data/usage/champions-reg-mc.ingame_doubles.v1.json",
    "data/usage/champions-reg-mc.showdown_doubles.v1.json",
    "data/moves/static.v1.json",
)
ITEMS_TS_PIN = PKG / "key_artifacts" / "showdown_items_ts.pin.json"


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


def pre_mega_id(snap_species: dict, mega_id: str) -> str | None:
    """Pre-Mega forme id: the Mega name minus its -Mega suffix when that is a legality species."""
    name = snap_species[mega_id]["name"]
    stem = to_id(re.sub(r"-Mega(-[XYZ])?$", "", name))
    for cand in (stem, snap_species[mega_id].get("base_species_id")):
        if cand in snap_species and any(snap_species[cand].get("abilities", {}).values()):
            return cand
    return None


def own_abilities(snap_species: dict, sid: str) -> list[str]:
    return [v for v in snap_species[sid]["abilities"].values() if v]


def form_conflation_pool(snap: dict) -> tuple[list[dict], list[dict]]:
    """Legal Mega forms with a False-case ability (base ability not in the Mega's own list)."""
    sp = snap["species"]
    ok, skipped = [], []
    for mid in sorted(sp):
        s = sp[mid]
        if s.get("is_nonstandard") is not None or not re.search(r"-Mega($|-)", s["name"]):
            continue
        pre = pre_mega_id(sp, mid)
        if pre is None:
            skipped.append({"form": mid, "reason": "no pre-Mega forme with abilities in legality"})
            continue
        m_list = own_abilities(sp, mid)
        false_pool = [a for a in own_abilities(sp, pre) if a not in m_list]
        rec = {"form": mid, "pre_mega": pre, "form_abilities": m_list, "false_pool": false_pool}
        if false_pool:
            ok.append(rec)
        else:
            skipped.append({**rec, "reason": "every pre-Mega ability is in the Mega's own list"})
    return ok, skipped


def showdown_stratum(snap: dict, ingame_ids: set[str], sd_species: dict) -> dict[str, Any]:
    """Admit Showdown rows with no in-game row under four checks; split by usage_pct median."""
    sp, items = snap["species"], snap["items"]
    legal_item_names = {v["name"] for v in items.values() if v.get("is_nonstandard") is None}
    admitted, rejected = [], []
    for sid in sorted(set(sd_species) - ingame_ids):
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
        if not row["common_items"] or row["common_items"][0]["name"] not in legal_item_names:
            reasons.append("top-listed item missing or not a legal item")
        if (row.get("teammates_meta") or {}).get("status") != "available":
            reasons.append("teammates_meta.status is not available")
        (rejected if reasons else admitted).append((sid, reasons))
    order = sorted((sid for sid, _ in admitted), key=lambda s: (-sd_species[s]["usage_pct"], s))
    half = len(order) // 2
    return {
        "candidates": len(admitted) + len(rejected),
        "admitted": [sid for sid, _ in admitted],
        "rejected": [{"id": sid, "reasons": r} for sid, r in rejected],
        "upper": order[:half],
        "lower": order[half:],
        "split_rule": (
            "admitted rows sorted by showdown usage_pct descending (ties by id); "
            "upper = first floor(n/2), lower = the rest; the blob has no rank field"
        ),
    }


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

    damaging_moves = [
        mid
        for mid in move_ids
        if move_field(mid, "category") in ("Physical", "Special")
        and int(move_field(mid, "basePower")) > 0
    ]
    if not damaging_moves:
        raise SystemExit("no damaging moves found in the legality blob")

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
    top_u = [r for r in top_q if r[0] not in INGAME_USAGE_EXCLUDE]
    bot_u = [r for r in bot_q if r[0] not in INGAME_USAGE_EXCLUDE]

    form_pool, form_skipped = form_conflation_pool(snap)
    sd_stratum = showdown_stratum(snap, set(ingame_species), sd_species)
    if len(sd_stratum["admitted"]) < 2:
        raise SystemExit("Showdown stratum has fewer than 2 admitted rows")

    templates = {
        "typing": ["Is {S} a {T} type?", "Does {S} have {T} typing?"],
        "ability": ["Does {S} have {A}?", "Is {A} legal on {S}?"],
        "ability_form": ["Does {M} have {A}?"],
        "item": ["Is {I} legal in Champions VGC?"],
        "legality": ["Is {S} legal?", "Can I use {S} in Champions VGC?"],
        "speed": [
            "Does {S1} (Jolly, 32 Spe SP) outspeed {S2} (Timid, 32 Spe SP)?",
            "Who is faster: {S1} (Jolly, 32 Spe SP) or {S2} (Timid, 32 Spe SP)?",
        ],
        "damage": [
            "What damage does {S1}'s {M} do into {S2}?",
            "Does {S1}'s {M} OHKO {S2}?",
        ],
        "usage": ["What are the top 5 held items and top 5 teammates for {S} (in-game)?"],
        "usage_showdown": [
            "Who are the top 5 teammates and top 5 held items for {S} (Showdown)?"
        ],
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
            rec = rng.choice(form_pool)
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
            sid1, sp1 = rng.choice(leg_sp)
            sid2, sp2 = rng.choice(leg_sp)
            mid = rng.choice(damaging_moves)
            gt = {
                "attacker": sp1["name"],
                "defender": sp2["name"],
                "move": lmoves[mid]["name"],
                "move_id": mid,
                "move_category": lmoves[mid]["category"],
                "move_basePower": lmoves[mid]["basePower"],
                "move_type": lmoves[mid]["type"],
                "note": "score via calc under explicit conditions; not asserted here",
                "requires_calc": True,
            }
            kind = "damage_range" if tmpl.startswith("What") else "ohko"
            return tmpl.format(S1=sp1["name"], S2=sp2["name"], M=gt["move"]), [(kind, gt)], tmpl
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
            half = sd_stratum["upper"] if i % 2 == 0 else sd_stratum["lower"]
            sid = rng.choice(half)
            row = sd_species[sid]
            name = sp_all[sid]["name"]
            held = [(x["name"], x["pct"]) for x in row["common_items"]]
            mates = sorted(row["teammates"], key=lambda t: (-t["conditional_pct"], t["rank"]))
            gt = {
                "species": name,
                "id": sid,
                "source": "showdown",
                "usage_half": "upper" if i % 2 == 0 else "lower",
                "usage_pct": row["usage_pct"],
                "common_items": key_with_ties(held),
                "teammates": key_with_ties([(t["name"], t["conditional_pct"]) for t in mates]),
            }
            return (
                tmpl.format(S=name),
                [("common_items", gt), ("teammates", gt)],
                tmpl,
            )
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
    return {
        "overlap_rejected_by_type": rejected,
        "schema": "part_g_v4_claim_battery",
        "seed": SEED,
        "n_items": len(items),
        "items": items,
        "claim_counts_by_type": claim_counts,
        "n_claims_total": sum(claim_counts.values()),
        "ground_truth_framing": "fidelity to pinned snapshot",
        "strata": {
            "ingame_usage_exclusions": INGAME_USAGE_EXCLUDE,
            "ingame_usage_quartile_size": len(top_q),
            "form_conflation": {
                "qualifying_forms": len(form_pool),
                "skipped_forms": form_skipped,
                "false_candidates": sum(len(r["false_pool"]) for r in form_pool),
                "true_candidates": sum(len(r["form_abilities"]) for r in form_pool),
            },
            "showdown_stratum": {
                "candidates": sd_stratum["candidates"],
                "admitted": len(sd_stratum["admitted"]),
                "rejected": sd_stratum["rejected"],
                "upper_n": len(sd_stratum["upper"]),
                "lower_n": len(sd_stratum["lower"]),
                "split_rule": sd_stratum["split_rule"],
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
        "Is {I} legal?",
        "Give me a set for {S} holding {I}.",
    ]
    for i in range(FALSE_LEGAL_ITEMS):
        mode = i % 3  # species-only / item-only / both
        if mode == 0:
            sid, sp = rng.choice(illeg_sp)
            sname = sp.get("name") or sid
            prompt = templates_ill[i % 2].format(S=sname, I="")
            gt = {"illegal_species": sname, "kind": "species_only"}
        elif mode == 1:
            iid, it = rng.choice(illeg_it)
            iname = it.get("name") or iid
            prompt = "Is {I} legal?".format(I=iname)
            gt = {"illegal_item": iname, "kind": "item_only"}
        else:
            sid, sp = rng.choice(illeg_sp)
            iid, it = rng.choice(illeg_it)
            sname, iname = sp.get("name") or sid, it.get("name") or iid
            prompt = templates_ill[3].format(S=sname, I=iname)
            gt = {"illegal_species": sname, "illegal_item": iname, "kind": "both"}
        items.append(
            {
                "id": f"false_legal_{i:03d}",
                "prompt": prompt,
                "ground_truth": gt,
                "score": "treats_illegal_as_usable → fail",
            }
        )

    controls = []
    for i in range(LEGAL_CONTROL_ITEMS):
        sid, sp = rng.choice(leg_sp)
        iid, it = rng.choice(leg_it)
        sname, iname = sp.get("name") or sid, it.get("name") or iid
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
        default=None,
        help="claim battery JSON; redraw items whose (type, kind, subject) matches it or an earlier item",
    )
    args = ap.parse_args()
    SEED = args.seed
    if SEED != 0 and args.out_dir is None:
        ap.error("--seed != 0 requires --out-dir (the default dir holds the frozen seed-0 battery)")
    rng = random.Random(SEED)
    avoid = json.loads(args.avoid_battery.read_text())["items"] if args.avoid_battery else None
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
        1.0 - (1.0 - answer_rate) ** int(it["n_claims"]) for it in claim["items"]
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
