"""A6: parser agreement on seven classes — dev labels only (not the 118 graded turns).

Live LLM required. Skip when Ollama/model unavailable.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
LABELS = HERE / "dev_guard_parser_labels.json"


def _llm_or_skip():
    pytest.importorskip("langchain_ollama")
    from langchain_ollama import ChatOllama
    from scripts.eval.part_g_arm.config import ArmConfig

    cfg = ArmConfig()
    try:
        llm = ChatOllama(
            model=cfg.model,
            temperature=0,
            reasoning=False,
            num_ctx=cfg.num_ctx,
            num_predict=256,
            client_kwargs={"timeout": 90.0},
        )
        # Cheap ping
        llm.invoke("ping")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"ollama unavailable: {exc}")
    return llm


def _start(kind: str):
    from scripts.eval.part_g_arm.state.fixtures import empty_team
    from scripts.eval.part_g_arm.state.guard_allowed import stamp_pending_team_fingerprint
    from scripts.eval.part_g_arm.state.seeds import builders

    if kind == "cs_pending":
        st = builders.build_cs_pending_seed()
        stamp_pending_team_fingerprint(st)
        return st
    return empty_team()


def test_a6_parser_confusion_matrix_dev_rows():
    llm = _llm_or_skip()
    from scripts.eval.part_g_arm.state.guard_parser import parse_user_turn, parser_prompt_sha256

    rows = json.loads(LABELS.read_text(encoding="utf-8"))["rows"]
    classes = [
        "LOOKUP",
        "WRITE",
        "ASK",
        "HYPOTHETICAL",
        "READ_STATE",
        "PENDING_ANSWER",
        "READ_ONLY_REFUSE",
    ]
    matrix = {g: Counter() for g in classes}
    split_errors = 0
    preds: list[tuple[str, str, str]] = []
    for row in rows:
        state = _start(row.get("start") or "empty")
        pending = row.get("pending_asked")
        rec = parse_user_turn(llm, row["text"], state, pending_asked=pending)
        subs = rec.get("sub_requests") or []
        if len(subs) != 1 and row["class"] not in ("WRITE", "LOOKUP"):
            # Count multi-split on a single-request label as a split error.
            if len(subs) > 1:
                split_errors += 1
        pred = str((subs[0] if subs else {}).get("class") or "ASK").upper()
        gold = row["class"]
        if gold not in matrix:
            matrix[gold] = Counter()
        matrix[gold][pred] += 1
        preds.append((row["id"], gold, pred))
    print("parser_prompt_sha256=", parser_prompt_sha256())
    print("predictions=", preds)
    print("split_errors=", split_errors)
    print("confusion=")
    for g in classes:
        print(f"  gold={g}: {dict(matrix[g])}")
    agree = sum(1 for _, g, p in preds if g == p)
    print(f"agreement={agree}/{len(preds)}")
    # Soft floor for smoke: at least half correct on this tiny set; report full matrix.
    assert agree >= max(1, len(preds) // 2)
