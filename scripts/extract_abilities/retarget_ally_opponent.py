"""Retarget ability tags: self/other → self/ally/opponent + resolve Phase B flags.

Run: uv run python scripts/extract_abilities/retarget_ally_opponent.py
Fail-closed: exits non-zero if any target=other remains or empties ≠ allowlist.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "data" / "abilities" / "all.v1.json"
REPORT = ROOT / "artifacts" / "ability_phase_b_flags.md"
PROPOSAL = ROOT / "artifacts" / "ability_taxonomy_proposal.md"


def T(target: str, activation: str, purpose: str) -> dict[str, str]:
    return {"target": target, "activation": activation, "purpose": purpose}


def both(activation: str, purpose: str) -> list[dict[str, str]]:
    return [T("ally", activation, purpose), T("opponent", activation, purpose)]


# --- Explicit full tag replacements (ids that had other, or newly resolved) ---

FULL: dict[str, list[dict[str, str]]] = {
    # Sample / previously other — foe-only
    "intimidate": [T("opponent", "unconditional", "disrupt")],
    "roughskin": [T("opponent", "triggered", "disrupt")],
    "ironbarbs": [T("opponent", "triggered", "disrupt")],
    "cursedbody": [T("opponent", "triggered", "disrupt")],
    "aftermath": [T("opponent", "triggered", "disrupt")],
    "innardsout": [T("opponent", "triggered", "disrupt")],
    "cutecharm": [T("opponent", "triggered", "disrupt")],
    "effectspore": [T("opponent", "triggered", "disrupt")],
    "flamebody": [T("opponent", "triggered", "disrupt")],
    "static": [T("opponent", "triggered", "disrupt")],
    "poisonpoint": [T("opponent", "triggered", "disrupt")],
    "gooey": [T("opponent", "triggered", "disrupt")],
    "tanglinghair": [T("opponent", "triggered", "disrupt")],
    "spicyspray": [T("opponent", "triggered", "disrupt")],
    "liquidooze": [T("opponent", "triggered", "disrupt")],
    "synchronize": [T("opponent", "triggered", "disrupt")],
    "mummy": [T("opponent", "triggered", "disrupt")],
    "lingeringaroma": [T("opponent", "triggered", "disrupt")],
    "baddreams": [T("opponent", "triggered", "disrupt")],
    "arenatrap": [T("opponent", "unconditional", "disrupt")],
    "shadowtag": [T("opponent", "unconditional", "disrupt")],
    "magnetpull": [T("opponent", "unconditional", "disrupt")],
    "unnerve": [T("opponent", "unconditional", "disrupt")],
    "pressure": [T("opponent", "unconditional", "disrupt")],
    "supersweetsyrup": [T("opponent", "unconditional", "disrupt")],
    "toxicdebris": [T("opponent", "triggered", "disrupt")],
    "poisonpuppeteer": [T("opponent", "triggered", "disrupt")],
    "mirrorarmor": [T("opponent", "triggered", "disrupt")],
    # Ally-only
    "friendguard": [T("ally", "unconditional", "support")],
    "battery": [T("ally", "unconditional", "boost")],
    "healer": [T("ally", "unconditional", "support")],
    "hospitality": [T("ally", "unconditional", "support")],
    "aromaveil": [T("ally", "unconditional", "support")],
    "pastelveil": [T("ally", "unconditional", "support")],
    "sweetveil": [T("ally", "unconditional", "support")],
    "flowerveil": [T("ally", "unconditional", "support")],
    "powerspot": [T("ally", "unconditional", "boost")],
    "steelyspirit": [T("ally", "unconditional", "boost")],
    "victorystar": [T("ally", "unconditional", "boost")],
    "symbiosis": [T("ally", "triggered", "support")],
    # Self + ally priority denial
    "armortail": [
        T("self", "unconditional", "support"),
        T("ally", "unconditional", "support"),
    ],
    "dazzling": [
        T("self", "unconditional", "support"),
        T("ally", "unconditional", "support"),
    ],
    "queenlymajesty": [
        T("self", "unconditional", "support"),
        T("ally", "unconditional", "support"),
    ],
    # Shared field → ally + opponent
    "drizzle": both("unconditional", "support"),
    "drought": both("unconditional", "support"),
    "electricsurge": both("unconditional", "support"),
    "grassysurge": both("unconditional", "support"),
    "mistysurge": both("unconditional", "support"),
    "psychicsurge": both("unconditional", "support"),
    "sandstream": both("unconditional", "support"),
    "snowwarning": both("unconditional", "support"),
    "deltastream": both("unconditional", "support"),
    "desolateland": both("unconditional", "support"),
    "primordialsea": both("unconditional", "support"),
    "sandspit": both("triggered", "support"),
    "seedsower": both("triggered", "support"),
    "airlock": both("unconditional", "disrupt"),
    "cloudnine": both("unconditional", "disrupt"),
    "aurabreak": both("unconditional", "disrupt"),
    "damp": both("unconditional", "disrupt"),
    "screencleaner": both("unconditional", "disrupt"),
    "persistent": both("unconditional", "support"),
    "teraformzero": both("triggered", "disrupt"),
    # Ruin
    "beadsofruin": both("unconditional", "disrupt"),
    "swordofruin": both("unconditional", "disrupt"),
    "tabletsofruin": both("unconditional", "disrupt"),
    "vesselofruin": both("unconditional", "disrupt"),
    # Ability ignore
    "moldbreaker": both("unconditional", "disrupt"),
    "teravolt": both("unconditional", "disrupt"),
    "turboblaze": both("unconditional", "disrupt"),
    "myceliummight": [
        T("ally", "unconditional", "disrupt"),
        T("opponent", "unconditional", "disrupt"),
        T("self", "unconditional", "disrupt"),
    ],
    "cottondown": both("triggered", "disrupt"),
    # Compound self + field/redirect
    "hadronengine": [
        *both("unconditional", "support"),
        T("self", "unconditional", "boost"),
    ],
    "orichalcumpulse": [
        *both("unconditional", "support"),
        T("self", "unconditional", "boost"),
    ],
    "flowergift": [
        T("self", "triggered", "boost"),
        T("ally", "triggered", "boost"),
    ],
    "lightningrod": [
        T("self", "unconditional", "support"),
        T("self", "triggered", "boost"),
        T("ally", "triggered", "support"),
    ],
    "stormdrain": [
        T("self", "unconditional", "support"),
        T("self", "triggered", "boost"),
        T("ally", "triggered", "support"),
    ],
    "magicbounce": [
        T("self", "unconditional", "support"),
        T("opponent", "triggered", "disrupt"),
    ],
    "rebound": [
        T("self", "unconditional", "support"),
        T("opponent", "triggered", "disrupt"),
    ],
    "asoneglastrier": [
        T("opponent", "unconditional", "disrupt"),
        T("self", "triggered", "boost"),
    ],
    "asonespectrier": [
        T("opponent", "unconditional", "disrupt"),
        T("self", "triggered", "boost"),
    ],
    "neutralizinggas": both("unconditional", "disrupt"),
    # Newly resolved flags
    "darkaura": both("unconditional", "boost"),
    "fairyaura": both("unconditional", "boost"),
    "illusion": [T("opponent", "unconditional", "disrupt")],
    "commander": [
        T("ally", "unconditional", "boost"),
        T("self", "unconditional", "disrupt"),
        T("opponent", "unconditional", "disrupt"),
    ],
    "curiousmedicine": [T("ally", "unconditional", "support")],
    "fluffy": [
        T("self", "triggered", "support"),
        T("self", "triggered", "disrupt"),
    ],
    "dryskin": [
        T("self", "triggered", "support"),
        T("self", "triggered", "disrupt"),
    ],
    "dancer": [T("self", "unconditional", "support")],
    "rivalry": [
        T("self", "triggered", "boost"),
        T("self", "triggered", "disrupt"),
    ],
    "gulpmissile": [T("opponent", "triggered", "disrupt")],
    "heavymetal": [
        T("self", "unconditional", "boost"),
        T("self", "unconditional", "support"),
        T("self", "unconditional", "disrupt"),
    ],
    "lightmetal": [
        T("self", "unconditional", "disrupt"),
        T("self", "unconditional", "support"),
    ],
    "noguard": [
        T("self", "unconditional", "boost"),
        T("self", "unconditional", "disrupt"),
    ],
    "perishbody": [
        T("opponent", "triggered", "disrupt"),
        T("self", "triggered", "disrupt"),
    ],
    "wanderingspirit": [
        T("opponent", "triggered", "disrupt"),
        T("self", "triggered", "support"),
    ],
}

INTENTIONAL_EMPTY: dict[str, str] = {
    "noability": "no_competitive_effect",
    "ballfetch": "no_competitive_effect",
    "honeygather": "no_competitive_effect",
    "runaway": "no_competitive_effect",
    "schooling": "forme_primary_excluded",
    "shieldsdown": "forme_primary_excluded",
    "stancechange": "forme_primary_excluded",
    "zenmode": "forme_primary_excluded",
    "zerotohero": "forme_primary_excluded",
    "hungerswitch": "forme_primary_excluded",
    "terashift": "forme_primary_excluded",
    "powerconstruct": "forme_primary_excluded",
    "asone": "placeholder_see_forme_variants",
}


def main() -> None:
    data = json.loads(PATH.read_text())
    abilities: dict = data["abilities"]

    # Snapshot who had other before
    had_other = {
        aid
        for aid, e in abilities.items()
        if any(t.get("target") == "other" for t in (e.get("tags") or []))
    }

    missing = had_other - set(FULL)
    if missing:
        raise SystemExit(f"had other but not in FULL remap: {sorted(missing)}")

    for aid, tags in FULL.items():
        if aid not in abilities:
            raise SystemExit(f"unknown id in FULL: {aid}")
        abilities[aid]["tags"] = tags
        # clear stale notes on tagged abilities
        abilities[aid].pop("note", None)

    for aid, note in INTENTIONAL_EMPTY.items():
        if aid not in abilities:
            raise SystemExit(f"unknown intentional empty: {aid}")
        abilities[aid]["tags"] = []
        abilities[aid]["note"] = note
        abilities[aid].pop("composed_of", None)
        abilities[aid].pop("provisional_purpose", None)
        # keep field if any — none on these

    # Fail-closed: no other
    still_other = [
        aid
        for aid, e in abilities.items()
        if any(t.get("target") == "other" for t in (e.get("tags") or []))
    ]
    if still_other:
        raise SystemExit(f"target=other remains: {still_other}")

    empty = {aid for aid, e in abilities.items() if not e.get("tags")}
    if empty != set(INTENTIONAL_EMPTY):
        raise SystemExit(
            f"empty set mismatch:\n"
            f"  unexpected empty: {sorted(empty - set(INTENTIONAL_EMPTY))}\n"
            f"  missing empty: {sorted(set(INTENTIONAL_EMPTY) - empty)}"
        )

    data["meta"]["taxonomy_status"] = "approved"
    data["meta"]["taxonomy"] = "target_activation_purpose_v1"
    data["meta"]["target_axis"] = ["self", "ally", "opponent"]
    data["meta"]["phase_b"] = {
        "flags_open": 0,
        "intentional_empties": len(INTENTIONAL_EMPTY),
        "prankster_class_ids": ["galewings", "prankster", "quickdraw", "triage"],
        "prankster_class_count": 4,
        "prankster_recommendation": "fold_into_boost",
    }

    PATH.write_text(json.dumps(data, indent=2) + "\n")

    REPORT.write_text(
        "\n".join(
            [
                "# Ability classification — intentional empties",
                "",
                "**taxonomy_status:** `approved`",
                "",
                "Target axis: `self` | `ally` | `opponent` (no `other`; multi-tag when multiple parties).",
                "",
                "## Intentional empties (not pending resolution)",
                "",
                *[
                    f"- `{aid}` — `{note}`"
                    for aid, note in sorted(INTENTIONAL_EMPTY.items(), key=lambda x: x[1] + x[0])
                ],
                "",
            ]
        )
    )
    PROPOSAL.write_text(
        "\n".join(
            [
                "# Ability taxonomy (approved)",
                "",
                "**Status:** `approved`",
                "",
                "**Axes:** `target` ∈ {self, ally, opponent}; `activation` ∈ {unconditional, triggered}; "
                "`purpose` ∈ {boost, support, disrupt}. Multi-tag when multiple parties/effects.",
                "",
                f"**Coverage:** {len(abilities)} abilities; "
                f"{len(abilities) - len(INTENTIONAL_EMPTY)} tagged; "
                f"{len(INTENTIONAL_EMPTY)} intentional empties.",
                "",
                "**Prankster-class:** 4 → fold into `boost` (provisional_purpose may remain on those four).",
                "",
                "See `ability_phase_b_flags.md` for intentional-empty notes.",
                "",
                "**Not written to ADRs / master log** (flag: target triad; aura ally+opponent multi-tag; cheap-search calibration).",
                "",
            ]
        )
    )
    print(
        f"retargeted FULL={len(FULL)} empties={len(INTENTIONAL_EMPTY)} "
        f"had_other={len(had_other)} status=approved"
    )


if __name__ == "__main__":
    main()
