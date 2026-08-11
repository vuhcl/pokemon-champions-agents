"""Resolve the bootstrap intake LLM parser from env / CLI flags."""

from __future__ import annotations

import os
from typing import Any

from recommender.present_text import BOOTSTRAP_PARSER_FIX_HINT

_ENV_PROVIDER = "POKEMON_CHAMPIONS_LLM_PROVIDER"
_ENV_OLLAMA_MODEL = "BOOTSTRAP_OLLAMA_MODEL"
_ENV_ANTHROPIC_MODEL = "BOOTSTRAP_ANTHROPIC_MODEL"


def _warn(detail: str) -> str:
    return f"{detail} {BOOTSTRAP_PARSER_FIX_HINT}"


def resolve_bootstrap_parser(
    provider: str | None = None,
) -> tuple[Any | None, str | None]:
    """Return ``(parser_or_none, startup_warning_or_none)``.

    ``provider`` overrides ``POKEMON_CHAMPIONS_LLM_PROVIDER`` (default ``ollama``).
    """

    name = (provider or os.environ.get(_ENV_PROVIDER) or "ollama").strip().casefold()
    if name == "none":
        return None, _warn(
            "Bootstrap intake parser disabled (provider=none);"
        )
    if name == "ollama":
        model = os.environ.get(_ENV_OLLAMA_MODEL)
        if not model:
            return None, _warn(f"{_ENV_OLLAMA_MODEL} is unset;")
        try:
            from recommender.bootstrap import build_ollama_bootstrap_intake_parser
        except ImportError as exc:
            return None, _warn(f"langchain-ollama unavailable: {exc}.")
        try:
            return build_ollama_bootstrap_intake_parser(model), None
        except ImportError as exc:
            return None, _warn(f"langchain-ollama unavailable: {exc}.")
        except Exception as exc:
            return None, _warn(f"failed to build Ollama bootstrap parser: {exc}.")
    if name == "anthropic":
        model = os.environ.get(_ENV_ANTHROPIC_MODEL)
        if not model:
            return None, _warn(f"{_ENV_ANTHROPIC_MODEL} is unset;")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None, _warn("ANTHROPIC_API_KEY is unset;")
        try:
            from recommender.bootstrap import build_anthropic_bootstrap_intake_parser
        except ImportError as exc:
            return None, _warn(f"langchain-anthropic unavailable: {exc}.")
        try:
            return build_anthropic_bootstrap_intake_parser(model), None
        except ImportError as exc:
            return None, _warn(f"langchain-anthropic unavailable: {exc}.")
        except Exception as exc:
            return None, _warn(f"failed to build Anthropic bootstrap parser: {exc}.")
    return None, _warn(
        f"Unknown POKEMON_CHAMPIONS_LLM_PROVIDER={name!r}; "
        "expected ollama, anthropic, or none."
    )
