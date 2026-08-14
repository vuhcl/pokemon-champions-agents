"""Pairwise threat classifier (ADR-015 Amendment 2026-07-28c)."""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from typing import Any, Hashable, Literal

from recommender.calc_client import (
    CalcClient,
    CalcRequest,
    CalcSuccessResponse,
    FieldSpec,
    PokemonSpecOptional,
)
from recommender.ids import to_id

# Unique keys for one detect_spof ≈ T_form × slots × field_variants ≤ ~80×6×2 ≈ 960.
# Cap keeps several multi-turn reviews resident so cross-turn reuse survives steering
# without mid-SPOF eviction (which would destroy ~(S-1)/S within-call hit rate).
MATCHUP_MEMO_MAX_ENTRIES = 8192

_MATCHUP_MEMO: OrderedDict[Hashable, Any] = OrderedDict()
_MATCHUP_MEMO_STATS = {"hits": 0, "misses": 0}
_MEMO_THREAD_ID: str | None = None

Severity = Literal["decisive", "costly", "toss-up"]
MatchupOutcome = Literal[
    "clean_kill",
    "intentional_non_ko_answer",
    "conditionally_dependent_answer",
    "no_answer",
]
TurnEconomyNote = Literal[
    "charge_delayed",
    "recharge_vulnerable_won",
    "recharge_vulnerable_lost",
    "recharge_vulnerable_moot",
]

# HP-chip path only (1/8). Status-on-contact is a separate set with no chip math yet.
_CONTACT_PUNISH_HP_ABILITIES = frozenset({"roughskin", "ironbarbs"})
_CONTACT_PUNISH_STATUS_ABILITIES = frozenset(
    {"flamebody", "static", "poisonpoint", "effectspore", "cutecharm"}
)
_CONTACT_PUNISH_ITEMS = frozenset({"rockyhelmet"})
_MULTI_HIT_MOVES = frozenset(
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
    }
)
_GUARANTEED_HIT_COUNT = frozenset({"skilllink"})
_WIDE_LENS = frozenset({"widelens"})
# ponytail: static Showdown contact snapshot (std); upgrade = extract flags.contact like gen9_accuracy
_CONTACT_MOVES = frozenset(
    {
        "accelerock",
        "acrobatics",
        "aerialace",
        "aquajet",
        "aquastep",
        "aquatail",
        "assurance",
        "avalanche",
        "axekick",
        "bind",
        "bite",
        "bitterblade",
        "blazekick",
        "bodypress",
        "bodyslam",
        "bounce",
        "bravebird",
        "breakingswipe",
        "brickbreak",
        "brutalswing",
        "bugbite",
        "bulletpunch",
        "ceaselessedge",
        "circlethrow",
        "closecombat",
        "comeuppance",
        "counter",
        "covet",
        "crabhammer",
        "crosschop",
        "crosspoison",
        "crunch",
        "crushclaw",
        "darkestlariat",
        "dig",
        "direclaw",
        "dive",
        "doubleedge",
        "doublehit",
        "dragonclaw",
        "dragonrush",
        "dragontail",
        "drainingkiss",
        "drainpunch",
        "drillpeck",
        "drillrun",
        "dualwingbeat",
        "dynamicpunch",
        "endeavor",
        "extremespeed",
        "facade",
        "fakeout",
        "fellstinger",
        "firefang",
        "firelash",
        "firepunch",
        "firstimpression",
        "flail",
        "flamecharge",
        "flareblitz",
        "flipturn",
        "fly",
        "flyingpress",
        "focuspunch",
        "foulplay",
        "gigaimpact",
        "grassknot",
        "grassyglide",
        "guillotine",
        "gyroball",
        "hammerarm",
        "hardpress",
        "headlongrush",
        "headsmash",
        "heatcrash",
        "heavyslam",
        "highhorsepower",
        "highjumpkick",
        "horndrill",
        "hornleech",
        "icefang",
        "icehammer",
        "icepunch",
        "icespinner",
        "infestation",
        "ironhead",
        "irontail",
        "jetpunch",
        "knockoff",
        "kowtowcleave",
        "lashout",
        "lastresort",
        "leafblade",
        "leechlife",
        "liquidation",
        "lowkick",
        "lowsweep",
        "lunge",
        "machpunch",
        "megahorn",
        "megakick",
        "meteormash",
        "mortalspin",
        "nightslash",
        "nuzzle",
        "outrage",
        "payback",
        "petaldance",
        "phantomforce",
        "playrough",
        "pluck",
        "poisonfang",
        "poisonjab",
        "populationbomb",
        "pounce",
        "pound",
        "powertrip",
        "powerwhip",
        "psychicfangs",
        "psyshieldbash",
        "quickattack",
        "ragefist",
        "ragingbull",
        "rapidspin",
        "razorshell",
        "reversal",
        "sacredsword",
        "seismictoss",
        "shadowclaw",
        "shadowpunch",
        "shadowsneak",
        "skittersmack",
        "smartstrike",
        "snaptrap",
        "solarblade",
        "spiritbreak",
        "steelroller",
        "steelwing",
        "stompingtantrum",
        "stoneaxe",
        "stormthrow",
        "struggle",
        "suckerpunch",
        "supercellslam",
        "superfang",
        "superpower",
        "tailslap",
        "temperflare",
        "thief",
        "thrash",
        "throatchop",
        "thunderfang",
        "thunderpunch",
        "trailblaze",
        "tripleaxel",
        "tropkick",
        "upperhand",
        "uturn",
        "volttackle",
        "waterfall",
        "wavecrash",
        "wildcharge",
        "woodhammer",
        "wrap",
        "xscissor",
        "zenheadbutt",
    }
)

# Sourced from Pokemon Showdown data/moves.ts: flags.charge: 1 / flags.recharge: 1
_CHARGE_MOVES = frozenset(
    {
        "bounce",
        "dig",
        "dive",
        "electroshot",
        "fly",
        "freezeshock",
        "geomancy",
        "iceburn",
        "meteorbeam",
        "phantomforce",
        "razorwind",
        "shadowforce",
        "skullbash",
        "skyattack",
        "skydrop",
        "solarbeam",
        "solarblade",
    }
)
_RECHARGE_MOVES = frozenset(
    {
        "blastburn",
        "eternabeam",
        "frenzyplant",
        "gigaimpact",
        "hydrocannon",
        "hyperbeam",
        "meteorassault",
        "prismaticlaser",
        "roaroftime",
        "rockwrecker",
    }
)
# Instant-under-weather from Showdown onTryMove (not a flag). FieldSpec weather names.
_CHARGE_INSTANT_WEATHER: dict[str, frozenset[str]] = {
    "solarbeam": frozenset({"Sun", "Harsh Sunshine"}),
    "solarblade": frozenset({"Sun", "Harsh Sunshine"}),
    "electroshot": frozenset({"Rain", "Heavy Rain"}),
}
CHARGE_INSTANT_WEATHER = _CHARGE_INSTANT_WEATHER


@dataclass(frozen=True)
class MatchupCaveats:
    contact_punish_applied: bool = False
    multi_hit_assumed: bool = False
    # Track B usability:
    condition_fail: Literal["no_terrain", "no_item"] | None = None
    expanding_force_boosted: bool = False
    # Track C reserved (defaults; apply_tactical_caveats sets these):
    screen_clear_applied: bool = False
    protect_bypass_applied: bool = False


@dataclass(frozen=True)
class MatchupResult:
    outcome: MatchupOutcome
    severity: Severity
    caveats: MatchupCaveats = field(default_factory=MatchupCaveats)
    # ponytail: single note, A-centric — dual-side quirks not dual-reported
    turn_economy_note: TurnEconomyNote | None = None


class MatchupEvidenceError(Exception):
    """Calc batch evidence is incomplete and cannot support a matchup claim."""


@dataclass
class _MoveProfile:
    move: str
    turns_to_ko: int | None
    ko_guaranteed: bool
    max_damage: int
    min_damage: int
    ko_chance: str
    calc: CalcSuccessResponse


def _build_fingerprint(build: PokemonSpecOptional) -> tuple[Any, ...]:
    evs = build.get("evs") or {}
    ev_items = tuple(sorted((str(k), int(v)) for k, v in evs.items()))
    moves = tuple(build.get("moves") or [])
    return (
        build.get("species") or "",
        build.get("item") or "",
        build.get("ability") or "",
        build.get("nature") or "",
        build.get("level"),
        moves,
        ev_items,
    )


def _side_fingerprint(side: dict[str, Any] | None) -> tuple[Any, ...]:
    if not side:
        return ()
    flags = (
        "isReflect",
        "isLightScreen",
        "isAuroraVeil",
        "isTailwind",
        "isHelpingHand",
        "isFriendGuard",
        "isBattery",
        "isProtected",
        "isSR",
    )
    return tuple((f, bool(side.get(f))) for f in flags) + (("spikes", side.get("spikes") or 0),)


def _field_fingerprint(field: FieldSpec | None) -> tuple[Any, ...]:
    if field is None:
        return ()
    return (
        field.get("gameType"),
        field.get("weather"),
        field.get("terrain"),
        bool(field.get("isGravity")),
        bool(field.get("isMagicRoom")),
        bool(field.get("isWonderRoom")),
        bool(field.get("isTrickRoom")),
        _side_fingerprint(field.get("attackerSide")),  # type: ignore[arg-type]
        _side_fingerprint(field.get("defenderSide")),  # type: ignore[arg-type]
    )


def _matchup_cache_key(
    build_a: PokemonSpecOptional,
    build_b: PokemonSpecOptional,
    field: FieldSpec | None,
) -> tuple[Any, ...]:
    return (_build_fingerprint(build_a), _build_fingerprint(build_b), _field_fingerprint(field))


def matchup_memo_stats() -> dict[str, int]:
    return dict(_MATCHUP_MEMO_STATS)


def clear_matchup_memo() -> dict[str, int]:
    """Clear memo storage and return prior hit/miss snapshot."""
    global _MEMO_THREAD_ID
    snap = matchup_memo_stats()
    _MATCHUP_MEMO.clear()
    _MATCHUP_MEMO_STATS["hits"] = 0
    _MATCHUP_MEMO_STATS["misses"] = 0
    _MEMO_THREAD_ID = None
    return snap


def bind_matchup_memo_thread(thread_id: str | None) -> None:
    """Bind memo to a LangGraph thread_id; clear when the thread changes."""
    global _MEMO_THREAD_ID
    tid = thread_id or ""
    if _MEMO_THREAD_ID is None:
        _MEMO_THREAD_ID = tid
        return
    if tid != _MEMO_THREAD_ID:
        clear_matchup_memo()
        _MEMO_THREAD_ID = tid


def _memo_get(key: Hashable) -> MatchupResult | None:
    hit = _MATCHUP_MEMO.get(key)
    if hit is None:
        return None
    _MATCHUP_MEMO.move_to_end(key)
    _MATCHUP_MEMO_STATS["hits"] += 1
    return hit  # type: ignore[return-value]


def _memo_put(key: Hashable, result: MatchupResult) -> None:
    _MATCHUP_MEMO[key] = result
    _MATCHUP_MEMO.move_to_end(key)
    _MATCHUP_MEMO_STATS["misses"] += 1
    while len(_MATCHUP_MEMO) > MATCHUP_MEMO_MAX_ENTRIES:
        _MATCHUP_MEMO.popitem(last=False)


def classify_matchup(
    build_a: PokemonSpecOptional,
    build_b: PokemonSpecOptional,
    field: FieldSpec | None = None,
    *,
    client: CalcClient | None = None,
) -> MatchupResult:
    key = _matchup_cache_key(build_a, build_b, field)
    cached = _memo_get(key)
    if cached is not None:
        return cached

    calc = client or CalcClient()
    neutral = _evaluate_exchange(build_a, build_b, None, calc)

    if field is None or _is_neutral_field(field):
        _memo_put(key, neutral)
        return neutral

    contextual = _evaluate_exchange(build_a, build_b, field, calc)
    if neutral.outcome == "no_answer" and contextual.outcome in {
        "clean_kill",
        "intentional_non_ko_answer",
    }:
        result = MatchupResult(
            outcome="conditionally_dependent_answer",
            severity=contextual.severity,
            caveats=contextual.caveats,
            turn_economy_note=contextual.turn_economy_note,
        )
        _memo_put(key, result)
        return result
    _memo_put(key, contextual)
    return contextual


def _is_neutral_field(field: FieldSpec) -> bool:
    if field.get("weather") or field.get("terrain"):
        return False
    if field.get("isGravity") or field.get("isMagicRoom") or field.get("isWonderRoom"):
        return False
    if field.get("isTrickRoom"):  # ponytail: extension until FieldSpec adds TR
        return False
    for side_key in ("attackerSide", "defenderSide"):
        side = field.get(side_key) or {}
        if any(
            side.get(flag)
            for flag in (
                "isTailwind",
                "isReflect",
                "isLightScreen",
                "isAuroraVeil",
                "isHelpingHand",
                "isFriendGuard",
                "isBattery",
                "isProtected",
                "isSR",
            )
        ):
            return False
        if side.get("spikes"):
            return False
    return True


def _evaluate_exchange(
    build_a: PokemonSpecOptional,
    build_b: PokemonSpecOptional,
    field: FieldSpec | None,
    calc: CalcClient,
) -> MatchupResult:
    a_moves = _damaging_moves(build_a)
    b_moves = _damaging_moves(build_b)
    if not a_moves or not b_moves:
        return MatchupResult(outcome="no_answer", severity="toss-up")

    requests: list[CalcRequest] = []
    for move in a_moves:
        requests.append(_calc_request(build_a, build_b, move, field))
    for move in b_moves:
        requests.append(_calc_request(build_b, build_a, move, field))

    results = calc.calculate_batch(requests)
    a_profiles = _profiles_from_batch(a_moves, results[: len(a_moves)])
    b_profiles = _profiles_from_batch(b_moves, results[len(a_moves) :])
    a_best = _pick_best_offense(a_profiles, field)
    b_best = _pick_best_offense(b_profiles, field)
    if a_best is None or b_best is None:
        return MatchupResult(outcome="no_answer", severity="toss-up")

    a_hp, b_hp = _defender_hp(a_best.calc), _defender_hp(b_best.calc)
    a_spe = _attacker_spe(a_best.calc)
    b_spe = _attacker_spe(b_best.calc)

    outcome, a_hp_remaining = _simulate_exchange(
        a_best, b_best, a_spe, b_spe, a_hp, b_hp, field
    )
    caveats = MatchupCaveats()
    severity = _severity_from_hp(a_hp_remaining, a_hp)
    note = _turn_economy_note(a_best, b_best, outcome, field)

    caveats = replace(caveats, **_usability_caveat_fields(a_best.move, build_b, field))

    if outcome in {"clean_kill", "intentional_non_ko_answer"} and _contact_punish_applies(
        build_b, a_best.move
    ):
        chip = _contact_punish_chip(build_b, a_hp)
        a_hp_remaining = max(0, a_hp_remaining - chip)
        caveats = replace(caveats, contact_punish_applied=True)
        severity = _severity_from_hp(a_hp_remaining, a_hp)

    if _multi_hit_assumed(build_a, a_best.move, a_best):
        caveats = replace(caveats, multi_hit_assumed=True)
        severity = _downgrade_for_multi_hit(severity, a_best)

    from recommender.tactical_mechanics import apply_tactical_caveats

    caveats = apply_tactical_caveats(
        move_id=a_best.move,
        attacker_ability=build_a.get("ability"),
        field=field,
        caveats=caveats,
    )

    return MatchupResult(
        outcome=outcome,
        severity=severity,
        caveats=caveats,
        turn_economy_note=note,
    )


def _calc_request(
    attacker: PokemonSpecOptional,
    defender: PokemonSpecOptional,
    move: str,
    field: FieldSpec | None,
) -> CalcRequest:
    req: CalcRequest = {"attacker": attacker, "defender": defender, "move": move}
    if field is not None:
        req["field"] = field
    return req


def _damaging_moves(build: PokemonSpecOptional) -> list[str]:
    from recommender.counters import load_move_flags

    flags = load_move_flags()
    out: list[str] = []
    for m in build.get("moves") or []:
        meta = flags.get(to_id(m))
        if meta and meta.get("category") == "Status":
            continue
        out.append(m)
    return out


def _profiles_from_batch(
    moves: list[str], results: list[object]
) -> list[_MoveProfile]:
    if len(results) != len(moves):
        raise MatchupEvidenceError(
            f"calc batch count mismatch: expected {len(moves)}, got {len(results)}"
        )
    profiles: list[_MoveProfile] = []
    for move, raw in zip(moves, results):
        if not isinstance(raw, dict):
            raise MatchupEvidenceError(
                f"calc batch row for {move!r} is not an object"
            )
        if "error" in raw:
            raise MatchupEvidenceError(
                f"calc batch row for {move!r} failed: {raw['error']}"
            )
        calc = raw  # CalcSuccessResponse
        turns, guaranteed = _parse_ko_turns(str(calc.get("koChance") or ""), calc)
        dmg_range = calc.get("damageRange") or calc.get("raw", {}).get("range") or [0, 0]
        profiles.append(
            _MoveProfile(
                move=move,
                turns_to_ko=turns,
                ko_guaranteed=guaranteed,
                max_damage=int(dmg_range[-1]),
                min_damage=int(dmg_range[0]),
                ko_chance=str(calc.get("koChance") or ""),
                calc=calc,
            )
        )
    return profiles


def _parse_ko_turns(ko_chance: str, calc: CalcSuccessResponse) -> tuple[int | None, bool]:
    text = ko_chance.lower()
    raw = calc.get("raw") or {}
    kochance = raw.get("kochance") or {}
    n = kochance.get("n")
    chance = kochance.get("chance")

    if "ohko" in text and "2hko" not in text and "3hko" not in text:
        guaranteed = chance is None or chance >= 1.0 or "100%" in text
        return 1, guaranteed
    if "2hko" in text:
        guaranteed = chance is None or chance >= 1.0 or "100%" in text
        return 2, guaranteed
    if "3hko" in text:
        guaranteed = chance is None or chance >= 1.0 or "100%" in text
        return 3, guaranteed
    if isinstance(n, int) and n > 0:
        guaranteed = chance is not None and chance >= 1.0
        return n, guaranteed
    return None, False


def _charge_delayed(move: str, field: FieldSpec | None) -> bool:
    # ponytail: Power Herb skips charge in-game — ignored until item handling is needed
    mid = to_id(move)
    if mid not in _CHARGE_MOVES:
        return False
    instant = _CHARGE_INSTANT_WEATHER.get(mid)
    if instant and field and field.get("weather") in instant:
        return False
    return True


def _effective_turns_to_ko(
    profile: _MoveProfile, field: FieldSpec | None
) -> int:
    turns = profile.turns_to_ko if profile.turns_to_ko is not None else 99
    if profile.turns_to_ko is not None and _charge_delayed(profile.move, field):
        return turns + 1
    return turns


def _pick_best_offense(
    profiles: list[_MoveProfile], field: FieldSpec | None = None
) -> _MoveProfile | None:
    viable = [p for p in profiles if p.max_damage > 0]
    if not viable:
        return None

    def key(p: _MoveProfile) -> tuple[int, int, int]:
        turns = _effective_turns_to_ko(p, field)
        guaranteed = 0 if p.ko_guaranteed else 1
        return (turns, guaranteed, -p.max_damage)

    return min(viable, key=key)


def _usability_caveat_fields(
    move: str,
    defender: PokemonSpecOptional,
    field: FieldSpec | None,
) -> dict[str, Any]:
    """Track B condition_fail / expanding_force_boosted fields for replace()."""
    mid = to_id(move)
    out: dict[str, Any] = {}
    if mid == "steelroller" and not (field and field.get("terrain")):
        out["condition_fail"] = "no_terrain"
    elif mid == "poltergeist" and not defender.get("item"):
        out["condition_fail"] = "no_item"
    if mid == "expandingforce" and field and field.get("terrain") == "Psychic":
        out["expanding_force_boosted"] = True
    return out


def _defender_hp(calc: CalcSuccessResponse) -> int:
    stats = (calc.get("raw") or {}).get("stats") or {}
    defender = stats.get("defender") or {}
    return int(defender.get("hp") or 100)


def _attacker_spe(calc: CalcSuccessResponse) -> int:
    stats = (calc.get("raw") or {}).get("stats") or {}
    attacker = stats.get("attacker") or {}
    return int(attacker.get("spe") or 0)


def _effective_spe(spe: int, side: dict[str, object] | None) -> int:
    if side and side.get("isTailwind"):
        return spe * 2
    return spe


def _trick_room_active(field: FieldSpec | None) -> bool:
    return bool(field and field.get("isTrickRoom"))


def _a_moves_first(
    spe_a: int, spe_b: int, field: FieldSpec | None
) -> bool:
    a_side = (field or {}).get("attackerSide") or {}
    b_side = (field or {}).get("defenderSide") or {}
    eff_a = _effective_spe(spe_a, a_side)
    eff_b = _effective_spe(spe_b, b_side)
    if _trick_room_active(field):
        if eff_a != eff_b:
            return eff_a < eff_b
        return True
    if eff_a != eff_b:
        return eff_a > eff_b
    return True


def _simulate_exchange(
    a_best: _MoveProfile,
    b_best: _MoveProfile,
    spe_a: int,
    spe_b: int,
    a_hp: int,
    b_hp: int,
    field: FieldSpec | None,
) -> tuple[MatchupOutcome, int]:
    # ponytail: no reverse classify_matchup — fresh rematch resets HP and re-enters
    # turn-economy; in-sim must_recharge skip uses already-batched reverse calcs.
    a_remaining, b_remaining = a_hp, b_hp
    b_ko_turn: int | None = None
    a_ko_turn: int | None = None
    must_recharge = {"a": False, "b": False}
    hits = {"a": 0, "b": 0}

    for turn in range(1, 5):
        a_first = _a_moves_first(spe_a, spe_b, field)
        order = ("a", "b") if a_first else ("b", "a")
        for actor in order:
            if a_remaining <= 0 or b_remaining <= 0:
                break
            if must_recharge[actor]:
                must_recharge[actor] = False
                continue
            profile = a_best if actor == "a" else b_best
            if _charge_delayed(profile.move, field) and turn == 1:
                dmg = 0
            else:
                hits[actor] += 1
                target = b_remaining if actor == "a" else a_remaining
                dmg = _turn_damage(profile, target, hits[actor])
            if actor == "a":
                b_remaining -= dmg
                if b_remaining <= 0 and a_ko_turn is None:
                    a_ko_turn = turn
            else:
                a_remaining -= dmg
                if a_remaining <= 0 and b_ko_turn is None:
                    b_ko_turn = turn
            if dmg > 0 and to_id(profile.move) in _RECHARGE_MOVES:
                must_recharge[actor] = True

        if a_ko_turn is not None and (b_ko_turn is None or a_ko_turn < b_ko_turn):
            return "clean_kill", a_remaining
        if b_ko_turn is not None and (a_ko_turn is None or b_ko_turn < a_ko_turn):
            return "no_answer", a_remaining
        if a_ko_turn is not None and b_ko_turn is not None and a_ko_turn == b_ko_turn:
            return "no_answer", a_remaining

    if a_remaining > 0 and b_remaining > 0 and _is_intentional_non_ko(a_best, b_best, a_hp):
        return "intentional_non_ko_answer", a_remaining
    if a_remaining <= 0:
        return "no_answer", 0
    if b_remaining <= 0:
        return "clean_kill", a_remaining
    return "no_answer", a_remaining


def _turn_economy_note(
    a_best: _MoveProfile,
    b_best: _MoveProfile,
    outcome: MatchupOutcome,
    field: FieldSpec | None,
) -> TurnEconomyNote | None:
    if to_id(a_best.move) in _RECHARGE_MOVES:
        if a_best.turns_to_ko == 1 and a_best.ko_guaranteed:
            return "recharge_vulnerable_moot"
        if outcome == "no_answer":
            return "recharge_vulnerable_lost"
        return "recharge_vulnerable_won"
    if _charge_delayed(a_best.move, field) or _charge_delayed(b_best.move, field):
        return "charge_delayed"
    return None


def _turn_damage(profile: _MoveProfile, target_hp: int, turn: int) -> int:
    if profile.turns_to_ko == 1 and profile.ko_guaranteed and turn == 1:
        return target_hp
    if profile.turns_to_ko == turn and profile.ko_guaranteed:
        return target_hp
    if profile.max_damage <= 0:
        return 0
    if profile.turns_to_ko and profile.ko_guaranteed:
        return min(profile.max_damage, max(1, math.ceil(target_hp / profile.turns_to_ko)))
    return profile.max_damage


def _is_intentional_non_ko(
    a_best: _MoveProfile, b_best: _MoveProfile, a_max_hp: int
) -> bool:
    if a_best.turns_to_ko == 1 and a_best.ko_guaranteed:
        return False
    inbound = b_best.max_damage
    if a_max_hp <= 0:
        return False
    inbound_pct = inbound / a_max_hp * 100
    return inbound_pct < 15 and (a_best.turns_to_ko is None or a_best.turns_to_ko > 2)


def _severity_from_hp(hp_remaining: int, hp_max: int) -> Severity:
    if hp_max <= 0:
        return "toss-up"
    pct = hp_remaining / hp_max * 100
    if pct >= 50:
        return "decisive"
    if pct >= 20:
        return "costly"
    return "toss-up"


def _makes_contact(move: str) -> bool:
    return to_id(move) in _CONTACT_MOVES


def _contact_punish_applies(defender: PokemonSpecOptional, move: str) -> bool:
    if not _makes_contact(move):
        return False
    ability = to_id(defender.get("ability") or "")
    item = to_id(defender.get("item") or "")
    return ability in _CONTACT_PUNISH_HP_ABILITIES or item in _CONTACT_PUNISH_ITEMS


def _contact_punish_chip(defender: PokemonSpecOptional, attacker_max_hp: int) -> int:
    item = to_id(defender.get("item") or "")
    if item in _CONTACT_PUNISH_ITEMS:
        return max(1, attacker_max_hp // 6)
    return max(1, attacker_max_hp // 8)


def _multi_hit_assumed(
    attacker: PokemonSpecOptional, move: str, profile: _MoveProfile
) -> bool:
    move_id = to_id(move)
    if move_id not in _MULTI_HIT_MOVES:
        return False
    if profile.turns_to_ko != 1 or not profile.ko_guaranteed:
        return False
    ability = to_id(attacker.get("ability") or "")
    item = to_id(attacker.get("item") or "")
    if ability in _GUARANTEED_HIT_COUNT or item in _WIDE_LENS:
        return False
    return True


def _downgrade_for_multi_hit(severity: Severity, profile: _MoveProfile) -> Severity:
    if "guaranteed" in profile.ko_chance.lower() or "100%" in profile.ko_chance:
        if severity == "decisive":
            return "costly"
        return "toss-up"
    return severity


# --- Static expected-hit / accuracy helpers (query_counters; no calc) ---

_DIST_2_5 = ((2, 0.35), (3, 0.35), (4, 0.15), (5, 0.15))  # Gen5+; E=3.1
_FIXED_MULTI_HITS = {
    "surgingstrikes": 3.0,
    "doublehit": 2.0,
    "dragondarts": 2.0,
    "dualwingbeat": 2.0,
    "twinbeam": 2.0,
}
_MULTIACCURACY_HITS = {"populationbomb": 10, "tripleaxel": 3}
_NO_GUARD = "noguard"
_COMPOUND_EYES = "compoundeyes"
_HUSTLE = "hustle"
_HUSTLE_ACC_MULT = 0.8
_COMPOUND_EYES_ACC_MULT = 1.3


def effective_accuracy(
    base_accuracy: int | bool | None,
    ability: str | None,
    *,
    defender_ability: str | None = None,
    category: str | None = None,
) -> float:
    """Move accuracy in [0, 1] after static ability modifiers.

    No Guard (attacker or defender) → 1.0. Hustle ×0.8 on Physical only.
    Compound Eyes ×1.3. Coil / weather / items are out of scope (ADR-021b).
    """
    atk = to_id(ability or "")
    dfn = to_id(defender_ability or "")
    if atk == _NO_GUARD or dfn == _NO_GUARD:
        return 1.0
    if base_accuracy is True or base_accuracy is None:
        base = 1.0
    else:
        v = float(base_accuracy)
        base = v / 100.0 if v > 1.0 else v
    if atk == _HUSTLE and (category or "") == "Physical":
        base *= _HUSTLE_ACC_MULT
    if atk == _COMPOUND_EYES:
        base *= _COMPOUND_EYES_ACC_MULT
    return min(1.0, max(0.0, base))


def expected_hit_factor(
    move: str, ability: str | None, accuracy: float
) -> tuple[float, bool]:
    """Expected hit count (or accuracy-folded EV) for a move.

    Returns ``(factor, accuracy_already_folded)``. When the second value is True
    (multiaccuracy without Skill Link), the caller must not multiply by accuracy again.
    """
    mid = to_id(move)
    aid = to_id(ability or "")
    guaranteed = aid in _GUARANTEED_HIT_COUNT

    if mid in _FIXED_MULTI_HITS:
        return _FIXED_MULTI_HITS[mid], False

    if mid in _MULTIACCURACY_HITS:
        n = _MULTIACCURACY_HITS[mid]
        if guaranteed:
            # Skill Link: full n-hit sequence is certain — do not also × accuracy.
            return float(n), True
        # multiaccuracy: E[hits] = sum_{i=1}^{n} acc^i
        total = 0.0
        p = accuracy
        for _ in range(n):
            total += p
            p *= accuracy
        return total, True

    if mid in _MULTI_HIT_MOVES:
        if guaranteed:
            return 5.0, False
        return sum(h * p for h, p in _DIST_2_5), False

    return 1.0, False
