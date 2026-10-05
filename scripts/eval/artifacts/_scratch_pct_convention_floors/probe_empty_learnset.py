"""Report-only: empty learnset keys vs legality check_set / resolve_learnset."""

from __future__ import annotations

from recommender.legality import (
    check_set,
    is_species_legal,
    legal_moves_for,
    load_snapshot,
    resolve_learnset,
)

PROBE = [
    "gourgeistsuper",
    "vivillonfancy",
    "vivillonpokeball",
    "polteageistantique",
    "sinistchamasterpiece",
]
EXPECTED = {
    "gourgeistsuper": ["trickroom", "shadowball", "protect"],
    "vivillonfancy": ["sleeppowder", "hurricane", "protect"],
    "vivillonpokeball": ["sleeppowder", "protect"],
    "polteageistantique": ["shellsmash", "shadowball", "protect"],
    "sinistchamasterpiece": ["matchagotcha", "ragepowder", "protect"],
}


def main() -> None:
    snap = load_snapshot()
    learnsets = snap.get("learnsets") or {}
    print("=== empty-learnset legality probe (report only) ===")
    for sid in PROBE:
        e = snap["species"].get(sid) or {}
        base = e.get("base_species_id")
        key_state = (
            "missing"
            if sid not in learnsets
            else f"present_len={len(learnsets[sid])}"
        )
        resolved = resolve_learnset(snap, sid)
        base_ls = resolve_learnset(snap, base) if base else None
        print(
            f"{sid}: legal={is_species_legal(snap, sid)} base={base} "
            f"learnset_key={key_state}"
        )
        print(
            "  resolve_learnset ->",
            None if resolved is None else f"len={len(resolved)}",
        )
        print(
            "  base resolve_learnset ->",
            None if base_ls is None else f"len={len(base_ls)}",
        )
        print("  legal_moves_for n=", len(legal_moves_for(sid, snap)))
        abil = next(iter((e.get("abilities") or {}).values()), None)
        name = str(e.get("name") or sid)
        for mv in EXPECTED.get(sid, []):
            result = check_set(name, [mv], "", ability=abil, snap=snap)
            lf = [
                (f.kind, f.detail)
                for f in result.failures
                if f.kind == "learnset"
            ]
            print(f"  check_set {mv}: ok={result.ok} learnset_fails={lf}")

    print("--- contrast: gourgeistlarge (missing key → inherit base) ---")
    sid = "gourgeistlarge"
    print(
        "key",
        "missing" if sid not in learnsets else f"len={len(learnsets[sid])}",
    )
    print("resolve len", len(resolve_learnset(snap, sid) or []))
    r = check_set("Gourgeist-Large", ["trickroom"], "", ability="Frisk", snap=snap)
    print("check_set trickroom", r.ok, [(f.kind, f.detail) for f in r.failures])


if __name__ == "__main__":
    main()
