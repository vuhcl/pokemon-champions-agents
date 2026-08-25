"""One-shot: extract nodes_classify.py from nodes.py (lines 60-1851)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODES = ROOT / "recommender" / "nodes.py"
OUT = ROOT / "recommender" / "nodes_classify.py"

HEADER = '''"""Turn-intent classification, spread validation, and gap-fill (extracted from nodes)."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Literal, Optional

from langgraph.types import RunnableConfig

from recommender.calc_client import CalcClientError
from recommender.ids import to_id
from recommender.legality import check_set, load_snapshot
from recommender.matchup import MatchupEvidenceError
from recommender.present_text import BOOTSTRAP_PARSER_NOT_CONFIGURED
from recommender.recommend import SP_BUDGET, spread_sum
from recommender.reconcile import simultaneous_lock_conflicts
from recommender.species_resolve import resolve_species_label
from recommender.state import (
    Attr,
    BootstrapResponsePayload,
    CandidateDiscoveryError,
    PendingPresentation,
    PendingFlag,
    PendingSlotIntent,
    ProvisionalSlot,
    ReasonRef,
    RecommenderState,
    Slot,
    TargetRoleDecision,
    UnresolvedSlotRefinement,
    empty_slot,
    slot_fingerprint,
)

'''

REEXPORTS = """
# Re-exported by recommender.nodes for graph.py and tests.
__all__ = [
    "CONTINUE_ABANDON_MSG",
    "KEEP_BUILD_MSG",
    "_BLOCKED_ON_KIND",
    "_MISMATCH_MSG",
    "build_gap_fill_context",
    "classify_pending",
    "find_option_reference_anywhere",
    "resolve_item_moveset_conflict",
    "resolve_spread_reallocation",
    "resolve_spread_target_question",
]
"""


def main() -> None:
    lines = NODES.read_text().splitlines(keepends=True)
    body = "".join(lines[59:1851])
    OUT.write_text(HEADER + body + "\n")
    print("wrote", OUT, "lines", len((HEADER + body).splitlines()))


if __name__ == "__main__":
    main()
