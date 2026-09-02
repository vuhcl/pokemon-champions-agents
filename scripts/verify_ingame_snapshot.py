#!/usr/bin/env python3
"""Compare ingame_doubles snapshot vs live CBD; report corruption scope."""

from __future__ import annotations

from recommender.usage_cbd import fetch_ingame_doubles_species
from recommender.usage_data import ingame_species_map
from recommender.usage_ingame_sanity import (
    find_stale_vs_live_suspects,
    stale_vs_live_suspect,
    top_move_ids,
)


def main() -> None:
    snap_map = ingame_species_map("champions-reg-mb")
    mismatches: list[tuple[str, list[str], list[str]]] = []
    zero_overlap: list[str] = []
    ok = 0
    missing_live = 0
    for sid, snap in sorted(snap_map.items()):
        if snap.get("ladder_rank_only"):
            continue
        name = snap.get("name") or sid
        live = fetch_ingame_doubles_species(name)
        if not live:
            missing_live += 1
            continue
        live_top4 = top_move_ids(live, n=4)
        snap_top4 = top_move_ids(snap, n=4)
        if live_top4 != snap_top4:
            mismatches.append((sid, snap_top4, live_top4))
            if stale_vs_live_suspect(snap, live):
                zero_overlap.append(sid)
        else:
            ok += 1

    suspects = find_stale_vs_live_suspects(snap_map)
    print(
        f"compared={ok + len(mismatches)} ok={ok} "
        f"mismatches={len(mismatches)} zero_overlap={len(zero_overlap)} "
        f"stale_gate={len(suspects)} missing_live={missing_live}"
    )
    for sid, snap_top4, live_top4 in mismatches:
        print(f"  {sid}: snap={snap_top4} live={live_top4}")
    if suspects:
        print(f"stale_vs_live_suspects={len(suspects)}")
        for sid, reason in suspects[:10]:
            print(f"  STALE {sid}: {reason}")
        if len(suspects) > 10:
            print(f"  ... and {len(suspects) - 10} more")


if __name__ == "__main__":
    main()
