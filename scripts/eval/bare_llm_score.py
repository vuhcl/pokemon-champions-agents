"""Extraction + scoring for bare-LLM baseline transcripts (eval-only)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from recommender.calc_client import PokemonSpecOptional, calculate
from recommender.legality import load_snapshot, resolve_learnset
from recommender.species_forms import item_mega_forme
from recommender.usage_spreads import effective_spe
from scripts.eval.oracle import item_legal, pair_legal, species_legal, to_id
from scripts.eval.species_fact_oracle import (
    load_species_snapshot,
    parse_claims,
    resolve_species,
    to_id as sf_to_id,
)

_STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")
_ZERO_SP = {k: 0 for k in _STAT_KEYS}

SpreadShape = Literal["EV-shaped", "SP-shaped", "unparsed"]
MechVerdict = Literal["TRUE", "FALSE", "unverifiable_shape"]


@dataclass
class TeamSlot:
    species: str
    item: str = ""
    ability: str = ""
    nature: str = "Serious"
    spread: dict[str, int] | None = None
    moves: list[str] = field(default_factory=list)
    extractor: str = ""
    # True when paste/prose claims Mega (e.g. "Lucario (Mega Evolution) @ Leftovers").
    # Mega forme requires its stone — not Leftovers / Life Orb / etc.
    mega_claimed: bool = False
    mega_xy: str | None = None  # "x" / "y" when specified


@dataclass
class ExtractedTeam:
    slots: list[TeamSlot]
    extractor: str
    incomplete: bool

    @property
    def completed(self) -> bool:
        return len(self.slots) == 6 and not self.incomplete


def _norm_item(raw: str) -> str:
    return re.sub(r"\s+", " ", raw.strip())


# Species [@ Item], with optional (Nickname)/(Form)/(M|F) before @.
_SHOWDOWN_SPECIES = re.compile(
    r"^(?P<species>[A-Za-z][A-Za-z0-9\-'.]*(?:\s+[A-Za-z][A-Za-z0-9\-'.]*)*)"
    r"(?:\s*\((?P<paren>[^)]*)\))?"
    r"(?:\s*@\s*(?P<item>[^\n]+))?\s*$",
    re.MULTILINE,
)
_MEGA_TOKEN = re.compile(
    r"\bmega(?:\s*[- ]?\s*(?P<xy>[xy]))?\b", re.IGNORECASE
)
_ABILITY_LINE = re.compile(r"^Ability:\s*(?P<ability>.+)$", re.MULTILINE | re.IGNORECASE)
_NATURE_LINE = re.compile(
    r"^(?:(?P<nature>[A-Za-z]+)\s+Nature\b|Nature:\s*(?P<nature2>[A-Za-z]+))",
    re.MULTILINE | re.IGNORECASE,
)
_EV_LINE = re.compile(
    r"^(?:EVs|SP|SPs):\s*(?P<body>.+)$", re.MULTILINE | re.IGNORECASE
)
_MOVE_LINE = re.compile(r"^[-–—]\s*(?P<move>.+)$", re.MULTILINE)
_NUMBERED = re.compile(
    r"^\s*\d+[.)]\s*"
    r"(?P<species>[A-Za-z][A-Za-z0-9\-'.]*(?:\s+[A-Za-z][A-Za-z0-9\-'.]*)*)"
    r"(?:\s*[@–—-]\s*(?P<item>[^\n]+))?",
    re.MULTILINE,
)
# Markdown / prose set blocks (common bare-LLM shape):
#   ### Slot 3: Toxel
#   - **Item:** Leftovers
#   - **Ability:** Poison Point
#   - **Moves:**
#     - Toxic
_MD_SLOT_HEADER = re.compile(
    r"(?:"
    r"#{1,4}\s*Slot\s*\d+\s*[:\-–—]\s*"
    r"|"
    r"\*\*Slot\s*\d+\s*[:\-–—]\s*"
    r"|"
    r"(?:^|\n)\s*(?:Slot\s*\d+\s*[:\-–—]\s*)"
    r"|"
    # Chat-shaped numbered set headers: ### 1. Species / 1. **Species**
    r"#{1,4}\s*\d+\.\s*"
    r"|"
    r"(?:^|\n)\s*\d+\.\s*\*?\*?"
    r")"
    r"(?P<species>[A-Za-z][A-Za-z0-9\-'.]*(?:\s+[A-Za-z][A-Za-z0-9\-'.]*){0,3})",
    re.IGNORECASE,
)
_MEGA_PREFIX_NAME = re.compile(
    r"^Mega\s+(?P<base>.+?)(?:\s+(?P<xy>[XY]))?$",
    re.IGNORECASE,
)
_MEGA_SUFFIX_NAME = re.compile(
    r"^(?P<base>.+?)-Mega(?:-(?P<xy>[XY]))?$",
    re.IGNORECASE,
)
_MD_FIELD = re.compile(
    r"^\s*[-*]?\s*\*?\*?(?P<key>Item|Ability|Nature|Spread|EVs|SP|SPs|Moves?)"
    r"\*?\*?\s*[:\-–—]\s*(?P<val>.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_STAT_TOKEN = re.compile(
    r"(?P<n>\d+)\s+(?P<stat>HP|Atk|Def|SpA|SpD|Spe)\b", re.IGNORECASE
)


def parse_spread_body(body: str) -> dict[str, int] | None:
    alias = {
        "hp": "hp",
        "atk": "atk",
        "def": "def",
        "spa": "spa",
        "spd": "spd",
        "spe": "spe",
    }
    out = {k: 0 for k in _STAT_KEYS}
    hits = 0
    for m in _STAT_TOKEN.finditer(body):
        key = alias[m.group("stat").casefold()]
        out[key] = int(m.group("n"))
        hits += 1
    return out if hits else None


def classify_spread(spread: dict[str, int] | None) -> SpreadShape:
    if not spread or any(k not in spread for k in _STAT_KEYS):
        return "unparsed"
    vals = [int(spread[k]) for k in _STAT_KEYS]
    total = sum(vals)
    if any(v > 32 for v in vals) or 480 <= total <= 520:
        return "EV-shaped"
    if all(0 <= v <= 32 for v in vals):
        return "SP-shaped"
    return "unparsed"


def _mega_flags(species: str, paren: str = "") -> tuple[bool, str | None]:
    """Detect Mega claim from species name and/or (Mega …) paren."""
    blob = f"{species} {paren}".strip()
    m = _MEGA_TOKEN.search(blob)
    if not m:
        return False, None
    xy = (m.group("xy") or "").lower() or None
    return True, xy


def _normalize_species(
    species: str, paren: str = ""
) -> tuple[str, bool, str | None]:
    """Strip Mega label to base name; return (species, mega_claimed, mega_xy)."""
    raw = species.strip().rstrip("*").strip()
    raw = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
    m = _MEGA_PREFIX_NAME.match(raw)
    if m:
        xy = (m.group("xy") or "").lower() or None
        return m.group("base").strip(), True, xy
    m = _MEGA_SUFFIX_NAME.match(raw)
    if m:
        xy = (m.group("xy") or "").lower() or None
        return m.group("base").strip(), True, xy
    mega_claimed, mega_xy = _mega_flags(raw, paren)
    return raw, mega_claimed, mega_xy


def _sid_is_mega_forme(sid: str) -> bool:
    return bool(re.search(r"mega[xyz]?$", sid))


def _mega_stone_legal(
    snap: dict[str, Any],
    species: str,
    item: str,
    *,
    mega_claimed: bool,
    mega_xy: str | None,
) -> bool | None:
    """None = no mega constraint; True/False = stone matches / does not."""
    sid = to_id(species)
    species_map = snap.get("species") or {}
    entry = species_map.get(sid)
    base_id: str | None = None
    want_mega: str | None = None  # None after claim → any mega stone for base

    if entry and entry.get("base_species_id") and _sid_is_mega_forme(sid):
        base_id = str(entry["base_species_id"])
        want_mega = sid
    elif mega_claimed:
        base_id = sid
        if mega_xy == "x":
            want_mega = f"{base_id}megax"
        elif mega_xy == "y":
            want_mega = f"{base_id}megay"
        else:
            want_mega = None  # any stone → a mega forme for this base
    else:
        return None

    got = item_mega_forme(to_id(item), base_id, snap)
    if not got:
        return False
    if want_mega is None:
        return True
    return got == want_mega


def _parse_showdown_blocks(text: str) -> list[TeamSlot]:
    """Line-scan Showdown pastes (incl. inside markdown fences). Requires @ Item."""
    lines = text.splitlines()
    slots: list[TeamSlot] = []
    i = 0
    while i < len(lines):
        raw = lines[i].strip()
        if raw in ("```", "```text", "```pokemon"):
            i += 1
            continue
        head = _SHOWDOWN_SPECIES.match(raw)
        if not head or not head.group("item"):
            i += 1
            continue
        species = head.group("species").strip()
        if len(species.split()) > 4:
            i += 1
            continue
        item = _norm_item(head.group("item") or "")
        species, mega_claimed, mega_xy = _normalize_species(
            species, head.group("paren") or ""
        )
        # Collect body until blank, fence, or next Species @ Item header.
        body_lines = [raw]
        i += 1
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt or nxt.startswith("```"):
                break
            nxt_head = _SHOWDOWN_SPECIES.match(nxt)
            if nxt_head and nxt_head.group("item"):
                break
            body_lines.append(nxt)
            i += 1
        block = "\n".join(body_lines)
        ab = _ABILITY_LINE.search(block)
        nat = _NATURE_LINE.search(block)
        nature = "Serious"
        if nat:
            nature = (nat.group("nature") or nat.group("nature2") or "Serious").strip()
        ev = _EV_LINE.search(block)
        moves = [m.group("move").strip() for m in _MOVE_LINE.finditer(block)]
        spread = parse_spread_body(ev.group("body")) if ev else None
        slots.append(
            TeamSlot(
                species=species,
                item=item,
                ability=(ab.group("ability").strip() if ab else ""),
                nature=nature,
                spread=spread,
                moves=moves[:4],
                extractor="showdown",
                mega_claimed=mega_claimed,
                mega_xy=mega_xy,
            )
        )
    return slots


def _parse_numbered(text: str) -> list[TeamSlot]:
    slots: list[TeamSlot] = []
    for m in _NUMBERED.finditer(text):
        slots.append(
            TeamSlot(
                species=m.group("species").strip(),
                item=_norm_item(m.group("item") or ""),
                extractor="numbered",
            )
        )
    return slots


def _parse_markdown_slots(text: str) -> list[TeamSlot]:
    """Extract ### Slot N: Species + bullet Item/Ability/Moves blocks."""
    headers = list(_MD_SLOT_HEADER.finditer(text))
    if not headers:
        return []
    slots: list[TeamSlot] = []
    for i, h in enumerate(headers):
        species = h.group("species").strip().rstrip("*").strip()
        # Role blurbs ("Psychic Type Pokémon…") are not species names.
        if (
            len(species.split()) > 3
            or "type" in species.casefold()
            or species.casefold() in {"mega", "pokemon", "pokémon"}
        ):
            continue
        species, mega_claimed, mega_xy = _normalize_species(species)
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[h.end() : end]
        item = ability = nature = ""
        spread = None
        moves: list[str] = []
        in_moves = False
        for line in block.splitlines():
            fm = _MD_FIELD.match(line)
            if fm:
                key = fm.group("key").casefold()
                val = fm.group("val").strip().strip("*").strip()
                in_moves = key.startswith("move")
                if key == "item":
                    # First bullet wins; drop explanatory tails
                    # ("Leftovers to provide some HP recovery…").
                    if not item:
                        cleaned = re.split(
                            r"\s+to\s+|\.|/", val, maxsplit=1, flags=re.I
                        )[0].strip()
                        if cleaned and len(cleaned.split()) <= 4:
                            item = _norm_item(cleaned)
                elif key == "ability":
                    ability = val.split("(")[0].strip()
                elif key == "nature":
                    nature = val.split("(")[0].strip() or "Serious"
                elif key in ("spread", "evs", "sp", "sps"):
                    spread = parse_spread_body(val) or spread
                elif in_moves and val:
                    # "Moves: A, B, C" single-line list, or empty then bullets
                    if not val.startswith("-"):
                        parts = [p.strip() for p in re.split(r"\s*,\s*", val) if p.strip()]
                        moves.extend(parts)
                continue
            if in_moves:
                bullet = re.match(r"^\s*[-*•]\s+(.+)$", line)
                if bullet:
                    moves.append(bullet.group(1).strip().strip("*").strip())
                elif line.strip() and not line.strip().startswith("#"):
                    # end move list on next prose heading-ish
                    if line.strip().startswith("**") or line.strip().startswith("###"):
                        in_moves = False
        if not item:
            # Composition lists / role blurbs without @ Item aren't sets.
            continue
        slots.append(
            TeamSlot(
                species=species,
                item=item,
                ability=ability,
                nature=nature or "Serious",
                spread=spread,
                moves=moves[:4],
                extractor="markdown_slot",
                mega_claimed=mega_claimed,
                mega_xy=mega_xy,
            )
        )
    return slots


def _parse_inline_at(text: str) -> list[TeamSlot]:
    slots: list[TeamSlot] = []
    for m in _SHOWDOWN_SPECIES.finditer(text):
        if "@" not in m.group(0):
            continue
        species = m.group("species").strip()
        if len(species.split()) > 4:
            continue
        slots.append(
            TeamSlot(
                species=species,
                item=_norm_item(m.group("item") or ""),
                extractor="inline_at",
            )
        )
    return slots


def extract_team(transcript: str) -> ExtractedTeam:
    showdown = _parse_showdown_blocks(transcript)
    candidates = [
        ("showdown", showdown),
        ("markdown_slot", _parse_markdown_slots(transcript)),
        ("inline_at", _parse_inline_at(transcript)),
        ("numbered", _parse_numbered(transcript)),
    ]

    def density(slots: list[TeamSlot]) -> tuple[int, int, int]:
        # Prefer filled sets over a longer list of bare species names.
        return (
            sum(1 for s in slots if s.item),
            sum(1 for s in slots if s.moves),
            len(slots),
        )

    # Prefer Showdown paste when it has a near-complete set of @ Item lines
    # (chat markdown can otherwise outvote it on raw header count).
    if sum(1 for s in showdown if s.item) >= 4:
        best_name, best_slots = "showdown", showdown
    else:
        best_name, best_slots = max(candidates, key=lambda c: density(c[1]))

    def richness(s: TeamSlot) -> tuple[int, int, int, int]:
        return (
            1 if s.item else 0,
            1 if s.ability else 0,
            len(s.moves),
            1 if s.spread else 0,
        )

    seen: dict[str, TeamSlot] = {}
    order: list[str] = []
    for s in best_slots:
        sid = to_id(s.species)
        if not sid:
            continue
        if sid not in seen:
            order.append(sid)
            seen[sid] = s
        elif richness(s) > richness(seen[sid]):
            seen[sid] = s
    uniq = [seen[sid] for sid in order][:6]
    return ExtractedTeam(
        slots=uniq, extractor=best_name, incomplete=len(uniq) < 6
    )


def item_clause_violation(team: ExtractedTeam) -> bool | None:
    if not team.completed:
        return None
    items = [to_id(s.item) for s in team.slots if s.item.strip()]
    return len(items) != len(set(items))


def spread_shapes(team: ExtractedTeam) -> list[SpreadShape]:
    return [classify_spread(s.spread) for s in team.slots if s.spread is not None]


_BAN_CLAIM = re.compile(
    r"(?P<subject>[A-Za-z][A-Za-z0-9\-']*(?:\s+[A-Za-z][A-Za-z0-9\-']*){0,3})"
    r"\s+(?:is|are|was|were)\s+"
    r"(?:banned|illegal|not\s+(?:legal|available|allowed)|unusable)"
    r"(?:\s+in\s+(?:Reg(?:ulation)?\s*)?M-?C|\s+in\s+Champions)?",
    re.IGNORECASE,
)


def extract_false_illegal(text: str, snap: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in _BAN_CLAIM.finditer(text):
        subj = m.group("subject").strip()
        if species_legal(snap, subj):
            out.append(
                {"subject": subj, "kind": "species", "display": m.group(0).strip()}
            )
        elif subj and item_legal(snap, subj):
            # item_legal(True) for unknown-empty only when empty; unknown items False
            e = (snap.get("items") or {}).get(to_id(subj))
            if e is not None:
                out.append(
                    {"subject": subj, "kind": "item", "display": m.group(0).strip()}
                )
    return out


def score_pair_legality(team: ExtractedTeam, snap: dict[str, Any]) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    false_legal = 0
    for s in team.slots:
        if not s.item.strip():
            continue
        ok = pair_legal(snap, s.species, s.item)
        stone = _mega_stone_legal(
            snap,
            s.species,
            s.item,
            mega_claimed=s.mega_claimed,
            mega_xy=s.mega_xy,
        )
        if stone is False:
            ok = False
        pairs.append(
            {
                "species": s.species,
                "item": s.item,
                "legal": ok,
                "mega_claimed": s.mega_claimed,
                "mega_stone_ok": stone,
            }
        )
        if not ok:
            false_legal += 1
    return {"pairs_checked": len(pairs), "false_legal": false_legal, "pairs": pairs}


_SPE_CLAIM = re.compile(
    r"(?P<a>[A-Za-z][A-Za-z0-9\-']*(?:\s+[A-Za-z][A-Za-z0-9\-']*){0,2})"
    r"\s+(?P<rel>outspeeds?|outpaces?|is\s+faster\s+than|is\s+slower\s+than|"
    r"faster\s+than|slower\s+than)\s+"
    r"(?P<b>[A-Za-z][A-Za-z0-9\-']*(?:\s+[A-Za-z][A-Za-z0-9\-']*){0,2})",
    re.IGNORECASE,
)
_KO_CLAIM = re.compile(
    r"(?P<a>[A-Za-z][A-Za-z0-9\-']*(?:\s+[A-Za-z][A-Za-z0-9\-']*){0,2})"
    r"(?:\s+(?:with|'s)\s+(?P<move>[A-Za-z][A-Za-z0-9\-']*"
    r"(?:\s+[A-Za-z][A-Za-z0-9\-']*){0,3}))?"
    r"\s+(?P<ko>OHKOs?|2HKOs?|3HKOs?)\s+"
    r"(?P<b>[A-Za-z][A-Za-z0-9\-']*(?:\s+[A-Za-z][A-Za-z0-9\-']*){0,2})",
    re.IGNORECASE,
)


def _slot_by_name(team: ExtractedTeam, name: str) -> TeamSlot | None:
    want = to_id(name)
    for s in team.slots:
        if to_id(s.species) == want:
            return s
    return None


def _spe_of(slot: TeamSlot | None, species: str) -> int | None:
    nature = (slot.nature if slot else "Serious") or "Serious"
    spread = dict(_ZERO_SP)
    scarf = False
    if slot and classify_spread(slot.spread) == "SP-shaped" and slot.spread:
        spread = slot.spread
        scarf = to_id(slot.item) == "choicescarf"
    try:
        return effective_spe(species, spread, nature, scarf=scarf)
    except Exception:
        return None


def _ko_n(text: str) -> int | None:
    t = text.upper()
    if t.startswith("OHKO"):
        return 1
    if t.startswith("2HKO"):
        return 2
    if t.startswith("3HKO"):
        return 3
    return None


def score_mech_claims(
    text: str, team: ExtractedTeam, *, calc_ok: bool
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in _SPE_CLAIM.finditer(text):
        a, b = m.group("a").strip(), m.group("b").strip()
        rel = m.group("rel").lower()
        sa = _spe_of(_slot_by_name(team, a), a)
        sb = _spe_of(_slot_by_name(team, b), b)
        display = m.group(0).strip()
        if sa is None or sb is None:
            verdict: MechVerdict = "unverifiable_shape"
        else:
            wants_faster = "slower" not in rel
            ok = (sa > sb) if wants_faster else (sa < sb)
            verdict = "TRUE" if ok else "FALSE"
        out.append(
            {"kind": "spe", "display": display, "verdict": verdict, "a": a, "b": b}
        )

    for m in _KO_CLAIM.finditer(text):
        a, b = m.group("a").strip(), m.group("b").strip()
        move = (m.group("move") or "").strip()
        ko_n = _ko_n(m.group("ko"))
        attacker = _slot_by_name(team, a)
        display = m.group(0).strip()
        if not calc_ok:
            out.append(
                {
                    "kind": "ko",
                    "display": display,
                    "verdict": "unverifiable_shape",
                    "note": "calc_down",
                }
            )
            continue
        if attacker and not move and attacker.moves:
            move = attacker.moves[0]
        if (
            attacker is None
            or classify_spread(attacker.spread) != "SP-shaped"
            or not move
            or ko_n is None
            or attacker.spread is None
        ):
            out.append(
                {"kind": "ko", "display": display, "verdict": "unverifiable_shape"}
            )
            continue
        atk: PokemonSpecOptional = {
            "species": attacker.species,
            "item": attacker.item or "",
            "ability": attacker.ability or "",
            "nature": attacker.nature or "Serious",
            "evs": dict(attacker.spread),
            "moves": list(attacker.moves) or [move],
        }
        dfn: PokemonSpecOptional = {"species": b, "evs": dict(_ZERO_SP)}
        try:
            result = calculate(atk, dfn, move, field={"gameType": "Doubles"})
            ko_text = (result.get("koChance") or "").lower()
            if not ko_text:
                verdict = "unverifiable_shape"
            elif ko_n == 1:
                verdict = "TRUE" if "ohko" in ko_text else "FALSE"
            elif ko_n == 2:
                verdict = "TRUE" if "2hko" in ko_text or "2-hit" in ko_text else "FALSE"
            else:
                verdict = "TRUE" if "3hko" in ko_text or "3-hit" in ko_text else "FALSE"
        except Exception:
            verdict = "unverifiable_shape"
        out.append(
            {
                "kind": "ko",
                "display": display,
                "verdict": verdict,
                "move": move,
                "a": a,
                "b": b,
            }
        )
    return out


def score_species_facts(text: str) -> list[dict[str, Any]]:
    return [
        {
            "kind": c.kind,
            "species": c.species,
            "asserted_value": c.asserted_value,
            "verdict": c.verdict,
            "display": c.display,
            "source": "prose",
        }
        for c in parse_claims(text)
    ]


def _move_name_index(snap: dict[str, Any]) -> dict[str, str]:
    """sf_to_id → canonical display name for known moves."""
    out: dict[str, str] = {}
    for key, entry in (snap.get("moves") or {}).items():
        if isinstance(entry, dict):
            mid = str(entry.get("id") or key)
            name = str(entry.get("name") or mid)
        else:
            mid = str(key)
            name = str(entry) if entry else mid
        out[sf_to_id(mid)] = name
        out[sf_to_id(name)] = name
    return out


def _longest_known_move(raw: str, mv_index: dict[str, str]) -> str | None:
    text = raw.strip().rstrip(".,;:!?")
    if not text:
        return None
    words = text.split()
    for n in range(len(words), 0, -1):
        cand = " ".join(words[:n])
        hit = mv_index.get(sf_to_id(cand))
        if hit is not None:
            return hit
    return None


def score_build_derived_claims(team: ExtractedTeam) -> list[dict[str, Any]]:
    """Implicit assertions from proposed sets (moves + ability). Item → legality."""
    by_id = load_species_snapshot()
    snap = load_snapshot()
    mv_index = _move_name_index(snap)
    out: list[dict[str, Any]] = []
    for slot in team.slots:
        entry = resolve_species(slot.species, by_id)
        species_name = str(entry["name"]) if entry else slot.species

        if slot.ability.strip():
            ab = slot.ability.strip()
            if entry is None:
                verdict = "unverifiable_shape"
                asserted = ab
            else:
                abilities = [
                    str(v)
                    for v in (entry.get("abilities") or {}).values()
                    if isinstance(v, str)
                ]
                want = sf_to_id(ab)
                if any(sf_to_id(a) == want for a in abilities):
                    verdict = "TRUE"
                    asserted = next(a for a in abilities if sf_to_id(a) == want)
                elif want and not any(sf_to_id(a) == want for a in abilities):
                    # Known-looking ability string not on species → FALSE if it
                    # matches any ability in the snapshot inventory; else unverifiable.
                    all_abs = {
                        sf_to_id(str(v)): str(v)
                        for e in by_id.values()
                        for v in (e.get("abilities") or {}).values()
                        if isinstance(v, str)
                    }
                    if want in all_abs:
                        verdict = "FALSE"
                        asserted = all_abs[want]
                    else:
                        verdict = "unverifiable_shape"
                        asserted = ab
                else:
                    verdict = "unverifiable_shape"
                    asserted = ab
            out.append(
                {
                    "kind": "ability",
                    "species": species_name if entry else None,
                    "asserted_value": asserted,
                    "verdict": verdict,
                    "display": f"{species_name} set ability: {asserted}",
                    "source": "build",
                }
            )

        learnset = resolve_learnset(snap, species_name) if entry else None
        learn_ids = {sf_to_id(m) for m in (learnset or [])}
        for raw_move in slot.moves:
            if not raw_move.strip():
                continue
            canon = _longest_known_move(raw_move, mv_index)
            if canon is None:
                out.append(
                    {
                        "kind": "move",
                        "species": species_name if entry else None,
                        "asserted_value": raw_move.strip(),
                        "verdict": "unverifiable_shape",
                        "display": f"{species_name} set: {raw_move.strip()}",
                        "source": "build",
                    }
                )
                continue
            if entry is None or learnset is None:
                verdict = "unverifiable_shape"
            else:
                verdict = "TRUE" if sf_to_id(canon) in learn_ids else "FALSE"
            out.append(
                {
                    "kind": "move",
                    "species": species_name if entry else None,
                    "asserted_value": canon,
                    "verdict": verdict,
                    "display": f"{species_name} set: {canon}",
                    "source": "build",
                }
            )
    return out


def merge_species_fact_claims(
    prose: list[dict[str, Any]], build: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Dedupe by (species, kind, value); prefer build for display when both."""
    by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str]] = []

    def key_of(row: dict[str, Any]) -> tuple[str, str, str]:
        return (
            sf_to_id(str(row.get("species") or "")),
            str(row.get("kind") or ""),
            sf_to_id(str(row.get("asserted_value") or "")),
        )

    for row in prose:
        k = key_of(row)
        if k not in by_key:
            order.append(k)
        by_key[k] = dict(row)
        by_key[k]["source"] = "prose"
    for row in build:
        k = key_of(row)
        if k not in by_key:
            order.append(k)
            by_key[k] = dict(row)
        else:
            # Prefer build display / source when duplicate.
            merged = dict(by_key[k])
            merged["verdict"] = row.get("verdict", merged.get("verdict"))
            merged["display"] = row.get("display", merged.get("display"))
            merged["source"] = "build"
            by_key[k] = merged
    return [by_key[k] for k in order]


def tally_verdicts(rows: list[dict[str, Any]]) -> dict[str, int]:
    c: Counter[str] = Counter(str(r.get("verdict", "unverifiable_shape")) for r in rows)
    return {
        "TRUE": int(c.get("TRUE", 0)),
        "FALSE": int(c.get("FALSE", 0)),
        "unverifiable_shape": int(c.get("unverifiable_shape", 0)),
        "total": len(rows),
    }


def score_transcript(
    transcript: str, snap: dict[str, Any], *, calc_ok: bool
) -> dict[str, Any]:
    team = extract_team(transcript)
    prose = score_species_facts(transcript)
    build = score_build_derived_claims(team)
    species_claims = merge_species_fact_claims(prose, build)
    false_illegal = extract_false_illegal(transcript, snap)
    pair = score_pair_legality(team, snap)
    mech = score_mech_claims(transcript, team, calc_ok=calc_ok)
    shapes = spread_shapes(team)
    ev_n = sum(1 for s in shapes if s == "EV-shaped")
    sp_n = sum(1 for s in shapes if s == "SP-shaped")
    unparsed_n = sum(1 for s in shapes if s == "unparsed")
    no_spread = sum(1 for s in team.slots if s.spread is None)
    return {
        "team": {
            "extractor": team.extractor,
            "incomplete": team.incomplete,
            "completed": team.completed,
            "slots": [
                {
                    "species": s.species,
                    "item": s.item,
                    "ability": s.ability,
                    "nature": s.nature,
                    "spread": s.spread,
                    "spread_shape": classify_spread(s.spread),
                    "moves": s.moves,
                    "mega_claimed": s.mega_claimed,
                    "mega_xy": s.mega_xy,
                }
                for s in team.slots
            ],
        },
        "legality": {
            **pair,
            "false_illegal": len(false_illegal),
            "false_illegal_examples": false_illegal[:8],
        },
        "species_facts": {
            "claims": species_claims,
            "tally": tally_verdicts(species_claims),
            "prose_n": len(prose),
            "build_n": len(build),
        },
        "mechanical": {
            "claims": mech,
            "tally": tally_verdicts(mech),
            "calc_ok": calc_ok,
        },
        "structural": {
            "spreads_ev_shaped": ev_n,
            "spreads_sp_shaped": sp_n,
            "spreads_unparsed": unparsed_n + no_spread,
            "spreads_parsed_denom": ev_n + sp_n,
            "item_clause_violation": item_clause_violation(team),
        },
    }


def _six_showdown_blocks() -> str:
    """Six Showdown-ish sets for extraction self-check (completed team)."""
    blocks = []
    specs = [
        ("Incineroar", "Safety Goggles", "Intimidate", "Fake Out", "Flare Blitz"),
        ("Amoonguss", "Rocky Helmet", "Regenerator", "Spore", "Rage Powder"),
        ("Flutter Mane", "Choice Specs", "Protosynthesis", "Moonblast", "Shadow Ball"),
        ("Rillaboom", "Assault Vest", "Grassy Surge", "Wood Hammer", "U-turn"),
        ("Landorus-Therian", "Choice Scarf", "Intimidate", "Earthquake", "U-turn"),
        ("Heliolisk", "Life Orb", "Dry Skin", "Thunderbolt", "Close Combat"),
    ]
    for sp, item, ab, m1, m2 in specs:
        blocks.append(
            f"{sp} @ {item}\n"
            f"Ability: {ab}\n"
            f"Timid Nature\n"
            f"EVs: 20 HP / 0 Atk / 4 Def / 32 SpA / 0 SpD / 10 Spe\n"
            f"- {m1}\n"
            f"- {m2}\n"
        )
    return "\n".join(blocks)


def _assert_structural_self_check() -> None:
    assert (
        classify_spread(
            {"hp": 252, "atk": 0, "def": 4, "spa": 252, "spd": 0, "spe": 0}
        )
        == "EV-shaped"
    )
    assert (
        classify_spread(
            {"hp": 20, "atk": 0, "def": 4, "spa": 32, "spd": 0, "spe": 10}
        )
        == "SP-shaped"
    )
    assert classify_spread(None) == "unparsed"
    paste = (
        "Incineroar @ Safety Goggles\n"
        "Ability: Intimidate\n"
        "Adamant Nature\n"
        "EVs: 252 Atk / 4 Def / 252 Spe\n"
        "- Fake Out\n"
        "- Flare Blitz\n\n"
        "Amoonguss @ Rocky Helmet\n"
        "Ability: Regenerator\n"
        "EVs: 252 HP / 252 Def / 4 SpD\n"
        "- Spore\n"
    )
    team = extract_team(paste)
    assert len(team.slots) >= 2, team
    assert team.slots[0].species == "Incineroar"
    assert classify_spread(team.slots[0].spread) == "EV-shaped"
    six = ExtractedTeam(
        slots=[
            TeamSlot("A", item="Leftovers"),
            TeamSlot("B", item="Leftovers"),
            TeamSlot("C", item="Sitrus Berry"),
            TeamSlot("D", item="Focus Sash"),
            TeamSlot("E", item="Life Orb"),
            TeamSlot("F", item="Choice Specs"),
        ],
        extractor="test",
        incomplete=False,
    )
    assert item_clause_violation(six) is True
    six2 = ExtractedTeam(
        slots=[TeamSlot(f"S{i}", item=f"Item{i}") for i in range(6)],
        extractor="test",
        incomplete=False,
    )
    assert item_clause_violation(six2) is False

    full = extract_team(_six_showdown_blocks())
    assert full.completed, (len(full.slots), full.incomplete, full.extractor)
    md = extract_team(
        "### Slot 1: Heliolisk\n"
        "- **Item:** Life Orb\n"
        "- **Ability:** Dry Skin\n"
        "- **Moves:**\n"
        "  - Thunderbolt\n"
        "  - Close Combat\n\n"
        "### Slot 2: Incineroar\n"
        "- **Item:** Safety Goggles\n"
        "- **Ability:** Intimidate\n"
        "- **Moves:**\n"
        "  - Fake Out\n"
        "  - Flare Blitz\n"
    )
    assert md.extractor == "markdown_slot" and len(md.slots) == 2, md
    assert md.slots[0].item == "Life Orb" and "Thunderbolt" in md.slots[0].moves
    chat_md = extract_team(
        "### Team Composition\n"
        "1. **Mega Charizard X**\n\n"
        "#### 1. Mega Charizard X\n"
        "- **Ability**: Blaze\n"
        "- **Item**: Leftovers\n"
        "- **Nature**: Adamant\n"
        "- **EVs**: 252 Atk / 252 Spe / 4 HP\n"
        "- **Moves**: Fire Blast, Dragon Dance, Flamethrower, Roost\n\n"
        "#### 2. Incineroar\n"
        "- **Ability**: Intimidate\n"
        "- **Item**: Safety Goggles\n"
        "- **Moves**: Fake Out, Flare Blitz\n"
    )
    assert chat_md.extractor == "markdown_slot", chat_md.extractor
    assert chat_md.slots[0].species == "Charizard"
    assert chat_md.slots[0].mega_claimed and chat_md.slots[0].mega_xy == "x"
    assert chat_md.slots[0].item == "Leftovers"
    assert "Fire Blast" in chat_md.slots[0].moves
    assert chat_md.slots[1].species == "Incineroar"
    paren = extract_team(
        "Here is the set:\n"
        "```\n"
        "Lucario (Mega Evolution) @ Leftovers\n"
        "Ability: Inner Focus\n"
        "Nature: Bold\n"
        "EVs: 252 HP / 252 Atk / 4 SpD\n"
        "- Gyro Ball\n"
        "- Psychic\n"
        "```\n\n"
        "Blacephalon (Mega Evolution) @ Choice Specs\n"
        "Ability: Beast Boost\n"
        "EVs: 4 HP / 252 SpA / 252 Spe\n"
        "- Shadow Ball\n"
    )
    assert paren.extractor == "showdown", paren.extractor
    assert len(paren.slots) == 2 and paren.slots[0].species == "Lucario"
    assert paren.slots[0].item == "Leftovers" and paren.slots[0].nature == "Bold"
    assert paren.slots[0].mega_claimed is True
    assert "Gyro Ball" in paren.slots[0].moves
    # Mega claim + non-stone item is false-legal (correct paste: Lucario @ Lucarionite).
    from recommender.legality import load_snapshot as _load_snap

    mega_legality = score_pair_legality(paren, _load_snap())
    assert mega_legality["false_legal"] >= 1, mega_legality
    assert any(p.get("mega_stone_ok") is False for p in mega_legality["pairs"])
    ok_mega = extract_team(
        "Lucario (Mega Evolution) @ Lucarionite\n"
        "Ability: Adaptability\n"
        "- Close Combat\n"
    )
    ok_score = score_pair_legality(ok_mega, _load_snap())
    assert ok_score["false_legal"] == 0 and ok_score["pairs"][0]["mega_stone_ok"] is True
    build_claims = score_build_derived_claims(full)
    move_false = [
        c
        for c in build_claims
        if c["kind"] == "move"
        and c.get("species") == "Heliolisk"
        and c.get("asserted_value") == "Close Combat"
    ]
    assert len(move_false) == 1 and move_false[0]["verdict"] == "FALSE", move_false
    assert move_false[0]["source"] == "build"
    # Unknown move → unverifiable
    junk = ExtractedTeam(
        slots=[
            TeamSlot(
                "Heliolisk",
                item="Life Orb",
                ability="Dry Skin",
                moves=["NotARealMoveXYZ"],
            )
        ],
        extractor="test",
        incomplete=True,
    )
    junk_claims = score_build_derived_claims(junk)
    assert any(
        c["kind"] == "move" and c["verdict"] == "unverifiable_shape" for c in junk_claims
    ), junk_claims
    # Empty ability → no ability claim
    bare = ExtractedTeam(
        slots=[TeamSlot("Heliolisk", item="Life Orb", ability="", moves=["Thunderbolt"])],
        extractor="test",
        incomplete=True,
    )
    bare_claims = score_build_derived_claims(bare)
    assert all(c["kind"] != "ability" for c in bare_claims), bare_claims
    # Merge prefers build display
    prose = [
        {
            "kind": "move",
            "species": "Heliolisk",
            "asserted_value": "Close Combat",
            "verdict": "FALSE",
            "display": "Heliolisk can learn Close Combat",
            "source": "prose",
        }
    ]
    merged = merge_species_fact_claims(prose, move_false)
    assert len(merged) == 1 and merged[0]["source"] == "build"
    print("bare_llm_score structural self-check OK")


if __name__ == "__main__":
    _assert_structural_self_check()
