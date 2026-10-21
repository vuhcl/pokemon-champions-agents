"""Offline tests for the MetaRoll in-game extractor (fixture trimmed from a real all.json)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from recommender.ids import to_id
from recommender.legality import load_snapshot
from scripts.extract_usage.fetch_usage_mc_metaroll import (
    ABS_FLOOR,
    extract,
    validate_snapshot,
)

FIXTURE = Path(__file__).parent / "fixtures" / "metaroll_all_trimmed.json"
SIX_FORMES = {
    "toxtricity": "punkrock",
    "toxtricitylowkey": "punkrock",
    "squawkabilly": "intimidate",
    "squawkabillyyellow": "intimidate",
    "meowstic": "prankster",
    "meowsticf": "competitive",
}


@pytest.fixture(scope="module")
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def built(payload):
    return extract(fetch=lambda _url: copy.deepcopy(payload))


def test_ids_strip_hyphens_and_forme_rows_stay_separate(built):
    snap, _payload, stats = built
    species = snap["ingame_doubles"]["species"]
    assert set(SIX_FORMES) <= set(species)
    assert "floetteeternal" in species and "floette" not in species
    assert stats["unmatched_ids"] == []
    assert all(row["id"] == sid for sid, row in species.items())


@pytest.mark.parametrize("sid,top", SIX_FORMES.items())
def test_forme_abilities_are_that_formes_legal_abilities(built, sid, top):
    species = built[0]["ingame_doubles"]["species"]
    legal = {to_id(a) for a in load_snapshot()["species"][sid]["abilities"].values()}
    names = [to_id(a["name"]) for a in species[sid]["common_abilities"]]
    assert names[0] == top
    assert set(names) <= legal


def test_base_formes_do_not_carry_other_formes_abilities(built):
    species = built[0]["ingame_doubles"]["species"]
    assert "minus" not in {to_id(a["name"]) for a in species["toxtricity"]["common_abilities"]}
    assert "sheerforce" not in {
        to_id(a["name"]) for a in species["squawkabilly"]["common_abilities"]
    }


def test_row_shape_matches_loader_contract(built, payload):
    row = built[0]["ingame_doubles"]["species"]["garchomp"]
    src = payload["entries"][0]
    assert row["source"] == "metaroll" and row["featured_sets"] == []
    assert row["usage_rank"] == src["rank"]
    assert row["common_moves"][0] == {"name": src["moves"][0]["name"], "pct": src["moves"][0]["percent"]}
    assert row["teammates"] == [t["name"] for t in src["teammates"]]
    first = row["top_spreads"][0]
    assert first["evs"] == src["spreads"][0]["statPoints"]
    assert first["pct"] == src["spreads"][0]["percent"]
    assert first["nature"] == src["natures"][0]["name"]  # rank-paired, labelled in meta
    assert row["common_natures"][0] == {"name": src["natures"][0]["name"], "pct": src["natures"][0]["percent"]}


def test_meta_carries_source_attribution_and_capture(built, payload):
    meta = built[0]["meta"]
    assert (meta["source"], meta["season"]) == ("metaroll", payload["season"])
    assert meta["capturedAt"] == payload["capturedAt"]
    assert meta["comparedTo"] == payload["comparedTo"]
    assert "Usage data from MetaRoll (metaroll.app)" in meta["attribution"]
    assert "rank-paired" in meta["spread_nature_pairing"]


def test_extract_rejects_malformed_payload():
    with pytest.raises(RuntimeError):
        extract(fetch=lambda _url: {"no": "entries"})


def _snap(n: int, *, captured: str = "2026-10-21T00:46:19.000Z", season: str | None = "M-7"):
    row = {
        k: [] for k in ("common_moves", "common_items", "common_abilities", "teammates", "top_spreads", "featured_sets")
    }
    species = {f"s{i}": {"id": f"s{i}", "name": f"S{i}", "source": "metaroll", **row} for i in range(n)}
    return {
        "meta": {"schema_version": 4, "capturedAt": captured, "season": season},
        "ingame_doubles": {"species": species},
    }


_IDX = {"count": 262, "attribution": {"required": True, "text": "Usage data from MetaRoll (metaroll.app)"}}


def test_validate_ok_and_floor():
    stats = {"index_count": 262}
    assert validate_snapshot(_snap(230), index=_IDX, stats=stats)[0] == "ok"
    assert validate_snapshot(_snap(ABS_FLOOR - 1), index=_IDX, stats=stats)[0] == "fail"


def test_validate_noop_when_capture_not_newer():
    prev = _snap(240, captured="2026-10-21T00:46:19.000Z")
    d, why = validate_snapshot(_snap(240), index=_IDX, stats={"index_count": 262}, previous=prev)
    assert d == "noop" and "not newer" in why


def test_validate_fails_on_drop_missing_attribution_or_season():
    stats = {"index_count": 262}
    prev = _snap(262, captured="2026-10-20T00:00:00Z")
    assert validate_snapshot(_snap(230), index=_IDX, stats=stats, previous=prev)[0] == "fail"
    no_attr = {"count": 262, "attribution": {"required": True}}
    assert validate_snapshot(_snap(240), index=no_attr, stats=stats)[0] == "fail"
    assert validate_snapshot(_snap(240, season=None), index=_IDX, stats=stats)[0] == "fail"
