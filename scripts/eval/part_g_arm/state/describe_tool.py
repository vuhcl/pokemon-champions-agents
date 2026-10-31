"""describe(kind, name) — Showdown text pin + Champions override diff (tool_fields)."""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from recommender.ids import to_id
from recommender.legality import (
    is_item_legal,
    is_move_legal,
    is_species_legal,
    load_snapshot,
)

ROOT = Path(__file__).resolve().parents[4]
TEXT_DIR = ROOT / "data" / "showdown_text"
OVERRIDES_PATH = TEXT_DIR / "champions_text_overrides.v1.json"
RULES_PATH = ROOT / "data" / "legality" / "champions_rules.v1.json"

_KIND_FILE = {"item": "items.ts", "move": "moves.ts", "ability": "abilities.ts"}

# Refusal / flat_rules aliases → registry id (beyond exact text / id match).
_RULE_ALIASES: dict[str, str] = {
    "speciesclause": "species_clause",
    "itemclause": "item_clause",
    "itemclause1": "item_clause",
    "mythical": "ban_mythical",
    "restrictedlegendary": "ban_restricted_legendary",
    "bring6pick36": "bring_6_pick_3_6",
    "bring6pick3": "bring_6_pick_3_6",
}


@lru_cache(maxsize=1)
def _overrides_by_id() -> dict[str, dict[str, Any]]:
    doc = json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))
    return {e["id"]: e for e in doc.get("entries") or []}


@lru_cache(maxsize=8)
def _parse_text_file(kind: str) -> tuple[dict[str, dict[str, str]], str, str]:
    """Return (id -> {desc?, shortDesc?}, rel_path, sha256)."""
    fname = _KIND_FILE[kind]
    path = TEXT_DIR / fname
    raw = path.read_text(encoding="utf-8")
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    rel = f"data/showdown_text/{fname}"
    entries: dict[str, dict[str, str]] = {}
    # Entries look like: \tfoo: {\n\t\tname: "...",\n\t\tdesc: "...",\n\t\tshortDesc: "...",\n\t},
    for m in re.finditer(r"(?m)^\t([a-zA-Z0-9]+):\s*\{", raw):
        name = m.group(1)
        depth = 1
        j = m.end()
        while j < len(raw) and depth:
            if raw[j] == "{":
                depth += 1
            elif raw[j] == "}":
                depth -= 1
            j += 1
        body = raw[m.end() : j - 1]
        fields: dict[str, str] = {}
        for key in ("shortDesc", "desc", "name"):
            km = re.search(rf"(?m)^\t\t{key}:\s*\"((?:\\.|[^\"])*)\"", body)
            if km:
                fields[key] = bytes(km.group(1), "utf-8").decode("unicode_escape")
        if fields:
            entries[name] = fields
    return entries, rel, sha


@lru_cache(maxsize=1)
def _rules_registry() -> tuple[list[dict[str, Any]], str]:
    doc = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    rel = "data/legality/champions_rules.v1.json"
    return list(doc.get("entries") or []), rel


def _match_rule(name: str) -> dict[str, Any] | None:
    entries, _rel = _rules_registry()
    needle = name.strip()
    nid = to_id(needle)
    compact = re.sub(r"[^a-z0-9]+", "", needle.casefold())
    for e in entries:
        eid = str(e.get("id") or "")
        text = str(e.get("text") or "")
        if eid == needle or eid == nid or to_id(eid) == nid:
            return e
        if text.casefold() == needle.casefold():
            return e
        if to_id(text) == nid:
            return e
        if re.sub(r"[^a-z0-9]+", "", text.casefold()) == compact:
            return e
    alias = _RULE_ALIASES.get(compact) or _RULE_ALIASES.get(nid)
    if alias:
        for e in entries:
            if e.get("id") == alias:
                return e
    return None


def describe(kind: object, name: object) -> dict[str, Any]:
    if kind not in ("item", "move", "ability", "rule"):
        return {"status": "error", "message": "kind must be item|move|ability|rule"}
    if not isinstance(name, str) or not name.strip():
        return {"status": "error", "message": "name is required"}
    if kind == "rule":
        entry = _match_rule(name)
        if entry is None:
            return {"status": "not_found", "query": name, "kind": "rule"}
        _entries, rel = _rules_registry()
        src = dict(entry.get("source") or {})
        enforced = entry.get("enforced_by") or "none"
        out: dict[str, Any] = {
            "status": "ok",
            "kind": "rule",
            "id": entry.get("id"),
            "name": entry.get("text"),
            "text": entry.get("text"),
            "source": {
                "file": src.get("file") or rel,
                "path": src.get("path"),
                "registry": rel,
            },
            "enforced_by": enforced,
        }
        if enforced == "none":
            out["enforcement_note"] = (
                "This rule is listed in the format registry but is not enforced by "
                "the team validator; do not claim a tool refusal for it."
            )
        else:
            out["enforcement_note"] = (
                "This rule is enforced by the team validator (refusals name it)."
            )
        return out

    snap = load_snapshot()
    kid = to_id(name)
    # Legal-pin gate
    if kind == "item":
        if not is_item_legal(snap, kid):
            return {"status": "not_found", "query": name, "kind": kind}
        canonical = str((snap.get("items") or {}).get(kid, {}).get("name") or name)
    elif kind == "move":
        if not is_move_legal(snap, kid):
            return {"status": "not_found", "query": name, "kind": kind}
        canonical = str((snap.get("moves") or {}).get(kid, {}).get("name") or name)
    else:
        # Snapshot has no abilities table — legal = appears on a legal species.
        by_id: dict[str, str] = {}
        for sid, e in (snap.get("species") or {}).items():
            if not is_species_legal(snap, sid):
                continue
            for v in (e.get("abilities") or {}).values():
                if isinstance(v, str) and v.strip():
                    by_id.setdefault(to_id(v), v)
        if kid not in by_id:
            return {"status": "not_found", "query": name, "kind": kind}
        canonical = by_id[kid]

    table, rel, sha = _parse_text_file(str(kind))
    text_entry = table.get(kid) or {}
    short = text_entry.get("shortDesc")
    if not short:
        return {
            "status": "error",
            "message": f"no shortDesc in {rel} for {kid}",
            "kind": kind,
            "name": canonical,
        }
    out: dict[str, Any] = {
        "status": "ok",
        "kind": kind,
        "name": canonical,
        "short_desc": short,
        "source": {"path": rel, "sha256": sha},
    }
    if text_entry.get("desc"):
        out["desc"] = text_entry["desc"]
    ov = _overrides_by_id().get(kid)
    if ov is not None:
        out["champions_overrides"] = list(ov.get("champions_overrides") or [])
        if ov.get("text_may_not_match"):
            out["text_may_not_match"] = True
    return out
