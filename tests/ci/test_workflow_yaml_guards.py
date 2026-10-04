"""Guards against known GitHub Actions workflow YAML footguns.

Pin deliberate 2026-10-04: GitHub changelog 2026-09-17 says ubuntu-latest
migrates to Ubuntu 26.04 gradually between 2026-10-19 and 2026-11-19.
Revisit intentionally; not a permanent OS choice. When ready to move, use an
explicit version label (for example ubuntu-26.04), never *-latest.
"""

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
# Statically resolvable matrix runs-on: ${{ matrix.<key> }}.
MATRIX_RUNS_ON_RE = re.compile(r"^\$\{\{\s*matrix\.([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}$")
_LATEST_HINT = (
    "use an explicit version label (for example ubuntu-26.04) when ready to move; "
    "*-latest is forbidden"
)


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _iter_job_steps(data: dict):
    for job_name, job in (data.get("jobs") or {}).items():
        steps = job.get("steps") or []
        yield job_name, steps


def _yamls_under_github(root: Path) -> list[Path]:
    """All .yml/.yaml under root/.github/ (workflows, composite actions, reusable)."""
    github = root / ".github"
    if not github.is_dir():
        return []
    return sorted(
        p for p in github.rglob("*") if p.is_file() and p.suffix in {".yml", ".yaml"}
    )


def _github_yamls() -> list[Path]:
    return _yamls_under_github(ROOT)


def _resolve_runs_on_labels(job: dict) -> list[str]:
    """Resolve runs-on labels we can check statically; skip unresolved dynamics."""
    runs_on = job.get("runs-on")
    if isinstance(runs_on, str):
        match = MATRIX_RUNS_ON_RE.match(runs_on.strip())
        if match:
            key = match.group(1)
            matrix = (job.get("strategy") or {}).get("matrix") or {}
            vals = matrix.get(key)
            # Unresolved fromJSON(...) / non-list matrices: skip (none in repo today).
            if isinstance(vals, list) and all(isinstance(v, str) for v in vals):
                return list(vals)
            return []
        return [runs_on]
    if isinstance(runs_on, list):
        return [x for x in runs_on if isinstance(x, str)]
    return []


def _latest_runner_failures(paths: list[Path]) -> list[str]:
    failures: list[str] = []
    for path in paths:
        data = _load(path)
        if not isinstance(data, dict):
            continue
        for job_name, job in (data.get("jobs") or {}).items():
            if not isinstance(job, dict):
                continue
            for label in _resolve_runs_on_labels(job):
                if label.endswith("-latest"):
                    failures.append(
                        f"{path.name}:{job_name}: runs-on={label} ({_LATEST_HINT})"
                    )
    return failures


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


def test_fixture_string_ubuntu_latest_is_detected() -> None:
    labels = _resolve_runs_on_labels({"runs-on": "ubuntu-latest"})
    assert labels == ["ubuntu-latest"]
    assert any(label.endswith("-latest") for label in labels)


def test_fixture_list_ubuntu_latest_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "list.yml"
    path.write_text(
        "jobs:\n"
        "  build:\n"
        "    runs-on: [self-hosted, ubuntu-latest]\n"
        "    steps: []\n",
        encoding="utf-8",
    )
    failures = _latest_runner_failures([path])
    assert len(failures) == 1
    assert "list.yml:build: runs-on=ubuntu-latest" in failures[0]
    assert "ubuntu-26.04" in failures[0]


def test_fixture_yaml_suffix_ubuntu_latest_is_detected(tmp_path: Path) -> None:
    """A .yaml workflow must not evade the guard (suffix, not only .yml)."""
    path = tmp_path / "evil.yaml"
    path.write_text(
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps: []\n",
        encoding="utf-8",
    )
    failures = _latest_runner_failures([path])
    assert len(failures) == 1
    assert "evil.yaml:build: runs-on=ubuntu-latest" in failures[0]
    assert "ubuntu-26.04" in failures[0]


def test_fixture_explicit_ubuntu_24_04_allowed(tmp_path: Path) -> None:
    path = tmp_path / "pinned.yml"
    path.write_text(
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-24.04\n"
        "    steps: []\n",
        encoding="utf-8",
    )
    assert _latest_runner_failures([path]) == []


def test_fixture_matrix_ubuntu_latest_is_detected(tmp_path: Path) -> None:
    path = tmp_path / "matrix.yml"
    path.write_text(
        "jobs:\n"
        "  build:\n"
        "    runs-on: ${{ matrix.os }}\n"
        "    strategy:\n"
        "      matrix:\n"
        "        os: [ubuntu-24.04, ubuntu-latest]\n"
        "    steps: []\n",
        encoding="utf-8",
    )
    failures = _latest_runner_failures([path])
    assert len(failures) == 1
    assert "matrix.yml:build: runs-on=ubuntu-latest" in failures[0]


def test_fixture_yamls_under_github_includes_yaml_suffix(tmp_path: Path) -> None:
    github = tmp_path / ".github" / "workflows"
    github.mkdir(parents=True)
    (github / "a.yml").write_text("jobs: {}\n", encoding="utf-8")
    (github / "b.yaml").write_text("jobs: {}\n", encoding="utf-8")
    (github / "c.txt").write_text("nope\n", encoding="utf-8")
    found = {p.name for p in _yamls_under_github(tmp_path)}
    assert found == {"a.yml", "b.yaml"}


def test_github_workflows_avoid_latest_runner_labels() -> None:
    """Pin deliberate 2026-10-04: changelog 2026-09-17 — ubuntu-latest → 26.04
    gradually 2026-10-19..2026-11-19. Explicit labels only; revisit intentionally.
    """
    failures = _latest_runner_failures(_github_yamls())
    assert not failures, "forbidden *-latest runs-on:\n" + "\n".join(failures)
