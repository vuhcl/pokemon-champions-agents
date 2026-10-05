"""UTC regulation schedule + readiness (legality letter). CI/data authority.

Product CLI/graph stay on DEFAULT_FORMAT_ID → resolve_format → regulation_mod.
active_regulation() is for CI/data jobs and schedule readiness checks.
showdown_ready() is intentionally not here — lands in PR-B3.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEDULE_PATH = ROOT / "data" / "active_regulation.json"
DEFAULT_LEGALITY_PATH = ROOT / "data" / "legality" / "champions.v1.json"

SCHEDULE_PAST_END_NOT_READY = "schedule_past_end_not_ready"
REGULATION_NOT_READY = "regulation_not_ready"

_REG_LETTER = re.compile(r"\bReg M-([A-Z])\b", re.I)

# Bo1 format ids / Showdown chaos format ids for known regulations.
REGULATIONS: dict[str, dict[str, str]] = {
    "champions-reg-ma": {
        "letter": "A",
        "mod": "championsregma",
        "vgc_format_id": "[Gen 9 Champions] VGC 2026 Reg M-A",
        "bss_format_id": "[Gen 9 Champions] BSS Reg M-A",
        "showdown_format": "gen9championsvgc2026regma",
    },
    "champions-reg-mb": {
        "letter": "B",
        "mod": "championsregmb",
        "vgc_format_id": "[Gen 9 Champions] VGC 2026 Reg M-B",
        "bss_format_id": "[Gen 9 Champions] BSS Reg M-B",
        "showdown_format": "gen9championsvgc2026regmb",
    },
    "champions-reg-mc": {
        "letter": "C",
        "mod": "champions",
        "vgc_format_id": "[Gen 9 Champions] VGC 2026 Reg M-C",
        "bss_format_id": "[Gen 9 Champions] BSS Reg M-C",
        "showdown_format": "gen9championsvgc2026regmc",
    },
}


@dataclass(frozen=True)
class ScheduleWindow:
    """Schedule row as published on Champions-news Duration pages.

    ``end`` is the inclusive last minute from the news page (e.g. 01:59).
    Membership is half-open ``[start, exclusive_end)`` where
    ``exclusive_end = end + 1 minute`` (so end 01:59 ⇒ exclusive 02:00),
    which abuts the next regulation's published start when news is consistent.
    """

    tag: str
    letter: str
    start: datetime
    end: datetime

    @property
    def exclusive_end(self) -> datetime:
        return self.end + timedelta(minutes=1)


@dataclass(frozen=True)
class RegulationStatus:
    tag: str
    letter: str
    ready: bool
    warnings: tuple[str, ...]


def _letter_from_format_name(name: str) -> str:
    m = _REG_LETTER.search(name or "")
    if not m:
        raise ValueError(f"could not parse Reg M-* letter from {name!r}")
    return m.group(1).upper()


def _parse_utc(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_schedule(path: Path | None = None) -> list[ScheduleWindow]:
    raw = json.loads((path or DEFAULT_SCHEDULE_PATH).read_text(encoding="utf-8"))
    windows: list[ScheduleWindow] = []
    for row in raw.get("regulations") or []:
        windows.append(
            ScheduleWindow(
                tag=str(row["tag"]),
                letter=str(row["letter"]).upper(),
                start=_parse_utc(str(row["start"])),
                end=_parse_utc(str(row["end"])),
            )
        )
    windows.sort(key=lambda w: w.start)
    return windows


def legality_vgc_letter(path: Path | None = None) -> str:
    snap = json.loads((path or DEFAULT_LEGALITY_PATH).read_text(encoding="utf-8"))
    vgc = ((snap.get("meta") or {}).get("formats") or {}).get("vgc")
    if not vgc:
        raise ValueError(f"missing meta.formats.vgc in {path or DEFAULT_LEGALITY_PATH}")
    return _letter_from_format_name(str(vgc))


def regulation_ready(
    letter: str,
    *,
    legality_path: Path | None = None,
) -> bool:
    """True when legality snapshot's VGC format letter matches ``letter``."""
    return legality_vgc_letter(legality_path) == letter.upper()


def _previous(windows: list[ScheduleWindow], current: ScheduleWindow) -> ScheduleWindow | None:
    prior = [w for w in windows if w.exclusive_end <= current.start]
    return prior[-1] if prior else None


def _window_containing(windows: list[ScheduleWindow], now: datetime) -> ScheduleWindow | None:
    for w in windows:
        if w.start <= now < w.exclusive_end:
            return w
    return None


def _latest_ended(windows: list[ScheduleWindow], now: datetime) -> ScheduleWindow | None:
    past = [w for w in windows if w.exclusive_end <= now]
    return past[-1] if past else None


def regulation_status(
    *,
    now: datetime | None = None,
    schedule_path: Path | None = None,
    legality_path: Path | None = None,
) -> RegulationStatus:
    """Resolve active tag from schedule + regulation_ready (legality letter).

    If the schedule window containing ``now`` is not ready, stay on the previous
    regulation. If ``now`` is past the last schedule end and the next letter is
    not ready (or has no schedule row), stay on the last regulation and emit
    ``schedule_past_end_not_ready``.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    windows = load_schedule(schedule_path)
    if not windows:
        raise ValueError("empty regulation schedule")

    containing = _window_containing(windows, now)
    if containing is not None:
        ready = regulation_ready(containing.letter, legality_path=legality_path)
        if ready:
            return RegulationStatus(
                tag=containing.tag,
                letter=containing.letter,
                ready=True,
                warnings=(),
            )
        prev = _previous(windows, containing)
        stay = prev or containing
        return RegulationStatus(
            tag=stay.tag,
            letter=stay.letter,
            ready=regulation_ready(stay.letter, legality_path=legality_path),
            warnings=(REGULATION_NOT_READY,),
        )

    ended = _latest_ended(windows, now)
    if ended is None:
        first = windows[0]
        ready = regulation_ready(first.letter, legality_path=legality_path)
        return RegulationStatus(
            tag=first.tag,
            letter=first.letter,
            ready=ready,
            warnings=() if ready else (REGULATION_NOT_READY,),
        )

    nxt = next((w for w in windows if w.start >= ended.exclusive_end), None)
    warnings: list[str] = []
    if nxt is None or not regulation_ready(nxt.letter, legality_path=legality_path):
        warnings.append(SCHEDULE_PAST_END_NOT_READY)
    return RegulationStatus(
        tag=ended.tag,
        letter=ended.letter,
        ready=regulation_ready(ended.letter, legality_path=legality_path),
        warnings=tuple(warnings),
    )


def active_regulation(
    *,
    now: datetime | None = None,
    schedule_path: Path | None = None,
    legality_path: Path | None = None,
) -> str:
    return regulation_status(
        now=now, schedule_path=schedule_path, legality_path=legality_path
    ).tag


_TAG_LITERAL = re.compile(
    r"^(?:champions-reg-m[a-z0-9-]*|championsregm[a-z0-9]*|"
    r"gen9championsvgc2026regm[a-z0-9]*|showdown_vgc_mb|VGC_M[A-Z])$",
    re.I,
)
_REG_M_LITERAL = re.compile(r"Reg M-[A-Z]|\[Gen 9 Champions\].*Reg M-")
_PRODUCT_MOD_LITERAL = re.compile(r"^champions$")

_AST_SKIP_PARTS = frozenset(
    {
        "artifacts",
        "_scratch",
        ".cache",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
    }
)
_DEFAULT_AST_ROOTS = (
    ROOT / "recommender",
    ROOT / "scripts" / "ci",
    ROOT / "scripts" / "extract_usage",
    ROOT / "scripts" / "eval",
    ROOT / "tests" / "ci",
    ROOT / "tests" / "recommender",
)

# Core loaders/query helpers: regulation must be required (no default).
REQUIRED_REGULATION_FUNCTIONS: frozenset[tuple[str, str]] = frozenset(
    {
        ("recommender/usage_data.py", "load_usage"),
        ("recommender/usage_data.py", "species_usage"),
        ("recommender/usage_data.py", "build_synthesis_usage_entry"),
        ("recommender/usage_data.py", "ingame_ladder_species_map"),
        ("recommender/usage_data.py", "ingame_species_map"),
        ("recommender/usage_data.py", "showdown_species_map"),
        ("recommender/usage_data.py", "featured_or_common_set"),
        ("recommender/usage_data.py", "set_from_showdown"),
        ("recommender/usage_data.py", "set_from_ingame"),
        ("recommender/usage_data.py", "load_vgcpastes_builds"),
        ("recommender/usage_chaos.py", "showdown_source_params"),
        ("recommender/by_usage.py", "query_by_usage"),
        ("recommender/counters.py", "query_counters"),
        ("recommender/threat_counters.py", "query_threat_counters"),
        ("recommender/threat_counters.py", "query_candidates_for_threats"),
        ("recommender/slot_fill.py", "_candidate_satisfies_need"),
        ("recommender/slot_fill.py", "_matching_needs_for"),
        ("recommender/move_narrowing.py", "pick_default_and_alternatives"),
    }
)

# Product-mod param default ``regulation: str = "champions"`` only — by file:function.
CHAMPIONS_MOD_DEFAULT_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        ("recommender/coverage.py", "_slot_to_spec"),
        ("recommender/coverage.py", "compute_team_coverage"),
        ("recommender/coverage.py", "detect_spof"),
        ("recommender/coverage.py", "subset_gap_counts"),
        ("recommender/coverage.py", "best_achievable_gap_counts"),
        ("recommender/coverage.py", "candidate_improves_best_bring"),
        ("recommender/teammates.py", "query_teammates"),
        ("recommender/teammates.py", "query_shared_teammates"),
        ("recommender/quick_pick.py", "quick_pick"),
        ("recommender/usage_spreads.py", "fetch_live_spreads"),
        ("recommender/usage_spreads.py", "select_usage_spread"),
        ("recommender/usage_live.py", "fetch_live_showdown_detail"),
        ("recommender/recommend.py", "select_opponent_builds"),
        ("recommender/recommend.py", "recommend_build"),
        ("recommender/role_compendium.py", "_UsageCtx"),
        ("recommender/role_compendium.py", "_offline_usage_row"),
        ("recommender/role_compendium.py", "construct_role_category"),
        ("recommender/role_compendium.py", "rebuild_role_category"),
        ("recommender/role_compendium_usage.py", "_showdown_entry"),
        ("recommender/role_compendium_setup.py", "_setup_threat_defenders"),
    }
)


def _iter_py_files(roots: Iterable[Path] | None) -> Iterable[Path]:
    for root in roots or _DEFAULT_AST_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in _AST_SKIP_PARTS for part in path.parts):
                continue
            yield path


def iter_regulation_literal_hits(
    roots: Iterable[Path] | None = None,
) -> list[tuple[str, int, str]]:
    """AST scan for regulation-ish string literals. Returns (path, lineno, value)."""
    import ast

    patterns = (
        _TAG_LITERAL,
        _REG_M_LITERAL,
        _PRODUCT_MOD_LITERAL,
    )
    hits: list[tuple[str, int, str]] = []
    for path in _iter_py_files(roots):
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            if any(p.search(value) for p in patterns):
                rel = str(path.relative_to(ROOT))
                hits.append((rel, int(getattr(node, "lineno", 0) or 0), value))
    return hits


def iter_regulation_parameter_default_hits(
    roots: Iterable[Path] | None = None,
) -> list[tuple[str, int, str, str]]:
    """AST: regulation-ish string used as a function/class parameter default.

    Returns (path, lineno, function_name, value).
    """
    import ast

    hits: list[tuple[str, int, str, str]] = []
    for path in _iter_py_files(roots):
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue
        rel = str(path.relative_to(ROOT))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = node.name
                args = node.args
                defaults = list(args.defaults)
                # Align positional-or-keyword defaults with args (rightmost).
                pos = list(args.posonlyargs) + list(args.args)
                for arg, default in zip(pos[-len(defaults) :], defaults):
                    if (
                        isinstance(default, ast.Constant)
                        and isinstance(default.value, str)
                        and (
                            _TAG_LITERAL.search(default.value)
                            or _PRODUCT_MOD_LITERAL.search(default.value)
                        )
                    ):
                        hits.append(
                            (
                                rel,
                                int(getattr(default, "lineno", 0) or 0),
                                fn,
                                default.value,
                            )
                        )
                for arg, default in zip(args.kwonlyargs, args.kw_defaults):
                    if default is None:
                        continue
                    if (
                        isinstance(default, ast.Constant)
                        and isinstance(default.value, str)
                        and (
                            _TAG_LITERAL.search(default.value)
                            or _PRODUCT_MOD_LITERAL.search(default.value)
                        )
                    ):
                        hits.append(
                            (
                                rel,
                                int(getattr(default, "lineno", 0) or 0),
                                fn,
                                default.value,
                            )
                        )
            elif isinstance(node, ast.ClassDef):
                # Dataclass field defaults: AnnAssign with Constant.
                for stmt in node.body:
                    if not isinstance(stmt, ast.AnnAssign) or stmt.value is None:
                        continue
                    if (
                        isinstance(stmt.value, ast.Constant)
                        and isinstance(stmt.value.value, str)
                        and (
                            _TAG_LITERAL.search(stmt.value.value)
                            or _PRODUCT_MOD_LITERAL.search(stmt.value.value)
                        )
                    ):
                        hits.append(
                            (
                                rel,
                                int(getattr(stmt.value, "lineno", 0) or 0),
                                node.name,
                                stmt.value.value,
                            )
                        )
    return hits


def missing_required_regulation_functions() -> list[tuple[str, str]]:
    """Registry entries with no matching function in the file (rename/delete guard)."""
    import ast

    by_file: dict[str, set[str]] = {}
    for path, fn in REQUIRED_REGULATION_FUNCTIONS:
        by_file.setdefault(path, set()).add(fn)

    found: dict[str, set[str]] = {rel: set() for rel in by_file}
    for rel, names in by_file.items():
        path = ROOT / rel
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in names:
                found[rel].add(node.name)

    missing: list[tuple[str, str]] = []
    for path, fn in sorted(REQUIRED_REGULATION_FUNCTIONS):
        if fn not in found.get(path, set()):
            missing.append((path, fn))
    return missing


def iter_required_regulation_default_hits() -> list[tuple[str, int, str, str]]:
    """Core APIs that must not default ``regulation`` (required-arg scan)."""
    import ast

    by_file: dict[str, set[str]] = {}
    for path, fn in REQUIRED_REGULATION_FUNCTIONS:
        by_file.setdefault(path, set()).add(fn)

    hits: list[tuple[str, int, str, str]] = []
    for rel, names in by_file.items():
        path = ROOT / rel
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name not in names:
                continue
            args = node.args
            pos = list(args.posonlyargs) + list(args.args)
            defaults = list(args.defaults)
            for arg, default in zip(pos[-len(defaults) :], defaults):
                if arg.arg == "regulation":
                    hits.append(
                        (rel, int(getattr(default, "lineno", 0) or 0), node.name, "default")
                    )
            for arg, default in zip(args.kwonlyargs, args.kw_defaults):
                if arg.arg == "regulation" and default is not None:
                    hits.append(
                        (rel, int(getattr(default, "lineno", 0) or 0), node.name, "default")
                    )
    return hits
