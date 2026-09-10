"""Partial migration: M-C identity tags still resolve to mb usage/paste files."""

from recommender.usage_data import load_usage, load_vgcpastes_builds


def test_load_usage_falls_back_to_mb_for_mc_tags():
    load_usage.cache_clear()
    mb = load_usage("champions-reg-mb")
    mc_tag = load_usage("champions-reg-mc")
    current_mod = load_usage("champions")
    mb_n = len(mb.get("species") or {})
    assert mb_n > 0
    assert len(mc_tag.get("species") or {}) == mb_n
    assert len(current_mod.get("species") or {}) == mb_n
    assert len((mc_tag.get("ingame_doubles") or {}).get("species") or {}) == len(
        (mb.get("ingame_doubles") or {}).get("species") or {}
    )


def test_load_vgcpastes_falls_back_to_mb_for_mc_tags():
    load_vgcpastes_builds.cache_clear()
    mb = load_vgcpastes_builds("champions-reg-mb")
    mc_tag = load_vgcpastes_builds("champions-reg-mc")
    current_mod = load_vgcpastes_builds("champions")
    mb_n = len(mb.get("teams") or [])
    assert mb_n > 0
    assert len(mc_tag.get("teams") or []) == mb_n
    assert len(current_mod.get("teams") or []) == mb_n
