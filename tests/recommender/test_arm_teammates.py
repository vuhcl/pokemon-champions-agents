"""Arm-facing explicit-source teammate tools (D7; ADR-014 2026-10-14a/14b)."""

from __future__ import annotations

import inspect
from datetime import date

import pytest

import recommender.arm_teammates as arm
from recommender.arm_teammates import (
    ARM_MESSAGE_ALLOWLIST,
    ArmLiveFetchError,
    arm_query_teammates,
    arm_query_teammates_multi,
    is_mega_forme,
    legal_mega_forme_ids,
    period_end_for_month,
)
from recommender.ids import to_id
from recommender.item_conditions import mega_stones_by_item_id
from recommender.legality import is_species_legal, load_snapshot
from recommender.regulation_registry import CHAMPIONS_MOD_DEFAULT_ALLOWLIST

LIVE_REG = "champions-reg-mb"  # the only regulation with a live tuple today
DETAIL = {"Abilities": {"Pressure": 20}, "Teammates": {"Pelipper": 10, "Incineroar": 8}}

H6_TOP5 = {"Incineroar", "Sneasler", "Salamence", "Gholdengo", "Raichu"}
MT2 = {"Basculegion-F", "Charizard", "Rillaboom", "Sneasler"}


class SpyMap(dict):
    """Dict that counts lookups, to prove which source was queried."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.gets = 0

    def get(self, key, default=None):
        self.gets += 1
        return super().get(key, default)


def ig(species_id: str, teammates: list[str]) -> dict:
    return {species_id: {"name": species_id.title(), "teammates": teammates}}


def sd(species_id: str, mates: list[tuple[str, float]]) -> dict:
    return {
        species_id: {
            "name": species_id.title(),
            "teammates": [
                {
                    "id": i,
                    "name": i.title(),
                    "rank": n,
                    "conditional_pct": p,
                    "chaos_weight": 1.0,
                }
                for n, (i, p) in enumerate(mates, start=1)
            ],
            "teammates_meta": {"raw_count": 100, "truncated": False},
        }
    }


@pytest.fixture
def maps(monkeypatch):
    """Replace both usage maps with controllable dicts (live fetch stays injected)."""
    state = {"ingame": SpyMap(), "showdown": SpyMap()}
    monkeypatch.setattr(arm, "ingame_ladder_species_map", lambda reg: state["ingame"])
    monkeypatch.setattr(arm, "showdown_species_map", lambda reg: state["showdown"])
    return state


@pytest.fixture
def logged(monkeypatch):
    calls: list[dict] = []
    monkeypatch.setattr(
        arm, "log_tool_call", lambda tool, args, **kw: calls.append({"tool": tool, **kw})
    )
    return calls


def _no_live(*_a):
    raise AssertionError("live fetch must not be called")


# --- source validation / build-level -------------------------------------


def test_source_is_required_with_no_default():
    for fn in (arm_query_teammates, arm_query_teammates_multi):
        p = inspect.signature(fn).parameters["source"]
        assert p.default is inspect.Parameter.empty
        assert p.kind is inspect.Parameter.KEYWORD_ONLY
        assert "phase" not in inspect.signature(fn).parameters


@pytest.mark.parametrize("bad", [None, "", "bogus", "cbd"])
def test_missing_or_unknown_source_is_an_error_result(bad):
    r = arm_query_teammates("Rillaboom", source=bad)
    m = arm_query_teammates_multi(["Pelipper"], source=bad)
    for res in (r, m):
        assert res.status == "error"
        assert res.error_kind == "invalid_source"
        assert res.message in ARM_MESSAGE_ALLOWLIST


@pytest.mark.parametrize(
    "build_source", ["vgcpastes", "pikalytics", "pokemon-zone", "writeups"]
)
def test_build_level_sources_are_deferred_not_invalid(build_source):
    assert (
        arm_query_teammates("Rillaboom", source=build_source).status
        == "deferred_build_surface"
    )
    assert (
        arm_query_teammates_multi(["Pelipper"], source=build_source).status
        == "deferred_build_surface"
    )


def test_invalid_mode_is_a_fourth_error_kind():
    m = arm_query_teammates_multi(["Pelipper"], source="ingame", mode="nope")
    assert (m.status, m.error_kind) == ("error", "invalid_mode")
    assert m.message in ARM_MESSAGE_ALLOWLIST


# --- showdown offline: happy path and malformed ---------------------------


def test_showdown_offline_serves_labeled_percentages():
    r = arm_query_teammates("Rillaboom", source="showdown", allow_live=False)
    assert (r.status, r.requested_source, r.used_source) == (
        "available",
        "showdown",
        "showdown",
    )
    assert (r.method, r.value_kind, r.fallback) == ("offline", "conditional_percent", None)
    assert all(
        row.conditional_pct is not None and row.value_kind == "conditional_percent"
        for row in r.rows
    )
    assert r.as_of.source == "showdown" and r.as_of.period_end
    assert r.attempts == (arm.ArmAttempt("showdown", "offline", None),)


@pytest.mark.parametrize(
    "entry",
    ["not-a-dict", {"name": "Rillaboom", "teammates": "oops"}],
    ids=["row-not-dict", "teammates-not-list"],
)
def test_malformed_showdown_row_errors_without_live_or_hop(maps, logged, entry):
    maps["showdown"]["rillaboom"] = entry
    maps["ingame"].update(ig("rillaboom", ["Incineroar"]))
    r = arm_query_teammates(
        "Rillaboom", source="showdown", regulation=LIVE_REG, live_showdown_fetch=_no_live
    )
    assert (r.status, r.error_kind) == ("error", "malformed_offline_row")
    assert r.message in ARM_MESSAGE_ALLOWLIST
    assert r.attempts == () and maps["ingame"].gets == 0
    assert logged and logged[-1]["error"].startswith("malformed_offline_row:")


def test_malformed_ingame_row_errors_without_hop(maps, logged):
    maps["ingame"]["rillaboom"] = {"name": "Rillaboom", "teammates": None}
    maps["showdown"].update(sd("rillaboom", [("incineroar", 30.0)]))
    r = arm_query_teammates("Rillaboom", source="ingame", live_showdown_fetch=_no_live)
    assert (r.status, r.error_kind) == ("error", "malformed_offline_row")
    assert maps["showdown"].gets == 0
    assert logged[-1]["error"] == "malformed_offline_row:dict"


# --- live path -------------------------------------------------------------


def test_live_success_is_labeled_live_with_one_call(maps):
    calls = []

    def fetch(species, regulation):
        calls.append((species, regulation))
        return DETAIL

    r = arm_query_teammates(
        "Exactform", source="showdown", regulation=LIVE_REG, live_showdown_fetch=fetch
    )
    assert calls == [("Exactform", LIVE_REG)]
    assert (r.status, r.used_source, r.method, r.fallback) == (
        "available",
        "showdown",
        "live",
        None,
    )
    assert r.as_of.extracted_at is None and r.as_of.fetched_at
    assert (r.as_of.month, r.as_of.period_end) == ("2026-06", "2026-06-30")


def test_live_miss_in_production_form_is_miss_or_error_then_hops(maps):
    maps["ingame"].update(ig("exactform", ["Incineroar"]))
    r = arm_query_teammates(
        "Exactform",
        source="showdown",
        regulation=LIVE_REG,
        live_showdown_fetch=lambda s, g: None,  # what production returns on any failure
    )
    assert r.used_source == "ingame"
    assert r.fallback.reason == r.fallback.error_kind == "live_unavailable"
    assert r.attempts[0].subkind == "miss_or_error"
    assert r.attempts[1].source == "ingame"


@pytest.mark.parametrize(
    "kind", ["http_4xx_miss", "transient_exhausted", "json_decode"]
)
def test_injected_live_error_subkinds_are_recorded(maps, kind):
    def fetch(species, regulation):
        raise ArmLiveFetchError(kind)

    r = arm_query_teammates(
        "Exactform", source="showdown", regulation=LIVE_REG, live_showdown_fetch=fetch
    )
    assert r.status == "unavailable"
    assert r.attempts[0].reason == "live_unavailable"
    assert r.attempts[0].subkind == kind


def test_allow_live_false_records_live_disabled_and_never_fetches(maps):
    r = arm_query_teammates(
        "Exactform",
        source="showdown",
        regulation=LIVE_REG,
        allow_live=False,
        live_showdown_fetch=_no_live,
    )
    assert r.attempts[0].reason == "live_disabled"


@pytest.mark.parametrize("reg", ["champions-reg-mc", "champions"])
def test_regulation_without_live_tuple_is_live_not_supported(maps, reg):
    r = arm_query_teammates(
        "Exactform", source="showdown", regulation=reg, live_showdown_fetch=_no_live
    )
    assert r.status == "unavailable"
    assert r.attempts[0].reason == "live_not_supported"


# --- in-game and Mega ------------------------------------------------------


def test_h6_rillaboom_top5_is_served_from_ingame_without_percentages():
    r = arm_query_teammates("Rillaboom", source="ingame", allow_live=False)
    assert (r.status, r.used_source, r.value_kind, r.fallback) == (
        "available",
        "ingame",
        "rank_only",
        None,
    )
    assert {row.name for row in r.rows[:5]} == H6_TOP5
    assert [row.rank for row in r.rows[:5]] == [1, 2, 3, 4, 5]


def test_ingame_rows_carry_no_percentage_fields():
    r = arm_query_teammates("Rillaboom", source="ingame", allow_live=False)
    assert all(
        row.conditional_pct is None and row.chaos_weight is None for row in r.rows
    )
    fields = set(arm.ArmTeammateRow.__dataclass_fields__)
    assert not {f for f in fields if "pct" in f or "percent" in f} - {"conditional_pct"}


def test_mega_capable_base_in_ingame_carries_mixed_usage_caveat():
    r = arm_query_teammates("Charizard", source="ingame", allow_live=False)
    assert r.used_source == "ingame"
    assert any("mixes base-form and Mega-form" in c for c in r.caveats)


def test_mega_request_on_ingame_is_served_whole_from_showdown():
    r = arm_query_teammates("Salamence-Mega", source="ingame", allow_live=False)
    assert (r.status, r.used_source) == ("available", "showdown")
    assert r.fallback.reason == r.fallback.error_kind == "form_not_in_source"
    assert [a.source for a in r.attempts] == ["ingame", "showdown"]


def test_detected_mega_set_equals_independent_derivation():
    snap = load_snapshot()
    expected = set()
    for pairs in mega_stones_by_item_id().values():
        for _base, mega in pairs:
            mid = to_id(mega)
            entry = snap["species"].get(mid) or {}
            if entry.get("base_species_id") and is_species_legal(snap, mid):
                expected.add(mid)
    assert expected  # an empty set would make the equality vacuous
    assert legal_mega_forme_ids() == expected
    assert all(is_mega_forme(m) for m in expected)


def test_names_that_merely_contain_mega_are_not_mega_formes():
    assert not is_mega_forme("Yanmega")
    assert not is_mega_forme("Meganium")


# --- dual miss: attempts[] shape -------------------------------------------


def test_ingame_no_row_then_showdown_miss_has_exactly_two_ordered_attempts(maps):
    r = arm_query_teammates("Exactform", source="ingame", allow_live=False)
    assert r.status == "unavailable"
    assert [(a.source, a.reason) for a in r.attempts] == [
        ("ingame", "no_row"),
        ("showdown", "live_disabled"),
    ]


def test_ingame_is_attempted_once_when_neither_source_has_the_species(maps):
    r = arm_query_teammates("Exactform", source="ingame", allow_live=False)
    assert r.status == "unavailable"
    assert maps["ingame"].gets == 1
    assert maps["showdown"].gets == 1


def test_mega_on_ingame_then_showdown_miss_has_no_duplicate_ingame_entry(maps):
    r = arm_query_teammates("Salamence-Mega", source="ingame", allow_live=False)
    assert [(a.source, a.reason) for a in r.attempts] == [
        ("ingame", "form_not_in_source"),
        ("showdown", "live_disabled"),
    ]
    assert maps["ingame"].gets == 0  # not queried for a Mega


def test_showdown_miss_then_ingame_miss_has_two_attempts(maps):
    r = arm_query_teammates("Exactform", source="showdown", allow_live=False)
    assert [(a.source, a.reason) for a in r.attempts] == [
        ("showdown", "live_disabled"),
        ("ingame", "no_row"),
    ]


def test_mega_on_showdown_with_live_disabled_adds_synthetic_ingame_entry(maps):
    maps["ingame"].update(ig("salamencemega", ["Incineroar"]))  # must never be served
    r = arm_query_teammates("Salamence-Mega", source="showdown", allow_live=False)
    assert r.status == "unavailable"
    assert [(a.source, a.reason) for a in r.attempts] == [
        ("showdown", "live_disabled"),
        ("ingame", "form_not_in_source"),
    ]
    assert maps["ingame"].gets == 0


def test_mega_on_showdown_with_failed_live_adds_synthetic_ingame_entry(maps):
    r = arm_query_teammates(
        "Salamence-Mega",
        source="showdown",
        regulation=LIVE_REG,
        live_showdown_fetch=lambda s, g: None,
    )
    assert [(a.source, a.reason) for a in r.attempts] == [
        ("showdown", "live_unavailable"),
        ("ingame", "form_not_in_source"),
    ]


# --- multi anchor -----------------------------------------------------------


def test_mt2_pelipper_whimsicott_intersection_on_ingame():
    m = arm_query_teammates_multi(
        ["Pelipper", "Whimsicott"], source="ingame", allow_live=False
    )
    assert (m.status, m.fallback) == ("available", None)
    assert {row.name for row in m.rows} == MT2
    assert all(r.used_source == "ingame" for r in m.anchor_results)
    assert [ao.source for ao in m.as_of.per_anchor] == ["ingame", "ingame"]


def test_reverse_lookup_scans_lists_and_carries_lower_bound_caveats(maps):
    maps["ingame"].update(
        {
            **ig("pelipper", ["Rillaboom"]),
            **ig("whimsicott", ["Rillaboom"]),
            **ig("incineroar", ["Pelipper", "Whimsicott"]),
            **ig("sneasler", ["Pelipper"]),
        }
    )
    m = arm_query_teammates_multi(
        ["Pelipper", "Whimsicott"],
        source="ingame",
        mode="reverse_lookup",
        allow_live=False,
    )
    assert [row.species_id for row in m.rows] == ["incineroar"]  # sneasler lists only one
    assert any("lower bound" in c for c in m.caveats)
    assert any("same team" in c for c in m.caveats)


def test_team_level_mode_is_deferred():
    m = arm_query_teammates_multi(
        ["Pelipper", "Whimsicott"], source="ingame", mode="team_level"
    )
    assert m.status == "deferred_build_surface"


def test_any_mega_anchor_on_ingame_moves_the_whole_query_to_showdown():
    m = arm_query_teammates_multi(
        ["Pelipper", "Salamence-Mega"], source="ingame", allow_live=False
    )
    assert m.status == "available"
    assert all(r.used_source == "showdown" for r in m.anchor_results)
    assert m.fallback.reason == "form_not_in_source"
    assert (m.fallback.requested, m.fallback.used) == ("ingame", "showdown")


def test_mega_anchor_missing_on_showdown_makes_whole_query_unavailable(maps):
    maps["showdown"].update(sd("pelipper", [("incineroar", 30.0)]))
    maps["ingame"].update(ig("pelipper", ["Incineroar"]))
    m = arm_query_teammates_multi(
        ["Pelipper", "Salamence-Mega"], source="showdown", allow_live=False
    )
    assert m.status == "unavailable" and m.rows is None
    assert m.fallback is None
    assert ("ingame", "form_not_in_source", "salamencemega") in {
        (a.source, a.reason, a.anchor_id) for a in m.attempts
    }
    assert maps["ingame"].gets == 0  # Mega present: in-game is never queried for data


def test_non_mega_missing_row_moves_every_anchor_to_the_other_source(maps):
    maps["ingame"].update(ig("pelipper", ["Rillaboom"]))  # whimsicott has no row
    maps["showdown"].update(
        {
            **sd("pelipper", [("rillaboom", 20.0)]),
            **sd("whimsicott", [("rillaboom", 25.0)]),
        }
    )
    m = arm_query_teammates_multi(
        ["Pelipper", "Whimsicott"], source="ingame", allow_live=False
    )
    assert m.status == "available"
    assert [r.used_source for r in m.anchor_results] == ["showdown", "showdown"]
    assert m.fallback.reason == "no_row"
    assert [row.species_id for row in m.rows] == ["rillaboom"]


def test_second_leg_miss_keeps_every_anchor_and_names_the_missing_one(maps):
    maps["ingame"].update(ig("pelipper", ["Rillaboom"]))
    maps["showdown"].update(sd("pelipper", [("rillaboom", 20.0)]))
    m = arm_query_teammates_multi(
        ["Pelipper", "Whimsicott"], source="ingame", allow_live=False
    )
    assert m.status == "unavailable"
    assert m.unavailable_anchors == ("whimsicott",)
    assert m.rows is None


def test_one_live_and_one_offline_anchor_flags_differing_dates(maps):
    maps["showdown"].update(sd("pelipper", [("rillaboom", 20.0)]))  # offline (M-B 2026-07)
    detail = {"Abilities": {"Drizzle": 20}, "Teammates": {"Rillaboom": 10}}
    m = arm_query_teammates_multi(
        ["Pelipper", "Exactform"],  # Exactform is absent offline, so it goes live (2026-06)
        source="showdown",
        regulation=LIVE_REG,
        live_showdown_fetch=lambda s, g: detail,
    )
    assert m.status == "available"
    assert [r.method for r in m.anchor_results] == ["offline", "live"]
    assert m.as_of.as_of_dates_differ is True
    assert m.as_of.note
    assert m.as_of.per_anchor[0].month != m.as_of.per_anchor[1].month
    assert m.as_of.per_anchor[1].fetched_at


# --- age and period_end ------------------------------------------------------


def test_ingame_age_counts_from_captured_on(monkeypatch):
    monkeypatch.setattr(arm, "_utc_today", lambda: date(2026, 10, 14))
    r = arm_query_teammates("Rillaboom", source="ingame", allow_live=False)
    assert (r.as_of.captured_on, r.as_of.season) == ("2026-10-06", "Current")
    assert r.as_of.age_days == 8


def test_showdown_age_counts_from_period_end_not_extracted_at(monkeypatch):
    monkeypatch.setattr(arm, "_utc_today", lambda: date(2026, 10, 14))
    r = arm_query_teammates("Rillaboom", source="showdown", allow_live=False)
    assert r.as_of.period_end == "2026-09-30"
    assert r.as_of.extracted_at == "2026-10-05T23:13:53Z"
    assert r.as_of.age_days == 14  # 09-30 -> 10-14; extracted_at would give 9


@pytest.mark.parametrize(
    ("month", "end"),
    [
        ("2026-09", "2026-09-30"),
        ("2026-02", "2026-02-28"),
        ("2028-02", "2028-02-29"),
        ("2026-12", "2026-12-31"),
    ],
)
def test_period_end_is_the_calendar_last_day(month, end):
    assert period_end_for_month(month) == end


def test_malformed_showdown_month_gives_unknown_age_and_a_caveat(monkeypatch):
    monkeypatch.setattr(
        arm, "load_usage", lambda reg: {"meta": {"showdown_month": "bogus"}}
    )
    r = arm_query_teammates("Rillaboom", source="showdown", allow_live=False)
    assert r.status == "available"
    assert (r.as_of.period_end, r.as_of.age_days) == (None, None)
    assert any("age is unknown" in c for c in r.caveats)


# --- failure and contrast ----------------------------------------------------


def test_unexpected_exception_returns_fixed_message_and_logs_the_class(
    monkeypatch, logged
):
    def boom(*_a, **_k):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(arm, "_retrieve_ingame", boom)
    r = arm_query_teammates("Rillaboom", source="ingame")
    m = arm_query_teammates_multi(["Pelipper"], source="ingame")
    for res in (r, m):
        assert (res.status, res.error_kind) == ("error", "unexpected_failure")
        assert res.message == arm.ARM_UNEXPECTED_MSG
        assert "secret" not in repr(res)
    assert [c["error"] for c in logged] == ["unexpected_failure:RuntimeError"] * 2


def test_showdown_result_is_labeled_separately_from_ingame_for_the_same_species():
    a = arm_query_teammates("Rillaboom", source="ingame", allow_live=False)
    b = arm_query_teammates("Rillaboom", source="showdown", allow_live=False)
    assert (a.used_source, b.used_source) == ("ingame", "showdown")
    assert all(r.conditional_pct is None for r in a.rows)
    assert all(r.conditional_pct is not None for r in b.rows)
    assert {r.name for r in a.rows[:5]} == H6_TOP5  # the ingame answer is unchanged


# --- registry ----------------------------------------------------------------


def test_arm_entry_points_are_registered_beside_the_teammate_entries():
    for fn in ("arm_query_teammates", "arm_query_teammates_multi"):
        assert ("recommender/arm_teammates.py", fn) in CHAMPIONS_MOD_DEFAULT_ALLOWLIST
    for fn in ("query_teammates", "query_shared_teammates"):
        assert ("recommender/teammates.py", fn) in CHAMPIONS_MOD_DEFAULT_ALLOWLIST
