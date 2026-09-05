#!/usr/bin/env python3
"""Independent species-fact oracle for pending_response clarification eval.

Loads data/legality/champions.v1.json directly. Does NOT import
try_parse_verifiable_claim_from_message / claim_is_true_against_snapshot /
rewrite_pending_response_message / load_snapshot.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT / "data" / "legality" / "champions.v1.json"

Verdict = Literal["TRUE", "FALSE", "unverifiable_shape"]
ClaimKind = Literal["type", "ability"]

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

_SPECIES = (
    r"(?P<species>[A-Za-z][A-Za-z0-9\-']*(?:\s+[A-Za-z][A-Za-z0-9\-']*)*?)"
)
# Allow trailing slash so "Bug/" is captured as incomplete (unverifiable_shape).
_TYPE_PHRASE = r"(?P<types>[A-Za-z]+(?:/[A-Za-z]*)*)"

# Positive type assertions only (negation spans are masked first).
_TYPE_RES = (
    re.compile(
        _SPECIES
        + r"\s+(?:is|has|as)\s+(?:a\s+)?"
        + _TYPE_PHRASE
        + r"(?:-|\s)?type\b",
        re.IGNORECASE,
    ),
    # Slash typing without the word "type": "Hatterene is Psychic/Fairy"
    re.compile(
        _SPECIES + r"\s+(?:is|as)\s+" + _TYPE_PHRASE + r"\b",
        re.IGNORECASE,
    ),
)

_ABILITY_RES = (
    re.compile(
        _SPECIES + r"'s\s+ability\s+is\s+(?P<ability>[A-Za-z][A-Za-z0-9\-']*)",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES
        + r"\s+has\s+(?:the\s+)?ability\s+(?P<ability>[A-Za-z][A-Za-z0-9\-']*)",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES
        + r"\s+(?:with|using)\s+(?:the\s+)?ability\s+(?P<ability>[A-Za-z][A-Za-z0-9\-']*)",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES + r"\s+has\s+(?P<ability>[A-Za-z][A-Za-z0-9\-']*)\b",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES + r"\s+with\s+(?P<ability>[A-Za-z][A-Za-z0-9\-']*)\b",
        re.IGNORECASE,
    ),
)

# Mask these spans so "not Grass type" is not extracted as a claim.
_NEGATION_SPAN_RE = re.compile(
    r"(?:is\s+not|isn't|aren't|doesn't\s+have|does\s+not\s+have|"
    r"don't\s+have|do\s+not\s+have|not\s+(?:a\s+)?(?:the\s+)?)"
    r".{0,40}?(?:type|ability)\b"
    r"|"
    r"\bnot\s+(?:a\s+)?[A-Za-z]+(?:/[A-Za-z]+)*(?:-|\s)?type\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Claim:
    kind: ClaimKind
    species: str | None
    asserted_value: str
    verdict: Verdict
    span: tuple[int, int]
    display: str


def to_id(label: str) -> str:
    return re.sub(r"[^a-z0-9]", "", label.casefold())


def load_species_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    species = raw.get("species") or {}
    aliases = raw.get("species_aliases") or {}
    by_id: dict[str, dict] = {}
    for key, entry in species.items():
        if not isinstance(entry, dict):
            continue
        sid = str(entry.get("id") or key)
        by_id[to_id(sid)] = entry
        name = entry.get("name")
        if isinstance(name, str):
            by_id[to_id(name)] = entry
    for alias, target in aliases.items():
        tid = to_id(str(target))
        if tid in by_id:
            by_id[to_id(str(alias))] = by_id[tid]
    return by_id


def resolve_species(raw: str, by_id: dict[str, dict]) -> dict | None:
    cleaned = raw.strip()
    # Strip leading conjunctions from list prose: "and Whimsicott"
    cleaned = re.sub(
        r"^(?:and|or|plus|,)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    return by_id.get(to_id(cleaned))


def normalize_types(phrase: str) -> list[str] | None:
    parts = [p.strip() for p in phrase.split("/") if p.strip()]
    if not parts:
        return None
    # Incomplete slash e.g. "Bug/" → trailing empty already dropped; bare "Bug/"
    # arrives as phrase "Bug/" with split giving ["Bug", ""] → filtered to ["Bug"].
    # Detect incomplete via trailing/leading slash on the raw phrase.
    if phrase.strip().startswith("/") or phrase.strip().endswith("/"):
        return None
    out: list[str] = []
    for part in parts:
        title = part.title()
        if title.lower() not in _POKEMON_TYPES:
            return None
        out.append(title)
    return out


def _ability_index(by_id: dict[str, dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in by_id.values():
        for ab in (entry.get("abilities") or {}).values():
            if isinstance(ab, str):
                out[to_id(ab)] = ab
    return out


def _mask_negations(text: str) -> str:
    chars = list(text)

    def _blank(m: re.Match[str]) -> str:
        return " " * (m.end() - m.start())

    return _NEGATION_SPAN_RE.sub(_blank, text)


def _verdict_type(entry: dict | None, asserted: list[str]) -> Verdict:
    if entry is None:
        return "unverifiable_shape"
    snap_types = [str(t) for t in (entry.get("types") or []) if isinstance(t, str)]
    snap_set = {t.title() for t in snap_types}
    assert_set = {t.title() for t in asserted}
    if len(asserted) >= 2:
        return "TRUE" if assert_set == snap_set else "FALSE"
    # Single type: membership
    return "TRUE" if assert_set and assert_set.issubset(snap_set) else "FALSE"


def _verdict_ability(entry: dict | None, asserted: str) -> Verdict:
    if entry is None:
        return "unverifiable_shape"
    abilities = [
        str(v)
        for v in (entry.get("abilities") or {}).values()
        if isinstance(v, str)
    ]
    want = to_id(asserted)
    return "TRUE" if any(to_id(a) == want for a in abilities) else "FALSE"


def parse_claims(message: str, by_id: dict[str, dict] | None = None) -> list[Claim]:
    """Return all non-overlapping positive type/ability claims in message."""
    text = message.strip()
    if not text:
        return []
    by_id = by_id or load_species_snapshot()
    ab_index = _ability_index(by_id)
    masked = _mask_negations(text)

    candidates: list[Claim] = []

    for pattern in _TYPE_RES:
        for match in pattern.finditer(masked):
            # Skip if the match sits entirely in blanked (negated) region of masked
            # vs original — blanked chars are spaces, so species/types still need content.
            if not match.group("species").strip() or not match.group("types").strip():
                continue
            raw_types = match.group("types").strip()
            species_raw = match.group("species").strip()
            entry = resolve_species(species_raw, by_id)
            types = normalize_types(raw_types)
            if types is None:
                if raw_types.startswith("/") or raw_types.endswith("/"):
                    verdict: Verdict = "unverifiable_shape"
                    asserted = raw_types
                else:
                    continue
            else:
                asserted = "/".join(types)
                verdict = (
                    "unverifiable_shape"
                    if entry is None
                    else _verdict_type(entry, types)
                )
            name = str(entry["name"]) if entry else None
            candidates.append(
                Claim(
                    kind="type",
                    species=name,
                    asserted_value=asserted,
                    verdict=verdict,
                    span=(match.start(), match.end()),
                    display=text[match.start() : match.end()],
                )
            )

    for pattern in _ABILITY_RES:
        for match in pattern.finditer(masked):
            species_raw = match.group("species").strip()
            ability_raw = match.group("ability").strip()
            if not species_raw or not ability_raw:
                continue
            # Reject ability tokens that are pokemon types (e.g. "has Electric")
            if ability_raw.title().lower() in _POKEMON_TYPES:
                continue
            canon = ab_index.get(to_id(ability_raw))
            entry = resolve_species(species_raw, by_id)
            if canon is None:
                # Unknown ability name with resolved species → FALSE (asserted something
                # that isn't an ability in the snapshot pool) only if it looks like a
                # multi-word ability miss; single unknown → unverifiable_shape
                if entry is None:
                    continue
                verdict = "unverifiable_shape"
                asserted = ability_raw
            else:
                asserted = canon
                verdict = _verdict_ability(entry, canon)
            name = str(entry["name"]) if entry else None
            if entry is None:
                verdict = "unverifiable_shape"
            candidates.append(
                Claim(
                    kind="ability",
                    species=name,
                    asserted_value=asserted,
                    verdict=verdict,
                    span=(match.start(), match.end()),
                    display=text[match.start() : match.end()],
                )
            )

    # Prefer longer spans; greedily keep non-overlapping
    candidates.sort(key=lambda c: (-(c.span[1] - c.span[0]), c.span[0]))
    kept: list[Claim] = []
    used: list[tuple[int, int]] = []

    def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
        return not (a[1] <= b[0] or b[1] <= a[0])

    for claim in candidates:
        if any(overlaps(claim.span, u) for u in used):
            continue
        kept.append(claim)
        used.append(claim.span)
    kept.sort(key=lambda c: c.span[0])
    return kept


def _assert_self_check() -> None:
    by_id = load_species_snapshot()

    def types_of(msg: str) -> list[Claim]:
        return parse_claims(msg, by_id)

    def one(msg: str) -> Claim:
        claims = types_of(msg)
        assert len(claims) == 1, (msg, claims)
        return claims[0]

    c = one("Heliolisk is Electric type")
    assert c.verdict == "TRUE" and c.asserted_value == "Electric", c

    c = one("Heliolisk is Grass type")
    assert c.verdict == "FALSE" and c.asserted_value == "Grass", c

    c = one("Heliolisk is Electric/Water type")
    assert c.verdict == "FALSE" and c.asserted_value == "Electric/Water", c

    c = one("Heliolisk is Electric/Normal type")
    assert c.verdict == "TRUE" and c.asserted_value == "Electric/Normal", c

    c = one("Ariados is Bug/Poison type")
    assert c.verdict == "TRUE" and c.asserted_value == "Bug/Poison", c
    assert set(c.asserted_value.split("/")) == {"Bug", "Poison"}

    c = one("Ariados is Bug type")
    assert c.verdict == "TRUE" and c.asserted_value == "Bug", c

    c = one("Corviknight is Flying/Steel type")
    assert c.verdict == "TRUE", c

    c = one("Corviknight is Flying/Dragon type")
    assert c.verdict == "FALSE", c

    c = one("Ariados is Bug/ type")
    assert c.verdict == "unverifiable_shape", c

    dual = types_of(
        "Heliolisk is Electric/Water type, not Grass type. "
        "Would you like me to filter for grass-type Pokémon?"
    )
    assert len(dual) == 1, dual
    assert dual[0].asserted_value == "Electric/Water" and dual[0].verdict == "FALSE"

    multi = types_of(
        "Each option's typing is as follows: Heliolisk is Grass, "
        "Abomasnow is Ice, and Whimsicott is Fairy."
    )
    assert len(multi) == 3, multi
    by_sp = {c.species: c for c in multi}
    assert by_sp["Heliolisk"].verdict == "FALSE"
    assert by_sp["Abomasnow"].verdict == "TRUE"
    assert by_sp["Whimsicott"].verdict == "TRUE"

    print("species_fact_oracle self-check OK")


if __name__ == "__main__":
    _assert_self_check()
