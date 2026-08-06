from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Generic, Literal, NotRequired, Optional, TypeVar, TypedDict, Union

from langgraph.graph.message import add_messages

from recommender.calc_client import FieldSpec, PokemonSpecOptional
from recommender.matchup import MatchupResult, Severity

T = TypeVar("T")

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


@dataclass
class ReasonRef:
    kind: Literal[
        "user_stated",
        "archetype",
        "core_detection",
        "role_compendium",
        "tier2_heuristic",
        "tier1_cache",
    ]
    ref: Optional[str] = None


@dataclass
class Attr(Generic[T]):
    value: Optional[T] = None
    locked: bool = False
    reason: Optional[ReasonRef] = None
    still_active: bool = True
    exempt_from_theme: bool = False


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


class RejectedEntry(TypedDict):
    species: str
    reason: str
    turn: int


class ConstraintPayload(TypedDict):
    type: Literal["hard", "soft"]
    predicate: str
    scope: Literal["per_slot", "team_wide"]
    groundedness: Literal[
        "mechanically-checkable",
        "enumerable-but-uncoded",
        "judgment-only",
    ]


class RejectionPayload(TypedDict, total=False):
    species: str
    slot_index: int
    reason: str


SlotAttrName = Literal["role", "species", "item", "moveset", "spread", "nature"]


class LockPayload(TypedDict, total=False):
    slot_index: int
    attr: SlotAttrName
    value: object
    locks: list[dict[str, object]]  # [{attr, value}, ...] for N-attr simultaneous lock


class ArchetypeChangePayload(TypedDict):
    components: list[str]


class ResetPayload(TypedDict, total=False):
    archetype: list[str]
    constraint: ConstraintPayload


class RestorePayload(TypedDict):
    slot_index: int
    attr: SlotAttrName


class SupersededEntry(TypedDict):
    slot_index: int
    attr: SlotAttrName
    value: object
    reason: str
    turn_removed: int


class PendingFlag(TypedDict):
    slot_index: int
    attr: SlotAttrName
    value: object
    flag_kind: str


TurnPayload = Union[
    ConstraintPayload,
    RejectionPayload,
    LockPayload,
    ArchetypeChangePayload,
    ResetPayload,
    RestorePayload,
]


class VerificationEntry(TypedDict):
    claim: str
    tool_called: str
    result: str
    turn: int


@dataclass
class Slot:
    role: Attr[str] = field(default_factory=Attr)
    species: Attr[str] = field(default_factory=Attr)
    item: Attr[str] = field(default_factory=Attr)
    moveset: Attr[list[str]] = field(default_factory=Attr)
    spread: Attr[dict[str, int]] = field(default_factory=Attr)
    nature: Attr[str] = field(default_factory=Attr)
    rationale: str = ""
    verification: list[VerificationEntry] = field(default_factory=list)


@dataclass
class Constraint:
    type: Literal["hard", "soft"]
    predicate: str
    source_turn: int
    still_active: bool = True
    scope: Literal["per_slot", "team_wide"] = "per_slot"
    groundedness: Literal[
        "mechanically-checkable",
        "enumerable-but-uncoded",
        "judgment-only",
    ] = "mechanically-checkable"


@dataclass(frozen=True)
class ThreatCandidate:
    """One form-level threat after in-game inclusion + optional Showdown expand."""

    ladder_species: str
    usage_rank: int | None
    form: str
    showdown_usage_pct: float | None
    showdown_formes: tuple[tuple[str, float], ...]
    spec: PokemonSpecOptional
    build_source: str  # showdown_form | ingame | showdown_partial_fallback
    # query_counters axis tags (empty for get_relevant_threats path)
    threat_kinds: frozenset[str] = frozenset()  # "ko_threshold" | "wall"
    ko_threshold_score: float = 0.0
    ko_best_was_stab: bool = False


@dataclass(frozen=True)
class ThreatCounterCandidate:
    """Teammate candidate from query_threat_counters (ADR-022 depth-one)."""

    candidate: ThreatCandidate
    threats_countered: tuple[str, ...]  # to_id species keys credited in merge
    threats_countered_count: int
    verified_score: float
    verified_vs: tuple[tuple[str, MatchupResult], ...]


@dataclass(frozen=True)
class ThreatCoverageResult:
    threat: PokemonSpecOptional
    best_outcome: MatchupResult
    covering_slot_indices: list[int]
    forced_field: FieldSpec | None
    flagged: bool


@dataclass(frozen=True)
class SPOFFinding:
    slot_index: int
    threats_lost: list[PokemonSpecOptional]
    threat_severity: dict[str, Severity]


@dataclass(frozen=True)
class TeamReviewResult:
    threats: list[ThreatCandidate]
    coverage: list[ThreatCoverageResult]
    spofs: list[SPOFFinding]


class RecommenderState(TypedDict):
    format_id: str
    game_type: str
    regulation_mod: str
    picked_team_size: int

    available_pool: list[PokemonSet]
    team_draft: list[Slot]
    archetype: Attr[list[str]]

    rejected: list[RejectedEntry]
    constraints: list[Constraint]
    messages: Annotated[list, add_messages]

    pending_input: NotRequired[Optional[str]]
    turn_intent: NotRequired[Optional[str]]
    turn_payload: NotRequired[Optional[TurnPayload]]
    turn: NotRequired[int]
    superseded: NotRequired[list[SupersededEntry]]
    pending_flags: NotRequired[list[PendingFlag]]
    last_team_review: NotRequired[Optional[TeamReviewResult]]


def all_locked(slot: Slot) -> bool:
    return all(
        getattr(slot, f).locked for f in ("role", "species", "item", "moveset", "spread")
    )


def core(state: RecommenderState) -> list[Slot]:
    """Slots with at least one unlocked attribute — the team's still-open shape."""
    return [s for s in state["team_draft"] if not all_locked(s)]


def empty_slot() -> Slot:
    return Slot()
