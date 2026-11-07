"""FU70 item 9: harness tests for #322 / #323 (no arm-tool changes)."""

from __future__ import annotations

import re

import pytest

from recommender.state import all_locked
from scripts.eval.part_g_arm.state.request_set_rows import (
    load_covered_ids,
    load_request_rows,
    resolve_start_state,
)

# Lock-count phrases that must not silently load empty_team (#322 acceptance 4).
_LOCK_COUNT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bone locked\b", re.I), "one"),
    (re.compile(r"\bslot\s*1 locked\b", re.I), "slot1"),
    (re.compile(r"\b2 locked\b", re.I), "two"),
    (re.compile(r"\btwo locked\b", re.I), "two"),
    (re.compile(r"[≥>=]=\s*1 locked|[≥>=]1 locked|≥1 locked|>=1 locked", re.I), "at_least_one"),
]


def _locked_slot_count(state: dict) -> int:
    return sum(1 for slot in state["team_draft"] if all_locked(slot))


def _species_locked_count(state: dict) -> int:
    return sum(1 for slot in state["team_draft"] if slot.species.locked and slot.species.value)


def _expected_kind(state_cell: str) -> str | None:
    for pat, kind in _LOCK_COUNT_PATTERNS:
        if pat.search(state_cell or ""):
            return kind
    return None


def test_322_lock_count_state_cells_match_loaded_start():
    """#322 acceptance 4: lock-count cells must load a matching seed, not empty."""
    rows = {r["id"]: r for r in load_request_rows()}
    covered = load_covered_ids()
    checked = 0
    failures: list[str] = []
    for rid in sorted(covered):
        row = rows.get(rid)
        if row is None:
            continue
        cell = row.get("state") or ""
        kind = _expected_kind(cell)
        if kind is None:
            continue
        state, meta = resolve_start_state(row)
        checked += 1
        if not meta.get("loaded") or state is None:
            failures.append(f"{rid}: lock-count cell {cell!r} failed to load ({meta.get('error')})")
            continue
        n_full = _locked_slot_count(state)
        n_species = _species_locked_count(state)
        source = str(meta.get("source") or "")
        if source == "empty_team" or (n_full == 0 and n_species == 0):
            failures.append(
                f"{rid}: cell {cell!r} loaded empty (source={source!r}); "
                "lock-count cells must not silently become empty_team"
            )
            continue
        if kind == "one" and n_full < 1 and n_species < 1:
            failures.append(f"{rid}: expected ≥1 locked slot, got full={n_full} species={n_species}")
        elif kind == "slot1":
            slot0 = state["team_draft"][0]
            if not (slot0.species.locked and slot0.species.value):
                failures.append(f"{rid}: slot1 locked cell but slot 1 has no locked species")
        elif kind == "two" and n_full < 2 and n_species < 2:
            failures.append(f"{rid}: expected 2 locked slots, got full={n_full} species={n_species}")
        elif kind == "at_least_one" and n_full < 1 and n_species < 1:
            failures.append(f"{rid}: expected ≥1 locked, got full={n_full} species={n_species}")
    assert checked >= 4, f"expected to check known lock-count rows, checked={checked}"
    assert not failures, "\n".join(failures)


def test_323_sc2_and_tb2_load():
    """#323 acceptance 3: SC2 and TB2 must load a start state."""
    rows = {r["id"]: r for r in load_request_rows()}
    for rid in ("SC2", "TB2"):
        assert rid in load_covered_ids(), f"{rid} missing from covered_list"
        state, meta = resolve_start_state(rows[rid])
        assert meta.get("loaded") is True, (rid, meta)
        assert state is not None
        assert state["team_draft"][0].species.value, (rid, meta)


def test_323_all_covered_rows_resolve_loaded():
    """#323 acceptance 2 companion: every covered row loads (or this fails)."""
    rows = {r["id"]: r for r in load_request_rows()}
    bad: list[str] = []
    for rid in sorted(load_covered_ids()):
        row = rows.get(rid)
        if row is None:
            bad.append(f"{rid}: not in request set")
            continue
        _state, meta = resolve_start_state(row)
        if not meta.get("loaded"):
            bad.append(f"{rid}: loaded=False error={meta.get('error')!r} source={meta.get('source')!r}")
    assert not bad, "\n".join(bad)
