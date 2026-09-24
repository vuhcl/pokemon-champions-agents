"""Bare-LLM baseline prompts (no tools, open-ended team build)."""

from __future__ import annotations

# Open-ended Reg M-C doubles request — not scaffolded for SP/Item Clause/legality.
INITIAL_PROMPT = (
    "I'm building a VGC 2026 Regulation M-C doubles team for Pokémon Champions. "
    "Can you put together a full 6-Pokémon team with items, abilities, moves, and "
    "spreads, and explain why the picks work together?"
)

CONTINUER = (
    "Please continue and finish the full 6-Pokémon team with sets when you can."
)

# At most once; only if ≥4 slots extracted and zero organic mech claims so far.
SOFT_MECH_NUDGE = (
    "Before we wrap up — are there any speed or damage matchups that make these picks work?"
)

TURN_CAP = 16
DEFAULT_RUNS = 5
TEMPERATURE = 0.7
