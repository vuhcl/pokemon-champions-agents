"""CLI session identity: mint, list, and resume incomplete threads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping
from uuid import uuid4

from recommender.nodes import team_phase
from recommender.state import all_locked

DEFAULT_FORMAT_ID = "[Gen 9 Champions] VGC 2026 Reg M-B"


def mint_thread_id() -> str:
    return f"team-{uuid4().hex}"


def thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def thread_exists(saver, thread_id: str) -> bool:
    return saver.get_tuple(thread_config(thread_id)) is not None


def is_incomplete(state: Mapping[str, Any]) -> bool:
    if not state or "team_draft" not in state:
        return False
    if team_phase(state) != "complete":  # type: ignore[arg-type]
        return True
    return bool(
        state.get("pending_presentation")
        or state.get("pending_slot_intent")
        or state.get("provisional_slot")
    )


@dataclass(frozen=True)
class ThreadSummary:
    thread_id: str
    phase: str
    locked_count: int
    pending_kind: str | None
    incomplete: bool
    checkpoint_id: str


def list_thread_summaries(graph, saver) -> list[ThreadSummary]:
    """Newest-first unique threads from saver.list(None).

    Materialize list() fully before get_state — nested queries on the same
    SqliteSaver connection deadlock while the list cursor is open.
    """

    seen: set[str] = set()
    newest: list[tuple[str, str]] = []
    for tup in saver.list(None):
        cfg = tup.config.get("configurable") or {}
        thread_id = str(cfg.get("thread_id") or "")
        if not thread_id or thread_id in seen:
            continue
        seen.add(thread_id)
        newest.append((thread_id, str(cfg.get("checkpoint_id") or "")))

    out: list[ThreadSummary] = []
    for thread_id, checkpoint_id in newest:
        values = graph.get_state(thread_config(thread_id)).values or {}
        if "team_draft" not in values:
            out.append(
                ThreadSummary(
                    thread_id=thread_id,
                    phase="unknown",
                    locked_count=0,
                    pending_kind=None,
                    incomplete=False,
                    checkpoint_id=checkpoint_id,
                )
            )
            continue
        draft = values["team_draft"]
        locked_count = sum(1 for slot in draft if all_locked(slot))
        pending = values.get("pending_presentation")
        kind = pending.get("kind") if pending else None
        out.append(
            ThreadSummary(
                thread_id=thread_id,
                phase=team_phase(values),  # type: ignore[arg-type]
                locked_count=locked_count,
                pending_kind=str(kind) if kind else None,
                incomplete=is_incomplete(values),
                checkpoint_id=checkpoint_id,
            )
        )
    return out


def pick_newest_incomplete(summaries: list[ThreadSummary]) -> str | None:
    for summary in summaries:
        if summary.incomplete:
            return summary.thread_id
    return None


def resolve_thread_id(
    *,
    mode: Literal["new", "resume", "explicit"],
    explicit_id: str | None,
    summaries: list[ThreadSummary],
) -> tuple[str, bool]:
    """Return (thread_id, is_new_session)."""

    if mode == "new":
        return mint_thread_id(), True
    if mode == "explicit":
        if not explicit_id:
            raise ValueError("explicit thread id required")
        return explicit_id, False
    picked = pick_newest_incomplete(summaries)
    if picked is None:
        return mint_thread_id(), True
    return picked, False
