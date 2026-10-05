"""Offline mapping/join tests for MunchStats champions-data extract."""

from __future__ import annotations

from scripts.extract_usage.fetch_usage_mc_munchstats import (
    build_ingame_from_index,
    build_snapshot,
    index_by_showdown_id,
    legal_lookup_ids,
    validate_snapshot,
)


def _mini_legality() -> dict:
    return {
        "flat_rules": {"banlist": ["Mythical", "Restricted Legendary"]},
        "species": {
            "rillaboom": {
                "id": "rillaboom",
                "name": "Rillaboom",
                "base_species_id": None,
                "is_nonstandard": None,
                "tier": "OU",
                "effective_tags": [],
            },
            "absolmegaz": {
                "id": "absolmegaz",
                "name": "Absol-Mega-Z",
                "base_species_id": "absol",
                "is_nonstandard": None,
                "tier": "OU",
                "effective_tags": [],
            },
            "absol": {
                "id": "absol",
                "name": "Absol",
                "base_species_id": None,
                "is_nonstandard": None,
                "tier": "OU",
                "effective_tags": [],
            },
            "raichualola": {
                "id": "raichualola",
                "name": "Raichu-Alola",
                "base_species_id": "raichu",
                "is_nonstandard": None,
                "tier": "OU",
                "effective_tags": [],
            },
            "missingno": {
                "id": "missingno",
                "name": "MissingNo",
                "base_species_id": None,
                "is_nonstandard": None,
                "tier": "OU",
                "effective_tags": [],
            },
        },
    }


def test_legal_lookup_collapses_mega_to_base():
    ids = legal_lookup_ids(_mini_legality())
    assert "absol" in ids
    assert "absolmegaz" not in ids
    assert ids["absol"] == "Absol"
    assert "rillaboom" in ids
    assert "raichualola" in ids  # regional must not collapse to raichu
    assert "missingno" in ids


def test_build_ingame_uses_index_slug_not_constructed_id():
    index = {
        "count": 2,
        "defaultSeason": "Current",
        "generatedAt": "2026-09-12T12:00:00+00:00",
        "publishedAt": "2026-09-12T12:01:00+00:00",
        "capturedOn": "2026-09-12",
        "pokemon": [
            {
                "showdownId": "absol",
                "slug": "absol-special",
                "showdownName": "Absol",
                "name": "Absol",
                "summary": {
                    "battleSummary": {"Current": {"Doubles": {"position": 10}}}
                },
            },
            {
                "showdownId": "rillaboom",
                "slug": "rillaboom",
                "showdownName": "Rillaboom",
                "name": "Rillaboom",
                "summary": {
                    "battleSummary": {"Current": {"Doubles": {"position": 2}}}
                },
            },
        ],
    }
    fetched: list[str] = []

    def fetch(url: str):
        fetched.append(url)
        if url.endswith("index.json"):
            return index
        if "absol-special" in url:
            return {
                "rows": [
                    {
                        "category": "move",
                        "name": "Sucker Punch",
                        "percentage_value": 90.0,
                    }
                ]
            }
        if url.endswith("rillaboom.json"):
            return {
                "rows": [
                    {
                        "category": "move",
                        "name": "Grassy Glide",
                        "percentage_value": 97.0,
                    }
                ]
            }
        return None

    by = index_by_showdown_id(index)
    assert by["absol"]["slug"] == "absol-special"

    ingame, stats = build_ingame_from_index(
        index, legality=_mini_legality(), fetch=fetch, max_workers=2
    )
    assert stats["join_n"] == 2
    assert stats["detail_fetch_ok_n"] == 2
    assert "absol" in ingame and "rillaboom" in ingame
    assert any("absol-special" in u for u in fetched)
    assert "missingno" not in ingame  # absent from index → skip

    snap = build_snapshot(ingame, index, stats)
    decision, _ = validate_snapshot(snap, index=index, stats=stats, previous=None)
    # floor 220 not met with 2 species
    assert decision == "fail"
