"""Extraction + scoring for bare-LLM baseline transcripts (eval-only)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

from recommender.calc_client import PokemonSpecOptional, calculate
from recommender.usage_spreads import effective_spe
from scripts.eval.oracle import item_legal, pair_legal, species_legal, to_id
from scripts.eval.species_fact_oracle import parse_claims

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


_SHOWDOWN_SPECIES = re.compile(
    r"^(?P<species>[A-Za-z][A-Za-z0-9\-'.]*(?:\s+[A-Za-z][A-Za-z0-9\-'.]*)*)"
    r"(?:\s*@\s*(?P<item>[^\n]+))?\s*$",
    re.MULTILINE,
)
_ABILITY_LINE = re.compile(r"^Ability:\s*(?P<ability>.+)$", re.MULTILINE | re.IGNORECASE)
_NATURE_LINE = re.compile(
    r"^(?P<nature>[A-Za-z]+)\s+Nature\b", re.MULTILINE | re.IGNORECASE
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


def _parse_showdown_blocks(text: str) -> list[TeamSlot]:
    blocks = re.split(r"\n\s*\n", text)
    slots: list[TeamSlot] = []
    for block in blocks:
        first = block.strip().splitlines()
        if not first:
            continue
        head = _SHOWDOWN_SPECIES.match(first[0].strip())
        if not head:
            continue
        species = head.group("species").strip()
        if len(species.split()) > 4:
            continue
        item = _norm_item(head.group("item") or "")
        ab = _ABILITY_LINE.search(block)
        nat = _NATURE_LINE.search(block)
        ev = _EV_LINE.search(block)
        moves = [m.group("move").strip() for m in _MOVE_LINE.finditer(block)]
        spread = parse_spread_body(ev.group("body")) if ev else None
        slots.append(
            TeamSlot(
                species=species,
                item=item,
                ability=(ab.group("ability").strip() if ab else ""),
                nature=(nat.group("nature").strip() if nat else "Serious"),
                spread=spread,
                moves=moves[:4],
                extractor="showdown",
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
    candidates = [
        ("showdown", _parse_showdown_blocks(transcript)),
        ("inline_at", _parse_inline_at(transcript)),
        ("numbered", _parse_numbered(transcript)),
    ]

    def density(slots: list[TeamSlot]) -> tuple[int, int, int]:
        return (
            len(slots),
            sum(1 for s in slots if s.item),
            sum(1 for s in slots if s.moves),
        )

    best_name, best_slots = max(candidates, key=lambda c: density(c[1]))
    seen: set[str] = set()
    uniq: list[TeamSlot] = []
    for s in best_slots:
        sid = to_id(s.species)
        if not sid or sid in seen:
            continue
        seen.add(sid)
        uniq.append(s)
    uniq = uniq[:6]
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
        pairs.append({"species": s.species, "item": s.item, "legal": ok})
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
        }
        for c in parse_claims(text)
    ]


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
    species_claims = score_species_facts(transcript)
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
    print("bare_llm_score structural self-check OK")


if __name__ == "__main__":
    _assert_structural_self_check()
