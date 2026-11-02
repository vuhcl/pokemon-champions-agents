"""Terminal fallback reply from tool results / refusals (no invented text)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def _key_fields(result: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a shallow copy of lookup-ish keys; skip huge nests."""
    if not isinstance(result, Mapping):
        return {}
    skip = {"_raw", "raw", "evidence", "annotated_candidates"}
    out: dict[str, Any] = {}
    for k, v in result.items():
        if k in skip:
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[k] = v
        elif isinstance(v, list) and len(v) <= 12:
            out[k] = v
        elif isinstance(v, dict) and len(v) <= 12:
            # one level of scalars
            out[k] = {
                ik: iv
                for ik, iv in v.items()
                if isinstance(iv, (str, int, float, bool)) or iv is None
            }
    return out


def build_fallback_reply(
    tool_calls: Sequence[Mapping[str, Any]],
    *,
    blocked_calls: Sequence[Mapping[str, Any]] | None = None,
    cap_hit: bool = False,
) -> str:
    """Deterministic reply from this turn's tool results and refusals."""
    lines: list[str] = []
    if cap_hit:
        lines.append("Turn tool-call cap reached.")
    for b in blocked_calls or ():
        name = b.get("name") or b.get("tool")
        reason = b.get("reason") or "blocked"
        lines.append(f"Refused {name}: {reason}.")
    for call in tool_calls:
        name = call.get("name")
        result = call.get("result")
        status = call.get("result_status")
        if isinstance(result, Mapping) and (
            result.get("guard_blocked") or result.get("status") == "refused"
        ):
            msg = result.get("message") or result.get("reason") or "refused"
            lines.append(f"Refused {name}: {msg}")
            continue
        if status == "refused":
            msg = ""
            if isinstance(result, Mapping):
                msg = str(result.get("message") or result.get("reason") or "")
            lines.append(f"Refused {name}: {msg}".rstrip(": "))
            continue
        fields = _key_fields(result if isinstance(result, Mapping) else None)
        if fields:
            parts = [f"{k}={fields[k]!r}" for k in sorted(fields)]
            lines.append(f"{name}: " + ", ".join(parts))
        elif name:
            lines.append(f"{name}: (no scalar fields)")
    text = "\n".join(lines).strip()
    return text or "No tool results this turn."
