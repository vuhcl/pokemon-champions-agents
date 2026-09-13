"""Usage archive fallback: prefer MC file when present; else fall back to MB."""

from __future__ import annotations

from pathlib import Path

from recommender.usage_data import USAGE_DIR, load_usage, load_vgcpastes_builds

MC_PATH = USAGE_DIR / "champions-reg-mc.v1.json"


def test_load_usage_prefers_mc_file_when_present():
    load_usage.cache_clear()
    mb = load_usage("champions-reg-mb")
    mc_tag = load_usage("champions-reg-mc")
    current_mod = load_usage("champions")
    mb_n = len(mb.get("species") or {})
    assert mb_n > 0
    if MC_PATH.exists():
        assert (mc_tag.get("meta") or {}).get("regulation") == "champions-reg-mc"
        assert len(mc_tag.get("species") or {}) > 0
        # Real M-C snapshot — not an archive alias of M-B.
        assert len(mc_tag.get("species") or {}) != mb_n or (
            (mc_tag.get("meta") or {}).get("sources")
            != (mb.get("meta") or {}).get("sources")
        )
        assert len(current_mod.get("species") or {}) == len(mc_tag.get("species") or {})
    else:
        assert len(mc_tag.get("species") or {}) == mb_n
        assert len(current_mod.get("species") or {}) == mb_n
        assert len((mc_tag.get("ingame_doubles") or {}).get("species") or {}) == len(
            (mb.get("ingame_doubles") or {}).get("species") or {}
        )


def test_load_usage_falls_back_to_mb_when_mc_missing(tmp_path: Path, monkeypatch):
    """With MC file absent from the usage dir, MC tags archive-fall to MB."""
    import recommender.usage_data as ud

    mb_src = USAGE_DIR / "champions-reg-mb.v1.json"
    assert mb_src.exists()
    fake = tmp_path / "usage"
    fake.mkdir()
    (fake / "champions-reg-mb.v1.json").write_bytes(mb_src.read_bytes())
    # Intentionally no champions-reg-mc.v1.json
    monkeypatch.setattr(ud, "USAGE_DIR", fake)
    ud.load_usage.cache_clear()
    mb = ud.load_usage("champions-reg-mb")
    mc = ud.load_usage("champions-reg-mc")
    assert len(mb.get("species") or {}) > 0
    assert len(mc.get("species") or {}) == len(mb.get("species") or {})
    ud.load_usage.cache_clear()


def test_load_vgcpastes_falls_back_to_mb_for_mc_tags():
    load_vgcpastes_builds.cache_clear()
    mb = load_vgcpastes_builds("champions-reg-mb")
    mc_tag = load_vgcpastes_builds("champions-reg-mc")
    current_mod = load_vgcpastes_builds("champions")
    mb_n = len(mb.get("teams") or [])
    assert mb_n > 0
    assert len(mc_tag.get("teams") or []) == mb_n
    assert len(current_mod.get("teams") or []) == mb_n
