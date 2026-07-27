"""Team Preview quick-pick: bring 4 of 6 (ADR-012a). Stateless."""

from __future__ import annotations

import itertools
from typing import Any, NotRequired, TypedDict

from recommender.calc_client import calculate_batch as default_calculate_batch
from recommender.ids import to_id
from recommender.recommend import select_opponent_builds
from recommender.state import PokemonSet


class QuickPickResult(TypedDict):
    ok: bool
    bring: list[int]
    rationales: list[str]
    detail: NotRequired[str]


def _damaging_move(s: PokemonSet) -> str | None:
    for m in s.get("moves") or []:
        if to_id(m) not in {"protect", "substitute", "tailwind", "trickroom", "helpinghand"}:
            return m
    return (s.get("moves") or [None])[0]


def quick_pick(
    team_draft: list[PokemonSet],
    opponent_species: list[str],
    *,
    regulation: str = "champions",
    calculate_batch=None,
) -> QuickPickResult:
    if len(team_draft) != 6:
        return {
            "ok": False,
            "bring": [],
            "rationales": [],
            "detail": f"team_draft must have 6 sets, got {len(team_draft)}",
        }

    calc = calculate_batch or default_calculate_batch
    opponents = select_opponent_builds(opponent_species, regulation=regulation, k=min(5, len(opponent_species)))
    if not opponents:
        return {
            "ok": False,
            "bring": [],
            "rationales": [],
            "detail": "no assumed opponent sets in usage snapshot",
        }

    best_score = float("-inf")
    best_combo: tuple[int, ...] = (0, 1, 2, 3)
    best_notes: list[str] = ["", "", "", ""]

    for combo in itertools.combinations(range(6), 4):
        brought = [team_draft[i] for i in combo]
        reqs: list[dict[str, Any]] = []
        meta: list[tuple[int, str, str]] = []  # bring_offset, move, opp species
        for bi, mine in enumerate(brought):
            move = _damaging_move(mine)
            if not move or not mine.get("species"):
                continue
            for opp in opponents[:3]:
                reqs.append(
                    {
                        "attacker": {
                            "species": mine["species"],
                            "item": mine.get("item"),
                            "evs": mine.get("evs") or {"hp": 20, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 14},
                        },
                        "defender": {
                            "species": opp.get("species"),
                            "item": opp.get("item"),
                            "evs": opp.get("evs") or {"hp": 32, "atk": 0, "def": 16, "spa": 0, "spd": 16, "spe": 0},
                        },
                        "move": move,
                        "field": {"gameType": "Doubles"},
                    }
                )
                meta.append((bi, move, str(opp.get("species"))))
            if len(reqs) >= 40:
                break
        if not reqs:
            continue
        try:
            results = calc(reqs[:40])
        except Exception:  # noqa: BLE001
            continue

        score = 0.0
        slot_best: dict[int, tuple[float, str]] = {}
        for (bi, move, opp_sp), r in zip(meta, results):
            if isinstance(r, dict) and "error" in r:
                continue
            # Heuristic: prefer OHKO/2HKO text
            ko = str(r.get("koChance") or "")
            pts = 0.0
            if "OHKO" in ko and "2HKO" not in ko and "3HKO" not in ko:
                pts = 3.0
            elif "2HKO" in ko:
                pts = 2.0
            elif "3HKO" in ko:
                pts = 1.0
            else:
                pts = 0.3
            # speed penalty crude: lower spe investment than opp
            my_spe = int((brought[bi].get("evs") or {}).get("spe", 0))
            opp_spe = int((opponents[0].get("evs") or {}).get("spe", 0))
            if my_spe < opp_spe and to_id(move) != "trickroom":
                pts -= 0.2
            score += pts
            prev = slot_best.get(bi)
            if prev is None or pts > prev[0]:
                slot_best[bi] = (pts, f"covers {opp_sp} via {move}")

        if score > best_score:
            best_score = score
            best_combo = combo
            best_notes = [
                slot_best.get(i, (0, f"slot {combo[i]}"))[1] for i in range(4)
            ]

    return {
        "ok": True,
        "bring": list(best_combo),
        "rationales": best_notes,
    }
