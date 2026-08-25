"""Rebuild role_compendium_setup.py from git and strip duplicated helpers."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
text = subprocess.check_output(
    ["git", "show", "HEAD:recommender/role_compendium.py"],
    cwd=ROOT,
    text=True,
)
lines = text.splitlines()
body = "\n".join(lines[1735:5007]) + "\n"
header = Path(__file__).with_name("_setup_module_header.py.txt").read_text()
out = header + body
for pat in (
    r"\ndef _species_types\(snap: dict\[str, Any\], sid: str\) -> set\[str\]:\n"
    r"    entry = snap\.get\(\"species\", \{\}\)\.get\(sid\) or \{\}\n"
    r"    return \{str\(t\)\.lower\(\) for t in \(entry\.get\(\"types\"\) or \[\]\)\}\n",
    r"\ndef _move_display\(snap: dict\[str, Any\] \| None, mid: str\) -> str:\n"
    r"    if snap:\n"
    r"        name = \(snap\.get\(\"moves\"\) or \{\}\)\.get\(to_id\(mid\), \{\}\)\.get\(\"name\"\)\n"
    r"        if name:\n"
    r"            return str\(name\)\n"
    r"    return mid\n",
):
    out, n = re.subn(pat, "\n", out, count=1)
    if n != 1:
        raise SystemExit(f"expected one removal for pattern, got {n}")
(ROOT / "recommender" / "role_compendium_setup.py").write_text(out)
print("ok", len(out.splitlines()))
