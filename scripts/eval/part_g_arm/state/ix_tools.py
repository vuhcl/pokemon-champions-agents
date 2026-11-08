"""FU73 / #367+#368: find_by_effect + get_type_effectiveness (behind ix_tools_v1)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from recommender.ids import to_id

ROOT = Path(__file__).resolve().parents[4]
FLAGS_PATH = ROOT / "data" / "moves" / "flags.v1.json"
STATIC_PATH = ROOT / "data" / "moves" / "static.v1.json"
MOVE_DESC_PATH = ROOT / "data" / "moves" / "descriptions.v1.json"
ITEM_DESC_PATH = ROOT / "data" / "items" / "descriptions.v1.json"
ABILITY_PATH = ROOT / "data" / "abilities" / "all.v1.json"
TYPE_CHART_PATH = ROOT / "scripts" / "eval" / "part_g_v4" / "key_artifacts" / "type_chart.v1.json"

# Curated flags: each derives from one pinned field (ADR lists the field).
# priority omitted: no description phrase covers the full non-zero-priority set (report).
FLAG_DERIVATIONS: dict[str, str] = {
    "redirection": "data/moves/flags.v1.json → volatileStatus ∈ {followme, ragepowder}",
    "pivot": "data/moves/flags.v1.json → selfSwitch truthy",
    "phazing": "data/moves/flags.v1.json → forceSwitch truthy",
    "protection": "data/moves/flags.v1.json → stallingMove truthy",
}

# Player term → flag. Alias query must equal flag query (test).
FLAG_ALIASES: dict[str, str] = {
    "redirection": "redirection",
    "redirect": "redirection",
    "follow me": "redirection",
    "pivot": "pivot",
    "self switch": "pivot",
    "self-switch": "pivot",
    "u-turn": "pivot",
    "phazing": "phazing",
    "phaze": "phazing",
    "force switch": "phazing",
    "drag": "phazing",
    "protection": "protection",
    "protect": "protection",
    "stall": "protection",
}

# Canonical keyword phrase used for test (b): every flag member ⊆ keyword hits.
FLAG_CANONICAL_PHRASE: dict[str, str] = {
    "redirection": "redirected",
    "pivot": "party",
    "phazing": "Forces the target to switch",
    "protection": "protect",
}

# Keyword extras beyond the flag set for each canonical phrase (ADR near-misses).
# Filled at import from live data so the ADR draft can cite them; tests assert ⊆.

_REDIRECT_VOLATILES = frozenset({"followme", "ragepowder"})


def _spec(name: str, description: str, **props: Any) -> dict[str, Any]:
    required = [k for k, v in props.items() if not v.pop("optional", False)]
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": props,
                "required": required,
            },
        },
    }


FIND_BY_EFFECT_SPEC = _spec(
    "find_by_effect",
    "Find moves, items, or abilities by curated functional flag and/or keyword over "
    "Showdown description text (not in-game). kind is required; supply flag and/or "
    "keyword. Returns matching names with matched_by (flag|description|both), a ~12-word "
    "matched_window around the keyword span (description/both), and full description "
    "text for flag/both matches, plus count and source labels. Flag-first ranking. "
    "Word-boundary keyword match.",
    kind={"type": "string", "enum": ["move", "item", "ability"]},
    flag={"type": "string", "optional": True},
    keyword={"type": "string", "optional": True},
)

GET_TYPE_EFFECTIVENESS_SPEC = _spec(
    "get_type_effectiveness",
    "Type chart from the eval's Champions type_chart.v1.json. For an attacking type, "
    "return defending types that take super-effective / resisted / no damage; "
    "optionally the reverse for a defending type. Nothing else.",
    attack_type={"type": "string", "optional": True},
    defend_type={"type": "string", "optional": True},
)

IX_TOOL_SPECS: list[dict[str, Any]] = [FIND_BY_EFFECT_SPEC, GET_TYPE_EFFECTIVENESS_SPEC]
IX_TOOL_NAMES = frozenset(s["function"]["name"] for s in IX_TOOL_SPECS)


@lru_cache(maxsize=1)
def _flags_doc() -> dict[str, Any]:
    return json.loads(FLAGS_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _move_desc_doc() -> dict[str, Any]:
    return json.loads(MOVE_DESC_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _item_desc_doc() -> dict[str, Any]:
    return json.loads(ITEM_DESC_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _ability_doc() -> dict[str, Any]:
    return json.loads(ABILITY_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _type_chart_doc() -> dict[str, Any]:
    return json.loads(TYPE_CHART_PATH.read_text(encoding="utf-8"))


def resolve_flag(name: str | None) -> str | None:
    if not name or not str(name).strip():
        return None
    key = " ".join(str(name).strip().casefold().split())
    return FLAG_ALIASES.get(key) or FLAG_ALIASES.get(to_id(key)) or (
        key if key in FLAG_DERIVATIONS else None
    )


def _flag_move_ids(flag: str) -> dict[str, str]:
    """id → display name for champions-legal moves matching the flag."""
    moves = _flags_doc()["moves"]
    out: dict[str, str] = {}
    for mid, row in moves.items():
        hit = False
        if flag == "redirection":
            hit = row.get("volatileStatus") in _REDIRECT_VOLATILES
        elif flag == "pivot":
            hit = bool(row.get("selfSwitch"))
        elif flag == "phazing":
            hit = bool(row.get("forceSwitch"))
        elif flag == "protection":
            hit = bool(row.get("stallingMove"))
        if hit:
            out[mid] = str(row["name"])
    return out


def _word_boundary_re(keyword: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])", re.I)


def _desc_corpus(kind: str) -> list[tuple[str, str, str, dict[str, Any]]]:
    """(id, name, haystack, source_meta) for keyword search. Legal moves only when kind=move."""
    if kind == "move":
        legal = _flags_doc()["moves"]
        doc = _move_desc_doc()
        src = doc["source"]
        rows = []
        for mid, legal_row in legal.items():
            entry = (doc.get("by_id") or {}).get(mid) or {}
            text = " ".join(
                x for x in (entry.get("shortDesc"), entry.get("desc")) if isinstance(x, str)
            )
            rows.append((mid, str(legal_row["name"]), text, src))
        return rows
    if kind == "item":
        doc = _item_desc_doc()
        src = doc["source"]
        rows = []
        for mid, entry in (doc.get("by_id") or {}).items():
            text = " ".join(
                x for x in (entry.get("shortDesc"), entry.get("desc")) if isinstance(x, str)
            )
            rows.append((mid, str(entry.get("name") or mid), text, src))
        return rows
    if kind == "ability":
        doc = _ability_doc()
        src = {
            "label": "abilities all.v1.json",
            "path": "data/abilities/all.v1.json",
            "note": doc.get("meta", {}).get("source"),
        }
        rows = []
        for mid, entry in (doc.get("abilities") or {}).items():
            text = str(entry.get("description") or "")
            rows.append((mid, str(entry.get("name") or mid), text, src))
        return rows
    return []


def _window_around(text: str, start: int, end: int, *, words: int = 12) -> str:
    """~`words` tokens centered on the match (whole string if shorter)."""
    tokens = text.split()
    if not tokens:
        return ""
    # Map char offset → token index via a cumulative scan on the original text.
    idx = 0
    positions: list[tuple[int, int]] = []
    for tok in tokens:
        at = text.find(tok, idx)
        if at < 0:
            at = idx
        positions.append((at, at + len(tok)))
        idx = at + len(tok)
    center = 0
    for i, (a, b) in enumerate(positions):
        if a <= start < b or a < end <= b or (start <= a and b <= end):
            center = i
            break
        if a >= start:
            center = i
            break
    half = max(words // 2, 1)
    lo = max(0, center - half)
    hi = min(len(tokens), lo + words)
    lo = max(0, hi - words)
    return " ".join(tokens[lo:hi])


def _full_description(kind: str, mid: str) -> str:
    if kind == "move":
        entry = (_move_desc_doc().get("by_id") or {}).get(mid) or {}
        return " ".join(
            x for x in (entry.get("shortDesc"), entry.get("desc")) if isinstance(x, str)
        ).strip()
    if kind == "item":
        entry = (_item_desc_doc().get("by_id") or {}).get(mid) or {}
        return " ".join(
            x for x in (entry.get("shortDesc"), entry.get("desc")) if isinstance(x, str)
        ).strip()
    entry = (_ability_doc().get("abilities") or {}).get(mid) or {}
    return str(entry.get("description") or "").strip()


def _keyword_hits(kind: str, keyword: str) -> dict[str, dict[str, Any]]:
    pat = _word_boundary_re(keyword)
    out: dict[str, dict[str, Any]] = {}
    for mid, name, text, src in _desc_corpus(kind):
        m = pat.search(text)
        if not m:
            continue
        out[mid] = {
            "name": name,
            "matched_span": m.group(0),
            "matched_window": _window_around(text, m.start(), m.end()),
            "description": text.strip(),
            "source": src,
        }
    return out


def find_by_effect(
    kind: object,
    flag: object = None,
    keyword: object = None,
) -> dict[str, Any]:
    if kind not in ("move", "item", "ability"):
        return {"status": "error", "message": "kind must be move|item|ability"}
    flag_raw = flag if isinstance(flag, str) else None
    kw_raw = keyword if isinstance(keyword, str) else None
    resolved = resolve_flag(flag_raw)
    if flag_raw and resolved is None:
        return {
            "status": "error",
            "message": f"unknown flag or alias: {flag_raw!r}",
            "known_flags": sorted(FLAG_DERIVATIONS),
        }
    if not resolved and not (kw_raw and kw_raw.strip()):
        return {"status": "error", "message": "provide flag and/or keyword"}

    # Flags are move-derived only (pinned move fields).
    flag_ids: dict[str, str] = {}
    if resolved:
        if kind != "move":
            return {
                "status": "error",
                "message": f"flag {resolved!r} applies to kind=move only",
            }
        flag_ids = _flag_move_ids(resolved)

    kw_hits: dict[str, dict[str, Any]] = {}
    if kw_raw and kw_raw.strip():
        kw_hits = _keyword_hits(str(kind), kw_raw.strip())

    # Flag-first ranking: flag matches, then description-only.
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    if resolved:
        for mid, name in sorted(flag_ids.items(), key=lambda x: x[1].casefold()):
            seen.add(mid)
            by = "both" if mid in kw_hits else "flag"
            full = _full_description(str(kind), mid)
            row: dict[str, Any] = {
                "id": mid,
                "name": name,
                "matched_by": by,
                "flag": resolved,
                "description": full,
            }
            if mid in kw_hits:
                row["matched_span"] = kw_hits[mid]["matched_span"]
                row["matched_window"] = kw_hits[mid]["matched_window"]
            matches.append(row)
    for mid, hit in sorted(kw_hits.items(), key=lambda x: x[1]["name"].casefold()):
        if mid in seen:
            continue
        matches.append(
            {
                "id": mid,
                "name": hit["name"],
                "matched_by": "description",
                "matched_span": hit["matched_span"],
                "matched_window": hit["matched_window"],
                # Keyword-only: window is the primary snippet; keep full text so
                # the arm can distinguish immunity vs boost without a follow-up describe.
                "description": hit["description"],
                **({"flag": resolved} if resolved else {}),
            }
        )

    sources: list[str] = []
    if resolved:
        sources.append(FLAG_DERIVATIONS[resolved])
    if kw_hits:
        # Kind-specific description source label.
        if kind == "ability":
            sources.append("data/abilities/all.v1.json (description)")
        elif kind == "move":
            sources.append("Showdown text (data/moves/descriptions.v1.json)")
        else:
            sources.append("Showdown text (data/items/descriptions.v1.json)")

    return {
        "status": "ok",
        "kind": kind,
        "flag": resolved,
        "keyword": kw_raw.strip() if kw_raw and kw_raw.strip() else None,
        "count": len(matches),
        "matches": matches,
        "source": sources,
    }


def get_type_effectiveness(
    attack_type: object = None,
    defend_type: object = None,
) -> dict[str, Any]:
    doc = _type_chart_doc()
    chart: dict[str, dict[str, float]] = doc["effectiveness"]
    types = list(doc["types"])
    src = {
        "path": "scripts/eval/part_g_v4/key_artifacts/type_chart.v1.json",
        "label": "Champions type chart (eval extract; Generations.get(0))",
        "generation": (doc.get("source") or {}).get("generation"),
    }

    def _norm(t: object) -> str | None:
        if not isinstance(t, str) or not t.strip():
            return None
        needle = t.strip().casefold()
        for name in types:
            if name.casefold() == needle:
                return name
        return None

    atk = _norm(attack_type)
    de = _norm(defend_type)
    if atk is None and de is None:
        return {"status": "error", "message": "provide attack_type and/or defend_type"}
    if attack_type is not None and atk is None:
        return {"status": "not_found", "query": attack_type, "source": src}
    if defend_type is not None and de is None:
        return {"status": "not_found", "query": defend_type, "source": src}

    out: dict[str, Any] = {"status": "ok", "source": src}
    if atk is not None:
        row = chart[atk]
        out["attack_type"] = atk
        out["super_effective"] = sorted(d for d, m in row.items() if m > 1)
        out["resisted"] = sorted(d for d, m in row.items() if 0 < m < 1)
        out["no_damage"] = sorted(d for d, m in row.items() if m == 0)
    if de is not None:
        out["defend_type"] = de
        out["from_attacking"] = {
            a: chart[a][de]
            for a in types
        }
        out["super_effective_from"] = sorted(a for a in types if chart[a][de] > 1)
        out["resisted_from"] = sorted(a for a in types if 0 < chart[a][de] < 1)
        out["no_damage_from"] = sorted(a for a in types if chart[a][de] == 0)
    return out


def canonical_keyword_extras(flag: str) -> list[str]:
    """Names in keyword(canonical_phrase) but not in the flag set (ADR near-misses)."""
    phrase = FLAG_CANONICAL_PHRASE[flag]
    flag_set = set(_flag_move_ids(flag))
    kw = _keyword_hits("move", phrase)
    return sorted(kw[mid]["name"] for mid in kw if mid not in flag_set)
