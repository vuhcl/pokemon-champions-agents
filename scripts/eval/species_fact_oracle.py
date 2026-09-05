#!/usr/bin/env python3
"""Independent species-fact oracle for pending_response clarification eval.

Loads data/legality/champions.v1.json directly. Does NOT import
try_parse_verifiable_claim_from_message / claim_is_true_against_snapshot /
rewrite_pending_response_message / load_snapshot.

Coverage (scored shapes)
------------------------
Common *direct* species type/ability assertions and simple list/glossary forms:

- ``{Species} is/has/as [a/an] {type}[-]type [Pokémon]``
- ``{Species} is {Type}/{Type}`` (slash typing without the word ``type``)
- Separator lists: ``{Species} -|–|—|: {type|ability}`` (optional ``type`` word)
- Parenthetical: ``{Species} ({type|ability})``
- Possessive typing: ``{Species}'s type/typing is {value}``
- Inverse adjectival: ``[a/an] {type}-type {Species}``
- Numbered/bullet prefixes on any of the above (``1. …``, ``- …``)
- Multi-claim extraction per message; negation-span skipping

Ability values in separator/paren forms use longest-match against the snapshot
ability inventory (multi-word names like Dry Skin / Solar Power).

Out of scope
------------
Not a general NLP fact extractor. Does **not** score entailment/inference
chains (e.g. "since it learns Solar Beam it must not be Dark-type"), bare
questions without an assertion, comparative-only prose, or values that are
neither a known type phrase nor a known ability. An after-run of "zero FALSE"
means zero FALSE among *scored shapes*, not that every possible false claim
in free text was caught.
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
_SEP = r"(?:-|–|—|:)"
# Value after separator / inside parens (type phrase or ability words).
_VALUE = r"(?P<value>[A-Za-z][A-Za-z0-9\-']*(?:\s+[A-Za-z][A-Za-z0-9\-']*)*(?:/[A-Za-z][A-Za-z0-9\-']*)*)"

# Positive type assertions only (negation spans are masked first).
# Possessive before bare "is {type}" so "Heliolisk's typing is Electric" does
# not resolve species as "Heliolisk's typing".
_TYPE_RES = (
    # Possessive: "Heliolisk's typing is Electric/Normal"
    re.compile(
        _SPECIES
        + r"'s\s+(?:type|typing)\s+is\s+"
        + _TYPE_PHRASE
        + r"(?:-|\s)?type?\b",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES + r"'s\s+(?:type|typing)\s+is\s+" + _TYPE_PHRASE + r"\b",
        re.IGNORECASE,
    ),
    # "Heliolisk is an Electric-type Pokémon" / "is Electric type"
    re.compile(
        _SPECIES
        + r"\s+(?:is|has|as)\s+(?:an?\s+)?"
        + _TYPE_PHRASE
        + r"(?:-|\s)?type(?:\s+pok[eé]mon)?\b",
        re.IGNORECASE,
    ),
    # Slash typing without the word "type": "Hatterene is Psychic/Fairy"
    re.compile(
        _SPECIES + r"\s+(?:is|as)\s+" + _TYPE_PHRASE + r"\b",
        re.IGNORECASE,
    ),
    # Inverse: "Electric-type Heliolisk" / "an Electric-type Heliolisk"
    re.compile(
        r"(?:(?P<a_an>an?)\s+)?"
        + _TYPE_PHRASE
        + r"(?:-|\s)?type\s+"
        + _SPECIES
        + r"\b",
        re.IGNORECASE,
    ),
)

# Separator / paren forms — disambiguated to type or ability after match.
_SEP_RES = (
    re.compile(
        _SPECIES
        + r"\s*"
        + _SEP
        + r"\s*"
        + _VALUE
        + r"(?:(?:-|\s)?type)?\b",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES + r"\s*\(\s*" + _VALUE + r"(?:(?:-|\s)?type)?\s*\)",
        re.IGNORECASE,
    ),
)

_ABILITY_PREFIX_RES = (
    re.compile(
        _SPECIES + r"'s\s+ability\s+is\s+(?P<ability>.+?)(?=\s*[.,;!?]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES
        + r"\s+has\s+(?:the\s+)?ability\s+(?P<ability>.+?)(?=\s*[.,;!?]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES
        + r"\s+(?:with|using)\s+(?:the\s+)?ability\s+(?P<ability>.+?)(?=\s*[.,;!?]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES + r"\s+has\s+(?P<ability>.+?)(?=\s*[.,;!?]|$)",
        re.IGNORECASE,
    ),
    re.compile(
        _SPECIES + r"\s+with\s+(?P<ability>.+?)(?=\s*[.,;!?]|$)",
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
    cleaned = re.sub(
        r"^(?:and|or|plus|,)\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()
    # Numbered / bullet list prefixes: "1. Heliolisk", "- Abomasnow"
    cleaned = re.sub(r"^\d+\.\s*", "", cleaned).strip()
    cleaned = re.sub(r"^[-*•]\s*", "", cleaned).strip()
    cleaned = cleaned.strip(".,;:!?")
    return by_id.get(to_id(cleaned))


def normalize_types(phrase: str) -> list[str] | None:
    parts = [p.strip() for p in phrase.split("/") if p.strip()]
    if not parts:
        return None
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


def _longest_ability_match(raw: str, ab_index: dict[str, str]) -> str | None:
    """Longest prefix of raw that matches a known ability (multi-word OK)."""
    text = raw.strip()
    if not text:
        return None
    # Prefer exact full-string match, then longest word-prefix.
    words = text.split()
    best: str | None = None
    best_len = 0
    for n in range(len(words), 0, -1):
        cand = " ".join(words[:n])
        hit = ab_index.get(to_id(cand))
        if hit is not None and len(cand) >= best_len:
            best = hit
            best_len = len(cand)
            break
    return best


def _mask_negations(text: str) -> str:
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


def _append_type_claim(
    candidates: list[Claim],
    *,
    text: str,
    span: tuple[int, int],
    species_raw: str,
    raw_types: str,
    by_id: dict[str, dict],
) -> None:
    entry = resolve_species(species_raw, by_id)
    types = normalize_types(raw_types)
    if types is None:
        if raw_types.startswith("/") or raw_types.endswith("/"):
            verdict: Verdict = "unverifiable_shape"
            asserted = raw_types
        else:
            return
    else:
        asserted = "/".join(types)
        verdict = (
            "unverifiable_shape" if entry is None else _verdict_type(entry, types)
        )
    name = str(entry["name"]) if entry else None
    candidates.append(
        Claim(
            kind="type",
            species=name,
            asserted_value=asserted,
            verdict=verdict,
            span=span,
            display=text[span[0] : span[1]],
        )
    )


def _append_ability_claim(
    candidates: list[Claim],
    *,
    text: str,
    span: tuple[int, int],
    species_raw: str,
    ability_raw: str,
    by_id: dict[str, dict],
    ab_index: dict[str, str],
) -> None:
    species_raw = species_raw.strip()
    ability_raw = ability_raw.strip().rstrip(".,;:!?")
    if not species_raw or not ability_raw:
        return
    # Reject pure type phrases mistaken for abilities
    if normalize_types(ability_raw) is not None:
        return
    canon = _longest_ability_match(ability_raw, ab_index)
    entry = resolve_species(species_raw, by_id)
    if canon is None:
        if entry is None:
            return
        verdict: Verdict = "unverifiable_shape"
        asserted = ability_raw
        name = str(entry["name"])
    else:
        asserted = canon
        name = str(entry["name"]) if entry else None
        verdict = (
            "unverifiable_shape"
            if entry is None
            else _verdict_ability(entry, canon)
        )
    candidates.append(
        Claim(
            kind="ability",
            species=name,
            asserted_value=asserted,
            verdict=verdict,
            span=span,
            display=text[span[0] : span[1]],
        )
    )


def _strip_trailing_type_word(value: str) -> str:
    return re.sub(r"(?:-|\s)?types?\s*$", "", value.strip(), flags=re.IGNORECASE).strip()


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
            if not match.group("species").strip() or not match.group("types").strip():
                continue
            _append_type_claim(
                candidates,
                text=text,
                span=(match.start(), match.end()),
                species_raw=match.group("species"),
                raw_types=match.group("types").strip(),
                by_id=by_id,
            )

    for pattern in _SEP_RES:
        for match in pattern.finditer(masked):
            species_raw = match.group("species").strip()
            value = _strip_trailing_type_word(match.group("value"))
            if not species_raw or not value:
                continue
            types = normalize_types(value)
            if types is not None or value.startswith("/") or value.endswith("/"):
                _append_type_claim(
                    candidates,
                    text=text,
                    span=(match.start(), match.end()),
                    species_raw=species_raw,
                    raw_types=value,
                    by_id=by_id,
                )
                continue
            ability = _longest_ability_match(value, ab_index)
            if ability is not None:
                _append_ability_claim(
                    candidates,
                    text=text,
                    span=(match.start(), match.end()),
                    species_raw=species_raw,
                    ability_raw=value,
                    by_id=by_id,
                    ab_index=ab_index,
                )
            # else skip (neither type nor known ability)

    for pattern in _ABILITY_PREFIX_RES:
        for match in pattern.finditer(masked):
            _append_ability_claim(
                candidates,
                text=text,
                span=(match.start(), match.end()),
                species_raw=match.group("species"),
                ability_raw=match.group("ability"),
                by_id=by_id,
                ab_index=ab_index,
            )

    # Prefer longer spans, then resolved species over unverifiable_shape.
    candidates.sort(
        key=lambda c: (
            -(c.span[1] - c.span[0]),
            0 if c.species is not None else 1,
            c.span[0],
        )
    )
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

    # --- existing is / slash fixtures ---
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

    # --- separator family (dash / em-dash / colon) ---
    c = one("Heliolisk - Electric type")
    assert c.verdict == "TRUE", c
    c = one("Heliolisk - Grass type")
    assert c.verdict == "FALSE", c
    c = one("Ariados - Bug/Poison")
    assert c.verdict == "TRUE", c
    c = one("Corviknight — Flying/Dragon")
    assert c.verdict == "FALSE", c
    c = one("Heliolisk: Electric/Normal")
    assert c.verdict == "TRUE", c

    # --- parenthetical ---
    c = one("Heliolisk (Electric)")
    assert c.verdict == "TRUE", c
    c = one("Heliolisk (Grass)")
    assert c.verdict == "FALSE", c
    c = one("Ariados (Bug/Poison)")
    assert c.verdict == "TRUE", c
    c = one("Corviknight (Flying/Dragon)")
    assert c.verdict == "FALSE", c

    # --- possessive typing ---
    c = one("Heliolisk's typing is Electric")
    assert c.verdict == "TRUE", c
    c = one("Heliolisk's type is Grass")
    assert c.verdict == "FALSE", c
    c = one("Ariados's typing is Bug/Poison")
    assert c.verdict == "TRUE", c
    c = one("Corviknight's typing is Flying/Dragon")
    assert c.verdict == "FALSE", c

    # --- inverse adjectival ---
    c = one("Electric-type Heliolisk")
    assert c.verdict == "TRUE" and c.species == "Heliolisk", c
    c = one("an Electric-type Heliolisk")
    assert c.verdict == "TRUE", c
    c = one("Grass-type Heliolisk")
    assert c.verdict == "FALSE", c
    c = one("a Bug/Poison-type Ariados")
    assert c.verdict == "TRUE", c
    c = one("Flying/Dragon-type Corviknight")
    assert c.verdict == "FALSE", c

    # --- is a/an …-type Pokémon ---
    c = one("Heliolisk is an Electric-type Pokémon")
    assert c.verdict == "TRUE", c

    # --- ability separator (multi-word) ---
    c = one("Heliolisk - Dry Skin")
    assert c.kind == "ability" and c.verdict == "TRUE", c
    c = one("Heliolisk - Intimidate")
    assert c.kind == "ability" and c.verdict == "FALSE", c
    c = one("Incineroar (Intimidate)")
    assert c.kind == "ability" and c.verdict == "TRUE", c
    c = one("Heliolisk has the ability Dry Skin")
    assert c.kind == "ability" and c.verdict == "TRUE", c

    # skip neither-type-nor-ability separator
    assert types_of("Heliolisk - option 1") == []

    # --- numbered multi-claim dash list (#193 live shape) ---
    numbered = types_of(
        "Here are the typings for each candidate:\n\n"
        "1. Heliolisk - Electric/Grass type\n"
        "2. Abomasnow - Ice/Grass type\n"
        "3. Whimsicott - Fairy/Grass type\n"
    )
    assert len(numbered) == 3, numbered
    by_sp = {c.species: c for c in numbered}
    assert by_sp["Heliolisk"].verdict == "FALSE"
    assert by_sp["Heliolisk"].asserted_value == "Electric/Grass"
    assert by_sp["Abomasnow"].verdict == "TRUE"
    assert by_sp["Whimsicott"].verdict == "TRUE"

    print("species_fact_oracle self-check OK")


if __name__ == "__main__":
    _assert_self_check()
