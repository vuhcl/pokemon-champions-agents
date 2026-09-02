"""Parse, stamp, and verify system factual claims for claim_correction."""

from __future__ import annotations

import re
from typing import Literal

from recommender.constraint_enforcement import (
    MechanicalSpec,
    matches_species,
    resolve_mechanical,
)
from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.species_resolve import resolve_species_label
from recommender.state import Constraint, ConstraintPayload, SystemClaim
from recommender.turn_intent import CLASSIFY_FAIL_USER_MSG

_POKEMON_TYPES = frozenset(
    {
        "normal",
        "fire",
        "water",
        "electric",
        "grass",
        "ice",
        "fighting",
        "poison",
        "ground",
        "flying",
        "psychic",
        "bug",
        "rock",
        "ghost",
        "dragon",
        "dark",
        "steel",
        "fairy",
    }
)

_TYPE_CLAIM_RES = (
    re.compile(
        r"(?P<species>[A-Za-z][A-Za-z0-9\-']*(?:\s+[A-Za-z][A-Za-z0-9\-']*)*?)"
        r"\s+(?:is|has|as)\s+(?:a\s+)?(?P<type>[A-Za-z]+)(?:-|\s)?type",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?P<species>[A-Za-z][A-Za-z0-9\-']*(?:\s+[A-Za-z][A-Za-z0-9\-']*)*?)"
        r".*?\b(?P<type>[A-Za-z]+)(?:-|\s)?type\b",
        re.IGNORECASE,
    ),
)

_TYPE_CONSTRAINT_RES = (
    re.compile(r"\b(?P<type>[a-zA-Z]+)\s+type\b", re.IGNORECASE),
    re.compile(r"\bmust\s+be\s+(?:a\s+)?(?P<type>[a-zA-Z]+)\b", re.IGNORECASE),
    re.compile(r"\btype\s*[:_]\s*(?P<type>[a-zA-Z]+)\b", re.IGNORECASE),
)

_NO_DUPLICATE_ITEMS_RE = re.compile(r"no\s+duplicate\s+items?", re.IGNORECASE)

_SPECIES_BAN_RES = (
    re.compile(r"^\s*(?:no|reject|don't\s+want|do\s+not\s+want)\s+", re.IGNORECASE),
)

_TYPE_NEGATION_RES = (
    re.compile(
        r"(?P<species>[A-Za-z][A-Za-z0-9\-']*(?:\s+[A-Za-z][A-Za-z0-9\-']*)*?)"
        r"\s+is\s+not\s+(?:a\s+)?(?P<type>[A-Za-z]+)(?:-|\s)?type",
        re.IGNORECASE,
    ),
    re.compile(
        r"not\s+(?:a\s+)?(?P<type>[A-Za-z]+)(?:-|\s)?type",
        re.IGNORECASE,
    ),
)

_SPECIES_CAPTURE = (
    r"(?P<species>[A-Za-z][A-Za-z0-9\-']*"
    r"(?:\s+[A-Za-z][A-Za-z0-9\-']*)*?)"
)

_ABILITY_CLAIM_PREFIX_RES = (
    re.compile(_SPECIES_CAPTURE + r"\s+has\s+(?:the\s+)?ability\s+", re.IGNORECASE),
    re.compile(_SPECIES_CAPTURE + r"'s\s+ability\s+is\s+", re.IGNORECASE),
    re.compile(
        _SPECIES_CAPTURE + r"\s+(?:with|using)\s+(?:the\s+)?ability\s+",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES_CAPTURE + r"\s+(?:with|using)\s+(?:the\s+)?",
        re.IGNORECASE,
    ),
    re.compile(_SPECIES_CAPTURE + r"\s+has\s+", re.IGNORECASE),
)

_ITEM_CLAIM_PREFIX_RES = (
    re.compile(_SPECIES_CAPTURE + r"'s\s+item\s+is\s+", re.IGNORECASE),
    re.compile(_SPECIES_CAPTURE + r"\s+holds?\s+", re.IGNORECASE),
    re.compile(_SPECIES_CAPTURE + r"\s+has\s+", re.IGNORECASE),
    re.compile(_SPECIES_CAPTURE + r"\s+(?:with|carrying)\s+", re.IGNORECASE),
)

_ABILITY_NEGATION_PREFIX_RES = (
    re.compile(
        _SPECIES_CAPTURE
        + r"\s+(?:doesn't|does not|don't|do not)\s+have\s+(?:the\s+)?ability\s+",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES_CAPTURE
        + r"\s+(?:doesn't|does not|don't|do not)\s+have\s+",
        re.IGNORECASE,
    ),
    re.compile(r"not\s+(?:the\s+)?ability\s+", re.IGNORECASE),
    re.compile(r"not\s+", re.IGNORECASE),
)

_ITEM_NEGATION_PREFIX_RES = (
    re.compile(
        _SPECIES_CAPTURE
        + r"\s+(?:doesn't|does not|don't|do not)\s+hold\s+",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES_CAPTURE
        + r"\s+(?:doesn't|does not|don't|do not)\s+have\s+",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES_CAPTURE + r"'s\s+item\s+is(?:n't| not)\s+",
        re.IGNORECASE,
    ),
    re.compile(r"not\s+", re.IGNORECASE),
)

NON_CLAIM_MESSAGES: frozenset[str] = frozenset(
    {
        CLASSIFY_FAIL_USER_MSG,
        "That action isn't available here.",
        "That sounds like two requests in one — an edit and a comparison. Which would you like first?",
        "That sounds like two requests in one — an edit and a selection. Which would you like first?",
        "That took too long to process — please try again, ideally with a shorter or simpler message.",
    }
)


def _normalize_type(raw: str) -> str | None:
    cleaned = raw.strip().title()
    if cleaned.lower() in _POKEMON_TYPES:
        return cleaned
    return None


def _resolve_species(raw: str, snap: dict) -> str | None:
    hit = resolve_species_label(raw.strip(), snap)
    return hit.name if hit else None


def _ability_candidates(snap: dict) -> dict[str, str]:
    candidates: dict[str, str] = {}
    for sp in (snap.get("species") or {}).values():
        for ability in (sp.get("abilities") or {}).values():
            if isinstance(ability, str):
                candidates[to_id(ability)] = ability
    return candidates


def _item_candidates(snap: dict) -> dict[str, str]:
    items = snap.get("items") or {}
    return {
        str(item.get("id") or ""): str(item.get("name") or "")
        for item in items.values()
    }


def _claim_with_species_prefix(
    text: str,
    prefixes: tuple[re.Pattern[str], ...],
    value: str,
) -> str | None:
    pos = text.lower().find(value.lower())
    if pos < 0:
        return None
    for pattern in prefixes:
        match = pattern.search(text[:pos])
        if match is not None:
            return match.group("species")
    return None


def _species_context_ok(
    *,
    match: re.Match[str] | None,
    claim: SystemClaim,
    text: str,
    snap: dict,
) -> bool:
    expected_species = to_id(claim["subject_species"])
    if match is not None and "species" in match.groupdict() and match.group("species"):
        species = _resolve_species(match.group("species"), snap)
        return species is not None and to_id(species) == expected_species
    return expected_species in to_id(text)


def _negated_value_matches(expected: str, extracted: str | None) -> bool:
    return extracted is not None and extracted.casefold() == expected.casefold()


def _try_parse_ability_claim(text: str, snap: dict) -> dict[str, object] | None:
    from recommender.turn_intent import _find_known_value_in_text

    ability = _find_known_value_in_text(text, _ability_candidates(snap))
    if ability is None:
        return None
    raw_species = _claim_with_species_prefix(text, _ABILITY_CLAIM_PREFIX_RES, ability)
    if raw_species is None:
        return None
    species = _resolve_species(raw_species, snap)
    if species is None:
        return None
    draft = Constraint(
        type="hard",
        predicate=f"ability:{ability}",
        source_turn=0,
        scope="per_slot",
        groundedness="mechanically-checkable",
    )
    spec = resolve_mechanical(
        draft,
        mechanical_kind="ability",
        mechanical_value=ability,
    )
    if spec is None:
        return None
    return {
        "kind": "ability",
        "subject_species": species,
        "asserted_value": spec.value,
        "verifiable": True,
    }


def _try_parse_item_claim(text: str, snap: dict) -> dict[str, object] | None:
    from recommender.turn_intent import _find_known_value_in_text

    item = _find_known_value_in_text(text, _item_candidates(snap))
    if item is None:
        return None
    raw_species = _claim_with_species_prefix(text, _ITEM_CLAIM_PREFIX_RES, item)
    if raw_species is None:
        return None
    species = _resolve_species(raw_species, snap)
    if species is None:
        return None
    draft = Constraint(
        type="hard",
        predicate=item,
        source_turn=0,
        scope="per_slot",
        groundedness="mechanically-checkable",
    )
    spec = resolve_mechanical(
        draft,
        mechanical_kind="item",
        mechanical_value=item,
    )
    if spec is None:
        return None
    return {
        "kind": "item",
        "subject_species": species,
        "asserted_value": spec.value,
        "verifiable": True,
    }


def _negation_matches_ability_claim(
    text: str,
    claim: SystemClaim,
    snap: dict,
) -> bool:
    from recommender.turn_intent import _find_known_value_in_text

    ability = _find_known_value_in_text(text, _ability_candidates(snap))
    if not _negated_value_matches(claim["asserted_value"], ability):
        return False
    pos = text.lower().find(ability.lower()) if ability else -1
    prefix_text = text[:pos] if pos >= 0 else text
    for pattern in _ABILITY_NEGATION_PREFIX_RES:
        match = pattern.search(prefix_text) or pattern.search(text)
        if match is None:
            continue
        if _species_context_ok(match=match, claim=claim, text=text, snap=snap):
            return True
    return False


def _negation_matches_item_claim(
    text: str,
    claim: SystemClaim,
    snap: dict,
) -> bool:
    from recommender.turn_intent import _find_known_value_in_text

    item = _find_known_value_in_text(text, _item_candidates(snap))
    if not _negated_value_matches(claim["asserted_value"], item):
        return False
    pos = text.lower().find(item.lower()) if item else -1
    prefix_text = text[:pos] if pos >= 0 else text
    for pattern in _ITEM_NEGATION_PREFIX_RES:
        match = pattern.search(prefix_text) or pattern.search(text)
        if match is None:
            continue
        if _species_context_ok(match=match, claim=claim, text=text, snap=snap):
            return True
    return False


def _mechanical_payload_from_spec(
    spec: MechanicalSpec,
    *,
    constraint_type: Literal["hard", "soft"] = "hard",
) -> ConstraintPayload:
    payload: ConstraintPayload = {
        "type": constraint_type,
        "predicate": spec.label,
        "scope": spec.scope,
        "groundedness": "mechanically-checkable",
    }
    if spec.kind != "no_duplicate_items":
        payload["mechanical_kind"] = spec.kind  # type: ignore[typeddict-item]
        payload["mechanical_value"] = spec.value
    else:
        payload["mechanical_kind"] = "no_duplicate_items"
    return payload


def try_parse_verifiable_claim_from_message(
    message: str,
) -> dict[str, object] | None:
    """Return partial SystemClaim fields or None (fail-closed)."""
    text = message.strip()
    if not text or text in NON_CLAIM_MESSAGES:
        return None

    snap = load_snapshot()
    for pattern in _TYPE_CLAIM_RES:
        match = pattern.search(text)
        if match is None:
            continue
        species = _resolve_species(match.group("species"), snap)
        normalized = _normalize_type(match.group("type"))
        if species is None or normalized is None:
            continue
        draft = Constraint(
            type="hard",
            predicate=f"type:{normalized.lower()}",
            source_turn=0,
            scope="per_slot",
            groundedness="mechanically-checkable",
        )
        spec = resolve_mechanical(
            draft,
            mechanical_kind="type",
            mechanical_value=normalized,
        )
        if spec is None:
            continue
        return {
            "kind": "type",
            "subject_species": species,
            "asserted_value": normalized,
            "verifiable": True,
        }

    parsed = _try_parse_ability_claim(text, snap)
    if parsed is not None:
        return parsed

    return _try_parse_item_claim(text, snap)


def try_extract_reattempt_constraint(user_text: str) -> ConstraintPayload | None:
    """Deterministic constraint recovery from the originating user turn."""
    text = user_text.strip()
    if not text:
        return None

    if _NO_DUPLICATE_ITEMS_RE.search(text):
        draft = Constraint(
            type="hard",
            predicate="no duplicate items",
            source_turn=0,
            scope="team_wide",
            groundedness="mechanically-checkable",
        )
        spec = resolve_mechanical(draft)
        if spec is not None:
            return _mechanical_payload_from_spec(spec)

    for pattern in _TYPE_CONSTRAINT_RES:
        match = pattern.search(text)
        if match is None:
            continue
        normalized = _normalize_type(match.group("type"))
        if normalized is None:
            continue
        draft = Constraint(
            type="hard",
            predicate=f"{normalized} type",
            source_turn=0,
            scope="per_slot",
            groundedness="mechanically-checkable",
        )
        spec = resolve_mechanical(
            draft,
            mechanical_kind="type",
            mechanical_value=normalized,
        )
        if spec is not None:
            return _mechanical_payload_from_spec(spec)

    from recommender.turn_intent import extract_ability_name_target, extract_item_name_target

    ability = extract_ability_name_target(text)
    if ability is not None:
        draft = Constraint(
            type="hard",
            predicate=f"ability:{ability}",
            source_turn=0,
            scope="per_slot",
            groundedness="mechanically-checkable",
        )
        spec = resolve_mechanical(
            draft,
            mechanical_kind="ability",
            mechanical_value=ability,
        )
        if spec is not None:
            return _mechanical_payload_from_spec(spec)

    item = extract_item_name_target(text)
    if item is not None:
        draft = Constraint(
            type="hard",
            predicate=item,
            source_turn=0,
            scope="per_slot",
            groundedness="mechanically-checkable",
        )
        spec = resolve_mechanical(
            draft,
            mechanical_kind="item",
            mechanical_value=item,
        )
        if spec is not None:
            return _mechanical_payload_from_spec(spec)

    return None


def mechanical_spec_from_claim(claim: SystemClaim) -> MechanicalSpec:
    kind = claim["kind"]
    if kind == "other":
        raise ValueError("unverifiable claim kind")
    draft = Constraint(
        type="hard",
        predicate=f"{kind}:{claim['asserted_value']}",
        source_turn=0,
        scope="per_slot",
        groundedness="mechanically-checkable",
    )
    spec = resolve_mechanical(
        draft,
        mechanical_kind=kind,  # type: ignore[arg-type]
        mechanical_value=claim["asserted_value"],
    )
    if spec is None:
        raise ValueError("claim does not resolve to mechanical spec")
    return spec


def claim_is_true_against_snapshot(claim: SystemClaim) -> bool:
    if not claim.get("verifiable") or claim.get("kind") == "other":
        return False
    spec = mechanical_spec_from_claim(claim)
    return matches_species(
        claim["subject_species"],
        spec,
        snap=load_snapshot(),
        team_draft=[],
    )


def format_snapshot_value(claim: SystemClaim, snap: dict | None = None) -> str:
    snap = snap or load_snapshot()
    if claim["kind"] == "type":
        from recommender.constraint_enforcement import _species_types

        types = _species_types(snap, claim["subject_species"])
        return "/".join(types) if types else "unknown"
    if claim["kind"] == "ability":
        from recommender.legality import _species_entry

        entry = _species_entry(snap, claim["subject_species"])
        abilities = [
            v for v in (entry.get("abilities") or {}).values() if isinstance(v, str)
        ] if entry else []
        return "/".join(abilities) if abilities else "unknown"
    # ponytail: no species-canonical item in snapshot; legality-only verification
    return claim["asserted_value"]


def negation_matches_claim(user_text: str, claim: SystemClaim) -> bool:
    if not claim.get("verifiable") or claim.get("kind") == "other":
        return False
    text = user_text.strip()
    if not text:
        return False
    for pattern in _SPECIES_BAN_RES:
        if pattern.search(text):
            return False

    snap = load_snapshot()
    kind = claim["kind"]

    if kind == "type":
        expected_type = claim["asserted_value"].casefold()
        expected_species = to_id(claim["subject_species"])
        for pattern in _TYPE_NEGATION_RES:
            match = pattern.search(text)
            if match is None:
                continue
            negated = _normalize_type(match.group("type"))
            if negated is None or negated.casefold() != expected_type:
                continue
            if "species" in match.groupdict() and match.group("species"):
                species = _resolve_species(match.group("species"), snap)
                if species is None or to_id(species) != expected_species:
                    continue
            elif expected_species not in to_id(text):
                continue
            return True
        return False

    if kind == "ability":
        return _negation_matches_ability_claim(text, claim, snap)

    if kind == "item":
        return _negation_matches_item_claim(text, claim, snap)

    return False


def serialize_last_system_claim(claim: SystemClaim | None) -> str:
    if claim is None:
        return ""
    excerpt = claim.get("display_excerpt", "").replace('"', "'")
    return (
        f"turn={claim.get('turn')} kind={claim.get('kind')} "
        f"subject={claim.get('subject_species')} asserted={claim.get('asserted_value')} "
        f'excerpt="{excerpt[:80]}"'
    )


def stamp_system_claim(
    *,
    message: str,
    originating_user_text: str,
    turn: int,
) -> SystemClaim | None:
    parsed = try_parse_verifiable_claim_from_message(message)
    if parsed is None:
        return None
    claim: SystemClaim = {
        "turn": turn,
        "kind": parsed["kind"],  # type: ignore[typeddict-item]
        "subject_species": str(parsed["subject_species"]),
        "asserted_value": str(parsed["asserted_value"]),
        "source": "pending_response_message",
        "display_excerpt": message.strip()[:120],
        "verifiable": bool(parsed["verifiable"]),
        "originating_user_text": originating_user_text,
    }
    reattempt = try_extract_reattempt_constraint(originating_user_text)
    if reattempt is not None:
        claim["reattempt_constraint"] = reattempt
    return claim


def build_deterministic_claim_correction(
    user_text: str,
    claim: SystemClaim,
) -> dict[str, object]:
    return {
        "turn_intent": "claim_correction",
        "turn_payload": {
            "subject_species": claim["subject_species"],
            "disputed_kind": claim["kind"],
            "disputed_value": claim["asserted_value"],
            "user_text": user_text.strip(),
            "targets_claim_turn": claim["turn"],
        },
    }
