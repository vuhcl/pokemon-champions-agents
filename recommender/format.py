from __future__ import annotations

from typing import TypedDict


class FormatResolved(TypedDict):
    game_type: str
    regulation_mod: str
    picked_team_size: int


def resolve_format(format_id: str) -> FormatResolved:
    if "Champions" not in format_id:
        raise ValueError(f"not a Champions format: {format_id!r}")

    if "VGC" in format_id:
        game_type, picked_team_size = "doubles", 4
    elif "BSS" in format_id:
        game_type, picked_team_size = "singles", 3
    else:
        raise ValueError(f"Champions format must be VGC or BSS: {format_id!r}")

    if "Reg M-A" in format_id:
        regulation_mod = "championsregma"
    elif "Reg M-B" in format_id:
        regulation_mod = "championsregmb"
    else:
        regulation_mod = "champions"
    return {
        "game_type": game_type,
        "regulation_mod": regulation_mod,
        "picked_team_size": picked_team_size,
    }
