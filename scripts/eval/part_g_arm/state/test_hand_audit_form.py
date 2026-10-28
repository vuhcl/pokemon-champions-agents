"""hand_audit_form — render + CSV round-trip on stub/dev transcripts only."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.eval.part_g_arm.state.hand_audit_form import (
    CSV_COLUMNS,
    EXPORT_JS,
    build_sections_from_diff,
    build_sections_from_transcript,
    expected_csv_line_count,
    split_acceptance_points,
    write_form,
)


def test_split_acceptance_points():
    assert split_acceptance_points("one") == [{"id": "acceptance", "text": "one"}]
    pts = split_acceptance_points("a; b; c")
    assert [p["id"] for p in pts] == ["p1", "p2", "p3"]


def test_form_render_and_csv_line_count(tmp_path: Path):
    transcript = [
        {
            "id": "dev-lookup",
            "turns": [
                {
                    "user": "What types does Venusaur have?",
                    "final_text": "Grass/Poison",
                    "mechanical_class": "lookup only",
                    "tool_calls": [
                        {"name": "get_typing", "args": {"species": "Venusaur"}, "result": {"types": ["Grass", "Poison"]}}
                    ],
                }
            ],
        }
    ]
    acceptance = {"dev-lookup": "Types Grass/Poison; order may vary"}
    sections = build_sections_from_transcript(transcript, acceptance_by_id=acceptance)
    assert len(sections) == 1
    assert expected_csv_line_count(sections) == 2  # two ;-clauses
    meta = write_form(sections, tmp_path / "out")
    html = Path(meta["html"]).read_text(encoding="utf-8")
    assert "Export CSV" in html
    assert "dev-lookup" in html
    assert "gemma" not in html.lower() or "omitted" in html.lower()
    assert "TRUE" not in html  # no scorer verdict colours
    assert "no model/judge verdict" in html.lower()
    with Path(meta["csv"]).open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == CSV_COLUMNS
    assert len(rows) - 1 == expected_csv_line_count(sections)


def test_export_js_round_trip(tmp_path: Path):
    """Node executes the same buildRows/toCsv as the page; re-read verdicts match."""
    import subprocess

    sections = [
        {
            "id": "r__t1",
            "row_id": "r",
            "turn": 1,
            "points": [{"id": "p1", "text": "a"}, {"id": "p2", "text": "b"}],
        }
    ]
    state = {
        "bySection": {
            "r__t1": {
                "points": {"p1": "pass", "p2": "fail"},
                "overall": "fail",
                "note": "wrong order",
            }
        }
    }
    js = (
        EXPORT_JS
        + "\nconst SECTIONS = "
        + json.dumps(sections)
        + ";\nconst state = "
        + json.dumps(state)
        + ";\nprocess.stdout.write(toCsv(buildRows(SECTIONS, state)));\n"
    )
    script = tmp_path / "export_roundtrip.mjs"
    script.write_text(js, encoding="utf-8")
    out = subprocess.check_output(["node", str(script)], text=True)
    lines = list(csv.reader(out.splitlines()))
    assert lines[0] == CSV_COLUMNS
    assert lines[1] == ["r", "1", "p1", "pass", "fail", "wrong order"]
    assert lines[2] == ["r", "1", "p2", "fail", "fail", "wrong order"]
    assert len(lines) - 1 == expected_csv_line_count(sections)


def test_diff_runs_sheet():
    differ = [
        {
            "id": "r1",
            "vs_run": 2,
            "status": "differ",
            "diffs": [{"kind": "turn", "turn": 1, "fields": ["final_text_sha256"]}],
        }
    ]
    run2 = [
        {
            "id": "r1",
            "turns": [
                {"user": "u", "final_text": "other", "tool_calls": [], "mechanical_class": "lookup only"}
            ],
        }
    ]
    sections = build_sections_from_diff(differ, {2: run2}, acceptance_by_id={"r1": "key"})
    assert len(sections) == 1
    assert sections[0]["id"] == "r1__run2__t1"
