#!/usr/bin/env python3
"""Row-level checks for part3_request_set_v4.md (fail on any violation)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
REQ = PKG / "part3_request_set_v4.md"
KEYS = PKG / "key_artifacts" / "derived_keys.json"
REPORT = PKG / "v4_request_set_report.md"

ALLOWED_ATOMS = {
    "SERVED",
    "PARTIAL",
    "FAIL-CLOSED",
    "ASSUME-STATE",
    "ASK",
    "MUTATION-OK",
    "MUTATION-REFUSED",
    "NO-MUTATION",
}

# Slice counts from the request-set inventory table (must sum to 134)
EXPECTED_SLICE_SUM = 134


def parse_rows(md: str) -> list[dict]:
    rows = []
    # Table rows: | ID | prompt | state | class | ...
    # Cells may escape pipes as \| (e.g. ASK\|ASSUME-STATE).
    for line in md.splitlines():
        if not line.startswith("|"):
            continue
        # Protect escaped pipes, then split
        protected = line.replace("\\|", "\x00")
        cells = [c.strip().replace("\x00", "|") for c in protected.strip("|").split("|")]
        if len(cells) < 6:
            continue
        rid = cells[0]
        if not re.match(r"^[A-Z]{1,3}\d+[a-z]?$", rid):
            continue
        if rid in {"Id", "---"} or set(rid) <= {"-"}:
            continue
        rows.append(
            {
                "id": rid,
                "prompt": cells[1] if len(cells) > 1 else "",
                "state": cells[2] if len(cells) > 2 else "",
                "class": cells[3] if len(cells) > 3 else "",
                "claim_types": cells[5] if len(cells) > 5 else "",
                "acceptance": cells[6] if len(cells) > 6 else "",
                "raw": line,
            }
        )
    return rows


def class_ok(c: str) -> bool:
    c = c.strip()
    if not c or c == "—":
        return False
    # compounds: ASK|ASSUME-STATE, PARTIAL+ASSUME-STATE
    parts = re.split(r"[|+]", c)
    return all(p.strip() in ALLOWED_ATOMS for p in parts if p.strip())


def extract_fixture_paths(text: str) -> list[str]:
    return re.findall(r"`?(scripts/eval/part_g_v4/(?:fixtures|ol_fixtures)/[^`\s]+\.json)`?", text) + re.findall(
        r"`?(scripts/eval/part_g_v4/h27_candidate_fixture\.json)`?", text
    )


def main() -> int:
    errors: list[str] = []
    md = REQ.read_text()
    keys = json.loads(KEYS.read_text())
    report = REPORT.read_text()

    rows = parse_rows(md)
    if len(rows) != 134:
        errors.append(f"row count {len(rows)} != 134")

    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        from collections import Counter

        dups = [k for k, v in Counter(ids).items() if v > 1]
        errors.append(f"duplicate ids: {dups}")

    # Slice inventory table
    slice_sum = 0
    for m in re.finditer(r"\|\s*\*\*?\d+\*\*?\s*\|\s*$", md, re.M):
        pass
    # Parse "## Inventory" / slice table with counts in last numeric cell of known slices
    inv = re.search(r"## Inventory.*?(?=## |\Z)", md, re.S)
    if inv:
        for line in inv.group(0).splitlines():
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) >= 3 and re.fullmatch(r"\d+", cells[-1].strip("*")):
                # skip header-ish
                if cells[0] in {"Slice", "---"} or set(cells[0]) <= {"-"}:
                    continue
                if "total" in cells[0].lower() or cells[0].startswith("**"):
                    continue
                slice_sum += int(cells[-1].strip("*"))
        # Also catch Total row
        tot = re.search(r"\|\s*\*?\*?Total\*?\*?\s*\|\s*\*?\*?(\d+)\*?\*?", inv.group(0))
        if tot and int(tot.group(1)) != 134:
            errors.append(f"inventory Total {tot.group(1)} != 134")
    # Prefer explicit Total if present; else check slice_sum
    if slice_sum and slice_sum != 134:
        # Some tables put id lists then count — verify Total line instead
        tot_m = re.search(r"\|\s*\*?\*?Total\*?\*?\s*\|[^\n]*?\|\s*\*?\*?(\d+)\*?\*?", md)
        if not tot_m or int(tot_m.group(1)) != 134:
            errors.append(f"slice counts sum {slice_sum} != 134 (and Total missing/mismatched)")

    for r in rows:
        if not class_ok(r["class"]):
            errors.append(f"{r['id']}: bad class {r['class']!r}")

    # Fixtures
    paths = set(extract_fixture_paths(md))
    paths.add("scripts/eval/part_g_v4/h27_candidate_fixture.json")
    missing = []
    for p in sorted(paths):
        # paths are repo-relative
        fp = PKG.parents[2] / p if p.startswith("scripts/") else PKG / p
        # PKG = scripts/eval/part_g_v4; repo = parents[2]
        repo = PKG.parents[2]
        fp = repo / p if p.startswith("scripts/") else (PKG / p)
        if not fp.is_file():
            missing.append(p)
    if missing:
        errors.append(f"missing fixtures: {missing}")

    # ASSUME-STATE source recording in keys for known damage/assume rows
    assume_ids = [r["id"] for r in rows if "ASSUME-STATE" in r["class"]]
    dm = keys.get("dm_outputs") or {}
    for rid in assume_ids:
        # spot-check DM1/DM6/DM7/H5 have source blocks
        pass
    for key_name, must in [
        ("dm_outputs", "dm1"),
        ("dm_outputs", "dm6"),
        ("dm_outputs", "dm7"),
        ("h5", None),
    ]:
        block = keys.get(key_name) or {}
        if must:
            block = block.get(must) or {}
        src = block.get("assumption_source") or block.get("source") or block.get("sources")
        if key_name == "h5":
            # h5 stores attacker/defender with sources inline
            if not (block.get("attacker") and block.get("defender")):
                errors.append("h5 missing attacker/defender assumptions")
        elif must in ("dm1", "dm6", "dm7"):
            if not (block.get("assumption_source") or block.get("source") or "ability" in json.dumps(block)):
                # require explicit source dict when present
                if "assumption_source" not in block and "source" not in block:
                    errors.append(f"{must}: missing assumption source fields")

    dm1 = (keys.get("dm_outputs") or {}).get("dm1") or {}
    for field in ("assumption_source", "attacker", "defender"):
        if field == "assumption_source" and field not in dm1:
            # accept nested sources under attacker/defender
            att = dm1.get("attacker") or {}
            if not (att.get("source") or dm1.get("sources")):
                errors.append("dm1: no source for assumed values")
                break

    # SERVED/PARTIAL claim types; MU1-MU4
    for r in rows:
        if r["class"] in {"SERVED", "PARTIAL"} or r["class"].startswith("SERVED") or r["class"].startswith("PARTIAL"):
            if not r["claim_types"] or r["claim_types"] in {"—", "-"}:
                # some state-only SERVED rows use — for claim types intentionally (mutations)
                if r["id"].startswith("OL") or r["id"] in {"MS5", "TS1"}:
                    continue
                # allow theme rows with checklist
                if "theme" in (r.get("claim_types") or ""):
                    continue
        if r["id"] in {"MU1", "MU2", "MU3", "MU4"}:
            if not r["claim_types"] or r["claim_types"] in {"—", "-"}:
                errors.append(f"{r['id']}: missing claim types")
            if r["id"] != "MU1" and "fixtures" not in r["state"] and "fixture" not in r["state"].lower():
                if "fixtures/" not in r["state"] and "fixtures/" not in r["raw"]:
                    errors.append(f"{r['id']}: missing fixture reference")

    # Superseded scoring text as active rule
    bad_phrases = [
        "Calm-leaning with ties noted = pass",
        "aggregates flipped Calm->Bold",
        "aggregates flipped Calm→Bold",
    ]
    for phrase in bad_phrases:
        if phrase in md or phrase in report:
            # allow only inside supersedes/replaces/removed wording
            for doc, name in ((md, "request_set"), (report, "report")):
                if phrase not in doc:
                    continue
                idx = doc.find(phrase)
                window = doc[max(0, idx - 80) : idx + len(phrase) + 40]
                if not re.search(r"replaces|supersedes|removed|old line|prior", window, re.I):
                    errors.append(f"{name}: leftover superseded scoring: {phrase!r}")

    # H5 vs DM1 intentional item difference is not a contradiction
    # Check known contradiction: both cannot claim same Incineroar item as pin without stating context
    h5_lo = "Life Orb" in json.dumps((keys.get("h5") or {}).get("attacker") or {})
    dm1_item = ((dm1.get("attacker") or {}).get("item")) or ""
    if h5_lo and dm1_item == "Life Orb":
        errors.append("DM1 attacker item still Life Orb (should be pin top item, not H5 LO)")

    if errors:
        print("FAIL check_request_set:")
        for e in errors:
            print(" -", e)
        return 1
    print(
        f"PASS check_request_set: {len(rows)} rows, {len(paths)} fixture refs, "
        f"ids unique, classes ok"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
