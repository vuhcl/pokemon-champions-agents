"""B2b: champions must not remap to champions-reg-mb for usage maps."""

from __future__ import annotations

import inspect

from recommender.move_narrowing import assemble_moveset_fallback, narrow_candidates_for_move
from recommender.slot_fill import (
    SlotFillContext,
    _regulation,
    annotate_overlap,
    build_anchored_slot_fill_context,
    merge_need_resolved,
)
from recommender.state import Attr, Slot


def test_regulation_champions_maps_to_mc_not_mb():
    # Red on pre-B2b main: returned "champions-reg-mb".
    assert _regulation({"regulation_mod": "champions"}) == "champions-reg-mc"
    assert _regulation({"regulation_mod": "champions-reg-mc"}) == "champions-reg-mc"
    assert _regulation({"regulation_mod": "champions-reg-mb"}) == "champions-reg-mb"
    assert _regulation({}) == "champions-reg-mc"


def test_annotate_and_merge_use_ctx_regulation_not_mb_literal():
    assert "champions-reg-mb" not in inspect.getsource(annotate_overlap)
    assert "champions-reg-mb" not in inspect.getsource(merge_need_resolved)
    ctx = SlotFillContext(
        anchor=None,
        role_shape_context=None,
        regulation="champions-reg-mc",
        threat_counter_results=[],
        support_needs=[],
    )
    assert ctx.regulation == "champions-reg-mc"


def test_build_anchored_context_sets_regulation_mc(monkeypatch):
    slot = Slot(species=Attr(value="Rillaboom", locked=True))
    state = {
        "regulation_mod": "champions",
        "team_draft": [slot],
        "format_id": "[Gen 9 Champions] VGC 2026 Reg M-C",
    }

    class _Resolved:
        def as_pokemon(self):
            return {"species": "Rillaboom"}

    monkeypatch.setattr(
        "recommender.anchor_roles.resolve_anchor_build",
        lambda *a, **k: _Resolved(),
    )
    monkeypatch.setattr(
        "recommender.anchor_roles.classify_anchor_role",
        lambda *a, **k: type("D", (), {"role": "bulky_attacker"})(),
    )
    monkeypatch.setattr(
        "recommender.anchor_roles.derive_role_shape_context",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "recommender.support_needs.query_support_needs",
        lambda *a, **k: [],
    )
    monkeypatch.setattr(
        "recommender.threat_counters.query_threat_counters",
        lambda *a, **k: type(
            "Q",
            (),
            {"candidates": [], "status": "available", "error": None},
        )(),
    )
    monkeypatch.setattr(
        "recommender.team_candidates.collect_locked_anchor_contexts",
        lambda *a, **k: [],
    )
    discovery = build_anchored_slot_fill_context(state, slot)
    assert discovery.context is not None
    assert discovery.context.regulation == "champions-reg-mc"


def test_move_narrowing_no_champions_to_mb_remap():
    assert 'regulation = "champions-reg-mb"' not in inspect.getsource(
        narrow_candidates_for_move
    )
    assert 'regulation = "champions-reg-mb"' not in inspect.getsource(
        assemble_moveset_fallback
    )
    src = inspect.getsource(narrow_candidates_for_move)
    assert "regulation_file_tag" in src
    assert 'if regulation == "champions"' not in src


def test_slot_fill_context_not_in_checkpoint_allowlist():
    from recommender.checkpointer import _CHECKPOINT_MSGPACK_TYPES

    names = {t.__name__ for t in _CHECKPOINT_MSGPACK_TYPES}
    assert "SlotFillContext" not in names
