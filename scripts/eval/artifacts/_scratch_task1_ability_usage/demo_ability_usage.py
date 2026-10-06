"""Scratch: Task 1 ability dual-read demos (non-modal grants, IG≠SD modal, churn).

Writes report.md + report.json under this directory. Does not touch data/roles.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recommender.ability_classification import (
    flinch_denial_ability_ids,
    priority_denial_ability_ids,
    taunt_denial_ability_ids,
)
from recommender.forme_identity import canonical_usage_species_id
from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium import (
    _ability_share_pcts,
    _effective_ability_for_predicate,
    _modal_ability_map,
    _species_abilities,
    _usage_ability_map,
    construct_role_category,
    legal_species_pool,
)
from recommender.role_compendium_read import _roles_filename
from recommender.usage_data import ingame_species_map, showdown_species_map
from scripts.ci.compendium_refresh_gate import COMPENDIUM_CATEGORIES

REG = "champions-reg-mc"
OUT = Path(__file__).resolve().parent


def _modal_from(entry: dict[str, Any] | None, legal: dict[str, str]) -> str | None:
    if not entry:
        return None
    best = -1.0
    winners: list[str] = []
    for row in entry.get("common_abilities") or []:
        aid = to_id(row.get("name") or "")
        if aid not in legal:
            continue
        pct = float(row.get("pct") or 0.0)
        if pct > best:
            best = pct
            winners = [aid]
        elif pct == best:
            winners.append(aid)
    return sorted(winners)[0] if winners else None


def _tier_basis_map(draft: Any) -> dict[str, tuple[str, str]]:
    return {
        c.species: (c.tier, str(c.excellence_basis or ""))
        for c in draft.candidates
        if c.tier
    }


def _members(draft: Any) -> set[str]:
    return {c.species for c in draft.candidates if c.tier}


def main() -> None:
    snap = load_snapshot()
    pool = legal_species_pool(snap)
    ig = ingame_species_map(REG)
    sd = showdown_species_map(REG)

    cats = list(COMPENDIUM_CATEGORIES)

    # --- Source disagreement: IG modal ≠ SD modal ---
    disagreements: list[dict[str, Any]] = []
    for name in pool:
        sid = to_id(name)
        legal = _species_abilities(snap, sid)
        if not legal:
            continue
        canon = canonical_usage_species_id(snap, sid, regulation=REG)
        ig_m = _modal_from(ig.get(canon), legal)
        sd_m = _modal_from(sd.get(canon), legal)
        if ig_m and sd_m and ig_m != sd_m:
            disagreements.append(
                {
                    "species": name,
                    "sid": sid,
                    "ingame_modal": ig_m,
                    "showdown_modal": sd_m,
                    "merged_modal": next(
                        iter(_modal_ability_map(snap, sid, regulation=REG))
                    ),
                    "shares": _ability_share_pcts(snap, sid, regulation=REG),
                }
            )
    disagreements.sort(key=lambda r: r["species"])

    # Current (split) drafts
    drafts_b: dict[str, Any] = {}
    for category, criteria in cats:
        label = _roles_filename(category, criteria).replace(".v1.json", "")
        drafts_b[label] = construct_role_category(
            category,
            criteria,
            pool,
            snap=snap,
            live_fetch=None,
            showdown_fetch=None,
            regulation=REG,
        )

    tr = drafts_b.get("trick_room_setter")
    tr_ids = {c.species_id for c in tr.candidates if c.tier} if tr else set()
    tr_dis = [d for d in disagreements if d["sid"] in tr_ids]

    setter_labels = [
        lb
        for lb in drafts_b
        if lb.endswith("_setter") or "terrain" in lb or lb in {"rain_setter", "sun_setter", "sand_setter", "snow_setter"}
    ]
    setter_ids: set[str] = set()
    for lb in setter_labels:
        setter_ids |= {c.species_id for c in drafts_b[lb].candidates if c.tier}
    setter_dis = [d for d in disagreements if d["sid"] in setter_ids]

    # Non-modal ≥10% grants (TR protection + weather/terrain setters + FG/Prankster)
    flinch = priority_denial_ability_ids()
    taunt = taunt_denial_ability_ids()
    non_modal: list[dict[str, Any]] = []
    for name in pool:
        sid = to_id(name)
        for path, pred in (
            ("tr_priority_denial", flinch),
            ("tr_taunt_denial", taunt),
            ("friend_guard", frozenset({"friendguard"})),
            ("prankster", frozenset({"prankster"})),
        ):
            amap, grant = _effective_ability_for_predicate(
                snap, sid, regulation=REG, predicate_ids=pred
            )
            if grant:
                modal = _modal_ability_map(snap, sid, regulation=REG)
                non_modal.append(
                    {
                        "species": name,
                        "sid": sid,
                        "path": path,
                        "granting": grant,
                        "modal": next(iter(modal), None),
                        "tier_assumed": next(iter(amap), None),
                        "shares": _ability_share_pcts(snap, sid, regulation=REG),
                    }
                )
    # Sand Spit / weather setters explicitly
    for name in pool:
        sid = to_id(name)
        for path, pred in (
            ("sand_spit", frozenset({"sandspit"})),
            ("drizzle", frozenset({"drizzle"})),
            ("drought", frozenset({"drought", "orichalcumpulse"})),
            ("sandstream", frozenset({"sandstream"})),
            ("snowwarning", frozenset({"snowwarning"})),
            ("electricsurge", frozenset({"electricsurge"})),
            ("grassysurge", frozenset({"grassysurge"})),
            ("psychicsurge", frozenset({"psychicsurge"})),
        ):
            amap, grant = _effective_ability_for_predicate(
                snap, sid, regulation=REG, predicate_ids=pred
            )
            if grant:
                modal = _modal_ability_map(snap, sid, regulation=REG)
                non_modal.append(
                    {
                        "species": name,
                        "sid": sid,
                        "path": path,
                        "granting": grant,
                        "modal": next(iter(modal), None),
                        "tier_assumed": next(iter(amap), None),
                        "shares": _ability_share_pcts(snap, sid, regulation=REG),
                    }
                )
    # de-dupe
    seen: set[tuple[str, str]] = set()
    uniq: list[dict[str, Any]] = []
    for row in non_modal:
        key = (row["sid"], row["path"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(row)
    uniq.sort(key=lambda r: (r["path"], r["species"]))

    # Membership churn / before-after: patch every module that imports the helpers.
    import recommender.role_compendium as rc
    import recommender.role_compendium_support as support
    import recommender.role_compendium_weather as weather
    import recommender.role_compendium_setup as setup

    targets = [rc, support, weather, setup]
    saved = {
        (mod, name): getattr(mod, name)
        for mod in targets
        for name in ("_usage_ability_map", "_modal_ability_map")
        if hasattr(mod, name)
    }

    def _install(usage_fn, modal_fn) -> None:
        for mod in targets:
            if hasattr(mod, "_usage_ability_map"):
                setattr(mod, "_usage_ability_map", usage_fn)
            if hasattr(mod, "_modal_ability_map"):
                setattr(mod, "_modal_ability_map", modal_fn)

    def _restore() -> None:
        for (mod, name), fn in saved.items():
            setattr(mod, name, fn)

    real_usage = saved[(rc, "_usage_ability_map")]
    real_modal = saved[(rc, "_modal_ability_map")]

    _install(
        lambda snap_, sid, *, regulation, floor=None: real_modal(
            snap_, sid, regulation=regulation
        ),
        real_modal,
    )
    try:
        drafts_modal: dict[str, Any] = {}
        for category, criteria in cats:
            label = _roles_filename(category, criteria).replace(".v1.json", "")
            drafts_modal[label] = construct_role_category(
                category,
                criteria,
                pool,
                snap=snap,
                live_fetch=None,
                showdown_fetch=None,
                regulation=REG,
            )
    finally:
        _restore()

    churn: dict[str, Any] = {}
    for label in drafts_b:
        a = _members(drafts_modal[label])
        b = _members(drafts_b[label])
        churn[label] = {
            "modal_only_count": len(a),
            "split_count": len(b),
            "added_by_split": sorted(b - a),
            "dropped_by_split": sorted(a - b),
        }

    def _full_legal(snap_, sid, *, regulation, floor=None):
        return _species_abilities(snap_, sid)

    # Pre-Task1: full legal slots + flinch-only denial (no Psychic Terrain credit).
    import recommender.ability_classification as ac
    import recommender.role_compendium_support as support_mod

    real_priority = ac.priority_denial_ability_ids
    real_support_priority = getattr(support_mod, "priority_denial_ability_ids", None)
    ac.priority_denial_ability_ids = ac.flinch_denial_ability_ids  # type: ignore[assignment]
    if real_support_priority is not None:
        support_mod.priority_denial_ability_ids = ac.flinch_denial_ability_ids  # type: ignore[assignment]
    _install(_full_legal, _full_legal)
    try:
        drafts_full: dict[str, Any] = {}
        for category, criteria in cats:
            label = _roles_filename(category, criteria).replace(".v1.json", "")
            drafts_full[label] = construct_role_category(
                category,
                criteria,
                pool,
                snap=snap,
                live_fetch=None,
                showdown_fetch=None,
                regulation=REG,
            )
    finally:
        _restore()
        ac.priority_denial_ability_ids = real_priority  # type: ignore[assignment]
        if real_support_priority is not None:
            support_mod.priority_denial_ability_ids = real_support_priority  # type: ignore[assignment]

    before_after: dict[str, Any] = {}
    for label in drafts_b:
        before = _tier_basis_map(drafts_full[label])
        after = _tier_basis_map(drafts_b[label])
        changed = []
        for sp in sorted(set(before) | set(after)):
            bt, at = before.get(sp), after.get(sp)
            if bt != at:
                changed.append(
                    {
                        "species": sp,
                        "before_tier": None if not bt else bt[0],
                        "before_basis": None if not bt else bt[1],
                        "after_tier": None if not at else at[0],
                        "after_basis": None if not at else at[1],
                    }
                )
        before_after[label] = {
            "n_before": len(before),
            "n_after": len(after),
            "changed": changed,
        }

    # Expected spotlight checks
    spotlight: dict[str, Any] = {}
    if tr:
        by = {c.species: c for c in tr.candidates if c.tier}
        for sp in ("Indeedee", "Indeedee-F"):
            c = by.get(sp)
            spotlight[sp] = (
                None
                if not c
                else {
                    "tier": c.tier,
                    "basis": c.excellence_basis,
                    "notes": (c.criteria_notes or {}).get("execution", "")[:200],
                }
            )
    sd_draft = drafts_b.get("swords_dance_attacker")
    if sd_draft:
        kg = next((c for c in sd_draft.candidates if c.species == "Kingambit"), None)
        spotlight["Kingambit"] = (
            None
            if not kg
            else {
                "tier": kg.tier,
                "basis": kg.excellence_basis,
                "notes": (kg.criteria_notes or {}).get("execution", "")[:200],
            }
        )
    redir = drafts_b.get("redirection")
    if redir:
        viv = next((c for c in redir.candidates if c.species == "Vivillon"), None)
        spotlight["Vivillon"] = (
            None
            if not viv
            else {
                "tier": viv.tier,
                "basis": viv.excellence_basis,
                "has_friend_guard_trait": any(
                    to_id(t.name) == "friendguard" for t in viv.claimed_traits
                ),
            }
        )

    report = {
        "regulation": REG,
        "n_disagreements": len(disagreements),
        "disagreements": disagreements,
        "tr_disagreements": tr_dis,
        "setter_disagreements": setter_dis,
        "non_modal_grants": uniq,
        "membership_churn_modal_vs_split": churn,
        "before_after_full_slots_vs_split": before_after,
        "spotlight": spotlight,
        "flinch_denial_count": len(flinch_denial_ability_ids()),
        "priority_denial_count": len(priority_denial_ability_ids()),
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    lines = [
        "# Task 1 ability-usage scratch demo",
        "",
        f"Regulation: `{REG}`",
        "",
        "## Spotlight",
        "",
        "```json",
        json.dumps(spotlight, indent=2),
        "```",
        "",
        f"## IG vs SD modal disagreements ({len(disagreements)})",
        "",
    ]
    if tr_dis or setter_dis:
        lines.append(
            "**TR/setter disagreements present — propose Showdown-prefer tie-break "
            "before changing the max(ig,sd) merger.**"
        )
        lines.append("")
        for row in tr_dis + setter_dis:
            lines.append(
                f"- {row['species']}: IG `{row['ingame_modal']}` vs SD "
                f"`{row['showdown_modal']}` → merged `{row['merged_modal']}`"
            )
        lines.append("")
    else:
        lines.append(
            "No TR candidates or weather/terrain setters on the disagreement list "
            "under current max(ig,sd) modal. No tie-break change proposed."
        )
        lines.append("")
    lines.append("| Species | IG modal | SD modal | Merged |")
    lines.append("|---|---|---|---|")
    for row in disagreements[:40]:
        lines.append(
            f"| {row['species']} | {row['ingame_modal']} | {row['showdown_modal']} | "
            f"{row['merged_modal']} |"
        )
    if len(disagreements) > 40:
        lines.append(f"| … | ({len(disagreements) - 40} more) | | |")
    lines.extend(["", "## Non-modal ≥10% grants (tier assumes granting ability)", ""])
    lines.append("| Species | Path | Granting | Modal |")
    lines.append("|---|---|---|---|")
    for row in uniq:
        lines.append(
            f"| {row['species']} | {row['path']} | {row['granting']} | {row['modal']} |"
        )
    lines.extend(
        [
            "",
            "## Vivillon Excellent path (not Friend Guard)",
            "",
            "Friend Guard share is below the 10% membership floor, so it is absent from",
            "`_usage_ability_map` and is not an admit/excellence ability path.",
            "Vivillon stays Excellent via `excellence_basis=secondary_stack`: usage-proven",
            "Rage Powder delivery plus closed Excellent secondary **moves** Tailwind and",
            "Light Screen (`_REDIRECTION_EXCELLENT_SECONDARY_MOVES`). That path is",
            "move-usage only — it does **not** rely on a non-modal ability.",
            "",
            "## Membership churn (modal-only admit vs split ≥10%) — all 18",
            "",
            "| Category | Modal-only n | Split n | Added by split | Dropped by split |",
            "|---|---:|---:|---|---|",
        ]
    )
    for label, row in sorted(churn.items()):
        add = ", ".join(row["added_by_split"]) or "—"
        drop = ", ".join(row["dropped_by_split"]) or "—"
        lines.append(
            f"| {label} | {row['modal_only_count']} | {row['split_count']} | {add} | {drop} |"
        )
    lines.extend(
        [
            "",
            "## Before/after (full legal + flinch-only → split + Psychic Terrain) — all 18",
            "",
        ]
    )
    for label, row in sorted(before_after.items()):
        lines.append(f"### {label} ({row['n_before']} → {row['n_after']})")
        if not row["changed"]:
            lines.append("- (no tier/basis changes)")
        else:
            for ch in row["changed"]:
                lines.append(
                    f"- {ch['species']}: {ch['before_tier']}/{ch['before_basis']} → "
                    f"{ch['after_tier']}/{ch['after_basis']}"
                )
        lines.append("")
    (OUT / "report.md").write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT / 'report.md'} disagreements={len(disagreements)} non_modal={len(uniq)}")


if __name__ == "__main__":
    main()
