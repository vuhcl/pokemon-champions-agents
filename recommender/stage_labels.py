"""Authored status labels for the hosted demo.

Every value is a placeholder. The real wording is written after the node list
is reviewed. A missing name still returns the placeholder, never the raw node name.
"""

from __future__ import annotations

_PLACEHOLDER = "Working…"

# Keys are build_graph() node names. __start__ and __end__ are not nodes we label.
LABELS: dict[str, str] = {
    "initialize": _PLACEHOLDER,
    "accept_available_pool": _PLACEHOLDER,
    "classify_input": _PLACEHOLDER,
    "apply_lock": _PLACEHOLDER,
    "record_constraint": _PLACEHOLDER,
    "record_rejection": _PLACEHOLDER,
    "handle_archetype_change": _PLACEHOLDER,
    "reset_team": _PLACEHOLDER,
    "restore_superseded": _PLACEHOLDER,
    "restore_constraint": _PLACEHOLDER,
    "route_team_phase": _PLACEHOLDER,
    "bootstrap_direction": _PLACEHOLDER,
    "record_bootstrap_response": _PLACEHOLDER,
    "discover_single_locked": _PLACEHOLDER,
    "refresh_team_signals": _PLACEHOLDER,
    "discover_multi_locked": _PLACEHOLDER,
    "generate_team_review": _PLACEHOLDER,
    "finish_pending_response": _PLACEHOLDER,
    "refine_provisional_slot": _PLACEHOLDER,
    "apply_provisional_edit": _PLACEHOLDER,
    "apply_provisional_option": _PLACEHOLDER,
    "resolve_spread_reallocation": _PLACEHOLDER,
    "resolve_spread_target_question": _PLACEHOLDER,
    "resolve_item_moveset_conflict": _PLACEHOLDER,
    "compare_build_options": _PLACEHOLDER,
    "commit_full_slot": _PLACEHOLDER,
    "begin_locked_slot_revision": _PLACEHOLDER,
    "unlock_locked_slot": _PLACEHOLDER,
    "handle_claim_correction": _PLACEHOLDER,
}


def stage_label(node_name: str) -> str:
    return LABELS.get(node_name, _PLACEHOLDER)
