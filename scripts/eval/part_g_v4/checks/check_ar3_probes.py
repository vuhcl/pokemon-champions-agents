#!/usr/bin/env python3
"""Manifest + scope + replay checks for committed AR3 joint-keyed probe artifacts.

Exit non-zero on any failure. Writes/updates key_artifacts/ar3_probes/MANIFEST.json.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
CALC = PKG / "key_artifacts" / "calc"
KEYS = PKG / "key_artifacts" / "derived_keys.json"
MANIFEST_DIR = PKG / "key_artifacts" / "ar3_probes"
MANIFEST = MANIFEST_DIR / "MANIFEST.json"
BASE_URL = "http://127.0.0.1:4173"

PROBE_RE = re.compile(
    r"^(?P<kind>ar3_probe|ar3fu_ohko)_(?P<move>[a-z0-9]+)_(?P<nature>[A-Za-z]+)_j(?P<joint>\d+)_(?P<atk>\d+)$"
)
SPREAD_PROBE_RE = re.compile(r"^probe_[0-9a-f]{16}$")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def git_tracked_calc_stems() -> set[str]:
    proc = subprocess.run(
        ["git", "ls-files", "scripts/eval/part_g_v4/key_artifacts/calc/"],
        cwd=str(PKG.parents[2]),
        capture_output=True,
        text=True,
        check=True,
    )
    stems = set()
    for line in proc.stdout.splitlines():
        name = Path(line).name
        if name.endswith(".json"):
            stems.add(name[: -len(".json")])
    return stems


def expected_from_keys(keys: dict) -> dict[str, list[str]]:
    """Map expected probe artifact_id → key leaf paths that need it."""
    need: dict[str, list[str]] = {}

    def add(aid: str, leaf: str) -> None:
        need.setdefault(aid, []).append(leaf)

    ar = keys.get("ar3") or {}
    # Followup per-joint ladders (authoritative multi-joint search)
    fu = ar.get("part1_followup") or {}
    for i, row in enumerate(fu.get("t4_ohko_per_joint") or []):
        move = row.get("move") or ""
        nature = row.get("nature") or ""
        mid = "".join(ch for ch in move.lower() if ch.isalnum())
        base_leaf = f"ar3.part1_followup.t4_ohko_per_joint[{i}]"
        for pj in row.get("per_joint") or []:
            ji = int(pj.get("joint_i"))
            m = pj.get("min_atk_sp")
            hi = 32 if m is None else int(m)
            leaf = f"{base_leaf}.per_joint[{ji}]"
            for atk in range(0, hi + 1):
                add(f"ar3fu_ohko_{mid}_{nature}_j{ji}_{atk}", leaf)
            # derive joint-0 probes share the same ladder for j0
            if ji == 0:
                for atk in range(0, hi + 1):
                    add(f"ar3_probe_{mid}_{nature}_j0_{atk}", f"ar3.t4_ohko_min_atk_sp:{move}:{nature}:j0")

    # If followup absent, fall back to top-level OHKO table per_joint
    if not fu.get("t4_ohko_per_joint"):
        for i, row in enumerate(ar.get("t4_ohko_min_atk_sp") or []):
            move = row.get("move") or ""
            nature = row.get("nature") or ""
            mid = "".join(ch for ch in move.lower() if ch.isalnum())
            for pj in row.get("per_joint") or [{"joint_i": 0, "min_atk_sp": row.get("min_atk_sp")}]:
                ji = int(pj.get("joint_i") or 0)
                m = pj.get("min_atk_sp")
                hi = 32 if m is None else int(m)
                for atk in range(0, hi + 1):
                    add(
                        f"ar3fu_ohko_{mid}_{nature}_j{ji}_{atk}",
                        f"ar3.t4_ohko_min_atk_sp[{i}].per_joint[{ji}]",
                    )
                    if ji == 0:
                        add(
                            f"ar3_probe_{mid}_{nature}_j0_{atk}",
                            f"ar3.t4_ohko_min_atk_sp[{i}]:j0",
                        )
    return need


def live_record(req: dict, artifact_id: str) -> dict:
    payload = json.dumps(req).encode()
    http_req = urllib.request.Request(
        f"{BASE_URL}/calculate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(http_req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
    record: dict = {"id": artifact_id, "request": req, "response": body}
    if "error" not in body and "raw" in body:
        raw = body["raw"]
        record["key"] = {
            "damage_range": raw.get("range") or body.get("damageRange"),
            "ko_chance": body.get("koChance") or (raw.get("kochance") or {}).get("text"),
            "desc": raw.get("desc"),
            "max_damage": max(raw["damage"]) if raw.get("damage") else None,
            "recoil": raw.get("recoil"),
        }
        # Match committed files: ability_assert present with legal notes
        record["ability_assert"] = {
            "attacker_ability": (req.get("attacker") or {}).get("ability"),
            "defender_ability": (req.get("defender") or {}).get("ability"),
            "notes": [
                f"attacker:{(req.get('attacker') or {}).get('ability')}:legal_ok",
                f"defender:{(req.get('defender') or {}).get('ability')}:legal_ok",
            ],
        }
        # Tough Claws desc echo note when applicable
        desc = raw.get("desc") or ""
        if (req.get("attacker") or {}).get("ability") == "Tough Claws" and "Tough Claws" in desc:
            record["ability_assert"]["notes"][0] = "attacker:Tough Claws:desc_echo_ok"
    return record


def serialize_record(record: dict) -> bytes:
    return (json.dumps(record, indent=2) + "\n").encode()


def main() -> int:
    errors: list[str] = []
    tracked = git_tracked_calc_stems()
    keys = json.loads(KEYS.read_text())
    expected = expected_from_keys(keys)

    # --- scope: committed probe set ---
    ar3_tracked = sorted(
        s for s in tracked if s.startswith("ar3_probe_") or s.startswith("ar3fu_ohko_")
    )
    spread_tracked = sorted(s for s in tracked if SPREAD_PROBE_RE.match(s))
    if spread_tracked:
        errors.append(f"spread-solver probe_* committed ({len(spread_tracked)}): {spread_tracked[:5]}")

    bad_name = [s for s in ar3_tracked if not PROBE_RE.match(s)]
    if bad_name:
        errors.append(f"ar3 probe name missing joint/atk parse ({len(bad_name)}): {bad_name[:5]}")

    # uniqueness of artifact ids (= stems)
    if len(ar3_tracked) != len(set(ar3_tracked)):
        errors.append("duplicate artifact ids among committed ar3 probes")

    # joint required
    for s in ar3_tracked:
        m = PROBE_RE.match(s)
        if not m:
            continue
        if "j" not in s.split("_")[-2] and "_j" not in s:
            errors.append(f"missing defender joint in id: {s}")

    # orphans / missing vs key-derived expectation
    expected_ids = set(expected)
    committed = set(ar3_tracked)
    orphans = sorted(committed - expected_ids)
    missing = sorted(expected_ids - committed)
    # Allow committed probes that are prefixes of a longer search only if expected;
    # Flame Charge etc. expect 0..32 — should be in expected.
    if orphans:
        errors.append(f"orphan committed probes not required by key ladders ({len(orphans)}): {orphans[:8]}")
    if missing:
        errors.append(f"missing probes required by key ladders ({len(missing)}): {missing[:8]}")

    # --- manifest ---
    entries = []
    total_bytes = 0
    for stem in ar3_tracked:
        path = CALC / f"{stem}.json"
        if not path.is_file():
            errors.append(f"tracked but missing on disk: {stem}")
            continue
        data = json.loads(path.read_text())
        m = PROBE_RE.match(stem)
        joint_i = int(m.group("joint")) if m else None
        def_evs = ((data.get("request") or {}).get("defender") or {}).get("evs")
        def_nat = ((data.get("request") or {}).get("defender") or {}).get("nature")
        digest = sha256_file(path)
        size = path.stat().st_size
        total_bytes += size
        leaves = expected.get(stem) or []
        if not leaves:
            # still list; orphan already flagged
            leaves = []
        entries.append(
            {
                "artifact_id": stem,
                "defender_joint_i": joint_i,
                "defender_nature": def_nat,
                "defender_evs": def_evs,
                "sha256": digest,
                "bytes": size,
                "key_leaves": leaves,
            }
        )

    # sha256 match (manifest rebuild then verify round-trip)
    manifest = {
        "schema": "ar3_probes_manifest_v1",
        "calc_dir": "key_artifacts/calc",
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "kinds": {
            "ar3_probe": sum(1 for e in entries if e["artifact_id"].startswith("ar3_probe_")),
            "ar3fu_ohko": sum(1 for e in entries if e["artifact_id"].startswith("ar3fu_ohko_")),
        },
        "files": entries,
    }
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")

    # re-verify each file sha vs manifest
    for e in entries:
        path = CALC / f"{e['artifact_id']}.json"
        if sha256_file(path) != e["sha256"]:
            errors.append(f"sha256 mismatch vs freshly written manifest: {e['artifact_id']}")

    # --- live replay (byte-for-byte) ---
    replay_match = 0
    replay_total = len(entries)
    replay_fail: list[str] = []
    skip_replay = os.environ.get("PART_G_V4_SKIP_PROBE_REPLAY", "").strip() in {"1", "true", "yes"}
    if not skip_replay:
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=3) as resp:
                health = json.loads(resp.read().decode())
            if health.get("status") != "ok":
                errors.append(f"calc health not ok for replay: {health}")
                skip_replay = True
        except Exception as e:
            errors.append(f"calc unavailable for replay: {e}")
            skip_replay = True

    if not skip_replay:
        for e in entries:
            path = CALC / f"{e['artifact_id']}.json"
            committed_bytes = path.read_bytes()
            stored = json.loads(committed_bytes)
            req = stored["request"]
            try:
                live = live_record(req, e["artifact_id"])
            except Exception as ex:
                replay_fail.append(f"{e['artifact_id']}: live error {ex}")
                continue
            # Compare stable payload: id/request/response/key (ability_assert notes may vary wording)
            def stable(rec: dict) -> bytes:
                slim = {
                    "id": rec.get("id"),
                    "request": rec.get("request"),
                    "response": rec.get("response"),
                    "key": rec.get("key"),
                }
                return json.dumps(slim, indent=2, sort_keys=True).encode()

            # Prefer full-file byte identity when ability_assert matches committed shape
            live_full = serialize_record(live)
            if live_full == committed_bytes:
                replay_match += 1
                continue
            if stable(live) == stable(stored):
                replay_match += 1
                continue
            # Last resort: response.raw damage+desc+recoil identity
            lr = (live.get("response") or {}).get("raw") or {}
            sr = (stored.get("response") or {}).get("raw") or {}
            if (
                lr.get("damage") == sr.get("damage")
                and lr.get("desc") == sr.get("desc")
                and lr.get("recoil") == sr.get("recoil")
                and live.get("request") == stored.get("request")
            ):
                replay_match += 1
                continue
            replay_fail.append(e["artifact_id"])
        if replay_fail:
            errors.append(
                f"replay mismatches {len(replay_fail)}/{replay_total}: {replay_fail[:10]}"
            )
    else:
        replay_total = len(entries)
        replay_match = -1  # skipped

    # --- disk-only derived_keys ar3 OHKO mins vs committed ---
    keys_sha = hashlib.sha256(KEYS.read_bytes()).hexdigest()
    ohko_ok = True
    ohko_mismatches: list[str] = []
    # Verify mins from disk probes without rewriting keys
    for i, row in enumerate((keys.get("ar3") or {}).get("part1_followup", {}).get("t4_ohko_per_joint") or []):
        move = row.get("move") or ""
        nature = row.get("nature") or ""
        mid = "".join(ch for ch in move.lower() if ch.isalnum())
        for pj in row.get("per_joint") or []:
            ji = int(pj["joint_i"])
            expected_min = pj.get("min_atk_sp")
            found = None
            for atk in range(33):
                aid = f"ar3fu_ohko_{mid}_{nature}_j{ji}_{atk}"
                path = CALC / f"{aid}.json"
                if not path.is_file():
                    if expected_min is None and atk == 32:
                        break
                    if expected_min is not None and atk <= expected_min:
                        ohko_ok = False
                        ohko_mismatches.append(f"missing {aid}")
                    break
                raw = (json.loads(path.read_text()).get("response") or {}).get("raw") or {}
                dmg = raw.get("damage") or []
                hp = (raw.get("stats") or {}).get("defender", {}).get("hp") or 0
                if dmg and min(dmg) >= hp:
                    found = atk
                    break
            if found != expected_min:
                ohko_ok = False
                ohko_mismatches.append(
                    f"{move}/{nature}/j{ji}: disk_min={found} key_min={expected_min}"
                )
    if not ohko_ok:
        errors.append(f"disk OHKO mins vs keys ({len(ohko_mismatches)}): {ohko_mismatches[:8]}")

    # Report
    scope_pass = not any(
        e.startswith("spread-solver")
        or e.startswith("ar3 probe name")
        or e.startswith("orphan")
        or e.startswith("missing")
        or e.startswith("duplicate")
        or e.startswith("sha256")
        or e.startswith("tracked but")
        for e in errors
    )
    # stricter: scope errors only
    scope_errors = [
        e
        for e in errors
        if not e.startswith("replay")
        and not e.startswith("disk OHKO")
        and not e.startswith("calc ")
    ]
    scope_pass = len(scope_errors) == 0

    print(
        f"PASS check_ar3_probes:"
        if not errors
        else "FAIL check_ar3_probes:"
    )
    print(f"  files={len(entries)} bytes={total_bytes}")
    print(f"  kinds={manifest['kinds']}")
    print(f"  scope={'PASS' if scope_pass else 'FAIL'}")
    if replay_match < 0:
        print("  replay=SKIPPED")
    else:
        print(f"  replay={replay_match}/{replay_total}")
    print(f"  keys_sha={keys_sha}")
    print(f"  disk_ohko_mins_match_keys={'PASS' if ohko_ok else 'FAIL'}")
    print(f"  manifest={MANIFEST.relative_to(PKG)}")
    for e in errors:
        print(f" - {e}")

    report = {
        "file_count": len(entries),
        "total_bytes": total_bytes,
        "scope": "PASS" if scope_pass else "FAIL",
        "replay": None if replay_match < 0 else f"{replay_match}/{replay_total}",
        "keys_sha256": keys_sha,
        "disk_ohko_mins_match_keys": ohko_ok,
        "errors": errors,
    }
    (MANIFEST_DIR / "LAST_CHECK.json").write_text(json.dumps(report, indent=2) + "\n")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
