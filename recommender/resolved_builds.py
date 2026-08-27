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


def _key(species: str, moves: list[str], item: str) -> tuple[str, tuple[str, ...], str]:
    return (to_id(species), tuple(sorted(to_id(m) for m in moves)), to_id(item))


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
