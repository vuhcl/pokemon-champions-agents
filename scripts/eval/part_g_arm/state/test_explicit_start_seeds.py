"""Explicit start-seed table (Vu 2026-10-30) + preflight + unchanged loaders."""

from __future__ import annotations

from recommender.slot_index import user_slot_to_index
from recommender.state import all_locked
from scripts.eval.part_g_arm.state.request_set_rows import (
    EXPLICIT_START_SEEDS,
    load_request_rows,
    resolve_start_state,
)


def _locked_species(state: dict, *, require_fully_locked: bool = True) -> dict[int, str]:
    out: dict[int, str] = {}
    for i, slot in enumerate(state["team_draft"]):
        if slot.species.value and slot.species.locked:
            out[i + 1] = slot.species.value
            if require_fully_locked:
                assert all_locked(slot), f"slot {i + 1} not fully locked"
    return out


def test_ms2_incineroar_slot1_fully_locked():
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["MS2"])
    assert meta["loaded"] and st
    assert _locked_species(st) == {1: "Incineroar"}
    assert st.get("pending_presentation") is None


def test_ms3_two_fully_locked():
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["MS3"])
    assert meta["loaded"] and st
    assert _locked_species(st) == {1: "Incineroar", 2: "Garchomp"}


def test_mr3_incineroar_slot1():
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["MR3"])
    assert meta["loaded"] and st
    assert _locked_species(st) == {1: "Incineroar"}


def test_mr4_two_locked_no_choice_scarf():
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["MR4"])
    assert meta["loaded"] and st
    assert _locked_species(st) == {1: "Incineroar", 2: "Garchomp"}
    for slot in st["team_draft"]:
        if slot.species.value:
            assert slot.item.value != "Choice Scarf"
            assert slot.item.value == "Sitrus Berry"


def test_mr5_garchomp_slot2_slot1_empty():
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["MR5"])
    assert meta["loaded"] and st
    assert _locked_species(st) == {2: "Garchomp"}
    s1 = st["team_draft"][user_slot_to_index(1)]
    assert s1.species.value is None and not s1.species.locked


def test_mu6_two_fully_locked():
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["MU6"])
    assert meta["loaded"] and st
    assert _locked_species(st) == {1: "Incineroar", 2: "Garchomp"}


def test_mw1_empty():
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["MW1"])
    assert meta["loaded"] and st
    assert _locked_species(st) == {}
    assert st.get("pending_presentation") is None


def test_mw2_two_fully_locked():
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["MW2"])
    assert meta["loaded"] and st
    assert _locked_species(st) == {1: "Incineroar", 2: "Garchomp"}


def test_mw4_cs_pending_nothing_locked():
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["MW4"])
    assert meta["loaded"] and st
    assert _locked_species(st) == {}
    pending = st.get("pending_presentation") or {}
    assert pending.get("kind") == "candidate_selection"
    opts = pending.get("options") or []
    assert len(opts) >= 2


def test_mt5_empty():
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["MT5"])
    assert meta["loaded"] and st
    assert _locked_species(st) == {}


def test_rb1_fixture_not_empty_team():
    rows = {r["id"]: r for r in load_request_rows()}
    st, meta = resolve_start_state(rows["RB1"])
    assert meta["loaded"] and st, meta
    assert "rb1_lucario" in (meta.get("source") or "")
    # Fixture leaves 4th move / nature / spread unlocked — species must be locked.
    locked = _locked_species(st, require_fully_locked=False)
    assert locked, "RB1 must not load empty_team"
    assert any("Lucario" in sp for sp in locked.values())
    s1 = st["team_draft"][0]
    assert s1.item.value == "Lucarionite Z"
    assert "Calm Mind" in (s1.moveset.value or [])


def test_explicit_start_preflight_sources():
    """Fails if an explicit-table row loads a different source family than expected."""
    rows = {r["id"]: r for r in load_request_rows()}
    expect_src = {
        "MS2": "explicit:build_fully_locked_slot(Incineroar@1)",
        "MS3": "explicit:Incineroar@1+Garchomp@2 fully locked",
        "MR3": "explicit:build_fully_locked_slot(Incineroar@1)",
        "MR4": "explicit:Incineroar@1+Garchomp@2 fully locked",
        "MR5": "explicit:build_fully_locked_slot(Garchomp@2)",
        "MU6": "explicit:Incineroar@1+Garchomp@2 fully locked",
        "MW1": "empty_team (explicit)",
        "MW2": "explicit:Incineroar@1+Garchomp@2 fully locked",
        "MW4": "explicit:seeds/cs_pending",
        "MT5": "empty_team (explicit)",
    }
    for rid, want in expect_src.items():
        _st, meta = resolve_start_state(rows[rid])
        assert meta.get("source") == want, (rid, meta.get("source"), want)
    _st, meta = resolve_start_state(rows["RB1"])
    assert (meta.get("source") or "").endswith("rb1_lucario_megaz_calmmind.json")


def test_unchanged_loaders_still_match():
    """The 14 rows that already matched their cells keep the same loader family."""
    rows = {r["id"]: r for r in load_request_rows()}
    # seed-backed
    for rid, seed in {
        "MS4": "fbc_pending",
        "MS7": "cs_pending",
        "MU7": "fbc_pending",
        "HC2": "hc2_after_t1",
        "MT3": "mt3_after_t1",
    }.items():
        _st, meta = resolve_start_state(rows[rid])
        assert meta["loaded"], rid
        assert seed in (meta.get("source") or "") or meta.get("seed") == seed, meta
    # fixture / OL
    for rid in ("H18b", "IC1", "OL2b", "OL4", "OL5", "OL6", "OL8", "OL9"):
        if rid not in rows:
            continue
        _st, meta = resolve_start_state(rows[rid])
        assert meta["loaded"], (rid, meta)
        src = meta.get("source") or ""
        assert "empty_team" not in src or rid == "skip", (rid, src)
    # MR6: none locked → empty_team (not in explicit table)
    _st, meta = resolve_start_state(rows["MR6"])
    assert meta["loaded"]
    assert "empty_team" in (meta.get("source") or "")


def test_explicit_set_covers_brief_rows():
    assert EXPLICIT_START_SEEDS == {
        "MS2",
        "MS3",
        "MR3",
        "MR4",
        "MR5",
        "MU6",
        "MW1",
        "MW2",
        "MW4",
        "MT5",
        "RB1",
    }
