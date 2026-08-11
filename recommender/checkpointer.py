"""SQLite checkpointer for the CLI runtime.

Usage::

    from recommender.checkpointer import open_sqlite_checkpointer
    from recommender.graph import compile_graph

    graph = compile_graph(checkpointer=open_sqlite_checkpointer())

Caller owns the SqliteSaver / connection for process lifetime.
Do not wrap ``from_conn_string`` in a short-lived context manager for CLI.

Serialization (JsonPlusSerializer / ormsgpack): pass an explicit
``allowed_msgpack_modules`` of every dataclass that can appear in
``RecommenderState``. Unlisted types warn today and will be dropped later.

Known gotcha — tuple fields revive as lists (ormsgpack arrays → list; LangGraph's
EXT_CONSTRUCTOR_KW_ARGS does ``cls(**kwargs)`` with no annotation coercion). Affects
e.g. TargetRoleDecision.evidence/ambiguity/provenance/needed_constraints/
wanted_constraints, PendingSlotIntent.evidence, ProvisionalSlot.moves/spread,
CandidateEvidence.evidence. Reconstruction still succeeds (no __post_init__). Current
post-restart call sites are sequence-generic (len/iter/list()/dict(pairs)/== between
two revived objects). Fresh-vs-revived ``==`` and hashing the frozen dataclass both
break (list fields are unhashable). Do not put revived instances in a set/dict key.
If a caller needs real tuples post-restart, normalize on read — do not assume tuple.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

from recommender.condition_types import (
    ConditionDependentMember,
    ConditionProviderMember,
    ConditionResilienceReport,
    ConditionResilienceRow,
)
from recommender.matchup import MatchupCaveats, MatchupResult
from recommender.state import (
    Attr,
    CandidateDiscoveryError,
    CandidateEvidence,
    Constraint,
    PendingSlotIntent,
    ProvisionalSlot,
    ReasonRef,
    Slot,
    SPOFFinding,
    TargetRoleDecision,
    TeamReviewResult,
    ThreatCandidate,
    ThreatCoverageResult,
    UnresolvedSlotRefinement,
    UnresolvedTargetRoleDecision,
)
from recommender.teammate_types import (
    SharedAnchorEvidence,
    SharedTeammate,
    SharedTeammateQueryResult,
    TeammateEvidence,
    TeammateQueryResult,
)

# Dataclasses that can sit in a checkpoint. SAFE_MSGPACK_TYPES stay allowed separately.
_CHECKPOINT_MSGPACK_TYPES = (
    Attr,
    CandidateDiscoveryError,
    CandidateEvidence,
    ConditionDependentMember,
    ConditionProviderMember,
    ConditionResilienceReport,
    ConditionResilienceRow,
    Constraint,
    MatchupCaveats,
    MatchupResult,
    PendingSlotIntent,
    ProvisionalSlot,
    ReasonRef,
    SharedAnchorEvidence,
    SharedTeammate,
    SharedTeammateQueryResult,
    Slot,
    SPOFFinding,
    TargetRoleDecision,
    TeammateEvidence,
    TeammateQueryResult,
    TeamReviewResult,
    ThreatCandidate,
    ThreatCoverageResult,
    UnresolvedSlotRefinement,
    UnresolvedTargetRoleDecision,
)

_ENV_DB = "POKEMON_CHAMPIONS_CHECKPOINT_DB"
_APP_DIR = "pokemon-champions-agents"
_DB_NAME = "checkpoints.db"


def default_db_path() -> Path:
    override = os.environ.get(_ENV_DB)
    if override:
        return Path(override).expanduser()
    home = Path.home()
    if sys.platform == "darwin":
        base = home / "Library" / "Application Support" / _APP_DIR
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / _APP_DIR
    return base / _DB_NAME


def open_sqlite_checkpointer(path: Path | str | None = None) -> SqliteSaver:
    db = Path(path) if path is not None else default_db_path()
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db), check_same_thread=False)
    return SqliteSaver(
        conn,
        serde=JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_MSGPACK_TYPES),
    )
