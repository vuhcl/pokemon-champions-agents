"""query_counters — data-only threat lookup (ADR-022 raw mechanical reasoning).

Two binary axes: KO-threshold (merged STAB + coverage) and wall-check.
No classify_matchup / calc-service calls.

# gap: STAT-FRAGILITY axis (ADR-022 typing/stats/kit) deferred —
# needs ruleset-conditioned Speed/bulk thresholds (Amendment 2026-07-27e).
# gap: ability-conditional damage (Adaptability, Technician) and Coil/move
# accuracy mods deferred to ADR-021 Amendment 2026-08-01b.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from recommender.calc_client import PokemonSpecOptional
from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot
from recommender.matchup import effective_accuracy, expected_hit_factor
from recommender.ranking import OwnershipMode, rank_and_cut
from recommender.state import ThreatCandidate
from recommender.usage_data import featured_or_common_set, ingame_species_map

REPO_ROOT = Path(__file__).resolve().parents[1]
_ACCURACY_PATH = REPO_ROOT / "data" / "moves" / "gen9_accuracy.v1.json"
_FLAGS_PATH = REPO_ROOT / "data" / "moves" / "flags.v1.json"

# Probe (top-20 anchors × ladder species w/ featured sets): all-pairs clear-rate
# 180→38.7% / 200→28.2%; SE-pairs 180→87.4% / 200→76.8%. Locked at 200.
KO_THRESHOLD_BP = 200

# Multiplicative bonus room: bound = round(1.5 * n). Proportional headroom;
# wall-only admit at n=20 is via usage-primary within-tier key, not this slack.
QUERY_COUNTERS_SLACK = 1.5

DEFAULT_REGULATION = "champions-reg-mb"

# Assumption A — fainted-teammate scaling (Supreme Overlord, Last Respects only).
# Average of the nonzero states {1,2,3} (=2), not {0,1,2,3} (=1.5): a rational
# player uses these specifically once the boost is worth using.
ASSUMED_FAINTED_TEAMMATES = 2

# Assumption B — hits-taken scaling (Rage Fist only). Independently justified:
# accumulating hits requires repeatedly surviving attacks (each survived hit is a
# real event the opponent failed to capitalize on); likelihood and danger both
# rise with count, so a flat average is the wrong shape. Low/conservative default;
# real ceiling belongs to deferred axis-tagged verification (ADR-021 Amendment
# 2026-08-01b). Do not inherit ASSUMED_FAINTED_TEAMMATES.
ASSUMED_HITS_TAKEN = 1

_ATE_ABILITIES: dict[str, str] = {
    "aerilate": "Flying",
    "dragonize": "Dragon",
    "pixilate": "Fairy",
    "refrigerate": "Ice",
}

_RAGING_BULL_TYPES: dict[str, str] = {
    "taurospaldeacombat": "Fighting",
    "taurospaldeablaze": "Fire",
    "taurospaldeaaqua": "Water",
}

_WEATHER_BALL_TYPES: dict[str, str] = {
    "Sun": "Fire",
    "Harsh Sunshine": "Fire",
    "Rain": "Water",
    "Heavy Rain": "Water",
    "Sand": "Rock",
    "Hail": "Ice",
    "Snow": "Ice",
}

_TERRAIN_PULSE_TYPES: dict[str, str] = {
    "Electric": "Electric",
    "Grassy": "Grass",
    "Misty": "Fairy",
    "Psychic": "Psychic",
}
# Champions = SS type chart (@smogon/calc TYPE_CHART[0]).
TYPE_CHART: dict[str, dict[str, float]] = {
    "Normal": {
        "Normal": 1, "Grass": 1, "Fire": 1, "Water": 1, "Electric": 1, "Ice": 1,
        "Flying": 1, "Bug": 1, "Poison": 1, "Ground": 1, "Rock": 0.5, "Fighting": 1,
        "Psychic": 1, "Ghost": 0, "Dragon": 1, "Dark": 1, "Steel": 0.5, "Fairy": 1,
    },
    "Grass": {
        "Normal": 1, "Grass": 0.5, "Fire": 0.5, "Water": 2, "Electric": 1, "Ice": 1,
        "Flying": 0.5, "Bug": 0.5, "Poison": 0.5, "Ground": 2, "Rock": 2, "Fighting": 1,
        "Psychic": 1, "Ghost": 1, "Dragon": 0.5, "Dark": 1, "Steel": 0.5, "Fairy": 1,
    },
    "Fire": {
        "Normal": 1, "Grass": 2, "Fire": 0.5, "Water": 0.5, "Electric": 1, "Ice": 2,
        "Flying": 1, "Bug": 2, "Poison": 1, "Ground": 1, "Rock": 0.5, "Fighting": 1,
        "Psychic": 1, "Ghost": 1, "Dragon": 0.5, "Dark": 1, "Steel": 2, "Fairy": 1,
    },
    "Water": {
        "Normal": 1, "Grass": 0.5, "Fire": 2, "Water": 0.5, "Electric": 1, "Ice": 1,
        "Flying": 1, "Bug": 1, "Poison": 1, "Ground": 2, "Rock": 2, "Fighting": 1,
        "Psychic": 1, "Ghost": 1, "Dragon": 0.5, "Dark": 1, "Steel": 1, "Fairy": 1,
    },
    "Electric": {
        "Normal": 1, "Grass": 0.5, "Fire": 1, "Water": 2, "Electric": 0.5, "Ice": 1,
        "Flying": 2, "Bug": 1, "Poison": 1, "Ground": 0, "Rock": 1, "Fighting": 1,
        "Psychic": 1, "Ghost": 1, "Dragon": 0.5, "Dark": 1, "Steel": 1, "Fairy": 1,
    },
    "Ice": {
        "Normal": 1, "Grass": 2, "Fire": 0.5, "Water": 0.5, "Electric": 1, "Ice": 0.5,
        "Flying": 2, "Bug": 1, "Poison": 1, "Ground": 2, "Rock": 1, "Fighting": 1,
        "Psychic": 1, "Ghost": 1, "Dragon": 2, "Dark": 1, "Steel": 0.5, "Fairy": 1,
    },
    "Flying": {
        "Normal": 1, "Grass": 2, "Fire": 1, "Water": 1, "Electric": 0.5, "Ice": 1,
        "Flying": 1, "Bug": 2, "Poison": 1, "Ground": 1, "Rock": 0.5, "Fighting": 2,
        "Psychic": 1, "Ghost": 1, "Dragon": 1, "Dark": 1, "Steel": 0.5, "Fairy": 1,
    },
    "Bug": {
        "Normal": 1, "Grass": 2, "Fire": 0.5, "Water": 1, "Electric": 1, "Ice": 1,
        "Flying": 0.5, "Bug": 1, "Poison": 0.5, "Ground": 1, "Rock": 1, "Fighting": 0.5,
        "Psychic": 2, "Ghost": 0.5, "Dragon": 1, "Dark": 2, "Steel": 0.5, "Fairy": 0.5,
    },
    "Poison": {
        "Normal": 1, "Grass": 2, "Fire": 1, "Water": 1, "Electric": 1, "Ice": 1,
        "Flying": 1, "Bug": 1, "Poison": 0.5, "Ground": 0.5, "Rock": 0.5, "Fighting": 1,
        "Psychic": 1, "Ghost": 0.5, "Dragon": 1, "Dark": 1, "Steel": 0, "Fairy": 2,
    },
    "Ground": {
        "Normal": 1, "Grass": 0.5, "Fire": 2, "Water": 1, "Electric": 2, "Ice": 1,
        "Flying": 0, "Bug": 0.5, "Poison": 2, "Ground": 1, "Rock": 2, "Fighting": 1,
        "Psychic": 1, "Ghost": 1, "Dragon": 1, "Dark": 1, "Steel": 2, "Fairy": 1,
    },
    "Rock": {
        "Normal": 1, "Grass": 1, "Fire": 2, "Water": 1, "Electric": 1, "Ice": 2,
        "Flying": 2, "Bug": 2, "Poison": 1, "Ground": 0.5, "Rock": 1, "Fighting": 0.5,
        "Psychic": 1, "Ghost": 1, "Dragon": 1, "Dark": 1, "Steel": 0.5, "Fairy": 1,
    },
    "Fighting": {
        "Normal": 2, "Grass": 1, "Fire": 1, "Water": 1, "Electric": 1, "Ice": 2,
        "Flying": 0.5, "Bug": 0.5, "Poison": 0.5, "Ground": 1, "Rock": 2, "Fighting": 1,
        "Psychic": 0.5, "Ghost": 0, "Dragon": 1, "Dark": 2, "Steel": 2, "Fairy": 0.5,
    },
    "Psychic": {
        "Normal": 1, "Grass": 1, "Fire": 1, "Water": 1, "Electric": 1, "Ice": 1,
        "Flying": 1, "Bug": 1, "Poison": 2, "Ground": 1, "Rock": 1, "Fighting": 2,
        "Psychic": 0.5, "Ghost": 1, "Dragon": 1, "Dark": 0, "Steel": 0.5, "Fairy": 1,
    },
    "Ghost": {
        "Normal": 0, "Grass": 1, "Fire": 1, "Water": 1, "Electric": 1, "Ice": 1,
        "Flying": 1, "Bug": 1, "Poison": 1, "Ground": 1, "Rock": 1, "Fighting": 1,
        "Psychic": 2, "Ghost": 2, "Dragon": 1, "Dark": 0.5, "Steel": 1, "Fairy": 1,
    },
    "Dragon": {
        "Normal": 1, "Grass": 1, "Fire": 1, "Water": 1, "Electric": 1, "Ice": 1,
        "Flying": 1, "Bug": 1, "Poison": 1, "Ground": 1, "Rock": 1, "Fighting": 1,
        "Psychic": 1, "Ghost": 1, "Dragon": 2, "Dark": 1, "Steel": 0.5, "Fairy": 0,
    },
    "Dark": {
        "Normal": 1, "Grass": 1, "Fire": 1, "Water": 1, "Electric": 1, "Ice": 1,
        "Flying": 1, "Bug": 1, "Poison": 1, "Ground": 1, "Rock": 1, "Fighting": 0.5,
        "Psychic": 2, "Ghost": 2, "Dragon": 1, "Dark": 0.5, "Steel": 1, "Fairy": 0.5,
    },
    "Steel": {
        "Normal": 1, "Grass": 1, "Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Ice": 2,
        "Flying": 1, "Bug": 1, "Poison": 1, "Ground": 1, "Rock": 2, "Fighting": 1,
        "Psychic": 1, "Ghost": 1, "Dragon": 1, "Dark": 1, "Steel": 0.5, "Fairy": 2,
    },
    "Fairy": {
        "Normal": 1, "Grass": 1, "Fire": 0.5, "Water": 1, "Electric": 1, "Ice": 1,
        "Flying": 1, "Bug": 1, "Poison": 0.5, "Ground": 1, "Rock": 1, "Fighting": 2,
        "Psychic": 1, "Ghost": 1, "Dragon": 2, "Dark": 2, "Steel": 0.5, "Fairy": 1,
    },
}

# Classic type-absorbing abilities → immunized attack type (wall-check only).
ABILITY_TYPE_IMMUNITY: dict[str, str] = {
    "flashfire": "Fire",
    "waterabsorb": "Water",
    "stormdrain": "Water",
    "dryskin": "Water",
    "voltabsorb": "Electric",
    "lightningrod": "Electric",
    "motordrive": "Electric",
    "levitate": "Ground",
    "eartheater": "Ground",
    "sapsipper": "Grass",
    "wellbakedbody": "Fire",
}


@lru_cache(maxsize=1)
def load_move_accuracy() -> dict[str, dict[str, Any]]:
    if not _ACCURACY_PATH.exists():
        return {}
    return json.loads(_ACCURACY_PATH.read_text())


@lru_cache(maxsize=1)
def load_move_flags() -> dict[str, dict[str, Any]]:
    if not _FLAGS_PATH.exists():
        return {}
    data = json.loads(_FLAGS_PATH.read_text())
    return dict(data.get("moves") or {})


def _move_has_sound_flag(move_id: str) -> bool:
    entry = load_move_flags().get(move_id) or {}
    flags = entry.get("flags") or {}
    return flags.get("sound") == 1


def effective_move_type(
    snap: dict[str, Any],
    move: str,
    *,
    ability: str | None = None,
    species: str | None = None,
    weather: str | None = None,
    terrain: str | None = None,
) -> str | None:
    """Single STAB/display type after Pass 1 rewrites. None if non-damaging.

    Flying Press stays Fighting here; dual-chart lives in ``type_effectiveness``.
    """
    mid = to_id(move)
    meta = snap["moves"].get(mid)
    if not meta or meta.get("category") == "Status":
        return None
    if int(meta.get("basePower") or 0) <= 0:
        return None
    base = meta.get("type")
    if not base:
        return None
    t = str(base)
    aid = to_id(ability or "")
    sid = to_id(species or "")

    if mid == "weatherball":
        if weather and weather in _WEATHER_BALL_TYPES:
            return _WEATHER_BALL_TYPES[weather]
        if aid == "megasol":
            return "Fire"
        return t
    if mid == "terrainpulse" and terrain and terrain in _TERRAIN_PULSE_TYPES:
        return _TERRAIN_PULSE_TYPES[terrain]
    if mid == "aurawheel":
        if sid == "morpekohangry":
            return "Dark"
        if sid.startswith("morpeko"):
            return "Electric"
        return t
    if mid == "ragingbull":
        return _RAGING_BULL_TYPES.get(sid, t)

    no_ate = mid in {"weatherball", "terrainpulse", "struggle"}
    if not no_ate:
        if aid == "liquidvoice" and _move_has_sound_flag(mid):
            return "Water"
        if t == "Normal" and aid in _ATE_ABILITIES:
            return _ATE_ABILITIES[aid]
    return t


def type_effectiveness(
    attack_type: str,
    defend_types: list[str],
    *,
    move_id: str | None = None,
    attacker_ability: str | None = None,
) -> float:
    """TYPE_CHART multiply + Freeze-Dry / Flying Press / Scrappy overrides."""
    mid = to_id(move_id or "")
    aid = to_id(attacker_ability or "")
    scrappy = aid == "scrappy" and attack_type in {"Normal", "Fighting"}

    mult = 1.0
    for t in defend_types:
        if mid == "freezedry" and t == "Water":
            leg = 2.0
        elif scrappy and t == "Ghost":
            leg = 1.0
        else:
            row = TYPE_CHART.get(attack_type) or {}
            leg = float(row.get(t, 1.0))
        if mid == "flyingpress":
            fly_row = TYPE_CHART.get("Flying") or {}
            leg *= float(fly_row.get(t, 1.0))
        mult *= leg
    return mult


def defensive_synergy_score(
    candidate_types: list[str], locked_types_list: list[list[str]]
) -> float:
    """Positive = candidate's weaknesses are generally covered by the
    locked team, and/or the candidate covers weaknesses the locked team
    already has. Negative = candidate compounds shared vulnerabilities.
    Zero if there's no locked team yet.

    Bidirectional, confirmed against real data (Vu's own worked examples
    and a 16-species stress test against known real teammates of
    Archaludon+Pelipper) before being written as production code:

    1. Compounding penalty: for each type the candidate is weak to,
       penalize proportional to (candidate's own weakness severity) x
       (number of locked members who ALSO share that weakness) -- a
       weakness two team members share is a real, concentrated risk
       (lose the one Pokemon that resists it, and both are now exposed),
       not just "someone happens to answer it."
    2. Coverage bonus: for each type the candidate resists/is immune to,
       reward proportional to (how severely the team is already exposed
       via its worst-off locked member) x (how much the candidate
       mitigates it -- 1.0 for immunity, 0.5 for a plain resist).
    3. Severity-scaled baseline penalty: a real weakness costs something
       even with zero team overlap (more exploitable surface area is
       objectively worse), scaled by how severe the weakness is (a 4x
       weakness costs more than a 2x one) -- NOT a flat penalty
       regardless of magnitude, which was a real bug caught and fixed
       during validation (it let a severe 4x weakness `pile up`
       stacking weaknesses without being penalized any more than a mild
       2x one).

    Explicitly bounded, not a complete answer on its own: confirmed via
    the same 16-species validation that this signal alone gets roughly
    60-70% accuracy against real known teammates -- it has no visibility
    into role/utility (a screens setter's value), condition-synergy
    (a Rain-boosted attacker's real offensive upside), or meta-context
    (countering what OTHER teams commonly run). Meant to be one signal
    among several (see team_candidates.py's per-category candidate
    selection), not a dominant or standalone ranking factor.
    """
    if not locked_types_list:
        return 0.0
    score = 0.0
    for attack_type in TYPE_CHART:
        cand_mult = type_effectiveness(attack_type, candidate_types)
        locked_mults = [
            type_effectiveness(attack_type, t) for t in locked_types_list
        ]
        if cand_mult > 1.0:
            shared_weak_count = sum(1 for m in locked_mults if m > 1.0)
            score -= cand_mult * shared_weak_count
            score -= (cand_mult - 1.0) * 0.5
        if cand_mult < 1.0:
            worst_locked = max(locked_mults) if locked_mults else 1.0
            if worst_locked > 1.0:
                mitigation = 1.0 - cand_mult
                score += worst_locked * mitigation
    return score


def _species_types(snap: dict[str, Any], species: str) -> list[str]:
    entry = snap["species"].get(to_id(species))
    if not entry:
        return []
    return list(entry.get("types") or [])


def _species_name(snap: dict[str, Any], species: str) -> str:
    entry = snap["species"].get(to_id(species))
    if entry and entry.get("name"):
        return str(entry["name"])
    return species


def _legality_ability(snap: dict[str, Any], species: str) -> str | None:
    entry = snap["species"].get(to_id(species))
    if not entry:
        return None
    abilities = entry.get("abilities") or {}
    raw = abilities.get("0") or abilities.get(0)
    return str(raw) if raw else None


def _damaging_move_types(
    snap: dict[str, Any],
    moves: list[str] | None,
    *,
    ability: str | None = None,
    species: str | None = None,
) -> list[str]:
    if not moves:
        return []
    out: list[str] = []
    for mv in moves:
        t = effective_move_type(snap, mv, ability=ability, species=species)
        if t:
            out.append(t)
    return out


def _anchor_attack_types(
    snap: dict[str, Any], pokemon: PokemonSpecOptional, anchor_types: list[str]
) -> list[str]:
    """Damaging move types, or STAB types if none (avoids vacuous wall)."""
    typed = _damaging_move_types(
        snap,
        pokemon.get("moves"),
        ability=pokemon.get("ability"),
        species=pokemon.get("species"),
    )
    return typed if typed else list(anchor_types)


def _incoming_effectiveness(
    attack_type: str,
    defend_types: list[str],
    ability: str | None,
    *,
    move_id: str | None = None,
    attacker_ability: str | None = None,
) -> float:
    aid = to_id(ability or "")
    immune_to = ABILITY_TYPE_IMMUNITY.get(aid)
    if immune_to and immune_to == attack_type:
        return 0.0
    return type_effectiveness(
        attack_type,
        defend_types,
        move_id=move_id,
        attacker_ability=attacker_ability,
    )


def _walls(
    attack_types: list[str],
    cand_types: list[str],
    ability: str | None,
    *,
    attacker_ability: str | None = None,
) -> bool:
    if not attack_types:
        return False  # should not happen after STAB fallback
    return all(
        _incoming_effectiveness(
            t, cand_types, ability, attacker_ability=attacker_ability
        )
        <= 0.5
        for t in attack_types
    )


def _move_base_accuracy(move_id: str) -> int | bool | None:
    entry = load_move_accuracy().get(move_id)
    if not entry:
        return None
    return entry.get("accuracy")


def _scaled_base_power(move_id: str, snapshot_bp: int) -> int:
    """Apply battle-state BP assumptions for Last Respects / Rage Fist."""
    if move_id == "lastrespects":
        # Assumption A: BP = 50 × (1 + fainted allies).
        return 50 * (1 + ASSUMED_FAINTED_TEAMMATES)
    if move_id == "ragefist":
        # Assumption B: BP = 50 × (1 + hits taken) — not fainted allies.
        return 50 * (1 + ASSUMED_HITS_TAKEN)
    return snapshot_bp


def _ko_best_move(
    snap: dict[str, Any],
    *,
    moves: list[str],
    cand_types: list[str],
    anchor_types: list[str],
    ability: str | None,
    species: str | None = None,
) -> tuple[float, bool]:
    """Return (best effective_bp, best_was_stab)."""
    best_bp = 0.0
    best_stab = False
    aid = to_id(ability or "")
    so_mult = (
        1.0 + 0.1 * ASSUMED_FAINTED_TEAMMATES
        if aid == "supremeoverlord"
        else 1.0
    )
    for mv in moves:
        mid = to_id(mv)
        meta = snap["moves"].get(mid)
        if not meta or meta.get("category") == "Status":
            continue
        bp = _scaled_base_power(mid, int(meta.get("basePower") or 0))
        at_s = effective_move_type(snap, mv, ability=ability, species=species)
        if bp <= 0 or not at_s:
            continue
        stab = at_s in cand_types
        type_mult = type_effectiveness(
            at_s, anchor_types, move_id=mid, attacker_ability=ability
        )
        acc = effective_accuracy(_move_base_accuracy(mid), ability)
        hits, folded = expected_hit_factor(mid, ability, acc)
        ebp = bp * type_mult * (1.5 if stab else 1.0) * hits * so_mult
        if not folded:
            ebp *= acc
        if ebp > best_bp:
            best_bp = ebp
            best_stab = stab
    return best_bp, best_stab


def threat_tier(kinds: frozenset[str]) -> int:
    """Axis-count tier: both axes → 0, one → 1."""
    n = len(kinds & {"ko_threshold", "wall"})
    return max(0, 2 - n)


def query_counters(
    pokemon: PokemonSpecOptional,
    n: int = 20,
    candidate_pool: list[PokemonSpecOptional] | None = None,
    *,
    available_pool: list[str] | None = None,
    ownership_mode: OwnershipMode = "off",
) -> list[ThreatCandidate]:
    """Cheap data-only threats for ``pokemon`` (ADR-022 stage-1, cap ``n``).

    ``candidate_pool`` restricts which species are searched as threats.
    ``None`` = full legal set (unchanged default); non-None (incl. ``[]``) = only
    those ids. ``available_pool`` is a species-level boolean signal: duplicate
    ids do not add weight. ``owned_only`` intersects it with ``candidate_pool``.
    """
    species = pokemon.get("species")
    if not species:
        return []

    snap = load_snapshot()
    if not is_species_legal(snap, species):
        return []

    anchor_id = to_id(species)
    anchor_types = _species_types(snap, species)
    if not anchor_types:
        return []

    allowed: set[str] | None = None
    if candidate_pool is not None:
        allowed = {
            to_id(p["species"]) for p in candidate_pool if p.get("species")
        }
    owned = {sid for species in available_pool or [] if (sid := to_id(species))}
    if ownership_mode == "owned_only":
        allowed = owned if allowed is None else allowed & owned

    attack_types = _anchor_attack_types(snap, pokemon, anchor_types)
    ig = ingame_species_map(DEFAULT_REGULATION)
    pool: list[ThreatCandidate] = []

    for sid, entry in snap["species"].items():
        if sid == anchor_id or not is_species_legal(snap, sid):
            continue
        if allowed is not None and sid not in allowed:
            continue

        cand_types = list(entry.get("types") or [])
        if not cand_types:
            continue

        usage_set = featured_or_common_set(sid, regulation=DEFAULT_REGULATION)
        ability = None
        if usage_set and usage_set.get("ability"):
            ability = str(usage_set["ability"])
        else:
            ability = _legality_ability(snap, sid)

        kinds: set[str] = set()
        ko_score = 0.0
        ko_stab = False

        if usage_set and usage_set.get("moves"):
            best_bp, ko_stab = _ko_best_move(
                snap,
                moves=list(usage_set["moves"]),
                cand_types=cand_types,
                anchor_types=anchor_types,
                ability=ability,
                species=sid,
            )
            ko_score = min(1.0, best_bp / KO_THRESHOLD_BP) if KO_THRESHOLD_BP else 0.0
            if ko_score >= 1.0:
                kinds.add("ko_threshold")

        if _walls(
            attack_types,
            cand_types,
            ability,
            attacker_ability=pokemon.get("ability"),
        ):
            kinds.add("wall")

        if not kinds:
            continue

        ig_entry = ig.get(sid) or {}
        rank = ig_entry.get("usage_rank")
        rank_i = int(rank) if rank is not None else None
        name = str(ig_entry.get("name") or entry.get("name") or sid)

        spec: PokemonSpecOptional = {"species": name}
        if usage_set:
            if usage_set.get("ability"):
                spec["ability"] = str(usage_set["ability"])
            if usage_set.get("item"):
                spec["item"] = str(usage_set["item"])
            if usage_set.get("moves"):
                spec["moves"] = list(usage_set["moves"])
            if usage_set.get("nature"):
                spec["nature"] = str(usage_set["nature"])
            if usage_set.get("evs"):
                spec["evs"] = dict(usage_set["evs"])  # type: ignore[typeddict-item]

        pool.append(
            ThreatCandidate(
                ladder_species=name,
                usage_rank=rank_i,
                form=name,
                showdown_usage_pct=None,
                showdown_formes=(),
                spec=spec,
                build_source="ingame",
                threat_kinds=frozenset(kinds),
                ko_threshold_score=ko_score,
                ko_best_was_stab=ko_stab if "ko_threshold" in kinds else False,
            )
        )

    def _key(c: ThreatCandidate) -> tuple[float, float]:
        # Within-tier: popularity primary so wall-only are not starved by capped
        # KO scores (=1.0); ko_threshold_score is tiebreak.
        pop = (
            -float(c.usage_rank)
            if c.usage_rank is not None
            else float("-inf")
        )
        return (pop, c.ko_threshold_score)

    return rank_and_cut(
        pool,
        key=_key,
        n=n,
        tier=lambda c: threat_tier(c.threat_kinds),
        slack=QUERY_COUNTERS_SLACK,
        order="descending",
        ownership_mode=ownership_mode,
        is_owned=lambda c: to_id(c.spec.get("species") or c.form) in owned,
    )
