"""Cross-option build compare: Spe for all options; damage/KO vs ≤2 threat contexts."""

from __future__ import annotations

from typing import Any, Callable

from recommender.calc_client import (
    CalcClientError,
    CalcRequest,
    CalcSuccessResponse,
    PokemonSpecOptional,
    calculate_batch,
)
from recommender.ids import to_id
from recommender.state import (
    BuildConfirmationOption,
    BuildFieldOverrides,
    BuildOptionGroup,
    ProvisionalSlot,
    RecommenderState,
)
from recommender.usage_spreads import effective_spe

_MAX_THREAT_CONTEXTS = 2


def parse_ko_turns(ko_chance: str, calc: CalcSuccessResponse) -> tuple[int | None, bool]:
    """Public wrap of matchup KO-tier parsing."""
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


def _index_options(
    groups: tuple[BuildOptionGroup, ...],
) -> dict[str, BuildConfirmationOption]:
    out: dict[str, BuildConfirmationOption] = {}
    for group in groups:
        for opt in group.get("options") or ():
            out[str(opt["option_id"])] = opt
    return out


def _apply_overrides(
    provisional: ProvisionalSlot, overrides: BuildFieldOverrides
) -> dict[str, Any]:
    return {
        "species": provisional.species,
        "ability": overrides.get("ability", provisional.ability),
        "item": overrides.get("item", provisional.item),
        "moves": list(overrides.get("moves", provisional.moves)),
        "nature": overrides.get("nature", provisional.nature),
        "evs": dict(overrides.get("spread", provisional.spread_dict())),
    }


def _as_spec(build: dict[str, Any]) -> PokemonSpecOptional:
    spec: PokemonSpecOptional = {"species": str(build["species"])}
    if build.get("ability"):
        spec["ability"] = str(build["ability"])
    if build.get("item"):
        spec["item"] = str(build["item"])
    if build.get("nature"):
        spec["nature"] = str(build["nature"])
    if build.get("moves"):
        spec["moves"] = list(build["moves"])
    if build.get("evs"):
        spec["evs"] = dict(build["evs"])  # type: ignore[typeddict-item]
    return spec


def _threat_specs(state: RecommenderState) -> list[PokemonSpecOptional]:
    specs: list[PokemonSpecOptional] = []
    seen: set[str] = set()
    for row in state.get("coverage") or []:
        threat = getattr(row, "threat", None)
        if threat is None and isinstance(row, dict):
            threat = row.get("threat")
        if not isinstance(threat, dict):
            continue
        species = str(threat.get("species") or "")
        if not species or to_id(species) in seen:
            continue
        if not threat.get("moves"):
            continue
        seen.add(to_id(species))
        specs.append(threat)  # type: ignore[arg-type]
        if len(specs) >= _MAX_THREAT_CONTEXTS:
            return specs
    for finding in state.get("spofs") or []:
        lost = getattr(finding, "threats_lost", None)
        if lost is None and isinstance(finding, dict):
            lost = finding.get("threats_lost")
        for threat in lost or ():
            if not isinstance(threat, dict):
                continue
            species = str(threat.get("species") or "")
            if not species or to_id(species) in seen:
                continue
            if not threat.get("moves"):
                continue
            seen.add(to_id(species))
            specs.append(threat)  # type: ignore[arg-type]
            if len(specs) >= _MAX_THREAT_CONTEXTS:
                return specs
    return specs


def _pick_move(build: dict[str, Any]) -> str | None:
    moves = build.get("moves") or []
    for move in moves:
        mid = to_id(str(move))
        if mid and mid != "protect":
            return str(move)
    return str(moves[0]) if moves else None


def compare_build_options(
    provisional: ProvisionalSlot,
    *,
    option_ids: tuple[str, ...],
    groups: tuple[BuildOptionGroup, ...],
    state: RecommenderState,
    calculate_batch_fn: Callable[[list[CalcRequest]], list[Any]] | None = None,
) -> str:
    """Calc-backed analysis text for every requested option_id."""
    index = _index_options(groups)
    missing = [oid for oid in option_ids if oid not in index]
    if missing:
        return f"unknown option id(s): {', '.join(missing)}"
    if len(option_ids) < 2:
        return "compare requires at least two option ids"

    builds: list[tuple[str, dict[str, Any]]] = []
    for oid in option_ids:
        opt = index[oid]
        builds.append((oid, _apply_overrides(provisional, opt.get("overrides") or {})))

    lines: list[str] = ["Compare:"]
    for oid, build in builds:
        scarf = to_id(str(build.get("item") or "")) == "choicescarf"
        spe = effective_spe(
            str(build["species"]),
            dict(build["evs"]),
            str(build["nature"]),
            scarf=scarf,
        )
        label = index[oid].get("label") or oid
        lines.append(f"  {oid} ({label}): Spe {spe}")

    threats = _threat_specs(state)
    if not threats:
        lines.append("No threat context for damage/KO.")
        return "\n".join(lines)

    batch = calculate_batch_fn or calculate_batch
    for threat in threats:
        foe_name = str(threat.get("species") or "?")
        lines.append(f"vs {foe_name}:")
        reqs: list[CalcRequest] = []
        meta: list[tuple[str, str]] = []
        for oid, build in builds:
            move = _pick_move(build)
            if not move:
                lines.append(f"  {oid}: no damaging move")
                continue
            reqs.append(
                {
                    "attacker": _as_spec(build),
                    "defender": threat,
                    "move": move,
                }
            )
            meta.append((oid, move))
        if not reqs:
            continue
        try:
            results = batch(reqs)
        except CalcClientError:
            lines.append(f"  damage/KO unavailable (calc error) vs {foe_name}")
            continue
        for (oid, move), result in zip(meta, results, strict=False):
            if not isinstance(result, dict) or result.get("error"):
                lines.append(f"  {oid}: calc unavailable for {move}")
                continue
            success: CalcSuccessResponse = result  # type: ignore[assignment]
            dmg = success.get("damageRange")
            ko = str(success.get("koChance") or "")
            turns, guaranteed = parse_ko_turns(ko, success)
            tier = ""
            if turns is not None:
                tier = f" ({'guaranteed ' if guaranteed else ''}{turns}HKO)"
            lines.append(f"  {oid}: {move} dmg={dmg} ko={ko}{tier}")
    return "\n".join(lines)
