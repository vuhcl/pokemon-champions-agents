"""Guards against known GitHub Actions workflow YAML footguns."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))

# Plain-scalar folding turns `cmd \` + next-line `--flag` into `\ --flag`.
FOLD_BUG_RE = re.compile(r"\\[ \t]+--")
# Step/input interpolations inside run: bodies (env:/with:/if: are OK).
RUN_INTERP_RE = re.compile(r"\$\{\{\s*(steps\.|inputs\.)")
ALLOWLIST_INTERP = (
    "${{ inputs.force }}",
)
# steps.<id> references in if: expressions.
STEPS_REF_RE = re.compile(r"steps\.([A-Za-z_][A-Za-z0-9_-]*)")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _iter_job_steps(data: dict):
    for job_name, job in (data.get("jobs") or {}).items():
        steps = job.get("steps") or []
        yield job_name, steps


def test_fixture_plain_scalar_folding_is_detected() -> None:
    """RED: folded plain-scalar run with backslash continuation."""
    doc = yaml.safe_load(
        "steps:\n"
        "  - name: Build PR body\n"
        "    run: uv run python -m foo \\\n"
        "      --gate x \\\n"
        "      --out y\n"
    )
    run = doc["steps"][0]["run"]
    assert "\n" not in run
    assert FOLD_BUG_RE.search(run), repr(run)


def test_fixture_block_scalar_shell_continuation_ok() -> None:
    doc = yaml.safe_load(
        "steps:\n"
        "  - name: Build PR body\n"
        "    run: |\n"
        "      uv run python -m foo \\\n"
        "        --gate x \\\n"
        "        --out y\n"
    )
    run = doc["steps"][0]["run"]
    assert "\n" in run
    assert not FOLD_BUG_RE.search(run), repr(run)


def test_workflows_have_no_folded_run_backslash_options() -> None:
    failures: list[str] = []
    for path in WORKFLOWS:
        data = _load(path)
        for job_name, steps in _iter_job_steps(data):
            for i, step in enumerate(steps):
                run = step.get("run")
                if not isinstance(run, str):
                    continue
                if FOLD_BUG_RE.search(run):
                    failures.append(f"{path.name}:{job_name}:step[{i}]/{step.get('name')}")
    assert not failures, "plain-scalar run folding bug:\n" + "\n".join(failures)


def test_fixture_steps_output_in_run_is_detected() -> None:
    doc = yaml.safe_load(
        "steps:\n"
        "  - name: Fail\n"
        "    run: |\n"
        "      echo \"${{ steps.gate.outputs.reason }}\"\n"
    )
    run = doc["steps"][0]["run"]
    assert RUN_INTERP_RE.search(run)


def test_run_bodies_avoid_step_and_input_interpolation() -> None:
    failures: list[str] = []
    for path in WORKFLOWS:
        data = _load(path)
        for job_name, steps in _iter_job_steps(data):
            for i, step in enumerate(steps):
                run = step.get("run")
                if not isinstance(run, str):
                    continue
                for match in RUN_INTERP_RE.finditer(run):
                    # Find the full ${{ ... }} containing this match.
                    start = match.start()
                    end = run.find("}}", start)
                    expr = run[start : end + 2] if end != -1 else run[start : start + 40]
                    if any(allowed in expr for allowed in ALLOWLIST_INTERP):
                        continue
                    # github.event_name is not steps./inputs. — ignore.
                    if "${{ inputs.force }}" in expr:
                        continue
                    failures.append(
                        f"{path.name}:{job_name}:step[{i}]/{step.get('name')}: {expr}"
                    )
    assert not failures, "disallowed ${{ }} in run:\n" + "\n".join(failures)


def _check_step_id_refs(steps: list[dict]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for i, step in enumerate(steps):
        if_expr = step.get("if")
        if isinstance(if_expr, str):
            for sid in STEPS_REF_RE.findall(if_expr):
                if sid == "outputs":
                    # defensive; steps.outputs is not a real form we use
                    continue
                # steps.<id>.outputs... — first capture is the id
                if sid not in seen_ids:
                    errors.append(
                        f"step[{i}]/{step.get('name')}: if references steps.{sid} "
                        f"before id is defined (seen={sorted(seen_ids)})"
                    )
        sid = step.get("id")
        if isinstance(sid, str) and sid:
            seen_ids.add(sid)
    return errors


def test_fixture_missing_step_id_in_if_fails() -> None:
    doc = yaml.safe_load(
        "steps:\n"
        "  - name: Gate\n"
        "    run: true\n"
        "  - name: After\n"
        "    if: steps.cpr.outputs.pull-request-number != ''\n"
        "    run: true\n"
    )
    errs = _check_step_id_refs(doc["steps"])
    assert errs and "steps.cpr" in errs[0]


def test_fixture_step_id_defined_later_fails() -> None:
    doc = yaml.safe_load(
        "steps:\n"
        "  - name: After\n"
        "    if: steps.cpr.outputs.pull-request-number != ''\n"
        "    run: true\n"
        "  - name: Open PR\n"
        "    id: cpr\n"
        "    run: true\n"
    )
    errs = _check_step_id_refs(doc["steps"])
    assert errs and "steps.cpr" in errs[0]


def test_workflows_if_step_refs_resolve_to_earlier_ids() -> None:
    failures: list[str] = []
    for path in WORKFLOWS:
        data = _load(path)
        for job_name, steps in _iter_job_steps(data):
            for err in _check_step_id_refs(steps):
                failures.append(f"{path.name}:{job_name}:{err}")
    assert not failures, "unresolved steps.* in if:\n" + "\n".join(failures)


def test_vgcpastes_and_compendium_marker_after_cpr() -> None:
    for name in ("vgcpastes-refresh-mc.yml", "compendium-refresh-gate.yml"):
        data = _load(ROOT / ".github" / "workflows" / name)
        steps = data["jobs"]["gate-and-pr"]["steps"]
        names = [s.get("name") for s in steps]
        assert "Open or update PR" in names
        assert "Commit marker to main" in names
        assert names.index("Commit marker to main") > names.index("Open or update PR")
        # CPR must have id: cpr for the marker if-gate.
        cpr = next(s for s in steps if s.get("name") == "Open or update PR")
        assert cpr.get("id") == "cpr"
        marker = next(s for s in steps if s.get("name") == "Commit marker to main")
        assert "pull-request-number" in str(marker.get("if", ""))
