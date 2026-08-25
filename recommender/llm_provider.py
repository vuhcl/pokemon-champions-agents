"""Resolve bootstrap + turn-intent LLM parsers from env / CLI flags."""

from __future__ import annotations

import os
from typing import Any

from recommender.present_text import BOOTSTRAP_PARSER_FIX_HINT

_ENV_PROVIDER = "POKEMON_CHAMPIONS_LLM_PROVIDER"
_ENV_OLLAMA_MODEL = "BOOTSTRAP_OLLAMA_MODEL"
_ENV_ANTHROPIC_MODEL = "BOOTSTRAP_ANTHROPIC_MODEL"

# Ollama's own default is 5 minutes, which forces a cold model reload on any
# gap longer than that — a real cost during normal, thinking-time-heavy CLI
# sessions, and one that could get misread as evidence of a slow/hung call
# rather than ordinary model-loading overhead. 30 minutes comfortably covers
# a real interactive session without keeping the model loaded indefinitely.
_OLLAMA_KEEP_ALIVE = "30m"


def _warn(detail: str) -> str:
    return f"{detail} {BOOTSTRAP_PARSER_FIX_HINT}"


def resolve_llm_parsers(
    provider: str | None = None,
) -> tuple[Any | None, Any | None, str | None]:
    """Return ``(bootstrap_parser, turn_intent_parser, startup_warning_or_none)``.

    ``provider`` overrides ``POKEMON_CHAMPIONS_LLM_PROVIDER`` (default ``ollama``).
    Both parsers are built from the same provider/model or both disabled together.
    """

    name = (provider or os.environ.get(_ENV_PROVIDER) or "ollama").strip().casefold()
    if name == "none":
        return None, None, _warn(
            "Bootstrap intake parser disabled (provider=none);"
        )
    if name == "ollama":
        model = os.environ.get(_ENV_OLLAMA_MODEL)
        if not model:
            return None, None, _warn(f"{_ENV_OLLAMA_MODEL} is unset;")
        try:
            from recommender.bootstrap import build_ollama_bootstrap_intake_parser
            from recommender.turn_intent import build_ollama_turn_intent_parser
        except ImportError as exc:
            return None, None, _warn(f"langchain-ollama unavailable: {exc}.")
        try:
            return (
                build_ollama_bootstrap_intake_parser(
                    model, keep_alive=_OLLAMA_KEEP_ALIVE
                ),
                build_ollama_turn_intent_parser(
                    model, keep_alive=_OLLAMA_KEEP_ALIVE
                ),
                None,
            )
        except ImportError as exc:
            return None, None, _warn(f"langchain-ollama unavailable: {exc}.")
        except Exception as exc:
            return None, None, _warn(f"failed to build Ollama parsers: {exc}.")
    if name == "anthropic":
        model = os.environ.get(_ENV_ANTHROPIC_MODEL)
        if not model:
            return None, None, _warn(f"{_ENV_ANTHROPIC_MODEL} is unset;")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None, None, _warn("ANTHROPIC_API_KEY is unset;")
        try:
            from recommender.bootstrap import build_anthropic_bootstrap_intake_parser
            from recommender.turn_intent import build_anthropic_turn_intent_parser
        except ImportError as exc:
            return None, None, _warn(f"langchain-anthropic unavailable: {exc}.")
        try:
            return (
                build_anthropic_bootstrap_intake_parser(model),
                build_anthropic_turn_intent_parser(model),
                None,
            )
        except ImportError as exc:
            return None, None, _warn(f"langchain-anthropic unavailable: {exc}.")
        except Exception as exc:
            return None, None, _warn(f"failed to build Anthropic parsers: {exc}.")
    return None, None, _warn(
        f"Unknown POKEMON_CHAMPIONS_LLM_PROVIDER={name!r}; "
        "expected ollama, anthropic, or none."
    )
