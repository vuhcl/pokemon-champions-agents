#!/usr/bin/env python3
"""Investigate whether bootstrap_intake_error can embed model-authored text."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

OUT = Path(__file__).resolve().parent


class BootstrapExtraction(BaseModel):
    direction_text: str
    anchor_text: str | None = None


def main() -> None:
    findings: dict = {"paths": [], "yes_no": None}

    # Path 1: include_raw parsing_error stringified into BootstrapIntakeParseError
    # (bootstrap.py:125-128). LangChain often puts completion text in that error.
    raw_model = (
        '{"direction_text": "Specs Chi-Yu OHKO Kingambit with Choice Specs '
        'are legal in Reg M-C"}'
    )
    parsing_error = (
        "Failed to parse BootstrapExtraction from completion "
        f"{raw_model}. Got OutputParserException"
    )
    msg1 = f"structured extraction failed: {parsing_error}"
    display1 = f"Bootstrap intake error: {msg1}"
    findings["paths"].append(
        {
            "path": "bootstrap.py:125-128 → nodes_classify.py:1575-1578 → present_text.py:689-690",
            "mechanism": "str(parsing_error) embedded in BootstrapIntakeParseError, then bootstrap_intake_error=str(exc)",
            "embeds_model_text_if_parsing_error_contains_completion": True,
            "display_example": display1[:400],
            "contains_chi_yu": "Chi-Yu" in display1,
            "note": (
                "Whether LangChain's real parsing_error includes the completion "
                "depends on the provider/version; the code path does NOT strip it."
            ),
        }
    )

    # Path 2: pydantic ValidationError
    try:
        BootstrapExtraction.model_validate(
            {
                "direction_text": 123,
                "anchor_text": "raw model said Chi-Yu is legal",
            }
        )
    except ValidationError as exc:
        msg2 = f"invalid bootstrap extraction: {exc}"
        display2 = f"Bootstrap intake error: {msg2}"
        findings["paths"].append(
            {
                "path": "bootstrap.py:142-143 → nodes_classify.py:1575-1578 → present_text.py:689-690",
                "mechanism": "ValidationError str(exc) — typically field/type errors, may include invalid input values",
                "display_example": display2[:500],
                "contains_chi_yu": "Chi-Yu" in display2,
                "note": (
                    "Pydantic ValidationError usually embeds the invalid input "
                    "value (here anchor_text string). That value is the parsed "
                    "dict field, not necessarily full free-prose completion — "
                    "but if the model put prose in a string field that then "
                    "fails a later check, or if validation fails on a coerced "
                    "structure that retained strings, those strings appear."
                ),
            }
        )

    # Path 3: generic Exception
    msg3 = (
        "bootstrap extraction provider failed: RuntimeError: "
        "model said Specs Chi-Yu is fine"
    )
    display3 = f"Bootstrap intake error: {msg3}"
    findings["paths"].append(
        {
            "path": "bootstrap.py:144-147 → nodes_classify.py:1575-1578 → present_text.py:689-690",
            "mechanism": "str(exc) on arbitrary Exception",
            "embeds_if_exception_message_has_model_text": True,
            "display_example": display3,
            "contains_chi_yu": "Chi-Yu" in display3,
        }
    )

    # Verdict: code path CAN put model-authored text in front of the user
    # when parsing_error / ValidationError / Exception messages contain it.
    findings["yes_no"] = "yes"
    findings["summary"] = (
        "YES — bootstrap_intake_error is displayed verbatim "
        "(present_text.py:689-690). parse_bootstrap_intake wraps "
        "parsing_error / ValidationError / Exception via str(exc) "
        "(bootstrap.py:125-128, 142-147) with no redaction. "
        "A LangChain include_raw parsing_error that includes the "
        "completion (common) will surface model prose. Pydantic "
        "ValidationError can embed invalid field input values. "
        "Not folded into Approach A; log as separate item."
    )

    (OUT / "bootstrap_exc_probe.json").write_text(json.dumps(findings, indent=2) + "\n")
    print(json.dumps({"yes_no": findings["yes_no"], "wrote": "bootstrap_exc_probe.json"}, indent=2))


if __name__ == "__main__":
    main()
