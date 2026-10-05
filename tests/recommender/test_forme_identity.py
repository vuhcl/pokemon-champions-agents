"""Forme identity classifier + pool/usage collapse."""

from __future__ import annotations

from recommender.forme_identity import (
    canonical_usage_species_id,
    classify_forme,
    should_skip_pool_member,
)
from recommender.legality import load_snapshot
from recommender.role_compendium import (
    REDIRECTION_CRITERIA,
    _offline_usage_row,
    _pool_index,
    construct_role_category,
    legal_species_pool,
)
from recommender.role_compendium_usage import _showdown_entry


REG = "champions-reg-mc"


def test_classify_cosmetic_locked_examples():
    snap = load_snapshot()
    for sid in (
        "mausholdfour",
        "vivillonfancy",
        "vivillonpokeball",
        "polteageistantique",
        "sinistchamasterpiece",
    ):
        assert classify_forme(snap, sid, regulation=REG) == "cosmetic"


def test_classify_battle_transform_blade_and_castform():
    snap = load_snapshot()
    assert classify_forme(snap, "aegislashblade", regulation=REG) == "battle_transform"
    assert classify_forme(snap, "castformsunny", regulation=REG) == "battle_transform"


def test_classify_mechanical_gourgeist_and_toxtricity():
    snap = load_snapshot()
    assert (
        classify_forme(snap, "gourgeistlarge", regulation=REG)
        == "mechanical_selectable"
    )
    assert (
        classify_forme(snap, "gourgeistsuper", regulation=REG)
        == "mechanical_selectable"
    )
    assert (
        classify_forme(snap, "toxtricitylowkey", regulation=REG)
        == "mechanical_selectable"
    )


def test_pool_skips_cosmetics_and_blade_keeps_gourgeist():
    snap = load_snapshot()
    pool = legal_species_pool(snap)
    idx = _pool_index(pool, snap, regulation=REG)
    assert "mausholdfour" not in idx
    assert "vivillonpokeball" not in idx
    assert "aegislashblade" not in idx
    assert "maushold" in idx
    assert "vivillon" in idx
    assert "aegislash" in idx
    assert "gourgeistsuper" in idx
    assert "gourgeistlarge" in idx


def test_usage_canonicalize_four_inherits_maushold_follow_me():
    snap = load_snapshot()
    assert canonical_usage_species_id(snap, "mausholdfour", regulation=REG) == "maushold"
    row = _offline_usage_row("mausholdfour", regulation=REG, snap=snap)
    # M-C may lack maushold offline — still stamp collapse when base resolves.
    if row is not None:
        assert row.get("forme_usage_canonical_id") == "maushold"
        assert row.get("forme_usage_collapsed_from") == "mausholdfour"
    # Showdown path likewise collapses.
    cache: dict = {}
    sd = _showdown_entry(
        "Maushold-Four",
        cache=cache,
        showdown_fetch=None,
        regulation=REG,
        snap=snap,
    )
    if sd is not None:
        assert sd.get("forme_usage_canonical_id") == "maushold"


def test_gourgeist_sizes_do_not_cross_borrow():
    """Mechanical sizes keep own id — Super must not canonicalize to base."""
    snap = load_snapshot()
    assert (
        canonical_usage_species_id(snap, "gourgeist", regulation=REG) == "gourgeist"
    )
    assert (
        canonical_usage_species_id(snap, "gourgeistsuper", regulation=REG)
        == "gourgeistsuper"
    )
    assert not should_skip_pool_member(
        snap, "gourgeistsuper", regulation=REG, pool_ids={"gourgeist", "gourgeistsuper"}
    )


def test_redirection_construct_excludes_cosmetic_formes():
    snap = load_snapshot()
    pool = legal_species_pool(snap)
    draft = construct_role_category(
        "redirection",
        REDIRECTION_CRITERIA,
        pool,
        snap=snap,
        live_fetch=None,
        showdown_fetch=None,
        regulation=REG,
    )
    ids = {c.species_id for c in draft.candidates}
    assert "vivillonpokeball" not in ids
    assert "vivillonfancy" not in ids
    assert "sinistchamasterpiece" not in ids
    assert "mausholdfour" not in ids


def test_should_skip_requires_base_in_pool():
    snap = load_snapshot()
    assert should_skip_pool_member(
        snap, "vivillonpokeball", regulation=REG, pool_ids={"vivillon"}
    )
    assert not should_skip_pool_member(
        snap, "vivillonpokeball", regulation=REG, pool_ids=set()
    )
