from __future__ import annotations

import json
import textwrap

from core.session_state import SELF_HEALING_ACTIONS
from services.openai_client import extract_openai_output_text
from services.usage_logging import log_usage_event


def request_self_healing_analysis_with_openai(
    issue_text: str,
    *,
    api_key: str,
    model: str,
    recent_issues: list[dict[str, object]],
    persistent_guidance: str = "",
) -> dict[str, object]:
    """Analyze an error or improvement idea and return safe maintenance guidance."""
    from openai import OpenAI

    action_names = list(SELF_HEALING_ACTIONS)
    response_schema = {
        "type": "object",
        "properties": {
            "assistant_message": {"type": "string"},
            "recommended_actions": {
                "type": "array",
                "items": {"type": "string", "enum": action_names},
            },
            "reusable_instruction": {"type": "string"},
            "maintenance_title": {"type": "string"},
        },
        "required": [
            "assistant_message",
            "recommended_actions",
            "reusable_instruction",
            "maintenance_title",
        ],
        "additionalProperties": False,
    }

    instructions = textwrap.dedent(
        """
        You are an app maintenance assistant for a Streamlit reporting system.

        Rules:
        - Diagnose the user's error or requested improvement succinctly.
        - Recommend only safe recovery actions from the allowed list.
        - If the user expresses a stable preference or reusable behavior, extract it into reusable_instruction.
        - If the issue sounds like a longer-term app improvement, suggest a short maintenance_title.
        - Do not claim that source code was changed automatically.
        """
    ).strip()
    if persistent_guidance:
        instructions = f"{instructions}\n\nSaved app preferences:\n{persistent_guidance}"

    try:
        response = OpenAI(api_key=api_key).responses.create(
            model=model,
            instructions=instructions,
            input=textwrap.dedent(
                f"""
                Recent runtime issues:
                {json.dumps(recent_issues[:10], ensure_ascii=True, indent=2)}

                User issue or improvement request:
                {issue_text.strip()}
                """
            ).strip(),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "self_healing_analysis",
                    "strict": True,
                    "schema": response_schema,
                }
            },
            store=False,
        )
        payload_text = extract_openai_output_text(response)
        if not payload_text:
            raise ValueError("OpenAI returned an empty self-healing analysis.")
        payload = json.loads(payload_text)
        if not isinstance(payload, dict):
            raise ValueError("OpenAI returned an invalid self-healing analysis.")
    except Exception as exc:
        log_usage_event(
            feature_name="self_healing",
            model=model,
            has_files=False,
            has_images=False,
            status="failed",
            error_summary=str(exc),
        )
        raise

    log_usage_event(
        feature_name="self_healing",
        model=model,
        has_files=False,
        has_images=False,
        status="success",
    )
    return payload

