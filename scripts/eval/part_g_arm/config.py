"""One config object for the Part G arm: everything that can change a run, so run_params can record it."""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = HERE / "system_prompt.md"
# Pinned by digest: the run refuses to start if the local model's digest differs.
QWEN_DIGEST = "44a38603922e14f1e3ae68c5d900cc39f2a925a9749d12ab6d268d75a01a399f"


@dataclasses.dataclass(frozen=True)
class ArmConfig:
    model: str = "qwen3.5:latest"
    model_digest: str = QWEN_DIGEST
    temperature: float = 0.0
    think: bool = False  # explicit; never None (the server default is think-on)
    num_ctx: int = 16384
    num_predict: int = 2048
    max_turns: int = 8  # model invocations per item
    call_timeout_s: float = 120.0  # each model request
    item_timeout_s: float = 300.0
    run_timeout_s: float = 4 * 3600.0
    fixed_now_utc: str | None = None  # RECOMMENDER_FIXED_NOW_UTC; None = undecided (recorded as pending_at_run)
    allow_live: bool = False
    regulation: str = "champions"
    calc_base_url: str = "http://127.0.0.1:4173"

    def __post_init__(self) -> None:
        assert self.allow_live is False, "arm runs are offline (ADR-014)"
        assert isinstance(self.think, bool), "think must be explicit"

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def system_prompt_hash() -> str:
    return hashlib.sha256(SYSTEM_PROMPT_PATH.read_bytes()).hexdigest()
