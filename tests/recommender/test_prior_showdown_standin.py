"""B4 prior Showdown stand-in helper (commit 2 — no propose/recommend wiring)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from recommender.prior_standin import (
    PRIOR_SHOWDOWN_STANDIN,
    SPREAD_SOURCE_TOKEN,
    candidate_confidence_for_standin_fields,
    default_build_set,
    previous_regulation_tag,
    standin_present_label,
    standin_reason_ref,
    standin_source_label,
)
from recommender.regulation_registry import REGULATIONS
from recommender.usage_data import USAGE_DIR, load_usage

MD = "champions-reg-md"
MC = "champions-reg-mc"


def _tiny_showdown_doc(species_rows: dict) -> dict:
    return {
        "meta": {
            "schema_version": 4,
            "regulation": MC,
            "section": "showdown_doubles",
            "showdown_format": "gen9championsvgc2026regmc",
            "showdown_month": "2026-09",
            "sources": ["smogon-chaos"],
        },
        "showdown_doubles": {"species": species_rows},
    }


def test_previous_tag_schedule_then_override():
    assert previous_regulation_tag(MC) == "champions-reg-mb"
    assert previous_regulation_tag(MD, previous_tag=MC) == MC


def test_labels_and_tokens():
    assert standin_reason_ref(MC) == f"{PRIOR_SHOWDOWN_STANDIN}:{MC}"
    assert standin_present_label("C") == "prior-reg Showdown stand-in (Reg M-C)"
    assert (
        standin_source_label(f"{PRIOR_SHOWDOWN_STANDIN}:{MC}")
        == "prior-reg Showdown stand-in (Reg M-C)"
    )
    assert standin_source_label("usage") is None
    assert SPREAD_SOURCE_TOKEN == "prior-showdown-standin"


def test_confidence_min_standin_fields_only():
    # ability alone → medium; ability+item → low (min); empty → None
    assert candidate_confidence_for_standin_fields({"ability"}) == "medium"
    assert candidate_confidence_for_standin_fields({"ability", "moves"}) == "medium"
    assert candidate_confidence_for_standin_fields({"ability", "item"}) == "low"
    assert candidate_confidence_for_standin_fields({"nature", "spread"}) == "low"
    assert candidate_confidence_for_standin_fields([]) is None


def test_standin_ability_non_standin_moves_stays_medium():
    """CHANGE 4: min over stand-in fields only — non-stand-in moves do not lower."""
    conf = candidate_confidence_for_standin_fields({"ability"})
    assert conf == "medium"


def test_md_load_usage_empty_helper_labeled(tmp_path: Path, monkeypatch):
    """M-D day-0: load_usage empty; helper returns labeled M-C stand-in."""
    import recommender.usage_data as ud

    # Fake usage dir: M-C showdown present, no M-D files.
    fake = tmp_path / "usage"
    fake.mkdir()
    src = USAGE_DIR / f"{MC}.showdown_doubles.v1.json"
    assert src.exists()
    (fake / src.name).write_bytes(src.read_bytes())

    monkeypatch.setattr(ud, "USAGE_DIR", fake)
    ud.load_usage.cache_clear()

    REGULATIONS[MD] = {
        "letter": "D",
        "mod": "championsregmd",
        "vgc_format_id": "[Gen 9 Champions] VGC 2026 Reg M-D",
        "bss_format_id": "[Gen 9 Champions] BSS Reg M-D",
        "showdown_format": "gen9championsvgc2026regmd",
    }
    try:
        md_usage = ud.load_usage(MD)
        assert md_usage.get("species") == {}
        assert (md_usage.get("showdown_doubles") or {}).get("species") == {}

        standin = default_build_set(
            "Incineroar",
            regulation=MD,
            previous_tag=MC,
            usage_dir=fake,
        )
        assert standin is not None
        assert standin.prior_tag == MC
        assert "ability" in standin.filled_fields or "moves" in standin.filled_fields
        assert standin.reason_ref.startswith(f"{PRIOR_SHOWDOWN_STANDIN}:")
        assert "prior-reg Showdown stand-in (Reg M-C)" in standin.present_label
        assert standin.entry.get("source") == PRIOR_SHOWDOWN_STANDIN
        # Never unlabeled M-C in the M-D flat map.
        assert "incineroar" not in (md_usage.get("species") or {})
    finally:
        REGULATIONS.pop(MD, None)
        ud.load_usage.cache_clear()


def test_legality_drops_illegal_ability_and_moves(tmp_path: Path):
    """Illegal prior ability/moves dropped; remaining legal fields kept."""
    fake = tmp_path / "usage"
    fake.mkdir()
    # Craft a prior row with a fake illegal ability name + mostly legal moves.
    row = {
        "name": "Incineroar",
        "id": "incineroar",
        "source": "smogon-chaos",
        "common_abilities": [{"name": "NotARealAbilityXYZ", "pct": 99.0}],
        "common_items": [{"name": "Sitrus Berry", "pct": 50.0}],
        "common_moves": [
            {"name": "Fake Out", "pct": 50.0},
            {"name": "Flare Blitz", "pct": 50.0},
            {"name": "Parting Shot", "pct": 50.0},
            {"name": "Throat Chop", "pct": 40.0},
        ],
        "featured_sets": [
            {
                "item": "Sitrus Berry",
                "moves": ["Fake Out", "Flare Blitz", "Parting Shot", "Throat Chop"],
                "ability": "NotARealAbilityXYZ",
                "nature": "Adamant",
            }
        ],
        "top_spreads": [
            {
                "nature": "Adamant",
                "evs": {"hp": 4, "atk": 252, "def": 0, "spa": 0, "spd": 0, "spe": 252},
                "pct": 1.0,
                "pct_kind": "chaos_weight",
            }
        ],
    }
    (fake / f"{MC}.showdown_doubles.v1.json").write_text(
        json.dumps(_tiny_showdown_doc({"incineroar": row})),
        encoding="utf-8",
    )
    standin = default_build_set(
        "Incineroar",
        regulation=MD,
        previous_tag=MC,
        usage_dir=fake,
    )
    assert standin is not None
    assert standin.ability is None
    assert "ability" not in standin.filled_fields
    assert standin.item == "Sitrus Berry"
    assert "item" in standin.filled_fields
    assert len(standin.moves) == 4
    assert "moves" in standin.filled_fields
    assert "Throat Chop" in standin.moves


def test_legality_drops_moves_when_fewer_than_four_legal(tmp_path: Path):
    fake = tmp_path / "usage"
    fake.mkdir()
    row = {
        "name": "Incineroar",
        "id": "incineroar",
        "source": "smogon-chaos",
        "common_abilities": [{"name": "Intimidate", "pct": 99.0}],
        "common_items": [{"name": "Sitrus Berry", "pct": 50.0}],
        "common_moves": [
            {"name": "Fake Out", "pct": 50.0},
            {"name": "NotARealMoveAAA", "pct": 50.0},
            {"name": "NotARealMoveBBB", "pct": 50.0},
            {"name": "NotARealMoveCCC", "pct": 40.0},
        ],
        "featured_sets": [
            {
                "item": "Sitrus Berry",
                "moves": [
                    "Fake Out",
                    "NotARealMoveAAA",
                    "NotARealMoveBBB",
                    "NotARealMoveCCC",
                ],
                "ability": "Intimidate",
                "nature": "Adamant",
            }
        ],
        "top_spreads": [],
    }
    (fake / f"{MC}.showdown_doubles.v1.json").write_text(
        json.dumps(_tiny_showdown_doc({"incineroar": row})),
        encoding="utf-8",
    )
    standin = default_build_set(
        "Incineroar",
        regulation=MD,
        previous_tag=MC,
        usage_dir=fake,
    )
    assert standin is not None
    assert standin.ability == "Intimidate"
    assert standin.moves == ()
    assert "moves" not in standin.filled_fields
    assert candidate_confidence_for_standin_fields(standin.filled_fields) in {
        "medium",
        "low",
    }


def test_no_monolith_prior_means_mc_noop_for_mb_only(tmp_path: Path):
    """Prior of M-C is M-B; M-B has monolith only → helper returns None (CHANGE 2)."""
    fake = tmp_path / "usage"
    fake.mkdir()
    # Only M-B monolith, no showdown_doubles file.
    mb = USAGE_DIR / "champions-reg-mb.v1.json"
    assert mb.exists()
    (fake / mb.name).write_bytes(mb.read_bytes())
    standin = default_build_set(
        "Incineroar",
        regulation=MC,
        usage_dir=fake,
    )
    assert standin is None


def test_real_mc_showdown_standin_under_md():
    """Real M-C Showdown file as prior under hypothetical M-D."""
    REGULATIONS[MD] = {
        "letter": "D",
        "mod": "championsregmd",
        "vgc_format_id": "[Gen 9 Champions] VGC 2026 Reg M-D",
        "bss_format_id": "[Gen 9 Champions] BSS Reg M-D",
        "showdown_format": "gen9championsvgc2026regmd",
    }
    try:
        standin = default_build_set(
            "Incineroar",
            regulation=MD,
            previous_tag=MC,
        )
        assert standin is not None
        assert standin.ability == "Intimidate"
        assert len(standin.moves) == 4
        assert standin.item is not None
        assert PRIOR_SHOWDOWN_STANDIN in standin.reason_ref
    finally:
        REGULATIONS.pop(MD, None)


def test_mc_propose_refine_unchanged_no_standin_refs():
    """CHANGE 2 scenario B: M-C refine has usage refs, never prior_showdown_standin."""
    from recommender.propose import _refine_defaults
    from recommender.state import Attr, Slot, empty_slot

    slot = Slot(species=Attr(value="Incineroar", locked=True))
    state = {
        "team_draft": [slot, *[empty_slot() for _ in range(5)]],
        "regulation": MC,
    }
    refined, _ = _refine_defaults(slot, state, regulation=MC)
    assert refined.ability.value == "Intimidate"
    assert refined.ability.reason is not None
    assert refined.ability.reason.ref == "usage"
    assert refined.item.reason is not None
    assert refined.item.reason.ref == "usage"
    assert "prior_showdown_standin" not in str(refined)


def test_mc_recommend_no_standin_token():
    """CHANGE 2 scenario A: M-C recommend_build never emits stand-in token."""
    from recommender.recommend import recommend_build

    result = recommend_build(
        "Incineroar",
        ["Fake Out", "Flare Blitz", "Parting Shot", "Throat Chop"],
        "Sitrus Berry",
        regulation=MC,
    )
    assert result.get("ok") is True
    assert "prior_showdown_standin" not in str(result)
    assert "prior-showdown-standin" not in str(result)


def test_standin_drizzle_present_medium_disclosed():
    """Stand-in Drizzle → present=True, medium, disclosed; leak tests untouched."""
    from unittest.mock import patch

    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
    from recommender.prior_standin import PriorStandinBuild
    from recommender.role_compendium import ReverseCompendiumEvidence
    from recommender.slot_fill import writeup_ability_source_label

    standin = PriorStandinBuild(
        species="Pelipper",
        prior_tag=MC,
        prior_letter="C",
        ability="Drizzle",
        item="Damp Rock",
        nature="Bold",
        moves=("Hurricane", "Weather Ball", "Protect", "Tailwind"),
        evs={"hp": 252, "atk": 0, "def": 252, "spa": 4, "spd": 0, "spe": 0},
        filled_fields=frozenset({"ability", "item", "moves", "nature", "spread"}),
        entry={"source": PRIOR_SHOWDOWN_STANDIN, "prior_regulation": MC},
    )
    REGULATIONS[MD] = {
        "letter": "D",
        "mod": "championsregmd",
        "vgc_format_id": "[Gen 9 Champions] VGC 2026 Reg M-D",
        "bss_format_id": "[Gen 9 Champions] BSS Reg M-D",
        "showdown_format": "gen9championsvgc2026regmd",
    }
    try:
        with (
            patch("recommender.anchor_roles.featured_or_common_set", return_value=None),
            patch("recommender.prior_standin.default_build_set", return_value=standin),
            patch("recommender.anchor_roles.get_writeup_kit", return_value=None),
            patch("recommender.anchor_roles.get_writeup_ability", return_value=None),
        ):
            build = resolve_anchor_build("Pelipper", regulation=MD)
        assert build.ability == "Drizzle"
        assert build.source_for("ability") == PRIOR_SHOWDOWN_STANDIN
        decision = classify_anchor_role(
            build, compendium=ReverseCompendiumEvidence()
        )
        rain = [
            m
            for m in decision.mechanisms
            if m.kind == "automatic_condition_setting" and m.present
        ]
        assert rain
        assert all(m.confidence == "medium" for m in rain)
        assert all(m.source == PRIOR_SHOWDOWN_STANDIN for m in rain)
        assert (
            writeup_ability_source_label(standin.reason_ref)
            == "prior-reg Showdown stand-in (Reg M-C)"
        )
    finally:
        REGULATIONS.pop(MD, None)


def test_propose_standin_reason_refs_under_md(tmp_path: Path, monkeypatch):
    """Day-0 M-D propose fills from M-C showdown with stand-in ReasonRefs."""
    import recommender.usage_data as ud
    from recommender.propose import _refine_defaults
    from recommender.state import Attr, Slot, empty_slot

    fake = tmp_path / "usage"
    fake.mkdir()
    src = USAGE_DIR / f"{MC}.showdown_doubles.v1.json"
    (fake / src.name).write_bytes(src.read_bytes())
    monkeypatch.setattr(ud, "USAGE_DIR", fake)
    ud.load_usage.cache_clear()

    REGULATIONS[MD] = {
        "letter": "D",
        "mod": "championsregmd",
        "vgc_format_id": "[Gen 9 Champions] VGC 2026 Reg M-D",
        "bss_format_id": "[Gen 9 Champions] BSS Reg M-D",
        "showdown_format": "gen9championsvgc2026regmd",
    }
    try:
        monkeypatch.setattr(
            "recommender.prior_standin.previous_regulation_tag",
            lambda regulation, previous_tag=None: MC,
        )
        monkeypatch.setattr("recommender.prior_standin.USAGE_DIR", fake)
        slot = Slot(species=Attr(value="Incineroar", locked=True))
        state = {
            "team_draft": [slot, *[empty_slot() for _ in range(5)]],
            "regulation": MD,
        }
        refined, _ = _refine_defaults(slot, state, regulation=MD)
        assert refined.ability.value == "Intimidate"
        assert refined.ability.reason is not None
        assert refined.ability.reason.ref == f"prior_showdown_standin:{MC}"
        assert refined.moveset.value is not None
        assert len(refined.moveset.value) == 4
        assert refined.moveset.reason is not None
        assert refined.moveset.reason.ref == f"prior_showdown_standin:{MC}"
    finally:
        REGULATIONS.pop(MD, None)
        ud.load_usage.cache_clear()
