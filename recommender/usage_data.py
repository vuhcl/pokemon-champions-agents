"""Load offline usage snapshots (in-game ladder + Showdown@1500)."""

from __future__ import annotations

import json
from collections import defaultdict, Counter
from datetime import date, datetime
from collections.abc import Callable, Sequence
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict

from recommender.ids import regulation_file_tag, to_id
from recommender.legality import load_snapshot as load_legality_snapshot
from recommender.usage_ingame_sanity import ingame_monotonic_tail_corrupt
from recommender.species_forms import ingame_excluded_species_ids, item_mega_forme
from recommender.sp_convert import evs_to_sp
from recommender.state import PokemonSet, StatsTable

REPO_ROOT = Path(__file__).resolve().parents[1]
USAGE_DIR = REPO_ROOT / "data" / "usage"
TEAM_COMP_DIR = REPO_ROOT / "data" / "team-composition"

# Doubles coverage pool (no relevance_filter). Not Role Compendium's 20-30 scale.
TEAM_THREAT_N = 50

# Slot-level when relevance_filter set. Practical update from ADR-015a "handful" (3-5);
# architecture_decisions.md remains read-only — note in task summary only.
SLOT_THREAT_N = 10  # allowed range 5-10; default top of range

# Smogon convention: 1500+ = high-level ladder filter (casual play stripped).
# Confirmed 2026-06 gen9championsvgc2026regmb: 1_163_315 battles at 1500 — adequate.
SHOWDOWN_USAGE_RATING = 1500

_STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")

SetMatchSource = Literal["vgcpastes", "featured"]
SetMatchProvenance = Literal["vgcpastes", "featured"]


class SetMatchEntry(TypedDict):
    set: PokemonSet
    source: SetMatchSource
    provenance: SetMatchProvenance
    occurrence_count: NotRequired[int]
    date_shared_earliest: NotRequired[str]


SetMatchResult = list[SetMatchEntry]


@lru_cache(maxsize=4)
def load_usage(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    tag = regulation_file_tag(regulation)
    path = USAGE_DIR / f"{tag}.v1.json"
    if not path.exists():
        return {"meta": {}, "species": {}, "ingame_doubles": {"species": {}}, "showdown_vgc_mb": {"species": {}}}
    return json.loads(path.read_text())


def species_usage(species: str, *, regulation: str = "champions-reg-mb") -> dict[str, Any] | None:
    snap = load_usage(regulation)
    return snap.get("species", {}).get(to_id(species))


def build_synthesis_usage_entry(
    species: str, *, regulation: str = "champions-reg-mb"
) -> dict[str, Any] | None:
    """Usage row for default build synthesis: ingame when present (ADR-046 filtered), else flat merge."""
    sid = to_id(species)
    ing = ingame_species_map(regulation).get(sid)
    if ing:
        snap = load_usage(regulation)
        sd = ((snap.get("showdown_vgc_mb") or {}).get("species") or {}).get(sid)
        if sd and ingame_monotonic_tail_corrupt(ing, sd):
            return species_usage(species, regulation=regulation)
        return ing
    return species_usage(species, regulation=regulation)


@lru_cache(maxsize=1)
def ingame_excluded_ids() -> frozenset[str]:
    return ingame_excluded_species_ids(load_legality_snapshot())


def ingame_ladder_species_map(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    """Raw in-game doubles ladder rows (rank/membership only — not build-safe).

    Includes mega-capable bases for popularity rank and threat-ladder membership.
    Do not use for move/item/spread build construction; use ingame_species_map()
    or Showdown for builds.
    """
    return (load_usage(regulation).get("ingame_doubles") or {}).get("species") or {}


def ingame_species_map(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    raw = ingame_ladder_species_map(regulation)
    excluded = ingame_excluded_ids()
    if not excluded:
        return raw
    return {sid: row for sid, row in raw.items() if sid not in excluded}


def showdown_species_map(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    snap = load_usage(regulation)
    return (snap.get("showdown_vgc_mb") or {}).get("species") or {}


def _spread_from_usage(entry: dict[str, Any]) -> StatsTable | None:
    spreads = entry.get("top_spreads") or []
    if not spreads:
        return None
    evs = spreads[0].get("evs") or {}
    return {
        "hp": int(evs.get("hp", 0)),
        "atk": int(evs.get("atk", 0)),
        "def": int(evs.get("def", 0)),
        "spa": int(evs.get("spa", 0)),
        "spd": int(evs.get("spd", 0)),
        "spe": int(evs.get("spe", 0)),
    }


def _nature_from_usage(entry: dict[str, Any]) -> str | None:
    spreads = entry.get("top_spreads") or []
    if spreads and spreads[0].get("nature"):
        return str(spreads[0]["nature"])
    return None


def calc_species_label(species: str, spec: dict[str, Any] | None = None) -> str:
    """Calc-service species label for a build (e.g. Aegislash → Aegislash-Shield)."""
    sid = to_id(species)
    entry = {"id": sid, "name": (spec or {}).get("species") or species}
    return _species_for_spec(entry, species)


def _species_for_spec(entry: dict[str, Any], fallback: str) -> str:
    """Calc-compatible species label: display name only when it to_id-matches the stored id."""
    sid = to_id(entry.get("id") or fallback)
    if sid == "aegislash":
        return "Aegislash-Shield"
    name = entry.get("name") or fallback
    if to_id(name) == sid:
        return name
    legal = (_legality_species().get(sid) or {}).get("name")
    if legal:
        return str(legal)
    return sid


def _nonempty_moves(names: Any) -> list[str]:
    """Skip blank chaos keys, then display-map, cap at 4."""
    out: list[str] = []
    for n in names:
        if n is None or not str(n).strip():
            continue
        out.append(_display_move(str(n)))
        if len(out) >= 4:
            break
    return out


def _set_from_entry(entry: dict[str, Any], species: str) -> PokemonSet | None:
    for fs in entry.get("featured_sets") or []:
        real = _nonempty_moves(fs.get("moves") or [])
        if len(real) >= 4 and fs.get("item") and fs.get("item") != "Nothing":
            out: PokemonSet = {
                "species": _species_for_spec(entry, species),
                "item": _display_item(fs["item"]),
                "moves": real,
            }
            if fs.get("ability"):
                out["ability"] = _display_ability(fs["ability"])
            if fs.get("nature"):
                out["nature"] = fs["nature"]
            elif nat := _nature_from_usage(entry):
                out["nature"] = nat
            spread = _spread_from_usage(entry)
            if spread:
                out["evs"] = spread
            return out
    moves = _nonempty_moves(m["name"] for m in (entry.get("common_moves") or []))
    items = entry.get("common_items") or []
    abilities = entry.get("common_abilities") or []
    if not moves or not items:
        return None
    out = {
        "species": _species_for_spec(entry, species),
        "item": _display_item(items[0]["name"]),
        "moves": moves,
    }
    if abilities:
        out["ability"] = _display_ability(abilities[0]["name"])
    if nat := _nature_from_usage(entry):
        out["nature"] = nat
    spread = _spread_from_usage(entry)
    if spread:
        out["evs"] = spread
    return out  # type: ignore[return-value]


def _iter_usage_ranked_items(entry: dict[str, Any]):
    """Usage-ranked item ids: featured_sets (4-move rows) then common_items."""
    seen: set[str] = set()
    for fs in entry.get("featured_sets") or []:
        real = _nonempty_moves(fs.get("moves") or [])
        if len(real) >= 4 and fs.get("item") and fs.get("item") != "Nothing":
            iid = to_id(fs["item"])
            if iid not in seen:
                seen.add(iid)
                yield _display_item(fs["item"])
    for row in entry.get("common_items") or []:
        iid = to_id(row["name"])
        if iid not in seen:
            seen.add(iid)
            yield _display_item(row["name"])


def _iter_usage_ranked_moves(entry: dict[str, Any]):
    """Usage-ranked move names: featured_sets rows then common_moves."""
    seen: set[str] = set()
    for fs in entry.get("featured_sets") or []:
        for move in _nonempty_moves(fs.get("moves") or []):
            mid = to_id(move)
            if mid not in seen:
                seen.add(mid)
                yield move
    for row in entry.get("common_moves") or []:
        mid = to_id(row["name"])
        if mid not in seen:
            seen.add(mid)
            yield row["name"]


def backfill_moves_from_usage(
    species: str,
    chosen: list[str],
    *,
    regulation: str = "champions-reg-mb",
    exclude_status: bool = True,
) -> list[str]:
    """Fill moveset to 4 from usage-ranked candidates; legality-only backfill."""
    entry = build_synthesis_usage_entry(species, regulation=regulation)
    if not entry:
        return list(chosen)
    snap = load_legality_snapshot()
    moves_meta = snap.get("moves") or {}
    out = list(chosen)
    seen = {to_id(m) for m in out}
    for move in _iter_usage_ranked_moves(entry):
        if len(out) >= 4:
            break
        mid = to_id(move)
        if mid in seen:
            continue
        if exclude_status:
            meta = moves_meta.get(mid) or {}
            if (meta.get("category") or "") == "Status":
                continue
        out.append(move)
        seen.add(mid)
    return out


class TeamConditionedBuild(TypedDict):
    moves: list[str]
    item: str | None
    ability: str | None
    nature: str | None
    evs: dict[str, int] | None
    occurrence_count: int
    match_tier: Literal["triple", "pair", "single"]
    provenance: Literal["team_conditioned"]


def locked_teammate_ids_for_pastes(
    team_draft: list[Any],
    *,
    exclude_species: str | None = None,
) -> frozenset[str]:
    exclude = to_id(exclude_species) if exclude_species else ""
    ids: set[str] = set()
    for slot in team_draft:
        species = getattr(getattr(slot, "species", None), "value", None)
        locked = getattr(getattr(slot, "species", None), "locked", False)
        if not locked or not species:
            continue
        if exclude and to_id(species) == exclude:
            continue
        item = getattr(getattr(slot, "item", None), "value", None)
        for lid in vgcpastes_lookup_species_ids(species, item):
            ids.add(lid)
    return frozenset(ids)


@lru_cache(maxsize=4)
def _vgcpastes_team_index(regulation: str) -> dict[str, tuple[int, ...]]:
    data = load_vgcpastes_builds(regulation)
    index: dict[str, list[int]] = defaultdict(list)
    for team_idx, team in enumerate(data.get("teams") or []):
        roster: set[str] = set()
        for member in team.get("members") or []:
            sid = to_id(str(member.get("species") or ""))
            if sid:
                roster.add(sid)
        for sid in roster:
            index[sid].append(team_idx)
    return {sid: tuple(idxs) for sid, idxs in index.items()}


def _teams_matching_query(query: frozenset[str], *, regulation: str) -> list[int]:
    if not query:
        return []
    index = _vgcpastes_team_index(regulation)
    sets_of_indices = [set(index.get(sid, ())) for sid in query]
    if not all(sets_of_indices):
        return []
    return sorted(set.intersection(*sets_of_indices))


def _query_sets_for_tier(
    candidate_id: str,
    locked_ids: frozenset[str],
    tier: Literal["triple", "pair", "single"],
) -> list[frozenset[str]]:
    locked = sorted(locked_ids)
    if tier == "triple":
        if len(locked) >= 3:
            return [
                frozenset({candidate_id, *combo})
                for combo in combinations(locked, 3)
            ]
        return [frozenset({candidate_id, *locked})]
    if tier == "pair":
        if len(locked) >= 2:
            return [
                frozenset({candidate_id, *combo})
                for combo in combinations(locked, 2)
            ]
        if len(locked) == 1:
            return [frozenset({candidate_id, locked[0]})]
        return []
    return [frozenset({candidate_id, lid}) for lid in locked]


def _member_build_signature(member: dict[str, Any]) -> tuple[Any, ...]:
    moves = tuple(sorted(to_id(m) for m in (member.get("moves") or [])))
    item = to_id(member.get("item") or "")
    ability = to_id(member.get("ability") or "")
    nature = str(member.get("nature") or "")
    spread = normalize_member_evs(member.get("evs"))
    evs_key = tuple(spread[s] for s in _STAT_KEYS) if spread else None
    return (moves, item, ability, nature, evs_key)


def _best_bucket_for_tier(
    species: str,
    locked_ids: frozenset[str],
    *,
    regulation: str,
    tier: Literal["triple", "pair", "single"],
    min_occurrences: int,
) -> TeamConditionedBuild | None:
    candidate_id = to_id(species)
    lookup_ids = set(vgcpastes_lookup_species_ids(species, None))
    data = load_vgcpastes_builds(regulation)
    teams = data.get("teams") or []
    queries = _query_sets_for_tier(candidate_id, locked_ids, tier)
    if not queries:
        return None

    buckets: dict[tuple[Any, ...], list[tuple[int, dict[str, Any]]]] = defaultdict(list)
    seen_teams: set[tuple[int, str]] = set()
    for query in queries:
        for team_idx in _teams_matching_query(query, regulation=regulation):
            if team_idx < 0 or team_idx >= len(teams):
                continue
            dedupe_key = (team_idx, tier)
            if dedupe_key in seen_teams:
                continue
            seen_teams.add(dedupe_key)
            team = teams[team_idx]
            for member in team.get("members") or []:
                sid = to_id(str(member.get("species") or ""))
                if sid not in lookup_ids:
                    continue
                sig = _member_build_signature(member)
                buckets[sig].append((team_idx, member))
                break

    if not buckets:
        return None
    best_sig, hits = max(buckets.items(), key=lambda kv: len(kv[1]))
    if len(hits) < min_occurrences:
        return None
    member = hits[0][1]
    spread = normalize_member_evs(member.get("evs"))
    return TeamConditionedBuild(
        moves=_nonempty_moves(member.get("moves") or []),
        item=_display_item(str(member.get("item") or "")) or None,
        ability=_display_ability(str(member["ability"]))
        if member.get("ability")
        else None,
        nature=str(member.get("nature") or "") or None,
        evs=spread,
        occurrence_count=len(hits),
        match_tier=tier,
        provenance="team_conditioned",
    )


def find_team_conditioned_build(
    species: str,
    locked_teammate_ids: frozenset[str],
    *,
    regulation: str = "champions-reg-mb",
    min_occurrences: int = 3,
) -> TeamConditionedBuild | None:
    # ponytail: paste teams are 6-mon rosters, not bring lists; subset match on
    # candidate+≤3 locked is the bring-4 ceiling — upgrade path if bring data exists.
    if not locked_teammate_ids:
        return None
    for tier in ("triple", "pair", "single"):
        hit = _best_bucket_for_tier(
            species,
            locked_teammate_ids,
            regulation=regulation,
            tier=tier,
            min_occurrences=min_occurrences,
        )
        if hit is not None:
            return hit
    return None


def locked_weather_beneficiaries(locked_contexts: Any) -> frozenset[str]:
    from recommender.anchor_roles import _canonical_weather, weather_beneficiary_ability_ids
    from recommender.condition_resilience import mechanism_condition

    out: set[str] = set()
    for ctx in locked_contexts:
        role_decision = getattr(ctx, "role_decision", None)
        if role_decision is not None:
            for mechanism in role_decision.mechanisms:
                if not mechanism.present or mechanism.relation != "benefits_from":
                    continue
                cond = mechanism_condition(mechanism)
                if not cond:
                    continue
                canon = _canonical_weather(cond) or cond
                if canon in ("Rain", "Sun", "Sand", "Snow"):
                    out.add(canon)
        build = getattr(ctx, "resolved_build", None)
        ability = to_id(getattr(build, "ability", None) or "")
        for weather in ("Rain", "Sun", "Sand", "Snow"):
            if ability in weather_beneficiary_ability_ids(weather):
                out.add(weather)
    return frozenset(out)


def _trim_unneeded_weather_moves(
    species: str,
    moves: list[str],
    *,
    team_draft: list[Any],
    regulation: str,
) -> list[str]:
    from recommender.condition_resilience import provided_conditions
    from recommender.move_narrowing import _WEATHER_MANUAL
    from recommender.team_candidates import collect_locked_anchor_contexts

    locked = collect_locked_anchor_contexts({"team_draft": team_draft})
    provided = provided_conditions(locked)
    beneficiaries = locked_weather_beneficiaries(locked)
    out = list(moves)
    for idx, move in enumerate(out):
        weather = _WEATHER_MANUAL.get(to_id(move))
        if not weather:
            continue
        if weather in provided or weather in beneficiaries:
            continue
        trimmed = out[:idx] + out[idx + 1 :]
        if len(trimmed) < 4:
            return backfill_moves_from_usage(
                species, trimmed, regulation=regulation
            )
        return trimmed
    return out


def _team_conditioned_to_pokemon_set(
    species: str, build: TeamConditionedBuild
) -> PokemonSet:
    out: PokemonSet = {
        "species": calc_species_label(species),
        "moves": list(build["moves"]),
    }
    if build.get("item"):
        out["item"] = build["item"]
    if build.get("ability"):
        out["ability"] = build["ability"]
    if build.get("nature"):
        out["nature"] = build["nature"]
    if build.get("evs"):
        out["evs"] = dict(build["evs"])
    return out


def build_team_aware_default_set(
    species: str,
    *,
    regulation: str = "champions-reg-mb",
    role_id: str | None = None,
    team_draft: list[Any] | None = None,
    state: Any | None = None,
    featured_fn: Callable[..., PokemonSet | None] | None = None,
) -> PokemonSet | None:
    """Team-conditioned default set with usage fallbacks and weather trim."""
    featured = featured_fn or featured_or_common_set
    draft = list(team_draft or [])
    locked_ids = (
        locked_teammate_ids_for_pastes(draft, exclude_species=species)
        if draft
        else frozenset()
    )

    if locked_ids:
        conditioned = find_team_conditioned_build(
            species, locked_ids, regulation=regulation
        )
        if conditioned:
            return _team_conditioned_to_pokemon_set(species, conditioned)

    usage: PokemonSet | None = None
    if role_id:
        from recommender.role_aware_synthesis import select_role_aware_build_fields

        entry = build_synthesis_usage_entry(species, regulation=regulation)
        if entry:
            base = featured(species, regulation=regulation)
            selection = select_role_aware_build_fields(
                species,
                role_id,
                entry,
                regulation=regulation,
                usage=base,
                state=state,
            )
            if selection and base:
                usage = dict(base)
                usage["moves"] = list(selection.moves)
                if selection.ability:
                    usage["ability"] = selection.ability

    if usage is None:
        usage = featured(species, regulation=regulation)
    if not usage:
        return None

    moves = list(usage.get("moves") or [])
    if locked_ids and moves:
        moves = _trim_unneeded_weather_moves(
            species, moves, team_draft=draft, regulation=regulation
        )
        if len(moves) < 4:
            moves = backfill_moves_from_usage(
                species, moves, regulation=regulation
            )
        usage = dict(usage)
        usage["moves"] = moves
    return usage


def _iter_usage_ranked_abilities(entry: dict[str, Any]):
    """Usage-ranked ability names: featured_sets rows then common_abilities."""
    seen: set[str] = set()
    for fs in entry.get("featured_sets") or []:
        if fs.get("ability"):
            aid = to_id(fs["ability"])
            if aid not in seen:
                seen.add(aid)
                yield _display_ability(fs["ability"])
    for row in entry.get("common_abilities") or []:
        aid = to_id(row["name"])
        if aid not in seen:
            seen.add(aid)
            yield _display_ability(row["name"])


def pick_team_aware_usage_item(
    species: str,
    *,
    regulation: str = "champions-reg-mb",
    used: set[str],
    entry: dict[str, Any] | None = None,
    snap: dict[str, Any] | None = None,
) -> str | None:
    """First legal usage-ranked item not already on team_draft (Item Clause)."""
    from recommender.legality import is_item_legal, load_snapshot

    row = (
        entry
        if entry is not None
        else build_synthesis_usage_entry(species, regulation=regulation)
    )
    if not row:
        return None
    snap = snap or load_snapshot()
    for item in _iter_usage_ranked_items(row):
        if to_id(item) in used:
            continue
        if is_item_legal(snap, item):
            return item
    return None


def featured_or_common_set(species: str, *, regulation: str = "champions-reg-mb") -> PokemonSet | None:
    """Most representative set: ingame CBD when present, else flat merge (Showdown-backed)."""
    entry = build_synthesis_usage_entry(species, regulation=regulation)
    if entry:
        built = _set_from_entry(entry, species)
        if built:
            return built
    fallback = species_usage(species, regulation=regulation)
    if not fallback:
        return None
    return _set_from_entry(fallback, species)


def set_from_showdown(species: str, *, regulation: str = "champions-reg-mb") -> PokemonSet | None:
    entry = showdown_species_map(regulation).get(to_id(species))
    if not entry:
        return None
    return _set_from_entry(entry, species)


def set_from_ingame(species: str, *, regulation: str = "champions-reg-mb") -> PokemonSet | None:
    entry = ingame_species_map(regulation).get(to_id(species))
    if not entry:
        return None
    return _set_from_entry(entry, species)


def find_set_matching(
    species: str,
    moves: list[str],
    item: str | None,
    *,
    regulation: str = "champions-reg-mb",
) -> SetMatchResult:
    """Exact moves+item match: VGCPastes first, then synthetic featured_sets.

    ``item is None`` means unspecified (no exact match attempted).
    ``item == ""`` means explicitly no held item.
    Returns a ranked list (empty = miss; [0] = primary; [1:] = alternatives).
    """
    if item is None:
        return []
    want_moves = sorted(to_id(m) for m in moves)
    want_item = to_id(item)

    vgcpastes_hits = _match_vgcpastes(
        species, want_moves, want_item, item=item, regulation=regulation
    )
    if vgcpastes_hits:
        return vgcpastes_hits

    entry = species_usage(species, regulation=regulation)
    if not entry:
        return []
    for fs in entry.get("featured_sets") or []:
        fs_moves = sorted(to_id(m) for m in (fs.get("moves") or []))
        fs_item = to_id(fs.get("item") or "")
        if fs_moves == want_moves and fs_item == want_item:
            out: PokemonSet = {
                "species": _species_for_spec(entry, species),
                "item": _display_item(fs.get("item") or item),
                "moves": _nonempty_moves(fs.get("moves") or moves),
            }
            if fs.get("ability"):
                out["ability"] = _display_ability(fs["ability"])
            spread = _spread_from_usage(entry)
            if spread:
                out["evs"] = spread
            return [
                {
                    "set": out,
                    "source": "featured",
                    "provenance": "featured",
                }
            ]
    return []


@lru_cache(maxsize=4)
def load_vgcpastes_builds(regulation: str = "champions-reg-mb") -> dict[str, Any]:
    tag = regulation_file_tag(regulation)
    path = TEAM_COMP_DIR / f"{tag}.vgcpastes-builds.v1.json"
    if not path.exists():
        return {"meta": {}, "teams": [], "cores": []}
    return json.loads(path.read_text())


def normalize_member_evs(raw: dict[str, Any] | None) -> dict[str, int] | None:
    """Normalize paste EVs to Champions SP (0–32, sum 66). None if unusable."""
    if not isinstance(raw, dict):
        return None
    try:
        spread = {stat: int(raw.get(stat, 0)) for stat in _STAT_KEYS}
    except (TypeError, ValueError):
        return None
    if any(v > 32 for v in spread.values()):
        spread = evs_to_sp(spread)
    if sum(spread.values()) != 66 or any(v < 0 or v > 32 for v in spread.values()):
        return None
    return spread


def nature_for_spread(
    species: str,
    spread: StatsTable,
    *,
    regulation: str = "champions-reg-mb",
    moves: Sequence[str] = (),
) -> str | None:
    """Join a real nature to a CBD/Showdown EV spread (or matching 4-move set).

    Order: featured/paste moveset match → exact EV Showdown → exact EV pastes →
    same-Spe L1≤4 Showdown (ponytail: 2-point spa/spd CBD noise; drop when dumps align).
    """
    sid = to_id(species)
    try:
        want = tuple(int(spread.get(k, 0)) for k in _STAT_KEYS)
    except (TypeError, ValueError):
        return None
    want_spe = want[5]
    move_list = [str(m) for m in moves if m]
    sd = showdown_species_map(regulation).get(sid) or {}

    if len(move_list) == 4:
        want_moves = frozenset(to_id(m) for m in move_list)
        for fs in sd.get("featured_sets") or []:
            fs_moves = fs.get("moves") or []
            if len(fs_moves) < 4:
                continue
            if frozenset(to_id(m) for m in fs_moves[:4]) != want_moves:
                continue
            nat = fs.get("nature")
            if nat:
                return str(nat)
        paste_natures: Counter[str] = Counter()
        lookup = set(vgcpastes_lookup_species_ids(species, None))
        for team in load_vgcpastes_builds(regulation).get("teams") or []:
            for member in team.get("members") or []:
                if to_id(str(member.get("species") or "")) not in lookup:
                    continue
                mem_moves = member.get("moves") or []
                if len(mem_moves) != 4:
                    continue
                if frozenset(to_id(m) for m in mem_moves) != want_moves:
                    continue
                nat = member.get("nature")
                if nat:
                    paste_natures[str(nat)] += 1
        if paste_natures:
            return paste_natures.most_common(1)[0][0]

    best: str | None = None
    best_pct = -1.0
    for row in sd.get("top_spreads") or []:
        nat = row.get("nature")
        if not nat:
            continue
        evs = row.get("evs") or {}
        try:
            tup = tuple(int(evs.get(k, 0)) for k in _STAT_KEYS)
        except (TypeError, ValueError):
            continue
        if tup != want:
            continue
        pct = float(row.get("pct") or 0)
        if pct > best_pct:
            best_pct = pct
            best = str(nat)
    if best:
        return best

    paste_exact: Counter[str] = Counter()
    lookup = set(vgcpastes_lookup_species_ids(species, None))
    for team in load_vgcpastes_builds(regulation).get("teams") or []:
        for member in team.get("members") or []:
            if to_id(str(member.get("species") or "")) not in lookup:
                continue
            n_evs = normalize_member_evs(member.get("evs"))
            if n_evs is None:
                continue
            if tuple(n_evs[k] for k in _STAT_KEYS) != want:
                continue
            nat = member.get("nature")
            if nat:
                paste_exact[str(nat)] += 1
    if paste_exact:
        return paste_exact.most_common(1)[0][0]

    nearest: str | None = None
    nearest_l1 = 999
    nearest_pct = -1.0
    for row in sd.get("top_spreads") or []:
        nat = row.get("nature")
        if not nat:
            continue
        evs = row.get("evs") or {}
        try:
            tup = tuple(int(evs.get(k, 0)) for k in _STAT_KEYS)
        except (TypeError, ValueError):
            continue
        if tup[5] != want_spe:
            continue
        l1 = sum(abs(a - b) for a, b in zip(tup, want, strict=True))
        if l1 > 4:
            continue
        pct = float(row.get("pct") or 0)
        if l1 < nearest_l1 or (l1 == nearest_l1 and pct > nearest_pct):
            nearest_l1 = l1
            nearest_pct = pct
            nearest = str(nat)
    return nearest


def parse_date_shared(raw: str | None) -> date | None:
    """Parse VGCPastes ``date_shared`` strings like ``12 Aug 2026``."""
    if not raw or not str(raw).strip():
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%d %b %Y").date()
    except ValueError:
        return None


def vgcpastes_lookup_species_ids(species: str, item: str | None) -> tuple[str, ...]:
    """Species ids to scan in VGCPastes (base + mega label when holding a stone)."""
    requested = to_id(species)
    snap = {"species": _legality_species()}
    ent = snap["species"].get(requested) or {}
    base = ent.get("base_species_id") or requested
    ids: list[str] = []
    for candidate in (requested, base):
        if candidate and candidate not in ids:
            ids.append(candidate)
    item_id = to_id(item) if item else ""
    if item_id:
        mega = item_mega_forme(item_id, base, snap)
        if mega and mega not in ids:
            ids.append(mega)
    return tuple(ids)


def _match_vgcpastes(
    species: str,
    want_moves: list[str],
    want_item: str,
    *,
    item: str,
    regulation: str,
) -> SetMatchResult:
    data = load_vgcpastes_builds(regulation)
    lookup_ids = set(vgcpastes_lookup_species_ids(species, item))
    # bucket_key -> list of (parsed_date_or_max, member, team)
    buckets: dict[
        tuple[str, tuple[int, ...] | None],
        list[tuple[date | None, dict[str, Any]]],
    ] = defaultdict(list)

    for team in data.get("teams") or []:
        team_date = parse_date_shared(team.get("date_shared"))
        for member in team.get("members") or []:
            sid = to_id(str(member.get("species") or ""))
            if sid not in lookup_ids:
                continue
            moves = member.get("moves") or []
            if len(moves) != 4 or not all(moves):
                continue
            mem_moves = sorted(to_id(m) for m in moves)
            mem_item = to_id(member.get("item") or "")
            if mem_moves != want_moves or mem_item != want_item:
                continue
            spread = normalize_member_evs(member.get("evs"))
            nature = str(member.get("nature") or "")
            spread_key: tuple[int, ...] | None = (
                tuple(spread[s] for s in _STAT_KEYS) if spread is not None else None
            )
            buckets[(nature, spread_key)].append((team_date, member))

    if not buckets:
        return []

    ranked: list[tuple[int, date, tuple[str, tuple[int, ...] | None], dict[str, Any]]] = []
    far_future = date(9999, 12, 31)
    for key, rows in buckets.items():
        count = len(rows)
        dates = [d for d, _ in rows if d is not None]
        earliest = min(dates) if dates else far_future
        member = rows[0][1]
        ranked.append((count, earliest, key, member))

    # occurrence desc, then earliest date asc
    ranked.sort(key=lambda r: (-r[0], r[1]))

    out: SetMatchResult = []
    for count, earliest, key, member in ranked:
        nature, spread_key = key
        built: PokemonSet = {
            "species": str(member.get("species_display") or member.get("species") or species),
            "moves": [str(m) for m in (member.get("moves") or [])][:4],
        }
        raw_item = member.get("item")
        if raw_item:
            built["item"] = _display_item(str(raw_item))
        else:
            built["item"] = ""
        if member.get("ability"):
            built["ability"] = _display_ability(str(member["ability"]))
        if nature:
            built["nature"] = nature
        if spread_key is not None:
            built["evs"] = {s: spread_key[i] for i, s in enumerate(_STAT_KEYS)}
        entry: SetMatchEntry = {
            "set": built,
            "source": "vgcpastes",
            "provenance": "vgcpastes",
            "occurrence_count": count,
        }
        if earliest != far_future:
            entry["date_shared_earliest"] = earliest.isoformat()
        out.append(entry)
    return out


@lru_cache(maxsize=1)
def _legality_species() -> dict[str, Any]:
    path = REPO_ROOT / "data" / "legality" / "champions.v1.json"
    if not path.exists():
        return {}
    return (json.loads(path.read_text()).get("species")) or {}


@lru_cache(maxsize=1)
def _legality_blob() -> dict[str, Any]:
    path = REPO_ROOT / "data" / "legality" / "champions.v1.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


@lru_cache(maxsize=1)
def _ability_display() -> dict[str, str]:
    out: dict[str, str] = {}
    for ent in _legality_species().values():
        for name in (ent.get("abilities") or {}).values():
            if isinstance(name, str) and name:
                out[to_id(name)] = name
    return out


def _display_item(raw: str) -> str:
    if not raw:
        return ""
    ent = (_legality_blob().get("items") or {}).get(to_id(raw))
    return (ent or {}).get("name") or raw


def _display_move(raw: str) -> str:
    ent = (_legality_blob().get("moves") or {}).get(to_id(raw))
    return (ent or {}).get("name") or raw


def _display_ability(raw: str) -> str:
    return _ability_display().get(to_id(raw), raw)


def lineage_ids(ladder_species: str) -> list[str]:
    """Base id plus legality children, even when called with an exact child form."""
    requested = to_id(ladder_species)
    base = (_legality_species().get(requested) or {}).get("base_species_id") or requested
    kids = [base]
    for sid, ent in _legality_species().items():
        if ent.get("base_species_id") == base and sid not in kids:
            kids.append(sid)
    return kids
