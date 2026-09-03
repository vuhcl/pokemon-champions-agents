"""Team-conditioned default builds from offline VGCPastes teams."""

from __future__ import annotations

from unittest.mock import patch

from recommender.state import Attr, Slot, empty_slot
from recommender.usage_data import (
    build_team_aware_default_set,
    find_team_conditioned_build,
    locked_teammate_ids_for_pastes,
    load_vgcpastes_builds,
    _trim_unneeded_weather_moves,
    _vgcpastes_team_index,
)


def _slot(species: str, *, moves: list[str] | None = None, item: str | None = None) -> Slot:
    return Slot(
        species=Attr(value=species, locked=True),
        item=Attr(value=item, locked=True) if item else Attr(),
        moveset=Attr(value=moves, locked=True) if moves else Attr(),
    )


def _inline_pastes() -> dict:
    return {
        "meta": {},
        "teams": [
            {
                "members": [
                    {
                        "species": "pelipper",
                        "item": "Focus Sash",
                        "ability": "Drizzle",
                        "nature": "Timid",
                        "evs": {"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32},
                        "moves": ["Hurricane", "Tailwind", "Weather Ball", "Wide Guard"],
                    },
                    {
                        "species": "sableye",
                        "item": "Light Clay",
                        "ability": "Prankster",
                        "nature": "Bold",
                        "evs": {"hp": 32, "atk": 0, "def": 32, "spa": 0, "spd": 0, "spe": 0},
                        "moves": ["Light Screen", "Reflect", "Rain Dance", "Quash"],
                    },
                ]
            }
            for _ in range(4)
        ],
        "cores": [],
    }


def _whims_staraptor_pastes() -> dict:
    teams = []
    for moves in (
        ["Charm", "Light Screen", "Moonblast", "Tailwind"],
        ["Charm", "Encore", "Moonblast", "Tailwind"],
        ["Charm", "Light Screen", "Moonblast", "Tailwind"],
    ):
        for _ in range(2):
            teams.append(
                {
                    "members": [
                        {
                            "species": "whimsicott",
                            "item": "Covert Cloak",
                            "ability": "Prankster",
                            "nature": "Timid",
                            "evs": {"hp": 4, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 32},
                            "moves": moves,
                        },
                        {
                            "species": "staraptor",
                            "item": "Staraptite",
                            "ability": "Intimidate",
                            "nature": "Adamant",
                            "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
                            "moves": ["Brave Bird", "Close Combat", "U-turn", "Protect"],
                        },
                    ]
                }
            )
    return {"meta": {}, "teams": teams, "cores": []}


def _clear_pastes_cache() -> None:
    load_vgcpastes_builds.cache_clear()
    _vgcpastes_team_index.cache_clear()


def test_sableye_pelipper_keeps_rain_dance_with_provider():
    draft = [_slot("Pelipper", moves=["Hurricane", "Tailwind", "Weather Ball", "Wide Guard"])]
    _clear_pastes_cache()
    with patch(
        "recommender.usage_data.load_vgcpastes_builds",
        return_value=_inline_pastes(),
    ):
        hit = find_team_conditioned_build(
            "Sableye", frozenset({"pelipper"}), min_occurrences=3
        )
    assert hit is not None
    assert "Rain Dance" in hit["moves"]


def test_trim_drops_rain_dance_without_provider_or_beneficiary():
    draft = [
        _slot(
            "Staraptor",
            moves=["Brave Bird", "Close Combat", "U-turn", "Protect"],
        )
    ]
    moves = ["Rain Dance", "Light Screen", "Reflect", "Knock Off"]
    trimmed = _trim_unneeded_weather_moves(
        "Sableye",
        moves,
        team_draft=draft,
        regulation="champions-reg-mb",
    )
    assert "Rain Dance" not in trimmed
    assert len(trimmed) == 4


def test_whimsicott_staraptor_conditioned_includes_charm():
    _clear_pastes_cache()
    with patch(
        "recommender.usage_data.load_vgcpastes_builds",
        return_value=_whims_staraptor_pastes(),
    ):
        hit = find_team_conditioned_build(
            "Whimsicott", frozenset({"staraptor"}), min_occurrences=3
        )
    assert hit is not None
    assert "Charm" in hit["moves"]


def test_no_locked_teammates_skips_team_conditioned_lookup():
    with patch("recommender.usage_data.find_team_conditioned_build") as mocked:
        build_team_aware_default_set("Pelipper", regulation="champions-reg-mb")
    mocked.assert_not_called()


def test_zero_paste_matches_falls_back_to_featured():
    draft = [_slot("Pelipper")]
    with patch("recommender.usage_data.find_team_conditioned_build", return_value=None):
        usage = build_team_aware_default_set(
            "Pelipper",
            regulation="champions-reg-mb",
            team_draft=draft,
        )
    assert usage is not None
    assert usage.get("moves")


def test_transcript_five_lock_quartet_matches_basculegion():
    _clear_pastes_cache()
    rows = [
        ("Archaludon", ["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"]),
        ("Pelipper", ["Hurricane", "Tailwind", "Weather Ball", "Wide Guard"]),
        ("Sinistcha", ["Matcha Gotcha", "Rage Powder", "Trick Room", "Protect"]),
        ("Swampert-Mega", ["Protect", "Wave Crash", "Ice Punch", "Earthquake"]),
        ("Delphox-Mega", ["Heat Wave", "Psychic", "Dazzling Gleam", "Protect"]),
    ]
    draft = [_slot(sp, moves=mv) for sp, mv in rows]
    draft.append(empty_slot())
    locked = locked_teammate_ids_for_pastes(draft, exclude_species="Basculegion")
    hit = find_team_conditioned_build("Basculegion", locked, min_occurrences=3)
    assert hit is not None
    assert hit["occurrence_count"] >= 3
    assert hit["match_tier"] in ("triple", "pair")


def test_pair_tier_relaxation_when_triple_thin():
    _clear_pastes_cache()
    locked = frozenset({"pelipper", "sinistcha", "swampert"})
    thin = find_team_conditioned_build(
        "Basculegion", locked, min_occurrences=100
    )
    assert thin is None
    pair = find_team_conditioned_build(
        "Basculegion", frozenset({"pelipper"}), min_occurrences=1
    )
    assert pair is not None
