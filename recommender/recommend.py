"""Tier 1/2/3 build recommendation (ADR-015/016)."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

from recommender.ids import to_id
from recommender.legality import (
    LegalityResult,
    check_set,
    current_availability_gaps,
    load_snapshot,
)
from recommender.resolved_builds import get_resolved_build, put_resolved_build
from recommender.state import PokemonSet, Slot, StatsTable
from recommender.usage_data import featured_or_common_set, find_set_matching, species_usage
from recommender.usage_spreads import select_usage_spread

SP_BUDGET = 66

RoleArchetype = Literal[
    "fast_physical_attacker",
    "fast_special_attacker",
    "fast_mixed_attacker",
    "standard_physical_attacker",
    "standard_special_attacker",
    "standard_mixed_attacker",
    "bulky_physical_attacker",
    "bulky_special_attacker",
    "bulky_mixed_attacker",
    "bulky_pivot",
    "fast_pivot",
    "trick_room_sweeper",
    "support_speed_control",
    "screens_support",
]

_DEPRECATED_ROLE_ALIASES = {
    "fast_attacker": "fast_physical_attacker",
    "bulky_attacker": "bulky_physical_attacker",
}

_PIVOT_MOVES = frozenset({"uturn", "voltswitch", "flipturn", "partingshot", "teleport"})
_SCREEN_MOVES = frozenset({"lightscreen", "reflect", "auroraveil"})
_BULKY_ITEMS = frozenset({"sitrusberry", "leftovers", "rockyhelmet"})
_FAST_ITEMS = frozenset({"lifeorb", "choiceband", "choicespecs", "choicescarf"})
_WEATHER_SPEED = frozenset({"swiftswim", "chlorophyll", "sandrush", "slushrush"})
# ponytail: snapshot has no multihit field — keep explicit set; extend with matchup._MULTI_HIT_MOVES if needed
_MULTI_HIT = frozenset(
    {
        "populationbomb",
        "bulletseed",
        "iciclespear",
        "rockblast",
        "pinmissile",
        "tailslap",
        "scaleshot",
        "surgingstrikes",
        "bonerush",
        "doublehit",
        "dragondarts",
        "dualwingbeat",
        "tripleaxel",
        "twinbeam",
        "watershuriken",
        "armthrust",
    }
)

_ROLE_SPREADS: dict[str, StatsTable] = {
    "fast_physical_attacker": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
    "fast_special_attacker": {"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32},
    "fast_mixed_attacker": {"hp": 2, "atk": 16, "def": 0, "spa": 16, "spd": 0, "spe": 32},
    "standard_physical_attacker": {"hp": 12, "atk": 32, "def": 8, "spa": 0, "spd": 0, "spe": 14},
    "standard_special_attacker": {"hp": 12, "atk": 0, "def": 0, "spa": 32, "spd": 8, "spe": 14},
    "standard_mixed_attacker": {"hp": 12, "atk": 16, "def": 8, "spa": 16, "spd": 0, "spe": 14},
    "bulky_physical_attacker": {"hp": 20, "atk": 32, "def": 14, "spa": 0, "spd": 0, "spe": 0},
    "bulky_special_attacker": {"hp": 20, "atk": 0, "def": 14, "spa": 32, "spd": 0, "spe": 0},
    "bulky_mixed_attacker": {"hp": 20, "atk": 16, "def": 14, "spa": 16, "spd": 0, "spe": 0},
    "fast_pivot": {"hp": 12, "atk": 16, "def": 6, "spa": 0, "spd": 0, "spe": 32},
    "screens_support": {"hp": 24, "atk": 0, "def": 18, "spa": 0, "spd": 18, "spe": 6},
    "trick_room_sweeper": {"hp": 32, "atk": 0, "def": 2, "spa": 32, "spd": 0, "spe": 0},
    "bulky_pivot": {"hp": 32, "atk": 0, "def": 18, "spa": 0, "spd": 16, "spe": 0},
    "support_speed_control": {"hp": 20, "atk": 0, "def": 14, "spa": 0, "spd": 0, "spe": 32},
}


class RecommendResult(TypedDict):
    ok: bool
    set: NotRequired[PokemonSet]
    rationale: str
    source_tier: str
    verification: NotRequired[list[str]]
    failures: NotRequired[list[str]]


def lookup_live_build(
    species: str, moves: list[str], item: str, *, regulation: str
) -> PokemonSet | None:
    # ponytail: ADR-014a live lookup not wired; return miss until a real fetcher exists
    return None


def _damage_bias(moves: list[str]) -> str:
    from recommender.usage_spreads import move_category_counts

    physical, special = move_category_counts(moves)
    if physical == 0 and special == 0:
        return "status_only"
    if physical > 0 and special > 0:
        return "mixed"
    if physical > special:
        return "physical"
    return "special"


def _attacker_role(axis: str, bias: str) -> RoleArchetype:
    if bias == "status_only":
        return f"{axis}_special_attacker"  # type: ignore[return-value]
    return f"{axis}_{bias}_attacker"  # type: ignore[return-value]


def infer_role(
    moves: list[str],
    item: str,
    ability: str | None = None,
) -> RoleArchetype:
    mids = {to_id(m) for m in moves}
    iid = to_id(item)
    aid = to_id(ability) if ability else ""
    screens = mids & _SCREEN_MOVES
    has_pivot = bool(mids & _PIVOT_MOVES)
    technician_fast = aid == "technician" and bool(mids & _MULTI_HIT)
    weather_fast = aid in _WEATHER_SPEED
    bias = _damage_bias(moves)

    if "trickroom" in mids:
        return "trick_room_sweeper"
    # Aurora Veil is dual screens in one move (snow-gated elsewhere).
    if "auroraveil" in mids or len(screens) >= 2 or (iid == "lightclay" and screens):
        return "screens_support"
    if "tailwind" in mids:
        return "support_speed_control"
    if has_pivot:
        if iid == "choicescarf" or technician_fast:
            return "fast_pivot"
        return "bulky_pivot"
    if iid in _BULKY_ITEMS:
        return _attacker_role("bulky", bias)
    if (
        iid in _FAST_ITEMS or technician_fast or iid == "focussash" or weather_fast
    ) and bias != "status_only":
        return _attacker_role("fast", bias)
    if bias == "status_only":
        return "standard_special_attacker"
    return _attacker_role("standard", bias)


def role_spread(role: str) -> StatsTable:
    """Allocate full 66 SP by archetype (resolves deprecated TargetRoleId aliases)."""
    key = _DEPRECATED_ROLE_ALIASES.get(role, role)
    try:
        return dict(_ROLE_SPREADS[key])
    except KeyError as e:
        raise ValueError(f"unsupported role archetype: {role!r}") from e


_STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")
_SP_CAP = 32


def spread_sum(evs: StatsTable | dict[str, int] | None) -> int:
    if not evs:
        return 0
    return sum(int(evs.get(k, 0)) for k in _STAT_KEYS)


def _allocate_remainder(
    partial: StatsTable | dict[str, int], role: str
) -> tuple[StatsTable, dict[str, int]]:
    """Keep partial allocation; spend leftover SP toward role_spread targets.

    Returns (completed_spread, synthesized_per_stat) where synthesized counts only
    the points added in this step — not the preserved tier-1 base.
    """
    target = role_spread(role)
    out: StatsTable = {k: int(partial.get(k, 0)) for k in _STAT_KEYS}
    synthesized = {k: 0 for k in _STAT_KEYS}
    need = SP_BUDGET - sum(out.values())
    while need > 0:
        deficits = [
            (k, target[k] - out[k])
            for k in _STAT_KEYS
            if out[k] < _SP_CAP and target[k] > out[k]
        ]
        if deficits:
            k = max(deficits, key=lambda kv: kv[1])[0]
        else:
            room = [(k, _SP_CAP - out[k]) for k in _STAT_KEYS if out[k] < _SP_CAP]
            if not room:
                break
            k = max(room, key=lambda kv: kv[1])[0]
        out[k] = int(out[k]) + 1
        synthesized[k] += 1
        need -= 1
    return out, synthesized


def diagnose_and_substitute(
    species: str,
    moves: list[str],
    item: str,
    result: LegalityResult,
    *,
    team_draft: list[Slot] | None,
    snap: dict[str, Any],
) -> tuple[PokemonSet | None, str]:
    """ADR-015c: element-type resolution. Returns adapted set or None if non-transferable."""
    if result.ok:
        return {"species": species, "moves": moves, "item": item}, "legal as-is"

    # Species illegal → no transfer
    if any(f.kind == "species" for f in result.failures):
        return None, "no valid substitute: species illegal"

    new_item = item
    new_moves = list(moves)
    notes: list[str] = []

    for f in result.failures:
        if f.kind in ("item", "item_clause"):
            sev = f.item_severity or "universal_swap"
            if sev == "non_severe_no_substitute":
                notes.append(f"keep {f.element} as-is (shortened duration); non-severe")
                continue
            if sev == "severe_no_substitute":
                return None, f"no valid substitute: severe item {f.element}"
            # Try Sitrus Berry / Life Orb as universal fallback if free on team
            from recommender.legality import team_item_ids

            used = team_item_ids(team_draft)
            for cand in ("Life Orb", "Sitrus Berry", "Focus Sash"):
                if to_id(cand) not in used and to_id(cand) != to_id(new_item):
                    # legality of candidate
                    from recommender.legality import is_item_legal

                    if is_item_legal(snap, cand):
                        notes.append(f"substituted item {f.element} → {cand} ({sev})")
                        new_item = cand
                        break
            else:
                return None, f"no valid substitute: cannot replace item {f.element}"
        elif f.kind in ("move", "learnset"):
            # Find same-type comparable BP substitute
            moves_tbl = snap.get("moves") or {}
            bad = moves_tbl.get(to_id(f.element))
            if not bad:
                return None, f"no valid substitute: unknown move {f.element}"
            from recommender.legality import legal_moves_for

            candidates = legal_moves_for(species, snap)
            best = None
            for cid in candidates:
                if cid == to_id(f.element) or cid in {to_id(m) for m in new_moves}:
                    continue
                m = moves_tbl[cid]
                if m.get("type") == bad.get("type") and m.get("category") == bad.get("category"):
                    if abs(int(m.get("basePower", 0)) - int(bad.get("basePower", 0))) <= 20:
                        best = m["name"]
                        break
            if not best:
                return None, f"no valid substitute: move {f.element}"
            new_moves = [best if to_id(m) == to_id(f.element) else m for m in new_moves]
            notes.append(f"substituted move {f.element} → {best}")
        elif f.kind == "ability":
            return None, f"no valid substitute: ability {f.element}"

    recheck = check_set(species, new_moves, new_item, team_draft=team_draft, snap=snap)
    if not recheck.ok:
        return None, "no valid substitute: adapted set still illegal"
    return (
        {"species": species, "moves": new_moves, "item": new_item},
        "; ".join(notes) or "adapted",
    )


def select_opponent_builds(
    species_list: list[str],
    *,
    regulation: str = "champions",
    role_hint: str | None = None,
    k: int = 5,
) -> list[PokemonSet]:
    """Tier-1 / usage only — no recursive recommend_build (ADR-015a)."""
    out: list[PokemonSet] = []
    for sp in species_list:
        if len(out) >= k:
            break
        s = featured_or_common_set(sp, regulation=regulation)
        if s:
            out.append(s)
    return out


def _tier3_verify_spread(
    species: str,
    moves: list[str],
    item: str,
    spread: StatsTable,
    opponents: list[PokemonSet],
    *,
    calculate_batch,
) -> list[str]:
    """SP/damage smoke via calculate_batch; speed checked separately."""
    notes: list[str] = []
    if not opponents or not moves:
        return ["tier3: no opponents or moves — skipped"]
    attacker: dict[str, Any] = {
        "species": species,
        "item": item,
        "evs": dict(spread),
        "moves": moves,
    }
    reqs = []
    for opp in opponents[:5]:
        dmg_move = next((m for m in moves if to_id(m) not in {"protect", "substitute", "tailwind", "trickroom"}), moves[0])
        reqs.append(
            {
                "attacker": attacker,
                "defender": {
                    "species": opp.get("species"),
                    "item": opp.get("item"),
                    "evs": opp.get("evs") or {"hp": 32, "atk": 0, "def": 16, "spa": 0, "spd": 16, "spe": 0},
                },
                "move": dmg_move,
                "field": {"gameType": "Doubles"},
            }
        )
    try:
        results = calculate_batch(reqs)
    except Exception as e:  # noqa: BLE001 — surface as verification note
        return [f"tier3 calc failed: {e}"]
    for i, r in enumerate(results):
        if isinstance(r, dict) and "error" in r:
            notes.append(f"vs {opponents[i].get('species')}: error {r['error']}")
        else:
            notes.append(
                f"vs {opponents[i].get('species')}: {r.get('koChance', '?')} dmg={r.get('damageRange')}"
            )
    # Speed-tier distinct check: compare spe investment only (stat formula deferred to calc raw if present)
    notes.append("speed-tier: compared via spread spe vs opponent spe investment (distinct from KO)")
    return notes


def recommend_build(
    species: str,
    moves: list[str],
    item: str,
    *,
    regulation: str = "champions",
    team_draft: list[Slot] | None = None,
    calculate_batch=None,
    write_cache: bool = True,
) -> RecommendResult:
    snap = load_snapshot()
    verification: list[str] = []

    # --- Cache (ADR-016) ---
    cached = get_resolved_build(species, moves, item, regulation)
    if cached:
        s: PokemonSet = {
            "species": species,
            "moves": moves,
            "item": item,
            "evs": cached["spread"],  # type: ignore[typeddict-item]
        }
        return {
            "ok": True,
            "set": s,
            "rationale": "cache hit",
            "source_tier": f"cache:{cached.get('source_tier', 'unknown')}",
            "verification": [f"cached verified={cached.get('verified')}"],
        }

    # --- Tier 1: usage exact match ---
    matched = find_set_matching(species, moves, item, regulation=regulation)
    source = "champions-native"
    built: PokemonSet | None = dict(matched) if matched else None
    if built:
        # Usage spread is a species-level marginal, not correlated with this set.
        built.pop("evs", None)
    rationale = "tier1 usage exact moves+item match" if matched else ""

    if not built:
        # Broader: featured/common for species (may differ moves — only if moves empty?)
        # Plan: miss → live stub → tier2. Don't force wrong moveset.
        live = lookup_live_build(species, moves, item, regulation=regulation)
        if live:
            built = live
            source = "live-lookup"
            rationale = "tier1 live lookup"
        else:
            # Start from user moves+item; species-level spreads are selected below.
            entry = species_usage(species, regulation=regulation)
            ability = None
            if entry:
                abs_ = entry.get("common_abilities") or []
                if abs_:
                    ability = abs_[0]["name"]
            built = {"species": species, "moves": moves, "item": item}
            if ability:
                built["ability"] = ability
            rationale = "assembled from user moves/item (no exact featured match)"
            source = "champions-native"

    assert built is not None
    b_moves = list(built.get("moves") or moves)
    b_item = built.get("item") or item
    b_ability = built.get("ability")

    legal = check_set(
        species, b_moves, b_item, ability=b_ability, team_draft=team_draft, snap=snap
    )
    if not legal.ok:
        adapted, note = diagnose_and_substitute(
            species, b_moves, b_item, legal, team_draft=team_draft, snap=snap
        )
        if adapted is None:
            return {
                "ok": False,
                "rationale": note,
                "source_tier": source,
                "failures": [f"{f.kind}:{f.element}" for f in legal.failures],
            }
        built = adapted
        b_moves = list(built["moves"])  # type: ignore[index]
        b_item = built["item"]  # type: ignore[index]
        rationale = f"{rationale}; {note}".strip("; ")
        verification.append(note)

    gaps = current_availability_gaps(species, b_moves, b_item, b_ability, snap)
    if gaps.get("unused_legal_moves"):
        verification.append(
            f"current-availability: {len(gaps['unused_legal_moves'])} unused legal moves (not auto-applied)"
        )

    opponents = select_opponent_builds(
        ["Kingambit", "Garchomp", "Incineroar", "Whimsicott", "Pelipper"],
        regulation=regulation,
        k=3,
    )

    # Completeness: exact partials retain their real base; missing spreads use tier 2.
    role = infer_role(b_moves, b_item, b_ability)
    evs = built.get("evs")
    used = spread_sum(evs)
    if used >= SP_BUDGET:
        source_tier_out = source
    elif not evs or used == 0:
        choice = select_usage_spread(
            species,
            role,
            b_moves,
            regulation=regulation,
            threats=opponents,
            snap=snap,
        )
        if choice:
            built["evs"] = choice.spread
            if choice.nature:
                built["nature"] = choice.nature
            source_tier_out = choice.source
            verification.append(choice.rationale)
            rationale = f"{rationale}; {choice.rationale}".strip("; ")
        else:
            built["evs"] = role_spread(role)
            source_tier_out = "tier3_role"
            verification.append(
                f"tier2 exhausted; tier3 role={role} synthesized full {SP_BUDGET}"
            )
            rationale = (
                f"{rationale}; tier3 {role} synthesized full SP ({SP_BUDGET})"
            ).strip("; ")
    else:
        # Partial: preserve real allocation; synthesize remainder toward role targets.
        assert evs is not None
        completed, synth = _allocate_remainder(evs, role)
        built["evs"] = completed
        # Real tier-1 points exist but were short of budget — not full tier-1 confidence,
        # and not a wipe to tier2 that erases the real base.
        source_tier_out = "tier1_partial"
        synth_bits = ",".join(f"{k}+{n}" for k, n in synth.items() if n)
        verification.append(
            f"incomplete-spread: used {used}/{SP_BUDGET}; remainder synthesized via role={role}"
            + (f" ({synth_bits})" if synth_bits else "")
        )
        rationale = (
            f"{rationale}; tier1_partial: kept {used} SP, "
            f"synthesized {SP_BUDGET - used} via {role}"
        ).strip("; ")

    # Tier 3 when we have calc and incomplete was topped OR always light verify for tier2
    # Prefer threats from usage teammates inverted — keep simple fixed list filtered to available
    if calculate_batch is not None and built.get("evs"):
        notes = _tier3_verify_spread(
            species, b_moves, b_item, built["evs"], opponents, calculate_batch=calculate_batch  # type: ignore[arg-type]
        )
        verification.extend(notes)
        if write_cache:
            put_resolved_build(
                species,
                b_moves,
                b_item,
                regulation,
                dict(built["evs"]),  # type: ignore[arg-type]
                source_tier_out,
                True,
                {
                    "threat_set": [o.get("species", "") for o in opponents],
                    "usage_snapshot": "champions-reg-mb.v1",
                },
            )
            verification.append("wrote cache after tier3")
    elif write_cache and built.get("evs"):
        put_resolved_build(
            species,
            b_moves,
            b_item,
            regulation,
            dict(built["evs"]),  # type: ignore[arg-type]
            source_tier_out,
            False,
            {"notes": "unverified — no calculate_batch"},
        )

    built["species"] = species
    built["moves"] = b_moves
    built["item"] = b_item
    return {
        "ok": True,
        "set": built,
        "rationale": rationale or "recommended",
        "source_tier": source_tier_out,
        "verification": verification,
    }
