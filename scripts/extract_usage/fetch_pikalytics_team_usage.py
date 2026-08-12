#!/usr/bin/env python3
"""Fetch Pikalytics Champions team-usage into a Pokemon-Zone-comparable schema.

Population note (verified 2026-08-12 against live API + embedded team records):
  GET /api/team-usage/championstournaments  → formatLabel "… Tournament"
  GET /api/team-usage/battledataregmbs3     → formatLabel "… Ranked Battle Data"
  Both return identical groups; every team record has source="limitless".
  This page is tournament team composition, not ladder usage.

Not merged into champions-reg-mb.v1.json (same Limitless-family population, but
different grain / extract path — keep sources separate).
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "team-composition" / "champions-reg-mb.pikalytics-team-usage.v1.json"
API = "https://www.pikalytics.com/api/team-usage/championstournaments"
UA = "pokemon-champions-agents/0.1"


def to_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def fetch(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    print(f"fetch {API}", file=sys.stderr)
    raw = fetch(API)
    groups = raw.get("groups") or []
    if not groups:
        print("no groups", file=sys.stderr)
        return 1

    sources: dict[str, int] = {}
    cores: list[dict] = []
    pairs: dict[tuple[str, str], int] = {}
    for g in groups:
        pokemon = g.get("pokemon") or []
        species = [to_id(p["name"]) for p in pokemon if p.get("name")]
        if len(species) < 2:
            continue
        uses = int(g.get("uses") or 0)
        for t in g.get("teams") or []:
            src = str(t.get("source") or "?")
            sources[src] = sources.get(src, 0) + 1
        cores.append(
            {
                "species": species,
                "uses": uses,
                "unique_players": int(g.get("uniquePlayers") or uses),
                "wins": int(g.get("wins") or 0),
                "losses": int(g.get("losses") or 0),
                "win_rate_pct": round(float(g.get("winRate") or 0.0), 2),
                "key": g.get("key"),
            }
        )
        uniq = sorted(set(species))
        for i in range(len(uniq)):
            for j in range(i + 1, len(uniq)):
                pairs[(uniq[i], uniq[j])] = pairs.get((uniq[i], uniq[j]), 0) + uses

    pair_list = [
        {"a": a, "b": b, "count": n}
        for (a, b), n in sorted(pairs.items(), key=lambda x: -x[1])
    ]
    # Keep the long tail available but cap the written pair list for readability;
    # analysis scripts can re-derive from cores if needed.
    pair_keep = [p for p in pair_list if p["count"] >= 3]

    pop = "tournament"
    if sources and set(sources) != {"limitless"}:
        pop = "mixed" if "limitless" in sources else "unknown"

    snap = {
        "meta": {
            "schema_version": 1,
            "source": "pikalytics",
            "source_detail": "team-usage API /api/team-usage/championstournaments",
            "population": pop,
            "population_evidence": {
                "page_kicker": "Tournament Team Usage",
                "format_label": raw.get("formatLabel"),
                "team_record_sources": sources,
                "note": (
                    "battledataregmbs3 format slug returns identical groups; "
                    "all team records are Limitless tournament entries."
                ),
            },
            "regulation": "champions-reg-mb",
            "format": raw.get("format"),
            "generated_at_source": raw.get("generatedAt"),
            "total_teams": int(raw.get("totalTeams") or sum(c["uses"] for c in cores)),
            "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": (
                "Species-level 6-mon team groups + uses-weighted pairs. "
                "Not merged with pokemon-zone champions-reg-mb.v1.json."
            ),
        },
        "cores": cores,
        "pairs": pair_keep,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, indent=2) + "\n")
    print(
        f"Wrote {OUT} ({len(cores)} cores, {len(pair_keep)} pairs "
        f"count>=3 / {len(pair_list)} total)",
        file=sys.stderr,
    )
    assert any(c["uses"] >= 100 for c in cores), "expected a high-use group"
    assert sources.get("limitless", 0) > 0, "expected Limitless team records"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
