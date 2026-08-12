#!/usr/bin/env python3
"""Discovery: shared-role redundancy + usage divergence on team-composition sources.

Read-only over:
  data/team-composition/champions-reg-mb.v1.json                  (pokemon-zone)
  data/team-composition/champions-reg-mb.pikalytics-team-usage.v1.json
  data/usage/champions-reg-mb.v1.json
  data/roles/*.v1.json
  data/moves/flags.v1.json

Writes:
  docs/artifacts/primary_function_backup_redundancy_calibration_2026-08-12.json
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PZ = ROOT / "data" / "team-composition" / "champions-reg-mb.v1.json"
PIKA = ROOT / "data" / "team-composition" / "champions-reg-mb.pikalytics-team-usage.v1.json"
USAGE = ROOT / "data" / "usage" / "champions-reg-mb.v1.json"
ROLES = ROOT / "data" / "roles"
FLAGS = ROOT / "data" / "moves" / "flags.v1.json"
OUT = ROOT / "docs" / "artifacts" / "primary_function_backup_redundancy_calibration_2026-08-12.json"

# Mechanism move/ability ids already used by role machinery / compendia — not a new taxonomy.
_MECH_TAGS: dict[str, str] = {
    "drizzle": "provides_rain",
    "raindance": "provides_rain",
    "drought": "provides_sun",
    "orichalcumpulse": "provides_sun",
    "sunnyday": "provides_sun",
    "sandstream": "provides_sand",
    "sandstorm": "provides_sand",
    "snowwarning": "provides_snow",
    "snowscape": "provides_snow",
    "trickroom": "provides_trick_room",
    "tailwind": "provides_tailwind",
    "followme": "provides_redirection",
    "ragepowder": "provides_redirection",
    "lightscreen": "provides_screens",
    "reflect": "provides_screens",
    "auroraveil": "provides_screens",
    "willowisp": "disruption_status",
    "encore": "disruption_status",
    "disable": "disruption_status",
    "taunt": "disruption_status",
    "quash": "disruption_speed",
    "fakeout": "disruption_priority",
    "wideguard": "support_protection",
    "quickguard": "support_protection",
    "protect": "support_protection",
    "helpinghand": "support_ally",
    "coaching": "support_ally",
    "lifedew": "support_ally",
    "painsplit": "support_ally",
}


def to_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def load_role_sets() -> dict[str, set[str]]:
    """role_id → species ids from shipped role compendia."""
    out: dict[str, set[str]] = {}
    mapping = {
        "weather_setter_rain.v1.json": "rain_setter",
        "weather_setter_sun.v1.json": "sun_setter",
        "weather_setter_sand.v1.json": "sand_setter",
        "weather_setter_snow.v1.json": "snow_setter",
        "trick_room_setter.v1.json": "trick_room_setter",
        "redirection.v1.json": "redirection",
    }
    for fname, role in mapping.items():
        path = ROLES / fname
        data = json.loads(path.read_text())
        ids: set[str] = set()
        for tier_list in (data.get("tiers") or {}).values():
            for name in tier_list:
                ids.add(to_id(name))
        out[role] = ids
    return out


def usage_index(usage: dict) -> dict[str, dict]:
    """Prefer in-game doubles row; fall back to top-level species / showdown."""
    idx: dict[str, dict] = {}
    for block_key in ("ingame_doubles", "showdown_vgc_mb"):
        block = usage.get(block_key) or {}
        species = block.get("species") or {}
        for sid, row in species.items():
            idx.setdefault(to_id(sid), row)
    for sid, row in (usage.get("species") or {}).items():
        idx.setdefault(to_id(sid), row)
    return idx


def build_profile(row: dict | None, move_cat: dict[str, str]) -> dict:
    if not row:
        return {
            "present": False,
            "tags": {},
            "top_moves": [],
            "top_items": [],
            "top_abilities": [],
            "damaging_share": None,
            "status_share": None,
        }
    moves = row.get("common_moves") or []
    items = row.get("common_items") or []
    abilities = row.get("common_abilities") or []
    tags: dict[str, float] = defaultdict(float)
    dmg = status = 0.0
    for m in moves:
        mid = to_id(m["name"])
        pct = float(m.get("pct") or 0.0)
        cat = move_cat.get(mid, "Unknown")
        if cat in ("Physical", "Special"):
            tags[f"category_{cat.lower()}"] += pct
            dmg += pct
        elif cat == "Status":
            tags["category_status"] += pct
            status += pct
        mech = _MECH_TAGS.get(mid)
        if mech:
            tags[mech] += pct
    for a in abilities:
        aid = to_id(a["name"])
        pct = float(a.get("pct") or 0.0)
        mech = _MECH_TAGS.get(aid)
        if mech:
            tags[mech] += pct
        # offense-leaning items are observed, not invented buckets
    for it in items[:5]:
        tags[f"item:{to_id(it['name'])}"] += float(it.get("pct") or 0.0)
    total = dmg + status
    return {
        "present": True,
        "tags": dict(tags),
        "top_moves": [{"name": m["name"], "pct": m.get("pct")} for m in moves[:8]],
        "top_items": [{"name": i["name"], "pct": i.get("pct")} for i in items[:5]],
        "top_abilities": [{"name": a["name"], "pct": a.get("pct")} for a in abilities[:3]],
        "damaging_share": round(dmg / total, 3) if total else None,
        "status_share": round(status / total, 3) if total else None,
    }


def jaccard_tags(a: dict[str, float], b: dict[str, float], min_pct: float = 15.0) -> dict:
    """Divergence on tags each species shows at ≥min_pct in usage (derived, not invented)."""
    sa = {k for k, v in a.items() if v >= min_pct and not k.startswith("item:")}
    sb = {k for k, v in b.items() if v >= min_pct and not k.startswith("item:")}
    inter = sa & sb
    union = sa | sb
    j = (len(inter) / len(union)) if union else None
    return {
        "shared_tags": sorted(inter),
        "a_only_tags": sorted(sa - sb),
        "b_only_tags": sorted(sb - sa),
        "jaccard": None if j is None else round(j, 3),
        "divergence": None if j is None else round(1.0 - j, 3),
    }


def offense_leaning(profile: dict) -> bool | None:
    """Coarse primary_function proxy from usage move categories only."""
    if not profile.get("present"):
        return None
    d = profile.get("damaging_share")
    s = profile.get("status_share")
    if d is None or s is None:
        return None
    return d >= 0.55


def pairs_from_cores(
    cores: list[dict],
    *,
    weight_key: str | None,
    species_key: str = "species",
) -> dict[tuple[str, str], int]:
    out: dict[tuple[str, str], int] = defaultdict(int)
    for c in cores:
        sp = sorted({to_id(x) for x in c.get(species_key) or []})
        w = int(c.get(weight_key) or 1) if weight_key else 1
        for a, b in combinations(sp, 2):
            out[(a, b)] += w
    return dict(out)


def shared_role_hits(
    pair_counts: dict[tuple[str, str], int],
    role_sets: dict[str, set[str]],
    *,
    total_weight: int,
    min_count: int,
) -> list[dict]:
    rows: list[dict] = []
    for role, members in role_sets.items():
        # all unordered pairs inside the role set that appear in data
        for a, b in combinations(sorted(members), 2):
            key = (a, b) if a < b else (b, a)
            n = pair_counts.get(key, 0)
            if n < min_count:
                continue
            rows.append(
                {
                    "role": role,
                    "a": a,
                    "b": b,
                    "count": n,
                    "share_of_source": round(n / total_weight, 4) if total_weight else None,
                }
            )
    rows.sort(key=lambda r: (-r["count"], r["role"], r["a"], r["b"]))
    return rows


def offense_pair_stats(
    cores: list[dict],
    profiles: dict[str, dict],
    *,
    weight_key: str | None,
) -> dict:
    """How often a team carries ≥2 offense-leaning species (coarse primary_function)."""
    teams = 0
    with_2plus = 0
    weight_total = 0
    weight_2plus = 0
    top_pairs: dict[tuple[str, str], int] = defaultdict(int)
    for c in cores:
        sp = [to_id(x) for x in c.get("species") or []]
        w = int(c.get(weight_key) or 1) if weight_key else 1
        offenders = [s for s in sp if offense_leaning(profiles.get(s, {})) is True]
        teams += 1
        weight_total += w
        if len(offenders) >= 2:
            with_2plus += 1
            weight_2plus += w
            for a, b in combinations(sorted(set(offenders)), 2):
                top_pairs[(a, b)] += w
    top = [
        {"a": a, "b": b, "count": n}
        for (a, b), n in sorted(top_pairs.items(), key=lambda x: -x[1])[:25]
    ]
    return {
        "teams": teams,
        "teams_with_2plus_offense": with_2plus,
        "team_rate": round(with_2plus / teams, 4) if teams else None,
        "weighted_total": weight_total,
        "weighted_2plus": weight_2plus,
        "weighted_rate": round(weight_2plus / weight_total, 4) if weight_total else None,
        "top_offense_pairs": top,
    }


def enrich(rows: list[dict], profiles: dict[str, dict]) -> list[dict]:
    out = []
    for r in rows:
        pa = profiles.get(r["a"], {"present": False})
        pb = profiles.get(r["b"], {"present": False})
        div = jaccard_tags(pa.get("tags") or {}, pb.get("tags") or {})
        # clone-ish if high jaccard on non-shared-role tags after removing the shared provider tag
        shared_provider = {
            "rain_setter": "provides_rain",
            "sun_setter": "provides_sun",
            "sand_setter": "provides_sand",
            "snow_setter": "provides_snow",
            "trick_room_setter": "provides_trick_room",
            "redirection": "provides_redirection",
        }.get(r["role"])
        a_sec = {
            k: v
            for k, v in (pa.get("tags") or {}).items()
            if k != shared_provider and not k.startswith("item:") and v >= 15
        }
        b_sec = {
            k: v
            for k, v in (pb.get("tags") or {}).items()
            if k != shared_provider and not k.startswith("item:") and v >= 15
        }
        sec = jaccard_tags(a_sec, b_sec, min_pct=15.0)
        pattern = "unknown"
        if div["divergence"] is None:
            pattern = "missing_usage"
        elif div["divergence"] >= 0.5:
            pattern = "diverged_secondary"
        elif div["divergence"] <= 0.25:
            pattern = "near_clone"
        else:
            pattern = "partial_overlap"
        out.append(
            {
                **r,
                "usage_a": {
                    "top_moves": pa.get("top_moves"),
                    "top_items": pa.get("top_items"),
                    "top_abilities": pa.get("top_abilities"),
                    "damaging_share": pa.get("damaging_share"),
                    "status_share": pa.get("status_share"),
                },
                "usage_b": {
                    "top_moves": pb.get("top_moves"),
                    "top_items": pb.get("top_items"),
                    "top_abilities": pb.get("top_abilities"),
                    "damaging_share": pb.get("damaging_share"),
                    "status_share": pb.get("status_share"),
                },
                "tag_overlap": div,
                "secondary_tag_overlap_excluding_shared_provider": sec,
                "pattern": pattern,
            }
        )
    return out


def main() -> int:
    if not PIKA.is_file():
        print(f"missing {PIKA}; run fetch_pikalytics_team_usage.py first", file=sys.stderr)
        return 1
    pz = json.loads(PZ.read_text())
    pika = json.loads(PIKA.read_text())
    usage = json.loads(USAGE.read_text())
    flags = json.loads(FLAGS.read_text())
    move_cat = {mid: (row.get("category") or "Unknown") for mid, row in (flags.get("moves") or {}).items()}
    role_sets = load_role_sets()
    uidx = usage_index(usage)
    profiles = {sid: build_profile(row, move_cat) for sid, row in uidx.items()}
    # also ensure role members get a profile slot even if absent
    for members in role_sets.values():
        for sid in members:
            profiles.setdefault(sid, build_profile(None, move_cat))

    pz_pairs = {(p["a"], p["b"]) if p["a"] < p["b"] else (p["b"], p["a"]): p["count"] for p in pz["pairs"]}
    # re-derive from cores too (same as stored pairs for zone)
    pz_from_cores = pairs_from_cores(pz["cores"], weight_key=None)
    pika_pairs = pairs_from_cores(pika["cores"], weight_key="uses")
    pz_total = len(pz["cores"])
    pika_total = int(pika["meta"].get("total_teams") or sum(c["uses"] for c in pika["cores"]))

    pz_shared = enrich(
        shared_role_hits(pz_from_cores, role_sets, total_weight=pz_total, min_count=1),
        profiles,
    )
    pika_shared = enrich(
        shared_role_hits(pika_pairs, role_sets, total_weight=pika_total, min_count=3),
        profiles,
    )

    # summary rates: any team with ≥2 members of same condition-provider role
    provider_tag = {
        "rain_setter": "provides_rain",
        "sun_setter": "provides_sun",
        "sand_setter": "provides_sand",
        "snow_setter": "provides_snow",
        "trick_room_setter": "provides_trick_room",
        "redirection": "provides_redirection",
    }

    def usage_confirms_provider(sid: str, role: str, min_pct: float = 15.0) -> bool:
        """Require the shared provider tag at ≥min_pct in usage — gates multi-role inflate."""
        tag = provider_tag.get(role)
        if not tag:
            return False
        return float((profiles.get(sid) or {}).get("tags", {}).get(tag) or 0.0) >= min_pct

    def redundancy_rate(cores: list[dict], weight_key: str | None) -> dict:
        by_role: dict[str, dict] = {}
        for role, members in role_sets.items():
            tw = hitw = hitw_confirmed = 0
            examples: dict[tuple[str, str], int] = defaultdict(int)
            confirmed_examples: dict[tuple[str, str], int] = defaultdict(int)
            for c in cores:
                sp = {to_id(x) for x in c.get("species") or []}
                w = int(c.get(weight_key) or 1) if weight_key else 1
                tw += w
                hit = sorted(sp & members)
                if len(hit) >= 2:
                    hitw += w
                    for a, b in combinations(hit, 2):
                        examples[(a, b)] += w
                    confirmed = [
                        s for s in hit if usage_confirms_provider(s, role)
                    ]
                    if len(confirmed) >= 2:
                        hitw_confirmed += w
                        for a, b in combinations(confirmed, 2):
                            confirmed_examples[(a, b)] += w
            by_role[role] = {
                "weighted_teams": tw,
                "weighted_with_2plus_compendium": hitw,
                "compendium_rate": round(hitw / tw, 4) if tw else None,
                "weighted_with_2plus_usage_confirmed": hitw_confirmed,
                "usage_confirmed_rate": round(hitw_confirmed / tw, 4) if tw else None,
                "top_pairs_compendium": [
                    {"a": a, "b": b, "count": n}
                    for (a, b), n in sorted(examples.items(), key=lambda x: -x[1])[:10]
                ],
                "top_pairs_usage_confirmed": [
                    {"a": a, "b": b, "count": n}
                    for (a, b), n in sorted(
                        confirmed_examples.items(), key=lambda x: -x[1]
                    )[:10]
                ],
            }
        return by_role

    report = {
        "meta": {
            "extracted_at_note": "discovery only; no design recommendation",
            "populations": {
                "pokemon-zone": {
                    "source": pz["meta"].get("source"),
                    "source_detail": pz["meta"].get("source_detail"),
                    "population": "tournament",
                    "evidence": (
                        "README + ADR-007c: Pokemon-Zone is Limitless / pokedata tournament "
                        "data; this extract's source_detail is Limitless team-cores."
                    ),
                    "n_cores": len(pz["cores"]),
                    "core_grain": "4-species cores from /champions/team-cores/",
                    "caveat": (
                        "141 published cores, not a full team census — pair counts are "
                        "co-occurrence inside that thin core list."
                    ),
                },
                "pikalytics-team-usage": {
                    "source": pika["meta"].get("source"),
                    "population": pika["meta"].get("population"),
                    "evidence": pika["meta"].get("population_evidence"),
                    "n_cores": len(pika["cores"]),
                    "total_teams": pika_total,
                    "core_grain": "exact 6-mon (+ mega forme) tournament team groups",
                },
                "comparable_for_backup_redundancy_calibration": False,
                "comparability_reason": (
                    "Both sources are tournament / Limitless-family populations. Neither "
                    "is ladder/broad-field. They are comparable *to each other* as "
                    "tournament composition, but not sufficient alone to calibrate a "
                    "ladder-style Team-Preview backup-redundancy pattern (e.g. dual rain "
                    "setters for an unpredictable opponent pool). A lower tournament "
                    "redundancy rate does not disprove that pattern."
                ),
                "ladder_gap": (
                    "data/usage/champions-reg-mb.v1.json has ladder-weighted Showdown "
                    "teammates (top-10 per species) and in-game doubles builds, but not "
                    "full 6-mon ladder team compositions — so ladder team-level "
                    "redundancy rates are not measured here."
                ),
            },
            "divergence_method": (
                "Tags derived from usage common_moves categories (Physical/Special/Status "
                "via data/moves/flags.v1.json) plus mechanism ids already present in role "
                "machinery (_MECH_TAGS). Jaccard on tags each species shows at ≥15% usage; "
                "shared provider tag excluded for secondary-overlap. No new role taxonomy."
            ),
            "role_membership_source": "data/roles/*.v1.json compendium tiers",
            "usage_confirmed_gate": (
                "A second rate requires each of ≥2 teammates to show the shared provider "
                "tag at ≥15% in usage data. This gates multi-role inflate (e.g. Whimsicott "
                "is in sun_setter Good via Sunny Day but runs Tailwind 96.3% / Sunny Day "
                "13.4% — compendium co-occurrence with Mega Charizard Y is mostly NOT "
                "dual-sun backup)."
            ),
        },
        "pokemon_zone": {
            "condition_provider_redundancy_rates": redundancy_rate(pz["cores"], None),
            "shared_role_pairs": pz_shared,
            "offense_pair_stats": offense_pair_stats(pz["cores"], profiles, weight_key=None),
            "pattern_counts": {},
        },
        "pikalytics_team_usage": {
            "condition_provider_redundancy_rates": redundancy_rate(pika["cores"], "uses"),
            "shared_role_pairs": pika_shared,
            "offense_pair_stats": offense_pair_stats(
                pika["cores"], profiles, weight_key="uses"
            ),
            "pattern_counts": {},
        },
    }
    for key in ("pokemon_zone", "pikalytics_team_usage"):
        pc: dict[str, int] = defaultdict(int)
        for row in report[key]["shared_role_pairs"]:
            pc[row["pattern"]] += 1
        report[key]["pattern_counts"] = dict(pc)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Wrote {OUT}", file=sys.stderr)

    # smoke: known dual-rain backup must surface in the tournament census
    assert any(
        r["role"] == "rain_setter" and {r["a"], r["b"]} == {"pelipper", "sableye"}
        for r in pika_shared
    ), "expected pelipper+sableye rain_setter pair in pikalytics shared roles"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
