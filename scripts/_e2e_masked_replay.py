from tests.recommender.test_masked_core import (
    _state,
    _sun_core_sequential_draft,
    _run_sequential_annotation_pipeline,
    should_try_masked_core,
)

state = _state(_sun_core_sequential_draft())
pipe = _run_sequential_annotation_pipeline(state)
pool = pipe["candidates"]
contexts = pipe["contexts"]
triggers = [
    c
    for c in pool
    if c.core_slot_conflicts and should_try_masked_core(c, pool, state, contexts)
]
print(f"should_try_masked_core triggers: {len(triggers)}")
for c in triggers:
    print(f"  {c.species} source={c.source} conflicts={len(c.core_slot_conflicts)}")

from recommender.nodes import discover_multi_locked

state2 = _state(_sun_core_sequential_draft(), team_completion_preference="balanced")
result = discover_multi_locked(state2, {"configurable": {"thread_id": "masked-e2e-replay"}})
pending = result.get("pending_presentation") or {}
print("discover_multi_locked kind:", pending.get("kind"))
