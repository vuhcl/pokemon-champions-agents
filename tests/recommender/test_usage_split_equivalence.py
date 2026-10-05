"""B3a equivalence: load_usage after split == normalized monolith.

Allowed diffs only:
  1. top-level key rename showdown_vgc_mb → showdown_doubles
  2. addition of showdown_singles: {species: {}}
  3. meta.schema_version 3 → 4
  4. per-section meta additions (meta.section on disk files; stripped on assemble)
Nothing else. Flat species must equal merge_species_flat(ingame, showdown).
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from recommender.usage_data import USAGE_DIR, load_usage, showdown_ready
from recommender.usage_split import (
    SCHEMA_VERSION,
    assemble_from_split,
    merge_species_flat,
    normalize_monolith,
    split_monolith,
)
from scripts.extract_usage.split_usage_monolith import write_split

ROOT = Path(__file__).resolve().parents[2]
MONOLITH_FIXTURE = (
    ROOT
    / "scripts"
    / "eval"
    / "artifacts"
    / "_scratch_mc_showdown_fill"
    / "monolith_pre_b3a.v1.json"
)

# Explicit allowlist — keep in sync with module docstring.
ALLOWED_EQUIVALENCE_DIFFS = (
    "key_rename:showdown_vgc_mb->showdown_doubles",
    "added_key:showdown_singles",
    "meta.schema_version:3->4",
    "per_section_meta:meta.section_on_disk_only",
)


def _assert_deep_equal(a, b, path: str = "") -> None:
    if type(a) is not type(b):
        raise AssertionError(f"{path}: type {type(a)} != {type(b)}")
    if isinstance(a, dict):
        if set(a) != set(b):
            raise AssertionError(
                f"{path}: keys {sorted(set(a) ^ set(b))} differ "
                f"(only allowlist diffs permitted: {ALLOWED_EQUIVALENCE_DIFFS})"
            )
        for k in a:
            _assert_deep_equal(a[k], b[k], f"{path}.{k}" if path else k)
        return
    if isinstance(a, list):
        if len(a) != len(b):
            raise AssertionError(f"{path}: list len {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b)):
            _assert_deep_equal(x, y, f"{path}[{i}]")
        return
    if a != b:
        raise AssertionError(f"{path}: {a!r} != {b!r}")


def test_allowed_equivalence_diffs_documented():
    assert "key_rename:showdown_vgc_mb->showdown_doubles" in ALLOWED_EQUIVALENCE_DIFFS
    assert "meta.schema_version:3->4" in ALLOWED_EQUIVALENCE_DIFFS


def test_tiny_monolith_split_load_equivalence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mono = {
        "meta": {
            "schema_version": 3,
            "regulation": "champions-reg-mc",
            "munchstats_generated_at": "2026-09-10T00:00:00Z",
            "ingame_ladder_n": 1,
            "showdown_format": "gen9championsvgc2026regmc",
            "showdown_month": "2026-09",
            "showdown_battles": 10,
            "showdown_rating": 1500,
            "sources": ["munchstats-champions-data", "smogon-chaos"],
        },
        "ingame_doubles": {
            "species": {
                "a": {
                    "id": "a",
                    "name": "A",
                    "common_moves": [{"name": "Tackle", "pct": 10.0}],
                    "common_items": [],
                    "common_abilities": [],
                    "teammates": [],
                    "top_spreads": [],
                    "featured_sets": [],
                    "source": "munchstats-champions-data",
                }
            }
        },
        "showdown_vgc_mb": {
            "species": {
                "b": {
                    "id": "b",
                    "name": "B",
                    "common_moves": [{"name": "Surf", "pct": 80.0}],
                    "common_items": [],
                    "common_abilities": [],
                    "teammates": [{"name": "A", "weight": 1}],
                    "teammates_meta": {"source_field": "Teammates"},
                    "top_spreads": [],
                    "featured_sets": [],
                    "source": "smogon-chaos",
                    "usage_pct": 5.0,
                }
            }
        },
        "species": {},
    }
    # Committed flat must match merge_species_flat
    mono["species"] = merge_species_flat(
        mono["ingame_doubles"]["species"], mono["showdown_vgc_mb"]["species"]
    )
    expected = normalize_monolith(copy.deepcopy(mono))
    write_split(mono, usage_dir=tmp_path, tag="champions-reg-mc")

    monkeypatch.setattr("recommender.usage_data.USAGE_DIR", tmp_path)
    load_usage.cache_clear()
    after = load_usage("champions-reg-mc")
    _assert_deep_equal(expected, after)
    assert after["meta"]["schema_version"] == SCHEMA_VERSION
    assert "showdown_vgc_mb" not in after
    assert after["showdown_singles"] == {"species": {}}
    assert after["species"] == merge_species_flat(
        after["ingame_doubles"]["species"], after["showdown_doubles"]["species"]
    )


@pytest.mark.skipif(not MONOLITH_FIXTURE.exists(), reason="pre-B3a monolith scratch fixture absent")
def test_real_mc_monolith_vs_split_files():
    """Local-only: species/flat vs pre-B3a scratch. Meta labels may differ after B3b."""
    mono = json.loads(MONOLITH_FIXTURE.read_text(encoding="utf-8"))
    # Flat equality vs merge (committed monolith must already satisfy this).
    assert mono["species"] == merge_species_flat(
        mono["ingame_doubles"]["species"], mono["showdown_vgc_mb"]["species"]
    )
    load_usage.cache_clear()
    after = load_usage("champions-reg-mc")
    assert after["ingame_doubles"]["species"] == mono["ingame_doubles"]["species"]
    # Spread rows may gain pct_kind labels post-B3b; pct values must match.
    before_sd = mono["showdown_vgc_mb"]["species"]
    after_sd = after["showdown_doubles"]["species"]
    assert set(after_sd) == set(before_sd)
    for sid, brow in before_sd.items():
        arow = after_sd[sid]
        for i, bs in enumerate(brow.get("top_spreads") or []):
            assert arow["top_spreads"][i]["pct"] == bs["pct"]
    assert showdown_ready("champions-reg-mc")
    assert after["meta"]["schema_version"] == 4
    assert len(after["species"]) == 343
    assert len(after["ingame_doubles"]["species"]) == 260
    assert len(after["showdown_doubles"]["species"]) == 316


def test_committed_split_flat_equals_merge():
    load_usage.cache_clear()
    snap = load_usage("champions-reg-mc")
    assert snap["species"] == merge_species_flat(
        snap["ingame_doubles"]["species"], snap["showdown_doubles"]["species"]
    )
    assert (USAGE_DIR / "champions-reg-mc.ingame_doubles.v1.json").exists()
    assert (USAGE_DIR / "champions-reg-mc.showdown_doubles.v1.json").exists()
    assert not (USAGE_DIR / "champions-reg-mc.v1.json").exists()


def _independent_split_disk_asserts(mono: dict, usage_dir: Path, tag: str) -> None:
    """Expected side does NOT use split_monolith/assemble/normalize."""
    ingame_p = usage_dir / f"{tag}.ingame_doubles.v1.json"
    showdown_p = usage_dir / f"{tag}.showdown_doubles.v1.json"
    ingame_file = json.loads(ingame_p.read_text(encoding="utf-8"))
    showdown_file = json.loads(showdown_p.read_text(encoding="utf-8"))
    union_meta = set(ingame_file["meta"]) | set(showdown_file["meta"])
    # section is disk-only; every other raw monolith meta key must appear.
    for key in mono["meta"]:
        assert key in union_meta or key == "section", f"meta key dropped: {key}"
    sd_key = "showdown_doubles" if "showdown_doubles" in mono else "showdown_vgc_mb"
    assert ingame_file["ingame_doubles"]["species"] == mono["ingame_doubles"]["species"]
    assert showdown_file["showdown_doubles"]["species"] == mono[sd_key]["species"]


def test_split_disk_independent_of_assemble(tmp_path: Path):
    mono = {
        "meta": {
            "schema_version": 3,
            "regulation": "champions-reg-mc",
            "munchstats_generated_at": "2026-09-10T00:00:00Z",
            "ingame_ladder_n": 1,
            "showdown_format": "gen9championsvgc2026regmc",
            "showdown_month": "2026-09",
            "showdown_battles": 10,
            "sources": ["munchstats-champions-data", "smogon-chaos"],
            "attribution": "both",
        },
        "ingame_doubles": {
            "species": {
                "a": {"id": "a", "name": "A", "common_moves": [], "source": "ingame"}
            }
        },
        "showdown_vgc_mb": {
            "species": {
                "b": {"id": "b", "name": "B", "common_moves": [], "source": "smogon-chaos"}
            }
        },
        "species": {},
    }
    write_split(mono, usage_dir=tmp_path, tag="champions-reg-mc")
    _independent_split_disk_asserts(mono, tmp_path, "champions-reg-mc")


def test_independent_asserts_catch_dropped_meta_and_species(tmp_path: Path, monkeypatch):
    """Red-first record: broken split fails independent asserts; fixed split passes."""
    mono = {
        "meta": {
            "schema_version": 3,
            "regulation": "champions-reg-mc",
            "munchstats_generated_at": "2026-09-10T00:00:00Z",
            "showdown_format": "gen9championsvgc2026regmc",
            "showdown_month": "2026-09",
            "sources": ["munchstats-champions-data", "smogon-chaos"],
        },
        "ingame_doubles": {
            "species": {"a": {"id": "a", "name": "A", "common_moves": [], "source": "i"}}
        },
        "showdown_vgc_mb": {
            "species": {"b": {"id": "b", "name": "B", "common_moves": [], "source": "s"}}
        },
        "species": {},
    }

    def broken_split(monolith):
        ingame_f, sd_f = split_monolith(monolith)
        ingame_f["meta"].pop("munchstats_generated_at", None)
        sd_f["showdown_doubles"]["species"] = {}
        return ingame_f, sd_f

    monkeypatch.setattr(
        "scripts.extract_usage.split_usage_monolith.split_monolith", broken_split
    )
    write_split(mono, usage_dir=tmp_path, tag="champions-reg-mc")
    with pytest.raises(AssertionError):
        _independent_split_disk_asserts(mono, tmp_path, "champions-reg-mc")

    monkeypatch.undo()
    # Fresh dir for green path
    green = tmp_path / "green"
    green.mkdir()
    write_split(mono, usage_dir=green, tag="champions-reg-mc")
    _independent_split_disk_asserts(mono, green, "champions-reg-mc")


def test_assemble_showdown_meta_overwrites_sources():
    ingame = {
        "meta": {
            "regulation": "champions-reg-mc",
            "sources": ["munchstats-champions-data", "smogon-chaos"],
            "attribution": "ingame text",
        },
        "ingame_doubles": {"species": {}},
    }
    showdown = {
        "meta": {
            "regulation": "champions-reg-mc",
            "sources": ["smogon-chaos"],
            "attribution": "showdown text",
            "showdown_month": "2026-09",
        },
        "showdown_doubles": {"species": {}},
    }
    snap = assemble_from_split(ingame, showdown)
    assert snap["meta"]["sources"] == ["smogon-chaos"]
    assert snap["meta"]["attribution"] == "showdown text"
