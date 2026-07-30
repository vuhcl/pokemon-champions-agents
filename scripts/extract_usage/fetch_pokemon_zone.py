#!/usr/bin/env python3
"""Extract Pokemon-Zone Reg M-B team cores / co-occurrence (Track G).

Confirmed site conventions (2026-07-27, via browser — plain curl hits Cloudflare):
  /champions/                  home
  /champions/teams/            best teams (UI: Regulation M-B)
  /champions/team-cores/       cores + usage/win-rate (primary extract target)
  /champions/pokemon/<slug>/   per-species pages
  /champions/api/team-builder/import/pokemon-set/?ids=…  resolves site numeric ids → slugs

Not Smogon `vgc-2026-regulation-m-b` / Pikalytics `battledataregmbs3`.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "team-composition" / "champions-reg-mb.v1.json"
BASE = "https://www.pokemon-zone.com"
CORES_PATH = "/champions/team-cores/"
UA = "pokemon-champions-agents/0.1"


class _ImportButtons(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "button":
            return
        d = dict(attrs)
        u = d.get("data-import-url")
        if u:
            self.urls.append(u)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main() -> int:
    url = BASE + CORES_PATH
    print(f"fetch {url}", file=sys.stderr)
    try:
        html = fetch(url)
    except urllib.error.HTTPError as e:
        print(
            f"HTTP {e.code} — Cloudflare or block. Re-run via browser/MCP; "
            f"confirmed paths: /champions/teams/, /champions/team-cores/, "
            f"regulation UI label 'Regulation M-B'.",
            file=sys.stderr,
        )
        return 2
    if "Just a moment" in html or "cf-browser-verification" in html.lower():
        print("Cloudflare challenge page — stop (no invented data).", file=sys.stderr)
        return 2

    p = _ImportButtons()
    p.feed(html)
    if not p.urls:
        print("no data-import-url buttons found", file=sys.stderr)
        return 1

    cores: list[dict] = []
    for import_url in p.urls:
        m = re.search(r"ids=([0-9,]+)", import_url)
        if not m:
            continue
        ids = [int(x) for x in m.group(1).split(",") if x]
        api = import_url if import_url.startswith("http") else BASE + import_url
        if api.startswith("/"):
            api = BASE + api
        # site uses /champions/api/... 
        if "/api/" in api and "/champions/api/" not in api:
            api = api.replace("/api/", "/champions/api/", 1)
        try:
            raw = fetch(api)
            data = json.loads(raw)
        except Exception as e:
            print(f"  skip {api}: {e}", file=sys.stderr)
            continue
        species = [
            mem["pokemon"]["slug"]
            for mem in data.get("members") or []
            if mem.get("pokemon") and mem["pokemon"].get("slug")
        ]
        cores.append({"species": species, "site_ids": ids})

    pairs: dict[tuple[str, str], int] = {}
    for c in cores:
        s = sorted(set(c["species"]))
        for i in range(len(s)):
            for j in range(i + 1, len(s)):
                pairs[(s[i], s[j])] = pairs.get((s[i], s[j]), 0) + 1
    pair_list = [
        {"a": a, "b": b, "count": n}
        for (a, b), n in sorted(pairs.items(), key=lambda x: -x[1])
    ]

    snap = {
        "meta": {
            "schema_version": 1,
            "source": "pokemon-zone",
            "source_detail": "Limitless",
            "regulation": "champions-reg-mb",
            "format_label": "Regulation M-B",
            "paths": {
                "home": "/champions/",
                "teams": "/champions/teams/",
                "team_cores": "/champions/team-cores/",
                "pokemon": "/champions/pokemon/<slug>/",
                "import_api": "/champions/api/team-builder/import/pokemon-set/?ids=",
            },
            "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": "Species-level co-occurrence/cores only; no spreads.",
        },
        "cores": cores,
        "pairs": pair_list,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, indent=2) + "\n")
    print(f"Wrote {OUT} ({len(cores)} cores, {len(pair_list)} pairs)", file=sys.stderr)
    assert len(cores) >= 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
