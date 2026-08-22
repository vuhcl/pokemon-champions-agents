"""Deterministic soft review flags for provisional-slot edits."""

from __future__ import annotations

from typing import Literal

from recommender.ids import to_id
from recommender.propose import scarf_clears_benchmarks
from recommender.state import ProvisionalSlot, RecommenderState, ReviewFlag

StatName = Literal["atk", "def", "spa", "spd", "spe"]

# All 25 natures → (plus_stat | None, minus_stat | None). HP is never boosted/hindered.
# Regression, confirmed live (2026-08-21): Jolly was listed as ("spe", "atk")
# -- an exact duplicate of Timid's row -- when Jolly's real minus-stat is
# "spa", not "atk". Jolly is one of the most common physical-attacker
# natures in the game specifically because it leaves Attack untouched; the
# bug caused collect_provisional_review_flags to falsely warn "Nature Jolly
# conflicts with physical role" for a nature that never conflicts with a
# physical role at all. Every other entry checked directly against the real
# nature chart and confirmed correct -- this was an isolated, single-row
# copy-paste error, not a systematic table problem.
_NATURE_MODIFIERS: dict[str, tuple[StatName | None, StatName | None]] = {
    "Hardy": (None, None),
    "Docile": (None, None),
    "Serious": (None, None),
    "Bashful": (None, None),
    "Quirky": (None, None),
    "Lonely": ("atk", "def"),
    "Adamant": ("atk", "spa"),
    "Naughty": ("atk", "spd"),
    "Brave": ("atk", "spe"),
    "Bold": ("def", "atk"),
    "Impish": ("def", "spa"),
    "Lax": ("def", "spd"),
    "Relaxed": ("def", "spe"),
    "Modest": ("spa", "atk"),
    "Mild": ("spa", "def"),
    "Rash": ("spa", "spd"),
    "Quiet": ("spa", "spe"),
    "Calm": ("spd", "atk"),
    "Gentle": ("spd", "def"),
    "Careful": ("spd", "spa"),
    "Sassy": ("spd", "spe"),
    "Timid": ("spe", "atk"),
    "Hasty": ("spe", "def"),
    "Jolly": ("spe", "spa"),
    "Naive": ("spe", "spd"),
}

_OFFENSE_AMP_ITEMS = frozenset(
    {"lifeorb", "expertbelt", "muscleband", "wiseglasses"}
)


def nature_stat_modifiers(
    nature: str,
) -> tuple[StatName | None, StatName | None]:
    return _NATURE_MODIFIERS.get(nature, (None, None))


def collect_provisional_review_flags(
    provisional: ProvisionalSlot,
    state: RecommenderState,
    *,
    edited_fields: frozenset[str] = frozenset(),
) -> tuple[ReviewFlag, ...]:
    """Soft, non-blocking. Never raises. Empty tuple is valid."""
    del edited_fields  # reserved for callers; full suite is cheap
    try:
        flags: list[ReviewFlag] = []
        spread = provisional.spread_dict()
        item_id = to_id(provisional.item)
        plus, minus = nature_stat_modifiers(provisional.nature)

        if minus is not None and int(spread.get(minus, 0)) > 0:
            flags.append(
                {
                    "claim": (
                        f"EVs invested in {minus.upper()}, which {provisional.nature} hinders"
                    ),
                    "check": "ev_into_nature_hindered",
                    "basis": "deterministic",
                    "fields": ("nature", "spread"),
                }
            )

        role_id = provisional.role
        if role_id.endswith("_physical_attacker"):
            if plus == "spa" or minus == "atk":
                flags.append(
                    {
                        "claim": (
                            f"Nature {provisional.nature} conflicts with physical role {role_id}"
                        ),
                        "check": "nature_axis_role_mismatch",
                        "basis": "deterministic",
                        "fields": ("nature",),
                    }
                )
        elif role_id.endswith("_special_attacker"):
            if plus == "atk" or minus == "spa":
                flags.append(
                    {
                        "claim": (
                            f"Nature {provisional.nature} conflicts with special role {role_id}"
                        ),
                        "check": "nature_axis_role_mismatch",
                        "basis": "deterministic",
                        "fields": ("nature",),
                    }
                )
        elif role_id.endswith("_mixed_attacker"):
            if minus in {"atk", "spa"} and plus in {"def", "spd", "spe"}:
                flags.append(
                    {
                        "claim": (
                            f"Nature {provisional.nature} hinders an offense stat on mixed role"
                        ),
                        "check": "nature_axis_role_mismatch",
                        "basis": "deterministic",
                        "fields": ("nature",),
                    }
                )

        if item_id == "focussash" and int(spread.get("hp", 0)) >= 20:
            flags.append(
                {
                    "claim": "Focus Sash with HP≥20 reads tanky for a glass item",
                    "check": "item_spread_glass_tanky",
                    "basis": "deterministic",
                    "fields": ("item", "spread"),
                }
            )

        atk = int(spread.get("atk", 0))
        spa = int(spread.get("spa", 0))
        if item_id in _OFFENSE_AMP_ITEMS and atk == 0 and spa == 0:
            flags.append(
                {
                    "claim": f"{provisional.item} with zero Atk and SpA investment",
                    "check": "item_spread_offense_amp_zero_ev",
                    "basis": "deterministic",
                    "fields": ("item", "spread"),
                }
            )

        if item_id == "muscleband" and spa > 0 and atk == 0:
            flags.append(
                {
                    "claim": "Muscle Band with SpA-only investment",
                    "check": "item_spread_category_boost_wrong_stat",
                    "basis": "deterministic",
                    "fields": ("item", "spread"),
                }
            )
        if item_id == "wiseglasses" and atk > 0 and spa == 0:
            flags.append(
                {
                    "claim": "Wise Glasses with Atk-only investment",
                    "check": "item_spread_category_boost_wrong_stat",
                    "basis": "deterministic",
                    "fields": ("item", "spread"),
                }
            )

        if item_id == "ironball" and int(spread.get("spe", 0)) > 0:
            flags.append(
                {
                    "claim": "Iron Ball with Speed investment",
                    "check": "item_spread_iron_ball_speed",
                    "basis": "deterministic",
                    "fields": ("item", "spread"),
                }
            )

        if item_id == "choicescarf" and plus == "spe":
            offensive = "Adamant" if atk >= spa else "Modest"
            slot = provisional.to_slot(locked=False, reason=None)
            if scarf_clears_benchmarks(slot, state, nature=offensive):
                flags.append(
                    {
                        "claim": (
                            "Choice Scarf already clears Spe benchmarks with an "
                            f"offensive nature; {provisional.nature} overshoots Speed"
                        ),
                        "check": "scarf_nature_overshoot",
                        "basis": "deterministic",
                        "fields": ("item", "nature", "spread"),
                    }
                )

        return tuple(flags)
    except Exception:
        return ()
