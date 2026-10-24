#!/usr/bin/env python3
"""Part G per-template claim extractors (ADR-060: no recommender imports; reads an answer record and the item's frozen key).

extract_item(item, answer) -> list[Claim]: typed claims already scored by the scorer's rules. Built and tuned on dev half P only
(dev_split.json); half T is untouched. Claims about facts the key does not hold are not extracted (they are not typed claims).
Negation is resolved into the proposition, a hedge is a claim with no verdict, and every claim carries copied_unchanged: the final_text contains
the whole tool-result line that carries the claim (see copied_unchanged_lines.md). The scorer reads that flag; it is computed here, from the
transcript, never in the scorer.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import copied_lines as cl  # noqa: E402
import scorer as sc  # noqa: E402
from scorer import Claim, Verdict  # noqa: E402

TYPES = "Normal Fire Water Electric Grass Ice Fighting Poison Ground Flying Psychic Bug Rock Ghost Dragon Dark Steel Fairy".split()
NUM = r"(\d+(?:\.\d+)?)"
WORDNUM = {"zero": 0, "none": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
           "all": 16}


def clean(t: str) -> str:
    """Markdown emphasis and backticks become spaces, so every offset in the cleaned text is an offset in final_text."""
    return re.sub(r"[*`]", " ", t)


_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"(\[])|\n+")


def sents_pos(t: str) -> list[tuple[str, int]]:
    """(sentence, start offset in final_text), emphasis blanked."""
    c, out, pos = clean(t), [], 0
    for m in list(_SPLIT.finditer(c)) + [None]:
        end = m.start() if m else len(c)
        seg = c[pos:end]
        lead = len(seg) - len(seg.lstrip())
        if seg.strip():
            out.append((seg.strip(), pos + lead))
        pos = m.end() if m else end
    return out


def sents(t: str) -> list[str]:
    return [s for s, _ in sents_pos(t)]


def first_sentence(t: str) -> str:
    ss = sents(t)
    return ss[0] if ss else ""


def first_span(t: str) -> tuple[int, int] | None:
    sp = sents_pos(t)
    return (sp[0][1], sp[0][1] + len(sp[0][0])) if sp else None


def at(c: Claim, span: tuple[int, int] | None) -> Claim:
    return replace(c, span=span)


def at_m(c: Claim, m: re.Match, off: int = 0) -> Claim:
    return replace(c, span=(m.start() + off, m.end() + off))


NEG = re.compile(r"\b(?:no|not|isn't|doesn't|does not|is not|cannot|can't|cannot have|never)\b|n't\b", re.I)


def polarity(text: str) -> bool | None:
    """The yes/no proposition the answer asserts, resolved from its first sentence (None = hedge or no verdict)."""
    f = first_sentence(text).lower()
    if re.match(r"^(yes|correct|true|that is correct)\b", f):
        return True
    if re.match(r"^(no|incorrect|false)\b", f) or NEG.search(f):
        return False
    if re.search(r"\b(?:is|are) legal\b|\bcan (?:use|have)\b|\bhas\b|\bcan be used\b", f):
        return True
    return None


# --- copied_unchanged ---------------------------------------------------------------------------

def flag(claims: list[Claim], answer: dict[str, Any]) -> list[Claim]:
    """Set copied_unchanged per copied_unchanged_lines.md: the final_text contains the whole tool-result line that carries the claim."""
    calls, text = answer.get("tool_calls") or [], answer.get("final_text") or ""
    return [replace(c, copied_unchanged=cl.is_copied_unchanged(c.kind, c.proposition, c.line, calls, text)) if c.verdict is not None else c for c in claims]


# --- shared pieces -----------------------------------------------------------------------------

def _names_in(phrase: str) -> list[str]:
    phrase = re.sub(r"\((?:or|also)?\s*([^)]*?)(?:\s+for [^)]*)?\)", r", \1", phrase)
    out = []
    for part in re.split(r",|\band\b|\bor\b|/|;", phrase):
        name = re.sub(r"^(?:the|a|an|its|three|two|only|also|either|abilities|ability)\s+", "", part.strip(" .:'\"\u2019"), flags=re.I).strip()
        if name and re.match(r"^[A-Z][\w'\u2019\-]*(?:\s+[A-Za-z][\w'\u2019\-]*){0,3}$", name):
            out.append(name)
    return out


_LIST_LEAD = (r"(?:abilities (?:are|include)|abilit(?:y|ies) (?:is|are)|its only abilit(?:y|ies) (?:is|are)|can have|has the abilit(?:y|ies)|"
              r"one of its abilities|(?:full )?typing is|(?:is|are) (?:a |an )?(?:dual[- ]typed? )?(?:pok\u00e9mon )?(?:of )?)")


def _list_claims(text: str, kind: str, subject: str, key_list: list[str], ctype: str, skip_first: bool) -> list[Claim]:
    """Membership claims from phrases like "abilities are A, B and C"; exact-list claims from "only"/"pure" phrasing."""
    claims: list[Claim] = []
    keyset = {sc.norm(k) for k in key_list}
    for i, (s, off) in enumerate(sents_pos(text)):
        if skip_first and i == 0:
            continue
        low = s.lower()
        if NEG.search(low) and not re.search(r"abilit(?:y|ies) (?:is|are)|abilities include|its abilities|typing is|types are", low):
            continue
        m = re.search(_LIST_LEAD + r"[:\s]+([^.]+)", s, re.I)
        if not m:
            continue
        names = [n for n in _names_in(m.group(1)) if kind != "type_list_member" or n.title() in TYPES]
        for n in names:
            j = s.find(n, m.start(1))
            span = (off + j, off + j + len(n)) if j >= 0 else (off, off + len(s))
            claims.append(Claim(kind, subject, n, Verdict.TRUE if sc.norm(n) in keyset else Verdict.FALSE, ctype=ctype, span=span))
        if names and re.search(r"\b(?:only|pure|single|sole)\b", low):
            same = {sc.norm(n) for n in names} == keyset
            claims.append(Claim(kind + "_exact", subject, "|".join(sorted(names)), Verdict.TRUE if same else Verdict.FALSE, ctype=ctype, span=(off, off + len(s))))
    return sc.dedupe(claims)


def _types_in(s: str) -> list[str]:
    return [t for t in TYPES if re.search(rf"\b{t}\b", s)]


# --- per type ----------------------------------------------------------------------------------

def x_typing(it, a):
    gt = it["claims"][0]["ground_truth"]
    text, subj, asked = a["final_text"], gt["species"], gt["asked_type"]
    claims = [at(replace(sc.score_equal("has_type", subj, polarity(text), gt["has_type"]), ctype="typing"), first_span(text))]
    for i, (s, off) in enumerate(sents_pos(text)):
        low = s.lower()
        if NEG.search(low) and i > 0 and not re.search(r"\bbut\b", low):
            continue
        tys = [t for t in _types_in(s) if not (i == 0 and t == asked)]
        if i == 0 and NEG.search(low):  # "No, X is not a Fire type. ..." the asked type is negated, nothing else is stated here
            tys = []
        for t in tys:
            m = re.search(rf"\b{t}\b", s)
            claims.append(Claim("type_list_member", subj, t, Verdict.TRUE if t in gt["types"] else Verdict.FALSE, ctype="typing",
                                span=(off + m.start(), off + m.end())))
        if tys and re.search(r"\b(?:pure|only|single)\b", low):
            claims.append(Claim("type_list_member_exact", subj, "|".join(sorted(_types_in(s))),
                                Verdict.TRUE if sorted(_types_in(s)) == sorted(gt["types"]) else Verdict.FALSE, ctype="typing", span=(off, off + len(s))))
    return sc.dedupe(claims)


def x_ability(it, a):
    gt = it["claims"][0]["ground_truth"]
    key_list = gt.get("form_abilities") or gt["abilities"]
    subj = gt.get("form") or gt["species"]
    text = a["final_text"]
    claims = [at(replace(sc.score_equal("has_ability", subj, polarity(text), gt["has_ability"]), ctype=it["claim_type"]), first_span(text))]
    extras = _list_claims(text, "ability_list_member", subj, key_list, it["claim_type"], skip_first=True)
    claims += [c for c in extras if sc.norm(c.proposition) != sc.norm(gt["asked_ability"]) or c.kind.endswith("_exact")]
    return sc.dedupe(claims)


def x_item(it, a):
    gt = it["claims"][0]["ground_truth"]
    return [at(replace(sc.score_equal("item_legal", gt["item"], polarity(a["final_text"]), gt["legal"]), ctype="item"), first_span(a["final_text"]))]


def x_legality(it, a):
    gt = it["claims"][0]["ground_truth"]
    return [at(replace(sc.score_equal("species_legal", gt["species"], polarity(a["final_text"]), gt["legal"]), ctype="legality"), first_span(a["final_text"]))]


def x_speed(it, a):
    gt = it["claims"][0]["ground_truth"]
    kind = it["claims"][0]["kind"]
    text, s1, s2 = a["final_text"], gt["s1"], gt["s2"]
    sp = sents_pos(text)
    verdict_sentences = [(s, off) for s, off in sp if re.search(r"faster|outspeed|slower|\btie\b", s, re.I)]
    stated, vspan = None, None
    if verdict_sentences:
        fs = sp[0]
        s, off = fs if re.search(r"faster|outspeed|slower", fs[0], re.I) else verdict_sentences[-1]
        vspan = (off, off + len(s))
        low = s.lower()
        if not re.search(r"\btie\b|same speed", low):
            i1, i2 = s.find(s1), s.find(s2)
            lead = s1 if (i1 >= 0 and (i2 < 0 or i1 < i2)) else s2
            neg = bool(re.search(r"slower|does not outspeed|doesn't outspeed|not faster|cannot outspeed|isn't faster", low))
            winner = (s2 if lead == s1 else s1) if neg else lead
            stated = winner == s1
    claims = [at(replace(sc.score_equal(kind, f"{s1}|{s2}", stated, gt["s1_outspeeds"]), ctype="speed"), vspan)]
    names = [s1, s2]
    for s, off in sp:
        for m in re.finditer(rf"(?<![\w.]){NUM}(?![\w%])(?!\.\d)", s):
            if not re.search(r"speed|\bspe\b", s, re.I) or re.match(r"\s*(?:Spe(?:ed)?\s+)?SP\b", s[m.end():], re.I):
                continue  # a number followed by "SP" is the prompt's SP echoed back, not a Speed stat
            if re.search(r"\bby\s*$", s[:m.start()], re.I) or re.match(r"\s*(?:Speed\s+)?points?\b", s[m.end():], re.I):
                continue  # a margin, handled below
            prev = [(s.rfind(n, 0, m.start()), n) for n in names if s.rfind(n, 0, m.start()) >= 0]
            if prev:
                claims.append(at_m(sc.score_speed_stat(gt, max(prev)[1], float(m.group(1))), m, off))
        for m in re.finditer(rf"by {NUM}\s*(?:points?|Speed)?", s):
            if re.search(r"faster|outspeed|slower", s[:m.start()], re.I):
                claims.append(at_m(sc.score_speed_margin(gt, s1, s2, float(m.group(1))), m, off))
    return sc.dedupe(claims)


def x_move_static(it, a):
    gt = it["claims"][0]["ground_truth"]
    kind = it["claims"][0]["kind"]
    subj = gt["move"]
    out: dict[str, Any] = {"category": None, "move_type": None, "base_power": None}
    spans: dict[str, tuple[int, int] | None] = {"category": None, "move_type": None, "base_power": None}
    for s, off in sents_pos(a["final_text"]):
        low = s.lower()
        if re.search(r"not a move|isn't a move|is a held item|terrain effect", low):
            continue
        for c in ("Physical", "Special", "Status"):
            m = re.search(rf"\b{c}\b", s, re.I)
            if m and not re.search(rf"(?:not|n't|no)\s+(?:a\s+)?{c}", s, re.I) and "like" not in low:
                out["category"], spans["category"] = c, (off + m.start(), off + m.end())
        m = re.search(r"\b(" + "|".join(TYPES) + r")[- ]type|type (?:is|of)\s+(" + "|".join(TYPES) + r")", s, re.I)
        if m:
            out["move_type"], spans["move_type"] = (m.group(1) or m.group(2)).title(), (off + m.start(), off + m.end())
        m = re.search(rf"base power (?:of |is )?{NUM}|{NUM}\s*(?:base power|BP)\b|base power of [^.\d]{{1,40}}? is {NUM}", s, re.I)
        if m:
            out["base_power"], spans["base_power"] = int(float(next(g for g in m.groups() if g))), (off + m.start(), off + m.end())
        elif re.search(r"no base power|base power of 0|0 base power", low):
            m = re.search(r"no base power|base power of 0|0 base power", low)
            out["base_power"], spans["base_power"] = 0, (off + m.start(), off + m.end())
    keyname = {"category": "category", "move_type": "type", "base_power": "basePower"}
    claims = []
    for k in ("category", "move_type", "base_power"):
        if out[k] is not None or k == kind:
            claims.append(at(replace(sc.score_equal(k, subj, out[k], gt[keyname[k]]), ctype="move_static"), spans[k]))
    return claims


# --- damage ------------------------------------------------------------------------------------

def _subject(gt: dict[str, Any]) -> str:
    return f"{gt['attacker']} {gt['move']} {gt['defender']}"


def _ko_pct_claim(gt, pct: float, m: re.Match) -> Claim:
    return at_m(Claim("ko_chance", _subject(gt), f"{pct:g}%", Verdict.TRUE if abs(pct - 100 * gt["rolls_ko_of_16"] / 16) <= gt["scoring"]["chance_tolerance_points"] else Verdict.FALSE,
                      line="ko_chance", ctype="damage"), m)


def _ko_numbers(text: str, gt: dict[str, Any]) -> list[Claim]:
    claims: list[Claim] = []
    low = text.lower()
    ratio = lambda n, d, m: at_m(sc.score_ko_ratio(gt, n, d), m)  # noqa: E731
    for m in re.finditer(r"(?<!every )(?<!each )(?<!single )(\d+|\b(?:zero|none|one|two|three|four|five|six|seven|eight|nine|ten|all)\b)\s*(?:out of|of)\s*(?:the\s*)?(\d+)\s*(?:possible\s*|damage\s*)*rolls?", low):
        n = int(m.group(1)) if m.group(1).isdigit() else WORDNUM[m.group(1)]
        if re.search(r"\b(?:ko|knock)", low[max(0, m.start() - 60):m.end() + 80]) and not re.search(r"(?:not|n't|fail|insufficient|survive)", low[m.end():m.end() + 25]):
            claims.append(ratio(n, int(m.group(2)), m))
    for m in re.finditer(r"\b(?:all (?:16 )?(?:of )?(?:the )?(?:16 )?(?:damage )?rolls?|every (?:single )?(?:one of the 16 )?(?:damage )?rolls?|every one of the 16 (?:damage )?rolls?)\b[^.]{0,60}\b(?:ko|knock)", low):
        if not re.search(r"\bnot\b[^.]{0,12}$", low[max(0, m.start() - 14):m.start()]) and not re.search(r"\bnot\b|n't|\bnone\b", low[m.start():m.end()]):
            claims.append(ratio(16, 16, m))
    for m in re.finditer(r"\b(?:only|just)\s+(\d+)\s+(?:of them|rolls?|damage rolls?|of the 16 (?:damage )?rolls?)\s+(?:would|will|can|could)?\s*(?:ko|knock)", low):
        claims.append(ratio(int(m.group(1)), 16, m))
    for m in re.finditer(r"\bonly (?:one|1) roll\b|\bonly the (?:max|maximum|highest|top) (?:damage )?roll\b", low):
        claims.append(ratio(1, 16, m))
    for m in re.finditer(r"\b(?:none|zero|no) (?:of )?(?:the )?(?:16 )?(?:damage )?rolls?\b[^.]{0,30}\b(?:ko|knock)|0 of the 16", low):
        claims.append(ratio(0, 16, m))
    for m in re.finditer(r"rolls_that_ko\W{0,4}:?\s*(?:is\s*)?(\d+)", low):
        claims.append(ratio(int(m.group(1)), 16, m))
    for m in re.finditer(r"ko chance of (\d+(?:\.\d+)?)\b(?!\s*%)", low):
        v = float(m.group(1))
        claims.append(_ko_pct_claim(gt, 100 * v if v <= 1 else v, m))
    for m in re.finditer(rf"{NUM}\s*%\s*chance(?! to \d*hko)(?:\s*to\s*ohko)?", low):
        claims.append(_ko_pct_claim(gt, float(m.group(1)), m))
    return claims


def x_damage(it, a):
    gt = it["claims"][0]["ground_truth"]
    text = a["final_text"]
    low = text.lower()
    yn, yspan = None, first_span(text)
    m = re.match(r"\W*(yes|no)\b", low) or re.search(r"(?:answer:?\s*)?\b(yes|no)\b[,.]", low[:200])
    if m:
        yn, yspan = m.group(1) == "yes", (m.start(1), m.end(1))
    elif re.search(r"does not guarantee|doesn't guarantee|not guaranteed|no guaranteed", low):
        yn = False
    claims = [at(Claim("guaranteed_ko", _subject(gt), {None: "hedge", True: "yes", False: "no"}[yn],
                       None if yn is None else (Verdict.TRUE if yn == gt["guaranteed_ko"] else Verdict.FALSE), ctype="damage"), yspan)]
    claims += _ko_numbers(text, gt)
    for m in re.finditer(r"(?:has|have|had)\s+(\d+)\s*HP\b", text):
        claims.append(at_m(sc.score_labelled(gt, "hp", float(m.group(1))), m))
    for m in re.finditer(rf"(?:defender|defender's|its)?\s*(?:full\s*)?HP (?:of|is|:)\s*{NUM}|{NUM}\s*HP\s*\(", text, re.I):
        v = m.group(1) or m.group(2)
        if float(v) >= 100:
            claims.append(at_m(sc.score_labelled(gt, "hp", float(v)), m))
    for m in re.finditer(rf"out of {NUM}\s*total HP", text, re.I):
        claims.append(at_m(sc.score_labelled(gt, "hp", float(m.group(1))), m))
    for m in re.finditer(rf"(?:needs?|requires?|would need|would require|at least)[^.\d]{{0,30}}?{NUM}\s*(?:or more\s*)?(?:damage|HP)?", low):
        if re.search(r"\b(?:ko|knock)", low[max(0, m.start() - 80):m.end() + 60]) and not re.match(r"\s*(?:hit|hko)", low[m.end(1):m.end(1) + 6]):
            claims.append(at_m(sc.score_ko_needed(gt, float(m.group(1))), m))
    for m in re.finditer(rf"{NUM}\s*(?:or|and)\s*(?:higher|more|above|greater)", low):
        if re.search(r"\b(?:ko|knock)", low[max(0, m.start() - 80):m.end() + 60]):
            claims.append(at_m(sc.score_ko_threshold(gt, float(m.group(1))), m))
    for m in re.finditer(rf"half of {NUM}\s*(?:HP)?", low):
        claims.append(at_m(sc.score_ko_needed(gt, float(m.group(1)) / 2), m))
    for m in re.finditer(rf"(maximum|max|highest|minimum|min|lowest)\s*(?:damage|roll)?\s*(?:roll\s*)?\(?\s*{NUM}\)?\s*(?:is|are)?\s*(less|lower|greater|higher|more|above|below|exceeds?)(?: than)?\s*(?:the\s*)?(?:defender.s\s*)?(?:full\s*)?(?:HP\s*)?\(?{NUM}", text, re.I):
        lab = "max_roll" if m.group(1).lower() in ("maximum", "max", "highest") else "min_roll"
        op = "<" if m.group(3).lower() in ("less", "lower", "below") else ">"
        claims.append(at_m(sc.score_hp_arithmetic(gt, (lab, float(m.group(2))), op, ("hp", float(m.group(4)))), m))
    for m in re.finditer(rf"(?:deals?|damage range (?:is|of)?|range (?:is|of))\s*{NUM}\s*(?:-|to)\s*{NUM}(?!\s*%)", text, re.I):
        claims.append(at_m(sc.score_damage_range(gt, float(m.group(1)), float(m.group(2))), m))
    for m in re.finditer(rf"rolls?\s*\(\s*(?:(?:ranging |ranges )?from\s*)?{NUM}\s*(?:-|to)\s*{NUM}\s*\)|rolls?\s*\((?:ranging|from)\s*{NUM}\s*to\s*{NUM}", text, re.I):
        v = [g for g in m.groups() if g]
        claims.append(at_m(sc.score_damage_range(gt, float(v[0]), float(v[1])), m))
    for m in re.finditer(rf"{NUM}\s*%?\s*(?:-|to|and)\s*{NUM}\s*%", text):
        if re.search(r"hp|health", text[m.end():m.end() + 40], re.I) or re.search(r"which is|corresponds|between|deals|\(\s*$", text[max(0, m.start() - 40):m.start()], re.I):
            claims.append(at_m(sc.score_percent_of_hp(gt, float(m.group(1)), float(m.group(2))), m))
    for m in re.finditer(r"(guaranteed|possible)\s*(\d+)\s*-?\s*hko", low):
        claims.append(at_m(sc.score_nhko(gt, m.group(1), int(m.group(2))), m))
    for m in re.finditer(rf"{NUM}\s*%\s*chance to\s*(\d+)\s*-?\s*hko", low):
        if int(m.group(2)) > 1:
            claims.append(at_m(sc.score_chance_nhko(gt, float(m.group(1)), int(m.group(2))), m))
        else:
            claims.append(_ko_pct_claim(gt, float(m.group(1)), m))
    return sc.dedupe(claims)


# --- usage -------------------------------------------------------------------------------------

def _lines_pos(text: str) -> list[tuple[str, int]]:
    c, out, pos = clean(text), [], 0
    for line in c.split("\n"):
        out.append((line, pos))
        pos += len(line) + 1
    return out


def _sections(text: str) -> dict[str, list[tuple[str, int]]]:
    """Split a usage answer into "items" and "teammates" blocks by heading words; lines before any heading are "all"."""
    cur, out = "all", {"all": [], "items": [], "teammates": []}
    for line, off in _lines_pos(text):
        low = line.lower()
        if re.search(r"held items?|\bitems\b", low) and not re.match(r"\s*\d+\.", line):
            cur = "items"
        elif re.search(r"teammates?|partners?", low) and not re.match(r"\s*\d+\.", line):
            cur = "teammates"
        out[cur].append((line, off))
    return out


def _entry_names(lines: list[tuple[str, int]]) -> list[tuple[str, float | None, int | None, tuple[int, int]]]:
    """(name, percent, asserted rank, span) from list lines such as "1. Choice Scarf (48.9%)" or "Farigiraf (rank 1)"."""
    out = []
    for line, off in lines:
        m = re.match(rf"\s*(?:\d+\.|[-\u2022*])?\s*([A-Z][\w'\u2019\-\. ]*?[\w\)])\s*(?:\s[-\u2013:]\s|\(|:|$)", line)
        if not m or re.match(r"\s*(?:top|here|these|based|the)\b", line, re.I):
            continue
        pct = re.search(rf"{NUM}\s*%", line)
        rank = re.search(r"\brank\s*(\d+)\b", line, re.I)
        out.append((m.group(1).strip(), float(pct.group(1)) if pct else None, int(rank.group(1)) if rank else None, (off, off + len(line))))
    return out


def _source_named(text: str) -> str | None:
    low = text.lower()
    ing, sd = bool(re.search(r"in-game|in game", low)), "showdown" in low
    return "in-game" if ing and not sd else "showdown" if sd and not ing else None


def _spanned(claims: list[Claim], entries) -> list[Claim]:
    by_name = {sc.norm(n): sp for n, _, _, sp in entries}
    return [replace(c, span=by_name.get(sc.norm(c.proposition.split("=")[0].replace("_rank", "")))) if c.span is None else c for c in claims]


def x_usage(it, a):
    claims: list[Claim] = []
    gt0 = it["claims"][0]["ground_truth"]
    subj = gt0["species"]
    secs = _sections(a["final_text"])
    src = _source_named(a["final_text"])
    for kind, sec in (("common_items", "items"), ("teammates", "teammates")):
        key = gt0[kind]
        entries = _entry_names(secs[sec] or (secs["all"] if sec == "items" and not secs["teammates"] else []))
        names = [e[0] for e in entries]
        ranks = {n: r for n, _, r, _ in entries if r is not None}
        key_ranks = sc.ranks([(n, None) for n in gt0["teammates"]]) if kind == "teammates" else {}
        cs = sc.score_set(kind, subj, names, key, key_source="in-game", stated_source=src if src not in (None, "in-game") else None,
                          asserted_ranks=ranks or None, key_ranks=key_ranks or None)
        claims += _spanned([replace(c, ctype="usage") for c in cs], entries)
        pcts = {n: p for n, p, _, _ in entries if p is not None}
        if pcts:
            claims += _spanned(sc.score_usage_pct(kind, subj, pcts, a.get("tool_calls") or []), entries)
    return claims


def x_usage_showdown(it, a):
    gt = it["claims"][0]["ground_truth"]
    subj = gt["species"]
    entries = _entry_names(_lines_pos(a["final_text"]))
    src = _source_named(a["final_text"])
    cs = sc.score_set("teammates", subj, [e[0] for e in entries], gt["teammates"], key_source="showdown", stated_source=src if src not in (None, "showdown") else None,
                      asserted_ranks={n: r for n, _, r, _ in entries if r is not None} or None)
    claims = _spanned([replace(c, ctype="usage_showdown") for c in cs], entries)
    pcts = {n: p for n, p, _, _ in entries if p is not None}
    if pcts:
        claims += _spanned([replace(c, ctype="usage_showdown") for c in sc.score_usage_pct("teammates", subj, pcts, a.get("tool_calls") or [])], entries)
    return claims


EXTRACT = {"typing": x_typing, "ability": x_ability, "ability_form": x_ability, "item": x_item, "legality": x_legality, "speed": x_speed,
           "damage": x_damage, "usage": x_usage, "usage_showdown": x_usage_showdown, "move_static": x_move_static}


def extract_item(item: dict[str, Any], answer: dict[str, Any]) -> list[Claim]:
    claims = EXTRACT[item["claim_type"]](item, answer)
    return flag(claims, answer)
