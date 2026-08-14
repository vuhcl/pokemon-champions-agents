from __future__ import annotations

from recommender.teammates import normalize_munch_teammates, without_snapshot_teammates
from recommender.usage_data import load_usage


def test_normalizes_against_munchstats_rendered_mega_swampert_values():
    # Oracle observed 2026-08-08 at:
    # https://www.munchstats.com/gen9championsvgc2026regmb/1500/Swampert-Mega?month=2026-06
    result = normalize_munch_teammates(
        {
            "Raw count": 319208,
            "Abilities": {"swiftswim": 183049.75921347798},
            "Teammates": {
                "Pelipper": 149375.76670527988,
                "Archaludon": 124072.26209990928,
                "Sinistcha": 85575.53425667596,
            },
        }
    )

    assert result.denominator_kind == "ability_weight"
    assert result.raw_count == 319208
    assert [(row.name, row.conditional_pct) for row in result.rows or ()] == [
        ("Pelipper", 81.604),
        ("Archaludon", 67.781),
        ("Sinistcha", 46.75),
    ]


def test_hotfix_uses_unconditional_larger_teammate_sum_div_6():
    result = normalize_munch_teammates(
        {
            "Abilities": {"Pressure": 5},
            "Teammates": {f"Form-{index}": 12 for index in range(6)},
        }
    )

    assert result.denominator_weight == 12
    assert result.denominator_kind == "teammate_weight_div_6"
    assert sum(row.conditional_pct for row in result.rows or ()) == 600


def test_preserves_exact_forms_and_truncates_after_full_denominator():
    teammates = {f"Species-{index}": float(index) for index in range(1, 13)}
    result = normalize_munch_teammates(
        {"Abilities": {"Ability": 100}, "Teammates": teammates}
    )

    assert result.source_row_count == 12
    assert result.truncated is True
    assert len(result.rows or ()) == 10
    assert result.rows and result.rows[0].name == "Species-12"
    assert result.rows[0].species_id == "species12"
    assert result.rows[0].rank == 1
    assert result.rows[-1].conditional_pct == 3


def test_invalid_weights_are_ignored_and_missing_differs_from_empty():
    missing = normalize_munch_teammates({"Abilities": {"A": 1}})
    empty = normalize_munch_teammates(
        {
            "Raw count": -1,
            "Abilities": {"A": float("nan"), "B": -2},
            "Teammates": {},
        }
    )
    filtered = normalize_munch_teammates(
        {
            "Abilities": {"A": 10},
            "Teammates": {
                "Valid": "5",
                "": 4,
                "Negative": -1,
                "Infinite": float("inf"),
                "Invalid": "nope",
            },
        }
    )

    assert missing.status == "unavailable"
    assert missing.rows is None
    assert empty.status == "available"
    assert empty.rows == ()
    assert empty.raw_count is None
    assert filtered.rows and [row.name for row in filtered.rows] == ["Valid"]


def test_compatibility_flat_shape_strips_showdown_teammates():
    entry = {
        "name": "Swampert-Mega",
        "common_moves": [{"name": "Protect", "pct": 50}],
        "teammates": [{"id": "pelipper", "conditional_pct": 80}],
        "teammates_meta": {"status": "available"},
    }

    stripped = without_snapshot_teammates(entry)

    assert stripped["name"] == "Swampert-Mega"
    assert stripped["common_moves"] == entry["common_moves"]
    assert "teammates" not in stripped
    assert "teammates_meta" not in stripped


def test_schema_v3_snapshot_has_exact_form_rows_only_in_showdown_slice():
    snapshot = load_usage()
    showdown = snapshot["showdown_vgc_mb"]["species"]

    assert snapshot["meta"]["schema_version"] == 3
    battles = snapshot["meta"]["showdown_battles"]
    assert isinstance(battles, int) and battles > 0
    assert showdown
    assert all(
        "teammates" in entry and "teammates_meta" in entry
        for entry in showdown.values()
    )
    assert all(
        not any(isinstance(row, dict) for row in entry.get("teammates") or [])
        for entry in snapshot["species"].values()
    )
