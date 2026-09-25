"""Bare-LLM baseline prompts — two conditions, never averaged.

Conditions
----------
chat  — "ungrounded chat baseline"
        One open-ended whole-team ask (real-user chat shape). Not a CLI mirror.

slot  — "ungrounded, matched decomposition"
        Slot-by-slot theme → species → set flow mirroring CLI decomposition,
        still with no tools / no legality or SP coaching.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# chat — ungrounded chat baseline
# ---------------------------------------------------------------------------

CHAT_INITIAL = (
    "I'm building a VGC 2026 Regulation M-C doubles team for Pokémon Champions. "
    "Can you put together a full 6-Pokémon team with items, abilities, moves, and "
    "spreads, and explain why the picks work together?"
)

CHAT_CONTINUER = (
    "Please continue and finish the full 6-Pokémon team with sets when you can."
)

# ---------------------------------------------------------------------------
# slot — ungrounded, matched decomposition
# ---------------------------------------------------------------------------

SLOT_INITIAL = (
    "I'm building a VGC 2026 Regulation M-C doubles team for Pokémon Champions. "
    "Let's build it the way a team builder would: pick a theme or core first, then "
    "fill each of the 6 slots one at a time (species, then a full set) before "
    "moving on. Start with your theme."
)

# Scripted user turns after the model's *theme* reply (first assistant turn).
# steer[0] is the first post-theme user message — do not insert SP/EV/Item Clause
# or legality coaching into these strings.
SLOT_STEERING: tuple[str, ...] = (
    "Recommend species for slot 1 and briefly why it fits the theme.",
    "Lock that species. Give the full set for slot 1 in Pokémon Showdown paste "
    "format (Species @ Item / Ability / Nature / EVs or SP line / four moves).",
    "Recommend species for slot 2 and briefly why.",
    "Lock that. Full set for slot 2 in Showdown paste format.",
    "Recommend species for slot 3 and briefly why.",
    "Lock that. Full set for slot 3 in Showdown paste format.",
    "Recommend species for slot 4 and briefly why.",
    "Lock that. Full set for slot 4 in Showdown paste format.",
    "Recommend species for slot 5 and briefly why.",
    "Lock that. Full set for slot 5 in Showdown paste format.",
    "Recommend species for slot 6 and briefly why.",
    "Lock that. Full set for slot 6 in Showdown paste format.",
)

SLOT_CONTINUER = (
    "Please continue with the next step toward finishing all 6 slots with full sets."
)

# Shared soft mech nudge (at most once; same honesty rule for both conditions).
SOFT_MECH_NUDGE = (
    "Before we wrap up — are there any speed or damage matchups that make these picks work?"
)

TURN_CAP_CHAT = 16
TURN_CAP_SLOT = 24  # theme + 12 steered turns + slack / nudge
DEFAULT_RUNS = 5
TEMPERATURE = 0.7

# Back-compat aliases (chat condition).
INITIAL_PROMPT = CHAT_INITIAL
CONTINUER = CHAT_CONTINUER
TURN_CAP = TURN_CAP_CHAT


@dataclass(frozen=True)
class Condition:
    id: str
    label: str
    initial: str
    turn_cap: int


CONDITIONS: dict[str, Condition] = {
    "chat": Condition(
        id="chat",
        label="ungrounded chat baseline",
        initial=CHAT_INITIAL,
        turn_cap=TURN_CAP_CHAT,
    ),
    "slot": Condition(
        id="slot",
        label="ungrounded, matched decomposition",
        initial=SLOT_INITIAL,
        turn_cap=TURN_CAP_SLOT,
    ),
}
