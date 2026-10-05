"""Previous-regulation Showdown stand-ins (B4) — labeled build fields only.

Does not merge prior Showdown into current ``load_usage`` flat maps. Prior file
is ``{tag}.showdown_doubles.v1.json`` only (no monolith alias).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

from recommender.ids import (
    regulation_file_tag,
    regulation_lookup_chain,
    to_id,
)
from recommender.legality import (
    is_item_legal,
    is_move_legal,
    is_species_legal,
    load_snapshot,
    resolve_learnset,
    species_can_have_ability,
)
from recommender.regulation_registry import REGULATIONS, _previous, load_schedule
from recommender.usage_data import USAGE_DIR, _set_from_entry

PRIOR_SHOWDOWN_STANDIN = "prior_showdown_standin"
SPREAD_SOURCE_TOKEN = "prior-showdown-standin"

FieldConfidence = Literal["medium", "low"]

_FIELD_CONFIDENCE: dict[str, FieldConfidence] = {
    "ability": "medium",
    "moves": "medium",
    "item": "low",
    "nature": "low",
    "spread": "low",
    "evs": "low",
}
_CONF_RANK = {"low": 0, "medium": 1}

# path → (mtime_ns, species_map | None). Cleared via clear_prior_showdown_cache.
_PRIOR_SHOWDOWN_CACHE: dict[str, tuple[int, dict[str, Any] | None]] = {}


@dataclass(frozen=True)
class PriorStandinBuild:
    """Legality-filtered prior Showdown fields for one species."""

    species: str
    prior_tag: str
    prior_letter: str
    ability: str | None
    item: str | None
    nature: str | None
    moves: tuple[str, ...]
    evs: dict[str, int] | None
    filled_fields: frozenset[str]
    entry: Mapping[str, Any]

    @property
    def reason_ref(self) -> str:
        return standin_reason_ref(self.prior_tag)

    @property
    def present_label(self) -> str:
        return standin_present_label(self.prior_letter)


def clear_prior_showdown_cache() -> None:
    """Drop cached prior Showdown species maps (tests / file rewrite)."""
    _PRIOR_SHOWDOWN_CACHE.clear()


def standin_reason_ref(prior_tag: str) -> str:
    return f"{PRIOR_SHOWDOWN_STANDIN}:{regulation_file_tag(prior_tag)}"


def standin_present_label(prior_letter: str) -> str:
    return f"prior-reg Showdown stand-in (Reg M-{prior_letter.upper()})"


def standin_source_label(reason_ref: str | None) -> str | None:
    """Human label from ReasonRef.ref / ability source string."""
    if not reason_ref or not reason_ref.startswith(f"{PRIOR_SHOWDOWN_STANDIN}:"):
        return None
    prior_tag = reason_ref.split(":", 1)[1]
    return standin_present_label(letter_for_tag(prior_tag))


def letter_for_tag(tag: str) -> str:
    try:
        key = regulation_file_tag(tag)
    except ValueError:
        key = tag
    reg = REGULATIONS.get(key)
    if reg and reg.get("letter"):
        return str(reg["letter"]).upper()
    for window in load_schedule():
        if window.tag == key:
            return window.letter.upper()
    return "?"


def standin_field_confidence(field: str) -> FieldConfidence:
    return _FIELD_CONFIDENCE.get(field, "low")


def candidate_confidence_for_standin_fields(
    filled_fields: Iterable[str],
) -> FieldConfidence | None:
    """Min confidence over stand-in-filled fields only; None if empty."""
    caps = [
        standin_field_confidence(f)
        for f in filled_fields
        if f in _FIELD_CONFIDENCE
    ]
    if not caps:
        return None
    return min(caps, key=lambda c: _CONF_RANK[c])


def previous_regulation_tag(
    regulation: str,
    *,
    previous_tag: str | None = None,
) -> str | None:
    """Prior file tag: explicit override, else schedule previous, else archive[1].

    Unknown / typo'd tags return None — never silently fall back to the newest
    archive (that would invent a stand-in for a misspelled regulation). Forward
    letters not yet on the schedule (e.g. M-D pre-landing) must pass
    ``previous_tag=`` in tests, or land on the schedule / archive order.
    """
    if previous_tag is not None:
        try:
            return regulation_file_tag(previous_tag)
        except ValueError:
            return None
    try:
        tag = regulation_file_tag(regulation)
    except ValueError:
        return None
    windows = load_schedule()
    current = next((w for w in windows if w.tag == tag), None)
    if current is not None:
        prev = _previous(windows, current)
        if prev is not None:
            return prev.tag
    chain = regulation_lookup_chain(tag)
    if len(chain) >= 2:
        return chain[1]
    return None


def _prior_showdown_species_map(
    prior_tag: str, *, usage_dir: Path
) -> dict[str, Any] | None:
    """Load ``{prior}.showdown_doubles.v1.json`` only — never monolith.

    Cached by resolved path + ``st_mtime_ns`` so propose/recommend/anchor loops
    do not re-parse the ~316-species file per species.
    """
    path = usage_dir / f"{prior_tag}.showdown_doubles.v1.json"
    if not path.exists():
        return None
    key = str(path.resolve())
    mtime_ns = path.stat().st_mtime_ns
    hit = _PRIOR_SHOWDOWN_CACHE.get(key)
    if hit is not None and hit[0] == mtime_ns:
        return hit[1]
    data = json.loads(path.read_text(encoding="utf-8"))
    section = data.get("showdown_doubles") or {}
    species = section.get("species")
    result: dict[str, Any] | None = species if isinstance(species, dict) else None
    _PRIOR_SHOWDOWN_CACHE[key] = (mtime_ns, result)
    return result


def _move_legal_for_species(
    snap: dict[str, Any], species: str, move: str
) -> bool:
    if not is_move_legal(snap, move):
        return False
    learnset = resolve_learnset(snap, species)
    if learnset is not None and to_id(move) not in learnset:
        return False
    return True


def default_build_set(
    species: str,
    *,
    regulation: str,
    previous_tag: str | None = None,
    usage_dir: Path | None = None,
    snap: dict[str, Any] | None = None,
) -> PriorStandinBuild | None:
    """Legality-checked prior Showdown set for ``species`` at ``regulation``.

    Returns None when there is no prior tag, no prior showdown file/row, the
    species is illegal now, or every stand-in field fails legality.
    """
    prior = previous_regulation_tag(regulation, previous_tag=previous_tag)
    if prior is None:
        return None
    root = usage_dir if usage_dir is not None else USAGE_DIR
    species_map = _prior_showdown_species_map(prior, usage_dir=root)
    if not species_map:
        return None
    entry = species_map.get(to_id(species))
    if not isinstance(entry, dict):
        return None

    legality = snap if snap is not None else load_snapshot()
    if not is_species_legal(legality, species):
        return None

    built = _set_from_entry(entry, species)
    if not built:
        return None

    filled: set[str] = set()
    ability = built.get("ability")
    if ability and species_can_have_ability(legality, species, str(ability)):
        ability_out: str | None = str(ability)
        filled.add("ability")
    else:
        ability_out = None

    item = built.get("item")
    if item and is_item_legal(legality, str(item)):
        item_out: str | None = str(item)
        filled.add("item")
    else:
        item_out = None

    raw_moves = list(built.get("moves") or [])
    legal_moves = [
        str(m) for m in raw_moves if _move_legal_for_species(legality, species, str(m))
    ]
    if len(legal_moves) >= 4:
        moves_out = tuple(legal_moves[:4])
        filled.add("moves")
    else:
        moves_out = ()

    nature = built.get("nature")
    nature_out = str(nature) if nature else None
    if nature_out:
        filled.add("nature")

    evs_raw = built.get("evs")
    evs_out: dict[str, int] | None = None
    if isinstance(evs_raw, dict) and evs_raw:
        evs_out = {str(k): int(v) for k, v in evs_raw.items()}
        filled.add("spread")

    # Need at least one identity field (ability / moves / item) to be useful.
    if not filled.intersection({"ability", "moves", "item"}):
        return None

    stamped = {
        **dict(entry),
        "source": PRIOR_SHOWDOWN_STANDIN,
        "prior_regulation": prior,
    }
    return PriorStandinBuild(
        species=str(built.get("species") or species),
        prior_tag=prior,
        prior_letter=letter_for_tag(prior),
        ability=ability_out,
        item=item_out,
        nature=nature_out,
        moves=moves_out,
        evs=evs_out,
        filled_fields=frozenset(filled),
        entry=stamped,
    )
