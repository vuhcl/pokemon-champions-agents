#!/usr/bin/env python3
"""Calc artifact coverage: every key calc_id must have a saved file; report call inventory."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
CALC = PKG / "key_artifacts" / "calc"
KEYS = PKG / "key_artifacts" / "derived_keys.json"
REPORT = PKG / "key_artifacts" / "calc_coverage.json"


def main() -> int:
    saved = {p.stem: p for p in CALC.glob("*.json")}
    keys = json.loads(KEYS.read_text())
    text = json.dumps(keys)

    ids_in_keys = set(re.findall(r'"calc_id":\s*"([^"]+)"', text))
    ids_in_keys |= set(re.findall(r'"artifact_id":\s*"([^"]+)"', text))

    # H12: every candidate move × nature for each threat must be on disk
    h12 = (keys.get("h12_sinistcha_calm_vs_bold") or {}).get("variant_a") or {}
    def _move_id(c: dict) -> str:
        if c.get("id"):
            return str(c["id"])
        name = c.get("name") or c.get("move") or ""
        return "".join(ch for ch in name.lower() if ch.isalnum())

    h12_expected: list[str] = []
    for t in h12.get("per_threat") or []:
        tid = t.get("threat_id")
        if not tid:
            continue
        for c in t.get("candidate_moves") or []:
            cid = _move_id(c)
            if not cid:
                continue
            for nat in ("calm", "bold"):
                h12_expected.append(f"h12_A_{tid}_{cid}_{nat}")
    h12_probes = [
        "h12_probe_ef_doubles_pt",
        "h12_probe_ef_singles_pt",
        "h12_probe_wb_politoed_dry",
        "h12_probe_wb_politoed_rain",
    ]

    required = set(ids_in_keys) | set(h12_expected) | set(h12_probes)
    missing = sorted(required - set(saved))

    # DM4 min_atk: require winner calc_id and full search ladder files when present in keys
    dm4 = ((keys.get("dm_outputs") or {}).get("dm4") or {}).get("incineroar_defender") or {}
    dm4_search_missing = []
    dm4_search_files = sorted(p for p in saved if "_min_atk" in p)
    for case in (dm4.get("cases") or {}).values() if isinstance(dm4.get("cases"), dict) else []:
        if not isinstance(case, dict):
            continue
        for sub in case.values():
            if not isinstance(sub, dict):
                continue
            detail = sub.get("min_atk_sp_detail") or {}
            winner_id = detail.get("calc_id")
            if winner_id and winner_id not in saved:
                dm4_search_missing.append(winner_id)
            # Every persisted search step for this prefix must exist when winner exists
            if winner_id and "_min_atk" in winner_id:
                prefix = winner_id.rsplit("_atk", 1)[0]
                sp = detail.get("min_atk_sp")
                if isinstance(sp, int):
                    for i in range(0, sp + 1):
                        aid = f"{prefix}_atk{i}"
                        if aid not in saved:
                            dm4_search_missing.append(aid)

    # Contiguous ladder 0..max_sp for each dm4_*_min prefix on disk (no gaps)
    prefixes = {p.rsplit("_atk", 1)[0] for p in dm4_search_files if "_atk" in p}
    for prefix in sorted(prefixes):
        sps = []
        for s in saved:
            if s.startswith(prefix + "_atk"):
                try:
                    sps.append(int(s.rsplit("_atk", 1)[1]))
                except ValueError:
                    pass
        if not sps:
            continue
        for i in range(0, max(sps) + 1):
            aid = f"{prefix}_atk{i}"
            if aid not in saved:
                dm4_search_missing.append(aid)

    coverage = {
        "artifacts_saved": len(saved),
        "calc_ids_in_keys": len(ids_in_keys),
        "h12_candidate_nature_calls_expected": len(h12_expected),
        "h12_probes_expected": len(h12_probes),
        "h12_calls_plus_probes": len(h12_expected) + len(h12_probes),
        "dm4_min_atk_search_artifacts": len(dm4_search_files),
        "required_for_offline_key_regen": len(required),
        "missing_required": missing,
        "dm4_search_missing": sorted(set(dm4_search_missing)),
        "inventory": {
            "h12_candidate_x_nature": len(h12_expected),
            "h12_probes": len(h12_probes),
            "dm4_min_atk_search_steps_saved": len(dm4_search_files),
            "other_artifacts": len(saved) - len(h12_expected) - len(h12_probes) - len(dm4_search_files),
            "total_saved": len(saved),
            "calls_without_saved_artifact": missing + sorted(set(dm4_search_missing)),
        },
        "note": (
            "H12 alone: up to 35 threats × ≤4 candidate moves × 2 natures; "
            "actual candidate×nature matrix from keys is h12_candidate_nature_calls_expected. "
            "calc_store is offline-first; PART_G_V4_REQUIRE_CALC_ARTIFACT=1 fails on missing ids."
        ),
    }
    REPORT.write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n")

    errors = []
    if missing:
        errors.append(f"missing required artifacts ({len(missing)}): {missing[:20]}")
    if dm4_search_missing:
        errors.append(f"dm4 min_atk winners missing: {dm4_search_missing}")

    # Sanity: saved count should be >= required
    if len(saved) < len(required) - len(missing):
        errors.append("saved count inconsistent with required set")

    if errors:
        print("FAIL check_calc_artifacts:")
        for e in errors:
            print(" -", e)
        print(json.dumps(coverage, indent=2)[:1200])
        return 1

    print(
        f"PASS check_calc_artifacts: saved={len(saved)} "
        f"required_offline={len(required)} "
        f"h12_candidate×nature={len(h12_expected)} "
        f"key_calc_ids={len(ids_in_keys)} "
        f"missing=0"
    )
    print(f"  wrote {REPORT.relative_to(PKG)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
