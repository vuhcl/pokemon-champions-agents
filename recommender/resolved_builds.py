"""Resolved-build JSONL cache (ADR-016)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from recommender.ids import regulation_file_tag, regulation_lookup_chain, to_id

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = REPO_ROOT / "data" / "resolved-builds"


class VerificationContext(TypedDict, total=False):
    threat_set: list[str]
    usage_snapshot: str
    notes: str


class ResolvedBuild(TypedDict):
    species: str
    moves: list[str]
    item: str
    regulation: str
    spread: dict[str, int]
    source_tier: str
    verified: bool
    verification_context: VerificationContext
    date_resolved: str
    variants: NotRequired[list[dict[str, int]]]
    carried_forward_from: NotRequired[str]
    rationale: NotRequired[str]
    source_format: NotRequired[str]
    found_in_regulation: NotRequired[str]
    nature: NotRequired[str]
    # Only set when the source material explicitly, unambiguously ties this
    # exact spread to one specific nature (e.g. "with Modest:" immediately
    # following the exact EV numbers, or "a Timid nature is mandatory"). Left
    # absent when the spread is genuinely nature-flexible in the source, or
    # when a nature word appears nearby but describes something else
    # entirely (an opposing Pokemon's set, or a different alternative
    # spread) — do not infer this field from loose proximity matching;
    # verify the tie is real and specific to this exact spread first.
    ability: NotRequired[str]
    ability_candidates: NotRequired[list[str]]
    ability_pick_index: NotRequired[int]
    ability_pick_policy: NotRequired[str]


class WriteupAbilityHit(TypedDict):
    ability: str
    source_tier: str
    source_format: str
    ability_candidates: list[str]
    ability_pick_index: int
    ability_pick_policy: str


def _key(species: str, moves: list[str], item: str) -> tuple[str, tuple[str, ...], str]:
    return (to_id(species), tuple(sorted(to_id(m) for m in moves)), to_id(item))


def _writeup_ability_rank(source_format: str) -> int:
    """Lower is better. Any VGC before any BSS; Champions-native before SV within family."""
    sf = source_format or ""
    if sf.startswith("champions/") and sf.removeprefix("champions/").startswith("vgc"):
        return 0
    if sf == "sv/vgc":
        return 1
    if sf.startswith("sv/") and sf.removeprefix("sv/").startswith("vgc"):
        return 2
    if sf == "champions/battle-stadium-singles":
        return 3
    if sf == "sv/battle-stadium-singles":
        return 4
    return 5


def get_writeup_ability(
    species: str,
    regulation: str,
    *,
    root: Path = DEFAULT_DIR,
) -> WriteupAbilityHit | None:
    """Species-scoped writeup ability lookup (ignores moves/item key).

    Ranking (lower better): champions/vgc* → sv/vgc → other sv/vgc* →
    champions/battle-stadium-singles → sv/battle-stadium-singles → other.
    Tie-break: prefer non-thin rationale if present, else first seen.
    """
    want = to_id(species)
    best: WriteupAbilityHit | None = None
    best_rank = 99
    best_thin = True
    for tag in regulation_lookup_chain(regulation):
        for row in _load(root / f"{tag}.jsonl"):
            if to_id(row.get("species") or "") != want:
                continue
            ability = row.get("ability")
            if not ability:
                continue
            sf = str(row.get("source_format") or "")
            rank = _writeup_ability_rank(sf)
            thin = len(str(row.get("rationale") or "").strip()) < 80
            if best is None or rank < best_rank or (
                rank == best_rank and best_thin and not thin
            ):
                best_rank = rank
                best_thin = thin
                cands = list(row.get("ability_candidates") or [ability])
                pick_i = int(row.get("ability_pick_index") or 0)
                best = {
                    "ability": str(ability),
                    "source_tier": str(row.get("source_tier") or ""),
                    "source_format": sf,
                    "ability_candidates": [str(c) for c in cands],
                    "ability_pick_index": pick_i,
                    "ability_pick_policy": str(
                        row.get("ability_pick_policy") or "first_listed"
                    ),
                }
            if rank == 0 and not thin:
                return best
    return best


def _path(regulation: str, *, root: Path = DEFAULT_DIR) -> Path:
    tag = regulation_file_tag(regulation)
    return root / f"{tag}.jsonl"


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _write_all(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))


def get_resolved_build(
    species: str,
    moves: list[str],
    item: str | None,
    regulation: str,
    *,
    root: Path = DEFAULT_DIR,
    chain: bool = True,
) -> ResolvedBuild | None:
    if item is None:
        return None
    tags = (
        regulation_lookup_chain(regulation)
        if chain
        else [regulation_file_tag(regulation)]
    )
    want = _key(species, moves, item)
    for tag in tags:
        for row in _load(root / f"{tag}.jsonl"):
            if _key(row["species"], row["moves"], row["item"]) == want:
                return {**row, "found_in_regulation": tag}  # type: ignore[return-value]
    return None


def put_resolved_build(
    species: str,
    moves: list[str],
    item: str,
    regulation: str,
    spread: dict[str, int],
    source_tier: str,
    verified: bool,
    verification_context: VerificationContext,
    variants: list[dict[str, int]] | None = None,
    *,
    root: Path = DEFAULT_DIR,
    carried_forward_from: str | None = None,
    rationale: str | None = None,
    source_format: str | None = None,
    ability: str | None = None,
    ability_candidates: list[str] | None = None,
    ability_pick_index: int | None = None,
    ability_pick_policy: str | None = None,
) -> bool:
    """Write or replace an unverified row. Returns False if existing verified=True (skip)."""
    path = _path(regulation, root=root)
    tag = regulation_file_tag(regulation)
    entry: dict[str, Any] = {
        "species": to_id(species),
        "moves": sorted(to_id(m) for m in moves),
        "item": to_id(item),
        "regulation": tag,
        "spread": spread,
        "source_tier": source_tier,
        "verified": verified,
        "verification_context": verification_context,
        "date_resolved": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if variants is not None:
        entry["variants"] = variants
    if carried_forward_from is not None:
        entry["carried_forward_from"] = carried_forward_from
    if rationale is not None:
        entry["rationale"] = rationale
    if source_format is not None:
        entry["source_format"] = source_format
    if ability is not None:
        entry["ability"] = ability
    if ability_candidates is not None:
        entry["ability_candidates"] = ability_candidates
    if ability_pick_index is not None:
        entry["ability_pick_index"] = ability_pick_index
    if ability_pick_policy is not None:
        entry["ability_pick_policy"] = ability_pick_policy

    want = _key(species, moves, item)
    rows = _load(path)
    replaced = False
    for i, row in enumerate(rows):
        if _key(row["species"], row["moves"], row["item"]) == want:
            if row.get("verified") is True and not verified:
                return False
            rows[i] = entry
            replaced = True
            break
    if not replaced:
        rows.append(entry)
    _write_all(path, rows)
    return True


def archive_regulation(old_tag: str, new_tag: str, *, root: Path = DEFAULT_DIR) -> None:
    """Archive prior regulation file under its own tag (no delete/merge).

    If `old_tag.jsonl` exists and `new_tag` is becoming current, ensure old file
    stays named for old_tag (already the case). Creates empty new_tag file if absent.
    """
    old_path = root / f"{regulation_file_tag(old_tag)}.jsonl"
    new_path = root / f"{regulation_file_tag(new_tag)}.jsonl"
    root.mkdir(parents=True, exist_ok=True)
    if not old_path.exists():
        old_path.write_text("")
    if not new_path.exists():
        new_path.write_text("")
