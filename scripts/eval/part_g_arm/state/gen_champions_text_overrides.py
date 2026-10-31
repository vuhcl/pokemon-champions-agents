#!/usr/bin/env python3
"""Generate data/showdown_text/champions_text_overrides.v1.json from Showdown cache.

Requires .cache/pokemon-showdown at commit 942cda71d14bf0618bd57991708a2e2734b6daba.
Omits pure inherit + isNonstandard toggles. Legal ∩ real field/handler override only.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
CACHE = ROOT / ".cache" / "pokemon-showdown" / "data"
OUT = ROOT / "data" / "showdown_text" / "champions_text_overrides.v1.json"
SHOWDOWN_COMMIT = "942cda71d14bf0618bd57991708a2e2734b6daba"
MEMBER_RE = re.compile(r"(?m)^\t\t([a-zA-Z][a-zA-Z0-9]*)\s*([:(])")
SCALAR = frozenset(
    {"basePower", "pp", "accuracy", "type", "category", "priority", "target", "critRatio"}
)


def parse_ts_object_entries(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    positions = [
        (m.group(1), m.end())
        for m in re.finditer(r"(?m)^\t([a-zA-Z0-9]+):\s*\{", text)
    ]
    entries: dict[str, str] = {}
    for name, start in positions:
        depth = 1
        j = start
        while j < len(text) and depth:
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            j += 1
        entries[name] = text[start : j - 1]
    return entries


def members(body: str) -> dict[str, str]:
    matches = list(MEMBER_RE.finditer(body))
    out: dict[str, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out[m.group(1)] = body[m.start() : end].rstrip().rstrip(",")
    return out


def _norm(src: str) -> str:
    return re.sub(r"\s+", " ", src.strip())


def _scalar(src: str) -> str | None:
    m = re.search(r":\s*([^,\n]+)", src)
    return m.group(1).strip() if m else None


def _sec_chance(src: str) -> str | None:
    m = re.search(r"chance:\s*(\d+)", src)
    return m.group(1) if m else None


def diffs(mod_body: str, base_body: str | None) -> list[dict[str, Any]]:
    mm = members(mod_body)
    bm = members(base_body) if base_body is not None else {}
    out: list[dict[str, Any]] = []
    for k, v in mm.items():
        if k in ("inherit", "isNonstandard", "num", "gen", "name", "shortDesc", "desc"):
            continue
        if re.search(r":\s*undefined\b", v):
            out.append({"field": k, "kind": "cleared", "handler": k.startswith("on")})
            continue
        if k not in bm:
            handler = bool(
                k.startswith("on") or "(this" in v or re.search(r"\)\s*\{", v)
            )
            out.append({"field": k, "kind": "added", "handler": handler})
            continue
        if _norm(v) == _norm(bm[k]):
            continue
        handler = bool(k.startswith("on") or "(this" in v or re.search(r"\)\s*\{", v))
        if k == "secondary":
            bc, mc = _sec_chance(bm[k]), _sec_chance(v)
            if bc and mc and bc != mc:
                out.append(
                    {"field": "secondary.chance", "kind": f"{bc}→{mc}", "handler": False}
                )
                continue
        if k in SCALAR:
            out.append(
                {
                    "field": k,
                    "kind": f"{_scalar(bm[k])}→{_scalar(v)}",
                    "handler": False,
                }
            )
        else:
            out.append({"field": k, "kind": "changed", "handler": handler})
    return out


def _lines(dlist: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for x in dlist:
        if x["handler"]:
            lines.append(f"{x['field']} handler")
        elif "→" in str(x["kind"]):
            lines.append(f"{x['field']} {x['kind']}")
        else:
            lines.append(f"{x['field']} {x['kind']}")
    return lines


def main() -> int:
    if not CACHE.is_dir():
        print(f"missing Showdown cache at {CACHE}", file=sys.stderr)
        return 1
    leg = json.loads((ROOT / "data/legality/champions.v1.json").read_text(encoding="utf-8"))
    legal_moves = {mid for mid, e in leg["moves"].items() if e.get("is_nonstandard") is None}
    legal_items = {iid for iid, e in leg["items"].items() if e.get("is_nonstandard") is None}
    legal_species = {
        sid for sid, e in leg["species"].items() if e.get("is_nonstandard") is None
    }
    legal_abs: set[str] = set()
    for sid in legal_species:
        for v in (leg["species"][sid].get("abilities") or {}).values():
            if isinstance(v, str):
                legal_abs.add(re.sub(r"[^a-z0-9]", "", v.lower()))

    base_moves = parse_ts_object_entries(CACHE / "moves.ts")
    mod_moves = parse_ts_object_entries(CACHE / "mods/champions/moves.ts")
    base_abs = parse_ts_object_entries(CACHE / "abilities.ts")
    mod_abs = parse_ts_object_entries(CACHE / "mods/champions/abilities.ts")
    base_items = parse_ts_object_entries(CACHE / "items.ts")
    mod_items = parse_ts_object_entries(CACHE / "mods/champions/items.ts")

    entries: list[dict[str, Any]] = []
    for mid, body in sorted(mod_moves.items()):
        if mid not in legal_moves:
            continue
        d = diffs(body, base_moves.get(mid))
        if not d:
            continue
        entries.append(
            {
                "id": mid,
                "kind": "move",
                "champions_overrides": _lines(d),
                "text_may_not_match": any(x["handler"] for x in d)
                and not any(not x["handler"] and "→" in str(x["kind"]) for x in d),
            }
        )
    for aid, body in sorted(mod_abs.items()):
        if aid not in legal_abs:
            continue
        d = diffs(body, base_abs.get(aid))
        if not d:
            continue
        entries.append(
            {
                "id": aid,
                "kind": "ability",
                "champions_overrides": _lines(d),
                "text_may_not_match": True,
            }
        )
    for iid, body in sorted(mod_items.items()):
        if iid not in legal_items:
            continue
        d = diffs(body, base_items.get(iid))
        if not d:
            continue
        entries.append(
            {
                "id": iid,
                "kind": "item",
                "champions_overrides": _lines(d),
                "text_may_not_match": any(x["handler"] for x in d),
            }
        )

    doc = {
        "schema": "champions_text_overrides_v1",
        "showdown_commit": SHOWDOWN_COMMIT,
        "generator": "scripts/eval/part_g_arm/state/gen_champions_text_overrides.py",
        "count": len(entries),
        "entries": entries,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} count={len(entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
