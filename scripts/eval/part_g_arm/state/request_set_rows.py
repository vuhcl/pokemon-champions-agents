"""Parse request-set rows and resolve start state for the stateful arm runner.

Read-only against part3_request_set_v4.md / derived_keys / fixtures.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.pending import build_mrb1_start, try_load_fixture

HERE = Path(__file__).resolve().parent
V4 = HERE.parents[1] / "part_g_v4"
REQUEST_SET = V4 / "part3_request_set_v4.md"
COVERED_LIST = HERE / "covered_list.json"
FROZEN_PROMPT_SHA256 = "bd2b69cde151fdb4dd2431c294ca46f4fbc251f54cebd82a13844d4eba0aaf86"

_TURN_SPLIT = re.compile(r"\(t\d+\)\s*", re.IGNORECASE)


def load_covered_ids() -> set[str]:
    doc = json.loads(COVERED_LIST.read_text(encoding="utf-8"))
    return set(doc["covered"])


def load_request_rows() -> list[dict[str, Any]]:
    sys.path.insert(0, str(V4 / "checks"))
    import check_request_set as c  # noqa: WPS433 - local checks helper

    return c.parse_rows(REQUEST_SET.read_text(encoding="utf-8"))


def parse_user_turns(prompt: str) -> list[str]:
    """Split `(t1) … (t2) …` prompts; single-turn prompts stay one element."""
    text = (prompt or "").strip()
    if not text:
        return []
    if _TURN_SPLIT.search(text):
        parts = [p.strip(" .") for p in _TURN_SPLIT.split(text) if p.strip()]
        return parts or [text]
    return [text]


def turns_for_row(row: dict[str, Any], state: dict[str, Any] | None) -> list[str]:
    """User turns the runner actually plays (seeds may skip already-applied t1)."""
    if state and state.get("_runner_turns"):
        return list(state["_runner_turns"])
    turns = parse_user_turns(row.get("prompt") or "")
    rid = row.get("id")
    if rid == "MT3" and len(turns) >= 3:
        return turns[1:]  # t1 applied as seed constraint
    if rid == "HC2" and len(turns) >= 2:
        return turns[1:]  # t1 applied as seed constraint
    return turns


# Explicit start seeds (Vu 2026-10-30). Checked before substring heuristics so
# e.g. RB1's "4th empty" cannot select empty_team.
EXPLICIT_START_SEEDS: frozenset[str] = frozenset(
    {
        "MS2",
        "MS3",
        "MR3",
        "MR4",
        "MR5",
        "MU6",
        "MW1",
        "MW2",
        "MW4",
        "MT5",
        "RB1",
    }
)


# Slot-2 default when pair would otherwise share Sitrus Berry (Item Clause = 1).
# Not Choice Scarf (MR4). Leftovers is legal on Garchomp and distinct from Sitrus.
_PAIR_SLOT2_ITEM = "Leftovers"


def _fully_locked_pair(
    first: tuple[str, int], second: tuple[str, int] | None = None
) -> dict[str, Any]:
    """Build one or two fully locked slots via build_fully_locked_slot (no fixture edits)."""
    from dataclasses import replace

    from recommender.slot_index import user_slot_to_index
    from recommender.state import Attr
    from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot

    species_a, slot_a = first
    state = build_fully_locked_slot(species_a, user_slot=slot_a)
    if second is None:
        return state
    species_b, slot_b = second
    other = build_fully_locked_slot(species_b, user_slot=slot_b)
    idx_b = user_slot_to_index(slot_b, team_size=len(state["team_draft"]))
    slot_b_obj = other["team_draft"][idx_b]
    item_a = state["team_draft"][
        user_slot_to_index(slot_a, team_size=len(state["team_draft"]))
    ].item.value
    # build_fully_locked_slot hardcodes Sitrus Berry — pair without a rewrite
    # duplicated it and violated Item Clause. Give slot 2 a distinct legal item.
    if slot_b_obj.item.value == item_a:
        slot_b_obj = replace(
            slot_b_obj,
            item=Attr(
                value=_PAIR_SLOT2_ITEM,
                locked=True,
                reason=slot_b_obj.item.reason,
                exempt_from_theme=slot_b_obj.item.exempt_from_theme,
            ),
        )
    state["team_draft"][idx_b] = slot_b_obj
    return state


def _resolve_explicit_start(
    rid: str, meta: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any]] | None:
    """Return (state, meta) for EXPLICIT_START_SEEDS rows, or None if rid not listed."""
    if rid not in EXPLICIT_START_SEEDS:
        return None
    from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot

    if rid in ("MW1", "MT5"):
        meta.update({"loaded": True, "complete": True, "source": "empty_team (explicit)"})
        return empty_team(), meta
    if rid == "MS2" or rid == "MR3":
        meta.update(
            {
                "loaded": True,
                "complete": True,
                "source": "explicit:build_fully_locked_slot(Incineroar@1)",
            }
        )
        return build_fully_locked_slot("Incineroar", user_slot=1), meta
    if rid in ("MS3", "MR4", "MU6", "MW2"):
        meta.update(
            {
                "loaded": True,
                "complete": True,
                "source": "explicit:Incineroar@1+Garchomp@2 fully locked",
            }
        )
        return _fully_locked_pair(("Incineroar", 1), ("Garchomp", 2)), meta
    if rid == "MR5":
        meta.update(
            {
                "loaded": True,
                "complete": True,
                "source": "explicit:build_fully_locked_slot(Garchomp@2)",
            }
        )
        return build_fully_locked_slot("Garchomp", user_slot=2), meta
    if rid == "MW4":
        from scripts.eval.part_g_arm.state.seeds import BUILDERS

        meta.update(
            {
                "loaded": True,
                "complete": True,
                "source": "explicit:seeds/cs_pending",
                "seed": "cs_pending",
            }
        )
        return BUILDERS["cs_pending"](), meta
    if rid == "RB1":
        path = "scripts/eval/part_g_v4/fixtures/rb1_lucario_megaz_calmmind.json"
        result = try_load_fixture(path)
        if result["loaded"] and result["state"] is not None:
            state = result["state"]
            incomplete = list(state.get("_fixture_incomplete") or [])
            meta.update(
                {
                    "loaded": True,
                    "complete": not incomplete,
                    "source": path,
                    "error": None if not incomplete else "; ".join(incomplete),
                }
            )
            return state, meta
        meta["error"] = result.get("error") or "RB1 fixture failed to load"
        return None, meta
    return None


def resolve_start_state(row: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return (state|None, meta). meta has loaded/complete/error/source/readback."""
    rid = row["id"]
    meta: dict[str, Any] = {
        "row": rid,
        "loaded": False,
        "complete": False,
        "source": None,
        "error": None,
        "readback": None,
    }
    explicit = _resolve_explicit_start(rid, meta)
    if explicit is not None:
        return explicit

    # Part 3 seeds for previously unloaded rows (MT3/MT4/MS4/MS7/MU7/HC2/HD1).
    from scripts.eval.part_g_arm.state.seeds import SEED_FOR_ROW, load_seed_state

    if rid in SEED_FOR_ROW:
        return load_seed_state(rid)

    if rid == "MRB1":
        state = build_mrb1_start()
        from recommender.slot_index import user_slot_to_index

        slot = state["team_draft"][user_slot_to_index(3)]
        meta.update(
            {
                "loaded": True,
                "complete": True,
                "source": "build_mrb1_start",
                "readback": {
                    "species": slot.species.value,
                    "ability": slot.ability.value,
                    "item": slot.item.value,
                },
            }
        )
        return state, meta

    # Named fixtures / OL ids that load_fixture understands.
    for key in (rid, rid.upper(), rid.lower()):
        try:
            result = try_load_fixture(key)
        except Exception as exc:  # noqa: BLE001
            meta["error"] = f"{type(exc).__name__}: {exc}"
            continue
        if result["loaded"] and result["state"] is not None:
            state = result["state"]
            incomplete = list(state.get("_fixture_incomplete") or [])
            meta.update(
                {
                    "loaded": True,
                    "complete": not incomplete,
                    "source": f"load_fixture({key!r})",
                    "error": None if not incomplete else "; ".join(incomplete),
                }
            )
            return state, meta

    state_cell = (row.get("state") or "").strip()
    state_l = state_cell.lower()

    # Named locked-species starts that are not fixture files.
    if state_l == "incineroar locked" or rid == "DM2":
        from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot

        meta.update({"loaded": True, "complete": True, "source": "build_fully_locked_slot(Incineroar)"})
        return build_fully_locked_slot("Incineroar", user_slot=1), meta
    if "tyranitar" in state_l or rid == "DM3":
        meta.update({"loaded": True, "complete": True, "source": "empty_team (ASSUME-STATE sides from pin)"})
        return empty_team(), meta

    # Pending screens without a named OL/v4 fixture are not invented here.
    if "cs pending" in state_l or "fbc pending" in state_l:
        meta["error"] = f"pending start {state_cell!r} needs a named OL/v4 fixture; not invented"
        return None, meta
    if state_l.startswith("after ") or state_l.startswith("after\t"):
        meta["error"] = f"multi-turn seed {state_cell!r} not built (prior turn not replayed)"
        return None, meta

    # Idle / empty / bootstrap / generic non-fixture labels → empty team.
    if (
        any(tok in state_l for tok in ("idle", "empty", "bootstrap", "mid-build"))
        or state_l in {
            "—",
            "-",
            "any",
            "nonempty",
            "occupied",
            "ambiguous",
            "none locked",
            "one locked",
            "two slots",
            "2 locked",
            "≥1 locked",
            "multi options",
            "slot1 locked",
        }
        or not state_cell
    ):
        meta.update({"loaded": True, "complete": True, "source": "empty_team"})
        return empty_team(), meta

    # Fixture path mentioned in the state cell.
    m = re.search(r"(scripts/eval/part_g_v4/(?:fixtures|ol_fixtures)/[\w./-]+\.json)", row.get("state") or "")
    if m:
        result = try_load_fixture(m.group(1))
        if result["loaded"]:
            state = result["state"]
            incomplete = list((state or {}).get("_fixture_incomplete") or [])
            meta.update(
                {
                    "loaded": True,
                    "complete": not incomplete,
                    "source": m.group(1),
                    "error": None if not incomplete else "; ".join(incomplete),
                }
            )
            return state, meta
        meta["error"] = result["error"]
        return None, meta

    meta["error"] = f"no loader for state cell {row.get('state')!r}"
    return None, meta
