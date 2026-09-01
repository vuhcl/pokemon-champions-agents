"""Read shipped Role Compendium JSON — evidence lookup only (no construction)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from recommender.ids import to_id

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROLES_DIR = ROOT / "data" / "roles"

# Strongest first — the order a consumer should prefer members in.
ROLE_TIER_ORDER = ("Excellent", "Good", "Acceptable")


def _tier_rank(tier: str | None) -> int:
    if tier in ROLE_TIER_ORDER:
        return ROLE_TIER_ORDER.index(tier)
    return len(ROLE_TIER_ORDER)  # missing/unknown tier sorts last


@dataclass(frozen=True)
class CompendiumRoleEvidence:
    """One reverse lookup result, kept distinct by evidence strength."""

    species: str
    role_id: str
    category: str
    condition: str
    tier: str | None
    mechanism: str | None
    source_file: str
    reason: str | None = None


@dataclass(frozen=True)
class ReverseCompendiumEvidence:
    exact: tuple[CompendiumRoleEvidence, ...] = ()
    species: tuple[CompendiumRoleEvidence, ...] = ()
    rejected: tuple[CompendiumRoleEvidence, ...] = ()


def _roles_filename(category: str, sub_criteria: dict[str, Any]) -> str:
    cond = to_id(str(sub_criteria.get("condition") or ""))
    if not cond:
        return f"{category}.v1.json"
    return f"{category}_{cond}.v1.json"


def load_prior_compendium(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _strategic_role_id(category: str, condition: str) -> str:
    if category == "weather_setter" and condition:
        return f"{to_id(condition)}_setter"
    return category.strip().lower().replace("-", "_").replace(" ", "_")


def _entry_evidence(raw: dict[str, Any], source_file: str) -> ReverseCompendiumEvidence:
    category = str(raw.get("category") or "")
    condition = str(raw.get("condition") or "")
    role_id = _strategic_role_id(category, condition)
    candidates = {
        to_id(str(row.get("species_id") or row.get("species") or "")): row
        for row in raw.get("candidates") or []
    }
    admitted: list[CompendiumRoleEvidence] = []
    for tier in ROLE_TIER_ORDER:
        for species in (raw.get("tiers") or {}).get(tier) or []:
            candidate = candidates.get(to_id(str(species))) or {}
            admitted.append(
                CompendiumRoleEvidence(
                    species=str(candidate.get("species") or species),
                    role_id=role_id,
                    category=category,
                    condition=condition,
                    tier=tier,
                    mechanism=str(candidate.get("mechanism") or "") or None,
                    source_file=source_file,
                )
            )
    rejected = tuple(
        CompendiumRoleEvidence(
            species=str(candidate.get("species") or candidate.get("species_id") or ""),
            role_id=role_id,
            category=category,
            condition=condition,
            tier=None,
            mechanism=str(candidate.get("mechanism") or "") or None,
            source_file=source_file,
            reason=str(candidate.get("reason") or ""),
        )
        for candidate in raw.get("considered_rejected") or []
    )
    return ReverseCompendiumEvidence(species=tuple(admitted), rejected=rejected)


def load_role_category(
    category: str,
    condition: str = "",
    *,
    roles_dir: Path | None = None,
) -> dict[str, Any] | None:
    """Shipped compendium entry for a role, or None when no entry has been built."""
    roles_dir = roles_dir or DEFAULT_ROLES_DIR
    return load_prior_compendium(
        roles_dir / _roles_filename(category, {"condition": condition})
    )


def role_category_evidence(
    category: str,
    condition: str = "",
    *,
    roles_dir: Path | None = None,
) -> ReverseCompendiumEvidence:
    """Forward role evidence; no concrete build exists to promote into exact."""
    root = roles_dir or DEFAULT_ROLES_DIR
    path = root / _roles_filename(category, {"condition": condition})
    raw = load_prior_compendium(path)
    return _entry_evidence(raw, path.name) if raw is not None else ReverseCompendiumEvidence()


def role_candidates(
    category: str,
    condition: str = "",
    *,
    roles_dir: Path | None = None,
) -> list[str]:
    """Species admitted to a role, best tier first. Empty when the role has no entry."""
    evidence = role_category_evidence(category, condition, roles_dir=roles_dir)
    return [row.species for row in evidence.species]


def reverse_compendium_evidence(
    species: str,
    *,
    moves: list[str] | tuple[str, ...] = (),
    ability: str | None = None,
    roles_dir: Path | None = None,
) -> ReverseCompendiumEvidence:
    """Find exact-build, species-only, and rejected compendium evidence."""
    root = roles_dir or DEFAULT_ROLES_DIR
    sid = to_id(species)
    present = {to_id(m) for m in moves}
    if ability:
        present.add(to_id(ability))
    exact: list[CompendiumRoleEvidence] = []
    species_only: list[CompendiumRoleEvidence] = []
    rejected: list[CompendiumRoleEvidence] = []
    for path in sorted(root.glob("*.v1.json")):
        rows = _entry_evidence(json.loads(path.read_text()), path.name)
        for row in rows.species:
            if to_id(row.species) != sid:
                continue
            (
                exact
                if row.mechanism and to_id(row.mechanism) in present
                else species_only
            ).append(row)
        for row in rows.rejected:
            if to_id(row.species) != sid:
                continue
            rejected.append(row)
    # Excellent > Good > Acceptable; same-tier ties → alphabetical source_file, then role_id.
    exact.sort(key=lambda row: (_tier_rank(row.tier), row.source_file, row.role_id))
    return ReverseCompendiumEvidence(
        exact=tuple(exact),
        species=tuple(species_only),
        rejected=tuple(rejected),
    )


_role_move_ids_cache: dict[str, frozenset[str]] = {}


def role_defining_move_ids(
    role_id: str,
    *,
    roles_dir: Path | None = None,
) -> frozenset[str]:
    """Union compendium sub_criteria move ids and _ROLE_PREF_MOVES for a role."""
    if role_id in _role_move_ids_cache:
        return _role_move_ids_cache[role_id]
    root = roles_dir or DEFAULT_ROLES_DIR
    ids: set[str] = set()
    for path in sorted(root.glob("*.v1.json")):
        raw = json.loads(path.read_text())
        category = str(raw.get("category") or "")
        condition = str(raw.get("condition") or "")
        if _strategic_role_id(category, condition) != role_id:
            continue
        sub = raw.get("sub_criteria") or {}
        for mid in sub.get("move_ids") or ():
            ids.add(to_id(str(mid)))
        if sub.get("move_id"):
            ids.add(to_id(str(sub["move_id"])))
    from recommender.move_narrowing import _ROLE_PREF_MOVES

    if role_id in _ROLE_PREF_MOVES:
        ids.update(_ROLE_PREF_MOVES[role_id])
    result = frozenset(ids)
    _role_move_ids_cache[role_id] = result
    return result
