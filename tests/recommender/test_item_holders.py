"""Tests for query_item_holders — expectations derived from usage JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from recommender.ids import to_id
from recommender.item_conditions import mega_stones_by_item_id, mega_locked_species_ids
from recommender.item_holders import (
    COMPLETE_FOOTER,
    format_item_holders_result,
    query_item_holders,
)
from recommender.legality import load_snapshot
from recommender.role_compendium_setup_constants import (
    _SETUP_PRESENCE_SHOWDOWN_WEIGHT_FLOOR,
)

REPO = Path(__file__).resolve().parents[2]
REG = "champions-reg-mc"
USAGE = REPO / "data" / "usage"


def _expected_showdown_top(iid: str, *, top_n: int = 5) -> list[str]:
    from recommender.legality import is_species_legal, load_snapshot

    snap = load_snapshot()
    path = USAGE / f"{REG}.showdown_doubles.v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    floor = float(_SETUP_PRESENCE_SHOWDOWN_WEIGHT_FLOOR)
    rows: list[tuple[float, str]] = []
    for sid, entry in (data.get("showdown_doubles") or {}).get("species", {}).items():
        if not is_species_legal(snap, sid):
            continue
        for it in entry.get("common_items") or []:
            if to_id(str(it.get("name") or "")) != iid:
                continue
            if "weight" not in it:
                break
            w = float(it["weight"])
            if w < floor:
                break
            rows.append((w, sid))
            break
    rows.sort(key=lambda t: (-t[0], t[1]))
    return [sid for _, sid in rows[:top_n]]


def _expected_ingame_top(iid: str, *, top_n: int = 5) -> list[str]:
    from recommender.legality import is_species_legal, load_snapshot

    snap = load_snapshot()
    path = USAGE / f"{REG}.ingame_doubles.v1.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[tuple[float, str]] = []
    for sid, entry in (data.get("ingame_doubles") or {}).get("species", {}).items():
        if not is_species_legal(snap, sid):
            continue
        for it in entry.get("common_items") or []:
            if to_id(str(it.get("name") or "")) != iid:
                continue
            rows.append((float(it.get("pct") or 0), sid))
            break
    rows.sort(key=lambda t: (-t[0], t[1]))
    return [sid for _, sid in rows[:top_n]]


def test_psychic_seed_observed_labels_and_rank():
    result = query_item_holders("Psychic Seed", regulation=REG)
    assert result.error is None
    text = format_item_holders_result(result)
    assert "In-game usage (held-item share on that species' top-10 list):" in text
    assert (
        "Showdown usage (ranked by item weight; pct = share of that species' sets):"
        in text
    )
    assert "Needs Psychic Terrain active" in text
    assert "Roost" not in text
    assert "roost" not in text.lower()
    assert "grounded" not in text.lower()
    assert "Also satisfy activation condition" not in text

    ingame = [h for h in result.observed if h.source == "ingame"]
    showdown = [h for h in result.observed if h.source == "showdown"]
    assert [h.species_id for h in ingame] == _expected_ingame_top("psychicseed")
    assert [h.species_id for h in showdown] == _expected_showdown_top("psychicseed")
    assert any(h.species_id == "corviknight" for h in result.observed)
    assert result.mechanical == ()


def test_type_boost_mechanical_never_outranks_observed():
    result = query_item_holders("Charcoal", regulation=REG)
    assert result.error is None
    text = format_item_holders_result(result)
    obs_ids = {h.species_id for h in result.observed}
    for m in result.mechanical:
        assert m.species_id not in obs_ids
        assert "type-boost" in m.condition_label
    if result.mechanical:
        assert "Also satisfy activation condition" in text
        assert text.index("Observed holders") < text.index(
            "Also satisfy activation condition"
        )


def test_resist_berry_occa():
    result = query_item_holders("Occa Berry", regulation=REG)
    assert result.error is None
    obs_ids = {h.species_id for h in result.observed}
    for m in result.mechanical:
        assert m.species_id not in obs_ids
        assert "weak to Fire" in m.condition_label


def test_chilan_no_tier_two():
    result = query_item_holders("Chilan Berry", regulation=REG)
    assert result.error is None
    assert result.mechanical == ()
    text = format_item_holders_result(result)
    assert "no species is weak to Normal" in text


def test_venusaurite_mega_lock():
    snap = load_snapshot()
    locked = mega_locked_species_ids("venusaurite", snap)
    assert locked is not None
    assert locked  # forme present in snap
    result = query_item_holders("Venusaurite", regulation=REG)
    assert result.error is None
    assert result.mechanical == ()
    # MEGA_STONES maps Venusaurite; no additive list.
    assert "venusaurite" in mega_stones_by_item_id()


def test_mega_z_absolite_z_no_crash():
    """Mega-Z lock from MEGA_STONES only; item_mega_forme unused by this tool."""
    snap = load_snapshot()
    assert "absolitez" in mega_stones_by_item_id()
    locked = mega_locked_species_ids("absolitez", snap)
    assert locked is not None
    result = query_item_holders("Absolite Z", regulation=REG)
    assert result.error is None
    assert result.mechanical == ()
    text = format_item_holders_result(result)
    assert COMPLETE_FOOTER in text


def test_illegal_item_fail_closed():
    # Past Z-crystal still in snapshot
    result = query_item_holders("Psychium Z", regulation=REG)
    assert result.error is not None
    assert "isn't legal" in result.error


def test_unknown_item_error():
    result = query_item_holders("notarealitemxyz", regulation=REG)
    assert result.error is not None


def test_regulation_required_and_exact_tag_writeups(tmp_path, monkeypatch):
    with pytest.raises(TypeError):
        query_item_holders("Life Orb")  # type: ignore[call-arg]

    import recommender.item_holders as ih

    monkeypatch.setattr(ih, "RESOLVED_BUILDS_DIR", tmp_path)
    monkeypatch.setattr(ih, "TEAM_COMP_DIR", tmp_path)
    # Missing current-tag files → empty vgcpastes/writeup, not prior-reg fill.
    result = query_item_holders("Psychic Seed", regulation=REG)
    assert result.error is None
    assert not any(h.source == "writeup" for h in result.observed)
    assert not any(h.source == "vgcpastes" for h in result.observed)


def test_callable_read_only_no_ladder_mutation():
    from recommender.usage_data import showdown_species_map

    before = showdown_species_map(REG)
    sid = next(iter(before))
    before_items = list((before[sid].get("common_items") or []))
    query_item_holders("Life Orb", regulation=REG)
    after = showdown_species_map(REG)
    assert list((after[sid].get("common_items") or [])) == before_items
