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
FROZEN_PROMPT_SHA256 = "b71764852eb66f87f17375ff3226a7e4be7517b09eb8961fb56e779fe32badd8"

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

    # Idle / empty / bootstrap → empty team (still a valid start).
    state_cell = (row.get("state") or "").strip().lower()
    idle_tokens = (
        "idle",
        "empty",
        "bootstrap",
        "—",
        "-",
        "none",
        "any",
        "nonempty",
        "occupied",
        "ambiguous",
        "mid-build",
        "after",
        "one locked",
        "two slots",
        "2 locked",
        "≥1 locked",
        "multi options",
        "slot1 locked",
        "incineroar locked",
        "tyranitar",
    )
    if any(state_cell.startswith(t) or t in state_cell for t in ("idle", "empty", "bootstrap")) or state_cell in {
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
        "mid-build",
    }:
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
