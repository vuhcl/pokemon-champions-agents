from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages

StatsTable = TypedDict(
    "StatsTable",
    {
        "hp": int,
        "atk": int,
        "def": int,
        "spa": int,
        "spd": int,
        "spe": int,
    },
)

# ponytail: pack/export/import open — use a Node @pkmn/sets bridge (likely shared with
# @smogon/calc) or hand-roll Python later; TypedDict shape only until then. Do not invent a parser here.
class PokemonSet(TypedDict, total=False):
    name: str  # nickname in Showdown
    species: str
    item: str
    ability: str
    moves: list[str]
    nature: str
    gender: str
    evs: StatsTable
    ivs: StatsTable
    level: int
    shiny: bool
    happiness: int
    pokeball: str
    hiddenPowerType: str
    gigantamax: bool
    dynamaxLevel: int
    teraType: str


class Slot(TypedDict):
    set: PokemonSet
    locked: bool
    rationale: str
    slot_index: int


class RejectedEntry(TypedDict):
    species: str
    reason: str
    turn: int


class Constraint(TypedDict):
    type: Literal["hard", "soft"]
    predicate: str
    source_turn: int
    still_active: bool


class VerificationEntry(TypedDict):
    claim: str
    tool_called: str
    result: str
    turn: int


class RecommenderState(TypedDict):
    format_id: str
    game_type: str
    regulation_mod: str
    picked_team_size: int

    available_pool: list[PokemonSet]
    team_draft: list[Slot]

    rejected: list[RejectedEntry]
    constraints: list[Constraint]
    verification_log: list[VerificationEntry]
    messages: Annotated[list, add_messages]


def empty_slot(slot_index: int) -> Slot:
    return {"set": {}, "locked": False, "rationale": "", "slot_index": slot_index}
