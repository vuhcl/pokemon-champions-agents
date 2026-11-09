"""FU74: optional revised key set (keys_fu72 ∪ keys_fu74), overrides, seeds.

Default (committed) path is unchanged. Callers pass key_set='fu74' to opt in.
fu74 turns replace fu72 turns for the same row_id__tN key (no point merge).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FU72 = HERE / "keys_fu72"
FU74 = HERE / "keys_fu74"
SEEDS = FU72 / "seeds"
OVERRIDES = FU72 / "request_text_overrides_fu72.json"
REV5 = FU74 / "expected_tools_rev5_2026-11-07.csv"
REV3 = HERE / "expected_tools_fu16" / "expected_tools_rev3_2026-11-02.csv"
HAND72 = FU72 / "hand_keys_fu72.json"
HAND74 = FU74 / "hand_keys_fu74.json"
MANIFEST74 = FU74 / "KEYS_MANIFEST_FU74.json"

# Row ids whose keys_fu72 seeds load under --keys fu74 only.
FU74_SEED_ROWS: frozenset[str] = frozenset(
    {"DM2", "H18b", "MR3", "MR4", "MS2", "MS3", "MW2", "RB1", "TB2"}
)

_KEY_SET: str = "committed"


def set_key_set(key_set: str) -> None:
    global _KEY_SET
    if key_set not in {"committed", "fu74"}:
        raise ValueError(f"unknown key_set {key_set!r}; use committed|fu74")
    _KEY_SET = key_set


def key_set() -> str:
    return _KEY_SET


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_tools_csv(key_set: str) -> Path:
    if key_set == "fu74":
        return REV5
    return REV3


def load_request_text_overrides(key_set: str) -> dict[str, str]:
    if key_set != "fu74":
        return {}
    return dict(json.loads(OVERRIDES.read_text(encoding="utf-8")))


def merge_hand_turns(key_set: str) -> dict[str, Any]:
    """Committed: empty (hand audit uses part3 acceptance). fu74: fu72 then fu74 replace."""
    if key_set != "fu74":
        return {}
    base = json.loads(HAND72.read_text(encoding="utf-8"))["turns"]
    overlay = json.loads(HAND74.read_text(encoding="utf-8"))["turns"]
    out = dict(base)
    for tid, turn in overlay.items():
        out[tid] = turn  # replace, do not merge points
    return out


def points_by_row_id(key_set: str) -> dict[str, list[dict[str, str]]]:
    """hand_audit_form points_by_id: one list per row (t1 points; multi-turn later)."""
    turns = merge_hand_turns(key_set)
    by_row: dict[str, list[dict[str, str]]] = {}
    for tid, turn in sorted(turns.items()):
        rid = turn["row_id"]
        # First turn wins as the rubric list for the form (multi-turn rows keep
        # per-turn keys in merge_hand_turns; form historically is per-row).
        if rid in by_row and turn.get("turn", 1) != 1:
            continue
        if turn.get("turn", 1) == 1 or rid not in by_row:
            by_row[rid] = [
                {"id": p["id"], "text": p["text"]} for p in turn.get("points") or []
            ]
    return by_row


def apply_turn_text_override(
    row_id: str, turn_index_0: int, text: str, *, key_set: str
) -> str:
    if key_set != "fu74":
        return text
    key = f"{row_id}__t{turn_index_0 + 1}"
    return load_request_text_overrides(key_set).get(key, text)


def pin_hashes_for_key_set(key_set: str) -> dict[str, str]:
    if key_set != "fu74":
        return {"key_set": "committed"}
    man = json.loads(MANIFEST74.read_text(encoding="utf-8"))
    out: dict[str, str] = {
        "key_set": "fu74",
        "revised_key_hash": man["revised_key_hash"],
        "keys_fu74_key_hash": man["key_hash"],
        "keys_fu72_key_hash": man["keys_fu72_key_hash"],
        "request_text_overrides_fu72_sha256": _sha(OVERRIDES),
        "expected_tools_rev5_sha256": _sha(REV5),
        "hand_keys_fu74_sha256": _sha(HAND74),
        "hand_keys_fu72_sha256": _sha(HAND72),
        "seed_index_sha256": _sha(SEEDS / "SEED_INDEX.json"),
    }
    for name in json.loads((SEEDS / "SEED_INDEX.json").read_text(encoding="utf-8"))["files"]:
        out[f"seed_{name}_sha256"] = _sha(SEEDS / name)
    return out


def _seed_path_for_row(row_id: str) -> Path | None:
    for path in SEEDS.glob("*.json"):
        if path.name == "SEED_INDEX.json":
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("row") == row_id:
            return path
    return None


def _lock_attrs(
    state: dict[str, Any],
    *,
    user_slot: int,
    species: str,
    item: str | None,
    ability: str | None,
    nature: str | None,
    moves: list[str] | None,
    evs: dict[str, int] | None,
    locks: dict[str, bool] | None,
) -> dict[str, Any]:
    # Use pending's internal locker (same path as build_fully_locked_slot).
    from scripts.eval.part_g_arm.state.pending import _lock_internal
    from recommender.slot_index import user_slot_to_index
    from recommender.state import Attr
    from dataclasses import replace

    index = user_slot_to_index(user_slot)
    values: dict[str, Any] = {"species": species, "role": "bulky_offense"}
    if ability is not None:
        values["ability"] = ability
    if item is not None:
        values["item"] = item
    if nature is not None:
        values["nature"] = nature
    if moves is not None:
        values["moveset"] = list(moves)
    if evs is not None:
        values["spread"] = dict(evs)
    raw_locks = dict(locks or {})
    if "moves" in raw_locks and "moveset" not in raw_locks:
        raw_locks["moveset"] = bool(raw_locks.pop("moves"))
    lock_map = {k: True for k in values}
    lock_map.update(raw_locks)
    lock_map["role"] = True
    for attr, value in values.items():
        state = _lock_internal(state, index, attr, value)
        if not bool(lock_map.get(attr, True)):
            slot = state["team_draft"][index]
            cur = getattr(slot, attr)
            state["team_draft"][index] = replace(
                slot,
                **{
                    attr: Attr(
                        value=cur.value,
                        locked=False,
                        reason=getattr(cur, "reason", None),
                        exempt_from_theme=getattr(cur, "exempt_from_theme", False),
                    )
                },
            )
    return state


def load_fu74_seed_state(row_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Load keys_fu72/seeds for a row. Caller must only invoke under key_set=fu74."""
    from scripts.eval.part_g_arm.state.fixtures import empty_team
    from scripts.eval.part_g_arm.state.pending import try_load_fixture

    meta: dict[str, Any] = {
        "row": row_id,
        "loaded": False,
        "complete": False,
        "source": None,
        "error": None,
    }
    if row_id not in FU74_SEED_ROWS:
        meta["error"] = f"no fu74 seed mapping for {row_id}"
        return None, meta
    path = _seed_path_for_row(row_id)
    if path is None:
        meta["error"] = f"seed file missing for {row_id}"
        return None, meta
    doc = json.loads(path.read_text(encoding="utf-8"))
    meta["seed_file"] = path.name

    if doc.get("source_fixture"):
        result = try_load_fixture(doc["source_fixture"])
        if result["loaded"] and result["state"] is not None:
            meta.update(
                {
                    "loaded": True,
                    "complete": True,
                    "source": f"keys_fu72/seeds/{path.name}→{doc['source_fixture']}",
                }
            )
            return result["state"], meta
        meta["error"] = result.get("error") or "fixture load failed"
        return None, meta

    state = empty_team()
    slots = list(doc.get("slots") or [])
    if not slots:
        for key, default_slot in (("primary", 1), ("secondary", 2)):
            block = doc.get(key)
            if isinstance(block, dict) and block.get("species"):
                slots.append({"user_slot": default_slot, **block, "locks": {}})
    for block in slots:
        if not isinstance(block, dict) or not block.get("species"):
            continue
        user_slot = int(block.get("user_slot") or block.get("slot") or 1)
        locks = block.get("locks")
        if locks == "all fields locked (sticky refusal path)" or locks is None:
            locks = {
                "species": True,
                "ability": True,
                "item": True,
                "moveset": True,
                "nature": True,
                "spread": True,
            }
        state = _lock_attrs(
            state,
            user_slot=user_slot,
            species=str(block["species"]),
            item=block.get("item"),
            ability=block.get("ability"),
            nature=block.get("nature"),
            moves=list(block["moves"]) if isinstance(block.get("moves"), list) else None,
            evs=block.get("evs") if isinstance(block.get("evs"), dict) else None,
            locks=locks if isinstance(locks, dict) else None,
        )
    meta.update(
        {
            "loaded": True,
            "complete": True,
            "source": f"keys_fu72/seeds/{path.name}",
        }
    )
    return state, meta


def rev5_user_turn_text(row_id: str, turn: int = 1) -> str | None:
    import csv

    with REV5.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["row_id"] == row_id and int(row["turn"]) == turn:
                return row["user_turn_text"]
    return None
