"""Empty learnset keys must not block base_species_id inheritance."""

from __future__ import annotations

import json
from pathlib import Path

from recommender.legality import check_set, load_snapshot, resolve_learnset

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "data" / "legality" / "champions.v1.json"
PINNED_SHOWDOWN_COMMIT = "9fb3a5b99f1a0bea17f495c5cc1bfe04fdd19c3e"
# Formes that previously had present-empty learnsets[sid] == [].
OMITTED_EMPTY_LEARNSET_KEYS = frozenset(
    {
        "gourgeistsuper",
        "vivillonfancy",
        "vivillonpokeball",
        "polteageistantique",
        "sinistchamasterpiece",
    }
)


def test_snapshot_pinned_showdown_commit():
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert snap["meta"]["source"]["commit"] == PINNED_SHOWDOWN_COMMIT


def test_learnsets_have_no_empty_lists_and_omitted_formes_absent():
    """CI-safe invariants (no git show origin/main — shallow checkouts lack it).

    One-time 'only these five keys changed vs pre-PR main' stays in the PR body.
    """
    snap = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    learnsets = snap.get("learnsets") or {}
    empty = sorted(sid for sid, moves in learnsets.items() if moves == [])
    assert empty == [], empty
    for sid in OMITTED_EMPTY_LEARNSET_KEYS:
        assert sid not in learnsets
    assert snap["meta"]["source"]["commit"] == PINNED_SHOWDOWN_COMMIT


def test_omitted_formes_absent_and_resolve_to_base():
    snap = load_snapshot()
    learnsets = snap.get("learnsets") or {}
    for sid in OMITTED_EMPTY_LEARNSET_KEYS:
        assert sid not in learnsets
        ls = resolve_learnset(snap, sid)
        assert ls is not None and len(ls) > 0, sid
        base = (snap["species"].get(sid) or {}).get("base_species_id")
        assert base
        assert ls == resolve_learnset(snap, base)


def test_resolve_learnset_treats_empty_list_as_missing():
    snap = load_snapshot()
    # Synthetic: empty key must walk to base even if extract forgot to omit.
    patched = dict(snap)
    patched["learnsets"] = dict(snap.get("learnsets") or {})
    patched["learnsets"]["gourgeistsuper"] = []
    ls = resolve_learnset(patched, "gourgeistsuper")
    assert ls is not None
    assert "trickroom" in ls


def test_gourgeist_super_check_set_trick_room():
    snap = load_snapshot()
    r = check_set(
        "Gourgeist-Super",
        ["Trick Room", "Protect", "Poltergeist", "Shadow Ball"],
        "Life Orb",
        snap=snap,
    )
    assert not any(f.kind == "learnset" for f in r.failures), r.failures


def test_other_omitted_formes_check_set_smoke():
    snap = load_snapshot()
    cases = [
        ("Vivillon-Fancy", ["Hurricane", "Protect", "Sleep Powder", "Quiver Dance"]),
        ("Vivillon-Pokeball", ["Hurricane", "Protect", "Sleep Powder", "Quiver Dance"]),
        ("Polteageist-Antique", ["Shadow Ball", "Protect", "Shell Smash", "Stored Power"]),
        ("Sinistcha-Masterpiece", ["Matcha Gotcha", "Protect", "Rage Powder", "Strength Sap"]),
    ]
    for species, moves in cases:
        r = check_set(species, moves, "Leftovers", snap=snap)
        assert not any(f.kind == "learnset" for f in r.failures), (species, r.failures)


def test_mega_learnset_keys_still_absent():
    snap = load_snapshot()
    assert "swampertmega" not in (snap.get("learnsets") or {})
    ls = resolve_learnset(snap, "Swampert-Mega")
    assert ls is not None
    assert "wavecrash" in ls
