"""Role Compendium construction / critic / rebuild (ADR-019).

Three separate callables — construct does not self-critique.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recommender.ability_classification import get_ability
from recommender.coverage import ABILITY_TO_FIELD
from recommender.ids import to_id
from recommender.legality import is_species_legal, load_snapshot, resolve_learnset
from recommender.usage_data import species_usage

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROLES_DIR = ROOT / "data" / "roles"

RAIN_SETTER_CRITERIA: dict[str, Any] = {
    "condition": "Rain",
    "ability_ids": frozenset({"drizzle"}),
    "move_id": "raindance",
    "priority_abilities": frozenset({"prankster"}),
}

_SUPPORT_MOVE_IDS = frozenset(
    {
        "tailwind",
        "lightscreen",
        "reflect",
        "auroraveil",
        "encore",
        "fakeout",
        "helpinghand",
        "followme",
        "ragepowder",
        "willowisp",
        "thunderwave",
        "wideguard",
        "quickguard",
        "allyswitch",
        "partingshot",
        "haze",
    }
)


@dataclass(frozen=True)
class ClaimedTrait:
    name: str
    criterion: str  # delivery | execution | secondary_role
    purpose_claimed: str


@dataclass
class CandidateEval:
    species: str
    species_id: str
    tier: str | None
    delivery_class: str
    mechanism: str
    criteria_notes: dict[str, str]
    claimed_traits: list[ClaimedTrait]
    reasoning: str
    change_reason: str | None = None


@dataclass
class RejectedCandidate:
    species: str
    species_id: str
    reason: str


@dataclass
class RoleConstructionDraft:
    category: str
    sub_criteria: dict[str, Any]
    candidates: list[CandidateEval]
    considered_rejected: list[RejectedCandidate]
    tiers: dict[str, list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class CritiqueFlag:
    principle: str
    candidates: tuple[str, ...]
    detail: str


@dataclass
class CritiqueResult:
    approved: bool
    flags: list[CritiqueFlag]


@dataclass
class RebuildResult:
    status: str
    draft: RoleConstructionDraft
    critique: CritiqueResult
    path: str | None


def _criteria_sets(sub_criteria: dict[str, Any]) -> tuple[frozenset[str], str, frozenset[str], str]:
    ability_ids = frozenset(to_id(a) for a in sub_criteria["ability_ids"])
    move_id = to_id(sub_criteria["move_id"])
    priority = frozenset(to_id(a) for a in sub_criteria["priority_abilities"])
    condition = str(sub_criteria["condition"])
    return ability_ids, move_id, priority, condition


def _serialize_criteria(sub_criteria: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in sub_criteria.items():
        if isinstance(v, (set, frozenset)):
            out[k] = sorted(v)
        else:
            out[k] = v
    return out


def _species_abilities(snap: dict[str, Any], sid: str) -> dict[str, str]:
    entry = snap["species"].get(sid) or {}
    out: dict[str, str] = {}
    for name in (entry.get("abilities") or {}).values():
        if isinstance(name, str):
            out[to_id(name)] = name
    return out


def _pool_index(
    legal_pool: list[str], snap: dict[str, Any]
) -> dict[str, str]:
    """species_id -> display name; only ids in legal_pool."""
    allowed = {to_id(s) for s in legal_pool}
    out: dict[str, str] = {}
    for sid in allowed:
        entry = snap["species"].get(sid)
        if not entry:
            # Pool may use display names for forms not in snap — still track id.
            out[sid] = next((s for s in legal_pool if to_id(s) == sid), sid)
            continue
        if not is_species_legal(snap, sid):
            continue
        out[sid] = str(entry.get("name") or sid)
    return out


def _usage_delivers_move(species: str, move_id: str) -> bool:
    entry = species_usage(species)
    if not entry:
        return False
    for m in entry.get("common_moves") or []:
        if to_id(m.get("name") or "") == move_id:
            return True
    for fs in entry.get("featured_sets") or []:
        for m in fs.get("moves") or []:
            if to_id(m) == move_id:
                return True
    return False


def _secondary_support_notes(species: str) -> tuple[str, list[ClaimedTrait]]:
    entry = species_usage(species) or {}
    hits: list[str] = []
    traits: list[ClaimedTrait] = []
    for m in entry.get("common_moves") or []:
        mid = to_id(m.get("name") or "")
        if mid in _SUPPORT_MOVE_IDS:
            name = str(m.get("name") or mid)
            hits.append(name)
            traits.append(
                ClaimedTrait(
                    name=name,
                    criterion="secondary_role",
                    purpose_claimed="other-directed support stacking",
                )
            )
    note = ", ".join(hits) if hits else "none observed in usage common_moves"
    return note, traits


def _ref_members(
    reference: dict[str, Any] | RoleConstructionDraft | None,
) -> dict[str, str]:
    """species_id -> tier from a prior compendium / draft."""
    if reference is None:
        return {}
    if isinstance(reference, RoleConstructionDraft):
        return {
            c.species_id: c.tier or ""
            for c in reference.candidates
            if c.tier
        }
    out: dict[str, str] = {}
    for c in reference.get("candidates") or []:
        sid = c.get("species_id") or to_id(c.get("species") or "")
        tier = c.get("tier")
        if sid and tier:
            out[str(sid)] = str(tier)
    # also accept tiers map
    for tier, names in (reference.get("tiers") or {}).items():
        for n in names or []:
            out.setdefault(to_id(n), str(tier))
    return out


def construct_role_category(
    category: str,
    sub_criteria: dict[str, Any],
    legal_pool: list[str],
    *,
    snap: dict[str, Any] | None = None,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None = None,
) -> RoleConstructionDraft:
    """Build a draft ranking from the legal pool forward — never legality-after-search."""
    snap = snap or load_snapshot()
    ability_ids, move_id, priority_abilities, _condition = _criteria_sets(sub_criteria)
    pool = _pool_index(legal_pool, snap)
    pool_ids = set(pool)
    # reference_compendium is context for callers/rebuild; fresh eval ignores it for tiers.
    _ = reference_compendium

    members: list[CandidateEval] = []
    rejected: list[RejectedCandidate] = []
    admitted_ids: set[str] = set()

    # Ability pathway — exhaustive over legal pool.
    for sid, name in sorted(pool.items(), key=lambda x: x[1]):
        abs_map = _species_abilities(snap, sid)
        hit = ability_ids & set(abs_map)
        if not hit:
            continue
        aid = next(iter(sorted(hit)))
        mechanism = abs_map[aid]
        secondary_note, secondary_traits = _secondary_support_notes(name)
        traits = [
            ClaimedTrait(
                name=mechanism,
                criterion="delivery",
                purpose_claimed=f"set {_condition_label(sub_criteria)} via ability",
            ),
            ClaimedTrait(
                name=mechanism,
                criterion="execution",
                purpose_claimed="automatic on switch-in; no turn cost",
            ),
            *secondary_traits,
        ]
        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier="Excellent",
                delivery_class="ability",
                mechanism=mechanism,
                criteria_notes={
                    "delivery": "ability-guaranteed (more reliable than move)",
                    "execution": "automatic on switch-in; no moveslot / priority risk",
                    "secondary_role": secondary_note,
                },
                claimed_traits=traits,
                reasoning=(
                    f"{mechanism} ability delivery clears Excellent bar; "
                    f"secondary kit noted but does not force-rank within tier "
                    f"({secondary_note})."
                ),
                # Fresh eval never auto-fills change_reason — critic flags silent diffs.
                change_reason=None,
            )
        )
        admitted_ids.add(sid)

    # Move pathway — skip species already ability-admitted (precondition).
    for sid, name in sorted(pool.items(), key=lambda x: x[1]):
        if sid in admitted_ids:
            continue
        abs_map = _species_abilities(snap, sid)
        prio = priority_abilities & set(abs_map)
        if not prio:
            continue
        ls = set(resolve_learnset(snap, sid) or [])
        if move_id not in ls:
            continue
        prio_name = abs_map[next(iter(sorted(prio)))]
        move_display = _move_display(snap, move_id)
        if not _usage_delivers_move(name, move_id):
            rejected.append(
                RejectedCandidate(
                    species=name,
                    species_id=sid,
                    reason=(
                        f"{prio_name}+{move_display} learnset but no usage evidence "
                        f"of {move_display} delivery"
                    ),
                )
            )
            continue
        secondary_note, secondary_traits = _secondary_support_notes(name)
        traits = [
            ClaimedTrait(
                name=move_display,
                criterion="delivery",
                purpose_claimed=f"set {_condition_label(sub_criteria)} via move",
            ),
            ClaimedTrait(
                name=prio_name,
                criterion="execution",
                purpose_claimed="priority on status setup move",
            ),
            *secondary_traits,
        ]
        members.append(
            CandidateEval(
                species=name,
                species_id=sid,
                tier="Good",
                delivery_class="move_priority",
                mechanism=move_display,
                criteria_notes={
                    "delivery": "move-based (less reliable than ability)",
                    "execution": (
                        f"{prio_name}-boosted status move; blocked by Dark-types / "
                        "Good as Gold / some immunities"
                    ),
                    "secondary_role": secondary_note,
                },
                claimed_traits=traits,
                reasoning=(
                    f"{prio_name} {move_display} clears Good (priority move delivery); "
                    f"below ability-guaranteed setters. Secondary: {secondary_note}."
                ),
                change_reason=None,
            )
        )
        admitted_ids.add(sid)

    # Guard: nothing outside pool.
    for c in members:
        if c.species_id not in pool_ids:
            raise ValueError(f"candidate escaped legal_pool: {c.species}")
    for r in rejected:
        if r.species_id not in pool_ids:
            raise ValueError(f"rejected escaped legal_pool: {r.species}")

    tiers: dict[str, list[str]] = {"Excellent": [], "Good": []}
    for c in members:
        if c.tier:
            tiers.setdefault(c.tier, []).append(c.species)

    return RoleConstructionDraft(
        category=category,
        sub_criteria=_serialize_criteria(sub_criteria),
        candidates=members,
        considered_rejected=rejected,
        tiers=tiers,
    )


def _condition_label(sub_criteria: dict[str, Any]) -> str:
    return str(sub_criteria.get("condition") or "")


def _move_display(snap: dict[str, Any], move_id: str) -> str:
    entry = (snap.get("moves") or {}).get(move_id) or {}
    return str(entry.get("name") or move_id)


def critique_role_ranking(
    draft: RoleConstructionDraft,
    reference_compendium: dict[str, Any] | RoleConstructionDraft | None = None,
) -> CritiqueResult:
    """Audit draft against tied-cluster / self-consistency / function-fit. Flags only."""
    flags: list[CritiqueFlag] = []
    by_id = {c.species_id: c for c in draft.candidates if c.tier}
    members = [c for c in draft.candidates if c.tier]

    # (a) tied_cluster — cross-tier pairs need a real delivery_class (degree) gap.
    for i, a in enumerate(members):
        for b in members[i + 1 :]:
            if a.tier == b.tier:
                continue
            if a.delivery_class == b.delivery_class:
                flags.append(
                    CritiqueFlag(
                        principle="tied_cluster",
                        candidates=(a.species, b.species),
                        detail=(
                            f"{a.species} ({a.tier}) vs {b.species} ({b.tier}) share "
                            f"delivery_class={a.delivery_class!r}; no criteria-based "
                            "degree gap — merge into one unordered tier"
                        ),
                    )
                )

    # (b) self_consistency vs prior.
    prior = _ref_members(reference_compendium)
    current_tiers = {c.species_id: c.tier for c in members}
    for sid, old_tier in prior.items():
        new_tier = current_tiers.get(sid)
        cand = by_id.get(sid)
        name = cand.species if cand else sid
        if new_tier is None:
            if cand is None or cand.change_reason is None:
                # dropped without stated reason
                dropped = next(
                    (c for c in draft.candidates if c.species_id == sid), None
                )
                if dropped is None or dropped.change_reason is None:
                    flags.append(
                        CritiqueFlag(
                            principle="self_consistency",
                            candidates=(name,),
                            detail=(
                                f"prior tier {old_tier!r} dropped with no change_reason"
                            ),
                        )
                    )
            continue
        if new_tier != old_tier:
            if cand is None or cand.change_reason is None:
                flags.append(
                    CritiqueFlag(
                        principle="self_consistency",
                        candidates=(name,),
                        detail=(
                            f"prior tier {old_tier!r} → {new_tier!r} with no "
                            "change_reason"
                        ),
                    )
                )

    # (c) function_fit
    condition = str(draft.sub_criteria.get("condition") or "")
    for c in members:
        for trait in c.claimed_traits:
            flags.extend(_function_fit_flags(c, trait, condition))

    return CritiqueResult(approved=not flags, flags=flags)


def _function_fit_flags(
    cand: CandidateEval, trait: ClaimedTrait, condition: str
) -> list[CritiqueFlag]:
    out: list[CritiqueFlag] = []
    tid = to_id(trait.name)
    purpose = trait.purpose_claimed.lower()
    criterion = trait.criterion

    field = ABILITY_TO_FIELD.get(tid)
    if field and "weather" in field:
        weather = str(field.get("weather") or "")
        if criterion == "delivery" and weather != condition:
            out.append(
                CritiqueFlag(
                    principle="function_fit",
                    candidates=(cand.species,),
                    detail=(
                        f"{trait.name} sets {weather!r}, not condition {condition!r}"
                    ),
                )
            )

    if tid == "prankster" and criterion != "execution":
        out.append(
            CritiqueFlag(
                principle="function_fit",
                candidates=(cand.species,),
                detail="Prankster only credits execution of status setup, not other criteria",
            )
        )

    allyish = "ally" in purpose or criterion == "secondary_role"
    if allyish and ("protect" in purpose or "ally" in purpose or criterion == "secondary_role"):
        ab = get_ability(tid)
        if ab:
            tags = ab.get("tags") or []
            # Self-only protective abilities do not satisfy ally-protection /
            # other-directed secondary support when purpose claims that.
            if tags and all(t.get("target") == "self" for t in tags):
                if "ally" in purpose or "protection" in purpose or "protect" in purpose:
                    out.append(
                        CritiqueFlag(
                            principle="function_fit",
                            candidates=(cand.species,),
                            detail=(
                                f"{trait.name} is self-targeted; does not serve "
                                f"claimed purpose {trait.purpose_claimed!r}"
                            ),
                        )
                    )
    return out


def _roles_filename(category: str, sub_criteria: dict[str, Any]) -> str:
    cond = to_id(str(sub_criteria.get("condition") or "unknown"))
    return f"{category}_{cond}.v1.json"


def draft_to_dict(draft: RoleConstructionDraft) -> dict[str, Any]:
    return {
        "category": draft.category,
        "condition": draft.sub_criteria.get("condition"),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "sub_criteria": draft.sub_criteria,
        "tiers": draft.tiers,
        "candidates": [
            {
                "species": c.species,
                "species_id": c.species_id,
                "tier": c.tier,
                "delivery_class": c.delivery_class,
                "mechanism": c.mechanism,
                "criteria_notes": c.criteria_notes,
                "claimed_traits": [asdict(t) for t in c.claimed_traits],
                "reasoning": c.reasoning,
                "change_reason": c.change_reason,
            }
            for c in draft.candidates
        ],
        "considered_rejected": [asdict(r) for r in draft.considered_rejected],
    }


def load_prior_compendium(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def persist_approved(
    draft: RoleConstructionDraft,
    roles_dir: Path,
    *,
    filename: str | None = None,
) -> Path:
    roles_dir.mkdir(parents=True, exist_ok=True)
    name = filename or _roles_filename(draft.category, draft.sub_criteria)
    current = roles_dir / name
    if current.exists():
        hist = roles_dir / "history"
        hist.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stem = name.replace(".v1.json", "")
        shutil.copy2(current, hist / f"{stem}.{ts}.json")
    current.write_text(json.dumps(draft_to_dict(draft), indent=2) + "\n")
    return current


def legal_species_pool(snap: dict[str, Any] | None = None) -> list[str]:
    snap = snap or load_snapshot()
    out: list[str] = []
    for sid, entry in (snap.get("species") or {}).items():
        if is_species_legal(snap, sid):
            out.append(str(entry.get("name") or sid))
    return out


def rebuild_role_category(
    category: str,
    sub_criteria: dict[str, Any],
    *,
    roles_dir: Path | None = None,
) -> RebuildResult:
    """Construct + critique; persist only on approval. Flags → human gate (no auto-revise)."""
    roles_dir = roles_dir or DEFAULT_ROLES_DIR
    snap = load_snapshot()
    pool = legal_species_pool(snap)
    path = roles_dir / _roles_filename(category, sub_criteria)
    prior = load_prior_compendium(path)
    draft = construct_role_category(
        category,
        sub_criteria,
        pool,
        snap=snap,
        reference_compendium=prior,
    )
    critique = critique_role_ranking(draft, reference_compendium=prior)
    if not critique.approved:
        return RebuildResult(
            status="needs_revision",
            draft=draft,
            critique=critique,
            path=None,
        )
    written = persist_approved(draft, roles_dir)
    return RebuildResult(
        status="approved",
        draft=draft,
        critique=critique,
        path=str(written),
    )
