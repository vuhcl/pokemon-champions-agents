"""Idempotent split script + assemble round-trip."""

from __future__ import annotations

import json
from pathlib import Path

from recommender.usage_split import assemble_from_split, split_monolith
from scripts.extract_usage.split_usage_monolith import write_split

FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "eval"
    / "artifacts"
    / "_scratch_mc_showdown_fill"
    / "monolith_pre_b3a.v1.json"
)


def _tiny_monolith() -> dict:
    return {
        "meta": {
            "schema_version": 3,
            "regulation": "champions-reg-mc",
            "munchstats_generated_at": "2026-09-10T00:00:00Z",
            "showdown_format": "gen9championsvgc2026regmc",
            "showdown_month": "2026-09",
            "showdown_battles": 100,
            "sources": ["munchstats-champions-data", "smogon-chaos"],
        },
        "ingame_doubles": {
            "species": {
                "rillaboom": {
                    "id": "rillaboom",
                    "name": "Rillaboom",
                    "common_moves": [],
                    "source": "munchstats-champions-data",
                }
            }
        },
        "showdown_vgc_mb": {
            "species": {
                "rillaboom": {
                    "id": "rillaboom",
                    "name": "Rillaboom",
                    "common_moves": [{"name": "Grassy Glide", "pct": 90.0}],
                    "source": "smogon-chaos",
                }
            }
        },
        "species": {},
    }


def test_write_split_idempotent(tmp_path: Path):
    mono = _tiny_monolith()
    write_split(mono, usage_dir=tmp_path, tag="champions-reg-mc")
    a = (tmp_path / "champions-reg-mc.ingame_doubles.v1.json").read_text(encoding="utf-8")
    b = (tmp_path / "champions-reg-mc.showdown_doubles.v1.json").read_text(encoding="utf-8")
    write_split(mono, usage_dir=tmp_path, tag="champions-reg-mc")
    assert (tmp_path / "champions-reg-mc.ingame_doubles.v1.json").read_text(
        encoding="utf-8"
    ) == a
    assert (tmp_path / "champions-reg-mc.showdown_doubles.v1.json").read_text(
        encoding="utf-8"
    ) == b


def test_assemble_round_trip_from_real_monolith_fixture():
    if not FIXTURE.exists():
        return  # scratch fixture optional in CI clones
    mono = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ingame_f, sd_f = split_monolith(mono)
    assembled = assemble_from_split(ingame_f, sd_f)
    assert len(assembled["ingame_doubles"]["species"]) == len(
        mono["ingame_doubles"]["species"]
    )
    assert len(assembled["showdown_doubles"]["species"]) == len(
        mono["showdown_vgc_mb"]["species"]
    )
    assert len(assembled["species"]) == len(mono["species"])
