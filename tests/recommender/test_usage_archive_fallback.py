"""Usage load: exact file tag only; vgcpastes still archive-fall."""

from __future__ import annotations

from pathlib import Path

from recommender.usage_data import TEAM_COMP_DIR, USAGE_DIR, load_usage, load_vgcpastes_builds

MC_INGAME_PATH = USAGE_DIR / "champions-reg-mc.ingame_doubles.v1.json"
MC_SHOWDOWN_PATH = USAGE_DIR / "champions-reg-mc.showdown_doubles.v1.json"
MC_PASTES_PATH = TEAM_COMP_DIR / "champions-reg-mc.vgcpastes-builds.v1.json"


def _mc_usage_present() -> bool:
    return MC_INGAME_PATH.exists() or MC_SHOWDOWN_PATH.exists()


def test_load_usage_prefers_mc_file_when_present():
    load_usage.cache_clear()
    mb = load_usage("champions-reg-mb")
    mc_tag = load_usage("champions-reg-mc")
    current_mod = load_usage("champions")
    mb_n = len(mb.get("species") or {})
    assert mb_n > 0
    assert _mc_usage_present()
    assert (mc_tag.get("meta") or {}).get("regulation") == "champions-reg-mc"
    assert len(mc_tag.get("species") or {}) > 0
    # Real M-C snapshot — not an archive alias of M-B.
    assert len(mc_tag.get("species") or {}) != mb_n or (
        (mc_tag.get("meta") or {}).get("sources")
        != (mb.get("meta") or {}).get("sources")
    )
    assert len(current_mod.get("species") or {}) == len(mc_tag.get("species") or {})


def test_load_usage_empty_when_tag_files_missing(tmp_path: Path, monkeypatch):
    """Exact-tag load: missing MC files → empty, not unlabeled MB (B4)."""
    import recommender.usage_data as ud

    mb_src = USAGE_DIR / "champions-reg-mb.v1.json"
    assert mb_src.exists()
    fake = tmp_path / "usage"
    fake.mkdir()
    (fake / "champions-reg-mb.v1.json").write_bytes(mb_src.read_bytes())
    # Intentionally no champions-reg-mc per-source or monolith files
    monkeypatch.setattr(ud, "USAGE_DIR", fake)
    ud.load_usage.cache_clear()
    mb = ud.load_usage("champions-reg-mb")
    mc = ud.load_usage("champions-reg-mc")
    assert len(mb.get("species") or {}) > 0
    assert mc.get("species") == {}
    assert (mc.get("showdown_doubles") or {}).get("species") == {}
    assert (mc.get("ingame_doubles") or {}).get("species") == {}
    ud.load_usage.cache_clear()


def test_load_usage_md_day0_empty_while_mc_present(tmp_path: Path, monkeypatch):
    """M-D day-0: no M-D files, M-C present → empty for M-D, full for M-C."""
    import shutil

    import recommender.usage_data as ud

    fake = tmp_path / "usage"
    fake.mkdir()
    for name in (
        "champions-reg-mc.ingame_doubles.v1.json",
        "champions-reg-mc.showdown_doubles.v1.json",
    ):
        src = USAGE_DIR / name
        if src.exists():
            shutil.copy2(src, fake / name)
    monkeypatch.setattr(ud, "USAGE_DIR", fake)
    ud.load_usage.cache_clear()
    md = ud.load_usage("champions-reg-md")
    mc = ud.load_usage("champions-reg-mc")
    assert md.get("species") == {}
    assert (md.get("showdown_doubles") or {}).get("species") == {}
    assert len(mc.get("species") or {}) > 0
    # Must not silently serve M-C under the M-D request.
    assert (mc.get("meta") or {}).get("regulation") == "champions-reg-mc"
    assert (md.get("meta") or {}) == {} or (md.get("meta") or {}).get(
        "regulation"
    ) != "champions-reg-mc"
    ud.load_usage.cache_clear()


def test_load_vgcpastes_prefers_mc_file_when_present():
    load_vgcpastes_builds.cache_clear()
    mb = load_vgcpastes_builds("champions-reg-mb")
    mc_tag = load_vgcpastes_builds("champions-reg-mc")
    current_mod = load_vgcpastes_builds("champions")
    mb_n = len(mb.get("teams") or [])
    assert mb_n > 0
    if MC_PASTES_PATH.exists():
        assert (mc_tag.get("meta") or {}).get("regulation") == "champions-reg-mc"
        assert len(mc_tag.get("teams") or []) > 0
        assert (mb.get("meta") or {}).get("regulation") != "champions-reg-mc"
        assert len(current_mod.get("teams") or []) == len(mc_tag.get("teams") or [])
    else:
        assert len(mc_tag.get("teams") or []) == mb_n
        assert len(current_mod.get("teams") or []) == mb_n


def test_load_vgcpastes_falls_back_to_mb_when_mc_missing(tmp_path: Path, monkeypatch):
    """With the M-C pastes file absent from the dir, M-C tags archive-fall to M-B."""
    import recommender.usage_data as ud

    mb_src = TEAM_COMP_DIR / "champions-reg-mb.vgcpastes-builds.v1.json"
    assert mb_src.exists()
    fake = tmp_path / "team-composition"
    fake.mkdir()
    (fake / mb_src.name).write_bytes(mb_src.read_bytes())
    monkeypatch.setattr(ud, "TEAM_COMP_DIR", fake)
    ud.load_vgcpastes_builds.cache_clear()
    mb = ud.load_vgcpastes_builds("champions-reg-mb")
    mc = ud.load_vgcpastes_builds("champions-reg-mc")
    assert len(mb.get("teams") or []) > 0
    assert len(mc.get("teams") or []) == len(mb.get("teams") or [])
    ud.load_vgcpastes_builds.cache_clear()
