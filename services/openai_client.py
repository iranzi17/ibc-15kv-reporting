from __future__ import annotations

import os

import streamlit as st

from core.session_state import (
    OPENAI_API_KEY_SESSION_KEY,
    OPENAI_MODEL_SESSION_KEY,
    OPENAI_PREVIOUS_RESPONSE_ID_KEY,
)
from services.usage_logging import log_usage_event

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
RESEARCH_OPENAI_MODEL = "gpt-5.4-mini"
TRANSCRIPTION_OPENAI_MODEL = "gpt-4o-transcribe"
TTS_OPENAI_MODEL = "gpt-4o-mini-tts"


def streamlit_secret(name: str, default: str = "") -> str:
    """Return one Streamlit secret value when available."""
    try:
        return str(st.secrets.get(name, default) or "").strip()
    except Exception:
        return str(default or "").strip()


def load_openai_api_key() -> str:
    """Load the OpenAI key from session state, env, or Streamlit secrets."""
    session_key = str(st.session_state.get(OPENAI_API_KEY_SESSION_KEY, "") or "").strip()
    if session_key:
        return session_key

    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key

    return streamlit_secret("OPENAI_API_KEY")


def default_openai_model() -> str:
    """Return the configured default OpenAI model."""
    session_model = str(st.session_state.get(OPENAI_MODEL_SESSION_KEY, "") or "").strip()
    if session_model:
        return session_model

    env_model = os.environ.get("OPENAI_MODEL", "").strip()
    if env_model:
        return env_model

    secret_model = streamlit_secret("OPENAI_MODEL")
    if secret_model:
        return secret_model

    return DEFAULT_OPENAI_MODEL


def openai_sdk_ready() -> tuple[bool, str]:
    """Check whether the OpenAI SDK can be imported."""
    try:
        from openai import OpenAI  # noqa: F401
    except ImportError as exc:
        return False, str(exc)
    return True, ""


def extract_openai_output_text(response) -> str:
    """Read the text output from an OpenAI Responses API object."""
    text = str(getattr(response, "output_text", "") or "").strip()
    if text:
        return text

    fragments: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            content_text = str(getattr(content, "text", "") or "").strip()
            if content_text:
                fragments.append(content_text)
    return "\n".join(fragments).strip()


def request_openai_reply(prompt: str, *, api_key: str, model: str) -> tuple[str, str]:
    """Send one general assistant turn to OpenAI and return (reply_text, response_id)."""
    from openai import OpenAI

    previous_response_id = st.session_state.get(OPENAI_PREVIOUS_RESPONSE_ID_KEY)
    request_kwargs = {
        "model": model,
        "input": [{"role": "user", "content": prompt}],
    }
    if previous_response_id:
        request_kwargs["previous_response_id"] = previous_response_id

    client = OpenAI(api_key=api_key)
    try:
        response = client.responses.create(**request_kwargs)
        reply_text = extract_openai_output_text(response) or "No text response was returned."
    except Exception as exc:
        log_usage_event(
            feature_name="general_chat",
            model=model,
            has_files=False,
            has_images=False,
            status="failed",
            error_summary=str(exc),
        )
        raise

    log_usage_event(
        feature_name="general_chat",
        model=model,
        has_files=False,
        has_images=False,
        status="success",
    )
    return reply_text, str(getattr(response, "id", "") or "")


def tool_enabled_model(
    model: str,
    *,
    allow_web_research: bool = False,
    allow_file_search: bool = False,
    allow_code_interpreter: bool = False,
) -> str:
    """Return a tool-capable model when one is required."""
    if not any((allow_web_research, allow_file_search, allow_code_interpreter)):
        return model
    if str(model or "").startswith("gpt-5"):
        return model
    return RESEARCH_OPENAI_MODEL


def converter_model(
    model: str,
    *,
    allow_web_research: bool,
    allow_file_search: bool = False,
) -> str:
    """Return the most suitable model for contractor converter flows."""
    return tool_enabled_model(
        model,
        allow_web_research=allow_web_research,
        allow_file_search=allow_file_search,
    )

