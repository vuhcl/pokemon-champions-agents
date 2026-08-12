"""Env-driven bootstrap parser resolution (no live network)."""

from __future__ import annotations

from recommender.llm_provider import resolve_bootstrap_parser, resolve_llm_parsers


def test_provider_none_warns(monkeypatch):
    monkeypatch.delenv("POKEMON_CHAMPIONS_LLM_PROVIDER", raising=False)
    parser, warning = resolve_bootstrap_parser("none")
    assert parser is None
    assert warning is not None
    assert "provider=none" in warning
    assert "BOOTSTRAP_OLLAMA_MODEL" in warning or "--provider ollama" in warning
    assert "--provider anthropic" in warning


def test_resolve_llm_parsers_none_disables_both(monkeypatch):
    monkeypatch.delenv("POKEMON_CHAMPIONS_LLM_PROVIDER", raising=False)
    boot, turn, warning = resolve_llm_parsers("none")
    assert boot is None
    assert turn is None
    assert warning is not None


def test_ollama_missing_model_warns(monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_OLLAMA_MODEL", raising=False)
    parser, warning = resolve_bootstrap_parser("ollama")
    assert parser is None
    assert warning is not None
    assert "BOOTSTRAP_OLLAMA_MODEL" is not None and "BOOTSTRAP_OLLAMA_MODEL" in warning
    assert "--provider ollama" in warning
    assert "No LLM provider is configured" in warning


def test_resolve_llm_parsers_ollama_missing_model_disables_both(monkeypatch):
    monkeypatch.delenv("BOOTSTRAP_OLLAMA_MODEL", raising=False)
    boot, turn, warning = resolve_llm_parsers("ollama")
    assert boot is None
    assert turn is None
    assert warning is not None
    assert "BOOTSTRAP_OLLAMA_MODEL" in warning


def test_anthropic_missing_model_warns(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("BOOTSTRAP_ANTHROPIC_MODEL", raising=False)
    parser, warning = resolve_bootstrap_parser("anthropic")
    assert parser is None
    assert warning is not None
    assert "BOOTSTRAP_ANTHROPIC_MODEL" in warning


def test_anthropic_missing_key_warns(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("BOOTSTRAP_ANTHROPIC_MODEL", "claude-test")
    parser, warning = resolve_bootstrap_parser("anthropic")
    assert parser is None
    assert warning is not None
    assert "ANTHROPIC_API_KEY" in warning


def test_unknown_provider_warns():
    parser, warning = resolve_bootstrap_parser("nope")
    assert parser is None
    assert warning is not None
    assert "Unknown" in warning


def test_resolve_llm_parsers_builds_both_when_factories_ok(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_OLLAMA_MODEL", "test-model")
    fake_boot = object()
    fake_turn = object()
    monkeypatch.setattr(
        "recommender.bootstrap.build_ollama_bootstrap_intake_parser",
        lambda model: fake_boot,
    )
    monkeypatch.setattr(
        "recommender.turn_intent.build_ollama_turn_intent_parser",
        lambda model: fake_turn,
    )
    boot, turn, warning = resolve_llm_parsers("ollama")
    assert boot is fake_boot
    assert turn is fake_turn
    assert warning is None
    wrapper_boot, wrapper_warn = resolve_bootstrap_parser("ollama")
    assert wrapper_boot is fake_boot
    assert wrapper_warn is None
