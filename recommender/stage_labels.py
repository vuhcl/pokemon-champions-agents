"""Authored status labels for the hosted demo.

A name that is not in the map returns "Working…", never the raw node name.
"""

from __future__ import annotations

_PLACEHOLDER = "Working…"

# Keys are build_graph() node names. __start__ and __end__ are not nodes we label.
LABELS: dict[str, str] = {
    "initialize": "Setting up your session",
    "accept_available_pool": "Getting started",
    "classify_input": "Reading your message",
    "apply_lock": "Locking in your pick",
    "record_constraint": "Noting your preference",
    "record_rejection": "Noting what you ruled out",
    "handle_archetype_change": "Switching team style",
    "reset_team": "Starting the team over",
    "restore_superseded": "Restoring an earlier choice",
    "restore_constraint": "Restoring an earlier preference",
    "route_team_phase": "Deciding the next step",
    "bootstrap_direction": "Choosing a starting direction",
    "record_bootstrap_response": "Noting your starting choice",
    "discover_single_locked": "Finding partners for your pick",
    "refresh_team_signals": "Checking how the team fits together",
    "discover_multi_locked": "Finding partners for your picks",
    "generate_team_review": "Reviewing your team",
    "finish_pending_response": "Wrapping up",
    "refine_provisional_slot": "Drafting a build for your pick",
    "apply_provisional_edit": "Applying your change to the build",
    "apply_provisional_option": "Applying the option you picked",
    "resolve_spread_reallocation": "Re-balancing the stat points",
    "resolve_spread_target_question": "Working out the stat points",
    "resolve_item_moveset_conflict": "Checking the item and moves fit",
    "compare_build_options": "Comparing build options",
    "commit_full_slot": "Checking the build is legal and locking it in",
    "begin_locked_slot_revision": "Opening a copy of that Pokémon to edit",
    "unlock_locked_slot": "Clearing that Pokémon so you can pick again",
    "handle_claim_correction": "Correcting an earlier answer",
}


def stage_label(node_name: str) -> str:
    return LABELS.get(node_name, _PLACEHOLDER)
