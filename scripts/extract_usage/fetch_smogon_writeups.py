#!/usr/bin/env python3
"""Fetch Smogon Strategy Dex writeups into resolved-build cache (Tracks E/F)."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from recommender.ids import to_id  # noqa: E402
from recommender.resolved_builds import (  # noqa: E402
    DEFAULT_DIR,
    get_resolved_build,
    put_resolved_build,
)
from recommender.sp_convert import evs_to_sp  # noqa: E402

UA = "pokemon-champions-agents/0.1"
RPC = "https://www.smogon.com/dex/_rpc"
THIN = 80
PAUSE = 0.2

SEED = [
    "Garchomp",
    "Kingambit",
    "Incineroar",
    "Charizard-Mega-Y",
    "Whimsicott",
    "Pelipper",
    "Sinistcha",
    "Basculegion",
    "Farigiraf",
    "Sneasler",
    "Hatterene",
    "Archaludon",
]

MEGA_STONE = {
    "charizarditey": "charizardmegay",
    "charizarditex": "charizardmegax",
    "blazikenite": "blazikenmega",
    "metagrossite": "metagrossmega",
    "swampertite": "swampertmega",
}

ABILITY_MEGA = {
    "drought": "charizardmegay",
    "toughclaws": "charizardmegax",
}

PRIMARY_ALIASES = frozenset({"vgc", "battle-stadium-singles"})


class _Strip(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", "".join(self._parts)).strip()


def strip_html(html: str) -> str:
    if not html:
        return ""
    p = _Strip()
    try:
        p.feed(html)
        p.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    return p.text()


def format_alias(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def rpc(method: str, body: dict[str, Any]) -> Any:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{RPC}/{method}",
        data=data,
        headers={"User-Agent": UA, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def dump_basics(gen: str) -> dict[str, Any]:
    return rpc("dump-basics", {"gen": gen})


def dump_format(gen: str, alias: str) -> dict[str, Any] | None:
    out = rpc("dump-format", {"alias": alias, "gen": gen, "language": "en"})
    return out if isinstance(out, dict) else None


def dump_pokemon(gen: str, alias: str) -> dict[str, Any] | None:
    out = rpc("dump-pokemon", {"alias": alias, "gen": gen, "language": "en"})
    return out if isinstance(out, dict) else None


def base_page_name(species: str) -> str:
    for suf in ("-Mega-Y", "-Mega-X", "-Mega"):
        if species.endswith(suf):
            return species[: -len(suf)]
    return species


def smogon_alias(species: str) -> str:
    return format_alias(base_page_name(species))


def wanted_mega_id(seed_name: str) -> str | None:
    sid = to_id(seed_name)
    if sid.endswith(("megay", "megax")) or (
        sid.endswith("mega") and not sid.endswith(("megay", "megax"))
    ):
        return sid
    return None


def resolve_mega(
    page_species: str,
    items: list[str],
    abilities: list[str],
    set_name: str,
    prose: str,
) -> str | None:
    """Return Showdown species id, or None to skip."""
    for it in items:
        mid = MEGA_STONE.get(to_id(it))
        if mid:
            return mid
    # Mega Charizard Y's ability is Drought — check the *set* ability list only
    # (not teammate Drought mentions in writeup prose).
    for ab in abilities:
        mid = ABILITY_MEGA.get(to_id(ab))
        if mid:
            return mid
    name_l = (set_name or "").lower()
    page = to_id(page_species)
    # Set-name cues (e.g. "Drought Offense") — not full prose (avoids teammate Drought)
    if page == "charizard" or page.startswith("charizard"):
        if re.search(r"mega[\s-]*y|charizardite\s*y|\bdrought\b", name_l):
            return "charizardmegay"
        if re.search(r"mega[\s-]*x|charizardite\s*x|\btough\s*claws\b", name_l):
            return "charizardmegax"
        prose_l = (prose or "").lower()
        if re.search(r"mega[\s-]*y|charizardite\s*y", prose_l):
            return "charizardmegay"
        if re.search(r"mega[\s-]*x|charizardite\s*x", prose_l):
            return "charizardmegax"
    if re.search(r"\bmega\b", name_l):
        for mid in ("blazikenmega", "metagrossmega", "swampertmega"):
            if page in mid or mid.startswith(page):
                return mid
    if any(to_id(it) in MEGA_STONE for it in items):
        return None
    return to_id(page_species)


def flatten_moves(moveslots: list[Any]) -> list[str] | None:
    out: list[str] = []
    for slot in moveslots or []:
        if not slot:
            return None
        first = slot[0]
        if isinstance(first, dict):
            mv = first.get("move")
        else:
            mv = first
        if not mv:
            return None
        out.append(str(mv))
    return out if len(out) >= 4 else None


def spread_and_variants(evconfigs: list[dict[str, int]]) -> tuple[dict[str, int], list[dict[str, int]] | None]:
    if not evconfigs:
        return {k: 0 for k in ("hp", "atk", "def", "spa", "spd", "spe")}, None

    def one(cfg: dict[str, int]) -> dict[str, int]:
        vals = {k: int(cfg.get(k, 0)) for k in ("hp", "atk", "def", "spa", "spd", "spe")}
        if max(vals.values(), default=0) > 32:
            return evs_to_sp(vals)
        return vals

    primary = one(evconfigs[0])
    rest = [one(c) for c in evconfigs[1:]] or None
    return primary, rest


def rationale_of(strategy: dict[str, Any], moveset: dict[str, Any]) -> str:
    parts = [
        strip_html(moveset.get("description") or ""),
        strip_html(strategy.get("overview") or ""),
        strip_html(strategy.get("comments") or ""),
    ]
    return "\n\n".join(p for p in parts if p)


def is_thin(rationale: str) -> bool:
    return len(rationale) < THIN


def enumerate_sv_formats() -> list[dict[str, Any]]:
    basics = dump_basics("sv")
    out: list[dict[str, Any]] = []
    for f in basics.get("formats") or []:
        name = f.get("name") or ""
        low = name.lower()
        if not any(
            k in low
            for k in ("vgc", "battle stadium singles", "bss", "battle spot singles")
        ):
            continue
        # Avoid matching unrelated names that merely contain "bss" as substring of another word — BSS is acronym
        if "bss" in low and "battle stadium" not in low and not re.search(r"\bbss\b", low):
            if "vgc" not in low and "battle spot" not in low:
                continue
        alias = format_alias(name)
        tier = "primary" if alias in PRIMARY_ALIASES else "secondary"
        out.append({"name": name, "alias": alias, "tier": tier})
    # Confirm primaries exist
    for alias in PRIMARY_ALIASES:
        if not any(x["alias"] == alias for x in out):
            print(f"warn: primary alias {alias} missing from dump-basics", file=sys.stderr)
        elif dump_format("sv", alias) is None:
            print(f"warn: dump-format null for primary {alias}", file=sys.stderr)
    return out


def put_writeup(
    *,
    species: str,
    moves: list[str],
    item: str,
    regulation: str,
    spread: dict[str, int],
    source_tier: str,
    source_format: str,
    rationale: str,
    variants: list[dict[str, int]] | None,
    analog_tier: str | None = None,
) -> bool:
    """Respect verified skip + never replace primary analogous with secondary."""
    existing = get_resolved_build(species, moves, item, regulation, chain=False)
    if existing and existing.get("verified") is True:
        print(f"  skip verified {to_id(species)}/{to_id(item)}", file=sys.stderr)
        return False
    if analog_tier == "secondary" and existing:
        sf = existing.get("source_format") or ""
        if sf in ("sv/vgc", "sv/battle-stadium-singles") and not is_thin(
            existing.get("rationale") or ""
        ):
            print(f"  skip secondary over primary {to_id(species)}", file=sys.stderr)
            return False
    notes = {}
    if analog_tier:
        notes = {"notes": f"analog:{analog_tier}"}
    ok = put_resolved_build(
        species,
        moves,
        item,
        regulation,
        spread,
        source_tier,
        False,
        notes,  # type: ignore[arg-type]
        variants=variants,
        rationale=rationale,
        source_format=source_format,
    )
    return ok


def iter_movesets(
    poke: dict[str, Any],
    format_names: set[str],
    page_name: str,
    only_species: str | None = None,
) -> list[dict[str, Any]]:
    """Yield normalized moveset dicts."""
    results: list[dict[str, Any]] = []
    for strat in poke.get("strategies") or []:
        fmt = strat.get("format") or ""
        if fmt not in format_names:
            continue
        for ms in strat.get("movesets") or []:
            moves = flatten_moves(ms.get("moveslots") or [])
            if not moves:
                continue
            items = list(ms.get("items") or []) or [""]
            abilities = list(ms.get("abilities") or [])
            rat = rationale_of(strat, ms)
            spread, variants = spread_and_variants(list(ms.get("evconfigs") or []))
            for item in items[:3]:
                if not item:
                    continue
                resolved = resolve_mega(
                    page_name, [item], abilities, ms.get("name") or "", rat
                )
                if resolved is None:
                    continue
                if only_species and resolved != only_species:
                    continue
                # If page is mega-capable and item is mega stone, resolved is mega — ok
                # Skip storing bare base when item is mega stone but resolve failed (already None)
                results.append(
                    {
                        "species": resolved,
                        "moves": moves,
                        "item": item,
                        "spread": spread,
                        "variants": variants,
                        "rationale": rat,
                        "format": fmt,
                    }
                )
    return results


def species_has_mb_native_nonthin(species_id: str) -> bool:
    path = DEFAULT_DIR / "champions-reg-mb.jsonl"
    if not path.exists():
        return False
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("species") != species_id:
            continue
        if row.get("source_tier") != "champions_native_writeup":
            continue
        if not is_thin(row.get("rationale") or ""):
            return True
    return False


def track_e() -> dict[str, Any]:
    stats: dict[str, Any] = {
        "mb_pages": [],
        "mb_written": 0,
        "ma_written": 0,
        "mega_y_kept": 0,
        "seed_mb_page_intersect": 0,
    }
    mb = dump_format("champions", "vgc-2026-regulation-m-b")
    ma = dump_format("champions", "vgc-2026-regulation-m-a")
    assert mb and mb.get("pokemon_with_strategies"), "M-B format dump failed"
    assert ma and ma.get("pokemon_with_strategies"), "M-A format dump failed"
    mb_list = list(mb["pokemon_with_strategies"])
    ma_list = list(ma["pokemon_with_strategies"])
    stats["mb_pages"] = mb_list
    seed_base_ids = {to_id(base_page_name(s)) for s in SEED}
    mb_ids = {to_id(n) for n in mb_list}
    stats["seed_mb_page_intersect"] = len(seed_base_ids & mb_ids)

    for name in mb_list:
        time.sleep(PAUSE)
        print(f"E/MB dump {name}", file=sys.stderr)
        poke = dump_pokemon("champions", format_alias(name))
        if not poke:
            continue
        for row in iter_movesets(poke, {"VGC 2026 Regulation M-B"}, name):
            if put_writeup(
                species=row["species"],
                moves=row["moves"],
                item=row["item"],
                regulation="champions-reg-mb",
                spread=row["spread"],
                source_tier="champions_native_writeup",
                source_format="champions/vgc-2026-regulation-m-b",
                rationale=row["rationale"],
                variants=row["variants"],
            ):
                stats["mb_written"] += 1

    ma_names = {to_id(n): n for n in ma_list}
    # page_name -> seeds that share that Smogon page (e.g. Charizard + Mega-Y)
    seeds_by_page: dict[str, list[str]] = {}
    for seed in SEED:
        seeds_by_page.setdefault(base_page_name(seed), []).append(seed)

    for page, seeds in seeds_by_page.items():
        page_id = to_id(page)
        if page_id not in ma_names:
            print(f"E/MA skip page {page} (not on M-A list)", file=sys.stderr)
            continue
        display = ma_names[page_id]
        time.sleep(PAUSE)
        print(f"E/MA dump {display}", file=sys.stderr)
        poke = dump_pokemon("champions", format_alias(display))
        if not poke:
            continue
        for seed in seeds:
            only = wanted_mega_id(seed)
            for row in iter_movesets(
                poke, {"VGC 2026 Regulation M-A"}, display, only_species=only
            ):
                if put_writeup(
                    species=row["species"],
                    moves=row["moves"],
                    item=row["item"],
                    regulation="champions-reg-ma",
                    spread=row["spread"],
                    source_tier="champions_native_writeup",
                    source_format="champions/vgc-2026-regulation-m-a",
                    rationale=row["rationale"],
                    variants=row["variants"],
                ):
                    stats["ma_written"] += 1
                    if row["species"] == "charizardmegay":
                        stats["mega_y_kept"] += 1

    # Champions BSS writeups (e.g. Charizard Mega-Y "Drought Offense") → M-B cache
    stats["bss_written"] = 0
    stats["bss_mega_y"] = 0
    for page, seeds in seeds_by_page.items():
        time.sleep(PAUSE)
        print(f"E/BSS dump {page}", file=sys.stderr)
        poke = dump_pokemon("champions", format_alias(page))
        if not poke:
            continue
        for seed in seeds:
            only = wanted_mega_id(seed)
            for row in iter_movesets(
                poke, {"Battle Stadium Singles"}, page, only_species=only
            ):
                if put_writeup(
                    species=row["species"],
                    moves=row["moves"],
                    item=row["item"],
                    regulation="champions-reg-mb",
                    spread=row["spread"],
                    source_tier="champions_native_writeup",
                    source_format="champions/battle-stadium-singles",
                    rationale=row["rationale"],
                    variants=row["variants"],
                ):
                    stats["bss_written"] += 1
                    if row["species"] == "charizardmegay":
                        stats["bss_mega_y"] += 1
    return stats


def track_f(sv_formats: list[dict[str, Any]]) -> dict[str, Any]:
    stats: dict[str, Any] = {"written": 0, "by_format": {}, "filled_species": []}
    primary = [f for f in sv_formats if f["tier"] == "primary"]
    secondary = [f for f in sv_formats if f["tier"] == "secondary"]

    def pri_key(f: dict[str, Any]) -> tuple[int, str]:
        a = f["alias"]
        if a == "vgc":
            return (0, a)
        if a == "battle-stadium-singles":
            return (1, a)
        return (2, a)

    primary_o = sorted(primary, key=pri_key)
    secondary_o = sorted(
        secondary,
        key=lambda f: (0 if f["alias"].startswith("vgc") else 1, f["alias"]),
    )
    name_to_meta = {f["name"]: f for f in sv_formats}

    for seed in SEED:
        sid = to_id(seed)
        if species_has_mb_native_nonthin(sid):
            print(f"F skip {seed}: has M-B native", file=sys.stderr)
            continue
        alias = smogon_alias(seed)
        page_name = base_page_name(seed)
        time.sleep(PAUSE)
        print(f"F dump sv/{alias} for {seed}", file=sys.stderr)
        poke = dump_pokemon("sv", alias)
        if not poke:
            print("  no pokemon dump", file=sys.stderr)
            continue

        only = wanted_mega_id(seed)
        got = False
        for group in (primary_o, secondary_o):
            if got:
                break
            format_names = {f["name"] for f in group}
            rows = iter_movesets(poke, format_names, page_name, only_species=only)

            def row_pri(r: dict[str, Any]) -> int:
                meta = name_to_meta.get(r["format"])
                if not meta:
                    return 9
                if meta["alias"] == "vgc":
                    return 0
                if meta["alias"] == "battle-stadium-singles":
                    return 1
                if meta["alias"].startswith("vgc"):
                    return 2
                return 3

            rows.sort(key=row_pri)
            for row in rows:
                meta = name_to_meta.get(row["format"])
                if not meta:
                    continue
                if is_thin(row["rationale"]) and max(row["spread"].values(), default=0) == 0:
                    continue
                sf = f"sv/{meta['alias']}"
                if put_writeup(
                    species=row["species"],
                    moves=row["moves"],
                    item=row["item"],
                    regulation="champions-reg-mb",
                    spread=row["spread"],
                    source_tier="analogous_format_writeup",
                    source_format=sf,
                    rationale=row["rationale"],
                    variants=row["variants"],
                    analog_tier=meta["tier"],
                ):
                    stats["written"] += 1
                    stats["by_format"][sf] = stats["by_format"].get(sf, 0) + 1
                    if not is_thin(row["rationale"]):
                        got = True
                        stats["filled_species"].append(seed)
                        break
    return stats


def main() -> int:
    print("=== SV BSS/VGC formats (live) ===", file=sys.stderr)
    sv_formats = enumerate_sv_formats()
    for f in sv_formats:
        print(f"  {f['tier']:9} {f['alias']:40} {f['name']}", file=sys.stderr)
    assert any(f["alias"] == "vgc" for f in sv_formats), "primary vgc missing"
    assert any(f["alias"] == "battle-stadium-singles" for f in sv_formats), "primary BSS missing"

    print("=== Track E ===", file=sys.stderr)
    e_stats = track_e()
    print("=== Track F ===", file=sys.stderr)
    f_stats = track_f(sv_formats)

    mb_path = DEFAULT_DIR / "champions-reg-mb.jsonl"
    assert mb_path.exists() and mb_path.read_text().strip(), "mb cache empty"
    rows = [json.loads(l) for l in mb_path.read_text().splitlines() if l.strip()]
    assert any(
        r.get("source_tier") in ("champions_native_writeup", "analogous_format_writeup")
        for r in rows
    )

    report = {
        "sv_formats": sv_formats,
        "track_e": e_stats,
        "track_f": f_stats,
        "mb_rows": len(rows),
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
