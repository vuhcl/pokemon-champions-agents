"""ADR-060 calc HTTP + persist request/response under part_g_v4/key_artifacts/calc/."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from _lib import PKG, load_legality, to_id

CALC_DIR = PKG / "key_artifacts" / "calc"
BASE_URL = "http://127.0.0.1:4173"
_CACHE: dict[str, dict] = {}


def _legal_abilities(species: str) -> set[str]:
    snap = load_legality()
    sp = snap["species"].get(to_id(species)) or {}
    return {str(v) for v in (sp.get("abilities") or {}).values() if v}


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
        # Abilities @smogon/calc literally names in desc when they modify the attacker's roll
        named_in_desc = {"Tough Claws", "Huge Power", "Pure Power", "Parental Bond", "Tinted Lens"}
        if side == "attacker" and sent in named_in_desc and desc and sent not in desc:
            raise RuntimeError(
                f"{side} sent ability {sent!r} for {species} but desc lacks it: {desc!r}"
            )
        if side == "attacker" and sent in named_in_desc and desc and sent in desc:
            notes.append(f"{side}:{sent}:desc_echo_ok")
        else:
            notes.append(f"{side}:{sent}:legal_ok")
        # Mega-X as attacker on contact moves: Tough Claws must appear (Blaze default omits it)
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


def calculate(req: dict[str, Any], artifact_id: str, *, persist: bool = True) -> dict[str, Any]:
    """POST /calculate; optionally write {id}.json; return merged record."""
    # Cross-cutting: every key calc must send abilities
    for side in ("attacker", "defender"):
        if not (req.get(side) or {}).get("ability"):
            raise RuntimeError(f"calculate({artifact_id}): {side} must set ability explicitly")

    key = json.dumps(req, sort_keys=True)
    if key in _CACHE:
        body = _CACHE[key]
        record = {"id": artifact_id, "request": req, "response": body, "cached": True}
    else:
        CALC_DIR.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(req).encode()
        http_req = urllib.request.Request(
            f"{BASE_URL}/calculate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(http_req, timeout=30) as resp:
                body = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = json.loads(e.read().decode()) if e.fp else {"error": str(e)}
        except Exception as e:
            body = {"error": f"{type(e).__name__}: {e}"}
        _CACHE[key] = body
        record = {"id": artifact_id, "request": req, "response": body}

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
        (CALC_DIR / f"{artifact_id}.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def health() -> dict:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=3) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"status": "error", "detail": str(e)}
