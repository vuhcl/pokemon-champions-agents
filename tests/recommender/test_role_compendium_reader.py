"""Read path for the shipped Role Compendium — construction writes these, nothing read them before."""

import json
from pathlib import Path

from recommender.role_compendium import DEFAULT_ROLES_DIR, ROLE_TIER_ORDER, load_role_category, reverse_compendium_evidence, role_category_evidence, role_candidates


def test_reads_a_shipped_unconditioned_role():
    entry = load_role_category("redirection")
    assert entry is not None
    assert entry["category"] == "redirection"
    assert entry["tiers"]["Excellent"]


def test_conditioned_role_resolves_its_own_file():
    """weather_setter is one category across four files, split only by condition."""
    rain = load_role_category("weather_setter", "Rain")
    sun = load_role_category("weather_setter", "Sun")
    assert rain is not None and sun is not None
    assert rain["condition"] == "Rain"
    assert sun["condition"] == "Sun"
    assert rain["tiers"] != sun["tiers"]

    # The condition is normalized through to_id, so casing does not matter.
    assert load_role_category("weather_setter", "rain") == rain

    # Without a condition there is no such file — the bare category must not resolve.
    assert load_role_category("weather_setter") is None


def test_candidates_run_strongest_tier_first():
    entry = load_role_category("swords_dance_attacker")
    assert entry is not None
    got = role_candidates("swords_dance_attacker")
    assert got == [sp for tier in ROLE_TIER_ORDER for sp in entry["tiers"][tier]]
    # Ordering is the point: every Excellent member outranks every Acceptable one.
    assert got.index(entry["tiers"]["Excellent"][0]) < got.index(entry["tiers"]["Acceptable"][0])


def test_forward_evidence_preserves_tiers_and_rejections():
    entry = load_role_category("trick_room_setter")
    assert entry is not None

    evidence = role_category_evidence("trick_room_setter")

    assert not evidence.exact
    assert [row.species for row in evidence.species] == role_candidates(
        "trick_room_setter"
    )
    assert evidence.species[0].tier == "Excellent"
    assert evidence.species[0].source_file == "trick_room_setter.v1.json"
    assert {row.species for row in evidence.rejected} == {
        row["species"] for row in entry["considered_rejected"]
    }


def test_unbuilt_role_is_a_miss_not_an_error():
    assert load_role_category("no_such_role") is None
    assert role_candidates("no_such_role") == []
    assert role_category_evidence("no_such_role") == role_category_evidence(
        "still_no_such_role"
    )


def test_every_shipped_file_is_reachable_and_uses_known_tiers():
    """Guards the read path against drift in what construction writes."""
    shipped = sorted(DEFAULT_ROLES_DIR.glob("*.v1.json"))
    assert shipped, "no role files shipped"
    for path in shipped:
        raw = json.loads(path.read_text())
        found = load_role_category(raw["category"], raw.get("condition") or "")
        assert found is not None, f"{path.name} unreachable via its own category/condition"
        assert found["built_at"] == raw["built_at"], f"{path.name} resolved to a different file"
        # An unknown tier name would be dropped silently by role_candidates.
        unknown = set(raw["tiers"]) - set(ROLE_TIER_ORDER)
        assert not unknown, f"{path.name} has tiers the reader ignores: {sorted(unknown)}"


def test_roles_dir_override(tmp_path: Path):
    (tmp_path / "made_up_role.v1.json").write_text(
        json.dumps({"category": "made_up_role", "tiers": {"Good": ["Ditto"]}})
    )
    assert role_candidates("made_up_role", roles_dir=tmp_path) == ["Ditto"]
    assert role_candidates("made_up_role") == []


def test_reverse_reader_separates_exact_species_and_rejected():
    king = reverse_compendium_evidence(
        "Kingambit",
        moves=["Sucker Punch", "Kowtow Cleave", "Protect", "Iron Head"],
        ability="Defiant",
    )
    assert not king.exact
    assert {row.role_id for row in king.species} == {"swords_dance_attacker"}

    setup_king = reverse_compendium_evidence(
        "Kingambit", moves=["Swords Dance"], ability="Defiant"
    )
    assert {row.role_id for row in setup_king.exact} == {"swords_dance_attacker"}
    assert {row.species for row in setup_king.exact} == {"Kingambit"}

    arch = reverse_compendium_evidence("Archaludon")
    assert any(row.role_id == "swords_dance_attacker" for row in arch.rejected)


def test_reverse_exact_matches_prefer_higher_tier_over_alphabetical_file():
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build

    build = resolve_anchor_build("Pelipper")
    evidence = reverse_compendium_evidence(
        build.species or "", moves=build.moves, ability=build.ability
    )
    assert len(evidence.exact) >= 2
    assert evidence.exact[0].role_id == "rain_setter"
    assert evidence.exact[0].tier == "Excellent"
    assert classify_anchor_role(build).role_id == "rain_setter"


def test_reverse_exact_tie_break_alphabetical_by_source_file(tmp_path: Path):
    (tmp_path / "alpha_role.v1.json").write_text(
        json.dumps(
            {
                "category": "alpha_role",
                "tiers": {"Excellent": ["Pelipper"]},
                "candidates": [
                    {
                        "species": "Pelipper",
                        "species_id": "pelipper",
                        "mechanism": "AlphaMech",
                    }
                ],
            }
        )
    )
    (tmp_path / "zulu_role.v1.json").write_text(
        json.dumps(
            {
                "category": "zulu_role",
                "tiers": {"Excellent": ["Pelipper"]},
                "candidates": [
                    {
                        "species": "Pelipper",
                        "species_id": "pelipper",
                        "mechanism": "ZuluMech",
                    }
                ],
            }
        )
    )
    evidence = reverse_compendium_evidence(
        "Pelipper", moves=["AlphaMech", "ZuluMech"], roles_dir=tmp_path
    )
    assert len(evidence.exact) == 2
    assert evidence.exact[0].source_file == "alpha_role.v1.json"
    assert evidence.exact[1].source_file == "zulu_role.v1.json"
