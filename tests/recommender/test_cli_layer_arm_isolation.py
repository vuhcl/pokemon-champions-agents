"""FU71/FU73: flag-off arm surface must not move vs main.

Golden hashes were captured from main (not a feature branch). Regenerate only on purpose
from main's tool code:
``python -c "from tests.recommender.test_cli_layer_arm_isolation import write_golden; write_golden()"``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.eval.part_g_arm.state.fixtures import empty_team, one_locked_slot
from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot
from scripts.eval.part_g_arm.state.set_slot_tool import set_slot
from scripts.eval.part_g_arm.state.tools import (
    combined_specs,
    commit_slot,
    confirm_build,
    edit_slot_field,
    lock_slot,
    reset_team_state,
    set_draft,
    set_ix_tools_v1,
    set_tool_fields,
    set_tool_fixes_v2,
    set_wrapper,
    unlock_slot,
)

GOLDEN = Path(__file__).parent / "fixtures" / "arm_wrapper_outputs_fu71.json"


def _all_flags_off() -> None:
    set_tool_fixes_v2(False)
    set_ix_tools_v1(False)
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)


def _probe() -> dict[str, str]:
    # Flag-off must match main / a393ae91 shapes (no FU70/FU73 extras).
    _all_flags_off()
    locked = one_locked_slot("Venusaur", 1)
    full = build_fully_locked_slot("Incineroar", user_slot=1)
    locked_for_edit, _ = lock_slot(empty_team(), 1, "Venusaur")

    def _set_slot_ok():
        set_wrapper(True)
        try:
            return set_slot(
                empty_team(),
                {"slot": 1, "species": "Venusaur", "item": "Leftovers"},
            )
        finally:
            set_wrapper(False)
            set_ix_tools_v1(False)

    def _schema():
        _all_flags_off()
        return combined_specs()

    calls = {
        "lock_slot_2": lambda: lock_slot(empty_team(), 2, "Venusaur"),
        "lock_slot_0": lambda: lock_slot(empty_team(), 0, "Venusaur"),
        "lock_slot_7": lambda: lock_slot(empty_team(), 7, "Venusaur"),
        "lock_illegal": lambda: lock_slot(empty_team(), 1, "Bulbasaur"),
        "unlock_locked": lambda: unlock_slot(locked, 1),
        "unlock_full_ok": lambda: unlock_slot(full, 1),
        "unlock_empty": lambda: unlock_slot(empty_team(), 2),
        "unlock_slot_0": lambda: unlock_slot(empty_team(), 0),
        "edit_item_ok": lambda: edit_slot_field(
            locked_for_edit, 1, "item", "Sitrus Berry"
        ),
        "set_slot_ok": _set_slot_ok,
        "reset_locked": lambda: reset_team_state(locked),
        "reset_empty": lambda: reset_team_state(empty_team()),
        "commit_idle": lambda: commit_slot(empty_team()),
        "confirm_idle": lambda: confirm_build(empty_team()),
        # FU73: schema must stay byte-identical when ix_tools_v1 is off.
        "combined_specs_flag_off": _schema,
    }
    return {name: hashlib.sha256(repr(call()).encode()).hexdigest() for name, call in calls.items()}


def write_golden() -> None:
    GOLDEN.parent.mkdir(exist_ok=True)
    GOLDEN.write_text(json.dumps(_probe(), indent=1, sort_keys=True) + "\n")


def test_arm_wrapper_output_is_byte_identical_to_main():
    assert _probe() == json.loads(GOLDEN.read_text())
