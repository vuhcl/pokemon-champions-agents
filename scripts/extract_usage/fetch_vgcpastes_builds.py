#!/usr/bin/env python3
"""Fetch VGCPastes Champions sheet + resolve Pokepaste URLs to full builds.

Default target is Reg M-C (same workbook as M-B; Champions M-C tab):
  https://docs.google.com/spreadsheets/d/1axlwmzPA49rYkqXh7zHvAtSP-TKbM0ijGYBPRflLSWw
  gid=736919171

M-B archive remains at champions-reg-mb.vgcpastes-builds.v1.json (gid=1458357160).

Population is whatever the sheet itself claims (mixed Twitter/community +
tournament placers) — do not treat as Limitless-only like the species-level
pikalytics-team-usage extract.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = (
    ROOT / "data" / "team-composition" / "champions-reg-mc.vgcpastes-builds.v1.json"
)
CACHE = ROOT / "artifacts" / "pikalytics-pokepaste" / "pokepaste-cache"
SHEET_CSV = ROOT / "artifacts" / "pikalytics-pokepaste" / "sheet.csv"
SHEET_ID = "1axlwmzPA49rYkqXh7zHvAtSP-TKbM0ijGYBPRflLSWw"
DEFAULT_SHEET_GID = "736919171"
DEFAULT_REGULATION = "champions-reg-mc"
UA = "pokemon-champions-agents/0.1 (vgcpastes-builds)"

# Validation floors (usage-refresh discipline).
ABS_FLOOR = 100
DROP_RATIO = 0.90
DROP_ABS = 50
RESOLVE_OK_RATIO = 0.90
EV_MEMBER_RATIO = 0.50

STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")
STAT_ALIASES = {
    "hp": "hp",
    "atk": "atk",
    "def": "def",
    "spa": "spa",
    "spd": "spd",
    "spe": "spe",
}


def to_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def fetch_bytes(url: str, *, timeout: float = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def sheet_urls(sheet_id: str, gid: str) -> tuple[str, str]:
    export = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}/export"
        f"?format=csv&gid={gid}"
    )
    edit = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit?gid={gid}"
    return export, edit


def ensure_sheet_csv(*, sheet_id: str = SHEET_ID, gid: str = DEFAULT_SHEET_GID) -> Path:
    export, _ = sheet_urls(sheet_id, gid)
    SHEET_CSV.parent.mkdir(parents=True, exist_ok=True)
    print(f"fetch sheet {export}", file=sys.stderr)
    SHEET_CSV.write_bytes(fetch_bytes(export, timeout=120))
    return SHEET_CSV


def validate_vgcpastes_snapshot(
    snap: dict[str, Any],
    *,
    previous: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Return (ok|fail|noop, reason)."""
    meta = snap.get("meta") or {}
    if meta.get("schema_version") != 1:
        return "fail", "schema_version_not_1"
    teams = snap.get("teams") or []
    n = len(teams)
    if n < ABS_FLOOR:
        return "fail", f"abs_floor_{n}_lt_{ABS_FLOOR}"
    sheet_rows = int(meta.get("sheet_rows") or 0)
    resolve = meta.get("resolve_counts") or {}
    ok_6 = int(resolve.get("ok_6") or 0)
    if sheet_rows > 0 and ok_6 / sheet_rows < RESOLVE_OK_RATIO:
        return "fail", f"resolve_ok_ratio_{ok_6}_of_{sheet_rows}"
    ev = meta.get("ev_completeness") or {}
    members_total = int(ev.get("members_total") or 0)
    with_ev = int(ev.get("members_with_nonzero_evs") or 0)
    if members_total <= 0 or with_ev / members_total < EV_MEMBER_RATIO:
        return "fail", f"ev_member_ratio_{with_ev}_of_{members_total}"

    if previous is not None:
        prev_n = int((previous.get("meta") or {}).get("teams_resolved") or 0)
        if prev_n > 0:
            if n < prev_n * DROP_RATIO:
                return "fail", f"drop_ratio_{n}_lt_{prev_n}*{DROP_RATIO}"
            if (prev_n - n) > DROP_ABS:
                return "fail", f"drop_abs_{prev_n - n}_gt_{DROP_ABS}"
        prev_ids = {
            str(t.get("team_id"))
            for t in (previous.get("teams") or [])
            if t.get("team_id") is not None
        }
        new_ids = {
            str(t.get("team_id"))
            for t in teams
            if t.get("team_id") is not None
        }
        if prev_n == n and prev_ids == new_ids:
            return "noop", "teams_unchanged"

    return "ok", f"validated_n_{n}"


def load_sheet_rows(path: Path) -> tuple[dict[str, str], list[dict[str, str]], list[str]]:
    """Return (title_meta, data rows as dicts, header notes)."""
    text = path.read_text(encoding="utf-8")
    rows = list(csv.reader(text.splitlines()))
    hdr_i = next(i for i, r in enumerate(rows) if r and r[0].strip() == "Team ID")
    header = [c.strip().replace("\n", " ") for c in rows[hdr_i]]
    # Collapse duplicate empty names so DictReader-like access stays unique-ish.
    seen: dict[str, int] = {}
    cols: list[str] = []
    for c in header:
        key = c or "_empty"
        n = seen.get(key, 0)
        seen[key] = n + 1
        cols.append(key if n == 0 else f"{key}_{n}")

    title_bits = [c.strip() for c in rows[0] if c and c.strip()]
    note_bits = [c.strip() for c in rows[1] if c and c.strip()]
    meta = {
        "title_row": title_bits,
        "note_row": note_bits,
    }

    data: list[dict[str, str]] = []
    for r in rows[hdr_i + 1 :]:
        if not r or not (r[0] or "").strip():
            continue
        d = {cols[i]: (r[i].strip() if i < len(r) else "") for i in range(len(cols))}
        data.append(d)
    return meta, data, cols


def pokepaste_id(url: str) -> str | None:
    m = re.search(r"pokepast\.es/([0-9a-fA-F]+)", url)
    return m.group(1).lower() if m else None


def fetch_pokepaste(pid: str) -> dict | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / f"{pid}.json"
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))
    url = f"https://pokepast.es/{pid}/json"
    try:
        raw = fetch_bytes(url)
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} {url}", file=sys.stderr)
        return None
    except Exception as e:  # noqa: BLE001 — discovery: keep going
        print(f"  fail {url}: {e}", file=sys.stderr)
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        print(f"  bad json {url}", file=sys.stderr)
        return None
    if not isinstance(data, dict) or not data.get("paste"):
        print(f"  empty paste {url}", file=sys.stderr)
        return None
    cache_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    time.sleep(0.12)
    return data


def parse_evs(line: str) -> dict[str, int]:
    evs = {k: 0 for k in STAT_KEYS}
    body = line.split(":", 1)[1] if ":" in line else line
    for part in body.split("/"):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"(\d+)\s+(\w+)", part, re.I)
        if not m:
            continue
        n, stat = int(m.group(1)), m.group(2).lower()
        key = STAT_ALIASES.get(stat)
        if key:
            evs[key] = n
    return evs


_SPECIES_LINE = re.compile(
    r"^(?:(.+?)\s+\((.+?)\)|(.+?))(?:\s+\(([MF])\))?(?:\s+@\s+(.+))?$",
    re.I,
)


def parse_paste(paste: str) -> list[dict]:
    """Parse Showdown export paste into member dicts."""
    blocks = re.split(r"\n\s*\n", paste.replace("\r\n", "\n").strip())
    members: list[dict] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        head = lines[0].rstrip(" ")
        m = _SPECIES_LINE.match(head)
        if not m:
            continue
        nick_or_sp, in_paren, bare, gender, item = m.groups()
        if in_paren and len(in_paren) == 1 and in_paren.upper() in "MF":
            # "Charizard (M) @ Item" — first group is species, paren is gender
            species_display = (nick_or_sp or "").strip()
            gender = in_paren.upper()
        elif in_paren:
            # "Nick (Species) @ Item" or "Nick (Species) (M) @ Item"
            species_display = in_paren.strip()
        else:
            species_display = (bare or nick_or_sp or "").strip()
        if item:
            item = item.strip()

        ability = nature = None
        level = None
        evs = {k: 0 for k in STAT_KEYS}
        moves: list[str] = []
        for ln in lines[1:]:
            low = ln.lower()
            if low.startswith("ability:"):
                ability = ln.split(":", 1)[1].strip()
            elif low.startswith("level:"):
                try:
                    level = int(ln.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif low.startswith("evs:"):
                evs = parse_evs(ln)
            elif low.endswith(" nature"):
                nature = ln[: -len(" nature")].strip()
            elif ln.startswith("-"):
                moves.append(ln.lstrip("- ").strip())
            elif gender is None and ln.upper() in ("M", "F"):
                gender = ln.upper()

        if not species_display:
            continue
        members.append(
            {
                "species": to_id(species_display),
                "species_display": species_display,
                "item": item,
                "ability": ability,
                "nature": nature,
                "level": level,
                "gender": gender,
                "evs": evs,
                "moves": moves,
            }
        )
    return members


def sheet_species(row: dict[str, str]) -> list[str]:
    """Species names from the sheet's 'Pokemon Text for Copypasta' columns."""
    # After header uniquify, these are typically bare names in trailing cols.
    # Prefer explicit ordered names if present under Pokemon Text… neighbors.
    # Fallback: scan values that look like species (no URL, no empty, Team ID skip).
    names: list[str] = []
    # Columns after Owner often hold the 6 species; find Owner then take next 6 nonempty.
    keys = list(row.keys())
    if "Owner" in row:
        oi = keys.index("Owner")
        for k in keys[oi + 1 :]:
            v = row[k].strip()
            if not v or v.startswith("http") or v == row.get("Team ID"):
                continue
            if v.startswith("MB") and v[2:].isdigit():
                continue
            names.append(v)
            if len(names) >= 6:
                break
    return names


def classify_population(rows: list[dict[str, str]], title_meta: dict) -> dict:
    event_key = next(
        (k for k in (rows[0] if rows else {}) if "Tournament" in k or "Event" in k),
        "Tournament / Event",
    )
    events = Counter((r.get(event_key) or "").strip() or "(blank/-)" for r in rows)
    # Sheet uses "-" for non-tournament / Twitter finds.
    blankish = sum(v for k, v in events.items() if k in {"(blank/-)", "-", ""})
    labeled = sum(v for k, v in events.items() if k not in {"(blank/-)", "-", ""})
    note_join = " | ".join(title_meta.get("note_row") or [])
    return {
        "population": "mixed",
        "population_evidence": {
            "sheet_title": (title_meta.get("title_row") or [None])[0],
            "sheet_notes": title_meta.get("note_row"),
            "tournament_event_labeled_rows": labeled,
            "tournament_event_blank_or_dash_rows": blankish,
            "top_events": events.most_common(12),
            "note": (
                "Sheet self-describes as VGCPastes Repository; note row says "
                "most teams are found on Twitter, with a Featured/tournament "
                "subset. Not the same population as Pikalytics Limitless "
                "team-usage API."
            ),
            "note_row_joined": note_join,
        },
    }


def extract(
    *,
    sheet_id: str = SHEET_ID,
    gid: str = DEFAULT_SHEET_GID,
    regulation: str = DEFAULT_REGULATION,
    out_path: Path = DEFAULT_OUT,
) -> dict[str, Any]:
    _, sheet_url = sheet_urls(sheet_id, gid)
    ensure_sheet_csv(sheet_id=sheet_id, gid=gid)
    title_meta, rows, _cols = load_sheet_rows(SHEET_CSV)
    pop = classify_population(rows, title_meta)

    teams: list[dict] = []
    resolve = Counter()
    for i, row in enumerate(rows):
        tid = row.get("Team ID") or f"row{i}"
        url = (row.get("Pokepaste") or "").strip()
        pid = pokepaste_id(url) if url else None
        if not pid:
            resolve["no_url"] += 1
            continue
        paste_doc = fetch_pokepaste(pid)
        if not paste_doc:
            resolve["fetch_fail"] += 1
            continue
        members = parse_paste(str(paste_doc.get("paste") or ""))
        if len(members) < 1:
            resolve["parse_empty"] += 1
            continue
        if len(members) != 6:
            resolve["parse_not_6"] += 1
        else:
            resolve["ok_6"] += 1

        sheet_sp = sheet_species(row)
        teams.append(
            {
                "team_id": tid,
                "description": row.get("Team Description") or None,
                "full_name": row.get("Full Name") or None,
                "owner": row.get("Owner") or None,
                "tournament_event": row.get("Tournament / Event") or None,
                "rank": row.get("Rank") or None,
                "date_shared": row.get("Date Shared") or None,
                "source_link": row.get("Link to Source") or None,
                "replica_status": row.get("Replica Status") or None,
                "replica_code": next(
                    (
                        row[k]
                        for k in row
                        if k.replace(" ", "").lower().startswith("replicacode")
                        and row[k]
                    ),
                    None,
                ),
                "pokepaste_url": url,
                "pokepaste_id": pid,
                "pokepaste_title": paste_doc.get("title"),
                "pokepaste_notes": paste_doc.get("notes"),
                "species_sheet": [to_id(s) for s in sheet_sp],
                "species_sheet_display": sheet_sp,
                "species": [m["species"] for m in members],
                "members": members,
            }
        )
        if (i + 1) % 50 == 0:
            print(f"  … {i + 1}/{len(rows)} rows", file=sys.stderr)

    core_counts: Counter[tuple[str, ...]] = Counter()
    for t in teams:
        key = tuple(sorted(set(t["species"])))
        if len(key) >= 2:
            core_counts[key] += 1
    cores = [
        {"species": list(sp), "uses": n, "key": "|".join(sp)}
        for sp, n in sorted(core_counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    snap: dict[str, Any] = {
        "meta": {
            "schema_version": 1,
            "source": "vgcpastes",
            "source_detail": (
                f"Google Sheet gid={gid} + pokepast.es/{{id}}/json resolution"
            ),
            "source_url": sheet_url,
            "sheet_gid": str(gid),
            "population": pop["population"],
            "population_evidence": pop["population_evidence"],
            "regulation": regulation,
            "sheet_claimed_total_teams": None,
            "sheet_rows": len(rows),
            "teams_resolved": len(teams),
            "resolve_counts": dict(resolve),
            "extracted_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": (
                "Full builds (item/ability/nature/evs/moves) per member from "
                "Pokepaste. Species-only cores also included for co-occurrence "
                "comparability. Not merged with pokemon-zone or pikalytics "
                "team-usage extracts. Paste species ids are base forms "
                "(mega stones live on item); species_sheet keeps the sheet's "
                "mega-aware labels when present."
            ),
        },
        "teams": teams,
        "cores": cores,
    }
    raw0 = SHEET_CSV.read_text(encoding="utf-8").splitlines()[0]
    m_tc = re.search(r"Total Team Count:\D+(\d+)", raw0)
    m_cc = re.search(r"Total Creator Count:\D+(\d+)", raw0)
    if m_tc:
        snap["meta"]["sheet_claimed_total_teams"] = int(m_tc.group(1))
    if m_cc:
        snap["meta"]["sheet_claimed_total_creators"] = int(m_cc.group(1))

    full_ev = sum(
        1
        for t in teams
        if all(sum(m["evs"].values()) > 0 for m in t["members"])
    )
    none_ev = sum(
        1
        for t in teams
        if all(sum(m["evs"].values()) == 0 for m in t["members"])
    )
    members_n = sum(len(t["members"]) for t in teams)
    with_ev = sum(
        1 for t in teams for m in t["members"] if sum(m["evs"].values()) > 0
    )
    snap["meta"]["ev_completeness"] = {
        "teams_all_members_have_evs": full_ev,
        "teams_all_members_zero_evs": none_ev,
        "teams_partial_evs": len(teams) - full_ev - none_ev,
        "members_with_nonzero_evs": with_ev,
        "members_total": members_n,
        "note": (
            "Sheet EVs column Yes/No tracks whether the paste includes spreads; "
            "zero-EV teams are still valid for item/moveset variation."
        ),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {out_path} ({len(teams)} teams, {len(cores)} unique species-sets, "
        f"resolve={dict(resolve)})",
        file=sys.stderr,
    )
    return snap


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sheet-id", default=SHEET_ID)
    p.add_argument("--gid", default=DEFAULT_SHEET_GID)
    p.add_argument("--regulation", default=DEFAULT_REGULATION)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--skip-validate",
        action="store_true",
        help="Write extract without floor checks (manual/debug only)",
    )
    args = p.parse_args(argv)

    previous = None
    if args.out.exists():
        try:
            previous = json.loads(args.out.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = None

    snap = extract(
        sheet_id=args.sheet_id,
        gid=args.gid,
        regulation=args.regulation,
        out_path=args.out,
    )
    if args.skip_validate:
        return 0
    decision, reason = validate_vgcpastes_snapshot(snap, previous=previous)
    if decision == "fail":
        print(f"validate fail: {reason}", file=sys.stderr)
        return 1
    print(f"validate {decision}: {reason}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
