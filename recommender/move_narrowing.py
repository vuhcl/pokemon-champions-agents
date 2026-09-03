"""Move-candidate narrowing + moveset redundancy validation (ADR-015 27f / ADR-021)."""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from typing import Any, Literal

from recommender.calc_client import CalcClient, PokemonSpecOptional
from recommender.contingent_value import REDIRECT_MOVES, WEATHER_SETTERS
from recommender.coverage import ABILITY_TO_FIELD, get_relevant_threats
from recommender.ids import to_id
from recommender.legality import (
    is_species_legal,
    load_snapshot,
    resolve_learnset,
    species_can_have_ability,
)
from recommender.matchup import _CHARGE_INSTANT_WEATHER, _makes_contact
from recommender.ranking import OwnershipMode, rank_and_cut
from recommender.state import RecommenderState, Slot
from recommender.usage_data import ingame_species_map, showdown_species_map, species_usage

SMALL_POOL = 8
BACKSTOP_CEILING = 20
MIN_USAGE_PCT = 1.0
NEAR_TIE_PCT = 5.0

Delivery = Literal["prankster", "natural_speed"]

# Champions / Gen9 priorities — snapshot has no priority field.
_PRIORITY_OVERRIDES: dict[str, int] = {
    "followme": 2,
    "ragepowder": 2,
    "trickroom": -7,
    "protect": 4,
    "detect": 4,
    "helpinghand": 5,
    "fakeout": 3,
    "encore": 0,
    "willowisp": 0,
    "tailwind": 0,
}

_WEATHER_MANUAL: dict[str, str] = {
    "raindance": "Rain",
    "sunnyday": "Sun",
    "sandstorm": "Sand",
    "snowscape": "Snow",
    "chillyreception": "Snow",
}
WEATHER_SETTING_MOVES = _WEATHER_MANUAL
_HARD_REQUIRE_WEATHER: dict[str, str] = {
    "auroraveil": "Snow",
}
_SPEED_CONTROL = frozenset({"tailwind", "trickroom"})
_COMPONENT_TO_ROLE: dict[str, str] = {
    "TrickRoom": "trick_room_sweeper",
    "Tailwind": "support_speed_control",
}
_SHARED_PHYSICAL = [
    "playrough",
    "woodhammer",
    "shadowclaw",
    "shadowsneak",
    "drainpunch",
    "closecombat",
    "earthquake",
    "ironhead",
    "aquajet",
    "icespinner",
]
_SHARED_SPECIAL = [
    "dazzlinggleam",
    "moonblast",
    "psychic",
    "mysticalfire",
    "gigadrain",
    "shadowball",
    "heatwave",
    "hydropump",
    "thunderbolt",
    "makeitrain",
]
_PIVOT_PREF = ["uturn", "voltswitch", "flipturn", "partingshot", "teleport"]
_ROLE_PREF_MOVES: dict[str, list[str]] = {
    "support_speed_control": ["tailwind", "trickroom"],
    "trick_room_sweeper": ["trickroom"],
    "trick_room_setter": ["trickroom", *_SHARED_SPECIAL],
    "tailwind_setter": ["tailwind", *_SHARED_SPECIAL],
    # Mechanism only — honest short (same class as weather / trick_room_sweeper).
    "redirection": ["followme", "ragepowder"],
    "swords_dance_attacker": ["swordsdance", *_SHARED_PHYSICAL],
    "nasty_plot_attacker": ["nastyplot", *_SHARED_SPECIAL],
    "fast_attacker": [*_SHARED_PHYSICAL, *_SHARED_SPECIAL],
    "bulky_attacker": [*_SHARED_PHYSICAL, *_SHARED_SPECIAL],
    "fast_physical_attacker": list(_SHARED_PHYSICAL),
    "standard_physical_attacker": list(_SHARED_PHYSICAL),
    "bulky_physical_attacker": list(_SHARED_PHYSICAL),
    "fast_special_attacker": list(_SHARED_SPECIAL),
    "standard_special_attacker": list(_SHARED_SPECIAL),
    "bulky_special_attacker": list(_SHARED_SPECIAL),
    "fast_mixed_attacker": [*_SHARED_PHYSICAL, *_SHARED_SPECIAL],
    "standard_mixed_attacker": [*_SHARED_PHYSICAL, *_SHARED_SPECIAL],
    "bulky_mixed_attacker": [*_SHARED_PHYSICAL, *_SHARED_SPECIAL],
    "bulky_pivot": [*_PIVOT_PREF, *_SHARED_PHYSICAL, *_SHARED_SPECIAL],
    "fast_pivot": [*_PIVOT_PREF, *_SHARED_PHYSICAL, *_SHARED_SPECIAL],
    "screens_support": [
        "lightscreen",
        "reflect",
        "auroraveil",
        *_SHARED_SPECIAL,
    ],
    "rain_setter": ["raindance"],
    "sun_setter": ["sunnyday"],
    "sand_setter": ["sandstorm"],
    "snow_setter": ["snowscape", "chillyreception"],
}
_ARCHETYPE_PREF_MOVES: dict[str, list[str]] = {
    "Rain": ["raindance"],
    "Sun": ["sunnyday"],
    "Sand": ["sandstorm"],
    "Snow": ["snowscape", "chillyreception"],
    "TrickRoom": ["trickroom"],
    "Tailwind": ["tailwind"],
}

KitInteractionProposer = Callable[[dict[str, Any], str], list["ProposedInteraction"]]


@dataclass
class ProposedInteraction:
    kind: str  # ability | move_flag | judgment
    claim: str
    ability: str | None = None
    flag: str | None = None  # contact | charge_weather
    quantitative: bool = False


@dataclass
class CandidateMeta:
    species: str
    delivery: Delivery
    commitment_pct: float | None
    usage_pct: float | None
    verified_reinforcements: int = 0


@dataclass
class NarrowResult:
    candidates: list[str]
    stopped_at: int
    delivery: dict[str, Delivery] = field(default_factory=dict)
    candidate_meta: dict[str, CandidateMeta] = field(default_factory=dict)
    verified_reinforcements: dict[str, int] = field(default_factory=dict)
    backstop_applied: bool = False
    grouping_skipped: bool = False


@dataclass
class RedundancyResult:
    ok: bool
    seeming: bool
    justified: bool
    pattern: str | None = None  # A-precondition | A-team | B | None
    drop_moves: list[str] = field(default_factory=list)


def move_priority(move: str) -> int:
    mid = to_id(move)
    if mid in _PRIORITY_OVERRIDES:
        return _PRIORITY_OVERRIDES[mid]
    return 0


def learners_of(move: str, *, snap: dict[str, Any] | None = None) -> list[str]:
    snap = snap or load_snapshot()
    mid = to_id(move)
    out: list[str] = []
    for sid, entry in (snap.get("species") or {}).items():
        if not is_species_legal(snap, sid):
            continue
        ls = resolve_learnset(snap, sid)
        if ls is None or mid not in ls:
            continue
        name = entry.get("name") or sid
        out.append(name)
    return out


def _has_prankster(snap: dict[str, Any], species: str) -> bool:
    e = (snap.get("species") or {}).get(to_id(species)) or {}
    return any(
        isinstance(v, str) and to_id(v) == "prankster"
        for v in (e.get("abilities") or {}).values()
    )


def _commitment_pct(species: str, move: str, *, regulation: str) -> float | None:
    sid = to_id(species)
    mid = to_id(move)
    ingame = ingame_species_map(regulation).get(sid)
    for source in (ingame, showdown_species_map(regulation).get(sid)):
        if not source:
            continue
        for row in source.get("common_moves") or []:
            if to_id(row.get("name") or "") == mid:
                pct = row.get("pct")
                return float(pct) if pct is not None else None
    return None


def move_appears_in_usage(species: str, move: str, *, regulation: str) -> bool:
    """True if the move is in top-10 common_moves or pct >= MIN_USAGE_PCT.

    Checks ingame then Showdown independently (OR). Unlike _commitment_pct,
    rank and threshold both count — a #11 move at 5% still qualifies.
    """
    sid = to_id(species)
    mid = to_id(move)
    for source in (
        ingame_species_map(regulation).get(sid),
        showdown_species_map(regulation).get(sid),
    ):
        if not source:
            continue
        for i, row in enumerate(source.get("common_moves") or []):
            if to_id(row.get("name") or "") != mid:
                continue
            if i < 10:
                return True
            pct = row.get("pct")
            if pct is not None and float(pct) >= MIN_USAGE_PCT:
                return True
    return False


def _ladder_usage_pct(species: str, *, regulation: str) -> float | None:
    entry = species_usage(species, regulation=regulation)
    if not entry:
        return None
    pct = entry.get("usage_pct")
    return float(pct) if pct is not None else None


def team_need_flags(state: RecommenderState) -> set[str]:
    """Unmet need tags: weather | redirection | speed_control | coverage_gap."""
    flags: set[str] = set()
    draft = list(state.get("team_draft") or [])
    present_roles = {s.role.value for s in draft if s.role.value}
    arch = state.get("archetype")
    components = list(getattr(arch, "value", None) or [])

    for c in components:
        role = _COMPONENT_TO_ROLE.get(c)
        if role and role not in present_roles and c in ("TrickRoom", "Tailwind"):
            flags.add("speed_control")
        if c in ("Rain", "Sun", "Sand", "Snow"):
            flags.add("weather")

    coverage = state.get("coverage") or []
    spofs = state.get("spofs") or []
    if any(not getattr(r, "covering_slot_indices", True) for r in coverage) or spofs:
        flags.add("coverage_gap")

    locked_moves: set[str] = set()
    for s in draft:
        if s.moveset.value:
            locked_moves.update(to_id(m) for m in s.moveset.value)
    if not (REDIRECT_MOVES & locked_moves) and "coverage_gap" in flags:
        flags.add("redirection")
    if not (_SPEED_CONTROL & locked_moves) and (
        "speed_control" in flags or "support_speed_control" in present_roles
    ):
        flags.add("speed_control")
    return flags


def _covers_flag(snap: dict[str, Any], species: str, flag: str) -> bool:
    sid = to_id(species)
    e = (snap.get("species") or {}).get(sid) or {}
    abs_ = [to_id(v) for v in (e.get("abilities") or {}).values() if isinstance(v, str)]
    ls = set(resolve_learnset(snap, species) or [])
    if flag == "weather":
        return any(a in WEATHER_SETTERS or a in ABILITY_TO_FIELD for a in abs_) or bool(
            ls & set(_WEATHER_MANUAL)
        )
    if flag == "redirection":
        return bool(ls & REDIRECT_MOVES)
    if flag == "speed_control":
        return bool(ls & _SPEED_CONTROL)
    if flag == "coverage_gap":
        return True
    return False


def _sort_group(
    metas: list[CandidateMeta],
) -> list[CandidateMeta]:
    def key(m: CandidateMeta) -> tuple:
        # Higher commitment first; missing last. Near-tie kit: more reinforcements better.
        # usage_pct higher better; name ascending.
        c = m.commitment_pct
        return (
            0 if c is None else 1,
            -(c or 0.0),
            -m.verified_reinforcements,
            0 if m.usage_pct is None else 1,
            -(m.usage_pct or 0.0),
            m.species,
        )

    # Near-tie: within NEAR_TIE_PCT, prefer more verified reinforcements.
    # Primary sort already puts commitment first; re-sort with near-tie awareness:
    ordered = sorted(metas, key=key)
    # Stable pairwise: if |c_a-c_b|<=NEAR_TIE and reinforcements differ, reinforcements win.
    # Implemented by key using reinforcements as secondary after commitment bucket.
    # Refine: group near-ties and sort by reinforcements within band.
    if len(ordered) < 2:
        return ordered
    out: list[CandidateMeta] = []
    i = 0
    while i < len(ordered):
        band = [ordered[i]]
        j = i + 1
        while j < len(ordered):
            a, b = band[0], ordered[j]
            if a.commitment_pct is None or b.commitment_pct is None:
                break
            if abs(a.commitment_pct - b.commitment_pct) <= NEAR_TIE_PCT:
                band.append(ordered[j])
                j += 1
            else:
                break
        band.sort(
            key=lambda m: (
                -m.verified_reinforcements,
                0 if m.usage_pct is None else 1,
                -(m.usage_pct or 0.0),
                m.species,
            )
        )
        out.extend(band)
        i = j if j > i else i + 1
    return out


def _apply_kit(
    metas: list[CandidateMeta],
    move: str,
    *,
    snap: dict[str, Any],
    proposer: KitInteractionProposer | None,
    calc_client: CalcClient | None,
) -> None:
    if proposer is None:
        return
    for m in metas:
        kit = {"species": m.species, "abilities": _ability_names(snap, m.species)}
        proposals = proposer(kit, move) or []
        n = 0
        for p in proposals:
            if verify_kit_interaction(p, kit, move, snap=snap, calc_client=calc_client):
                n += 1
        m.verified_reinforcements = n


def _ability_names(snap: dict[str, Any], species: str) -> list[str]:
    e = (snap.get("species") or {}).get(to_id(species)) or {}
    return [v for v in (e.get("abilities") or {}).values() if isinstance(v, str)]


def verify_kit_interaction(
    proposal: ProposedInteraction,
    kit: dict[str, Any],
    move: str,
    *,
    snap: dict[str, Any] | None = None,
    calc_client: CalcClient | None = None,
) -> bool:
    snap = snap or load_snapshot()
    species = kit.get("species") or ""
    if proposal.kind == "ability":
        ab = proposal.ability or ""
        if not ab or not species_can_have_ability(snap, species, ab):
            return False
        if not proposal.quantitative:
            return True
        if calc_client is None:
            return False
        return _calc_ability_differs(calc_client, species, ab, move)
    if proposal.kind == "move_flag":
        if proposal.flag == "contact":
            return _makes_contact(move)
        if proposal.flag == "charge_weather":
            return to_id(move) in _CHARGE_INSTANT_WEATHER
        return False
    # judgment-only / unknown → discard
    return False


def _calc_ability_differs(
    client: CalcClient, species: str, ability: str, move: str
) -> bool:
    try:
        with_ab: PokemonSpecOptional = {
            "species": species,
            "ability": ability,
            "moves": [move],
        }
        without: PokemonSpecOptional = {"species": species, "moves": [move]}
        stub: PokemonSpecOptional = {"species": "Blissey", "moves": ["Seismic Toss"]}
        a = client.calculate(with_ab, stub, move)
        b = client.calculate(without, stub, move)
        return a != b
    except Exception:
        return False


def propose_kit_interactions(
    kit: dict[str, Any],
    move: str,
    *,
    proposer: KitInteractionProposer | None = None,
) -> list[ProposedInteraction]:
    if proposer is None:
        return []
    return list(proposer(kit, move) or [])


def narrow_candidates_for_move(
    move: str,
    state: RecommenderState,
    *,
    snap: dict[str, Any] | None = None,
    small_pool: int = SMALL_POOL,
    proposer: KitInteractionProposer | None = None,
    calc_client: CalcClient | None = None,
    commitment_override: dict[str, float | None] | None = None,
    usage_override: dict[str, float | None] | None = None,
    available_species: Collection[str] = (),
    ownership_mode: OwnershipMode = "off",
) -> NarrowResult:
    snap = snap or load_snapshot()
    regulation = state.get("regulation_mod") or "champions-reg-mb"
    # usage files keyed champions-reg-mb; map short form
    if regulation == "champions":
        regulation = "champions-reg-mb"

    owned = {sid for species in available_species if (sid := to_id(species))}
    pool = learners_of(move, snap=snap)
    if ownership_mode == "owned_only":
        pool = [name for name in pool if to_id(name) in owned]

    def ownership_order(names: list[str]) -> list[str]:
        if ownership_mode not in {"owned_first", "owned_last"}:
            return names
        return sorted(names, key=lambda name: to_id(name) not in owned)

    if len(pool) <= small_pool:
        pool = ownership_order(pool)
        delivery = {
            n: ("prankster" if _has_prankster(snap, n) else "natural_speed") for n in pool
        }
        return NarrowResult(
            candidates=pool,
            stopped_at=1,
            delivery=delivery,
            grouping_skipped=move_priority(move) != 0,
        )

    flags = team_need_flags(state)
    filtered = pool
    if flags:
        narrowed = [n for n in pool if any(_covers_flag(snap, n, f) for f in flags)]
        if narrowed:
            filtered = narrowed
            if len(filtered) <= small_pool:
                filtered = ownership_order(filtered)
                delivery = {
                    n: ("prankster" if _has_prankster(snap, n) else "natural_speed")
                    for n in filtered
                }
                return NarrowResult(
                    candidates=filtered,
                    stopped_at=2,
                    delivery=delivery,
                    grouping_skipped=move_priority(move) != 0,
                )

    prio = move_priority(move)
    grouping_skipped = prio != 0

    def meta_for(name: str, delivery: Delivery) -> CandidateMeta:
        if commitment_override and name in commitment_override:
            c = commitment_override[name]
        elif commitment_override and to_id(name) in commitment_override:
            c = commitment_override[to_id(name)]
        else:
            c = _commitment_pct(name, move, regulation=regulation)
        if usage_override and name in usage_override:
            u = usage_override[name]
        elif usage_override and to_id(name) in usage_override:
            u = usage_override[to_id(name)]
        else:
            u = _ladder_usage_pct(name, regulation=regulation)
        return CandidateMeta(
            species=name, delivery=delivery, commitment_pct=c, usage_pct=u
        )

    if grouping_skipped:
        metas = [meta_for(n, "natural_speed") for n in filtered]
        _apply_kit(metas, move, snap=snap, proposer=proposer, calc_client=calc_client)
        final, backstop = _admit_candidates(
            metas, ownership_mode=ownership_mode, owned=owned
        )
    else:
        prank = [n for n in filtered if _has_prankster(snap, n)]
        nat = [n for n in filtered if not _has_prankster(snap, n)]
        p_metas = [meta_for(n, "prankster") for n in prank]
        n_metas = [meta_for(n, "natural_speed") for n in nat]
        _apply_kit(p_metas, move, snap=snap, proposer=proposer, calc_client=calc_client)
        _apply_kit(n_metas, move, snap=snap, proposer=proposer, calc_client=calc_client)
        prepared = _prepare_delivery_group(p_metas) + _prepare_delivery_group(n_metas)
        final, backstop = _admit_prepared(
            prepared, ownership_mode=ownership_mode, owned=owned
        )

    # ponytail: step 4 opportunity-cost ranking needs move-usage density we don't have;
    # learnsets alone are not enough. Upgrade when per-move set-inclusion ranks exist.
    delivery_map = {m.species: m.delivery for m in final}
    reinf = {m.species: m.verified_reinforcements for m in final}
    return NarrowResult(
        candidates=[m.species for m in final],
        stopped_at=3,
        delivery=delivery_map,
        candidate_meta={to_id(m.species): m for m in final},
        verified_reinforcements=reinf,
        backstop_applied=backstop,
        grouping_skipped=grouping_skipped,
    )


def _demoted(m: CandidateMeta) -> bool:
    return m.usage_pct is None or m.usage_pct < MIN_USAGE_PCT


def _prepare_delivery_group(metas: list[CandidateMeta]) -> list[CandidateMeta]:
    # intentional correction: MIN_USAGE_PCT demotion is within-tier only.
    # Delivery tier (Prankster=0) outranks usage demotion — ADR-015 2026-07-27f.
    # Old recombined-list demotion let nat clearers beat demoted Pranksters; removed.
    #
    # Logical within-tier order (ascending after prepare→position for rank_and_cut):
    #   (demoted: 0 clearer / 1 demoted,
    #    then _sort_group: has-commitment, -commitment, -reinforcements,
    #    has-usage, -usage_pct, species)
    # Near-tie band lives inside _sort_group per demotion bucket — not a static tuple
    # component — hence prepare-then-position rather than a raw tuple on rank_and_cut.
    clear = _sort_group([m for m in metas if not _demoted(m)])
    low = _sort_group([m for m in metas if _demoted(m)])
    return clear + low


def _delivery_tier(m: CandidateMeta) -> int:
    return 0 if m.delivery == "prankster" else 1


def _admit_prepared(
    prepared: list[CandidateMeta],
    *,
    ownership_mode: OwnershipMode = "off",
    owned: Collection[str] = (),
) -> tuple[list[CandidateMeta], bool]:
    pos = {id(m): i for i, m in enumerate(prepared)}
    final = rank_and_cut(
        prepared,
        key=lambda m: pos[id(m)],
        n=BACKSTOP_CEILING,
        tier=_delivery_tier,
        slack=-1,
        order="ascending",
        ownership_mode=ownership_mode,
        is_owned=lambda meta: to_id(meta.species) in owned,
    )
    return final, len(prepared) > BACKSTOP_CEILING


def _admit_candidates(
    metas: list[CandidateMeta],
    *,
    ownership_mode: OwnershipMode = "off",
    owned: Collection[str] = (),
) -> tuple[list[CandidateMeta], bool]:
    """Single delivery group (e.g. grouping_skipped → all natural_speed)."""
    return _admit_prepared(
        _prepare_delivery_group(metas),
        ownership_mode=ownership_mode,
        owned=owned,
    )


def pick_default_and_alternatives(
    candidates: list[str],
    *,
    regulation: str = "champions-reg-mb",
    redundancy_tier: dict[str, int] | None = None,
) -> dict[str, Any]:
    """default is always candidates[0] (unchanged) -- the single strongest
    candidate stays purely rank-based, since "the best available option
    also happens to cover an already-satisfied role" is a reasonable
    default. redundancy_tier (species -> 0/1/2, lower = prefer) only
    affects which 2 alternatives get shown alongside it: prefers
    candidates offering genuinely distinct strategic value over ones
    whose only real contribution duplicates a role the locked team
    already has covered. A stable sort preserves relative rank order
    within each tier, so this reorders for diversity without overriding
    the underlying ranking's judgment about which candidates within a
    tier are actually stronger. Never leaves an alternative slot empty
    to avoid redundancy -- if there aren't enough tier-0/1 candidates to
    fill both slots, tier-2 candidates still fill the remainder.
    """
    if not candidates:
        return {"default": None, "alternatives": []}
    default = candidates[0]
    rest = candidates[1:]
    if redundancy_tier:
        rest = sorted(rest, key=lambda c: redundancy_tier.get(c, 0))
    return {
        "default": default,
        "alternatives": rest[:2],
    }


def preferred_move_ids(
    role: str | None,
    archetype_components: list[str],
    flags: set[str],
) -> list[str]:
    prefs: list[str] = []
    seen: set[str] = set()

    def add(mids: list[str]) -> None:
        for m in mids:
            if m not in seen:
                seen.add(m)
                prefs.append(m)

    if role and role in _ROLE_PREF_MOVES:
        add(_ROLE_PREF_MOVES[role])
    for c in archetype_components:
        if c in _ARCHETYPE_PREF_MOVES:
            add(_ARCHETYPE_PREF_MOVES[c])
    if "redirection" in flags:
        add(list(REDIRECT_MOVES))
    if "speed_control" in flags:
        add(list(_SPEED_CONTROL))
    if "weather" in flags:
        add(list(_WEATHER_MANUAL))
    return prefs


def assemble_moveset_fallback(
    species: str,
    slot: Slot,
    state: RecommenderState,
    *,
    snap: dict[str, Any] | None = None,
) -> list[str]:
    snap = snap or load_snapshot()
    regulation = state.get("regulation_mod") or "champions-reg-mb"
    if regulation == "champions":
        regulation = "champions-reg-mb"
    ls = set(resolve_learnset(snap, species) or [])
    arch = state.get("archetype")
    components = list(getattr(arch, "value", None) or [])
    flags = team_need_flags(state)
    prefs = preferred_move_ids(slot.role.value, components, flags)
    kept = [m for m in prefs if m in ls]
    order = {m: i for i, m in enumerate(prefs)}

    def _c(m: str) -> float | None:
        return _commitment_pct(species, m, regulation=regulation)

    kept.sort(
        key=lambda m: (
            0 if _c(m) is None else 1,
            -(_c(m) or 0.0),
            order.get(m, 10**9),
        )
    )

    def _with_protect(chosen: list[str]) -> list[str]:
        body = [m for m in chosen if to_id(m) != "protect"]
        if "protect" in ls:
            return body[:3] + ["protect"]
        return body[:4]

    moves = _with_protect(kept)
    red = validate_moveset_redundancy(
        species,
        moves,
        team_draft=list(state.get("team_draft") or []),
        state=state,
        snap=snap,
    )
    if red.seeming and not red.justified and red.drop_moves:
        drop = {to_id(m) for m in red.drop_moves}
        moves = _with_protect([m for m in moves if to_id(m) not in drop])
    return moves


def _resolve_weather_ability(
    species: str, ability: str | None, snap: dict[str, Any]
) -> str | None:
    if ability:
        return to_id(ability)
    e = (snap.get("species") or {}).get(to_id(species)) or {}
    for v in (e.get("abilities") or {}).values():
        if isinstance(v, str) and to_id(v) in ABILITY_TO_FIELD:
            return to_id(v)
    return None


def _weather_from_ability(aid: str | None) -> str | None:
    if not aid:
        return None
    field = ABILITY_TO_FIELD.get(to_id(aid))
    if not field:
        return None
    return field.get("weather")  # type: ignore[return-value]


def validate_moveset_redundancy(
    species: str,
    moves: list[str],
    *,
    ability: str | None = None,
    team_draft: list[Slot] | None = None,
    threats: list[PokemonSpecOptional] | None = None,
    state: RecommenderState | None = None,
    snap: dict[str, Any] | None = None,
) -> RedundancyResult:
    snap = snap or load_snapshot()
    mids = [to_id(m) for m in moves]
    aid = _resolve_weather_ability(species, ability, snap)
    c1 = _weather_from_ability(aid)

    weather_moves = [m for m in mids if m in _WEATHER_MANUAL]
    speed_moves = [m for m in mids if m in _SPEED_CONTROL]
    redirect_moves = [m for m in mids if m in REDIRECT_MOVES]

    seeming = False
    drop: list[str] = []
    if len(weather_moves) >= 2:
        seeming = True
        drop.append(weather_moves[1])
    if len(speed_moves) >= 2:
        seeming = True
        drop.append(speed_moves[1])
    if len(redirect_moves) >= 2:
        seeming = True
        drop.append(redirect_moves[1])
    # Passive ability + any manual weather move needs justification (same- or cross-weather).
    if c1 and weather_moves:
        seeming = True
        for wm in weather_moves:
            drop.append(wm)

    if not seeming:
        return RedundancyResult(ok=True, seeming=False, justified=False)

    # Pattern A-precondition
    hard = [m for m in mids if m in _HARD_REQUIRE_WEATHER]
    for wm in weather_moves:
        c2 = _WEATHER_MANUAL[wm]
        if c1 and c2 != c1 and hard and any(_HARD_REQUIRE_WEATHER[h] == c1 for h in hard):
            return RedundancyResult(
                ok=True, seeming=True, justified=True, pattern="A-precondition"
            )

    # Pattern A-team
    if c1 and weather_moves and team_draft:
        for wm in weather_moves:
            c2 = _WEATHER_MANUAL[wm]
            if c2 == c1:
                continue
            for slot in team_draft:
                if slot.species.value is None:
                    continue
                if to_id(slot.species.value) == to_id(species):
                    continue
                if not slot.species.locked and slot.species.value is None:
                    continue
                t_aid = _resolve_weather_ability(slot.species.value, None, snap)
                tw = _weather_from_ability(t_aid)
                if tw == c2:
                    return RedundancyResult(
                        ok=True, seeming=True, justified=True, pattern="A-team"
                    )

    # Pattern B
    threat_specs = threats
    if threat_specs is None and state is not None:
        threat_specs = [tc.spec for tc in get_relevant_threats(state)]
    if weather_moves and threat_specs:
        for wm in weather_moves:
            c2 = _WEATHER_MANUAL[wm]
            for t in threat_specs:
                t_ab = to_id(t.get("ability") or "")
                w = _weather_from_ability(t_ab)
                if w and w != c2:
                    return RedundancyResult(
                        ok=True, seeming=True, justified=True, pattern="B"
                    )

    return RedundancyResult(
        ok=False, seeming=True, justified=False, drop_moves=list(dict.fromkeys(drop))
    )
