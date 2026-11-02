"""Calc service preflight, infra vs input-error classification, health ping.

Harness-only: does not change tool schemas, prompts, or tool result shapes.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from recommender.calc_client import CalcClient, CalcClientError

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PINS = ROOT / "scripts" / "eval" / "part_g_v4" / "pins_manifest.json"
VENDOR_PKG = ROOT / "vendor" / "smogon-calc" / "package.json"

# Probe sources (frozen keys / Vu worked examples — not live-derived).
PROBE_SOURCES = {
    "speed_stage_scarf_tw": (
        "Vu Dragonite Spe table / test_get_speed_dragonite_vu_examples: "
        "Jolly Spe-32 + stage1 + Scarf + Tailwind → 651"
    ),
    "speed_paralyzed_scarf": (
        "same Dragonite table: Jolly Spe-32 + Scarf + paralyzed → 108"
    ),
    "damage_mega_ability": (
        "derived_keys.dm_outputs.dm6: Gallade-Mega Inner Focus Close Combat "
        "vs Incineroar → 270-318"
    ),
    "damage_recoil": (
        "battery_damage_pool Steel Beam Kingambit vs Slowking-Galar → 76-90 "
        "(ADR-079/080 recoil path)"
    ),
}

_INFRA_MARKERS = (
    "Connection refused",
    "Errno 61",
    "Errno 111",
    "timed out",
    "Timeout",
    "URLError",
    "Remote end closed",
    "Connection reset",
    "Broken pipe",
    "ECONNREFUSED",
    "calc service exited",
    "Empty reply",
    "BadStatusLine",
    "RemoteDisconnected",
)


def expected_calc_version() -> str:
    doc = json.loads(PINS.read_text(encoding="utf-8"))
    return str((doc.get("calc_service") or {}).get("version") or "")


def vendor_calc_version() -> str:
    return str(json.loads(VENDOR_PKG.read_text(encoding="utf-8")).get("version") or "")


def classify_calc_failure(exc_or_result: object) -> str:
    """Return 'infrastructure' or 'input_refusal'."""
    if isinstance(exc_or_result, CalcClientError):
        status = int(exc_or_result.status)
        body = exc_or_result.body
        text = json.dumps(body, default=str) if not isinstance(body, str) else body
        if status == 0 or status >= 500:
            return "infrastructure"
        if any(m.lower() in text.lower() for m in _INFRA_MARKERS):
            return "infrastructure"
        if status == 400:
            return "input_refusal"
        return "input_refusal"
    if isinstance(exc_or_result, dict):
        kind = str(exc_or_result.get("error_kind") or "")
        msg = str(exc_or_result.get("message") or exc_or_result.get("error") or "")
        blob = f"{kind} {msg}"
        if any(m.lower() in blob.lower() for m in _INFRA_MARKERS):
            return "infrastructure"
        if kind in {"bad_arguments", "unknown_species", "invalid_field", "calc_error"}:
            # calc_error without transport markers = service answered with a refusal.
            if kind == "calc_error" and any(
                m.lower() in blob.lower() for m in _INFRA_MARKERS
            ):
                return "infrastructure"
            return "input_refusal"
        return "input_refusal"
    text = str(exc_or_result)
    if any(m.lower() in text.lower() for m in _INFRA_MARKERS):
        return "infrastructure"
    return "input_refusal"


def _dragonite_bare_spe(client: CalcClient) -> int:
    r = client.calculate(
        {
            "species": "Dragonite",
            "nature": "Jolly",
            "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 32},
            "level": 50,
        },
        {
            "species": "Incineroar",
            "nature": "Adamant",
            "evs": {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            "level": 50,
        },
        "Dragon Claw",
        {"gameType": "Doubles"},
    )
    return int(r["raw"]["stats"]["attacker"]["spe"])


def _apply_stage_scarf_tw_para(
    bare: int,
    *,
    stage: int = 0,
    scarf: bool = False,
    tw: bool = False,
    paralyzed: bool = False,
) -> int:
    """Match enrich_get_speed / calc getFinalSpeed floor chain."""
    speed = bare
    if stage > 0:
        speed = math.floor(speed * (2 + stage) / 2)
    elif stage < 0:
        speed = math.floor(speed * 2 / (2 + abs(stage)))
    mult = 1.0
    if scarf:
        mult *= 1.5
    if tw:
        mult *= 2.0
    if mult != 1.0:
        speed = math.floor(speed * mult)
    if paralyzed:
        speed = math.floor(speed / 2)
    return int(speed)


def run_preflight(
    client: CalcClient,
    *,
    require_version: bool = True,
) -> dict[str, Any]:
    """Four known-answer probes + version check. ok False → do not start the run."""
    out: dict[str, Any] = {
        "ok": False,
        "expected_version": expected_calc_version(),
        "vendor_version": vendor_calc_version(),
        "probes": {},
        "probe_sources": dict(PROBE_SOURCES),
        "errors": [],
    }
    if require_version and out["expected_version"] != out["vendor_version"]:
        out["errors"].append(
            f"calc version mismatch: pins {out['expected_version']!r} != "
            f"vendor {out['vendor_version']!r}"
        )
        return out
    try:
        client.health(timeout=2.0)
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"health: {type(exc).__name__}: {exc}")
        out["classification"] = classify_calc_failure(exc)
        return out

    try:
        bare = _dragonite_bare_spe(client)
        if bare != 145:
            out["errors"].append(f"Dragonite bare Spe {bare} != 145")
        a = _apply_stage_scarf_tw_para(bare, stage=1, scarf=True, tw=True)
        b = _apply_stage_scarf_tw_para(bare, scarf=True, paralyzed=True)
        out["probes"]["speed_stage_scarf_tw"] = {
            "got": a,
            "expected": 651,
            "ok": a == 651,
            "bare": bare,
        }
        out["probes"]["speed_paralyzed_scarf"] = {
            "got": b,
            "expected": 108,
            "ok": b == 108,
            "bare": bare,
        }
        if a != 651:
            out["errors"].append(f"probe a: {a} != 651")
        if b != 108:
            out["errors"].append(f"probe b: {b} != 108")
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"speed probes: {type(exc).__name__}: {exc}")
        out["classification"] = classify_calc_failure(exc)
        return out

    try:
        dm = client.calculate(
            {
                "species": "Gallade-Mega",
                "nature": "Jolly",
                "ability": "Inner Focus",
                "item": "Galladite",
                "evs": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
                "level": 50,
            },
            {
                "species": "Incineroar",
                "nature": "Adamant",
                "ability": "Intimidate",
                "item": "Sitrus Berry",
                "evs": {"hp": 32, "atk": 32, "def": 0, "spa": 0, "spd": 2, "spe": 0},
                "level": 50,
            },
            "Close Combat",
            {"gameType": "Doubles"},
        )
        lo, hi = dm.get("damageRange") or [None, None]
        if lo is None:
            rolls = dm["raw"].get("damage") or []
            lo, hi = (min(rolls), max(rolls)) if rolls else (None, None)
        ok = lo == 270 and hi == 318
        out["probes"]["damage_mega_ability"] = {
            "got": [lo, hi],
            "expected": [270, 318],
            "ok": ok,
            "attacker_ability": "Inner Focus",
            "note": "Mega ability Inner Focus (Intimidate immunity) in key-pinned range",
        }
        if not ok:
            out["errors"].append(f"probe c: damage {[lo, hi]} != [270, 318]")
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"damage mega: {type(exc).__name__}: {exc}")
        out["classification"] = classify_calc_failure(exc)
        return out

    try:
        rec = client.calculate(
            {
                "species": "Kingambit",
                "nature": "Modest",
                "ability": "Supreme Overlord",
                "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 0},
                "level": 50,
            },
            {
                "species": "Slowking-Galar",
                "nature": "Modest",
                "ability": "Curious Medicine",
                "evs": {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
                "level": 50,
            },
            "Steel Beam",
            {"gameType": "Doubles"},
        )
        lo, hi = rec.get("damageRange") or [None, None]
        if lo is None:
            rolls = rec["raw"].get("damage") or []
            lo, hi = (min(rolls), max(rolls)) if rolls else (None, None)
        raw_recoil = (rec.get("raw") or {}).get("recoil")
        ok = lo == 76 and hi == 90 and raw_recoil is not None
        out["probes"]["damage_recoil"] = {
            "got": [lo, hi],
            "expected": [76, 90],
            "ok": ok,
            "raw_recoil": raw_recoil,
        }
        if not ok:
            out["errors"].append(
                f"probe d: damage {[lo, hi]} / recoil {raw_recoil!r} != [76, 90] + recoil"
            )
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"recoil: {type(exc).__name__}: {exc}")
        out["classification"] = classify_calc_failure(exc)
        return out

    out["ok"] = not out["errors"] and all(p.get("ok") for p in out["probes"].values())
    return out


def cheap_health(client: CalcClient, *, timeout: float = 1.0) -> dict[str, Any]:
    """Between-row ping: GET /health only (lighter than full preflight)."""
    try:
        body = client.health(timeout=timeout)
        return {"ok": True, "body": body}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "classification": classify_calc_failure(exc),
        }


def scan_turn_for_infra(tool_calls: list[dict[str, Any]]) -> str | None:
    """If any tool result is an infra calc failure, return a short reason."""
    for call in tool_calls or []:
        result = call.get("result") or {}
        if not isinstance(result, dict):
            continue
        # Only treat calc-shaped failures as infra candidates.
        name = str(call.get("name") or "")
        if name and not any(
            x in name
            for x in ("calc", "damage", "speed", "survive", "ko", "spread", "solve")
        ):
            # Still classify if message looks like transport death.
            if classify_calc_failure(result) == "infrastructure":
                return f"{name}: {result.get('message') or result.get('error_kind')}"
            continue
        if classify_calc_failure(result) == "infrastructure":
            return f"{name}: {result.get('message') or result.get('error_kind')}"
    return None
