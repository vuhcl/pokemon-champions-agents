#!/usr/bin/env python3
"""Scripted elicitation turns for species-fact pending_response baseline eval."""

from __future__ import annotations

SETUP = "trick room with Hatterene"

# Navigate / lock
PICK = "1"
YES = "yes"
DEFER = "defer"
CONTINUE = "continue"

# Phrases that (in live probes) produce llm_authored pending_response more often
# than CLASSIFY_FAIL / claim_correction misroutes. Claim-bearing hits are rarer
# on qwen2.5:7b — include type/ability nudges anyway.
ELICIT: dict[str, list[str]] = {
    "candidate_selection": [
        "pick something else, maybe a water type",
        "I want a grass type",
        "tell me each option's typing before I choose",
        "none of these — need something with Intimidate",
        "is there a steel type option among these?",
    ],
    "full_build_confirmation": [
        "what type is this species again?",
        "does this set use Dry Skin?",
        "make it more like a special attacker but clarify the typing",
        "remind me if Hatterene is Psychic/Fairy",
    ],
    "completion_preference": [
        "whatever covers grass types best",
        "I want intimidate support preference",
        "lean toward electric coverage",
    ],
    "idle": [
        "suggest a grass type for the next slot",
        "I want a fire type next",
        "need something with Levitate",
        "what about a fairy type next?",
    ],
}

# Targeted gap-fill probes (same turn_intent_parser; not classify_pending mock).
# Used when graph conversation under-produces claim-bearing clarifications.
GAP_FILL_PROBES: list[tuple[str, str, list[str]]] = [
    (
        "candidate_selection",
        "Options: 1 Heliolisk 2 Abomasnow 3 Whimsicott. User asked for grass type.",
        [
            "tell me each option's typing before I choose",
            "I asked for grass; list each option's typing",
        ],
    ),
    (
        "full_build_confirmation",
        "Confirming Heliolisk build. Ability Dry Skin on the default.",
        [
            "what type is Heliolisk before I confirm?",
            "does Heliolisk have Dry Skin on this set?",
        ],
    ),
    (
        "completion_preference",
        "preference_options: attacker, support, balanced",
        [
            "prefer whatever covers water types best — which typing helps?",
        ],
    ),
    (
        "none",
        "No pending. Roster has Hatterene. Open slot next.",
        [
            "suggest a grass type for the next slot and name its typing",
        ],
    ),
]
