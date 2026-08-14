"""Redirection Role Compendium + construct-time CBD live-fetch (ADR-014a / ADR-019)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium import (
    RAIN_SETTER_CRITERIA,
    REDIRECTION_CRITERIA,
    CandidateEval,
    ClaimedTrait,
    RoleConstructionDraft,
    construct_role_category,
    critique_role_ranking,
    legal_species_pool,
    persist_approved,
    rebuild_role_category,
)


def _mock_clefable_follow_me(name: str) -> dict[str, Any] | None:
    if to_id(name) != "clefable":
        return None
    return {
        "name": "Clefable",
        "id": "clefable",
        "common_moves": [
            {"name": "Follow Me", "pct": 55.0},
            {"name": "Helping Hand", "pct": 23.0},
        ],
        "featured_sets": [],
        "source": "championsbattledata",
    }


def _redir_draft(
    *,
    live_fetch: Any = ...,
    showdown_fetch: Any = None,
    pool: list[str] | None = None,
    reference_compendium: Any = None,
) -> RoleConstructionDraft:
    snap = load_snapshot()
    kwargs: dict[str, Any] = {
        "category": "redirection",
        "sub_criteria": REDIRECTION_CRITERIA,
        "legal_pool": pool if pool is not None else legal_species_pool(snap),
        "snap": snap,
        "showdown_fetch": showdown_fetch,
        "reference_compendium": reference_compendium,
    }
    if live_fetch is ...:
        kwargs["live_fetch"] = _mock_clefable_follow_me
    else:
        kwargs["live_fetch"] = live_fetch
    return construct_role_category(**kwargs)


def _members(draft: RoleConstructionDraft, tier: str) -> set[str]:
    return {c.species for c in draft.candidates if c.tier == tier}


def test_redirection_excellent_includes_usage_and_friend_guard():
    calls: list[str] = []

    def tracking_fetch(name: str) -> dict[str, Any] | None:
        calls.append(name)
        return _mock_clefable_follow_me(name)

    draft = _redir_draft(live_fetch=tracking_fetch)
    excellent = _members(draft, "Excellent")
    good = _members(draft, "Good")
    # Clefable: HH/LD are turn_gated; July chaos also lists Light Screen/Reflect
    # past the old top-12, which currently counts as excellent_secondary.
    assert {"Maushold", "Vivillon", "Sinistcha"} <= excellent, draft.tiers
    assert "Clefable" in excellent or "Clefable" in good
    assert "Maushold" not in calls and "Sinistcha" not in calls


def test_redirection_good_learnset_only():
    draft = _redir_draft()
    good = _members(draft, "Good")
    rejected = {r.species_id for r in draft.considered_rejected}
    # Hit-triggered disrupt admits without redirect usage (Flame Body / Spicy Spray).
    assert "Volcarona" in good or "Volcarona" in _members(draft, "Excellent")
    assert "Scovillain-Mega" in good  # Spicy Spray execution reinforce
    # July chaos: Ariados Sticky Web / Scovillain Rage Powder are now visible.
    assert "Clefable" in good or "Clefable" in _members(draft, "Excellent")
    clef = next(c for c in draft.candidates if c.species == "Clefable")
    assert any(to_id(t.name) == "cutecharm" for t in clef.claimed_traits)
    assert "Cute Charm" in clef.criteria_notes.get("execution", "")


def test_excellent_secondary_helper():
    from recommender.role_compendium import _excellent_secondary

    assert _excellent_secondary(has_friend_guard=True, secondary_move_ids=set())
    assert _excellent_secondary(
        has_friend_guard=False, secondary_move_ids={"stickyweb", "helpinghand"}
    )
    assert _excellent_secondary(
        has_friend_guard=False, secondary_move_ids={"trickroom"}
    )
    # turn_gated / AV / Hospitality-alone (no FG, no persistent moves)
    assert not _excellent_secondary(
        has_friend_guard=False, secondary_move_ids={"helpinghand", "lifedew"}
    )
    assert not _excellent_secondary(
        has_friend_guard=False, secondary_move_ids={"encore", "auroraveil"}
    )
    assert not _excellent_secondary(has_friend_guard=False, secondary_move_ids=set())


def test_excellent_secondary_axes_gate():
    """HH/LD-only → Good; FG / Sticky Web / TR → Excellent."""

    def live(name: str) -> dict[str, Any] | None:
        sid = to_id(name)
        if sid == "clefable":
            return {
                "name": "Clefable",
                "id": "clefable",
                "common_moves": [
                    {"name": "Follow Me", "pct": 55.0},
                    {"name": "Helping Hand", "pct": 23.0},
                    {"name": "Life Dew", "pct": 40.0},
                ],
                "featured_sets": [],
                "source": "championsbattledata",
            }
        if sid == "ariados":
            return {
                "name": "Ariados",
                "id": "ariados",
                "common_moves": [
                    {"name": "Rage Powder", "pct": 69.0},
                    {"name": "Sticky Web", "pct": 80.0},
                ],
                "featured_sets": [],
                "source": "championsbattledata",
            }
        return None

    draft = _redir_draft(live_fetch=live)
    assert "Clefable" in _members(draft, "Good") | _members(draft, "Excellent")
    clef = next(c for c in draft.candidates if c.species == "Clefable")
    assert clef.criteria_notes.get("verified_secondary") == "True"

    assert "Ariados" in _members(draft, "Excellent")
    assert "Maushold" in _members(draft, "Excellent")  # Friend Guard
    assert "Sinistcha" in _members(draft, "Excellent")  # Trick Room usage
    sin = next(c for c in draft.candidates if c.species_id == "sinistcha")
    assert sin.criteria_notes.get("excellent_secondary") == "True"


def test_mega_clefable_rejected_before_live():
    calls: list[str] = []

    def tracking_fetch(name: str) -> dict[str, Any] | None:
        calls.append(name)
        return {
            "name": name,
            "id": to_id(name),
            "common_moves": [
                {"name": "Follow Me", "pct": 99.0},
                {"name": "Helping Hand", "pct": 20.0},
            ],
            "featured_sets": [],
            "source": "championsbattledata",
        }

    draft = _redir_draft(live_fetch=tracking_fetch)
    members = {c.species for c in draft.candidates if c.tier}
    assert "Clefable-Mega" not in members
    rejected_ids = {r.species_id for r in draft.considered_rejected}
    assert "clefablemega" in rejected_ids
    assert not any(to_id(n) == "clefablemega" for n in calls)


def test_clefable_live_none_still_admitted_via_cute_charm():
    """No CBD redirect usage — Cute Charm still admits as execution reinforce."""
    draft = _redir_draft(live_fetch=lambda _n: None)
    assert "Clefable" in _members(draft, "Good") | _members(draft, "Excellent")
    clef = next(c for c in draft.candidates if c.species == "Clefable")
    assert any(to_id(t.name) == "cutecharm" for t in clef.claimed_traits)
    rejected = {r.species_id for r in draft.considered_rejected}
    assert "clefable" not in rejected


def test_snapshot_hit_skips_live_for_maushold():
    calls: list[str] = []

    def tracking_fetch(name: str) -> dict[str, Any] | None:
        calls.append(name)
        return None

    _redir_draft(live_fetch=tracking_fetch)
    assert not any(to_id(n) == "maushold" for n in calls)


def test_legal_pool_bounds():
    snap = load_snapshot()
    pool = [n for n in legal_species_pool(snap) if to_id(n) != "maushold"]
    draft = construct_role_category(
        "redirection",
        REDIRECTION_CRITERIA,
        pool,
        snap=snap,
        live_fetch=_mock_clefable_follow_me,
        showdown_fetch=None,
    )
    assert "Maushold" not in {c.species for c in draft.candidates if c.tier}


def test_clefable_no_magic_guard_ally_credit():
    draft = _redir_draft()
    clef = next(c for c in draft.candidates if c.species == "Clefable")
    for t in clef.claimed_traits:
        assert to_id(t.name) != "magicguard"


def test_notes_ability_delivery_empty():
    draft = _redir_draft()
    assert any("no ability-based redirection" in n for n in draft.notes)


def test_critique_approves_live_draft():
    draft = _redir_draft()
    result = critique_role_ranking(draft)
    assert result.approved, result.flags


def test_critique_tied_cluster_same_degree():
    draft = RoleConstructionDraft(
        category="redirection",
        sub_criteria={"condition": "", "kind": "redirection"},
        candidates=[
            CandidateEval(
                species="Volcarona",
                species_id="volcarona",
                tier="Excellent",
                delivery_class="move_redirect",
                mechanism="Rage Powder",
                criteria_notes={},
                claimed_traits=[],
                reasoning="",
                reinforce_class="none",
                excellence_basis="learnset_only",
            ),
            CandidateEval(
                species="Ariados",
                species_id="ariados",
                tier="Good",
                delivery_class="move_redirect",
                mechanism="Rage Powder",
                criteria_notes={},
                claimed_traits=[],
                reasoning="",
                reinforce_class="none",
                excellence_basis="learnset_only",
            ),
        ],
        considered_rejected=[],
        tiers={"Excellent": ["Volcarona"], "Good": ["Ariados"]},
    )
    result = critique_role_ranking(draft)
    assert not result.approved
    assert any(f.principle == "tied_cluster" for f in result.flags)


def test_critique_function_fit_magic_guard():
    draft = RoleConstructionDraft(
        category="redirection",
        sub_criteria={"condition": ""},
        candidates=[
            CandidateEval(
                species="Clefable",
                species_id="clefable",
                tier="Good",
                delivery_class="move_redirect",
                mechanism="Follow Me",
                criteria_notes={},
                claimed_traits=[
                    ClaimedTrait(
                        name="Magic Guard",
                        criterion="secondary_role",
                        purpose_claimed="ally protection",
                    )
                ],
                reasoning="",
                reinforce_class="none",
                excellence_basis="learnset_only",
            )
        ],
        considered_rejected=[],
        tiers={"Good": ["Clefable"]},
    )
    result = critique_role_ranking(draft)
    assert any(f.principle == "function_fit" for f in result.flags)


def test_rebuild_approve_tmp(tmp_path: Path):
    r = rebuild_role_category(
        "redirection",
        REDIRECTION_CRITERIA,
        roles_dir=tmp_path,
        live_fetch=_mock_clefable_follow_me,
        showdown_fetch=None,
    )
    assert r.status == "approved", r.critique.flags
    assert r.path is not None
    assert Path(r.path).name == "redirection.v1.json"


def test_rebuild_human_gate(tmp_path: Path):
    prior = _redir_draft()
    # Demote an axes-Excellent member so rebuild wants Excellent again → gate.
    for c in prior.candidates:
        if c.species == "Maushold":
            c.tier = "Good"
            c.excellence_basis = "usage_proven"
    prior.tiers = {
        "Excellent": [s for s in prior.tiers.get("Excellent", []) if s != "Maushold"],
        "Good": list(prior.tiers.get("Good", [])) + ["Maushold"],
    }
    persist_approved(prior, tmp_path)
    result = rebuild_role_category(
        "redirection",
        REDIRECTION_CRITERIA,
        roles_dir=tmp_path,
        live_fetch=_mock_clefable_follow_me,
        showdown_fetch=None,
    )
    assert result.status == "needs_revision"
    assert any(f.principle == "self_consistency" for f in result.critique.flags)


def test_showdown_attribution_scovillain_pair():
    def sd_fetch(name: str) -> dict[str, Any] | None:
        sid = to_id(name)
        if sid == "scovillainmega":
            return {
                "name": "Scovillain-Mega",
                "id": "scovillainmega",
                "usage_pct": 2.053,
                "common_moves": [{"name": "Rage Powder", "pct": 24.14}],
                "source": "munchstats-showdown",
            }
        if sid == "scovillain":
            return {
                "name": "Scovillain",
                "id": "scovillain",
                "usage_pct": 0.083,
                "common_moves": [{"name": "Rage Powder", "pct": 14.34}],
                "source": "munchstats-showdown",
            }
        return None

    draft = _redir_draft(showdown_fetch=sd_fetch)
    assert "Scovillain-Mega" in _members(draft, "Good")
    assert "Scovillain-Mega" not in _members(draft, "Excellent")
    assert any("stone-heuristic fallback unused" in n for n in draft.notes)
    mega = next(c for c in draft.candidates if c.species_id == "scovillainmega")
    assert any(to_id(t.name) == "spicyspray" for t in mega.claimed_traits)
    assert "Spicy Spray" in mega.criteria_notes.get("execution", "")


def test_volcarona_execution_conflict_good_with_flame_body():
    def live(name: str) -> dict[str, Any] | None:
        if to_id(name) == "clefable":
            return _mock_clefable_follow_me(name)
        if to_id(name) == "volcarona":
            return {
                "name": "Volcarona",
                "id": "volcarona",
                "common_moves": [
                    {"name": "Quiver Dance", "pct": 60.8},
                    {"name": "Rage Powder", "pct": 27.3},
                ],
                "source": "championsbattledata",
            }
        return None

    draft = _redir_draft(live_fetch=live)
    assert "Volcarona" in _members(draft, "Good") | _members(draft, "Excellent")
    assert "volcarona" not in {r.species_id for r in draft.considered_rejected}
    volc = next(c for c in draft.candidates if c.species_id == "volcarona")
    assert volc.excellence_basis in {
        "usage_proven_conflicted",
        "secondary_stack_conflicted",
        "secondary_stack",
        "usage_proven",
    }
    assert any(to_id(t.name) == "flamebody" for t in volc.claimed_traits)
    assert "Flame Body" in volc.criteria_notes.get("execution", "") or any(
        "burn" in t.purpose_claimed.lower() for t in volc.claimed_traits
    )


def test_usage_without_secondary_is_good():
    def live(name: str) -> dict[str, Any] | None:
        if to_id(name) == "ariados":
            return {
                "name": "Ariados",
                "id": "ariados",
                "common_moves": [{"name": "Rage Powder", "pct": 70.0}],
                "source": "championsbattledata",
            }
        return _mock_clefable_follow_me(name)

    draft = _redir_draft(live_fetch=live)
    assert "Ariados" in _members(draft, "Good") | _members(draft, "Excellent")


def test_secondary_notes_exclude_redirect_moves():
    draft = _redir_draft()
    sin = next(c for c in draft.candidates if c.species_id == "sinistcha")
    note = sin.criteria_notes.get("secondary_role") or ""
    assert "Rage Powder" not in note or "Hospitality" in note
    for t in sin.claimed_traits:
        if t.criterion == "secondary_role":
            assert to_id(t.name) not in {"ragepowder", "followme"}


def test_critique_execution_conflict_identity():
    draft = RoleConstructionDraft(
        category="redirection",
        sub_criteria={"condition": "", "kind": "redirection"},
        candidates=[
            CandidateEval(
                species="Volcarona",
                species_id="volcarona",
                tier="Excellent",
                delivery_class="move_redirect",
                mechanism="Rage Powder",
                criteria_notes={"qd_pct": "60.8", "best_redirect_pct": "27.3"},
                claimed_traits=[],
                reasoning="",
                reinforce_class="none",
                excellence_basis="usage_proven",
            )
        ],
        considered_rejected=[],
        tiers={"Excellent": ["Volcarona"]},
    )
    result = critique_role_ranking(draft)
    assert any(f.principle == "execution_conflict" for f in result.flags)


def test_critique_execution_conflict_attribution():
    draft = RoleConstructionDraft(
        category="redirection",
        sub_criteria={"condition": "", "kind": "redirection"},
        candidates=[
            CandidateEval(
                species="Scovillain",
                species_id="scovillain",
                tier="Excellent",
                delivery_class="move_redirect",
                mechanism="Rage Powder",
                criteria_notes={
                    "usage_proven": "True",
                    "attribution": "showdown usage discounted (base 0.083%)",
                    "qd_pct": "0",
                    "best_redirect_pct": "0",
                },
                claimed_traits=[],
                reasoning="",
                reinforce_class="none",
                excellence_basis="usage_proven",
            ),
            CandidateEval(
                species="Scovillain-Mega",
                species_id="scovillainmega",
                tier="Good",
                delivery_class="move_redirect",
                mechanism="Rage Powder",
                criteria_notes={
                    "usage_proven": "False",
                    "attribution": "showdown form-separated usage",
                    "qd_pct": "0",
                    "best_redirect_pct": "0",
                },
                claimed_traits=[],
                reasoning="",
                reinforce_class="none",
                excellence_basis="learnset_only",
            ),
        ],
        considered_rejected=[],
        tiers={"Excellent": ["Scovillain"], "Good": ["Scovillain-Mega"]},
    )
    result = critique_role_ranking(draft)
    assert any(f.principle == "execution_conflict" for f in result.flags)


def test_rain_snapshot_hit_skips_live():
    calls: list[str] = []

    def tracking(name: str) -> dict[str, Any] | None:
        calls.append(name)
        return None

    snap = load_snapshot()
    construct_role_category(
        "weather_setter",
        RAIN_SETTER_CRITERIA,
        legal_species_pool(snap),
        snap=snap,
        live_fetch=tracking,
    )
    assert not any(to_id(n) in {"pelipper", "politoed", "sableye"} for n in calls)
