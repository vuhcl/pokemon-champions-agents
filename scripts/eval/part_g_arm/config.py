"""One config object for the Part G arm: everything that can change a run, so run_params can record it."""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
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
    prompt_file: str = "system_prompt.md"  # a file next to this module
    no_lookup_tool: bool = True  # bind no_lookup_needed (and keep the prompt's line about it)
    enforce_first_turn_tool: bool = True  # a first turn without a tool call is rejected once and re-asked

    def __post_init__(self) -> None:
        assert self.allow_live is False, "arm runs are offline (ADR-014)"
        assert isinstance(self.think, bool), "think must be explicit"
        assert self.no_lookup_tool or not self.enforce_first_turn_tool, "first-turn enforcement offers no_lookup_needed"

    def prompt_text(self) -> str:
        """The system prompt as sent: the file, minus any line about no_lookup_needed when that tool is off."""
        text = (HERE / self.prompt_file).read_text(encoding="utf-8")
        if self.no_lookup_tool:
            return text
        return "".join(line for line in text.splitlines(keepends=True) if "no_lookup_needed" not in line)

    def prompt_hash(self) -> str:
        return hashlib.sha256(self.prompt_text().encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)
