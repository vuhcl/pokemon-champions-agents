from __future__ import annotations

from unittest.mock import patch

from recommender.teammates import (
    TeammateEvidence,
    TeammateQueryResult,
    _attribution_status,
    query_shared_teammates,
    query_teammates,
)


def _row(
    species_id: str,
    rank: int,
    pct: float | None,
    *,
    attribution: str = "exact",
) -> TeammateEvidence:
    return TeammateEvidence(
        species_id=species_id,
        name=species_id.title(),
        rank=rank,
        conditional_pct=pct,
        chaos_weight=None,
        attribution_status=attribution,  # type: ignore[arg-type]
    )


def _result(
    anchor: str,
    rows: tuple[TeammateEvidence, ...] | None,
) -> TeammateQueryResult:
    return TeammateQueryResult(
        anchor_id=anchor,
        anchor_name=anchor.title(),
        status="available" if rows is not None else "unavailable",
        source="showdown-offline" if rows is not None else None,
        rows=rows,
        raw_count=100,
        truncated=True if rows is not None else None,
        caveats=(f"{anchor}-caveat",),
    )


def test_exact_form_offline_queries_keep_distinct_percentages():
    base = query_teammates("Swampert")
    mega = query_teammates("Swampert-Mega")

    assert base.status == mega.status == "available"
    assert base.source == mega.source == "showdown-offline"
    base_sinistcha = next(row for row in base.rows or () if row.species_id == "sinistcha")
    mega_sinistcha = next(row for row in mega.rows or () if row.species_id == "sinistcha")
    assert base_sinistcha.conditional_pct == 13.7
    assert mega_sinistcha.conditional_pct == 37.563
    assert (base.anchor_id, mega.anchor_id) == ("swampert", "swampertmega")


def test_out_of_snapshot_query_uses_exact_form_live_showdown():
    detail = {
        "Abilities": {"Pressure": 20},
        "Teammates": {"Pelipper": 10},
    }
    calls: list[tuple[str, str]] = []

    def live(species: str, regulation: str):
        calls.append((species, regulation))
        return detail

    with (
        patch("recommender.teammates.showdown_species_map", return_value={}),
        patch("recommender.teammates.ingame_species_map", return_value={}),
    ):
        result = query_teammates(
            "Exact-Form",
            live_showdown_fetch=live,
        )

    assert calls == [("Exact-Form", "champions")]
    assert result.source == "showdown-live"
    assert result.rows and result.rows[0].conditional_pct == 50


def test_cbd_fallback_marks_form_labels_ambiguous_and_unknown_labels_unresolved():
    with (
        patch("recommender.teammates.showdown_species_map", return_value={}),
        patch(
            "recommender.teammates.ingame_species_map",
            return_value={
                "pelipper": {
                    "name": "Pelipper",
                    "teammates": ["Garchomp", "MissingNo"],
                }
            },
        ),
    ):
        result = query_teammates(
            "Pelipper",
            live_showdown_fetch=lambda _species, _regulation: None,
        )

    assert result.source == "cbd-offline"
    assert [row.conditional_pct for row in result.rows or ()] == [None, None]
    assert [row.attribution_status for row in result.rows or ()] == [
        "ambiguous",
        "unresolved",
    ]


def test_existing_malformed_showdown_row_is_unavailable_without_live_fetch():
    calls: list[tuple[str, str]] = []

    def live(species: str, regulation: str):
        calls.append((species, regulation))
        return {"Abilities": {"A": 1}, "Teammates": {"Pelipper": 1}}

    with (
        patch(
            "recommender.teammates.showdown_species_map",
            return_value={
                "pelipper": {
                    "name": "Pelipper",
                    "teammates": None,
                    "teammates_meta": {"status": "unavailable"},
                }
            },
        ),
        patch(
            "recommender.teammates.ingame_species_map",
            return_value={"pelipper": {"teammates": ["Archaludon"]}},
        ),
    ):
        result = query_teammates(
            "Pelipper",
            live_showdown_fetch=live,
        )

    assert calls == []
    assert result.status == "unavailable"
    assert result.source is None
    assert result.rows is None
    assert result.caveats == ("offline exact-form teammate record is malformed",)


def test_shared_query_is_strict_and_distinguishes_empty_from_unavailable():
    available = {
        "a": _result("a", (_row("x", 1, 10),)),
        "b": _result("b", (_row("y", 1, 10),)),
    }
    empty = query_shared_teammates(
        ["A", "B"], query=lambda species, _reg: available[species.lower()]
    )
    unavailable = query_shared_teammates(
        ["A", "C"],
        query=lambda species, _reg: (
            available["a"] if species == "A" else _result("c", None)
        ),
    )

    assert empty.status == "available"
    assert empty.rows == ()
    assert unavailable.status == "unavailable"
    assert unavailable.rows is None
    assert unavailable.unavailable_anchors == ("c",)


def test_shared_query_orders_complete_percentages_by_bottleneck_probability():
    per_anchor = {
        "a": _result("a", (_row("x", 1, 10), _row("y", 2, 80))),
        "b": _result("b", (_row("x", 1, 9), _row("y", 10, 70))),
    }

    result = query_shared_teammates(
        ["A", "B"], query=lambda species, _reg: per_anchor[species.lower()]
    )

    assert result.rows and [row.species_id for row in result.rows] == ["y", "x"]
    assert result.rows[0].min_conditional_pct == 70
    assert result.rows[0].worst_rank == 10


def test_shared_rank_only_rows_use_minimax_worst_rank_order():
    per_anchor = {
        "a": _result("a", (_row("x", 1, None), _row("y", 3, None))),
        "b": _result("b", (_row("x", 8, None), _row("y", 4, None))),
    }

    result = query_shared_teammates(
        ["A", "B"], query=lambda species, _reg: per_anchor[species.lower()]
    )

    assert result.rows and [row.species_id for row in result.rows] == ["y", "x"]
    assert [row.worst_rank for row in result.rows] == [4, 8]


def test_shared_query_excludes_every_locked_anchors_lineage():
    per_anchor = {
        "swampert": _result(
            "swampert",
            (_row("swampertmega", 1, 90), _row("pelipper", 2, 80)),
        ),
        "pelipper": _result(
            "pelipper",
            (_row("swampertmega", 1, 90), _row("pelipper", 2, 80)),
        ),
    }

    result = query_shared_teammates(
        ["Swampert", "Pelipper"],
        query=lambda species, _reg: per_anchor[species.lower()],
    )

    assert result.rows == ()


def test_gmax_only_bases_are_exact_garchomp_stays_ambiguous():
    assert _attribution_status("grimmsnarl") == "exact"
    assert _attribution_status("hatterene") == "exact"
    assert _attribution_status("garchomp") == "ambiguous"


def _no_live(_species: str, _regulation: str):
    return None


def _cbd_only(species: str) -> TeammateQueryResult:
    return query_teammates(species, live_showdown_fetch=_no_live)


def _force_cbd(species: str) -> TeammateQueryResult:
    with patch("recommender.teammates.showdown_species_map", return_value={}):
        return query_teammates(species, live_showdown_fetch=_no_live)


def _row_named(result: TeammateQueryResult, species_id: str) -> TeammateEvidence:
    return next(row for row in result.rows or () if row.species_id == species_id)


def test_cbd_swampert_remaps_to_mega():
    result = _cbd_only("vivillonfancy")
    assert result.source == "cbd-offline"
    row = _row_named(result, "swampertmega")
    assert row.name == "Swampert-Mega"
    assert row.attribution_status == "exact"
    assert all(row.species_id != "swampert" for row in result.rows or ())


def test_cbd_raichu_remaps_to_mega_y_not_x():
    result = _force_cbd("ninetalesalola")
    assert result.source == "cbd-offline"
    row = _row_named(result, "raichumegay")
    assert row.name == "Raichu-Mega-Y"
    assert row.attribution_status == "exact"
    assert all(row.species_id not in {"raichu", "raichumegax"} for row in result.rows or ())


def test_cbd_tyranitar_stays_ambiguous():
    result = _force_cbd("excadrill")
    assert result.source == "cbd-offline"
    row = _row_named(result, "tyranitar")
    assert row.name == "Tyranitar"
    assert row.attribution_status == "ambiguous"


def test_cbd_garchomp_stays_ambiguous():
    result = _cbd_only("mausholdfour")
    assert result.source == "cbd-offline"
    row = _row_named(result, "garchomp")
    assert row.name == "Garchomp"
    assert row.attribution_status == "ambiguous"


def test_cbd_mawile_shared_query_is_mega_exact():
    result = query_shared_teammates(
        ["mausholdfour", "vivillonfancy"],
        query=lambda species, regulation: query_teammates(
            species, regulation, live_showdown_fetch=_no_live
        ),
    )
    assert result.status == "available"
    row = next(r for r in result.rows or () if r.species_id == "mawilemega")
    assert row.name == "Mawile-Mega"
    assert row.attribution_status == "exact"
    assert all(r.species_id != "mawile" for r in result.rows or ())


def test_cbd_sinistcha_and_flavor_names_untouched():
    maushold = _cbd_only("mausholdfour")
    assert maushold.anchor_id == "mausholdfour"
    assert maushold.source == "cbd-offline"
    sinistcha = _row_named(maushold, "sinistcha")
    assert sinistcha.name == "Sinistcha"
    assert sinistcha.attribution_status == "ambiguous"

    mawile = _cbd_only("mawile")
    four = _row_named(mawile, "mausholdfamilyoffour")
    assert four.name == "Maushold Family of Four"
    assert four.attribution_status == "unresolved"

    fancy_page = _cbd_only("vivillonfancy")
    assert fancy_page.anchor_id == "vivillonfancy"
    gengar = _force_cbd("gengar")
    fancy = _row_named(gengar, "vivillonfancypattern")
    assert fancy.name == "Vivillon Fancy Pattern"
    assert fancy.attribution_status == "unresolved"
