"""Non-gating judge: Ollama /api/chat with a JSON schema, temperature 0, thinking off. The judge reads only the question prompt and the
arm's final_text, never tool results or keys. Not part of the gate: the pass bar is set elsewhere and a failure drops the judge."""
from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLLAMA = "http://127.0.0.1:11434"
MODEL = "gemma4:12b"
PINNED_DIGEST = "c7597fc90b86aff6965317f37dd5465402284e26382d9b4bf2dfe3ef1491f4b6"  # `ollama show`/api/tags digest; the list ID is c7597fc90b86
PROMPT_PATH = HERE / "extract_prompt.md"
SAMPLER = {"temperature": 0, "num_ctx": 8192, "num_predict": 2000}  # top_k, top_p and the rest are the model's own defaults
SCHEMA = {
    "type": "object",
    "properties": {"claims": {"type": "array", "items": {
        "type": "object",
        "properties": {"subject": {"type": "string"}, "predicate": {"type": "string"}, "value": {"type": "string"},
                       "polarity": {"type": "string", "enum": ["T", "F"]}},
        "required": ["subject", "predicate", "value", "polarity"], "additionalProperties": False}}},
    "required": ["claims"], "additionalProperties": False,
}


def prompt_text() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def prompt_sha256() -> str:
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()


def _call(path: str, body: dict | None = None, timeout: float = 300) -> dict:
    req = urllib.request.Request(OLLAMA + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def loaded_models() -> list[str]:
    return [m["name"] for m in _call("/api/ps").get("models", [])]


def local_digest() -> str | None:
    return next((m["digest"] for m in _call("/api/tags")["models"] if m["name"] == MODEL), None)


def build_request(question: str, final_text: str, keep_alive: str | int = "5m") -> dict:
    """The whole request. The user message holds the question and the answer text and nothing else."""
    user = f"Question:\n{question}\n\nAnswer:\n{final_text}"
    return {"model": MODEL, "stream": False, "think": False, "format": SCHEMA, "options": SAMPLER, "keep_alive": keep_alive,
            "messages": [{"role": "system", "content": prompt_text()}, {"role": "user", "content": user}]}


def extract(question: str, final_text: str, keep_alive: str | int = "5m") -> dict:
    """-> {"claims": [...], "raw": str, "parsed": bool}; parsed is False when the JSON does not parse or fits the schema badly (no repair)."""
    raw = _call("/api/chat", build_request(question, final_text, keep_alive))["message"]["content"]
    try:
        doc = json.loads(raw)
        ok = isinstance(doc.get("claims"), list) and all(set(c) == {"subject", "predicate", "value", "polarity"} and c["polarity"] in ("T", "F") for c in doc["claims"])
    except (json.JSONDecodeError, AttributeError, TypeError):
        return {"claims": [], "raw": raw, "parsed": False}
    return {"claims": doc["claims"] if ok else [], "raw": raw, "parsed": ok}
