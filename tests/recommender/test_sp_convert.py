"""Regression tests for EV→SP budget completion and SV writeup cache refresh."""

from __future__ import annotations

from recommender.anchor_roles import resolve_anchor_build
from recommender.bootstrap import discover_bootstrap_directions
from recommender.ids import to_id
from recommender.nodes import initialize, record_bootstrap_response
from recommender.recommend import SP_BUDGET, is_valid_spread
from recommender.resolved_builds import DEFAULT_DIR, _load, _path, get_writeup_kit
from recommender.slot_fill import build_provisional_slot
from recommender.sp_convert import _SP_BUDGET, _STATS, evs_to_sp
from recommender.state import (
    PendingSlotIntent,
    UnresolvedSlotRefinement,
    slot_fingerprint,
)
from recommender.usage_data import normalize_member_evs

BAX_RAW = {"hp": 20, "atk": 252, "def": 4, "spa": 0, "spd": 28, "spe": 204}
BAX_SP = {"hp": 3, "atk": 32, "def": 1, "spa": 0, "spd": 4, "spe": 26}
CLASSIC_RAW = {"hp": 0, "atk": 252, "def": 0, "spa": 0, "spd": 4, "spe": 252}
CLASSIC_SP = {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 2, "spe": 32}
DUAL_MAX_RAW = {"hp": 0, "atk": 252, "def": 0, "spa": 0, "spd": 0, "spe": 252}
DUAL_MAX_SP = {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}
ROLE_DEFAULT_BAX = {"hp": 12, "atk": 32, "def": 8, "spa": 0, "spd": 0, "spe": 14}
VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"


def _bootstrap_state(anchor: str):
    state = {**initialize({"format_id": VGC_MB})}
    payload = {
        "direction_text": None,
        "anchor_text": anchor,
        "pool_entries": (),
        "delegated": False,
        "ownership_mode": None,
    }
    return {**state, **record_bootstrap_response({**state, "turn_payload": payload})}


def _provisional_for(anchor: str):
    state = _bootstrap_state(anchor)
    discovery = discover_bootstrap_directions(state)
    assert discovery.clarification is None
    provisional = build_provisional_slot(
        PendingSlotIntent(
            schema_version=1,
            slot_index=0,
            species=anchor,
            target_role_decision=discovery.candidates[0].target_role_decision,
            source="bootstrap",
            evidence=discovery.candidates[0].evidence,
            base_slot_fingerprint=slot_fingerprint(state["team_draft"][0]),
        ),
        state,
    )
    assert not isinstance(provisional, UnresolvedSlotRefinement)
    return provisional


def test_sp_budget_constant_matches_recommend():
    assert _SP_BUDGET == SP_BUDGET == 66


def test_evs_to_sp_bax_max_investment_completes_to_66():
    out = evs_to_sp(BAX_RAW)
    assert out == BAX_SP
    assert sum(out.values()) == 66


def test_evs_to_sp_classic_508_spd_absorbs_both_points():
    out = evs_to_sp(CLASSIC_RAW)
    assert out == CLASSIC_SP
    assert sum(out.values()) == 66


def test_evs_to_sp_dual_max_504_not_padded():
    out = evs_to_sp(DUAL_MAX_RAW)
    assert out == DUAL_MAX_SP
    assert sum(out.values()) == 64


def test_evs_to_sp_underinvested_stays_under_budget():
    raw = {"hp": 100, "atk": 100, "def": 100, "spa": 100, "spd": 0, "spe": 0}
    assert sum(raw.values()) == 400
    out = evs_to_sp(raw)
    assert sum(out.values()) < 66
    assert out == {k: min(32, round(raw[k] / 8)) for k in _STATS}


def test_normalize_member_evs_completes_bax_and_preserves_valid_sp():
    assert normalize_member_evs(BAX_RAW) == BAX_SP
    already = {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}
    assert normalize_member_evs(already) == already


def test_resolved_builds_sv_spreads_valid_champions_unchanged():
    rows = _load(_path("champions-reg-mb", root=DEFAULT_DIR))
    sv = [r for r in rows if str(r.get("source_format") or "").startswith("sv/")]
    champions = [
        r for r in rows if str(r.get("source_format") or "").startswith("champions/")
    ]
    assert len(sv) == 16
    # Verified against live cache (plan's "89" was stale — current file has 66).
    assert len(champions) == 66
    for row in sv:
        assert is_valid_spread(row.get("spread")), row.get("species")
        assert sum((row.get("spread") or {}).values()) == 66
    for row in champions:
        assert sum((row.get("spread") or {}).values()) == 66
        assert is_valid_spread(row.get("spread"))


def test_bax_resolve_and_provisional_use_writeup_sum66_not_role_default():
    build = resolve_anchor_build("Baxcalibur")
    assert build.spread == BAX_SP
    assert sum(build.spread.values()) == 66
    assert build.spread != ROLE_DEFAULT_BAX
    assert build.source_for("evs") == "analogous_format_writeup"

    kit = get_writeup_kit("Baxcalibur", "champions-reg-mb")
    assert kit is not None
    assert kit["spread"] == BAX_SP

    provisional = _provisional_for("Baxcalibur")
    assert provisional.spread_dict() == BAX_SP
    assert "writeup" in (provisional.ability_source_label or "").lower()


def test_bax_mega_proxy_disclosure_still_accurate():
    kit = get_writeup_kit("Baxcalibur-Mega", "champions-reg-mb")
    assert kit is not None
    assert kit.get("proxy_from") == "Baxcalibur"
    assert kit["spread"] == BAX_SP
    assert is_valid_spread(kit["spread"])

    provisional = _provisional_for("Baxcalibur-Mega")
    assert provisional.spread_dict() == BAX_SP
    assert "base Baxcalibur" in (provisional.ability_source_label or "")
    assert to_id(provisional.item) != "loadeddice"
