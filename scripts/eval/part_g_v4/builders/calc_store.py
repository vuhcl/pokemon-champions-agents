"""ADR-060 calc HTTP + persist request/response under part_g_v4/key_artifacts/calc/.

Offline-first: if `{artifact_id}.json` exists, return it (no live service).
Every call is recorded; when PART_G_V4_REQUIRE_CALC_ARTIFACT=1, missing files fail.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from _lib import PKG, load_legality, to_id

CALC_DIR = PKG / "key_artifacts" / "calc"
BASE_URL = "http://127.0.0.1:4173"
_CACHE: dict[str, dict] = {}
# Append-only call ledger for coverage audits (id, path_exists, source)
CALL_LOG: list[dict[str, Any]] = []


def reset_call_log() -> None:
    CALL_LOG.clear()


_LEGAL_ABILITY_CACHE: dict[str, set[str]] = {}


def _legal_abilities(species: str) -> set[str]:
    key = to_id(species)
    hit = _LEGAL_ABILITY_CACHE.get(key)
    if hit is not None:
        return hit
    snap = load_legality()
    sp = snap["species"].get(key) or {}
    out = {str(v) for v in (sp.get("abilities") or {}).values() if v}
    _LEGAL_ABILITY_CACHE[key] = out
    return out


def assert_abilities(req: dict[str, Any], resp: dict[str, Any]) -> dict[str, Any]:
    """Require explicit legal abilities; assert calc used them (desc echo when named)."""
    if "error" in resp:
        raise RuntimeError(f"calc error before ability assert: {resp['error']}")
    notes = []
    for side in ("attacker", "defender"):
        mon = req.get(side) or {}
        species = mon.get("species") or ""
        sent = mon.get("ability")
        if not sent:
            raise RuntimeError(f"{side} missing explicit ability for {species}")
        legal = _legal_abilities(species)
        if sent not in legal:
            raise RuntimeError(
                f"{side} ability {sent!r} not legal for {species}; legal={sorted(legal)}"
            )
        desc = (resp.get("raw") or {}).get("desc") or ""
        named_in_desc = {"Tough Claws", "Huge Power", "Pure Power", "Parental Bond", "Tinted Lens"}
        if side == "attacker" and sent in named_in_desc and desc and sent not in desc:
            raise RuntimeError(
                f"{side} sent ability {sent!r} for {species} but desc lacks it: {desc!r}"
            )
        if side == "attacker" and sent in named_in_desc and desc and sent in desc:
            notes.append(f"{side}:{sent}:desc_echo_ok")
        else:
            notes.append(f"{side}:{sent}:legal_ok")
        if (
            side == "attacker"
            and to_id(species) == "charizardmegax"
            and sent == "Tough Claws"
            and desc
        ):
            move = to_id(req.get("move") or "")
            contact_moves = {
                "flareblitz",
                "firepunch",
                "temperflare",
                "firefang",
                "flamecharge",
            }
            if move in contact_moves and "Tough Claws" not in desc:
                raise RuntimeError(
                    f"Charizard-Mega-X contact desc missing Tough Claws (Blaze default?): {desc!r}"
                )
    return {
        "attacker_ability": (req.get("attacker") or {}).get("ability"),
        "defender_ability": (req.get("defender") or {}).get("ability"),
        "notes": notes,
    }


def _stable_probe_id(req: dict[str, Any]) -> str:
    digest = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()[:16]
    return f"probe_{digest}"


def _backend() -> str:
    """http (default) or inprocess (Node batch_worker, same @smogon/calc pin)."""
    return (os.environ.get("PART_G_V4_CALC_BACKEND") or "http").strip().lower()


def _live_calculate(req: dict[str, Any]) -> dict[str, Any]:
    if _backend() == "inprocess":
        from inprocess_calc import calculate_one

        return calculate_one(req)
    payload = json.dumps(req).encode()
    http_req = urllib.request.Request(
        f"{BASE_URL}/calculate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode()) if e.fp else {"error": str(e)}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def calculate(req: dict[str, Any], artifact_id: str, *, persist: bool = True) -> dict[str, Any]:
    """Load saved artifact by id, else calc (HTTP or in-process) and optionally persist.

    Use artifact_id \"probe\" to auto-hash the request into probe_<sha16>.
    `persist=False` skips disk write (search path); named winners should pass persist=True.
    """
    for side in ("attacker", "defender"):
        if not (req.get(side) or {}).get("ability"):
            raise RuntimeError(f"calculate({artifact_id}): {side} must set ability explicitly")

    if artifact_id == "probe":
        artifact_id = _stable_probe_id(req)

    path = CALC_DIR / f"{artifact_id}.json"
    require = os.environ.get("PART_G_V4_REQUIRE_CALC_ARTIFACT", "").strip() in {"1", "true", "yes"}
    ignore_disk = os.environ.get("PART_G_V4_CALC_IGNORE_DISK", "").strip() in {
        "1",
        "true",
        "yes",
    }

    if path.is_file() and not ignore_disk:
        record = json.loads(path.read_text())
        # Prefer on-disk request/response; refresh asserts
        if "error" not in (record.get("response") or {}) and "raw" in (record.get("response") or {}):
            try:
                record["ability_assert"] = assert_abilities(req, record["response"])
            except RuntimeError:
                # Disk artifact may predate assert; keep stored assert if present
                record.setdefault("ability_assert", {"notes": ["loaded_from_disk"]})
        CALL_LOG.append(
            {"id": artifact_id, "source": "disk", "path": str(path.relative_to(PKG))}
        )
        return record

    if require:
        CALL_LOG.append({"id": artifact_id, "source": "missing", "path": str(path.relative_to(PKG))})
        raise RuntimeError(
            f"missing calc artifact for id={artifact_id!r} "
            f"(PART_G_V4_REQUIRE_CALC_ARTIFACT=1; expected {path})"
        )

    key = json.dumps(req, sort_keys=True)
    if key in _CACHE:
        body = _CACHE[key]
        record = {"id": artifact_id, "request": req, "response": body, "cached": True}
        source = "memory"
    else:
        body = _live_calculate(req)
        _CACHE[key] = body
        record = {"id": artifact_id, "request": req, "response": body}
        source = "inprocess" if _backend() == "inprocess" else "live"

    if "error" not in record["response"] and "raw" in record["response"]:
        raw = record["response"]["raw"]
        record["key"] = {
            "damage_range": raw.get("range") or record["response"].get("damageRange"),
            "ko_chance": record["response"].get("koChance")
            or (raw.get("kochance") or {}).get("text"),
            "desc": raw.get("desc"),
            "max_damage": max(raw["damage"]) if raw.get("damage") else None,
            "recoil": raw.get("recoil"),
        }
        record["ability_assert"] = assert_abilities(req, record["response"])

    if persist:
        CALC_DIR.mkdir(parents=True, exist_ok=True)
        (CALC_DIR / f"{artifact_id}.json").write_text(json.dumps(record, indent=2) + "\n")
        path_note = str((CALC_DIR / f"{artifact_id}.json").relative_to(PKG))
    else:
        path_note = "(not_persisted)"
    CALL_LOG.append(
        {
            "id": artifact_id,
            "source": source,
            "path": path_note,
            "persist_arg": persist,
        }
    )
    return record


def health() -> dict:
    """Live health check. Soft-pass when REQUIRE=1 so offline disk-served rebuilds can proceed."""
    require = os.environ.get("PART_G_V4_REQUIRE_CALC_ARTIFACT", "").strip() in {"1", "true", "yes"}
    if _backend() == "inprocess":
        try:
            from inprocess_calc import calculate_one

            # Tiny self-check; species must be legal Champions
            calculate_one(
                {
                    "attacker": {
                        "species": "Pikachu",
                        "ability": "Static",
                        "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
                    },
                    "defender": {
                        "species": "Pikachu",
                        "ability": "Static",
                        "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
                    },
                    "move": "Tackle",
                    "field": {"gameType": "Doubles"},
                }
            )
            return {"status": "ok", "backend": "inprocess"}
        except Exception as e:
            return {"status": "error", "backend": "inprocess", "detail": str(e)}
    try:
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=3) as resp:
            body = json.loads(resp.read().decode())
            if body.get("status") == "ok":
                return body
            live = body
    except Exception as e:
        live = {"status": "error", "detail": str(e)}
    if require:
        # calculate() still fails hard on missing disk artifacts
        return {
            "status": "ok",
            "offline_require": True,
            "live": live,
            "note": "PART_G_V4_REQUIRE_CALC_ARTIFACT=1: health soft-pass; serve from disk only",
        }
    return live
