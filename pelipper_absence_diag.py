"""
Single-lock Pelipper-absence diagnostic -- calls the REAL discover_multi_locked
node directly, not a reimplementation. Run with the local calc service up.

    cd pokemon-champions-agents
    python3 pelipper_absence_diag.py

Prints the full _rank_key tuple (not just fills_essential_gap) for every
candidate in the ranked pool, so we can see directly whether Pelipper:
  (a) isn't in the pool at all,
  (b) is in the pool with fills_essential_gap=False (unexpected -- would
      mean the essential-gap detection itself differs from the sandbox
      repro), or
  (c) is in the pool with fills_essential_gap=True but still ranks below
      the cutoff (would mean there are >= as many other essential-gap
      fillers with better secondary-field scores, or n itself is smaller
      than expected).

This distinguishes those three cases directly instead of guessing further.
"""

from recommender.state import Attr, Slot, empty_slot
from recommender.nodes import discover_multi_locked
from recommender.team_candidates import _rank_key, _BASIS_RANK, _CONFIDENCE_RANK

_RANK_FIELD_NAMES = (
    "fills_essential_gap",
    "uncovered_verified_decisive",
    "uncovered_verified_costly",
    "composition_fit_rank",
    "preference_fit",
    "uncovered_verified_toss-up",
    "uncovered_conditional_decisive",
    "uncovered_conditional_costly",
    "uncovered_conditional_toss-up",
    "spof_verified_decisive",
    "spof_verified_costly",
    "spof_verified_toss-up",
    "len_anchor_ids",
    "len_distinct_needs",
    "best_evidence_basis_rank",
    "best_evidence_confidence_rank",
    "shared_min_pct",
    "neg_shared_worst_rank",
)


def locked_archaludon() -> Slot:
    return Slot(
        role=Attr("bulky_special_attacker", locked=True),
        species=Attr("Archaludon", locked=True),
        ability=Attr("Stamina", locked=True),
        item=Attr("Leftovers", locked=True),
        moveset=Attr(
            ["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"], locked=True
        ),
        spread=Attr(
            # Exact Calm spread from the reproducing session (spread_nature:4
            # off the Modest default), not the Timid offensive spread the
            # earlier diagnostic run used -- that run correctly showed
            # Pelipper #1, this build did not in the live session. Isolating
            # whether the spread/nature choice itself is the variable.
            {"hp": 32, "atk": 0, "def": 1, "spa": 1, "spd": 25, "spe": 7},
            locked=True,
        ),
        nature=Attr("Calm", locked=True),
    )


if __name__ == "__main__":
    team_draft = [locked_archaludon()] + [empty_slot() for _ in range(5)]
    state = {
        "team_draft": team_draft,
        "regulation_mod": "champions-reg-mb",
        "rejected": [],
        "ownership_mode": "off",
        "constraints": [],
        "team_completion_preference": None,  # match the real fresh-session state
    }
    config = {"configurable": {"thread_id": "diag"}}

    # --- Call the REAL node directly. No reimplementation. ---
    out = discover_multi_locked(state, config)

    if out.get("candidate_discovery_error") is not None:
        print("discover_multi_locked returned an error -- check calc service:")
        print(out["candidate_discovery_error"])
        raise SystemExit(1)

    pending = out.get("pending_presentation")
    if pending is None:
        print("No pending_presentation returned -- check candidate_discovery_error above.")
        raise SystemExit(1)

    if pending.get("kind") == "completion_preference":
        print("Hit the completion_preference branch first (material_completion_preferences")
        print("returned real choices) -- team_completion_preference wasn't pre-set. This")
        print("itself may be relevant: it means preference isn't None by the time")
        print("rank_multi_locked_candidates runs in the real flow, once you answer it.")
        print("preference_options:", pending.get("preference_options"))
        raise SystemExit(0)

    print(f"pending_presentation.kind = {pending.get('kind')}")
    print("\nDisplayed options (what the user actually sees):")
    for opt in pending.get("options") or []:
        print(" ", opt.get("species"), "-", opt.get("source"))

    # The ranked-and-annotated candidate objects aren't in the trimmed
    # pending_presentation dict, so recompute them the same way the node
    # does internally, using the SAME state/config/signals this run just
    # produced -- not a fresh, possibly-inconsistent recomputation.
    from recommender.condition_resilience import assess_condition_resilience
    from recommender.team_candidates import (
        annotate_composition_impact,
        build_team_threat_objective,
        collect_locked_anchor_contexts,
        merge_multi_locked_candidates,
        owned_species_ids,
        rank_multi_locked_candidates,
    )
    from recommender.threat_counters import query_candidates_for_threats
    from recommender.usage_data import lineage_ids

    ownership_mode = state.get("ownership_mode", "off")
    owned = owned_species_ids(state)
    contexts = collect_locked_anchor_contexts(state)
    resilience = out["condition_resilience"]
    # Re-fetch the real review object directly rather than stubbing a
    # partial one from `out`'s trimmed signals -- build_team_threat_objective
    # needs .threats too, not just .coverage/.spofs.
    from recommender.nodes import _compute_team_review

    review = _compute_team_review(state, config)
    objective = build_team_threat_objective(review)
    locked_species = [str(c.resolved_build.species) for c in contexts]
    excluded = {lid for sp in locked_species for lid in lineage_ids(sp)}
    threat_discovery = query_candidates_for_threats(
        objective, available_pool=sorted(owned), ownership_mode=ownership_mode,
        excluded_species=excluded,
    )
    merged = merge_multi_locked_candidates(
        state, contexts, threat_discovery.candidates, out["shared_teammates"],
        ownership_mode=ownership_mode, owned_species=owned,
        condition_resilience=resilience,
    )
    annotated = annotate_composition_impact(
        merged, state, locked_anchors=contexts, condition_resilience=resilience
    )
    preference = state.get("team_completion_preference")
    ranked = rank_multi_locked_candidates(
        annotated, objective=objective, preference=preference,
        ownership_mode=ownership_mode, owned_species=owned,
        regulation=state.get("regulation_mod") or "champions-reg-mb",
    )

    print(f"\nTotal ranked pool size: {len(ranked)}")
    rain_species = {"Pelipper", "Politoed", "Klefki", "Liepard", "Meowstic", "Sableye"}

    pelipper = next((c for c in ranked if c.species == "Pelipper"), None)
    if pelipper is None:
        print("\n>>> Pelipper is NOT in the ranked pool at all. Check merge_multi_locked_candidates")
        print(">>> / query_candidates_for_threats eligibility filtering next, not ranking.")
    else:
        rank_pos = ranked.index(pelipper) + 1
        key = _rank_key(pelipper, objective, preference, state.get("regulation_mod") or "champions-reg-mb")
        print(f"\nPelipper: rank position {rank_pos} of {len(ranked)}")
        print(f"  fills_essential_gap = {pelipper.fills_essential_gap}")
        for name, val in zip(_RANK_FIELD_NAMES, key):
            print(f"    {name}: {val}")

    print("\nFull rank-key breakdown, top 8 (and any rain-setter further down):")
    shown = set()
    for i, c in enumerate(ranked, start=1):
        if i > 8 and c.species not in rain_species:
            continue
        key = _rank_key(c, objective, preference, state.get("regulation_mod") or "champions-reg-mb")
        star = "*" if c.species in rain_species else " "
        print(f"  {i}. {star} {c.species:15s} key={key}")
        shown.add(c.species)
