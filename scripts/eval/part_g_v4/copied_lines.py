"""copied_unchanged per scripts/eval/part_g_v4/copied_unchanged_lines.md (ADR-060: no recommender imports). Computed by the extractor from the
item's transcript; the scorer only reads the flag."""
from __future__ import annotations

import re
from typing import Any

# ponytail: kinds with no value string are never copied; this list is the definition, not a heuristic.
_NAME_KINDS = {"type_list_member", "ability_list_member", "common_items", "teammates"}


def norm(s: str) -> str:
    return " ".join(str(s).lower().split())


def _num(x: Any) -> str:
    return repr(x) if isinstance(x, float) else str(x)


def carrier_lines(tool_calls: list[dict[str, Any]]) -> list[str]:
    """Every line the item's tool results contain, per the per-tool table, normalised."""
    out: list[str] = []
    strings = lambda xs: [x for x in xs or [] if isinstance(x, str)]  # noqa: E731
    for call in tool_calls or []:
        name, res = call.get("name"), call.get("result") or {}
        if not isinstance(res, dict):
            continue
        if name == "get_typing":
            out += strings(res.get("types"))
        elif name == "get_abilities":
            out += strings(res.get("abilities"))
        elif name == "check_species_ability":
            out += strings(res.get("species_abilities"))
        elif name == "get_move_static":
            out += strings([res.get("type"), res.get("category")])
        elif name == "calc_damage":
            out += strings([res.get("ko_text"), res.get("calc_desc"), (res.get("kochance") or {}).get("text") if isinstance(res.get("kochance"), dict) else None])
        elif name == "get_usage_items":
            out += [f"{e['name']} {_num(e['pct'])}" for e in res.get("items") or [] if isinstance(e, dict) and "name" in e and e.get("pct") is not None]
        elif name == "get_usage_teammates":
            out += [f"{e['name']} {_num(e['conditional_pct'])}" if e.get("conditional_pct") is not None else str(e["name"])
                    for e in res.get("rows") or [] if isinstance(e, dict) and "name" in e]
            out += strings(res.get("caveats"))
        out += strings([res.get("note"), res.get("message")])  # a `note` or `message` string in any result is a line
    return [norm(x) for x in out if x]


def value_strings(kind: str, proposition: str, line: str = "gate") -> list[str]:
    """The strings a carrier line must contain to carry this claim; [] means no line can carry it."""
    if line == "usage_pct" and kind in _NAME_KINDS and "=" in proposition:
        name, pct = proposition.rsplit("=", 1)
        return [name, pct]
    if kind in _NAME_KINDS:
        return [proposition]
    if kind.endswith("_rank") and "=" in proposition:
        name, rank = proposition.rsplit("=", 1)
        return [name, rank]
    if kind == "speed_stat":
        return [proposition.rsplit("=", 1)[-1]]
    if kind in ("damage_range", "percent_of_hp"):
        m = re.search(r"(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)\s*$", proposition)
        return list(m.groups()) if m else []
    if kind == "ko_chance":
        return [proposition.rstrip("%")]
    if kind == "nhko":
        m = re.search(r"(\d+)HKO", proposition)
        return [f"{m.group(1)}hko"] if m else []
    if kind == "chance_nhko":
        m = re.match(r"(\d+(?:\.\d+)?)% chance to (\d+)HKO", proposition)
        return [m.group(1), f"{m.group(2)}hko"] if m else []
    if kind in ("category", "move_type", "base_power"):
        return [proposition]
    if kind == "labelled_value":
        return [proposition.rsplit("=", 1)[-1]]
    return []


def _has(line: str, value: str) -> bool:
    return re.search(r"(?<![\w.])" + re.escape(norm(value)) + r"(?![\w])(?!\.\d)", line) is not None


def is_copied_unchanged(kind: str, proposition: str, line: str, tool_calls: list[dict[str, Any]], final_text: str) -> bool:
    vals = value_strings(kind, proposition, line)
    if not vals:
        return False
    text = norm(final_text)
    return any(all(_has(ln, v) for v in vals) and ln in text for ln in carrier_lines(tool_calls))
