"""Retarget DEFAULT_FORMAT_ID / ids.py / format.py for a new Champions regulation."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from scripts.ci.regulation_letters import (
    archive_mod_for_letter,
    file_tag_for_letter,
    letter_from_format_name,
    letters_adjacent,
)

ROOT = Path(__file__).resolve().parents[2]
SESSION = ROOT / "recommender" / "session.py"
IDS = ROOT / "recommender" / "ids.py"
FORMAT = ROOT / "recommender" / "format.py"
RESOLVED_TEST = ROOT / "tests" / "recommender" / "test_resolved_builds.py"


def retarget(gate: dict) -> None:
    current = str(gate["current_letter"]).upper()
    live = str(gate["live_letter"]).upper()
    if not letters_adjacent(current, live):
        raise SystemExit(f"refusing retarget: {current} → {live} not adjacent")

    vgc = str(gate["showdown_vgc"])
    if letter_from_format_name(vgc) != live:
        raise SystemExit(f"showdown_vgc letter mismatch: {vgc!r} vs M-{live}")

    prev_mod = archive_mod_for_letter(current)
    prev_tag = file_tag_for_letter(current)
    new_tag = file_tag_for_letter(live)

    session = SESSION.read_text(encoding="utf-8")
    session2, n = re.subn(
        r'DEFAULT_FORMAT_ID = "[^"]+"',
        f'DEFAULT_FORMAT_ID = "{vgc}"',
        session,
        count=1,
    )
    if n != 1:
        raise SystemExit("session.py: DEFAULT_FORMAT_ID replace failed")
    SESSION.write_text(session2, encoding="utf-8")

    ids = IDS.read_text(encoding="utf-8")
    ids, n = re.subn(
        r'("champions":\s*")champions-reg-m[a-z](")',
        rf"\1{new_tag}\2",
        ids,
        count=1,
    )
    if n != 1:
        raise SystemExit("ids.py: champions mapping replace failed")

    # Ensure prior mod + tag aliases exist
    if f'"{prev_mod}"' not in ids:
        ids = ids.replace(
            f'    "champions": "{new_tag}",\n',
            f'    "champions": "{new_tag}",\n'
            f'    "{prev_mod}": "{prev_tag}",\n',
            1,
        )
    if f'"{prev_tag}": "{prev_tag}"' not in ids:
        ids = ids.replace(
            f'    "{new_tag}": "{new_tag}",\n',
            f'    "{new_tag}": "{new_tag}",\n'
            f'    "{prev_tag}": "{prev_tag}",\n',
            1,
        )
    # Also allow bare new_tag key if missing (champions-reg-md)
    if f'"{new_tag}": "{new_tag}"' not in ids:
        ids = ids.replace(
            f'    "champions": "{new_tag}",\n',
            f'    "champions": "{new_tag}",\n'
            f'    "{new_tag}": "{new_tag}",\n',
            1,
        )

    # Prepend REGULATION_ARCHIVE_ORDER
    m = re.search(
        r"REGULATION_ARCHIVE_ORDER:\s*tuple\[str,\s*\.\.\.\]\s*=\s*\((.*?)\)",
        ids,
        re.S,
    )
    if not m:
        raise SystemExit("ids.py: REGULATION_ARCHIVE_ORDER not found")
    body = m.group(1)
    if f'"{new_tag}"' not in body:
        ids = ids[: m.start(1)] + f'\n    "{new_tag}",' + body + ids[m.end(1) :]
    IDS.write_text(ids, encoding="utf-8")

    fmt = FORMAT.read_text(encoding="utf-8")
    if f'"Reg M-{current}"' not in fmt:
        needle = '    else:\n        regulation_mod = "champions"\n'
        branch = (
            f'    elif "Reg M-{current}" in format_id:\n'
            f'        regulation_mod = "{prev_mod}"\n'
        )
        if needle not in fmt:
            raise SystemExit("format.py: else→champions branch not found")
        FORMAT.write_text(fmt.replace(needle, branch + needle, 1), encoding="utf-8")

    if RESOLVED_TEST.exists():
        t = RESOLVED_TEST.read_text(encoding="utf-8")
        t, n = re.subn(
            r'assert regulation_file_tag\("champions"\) == "champions-reg-m[a-z]"',
            f'assert regulation_file_tag("champions") == "{new_tag}"',
            t,
            count=1,
        )
        if n != 1:
            raise SystemExit("test_resolved_builds.py: champions tag assert not found")
        # Replace first element of regulation_lookup_chain("champions") list
        t2, n2 = re.subn(
            r'(assert regulation_lookup_chain\("champions"\) == \[\n\s*")[^"]+(")',
            rf"\1{new_tag}\2",
            t,
            count=1,
        )
        if n2 != 1:
            raise SystemExit("test_resolved_builds.py: champions chain assert not found")
        RESOLVED_TEST.write_text(t2, encoding="utf-8")

    print(
        f"retargeted identity: M-{current} → M-{live} "
        f"DEFAULT_FORMAT_ID={vgc!r} prior_mod={prev_mod} tag={new_tag}",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gate", type=Path, required=True)
    args = p.parse_args(argv)
    gate = json.loads(args.gate.read_text(encoding="utf-8"))
    if gate.get("decision") != "extract":
        print(
            f"gate decision is {gate.get('decision')!r}, not extract",
            file=sys.stderr,
        )
        return 1
    retarget(gate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
