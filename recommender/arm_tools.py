"""The arm's lookup tools: each takes plain arguments and returns a JSON-safe dict with an explicit ``source``.

Legality, typing, abilities and move statics come from the extracted legality snapshot; Speed and damage
come from the calc service (``@smogon/calc``); usage comes from the offline usage files. Nothing here
searches the web (``allow_live`` is pinned False at construction). Failures come back as
``{"status": "error", ...}`` so a tool-using loop can record them instead of crashing.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from recommender import legality
from recommender.arm_teammates import arm_query_teammates, mega_capable_base_ids
from recommender.calc_client import CalcClient, CalcClientError
from recommender.ids import to_id
from recommender.usage_data import ingame_ladder_species_map, showdown_species_map

LEGALITY_SOURCE = "legality snapshot (Showdown Champions mod extract)"
CALC_SOURCE = "@smogon/calc via calc service"
USAGE_SOURCES = ("ingame", "showdown")
# Speed is read from the calc's own final stats; this move/opponent only make the call valid.
SPEED_FILLER = {"move": "Tackle", "opponent": {"species": "Pikachu", "nature": "Hardy"}}
_MON_KEYS = {"species", "nature", "sp", "item", "ability", "boosts"}
_FIELD_KEYS = {"gameType", "weather", "terrain", "isGravity", "isMagicRoom", "isWonderRoom", "attackerSide", "defenderSide"}


def to_jsonable(obj: Any) -> Any:
    """Frozen dataclasses -> dicts, tuples -> lists, recursively. Unknown types raise instead of being str()'d."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    raise TypeError(f"not JSON-serializable: {type(obj).__name__}")


def dumps(obj: Any) -> str:
    return json.dumps(to_jsonable(obj), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _err(kind: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"status": "error", "error_kind": kind, "message": message, **extra}


def top_n_with_ties(entries: list[dict[str, Any]], n: int) -> list[dict[str, Any]]:
    """First n of a pct-descending list plus every later entry tied with the n-th."""
    k = min(n, len(entries))
    while 0 < k < len(entries) and entries[k]["pct"] == entries[n - 1]["pct"]:
        k += 1
    return entries[:k]


class ArmTools:
    def __init__(self, *, regulation: str, allow_live: bool, calc: CalcClient | None = None) -> None:
        assert allow_live is False, "arm tools run offline only (ADR-014)"
        self.regulation = regulation
        self.allow_live = allow_live
        self.calc = calc or CalcClient()
        self.snap = legality.load_snapshot()

    # -- snapshot lookups ---------------------------------------------------
    def get_typing(self, species: str) -> dict[str, Any]:
        types = legality.species_types(self.snap, species)
        if types is None:
            return {"status": "not_found", "query": species, "source": LEGALITY_SOURCE}
        return {"status": "ok", "species": self.snap["species"][to_id(species)]["name"], "types": types, "source": LEGALITY_SOURCE}

    def get_abilities(self, species: str) -> dict[str, Any]:
        abilities = legality.species_abilities(self.snap, species)
        if abilities is None:
            return {"status": "not_found", "query": species, "source": LEGALITY_SOURCE}
        return {"status": "ok", "species": self.snap["species"][to_id(species)]["name"], "abilities": abilities, "source": LEGALITY_SOURCE}

    def check_species_legal(self, species: str) -> dict[str, Any]:
        known = to_id(species) in self.snap["species"]
        return {"status": "ok", "query": species, "in_snapshot": known,
                "legal": legality.is_species_legal(self.snap, species), "source": LEGALITY_SOURCE}

    def check_item_legal(self, item: str) -> dict[str, Any]:
        known = to_id(item) in self.snap["items"]
        return {"status": "ok", "query": item, "in_snapshot": known, "legal_as_held_item": legality.is_item_legal(self.snap, item),
                "source": LEGALITY_SOURCE}

    def get_move_static(self, move: str) -> dict[str, Any]:
        m = (self.snap.get("moves") or {}).get(to_id(move))
        if m is None:
            return {"status": "not_found", "query": move, "source": LEGALITY_SOURCE}
        return {"status": "ok", "move": m["name"], "type": m.get("type"), "category": m.get("category"),
                "base_power": m.get("basePower"), "source": LEGALITY_SOURCE}

    # -- calc-backed --------------------------------------------------------
    def get_speed(self, species: str, nature: str, speed_sp: int) -> dict[str, Any]:
        spec = {"species": species, "nature": nature, "evs": {"spe": speed_sp}, "level": 50}
        try:
            r = self.calc.calculate(spec, dict(SPEED_FILLER["opponent"], level=50), SPEED_FILLER["move"])
        except CalcClientError as exc:
            return _err("calc_error", str(exc.body), source=CALC_SOURCE)
        return {"status": "ok", "species": species, "nature": nature, "speed_sp": speed_sp,
                "speed": r["raw"]["stats"]["attacker"]["spe"],
                "note": "final Speed stat from calc; no item, stat stage, weather, terrain or Tailwind applied",
                "source": CALC_SOURCE}

    def calc_damage(self, attacker: dict[str, Any], defender: dict[str, Any], move: str,
                    field: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            req_a, req_d = _mon(attacker), _mon(defender)
            req_f = _field(field)
        except ValueError as exc:
            return _err("bad_arguments", str(exc))
        try:
            r = self.calc.calculate(req_a, req_d, move, req_f)
        except CalcClientError as exc:
            return _err("calc_error", str(exc.body), source=CALC_SOURCE)
        raw = r["raw"]
        return {"status": "ok", "move": move, "request": {"attacker": req_a, "defender": req_d, "field": req_f},
                "damage_rolls": raw.get("damage"), "damage_range": r["damageRange"],
                "defender_hp": raw["stats"]["defender"]["hp"], "ko_text": r["koChance"], "kochance": raw.get("kochance"),
                "calc_desc": raw.get("desc"), "ability_resolution": r.get("abilityResolution"), "source": CALC_SOURCE}

    # -- usage --------------------------------------------------------------
    def get_usage_items(self, species: str, source: str, n: int = 5) -> dict[str, Any]:
        if source not in USAGE_SOURCES:
            return _err("invalid_source", "source must be 'ingame' or 'showdown'")
        rows = ingame_ladder_species_map(self.regulation) if source == "ingame" else showdown_species_map(self.regulation)
        row = rows.get(to_id(species))
        label = "in-game usage ladder (offline snapshot)" if source == "ingame" else "Showdown usage (offline snapshot)"
        if row is None:
            return {"status": "not_found", "query": species, "requested_source": source, "source": label}
        items = [{"name": x["name"], "pct": x["pct"]} for x in row.get("common_items") or []]
        out = {"status": "ok", "species": row["name"], "source": label, "n_requested": n,
               "listed_count": len(items), "items": top_n_with_ties(items, n)}
        if source == "ingame" and to_id(species) in mega_capable_base_ids():
            out["caveat"] = "in-game usage for a Mega-capable base species mixes base-form and Mega-form usage"
        return out

    def get_usage_teammates(self, species: str, source: str) -> dict[str, Any]:
        res = arm_query_teammates(species, source=source, regulation=self.regulation, allow_live=self.allow_live)
        return {"source": f"{source} usage (offline snapshot)", **to_jsonable(res)}

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Dispatch by tool name; bad names/arguments and unexpected exceptions come back as error results."""
        fn = getattr(self, name, None)
        if name not in TOOL_NAMES or fn is None:
            return _err("unknown_tool", f"no tool named {name!r}")
        try:
            return fn(**args)
        except TypeError as exc:
            return _err("bad_arguments", str(exc))
        except Exception as exc:  # noqa: BLE001 - the loop records the failure rather than dying
            return _err("unexpected_failure", f"{type(exc).__name__}: {exc}")


def _mon(spec: dict[str, Any]) -> dict[str, Any]:
    extra = set(spec) - _MON_KEYS
    if extra or "species" not in spec:
        raise ValueError(f"pokemon needs 'species' and only {sorted(_MON_KEYS)}; got extra {sorted(extra)}")
    out = {k: v for k, v in spec.items() if k != "sp" and v is not None}
    if spec.get("sp") is not None:
        out["evs"] = spec["sp"]
    out["level"] = 50
    return out


def _field(field: dict[str, Any] | None) -> dict[str, Any] | None:
    if not field:
        return None
    extra = set(field) - _FIELD_KEYS
    if extra:
        raise ValueError(f"field keys must be among {sorted(_FIELD_KEYS)}; got {sorted(extra)}")
    return field


def _spec(name: str, description: str, **props: Any) -> dict[str, Any]:
    required = [k for k, v in props.items() if not v.pop("optional", False)]
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": required}}}


_S = {"type": "string"}
_MON_SCHEMA = {"type": "object", "description": "species, nature, sp (dict hp/atk/def/spa/spd/spe -> Champions SP 0-32), item, ability, boosts"}
TOOL_SPECS: list[dict[str, Any]] = [
    _spec("get_typing", "Types of a species or form id (e.g. 'Glalie-Mega').", species=dict(_S)),
    _spec("get_abilities", "Abilities of a species or form id; a Mega form lists its single ability.", species=dict(_S)),
    _spec("check_species_legal", "Whether a species or form id is legal in Champions VGC.", species=dict(_S)),
    _spec("check_item_legal", "Whether an item is legal as a held item in Champions VGC.", item=dict(_S)),
    _spec("get_move_static", "Type, category and base power of a move.", move=dict(_S)),
    _spec("get_speed", "Final Speed stat from the calc for a species, nature and Speed SP (no item or field effects).",
          species=dict(_S), nature=dict(_S), speed_sp={"type": "integer"}),
    _spec("calc_damage", "Damage calc for one move. Returns the calc's rolls, range, defender HP and KO text. Level is always 50; "
          "critical hits are not supported. field may set gameType, weather, terrain, attackerSide, defenderSide.",
          attacker=dict(_MON_SCHEMA), defender=dict(_MON_SCHEMA), move=dict(_S), field={"type": "object", "optional": True}),
    _spec("get_usage_items", "Most-used held items for a species from one usage source, with percentages, plus any entries tied at rank n.",
          species=dict(_S), source={"type": "string", "enum": list(USAGE_SOURCES)}, n={"type": "integer", "optional": True}),
    _spec("get_usage_teammates", "Teammate list for a species from one usage source (in-game lists carry rank only).",
          species=dict(_S), source={"type": "string", "enum": list(USAGE_SOURCES)}),
]
TOOL_NAMES = frozenset(s["function"]["name"] for s in TOOL_SPECS)
