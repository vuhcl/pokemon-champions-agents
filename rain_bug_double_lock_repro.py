"""
Rain-suggestion degradation bug — verified repro, run this with the local
calc service up (needed for real verified_vs threat-coverage scoring, which
this sandbox couldn't provide).

Every import and function signature in this script has already been
confirmed against the real repo (tip 2623f7a as of this writing) — this is
not a placeholder like the earlier draft. Run it from the repo root:

    cd pokemon-champions-agents
    python3 rain_bug_double_lock_repro.py

WHAT'S ALREADY CONFIRMED (don't re-derive):
  - Finding 1 (display bug) is CLOSED. present_text.py's
    _format_candidate_selection reads evidence_rows[0] instead of the best
    evidence item. Root cause: Archaludon's universal "screens" need
    resolves through the generic mechanical fallback (screens isn't in
    _compendium_roles_for_need's category map, even though
    screens_support.v1.json exists), tagging screens-capable species like
    Meowstic with mechanical_only/low entries that land ahead of their real
    compendium_backed/medium Rain entry in the merged evidence tuple.
  - Rain's condition_resilience classification stays essential/
    missing_provider correctly across both single- and double-lock — the
    original "dilution" hypothesis is disproven.

WHAT THIS SCRIPT IS FOR: Finding 2 is still open. Without a live calc
service, the earlier sandbox run couldn't confirm whether Rain candidates
genuinely get outranked by Trick Room candidates once Sinistcha's real
threat coverage enters the objective (a legitimate ranking outcome) or
whether something is actually suppressing them (a real bug). This script
prints the verified_vs/threat-coverage numbers _rank_key actually uses,
so you can see which one it is directly instead of inferring from rank
position alone.
"""

from recommender.state import Attr, Slot, empty_slot
from recommender.team_candidates import (
    collect_locked_anchor_contexts,
    merge_multi_locked_candidates,
    build_team_threat_objective,
    annotate_composition_impact,
    rank_multi_locked_candidates,
)
from recommender.condition_resilience import assess_condition_resilience
from recommender.threat_counters import query_candidates_for_threats
from recommender.usage_data import lineage_ids
from recommender.nodes import _compute_team_review, query_shared_teammates

_BASIS_RANK = {
    "synthesized": 0,
    "ownership_backed": 0,
    "teammate_backed": 1,
    "mechanical_only": 2,
    "usage_backed": 3,
    "compendium_backed": 4,
}
_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def locked_archaludon() -> Slot:
    # Real accepted build from the live transcript (default Timid spread).
    return Slot(
        role=Attr("bulky_special_attacker", locked=True),
        species=Attr("Archaludon", locked=True),
        ability=Attr("Stamina", locked=True),
        item=Attr("Leftovers", locked=True),
        moveset=Attr(
            ["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"], locked=True
        ),
        spread=Attr(
            {"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32},
            locked=True,
        ),
        nature=Attr("Timid", locked=True),
    )


def locked_sinistcha() -> Slot:
    return Slot(
        role=Attr("trick_room_setter", locked=True),
        species=Attr("Sinistcha", locked=True),
        ability=Attr("Hospitality", locked=True),
        item=Attr("Kasib Berry", locked=True),
        moveset=Attr(
            ["Matcha Gotcha", "Rage Powder", "Trick Room", "Protect"], locked=True
        ),
        spread=Attr(
            {"hp": 32, "atk": 0, "def": 32, "spa": 2, "spd": 0, "spe": 0},
            locked=True,
        ),
        nature=Attr("Bold", locked=True),
    )


def best_evidence(candidate) -> tuple[str, str]:
    if not candidate.evidence:
        return ("none", "none")
    item = max(
        candidate.evidence,
        key=lambda e: (_BASIS_RANK[e.basis], _CONFIDENCE_RANK[e.confidence]),
    )
    return (item.basis, item.confidence)


def run(label: str, slots: list[Slot]) -> None:
    team_draft = slots + [empty_slot() for _ in range(6 - len(slots))]
    state = {
        "team_draft": team_draft,
        "regulation_mod": "champions-reg-mb",
        "rejected": [],
        "ownership_mode": "off",
        "constraints": [],
    }
    contexts = collect_locked_anchor_contexts(state)
    resilience = assess_condition_resilience(contexts)
    rain_row = next((r for r in resilience.conditions if r.condition == "Rain"), None)

    review = _compute_team_review(state, {"configurable": {"thread_id": "t"}})
    locked_species = [str(c.resolved_build.species) for c in contexts]
    shared = query_shared_teammates(locked_species, "champions")
    objective = build_team_threat_objective(review)
    excluded = {lid for sp in locked_species for lid in lineage_ids(sp)}
    threat_discovery = query_candidates_for_threats(
        objective, available_pool=[], ownership_mode="off", excluded_species=excluded
    )

    merged = merge_multi_locked_candidates(
        state,
        contexts,
        threat_discovery.candidates,
        shared,
        ownership_mode="off",
        owned_species=frozenset(),
        condition_resilience=resilience,
    )
    annotated = annotate_composition_impact(
        merged, state, locked_anchors=contexts, condition_resilience=resilience
    )
    ranked = rank_multi_locked_candidates(
        annotated,
        objective=objective,
        preference=None,
        ownership_mode="off",
        owned_species=frozenset(),
        regulation="champions-reg-mb",
    )

    print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
    print(
        f"Rain resilience: classification={rain_row.classification if rain_row else None} "
        f"gap={rain_row.gap if rain_row else None}"
    )
    print(f"Total ranked candidates: {len(ranked)}")

    rain_species = {"Pelipper", "Politoed", "Klefki", "Liepard", "Meowstic", "Sableye"}
    print("\nTop 8 ranked (* = known Rain-setter candidate):")
    for i, c in enumerate(ranked[:8], start=1):
        star = "*" if c.species in rain_species else " "
        displayed = (
            (c.evidence[0].basis, c.evidence[0].confidence) if c.evidence else ("none", "none")
        )
        best = best_evidence(c)
        mismatch = " <-- DISPLAY BUG" if displayed != best else ""
        # This is what _rank_key actually sorts on first -- if Rain candidates
        # are being legitimately outranked, it'll show up here as real
        # nonzero uncovered/spof counts for the candidates ranked above them.
        verified_hits = (
            len(c.threat_row.verified_vs) if c.threat_row is not None else 0
        )
        print(
            f"  {i}. {star} {c.species:15s} displayed={displayed} best={best}{mismatch} "
            f"verified_vs_count={verified_hits} composition_fit={c.composition_fit}"
        )

    rain_in_top8 = [c.species for c in ranked[:8] if c.species in rain_species]
    rain_anywhere = [c.species for c in ranked if c.species in rain_species]
    print(f"\nRain candidates in top 8: {rain_in_top8 or 'NONE'}")
    print(f"Rain candidates anywhere in ranked pool ({len(ranked)} total): {rain_anywhere or 'NONE'}")
    if not rain_anywhere:
        print(">>> Rain fully absent from the ranked pool, not just outranked -- check merge_multi_locked_candidates/eligible() filtering next.")
    elif not rain_in_top8:
        print(">>> Rain present in the pool but pushed out of the top slice shown to the user -- check whether this is legitimate (better verified_vs coverage elsewhere) or a ranking bug.")


if __name__ == "__main__":
    run("SINGLE-LOCK (Archaludon only)", [locked_archaludon()])
    run("DOUBLE-LOCK (Archaludon + Sinistcha)", [locked_archaludon(), locked_sinistcha()])
