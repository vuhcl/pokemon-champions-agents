"""tool_fields rung: find_species extras, get_speed mods, move fields, describe, show errors."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest

from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.describe_tool import describe
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot
from scripts.eval.part_g_arm.state.request_set_rows import (
    FROZEN_PROMPT_SHA256,
    load_request_rows,
    resolve_start_state,
)
from scripts.eval.part_g_arm.state.request_set_runner import (
    DEFAULT_RUN_FLAGS,
    TOOL_FIELDS_PROMPT_FILE,
    build_run_parameters,
    pin_hashes,
)
from scripts.eval.part_g_arm.state.tools import (
    combined_specs,
    enrich_get_speed,
    find_species,
    set_tool_fields,
    show_candidates,
    with_move_static_fields,
)
ROOT = Path(__file__).resolve().parents[4]
from scripts.eval.part_g_arm.state.errata_read import load_derived_keys_effective

KEYS = load_derived_keys_effective()
PRE_RS_ARM_TOOL_SCHEMA_SHA256 = "f0c97ad3b88cb3f118e241111bd454a4e86f7937cd4342f0969cadbe5049b845"


@pytest.fixture(autouse=True)
def _reset_flag():
    from scripts.eval.part_g_arm.state.tools import set_wrapper

    set_tool_fields(False)
    set_wrapper(False)
    yield
    set_tool_fields(False)
    set_wrapper(False)


def test_flags_off_still_pre_rs_arm_schema():
    set_tool_fields(False)
    cfg = ArmConfig(prompt_file="state/prompt.md")
    assert cfg.prompt_hash() == FROZEN_PROMPT_SHA256
    schema_sha = hashlib.sha256(
        json.dumps(combined_specs(), sort_keys=True).encode()
    ).hexdigest()
    assert schema_sha == PRE_RS_ARM_TOOL_SCHEMA_SHA256


def test_pair_seed_no_item_clause_duplicate():
    rows = {r["id"]: r for r in load_request_rows()}
    for rid in ("MS3", "MR4", "MU6", "MW2"):
        st, meta = resolve_start_state(rows[rid])
        assert meta["loaded"] and st
        items = [
            s.item.value
            for s in st["team_draft"]
            if s.item.value and s.item.locked
        ]
        assert len(items) == len(set(items)), (rid, items)
        assert "Choice Scarf" not in items
    # Slot2 default after fix
    st, _ = resolve_start_state(rows["MR4"])
    assert st["team_draft"][0].item.value == "Sitrus Berry"
    assert st["team_draft"][1].item.value == "Leftovers"


def test_additions_file_sha_in_pin_hashes(tmp_path: Path):
    add = tmp_path / "additions.json"
    add.write_text(
        json.dumps({"rows": [{"id": "MR5b", "turns": ["hi"]}]}) + "\n",
        encoding="utf-8",
    )
    pins = pin_hashes(additions_file=add)
    assert pins["additions_file_sha256"] == hashlib.sha256(add.read_bytes()).hexdigest()
    cfg = ArmConfig(prompt_file="state/prompt.md")
    rec = build_run_parameters(cfg, {"digest": "x"}, additions_file=add)
    assert rec["pin_hashes"]["additions_file_sha256"] == pins["additions_file_sha256"]


def test_find_species_truncated_and_within_n():
    set_tool_fields(True)
    st = empty_team()
    big = find_species(st, types=["Water"], n=20)
    assert big["status"] == "ok"
    assert big["legal_only"] is True
    assert big["total_matches"] > big["count"] == 20
    assert big["truncated"] is True
    small = find_species(st, types=["Water"], learns_move="Hurricane", n=50)
    assert small["status"] == "ok"
    assert small["truncated"] is False
    assert small["total_matches"] == small["count"]


def _base_spe(species: str, nature: str, spe_sp: int) -> int:
    from recommender.ids import to_id
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    base = int((snap["species"][to_id(species)]["base_stats"]["spe"]))
    n = 1.1 if nature in ("Jolly", "Timid", "Hasty", "Naive") else (
        0.9 if nature in ("Brave", "Relaxed", "Quiet", "Sassy") else 1.0
    )
    return math.floor(n * (base + spe_sp + 20))


def test_get_speed_hn2d_and_scarf_tw_keys():
    set_tool_fields(True)
    # HN2d
    bare = _base_spe("Blaziken-Mega", "Jolly", 32)
    assert bare == KEYS["hn2d_mega_blaziken"]["jolly_32"] == 167
    r = enrich_get_speed(
        {"status": "ok", "speed": bare, "species": "Blaziken-Mega"}, stage=1
    )
    assert r["speed"] == KEYS["hn2d_mega_blaziken"]["jolly_32_plus1"] == 250
    assert r["unmodified_speed"] == 167 and r["stage"] == 1
    # +1 then Scarf
    r2 = enrich_get_speed(
        {"status": "ok", "speed": bare}, stage=1, scarf=True
    )
    assert r2["speed"] == 375
    # negative stage
    r3 = enrich_get_speed({"status": "ok", "speed": 100}, stage=-1)
    assert r3["speed"] == math.floor(100 * 2 / 3)
    # refuse out of range
    bad = enrich_get_speed({"status": "ok", "speed": 100}, stage=7)
    assert bad["status"] == "error"

    # HN2b scarf / tw lines (Annihilape)
    for line in KEYS["hn2b_forward_grid"]["own_lines"]:
        nature, sp = line["nature"], line["spe_sp"]
        base = _base_spe("Annihilape", nature, sp)
        if line.get("kind") == "scarf":
            got = enrich_get_speed({"status": "ok", "speed": base}, scarf=True)
            assert got["speed"] == line["spe"], (line, got)
        else:
            assert base == line["spe"]
            got = enrich_get_speed({"status": "ok", "speed": base}, tailwind=True)
            assert got["speed"] == line["spe_tw"], (line, got)

    # IS3/IS4: effective keys (G7 errata) match floor-once scarf+TW
    for species, block in KEYS["is3_is4"].items():
        if species == "notes" or not isinstance(block, dict):
            continue
        if "plus_32" not in block:
            continue
        plus = block["plus_32"]
        assert _base_spe(species, "Jolly", 32) == plus or _base_spe(
            species, "Timid", 32
        ) == plus
        scarf = enrich_get_speed({"status": "ok", "speed": plus}, scarf=True)
        assert scarf["speed"] == block["plus_32_scarf"], (species, scarf, block)
        tw = enrich_get_speed(
            {"status": "ok", "speed": plus}, scarf=True, tailwind=True
        )
        assert tw["speed"] == block["plus_32_scarf_tw"] == math.floor(plus * 1.5 * 2), (
            species,
            tw,
            block,
        )

    # IS1 bare max Garchomp Jolly 32; scarf_beneficial Spe-at-n from key
    assert _base_spe("Garchomp", "Jolly", 32) == KEYS["is1_min_spe"]["bare_max_spe"] == 169
    assert KEYS["is1_min_spe"]["per_cell"][0]["scarf_beneficial"]["final_spe_at_n"] == 214
    # IS2 Basculegion Jolly Scarf Spe-32 → 214 (per_cell final_spe_at_n)
    bas = _base_spe("Basculegion", "Jolly", 32)
    got = enrich_get_speed({"status": "ok", "speed": bas}, scarf=True)
    assert got["speed"] == 214
    assert KEYS["is2_min_spe"]["per_cell"][0]["final_spe_at_n"] == 214


def test_get_speed_dragonite_vu_examples():
    """Vu worked examples: Jolly-32 Dragonite base 145 (pinned-calc-matched two-step)."""
    set_tool_fields(True)
    bare = _base_spe("Dragonite", "Jolly", 32)
    assert bare == 145
    none = enrich_get_speed({"status": "ok", "speed": bare})
    assert none["speed"] == 145
    scarf = enrich_get_speed({"status": "ok", "speed": bare}, scarf=True)
    assert scarf["speed"] == 217
    plus1 = enrich_get_speed({"status": "ok", "speed": bare}, stage=1)
    assert plus1["speed"] == 217
    plus1_scarf = enrich_get_speed(
        {"status": "ok", "speed": bare}, stage=1, scarf=True
    )
    assert plus1_scarf["speed"] == 325
    plus1_scarf_tw = enrich_get_speed(
        {"status": "ok", "speed": bare}, stage=1, scarf=True, tailwind=True
    )
    assert plus1_scarf_tw["speed"] == 651
    scarf_tw = enrich_get_speed(
        {"status": "ok", "speed": bare}, scarf=True, tailwind=True
    )
    assert scarf_tw["speed"] == 435
    assert math.floor(bare * 1.5) * 2 == 434  # wrong: floor after Scarf then ×TW
    # Paralysis after Scarf/TW chain (calc order): floor(speed/2)
    assert enrich_get_speed({"status": "ok", "speed": bare}, paralyzed=True)["speed"] == 72
    assert (
        enrich_get_speed({"status": "ok", "speed": bare}, scarf=True, paralyzed=True)[
            "speed"
        ]
        == 108
    )
    assert (
        enrich_get_speed(
            {"status": "ok", "speed": bare}, stage=1, scarf=True, paralyzed=True
        )["speed"]
        == 162
    )
    par_full = enrich_get_speed(
        {"status": "ok", "speed": bare},
        stage=1,
        scarf=True,
        tailwind=True,
        paralyzed=True,
    )
    assert par_full["speed"] == 325
    assert par_full["paralyzed"] is True
    note = (par_full.get("note") or "").lower()
    assert "quick feet" in note and "electric" in note
    assert "iron ball" in note and "unburden" in note


def test_get_move_static_mv2_mv3_fields():
    set_tool_fields(True)
    wish = with_move_static_fields(
        {"status": "ok", "move": "Wish", "type": "Normal", "category": "Status", "base_power": 0}
    )
    assert wish["pp"] == 8
    assert wish["priority"] == 0
    assert wish["target"] == "self"
    rock = with_move_static_fields(
        {
            "status": "ok",
            "move": "Rock Slide",
            "type": "Rock",
            "category": "Physical",
            "base_power": 75,
        }
    )
    assert rock["target"] == KEYS["mv3_rock_slide"]["target"] == "allAdjacentFoes"
    assert rock["accuracy"] == KEYS["mv3_rock_slide"]["accuracy"] == 90
    assert isinstance(rock["flags"], dict)


def test_show_candidates_refusal_cases():
    set_tool_fields(True)
    # no slot locked
    _, res = show_candidates(empty_team(), 1)
    assert "no slot locked" in str(res.get("slot_commit_error") or "").lower()
    assert "empty team" not in str(res.get("slot_commit_error") or "").lower()

    # partial lock (species only) — not all-locked
    from scripts.eval.part_g_arm.state.tools import lock_slot

    st, _ = lock_slot(empty_team(), 1, "Venusaur")
    _, res = show_candidates(st, 2)
    err = str(res.get("slot_commit_error") or "")
    assert "not fully locked" in err.lower()
    assert "empty team" not in err.lower()
    assert any(x in err.lower() for x in ("role", "moveset", "missing"))

    # wrong blank index
    st = build_fully_locked_slot("Venusaur", user_slot=1)
    _, res = show_candidates(st, 3)
    err = str(res.get("slot_commit_error") or "")
    assert "not the next open blank" in err.lower()
    assert "2" in err  # next is slot 2


def test_describe_cases_and_coverage():
    set_tool_fields(True)
    lo = describe("item", "Life Orb")
    assert lo["status"] == "ok" and lo["short_desc"]
    assert "source" in lo and lo["source"]["sha256"]
    mb = describe("move", "Moonblast")
    assert mb["status"] == "ok"
    assert any("secondary.chance" in x for x in mb.get("champions_overrides") or [])
    curse = describe("move", "Curse")
    assert curse.get("text_may_not_match") is True
    regen = describe("ability", "Regenerator")
    assert regen["status"] == "ok" and regen.get("champions_overrides")
    assert describe("item", "NotARealItemXYZ")["status"] == "not_found"

    # coverage: every legal item/move/ability has short_desc
    from recommender.ids import to_id
    from recommender.legality import is_item_legal, is_move_legal, is_species_legal, load_snapshot

    snap = load_snapshot()
    missing = []
    for iid, e in (snap.get("items") or {}).items():
        if not is_item_legal(snap, iid):
            continue
        r = describe("item", e["name"])
        if r.get("status") != "ok" or not r.get("short_desc"):
            missing.append(("item", e["name"], r.get("status")))
    for mid, e in (snap.get("moves") or {}).items():
        if not is_move_legal(snap, mid):
            continue
        r = describe("move", e["name"])
        if r.get("status") != "ok" or not r.get("short_desc"):
            missing.append(("move", e["name"], r.get("status")))
    ab_names: dict[str, str] = {}
    for sid, e in (snap.get("species") or {}).items():
        if not is_species_legal(snap, sid):
            continue
        for v in (e.get("abilities") or {}).values():
            if isinstance(v, str) and v.strip():
                ab_names.setdefault(to_id(v), v)
    for aname in ab_names.values():
        r = describe("ability", aname)
        if r.get("status") != "ok" or not r.get("short_desc"):
            missing.append(("ability", aname, r.get("status")))
    assert not missing, missing[:20]


def test_rules_registry_matches_flat_rules_and_f7():
    rules = json.loads(
        (ROOT / "data/legality/champions_rules.v1.json").read_text(encoding="utf-8")
    )
    flat = json.loads(
        (ROOT / "data/legality/champions.v1.json").read_text(encoding="utf-8")
    )["flat_rules"]
    texts = {e["text"] for e in rules["entries"]}
    for name in flat["ruleset"]:
        assert name in texts, name
    for name in flat["banlist"]:
        assert name in texts, name
    assert any("Bring 6 Pick 3-6" in e["text"] for e in rules["entries"])
    for e in rules["entries"]:
        assert e.get("source") and e["source"].get("path")
    by_id = {e["id"]: e for e in rules["entries"]}
    # Follow-up 7: Species/Item/Mythical/Restricted → validator; rest → none
    for rid in (
        "species_clause",
        "item_clause",
        "ban_mythical",
        "ban_restricted_legendary",
    ):
        assert by_id[rid]["enforced_by"] == "validator"
    for rid in (
        "adjust_level",
        "picked_team_size",
        "min_team_size",
        "team_preview",
        "nickname_clause",
        "obtainable",
        "cancel_mod",
        "bring_6_pick_3_6",
    ):
        assert by_id[rid]["enforced_by"] == "none"


def test_describe_rule_cases():
    set_tool_fields(True)
    sp = describe("rule", "Species Clause")
    assert sp["status"] == "ok"
    assert sp["text"] == "Species Clause"
    assert sp["enforced_by"] == "validator"
    assert "validator" in (sp.get("enforcement_note") or "").lower()
    assert sp["source"].get("path")
    ic = describe("rule", "Item Clause")
    assert ic["status"] == "ok" and ic["text"].startswith("Item Clause")
    myth = describe("rule", "Mythical")
    assert myth["status"] == "ok" and myth["enforced_by"] == "validator"
    rl = describe("rule", "Restricted Legendary")
    assert rl["status"] == "ok" and rl["id"] == "ban_restricted_legendary"
    bring = describe("rule", "Bring 6 Pick 3-6")
    assert bring["status"] == "ok"
    assert bring["enforced_by"] == "none"
    assert "not enforced" in (bring.get("enforcement_note") or "").lower()
    assert describe("rule", "NotARealRuleXYZ")["status"] == "not_found"


def test_tool_fields_prompt_sha_distinct():
    cfg = ArmConfig(prompt_file=TOOL_FIELDS_PROMPT_FILE)
    h = cfg.prompt_hash()
    assert h != FROZEN_PROMPT_SHA256
    assert h == "911845a631e165f3162f901cee1d3580860205860508e7c6c126be97b53c135d"
