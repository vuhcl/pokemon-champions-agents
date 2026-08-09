from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Annotated, Generic, Literal, NotRequired, Optional, TypeVar, TypedDict, Union

from langgraph.graph.message import add_messages

from recommender.calc_client import FieldSpec, PokemonSpecOptional
from recommender.matchup import MatchupResult, Severity
from recommender.ranking import OwnershipMode
from recommender.teammate_types import SharedTeammateQueryResult

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


SlotAttrName = Literal[
    "role", "species", "ability", "item", "moveset", "spread", "nature"
]


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


OwnershipModeSource = Literal["default", "user"]


class BootstrapResponsePayload(TypedDict):
    direction_text: str | None
    anchor_text: str | None
    pool_entries: tuple[str, ...] | None
    delegated: bool
    ownership_mode: OwnershipMode | None


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


PresentationSource = Literal[
    "threat", "need", "both", "teammate", "mixed", "bootstrap"
]
CandidateEvidenceBasis = Literal[
    "usage_backed",
    "compendium_backed",
    "mechanical_only",
    "synthesized",
    "teammate_backed",
    "ownership_backed",
]
CandidateConfidence = Literal["high", "medium", "low"]
CandidateBranch = Literal["threat", "need", "teammate"]
CompositionFit = Literal[
    "severe_duplication", "duplicative", "neutral", "complementary"
]
TeamCompletionPreference = Literal["attacker", "support", "balanced"]
TargetRoleId = Literal[
    "fast_attacker",
    "bulky_attacker",
    "bulky_pivot",
    "fast_pivot",
    "trick_room_sweeper",
    "trick_room_setter",
    "tailwind_setter",
    "rain_setter",
    "sun_setter",
    "sand_setter",
    "snow_setter",
    "redirection",
    "swords_dance_attacker",
    "nasty_plot_attacker",
]
TargetRoleConfidence = Literal["high", "medium", "low"]
TargetRoleSource = Literal["_pick_role", "support_need", "user_choice", "other"]


@dataclass(frozen=True)
class CandidateEvidence:
    """Why one presented species entered the candidate set."""

    basis: CandidateEvidenceBasis
    confidence: CandidateConfidence
    producer_name: str
    evidence: tuple[str, ...] = ()
    branch: CandidateBranch | None = None
    origin_slot_index: int | None = None
    origin_anchor_id: str | None = None
    subject_id: str | None = None


@dataclass(frozen=True)
class CandidateDiscoveryError:
    kind: Literal[
        "calc_unavailable",
        "calc_incomplete",
        "no_candidates",
        "unsupported_constraint",
    ]
    stage: Literal[
        "constraint_validation",
        "coverage",
        "spof",
        "candidate_verification",
        "candidate_merge",
    ]
    message: str
    retryable: bool
    exception_type: str | None = None
    status_code: int | None = None


@dataclass(frozen=True)
class TargetRoleDecision:
    """Resolved, open-slot role intent kept separate from anchor classification."""

    role_id: TargetRoleId
    source: TargetRoleSource
    evidence: tuple[str, ...] = ()
    needed_constraints: tuple[str, ...] = ()
    wanted_constraints: tuple[str, ...] = ()
    confidence: TargetRoleConfidence = "medium"
    ambiguity: tuple[TargetRoleId, ...] = ()
    provenance: tuple[str, ...] = ()
    producer_name: str | None = None


@dataclass(frozen=True)
class UnresolvedTargetRoleDecision:
    """A role choice that must not be silently collapsed to one option."""

    reason: Literal["ambiguous_speed_control", "incompatible_support_roles"]
    ambiguity: tuple[TargetRoleId, ...]
    source: TargetRoleSource
    evidence: tuple[str, ...] = ()
    needed_constraints: tuple[str, ...] = ()
    wanted_constraints: tuple[str, ...] = ()
    confidence: Literal["unresolved"] = "unresolved"
    provenance: tuple[str, ...] = ()
    producer_name: str | None = None


TargetRoleResult = TargetRoleDecision | UnresolvedTargetRoleDecision


class PendingPresentationOption(TypedDict):
    species: str
    source: PresentationSource
    target_role_decision: NotRequired[TargetRoleResult]
    evidence: NotRequired[tuple[CandidateEvidence, ...]]
    direction_label: NotRequired[str]
    strategic_role_id: NotRequired[str]
    primary_function: NotRequired[Literal["offense", "support", "unknown"]]
    mechanism_ids: NotRequired[tuple[str, ...]]


class PendingPresentation(TypedDict, total=False):
    schema_version: int
    kind: Literal[
        "candidate_selection",
        "full_build_confirmation",
        "completion_preference",
        "bootstrap_intake",
    ]
    slot_index: int
    options: list[PendingPresentationOption]
    preference_options: tuple[TeamCompletionPreference, ...]
    provisional_fingerprint: str
    prompt_text: str
    existing_pool_labels: tuple[str, ...]
    notices: tuple[str, ...]


@dataclass(frozen=True)
class PendingSlotIntent:
    schema_version: int
    slot_index: int
    species: str
    target_role_decision: TargetRoleResult | None
    source: PresentationSource
    evidence: tuple[CandidateEvidence, ...] = ()
    base_slot_fingerprint: str = ""
    stage: Literal["candidate_selected"] = "candidate_selected"


@dataclass(frozen=True)
class ProvisionalSlot:
    schema_version: int
    slot_index: int
    target_role_decision: TargetRoleDecision
    species: str
    ability: str
    item: str
    moves: tuple[str, str, str, str]
    nature: str
    spread: tuple[tuple[str, int], ...]
    base_slot_fingerprint: str = ""
    fingerprint: str = ""

    @property
    def role(self) -> TargetRoleId:
        return self.target_role_decision.role_id

    def spread_dict(self) -> dict[str, int]:
        return dict(self.spread)


@dataclass(frozen=True)
class UnresolvedSlotRefinement:
    schema_version: int
    intent: PendingSlotIntent
    unresolved_fields: tuple[str, ...]
    reason: Literal["incomplete_build", "unresolved_target_role"] = "incomplete_build"


TurnPayload = Union[
    ConstraintPayload,
    RejectionPayload,
    LockPayload,
    ArchetypeChangePayload,
    ResetPayload,
    RestorePayload,
    BootstrapResponsePayload,
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
    ability: Attr[str] = field(default_factory=Attr)
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
    status: Literal["available", "unavailable"] = "available"
    error: CandidateDiscoveryError | None = None


ThreatObjectiveKind = Literal["uncovered", "spof"]


@dataclass(frozen=True)
class TeamThreatObjectiveRow:
    threat: ThreatCandidate
    kinds: frozenset[ThreatObjectiveKind]
    spof_slot_indices: tuple[int, ...] = ()
    baseline_outcome: MatchupResult | None = None


@dataclass(frozen=True)
class TeamThreatDiscovery:
    status: Literal["available", "unavailable"]
    candidates: tuple[ThreatCounterCandidate, ...]
    error: CandidateDiscoveryError | None = None


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
    pending_presentation: NotRequired[Optional[PendingPresentation]]
    pending_slot_intent: NotRequired[Optional[PendingSlotIntent]]
    provisional_slot: NotRequired[Optional[ProvisionalSlot]]
    provisional_refinement: NotRequired[Optional[UnresolvedSlotRefinement]]
    slot_commit_error: NotRequired[Optional[str]]
    last_team_review: NotRequired[Optional[TeamReviewResult]]
    coverage: NotRequired[list[ThreatCoverageResult]]
    spofs: NotRequired[list[SPOFFinding]]
    shared_teammates: NotRequired[Optional["SharedTeammateQueryResult"]]
    ownership_mode: NotRequired["OwnershipMode"]
    ownership_mode_source: NotRequired[OwnershipModeSource]
    bootstrap_intake_complete: NotRequired[bool]
    bootstrap_response: NotRequired[Optional[BootstrapResponsePayload]]
    bootstrap_intake_error: NotRequired[Optional[str]]
    unresolved_pool_entries: NotRequired[tuple[str, ...]]
    team_completion_preference: NotRequired[Optional[TeamCompletionPreference]]
    candidate_discovery_error: NotRequired[Optional[CandidateDiscoveryError]]


def all_locked(slot: Slot) -> bool:
    return all(
        getattr(slot, f).locked
        for f in ("role", "species", "ability", "item", "moveset", "spread", "nature")
    )


def slot_fingerprint(slot: Slot) -> str:
    """Stable value/lock fingerprint used to reject stale full-slot commits."""
    payload = {
        name: {
            "value": getattr(slot, name).value,
            "locked": getattr(slot, name).locked,
        }
        for name in ("role", "species", "ability", "item", "moveset", "spread", "nature")
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def core(state: RecommenderState) -> list[Slot]:
    """Slots with at least one unlocked attribute — the team's still-open shape."""
    return [s for s in state["team_draft"] if not all_locked(s)]


def empty_slot() -> Slot:
    return Slot()
