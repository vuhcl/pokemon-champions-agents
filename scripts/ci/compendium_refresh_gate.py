"""Usage-event + spacing gate for PR-gated Role Compendium refresh (ADR-019a)."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from recommender.legality import load_snapshot
from recommender.role_compendium import (
    BULK_UP_ATTACKER_CRITERIA,
    CALM_MIND_ATTACKER_CRITERIA,
    DRAGON_DANCE_ATTACKER_CRITERIA,
    ELECTRIC_TERRAIN_SETTER_CRITERIA,
    GRASSY_TERRAIN_SETTER_CRITERIA,
    IRON_DEFENSE_BODY_PRESS_CRITERIA,
    NASTY_PLOT_ATTACKER_CRITERIA,
    PSYCHIC_TERRAIN_SETTER_CRITERIA,
    RAIN_SETTER_CRITERIA,
    REDIRECTION_CRITERIA,
    SAND_SETTER_CRITERIA,
    SCREENS_SUPPORT_CRITERIA,
    SLEEP_STATUS_SPREADER_CRITERIA,
    SNOW_SETTER_CRITERIA,
    SUN_SETTER_CRITERIA,
    SWORDS_DANCE_ATTACKER_CRITERIA,
    TAILWIND_SETTER_CRITERIA,
    TRICK_ROOM_SETTER_CRITERIA,
    RoleConstructionDraft,
    construct_role_category,
    critique_role_ranking,
    legal_species_pool,
    persist_approved,
)
from recommender.role_compendium_read import (
    DEFAULT_ROLES_DIR,
    ROLE_TIER_ORDER,
    _roles_filename,
    load_prior_compendium,
)

ROOT = Path(__file__).resolve().parents[2]
USAGE_PATH = ROOT / "data" / "usage" / "champions-reg-mc.v1.json"
MARKER_PATH = ROOT / "data" / "roles" / "fixtures" / "compendium_refresh_marker.json"
MIN_SPACING_DAYS = 14

# Explicit 18 — do not scrape globals.
COMPENDIUM_CATEGORIES: list[tuple[str, dict[str, Any]]] = [
    ("weather_setter", RAIN_SETTER_CRITERIA),
    ("weather_setter", SUN_SETTER_CRITERIA),
    ("weather_setter", SAND_SETTER_CRITERIA),
    ("weather_setter", SNOW_SETTER_CRITERIA),
    ("terrain_setter", ELECTRIC_TERRAIN_SETTER_CRITERIA),
    ("terrain_setter", GRASSY_TERRAIN_SETTER_CRITERIA),
    ("terrain_setter", PSYCHIC_TERRAIN_SETTER_CRITERIA),
    ("redirection", REDIRECTION_CRITERIA),
    ("trick_room_setter", TRICK_ROOM_SETTER_CRITERIA),
    ("tailwind_setter", TAILWIND_SETTER_CRITERIA),
    ("sleep_status_spreader", SLEEP_STATUS_SPREADER_CRITERIA),
    ("screens_support", SCREENS_SUPPORT_CRITERIA),
    ("swords_dance_attacker", SWORDS_DANCE_ATTACKER_CRITERIA),
    ("nasty_plot_attacker", NASTY_PLOT_ATTACKER_CRITERIA),
    ("calm_mind_attacker", CALM_MIND_ATTACKER_CRITERIA),
    ("bulk_up_attacker", BULK_UP_ATTACKER_CRITERIA),
    ("dragon_dance_attacker", DRAGON_DANCE_ATTACKER_CRITERIA),
    ("iron_defense_body_press", IRON_DEFENSE_BODY_PRESS_CRITERIA),
]


def write_github_output(path: Path | None, fields: dict[str, str]) -> None:
    if path is None:
        return
    with path.open("a", encoding="utf-8") as f:
        for k, v in fields.items():
            f.write(f"{k}={v}\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def usage_fingerprint(usage_path: Path = USAGE_PATH) -> str | None:
    if not usage_path.exists():
        return None
    meta = (load_json(usage_path).get("meta") or {})
    raw = meta.get("munchstats_generated_at")
    return str(raw) if raw else None


def load_marker(path: Path = MARKER_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "last_check_at": None,
            "usage_munchstats_generated_at": None,
            "usage_path": str(USAGE_PATH.relative_to(ROOT)),
            "last_outcome": None,
        }
    return load_json(path)


def write_marker(marker: dict[str, Any], path: Path = MARKER_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")


def should_run_check(
    *,
    now: datetime,
    marker: dict[str, Any],
    usage_gen: str | None,
    force: bool = False,
    spacing_days: int = MIN_SPACING_DAYS,
) -> tuple[bool, str]:
    if force:
        return True, "force"
    if not usage_gen:
        return False, "usage_fingerprint_missing"
    prev = marker.get("usage_munchstats_generated_at")
    prev_dt = _parse_iso(str(prev) if prev else None)
    new_dt = _parse_iso(usage_gen)
    if new_dt is None:
        return False, "usage_fingerprint_unparseable"
    if prev_dt is not None and new_dt <= prev_dt:
        return False, "usage_not_newer_than_last_clear_check"
    last = _parse_iso(str(marker.get("last_check_at") or "") or None)
    if last is not None:
        days = (now.date() - last.date()).days
        if days < spacing_days:
            return False, f"spacing_{days}_lt_{spacing_days}"
    return True, "usage_newer_and_spacing_ok"


def _tier_map(tiers: dict[str, Any] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for tier in ROLE_TIER_ORDER:
        for name in (tiers or {}).get(tier) or []:
            out[str(name)] = tier
    return out


def category_semantic_diff(
    prior: dict[str, Any] | None, draft: RoleConstructionDraft
) -> dict[str, Any]:
    """Membership/tier diff ignoring built_at."""
    disk_map = _tier_map((prior or {}).get("tiers") if prior else None)
    live_map = _tier_map(draft.tiers)
    admitted_new = sorted(set(live_map) - set(disk_map))
    dropped = sorted(set(disk_map) - set(live_map))
    tier_changed = sorted(
        s for s in set(disk_map) & set(live_map) if disk_map[s] != live_map[s]
    )
    reasons = {
        c.species: c.change_reason
        for c in draft.candidates
        if c.tier and c.species in tier_changed
    }
    return {
        "disk_admitted": len(disk_map),
        "live_admitted": len(live_map),
        "admitted_new": [{"species": s, "tier": live_map[s]} for s in admitted_new],
        "dropped": [{"species": s, "tier": disk_map[s]} for s in dropped],
        "tier_changed": [
            {
                "species": s,
                "disk": disk_map[s],
                "live": live_map[s],
                "change_reason": reasons.get(s),
            }
            for s in tier_changed
        ],
        "has_diff": bool(admitted_new or dropped or tier_changed),
    }


def run_offline_rebuild(
    *,
    roles_dir: Path = DEFAULT_ROLES_DIR,
    regulation: str = "champions",
    categories: list[tuple[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Construct+critique all categories; persist only if every category clears."""
    cats = categories or COMPENDIUM_CATEGORIES
    snap = load_snapshot()
    pool = legal_species_pool(snap)
    built: list[tuple[str, dict[str, Any], RoleConstructionDraft, Any, Path]] = []
    report_cats: dict[str, Any] = {}
    any_flags = False

    for category, criteria in cats:
        path = roles_dir / _roles_filename(category, criteria)
        prior = load_prior_compendium(path)
        draft = construct_role_category(
            category,
            criteria,
            pool,
            snap=snap,
            reference_compendium=prior,
            live_fetch=None,
            showdown_fetch=None,
            regulation=regulation,
        )
        critique = critique_role_ranking(draft, reference_compendium=prior)
        label = path.name.replace(".v1.json", "")
        diff = category_semantic_diff(prior, draft)
        flags = [
            {
                "principle": f.principle,
                "candidates": list(f.candidates),
                "detail": f.detail,
            }
            for f in critique.flags
        ]
        report_cats[label] = {
            "label": label,
            "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            "disk_exists": prior is not None,
            "admitted": diff["live_admitted"],
            "disk_admitted": diff["disk_admitted"],
            "rejected": len(draft.considered_rejected),
            "tiers": {t: list(draft.tiers.get(t) or []) for t in ROLE_TIER_ORDER},
            "diff": diff,
            "critic_approved": critique.approved,
            "critic_flag_count": len(flags),
            "critic_flags": flags,
        }
        if not critique.approved:
            any_flags = True
        built.append((category, criteria, draft, critique, path))

    if any_flags:
        return {
            "status": "needs_revision",
            "categories": report_cats,
            "has_semantic_diff": any(
                report_cats[k]["diff"]["has_diff"] for k in report_cats
            ),
        }

    for _category, _criteria, draft, _critique, _path in built:
        persist_approved(draft, roles_dir)

    return {
        "status": "approved",
        "categories": report_cats,
        "has_semantic_diff": any(
            report_cats[k]["diff"]["has_diff"] for k in report_cats
        ),
    }


def run_gate(
    *,
    now: datetime | None = None,
    force: bool = False,
    github_output: Path | None = None,
    marker_path: Path = MARKER_PATH,
    usage_path: Path = USAGE_PATH,
    roles_dir: Path = DEFAULT_ROLES_DIR,
    report_out: Path | None = None,
    rebuild_fn=run_offline_rebuild,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    marker = load_marker(marker_path)
    usage_gen = usage_fingerprint(usage_path)
    result: dict[str, Any] = {
        "checked_at_utc": now.isoformat().replace("+00:00", "Z"),
        "usage_munchstats_generated_at": usage_gen,
        "usage_path": str(usage_path.relative_to(ROOT))
        if usage_path.is_relative_to(ROOT)
        else str(usage_path),
    }

    run, reason = should_run_check(
        now=now, marker=marker, usage_gen=usage_gen, force=force
    )
    result["gate_reason"] = reason
    if not run:
        result["decision"] = "noop"
        result["reason"] = reason
        result["bump_marker"] = False
        write_github_output(
            github_output,
            {
                "decision": "noop",
                "reason": reason,
                "bump_marker": "false",
            },
        )
        return result

    report = rebuild_fn(roles_dir=roles_dir)
    result["rebuild_status"] = report["status"]
    result["has_semantic_diff"] = bool(report.get("has_semantic_diff"))
    if report_out is not None:
        payload = {
            "checked_at_utc": result["checked_at_utc"],
            "usage_munchstats_generated_at": usage_gen,
            "usage_path": result["usage_path"],
            "status": report["status"],
            "categories": report["categories"],
        }
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        result["report_path"] = str(report_out)

    iso_now = now.isoformat().replace("+00:00", "Z")
    if report["status"] == "needs_revision":
        marker.update(
            {
                "last_check_at": iso_now,
                "last_outcome": "fail_flags",
                "usage_path": result["usage_path"],
            }
        )
        # Do not advance usage fingerprint — same event stays eligible after force.
        write_marker(marker, marker_path)
        result["decision"] = "fail"
        result["reason"] = "critic_flags"
        result["bump_marker"] = True
        write_github_output(
            github_output,
            {
                "decision": "fail",
                "reason": "critic_flags",
                "bump_marker": "true",
            },
        )
        return result

    marker.update(
        {
            "last_check_at": iso_now,
            "usage_munchstats_generated_at": usage_gen,
            "usage_path": result["usage_path"],
            "last_outcome": (
                "pr_opened" if report.get("has_semantic_diff") else "noop_no_diff"
            ),
        }
    )
    write_marker(marker, marker_path)
    result["bump_marker"] = True

    if report.get("has_semantic_diff"):
        result["decision"] = "pr"
        result["reason"] = "critic_clear_with_diffs"
        write_github_output(
            github_output,
            {
                "decision": "pr",
                "reason": result["reason"],
                "bump_marker": "true",
                "report_path": str(report_out or ""),
            },
        )
        return result

    result["decision"] = "marker_only"
    result["reason"] = "critic_clear_no_semantic_diff"
    write_github_output(
        github_output,
        {
            "decision": "marker_only",
            "reason": result["reason"],
            "bump_marker": "true",
        },
    )
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--github-output", type=Path, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--report-out", type=Path, default=None)
    p.add_argument("--out-json", type=Path, default=None)
    p.add_argument("--marker", type=Path, default=MARKER_PATH)
    p.add_argument("--usage", type=Path, default=USAGE_PATH)
    p.add_argument("--roles-dir", type=Path, default=DEFAULT_ROLES_DIR)
    args = p.parse_args(argv)

    gh_out = args.github_output
    if gh_out is None:
        env = os.environ.get("GITHUB_OUTPUT")
        if env:
            gh_out = Path(env)

    result = run_gate(
        force=args.force,
        github_output=gh_out,
        marker_path=args.marker,
        usage_path=args.usage,
        roles_dir=args.roles_dir,
        report_out=args.report_out,
    )
    if args.out_json:
        args.out_json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    # Always exit 0 — workflow fails the job on decision=fail after marker commit.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
