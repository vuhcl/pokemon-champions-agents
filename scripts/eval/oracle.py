"""Eval-only species/item legality — does not import recommender.legality gates."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def to_id(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def load_oracle_snapshot(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def species_legal(snap: dict[str, Any], species: str) -> bool:
    e = (snap.get("species") or {}).get(to_id(species))
    if not e:
        return False
    if e.get("is_nonstandard") is not None:
        return False
    if e.get("tier") == "Illegal":
        return False
    ban = set((snap.get("flat_rules") or {}).get("banlist") or [])
    if ban & set(e.get("effective_tags") or []):
        return False
    return True


def item_legal(snap: dict[str, Any], item: str) -> bool:
    if not item:
        return True  # empty locked item: no item claim to fail
    e = (snap.get("items") or {}).get(to_id(item))
    if not e:
        return False
    return e.get("is_nonstandard") is None


def pair_legal(snap: dict[str, Any], species: str, item: str) -> bool:
    return species_legal(snap, species) and item_legal(snap, item)
