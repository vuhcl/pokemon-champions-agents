"""GITHUB_OUTPUT reason/message sanitization."""

from __future__ import annotations

from pathlib import Path

from scripts.ci.github_output import sanitize_github_output_value
from scripts.ci.vgcpastes_refresh_gate import write_github_output


def test_sanitize_collapses_controls_and_caps():
    raw = 'line1\nline2 "quote" `backtick` $(id)\x07 ' + ("x" * 250)
    out = sanitize_github_output_value(raw)
    assert "\n" not in out
    assert "\r" not in out
    assert "\x07" not in out
    assert len(out) <= 200
    assert '"' in out and "`" in out and "$(id)" in out
    assert all(ord(c) >= 32 for c in out)


def test_write_github_output_sanitizes_reason(tmp_path: Path):
    path = tmp_path / "out.txt"
    dirty = 'fail:\n"boom" `x` $(id)\x00more'
    write_github_output(path, {"decision": "fail", "reason": dirty})
    text = path.read_text(encoding="utf-8")
    assert text.count("\n") == 2  # two keys, each one line
    reason_line = [ln for ln in text.splitlines() if ln.startswith("reason=")][0]
    value = reason_line.split("=", 1)[1]
    assert "\n" not in value
    assert "\x00" not in value
    assert len(value) <= 200
