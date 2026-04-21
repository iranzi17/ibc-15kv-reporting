from __future__ import annotations

import os

import streamlit as st

from core.session_state import (
    AI_PROVIDER_SESSION_KEY,
    OPENAI_API_KEY_SESSION_KEY,
    OPENAI_CHAT_MESSAGES_KEY,
    OPENAI_MODEL_SESSION_KEY,
    OPENAI_PREVIOUS_RESPONSE_ID_KEY,
    OPENROUTER_API_KEY_SESSION_KEY,
    OPENROUTER_MODEL_SESSION_KEY,
)
from services.usage_logging import log_usage_event

PROVIDER_OPENROUTER = "openrouter"
PROVIDER_OPENAI = "openai"
SUPPORTED_AI_PROVIDERS = (PROVIDER_OPENROUTER, PROVIDER_OPENAI)
DEFAULT_AI_PROVIDER = PROVIDER_OPENROUTER
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_APP_TITLE = "IBC 15kV Reporting Platform"

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
RESEARCH_OPENAI_MODEL = "gpt-5.4-mini"
TRANSCRIPTION_OPENAI_MODEL = "gpt-4o-transcribe"
TTS_OPENAI_MODEL = "gpt-4o-mini-tts"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"
RESEARCH_OPENROUTER_MODEL = "openai/gpt-4o-mini"
TRANSCRIPTION_OPENROUTER_MODEL = "openai/gpt-audio-mini"

OPENAI_ONLY_RESPONSES_FEATURE_MESSAGE = (
    "This feature still uses OpenAI Responses tools. Switch the AI provider to OpenAI for this workflow."
)


def streamlit_secret(name: str, default: str = "") -> str:
    """Return one Streamlit secret value when available."""
    try:
        return str(st.secrets.get(name, default) or "").strip()
    except Exception:
        return str(default or "").strip()


def normalize_ai_provider(provider: str | None) -> str:
    """Return a supported AI provider id."""
    value = str(provider or "").strip().lower()
    if value in SUPPORTED_AI_PROVIDERS:
        return value
    return DEFAULT_AI_PROVIDER


def provider_label(provider: str | None = None) -> str:
    """Return a display label for an AI provider."""
    normalized = normalize_ai_provider(provider or active_ai_provider())
    return "OpenRouter" if normalized == PROVIDER_OPENROUTER else "OpenAI"


def _configured_provider_key(provider: str) -> str:
    if provider == PROVIDER_OPENROUTER:
        return load_openrouter_api_key()
    return load_openai_api_key()


def active_ai_provider() -> str:
    """Return the selected app-wide AI provider."""
    session_provider = str(st.session_state.get(AI_PROVIDER_SESSION_KEY, "") or "").strip()
    if session_provider:
        return normalize_ai_provider(session_provider)

    for env_name in ("AI_PROVIDER", "LLM_PROVIDER"):
        env_provider = os.environ.get(env_name, "").strip()
        if env_provider:
            return normalize_ai_provider(env_provider)

    secret_provider = streamlit_secret("AI_PROVIDER") or streamlit_secret("LLM_PROVIDER")
    if secret_provider:
        return normalize_ai_provider(secret_provider)

    if load_openrouter_api_key():
        return PROVIDER_OPENROUTER
    if load_openai_api_key():
        return PROVIDER_OPENAI
    return DEFAULT_AI_PROVIDER


def load_openai_api_key() -> str:
    """Load the OpenAI key from session state, env, or Streamlit secrets."""
    session_key = str(st.session_state.get(OPENAI_API_KEY_SESSION_KEY, "") or "").strip()
    if session_key:
        return session_key

    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key

    return streamlit_secret("OPENAI_API_KEY")


def load_openrouter_api_key() -> str:
    """Load the OpenRouter key from session state, env, or Streamlit secrets."""
    session_key = str(st.session_state.get(OPENROUTER_API_KEY_SESSION_KEY, "") or "").strip()
    if session_key:
        return session_key

    env_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if env_key:
        return env_key

    return streamlit_secret("OPENROUTER_API_KEY")


def load_ai_api_key(provider: str | None = None) -> str:
    """Load the API key for the active or requested provider."""
    return _configured_provider_key(normalize_ai_provider(provider or active_ai_provider()))


def ai_api_key_source(provider: str | None = None) -> str:
    """Return a human-readable source for the configured API key."""
    normalized = normalize_ai_provider(provider or active_ai_provider())
    if normalized == PROVIDER_OPENROUTER:
        if st.session_state.get(OPENROUTER_API_KEY_SESSION_KEY):
            return "session input"
        if os.environ.get("OPENROUTER_API_KEY", "").strip():
            return "environment variable"
        if streamlit_secret("OPENROUTER_API_KEY"):
            return "Streamlit secrets"
        return "not configured"

    if st.session_state.get(OPENAI_API_KEY_SESSION_KEY):
        return "session input"
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return "environment variable"
    if streamlit_secret("OPENAI_API_KEY"):
        return "Streamlit secrets"
    return "not configured"


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


def default_openrouter_model() -> str:
    """Return the configured default OpenRouter model."""
    session_model = str(st.session_state.get(OPENROUTER_MODEL_SESSION_KEY, "") or "").strip()
    if session_model:
        return session_model

    env_model = os.environ.get("OPENROUTER_MODEL", "").strip()
    if env_model:
        return env_model

    secret_model = streamlit_secret("OPENROUTER_MODEL")
    if secret_model:
        return secret_model

    return DEFAULT_OPENROUTER_MODEL


def default_ai_model(provider: str | None = None) -> str:
    """Return the default model for the active or requested provider."""
    normalized = normalize_ai_provider(provider or active_ai_provider())
    if normalized == PROVIDER_OPENROUTER:
        return default_openrouter_model()
    return default_openai_model()


def default_transcription_model(provider: str | None = None) -> str:
    """Return the transcription-capable model for the active or requested provider."""
    normalized = normalize_ai_provider(provider or active_ai_provider())
    if normalized == PROVIDER_OPENROUTER:
        return TRANSCRIPTION_OPENROUTER_MODEL
    return TRANSCRIPTION_OPENAI_MODEL


def openai_sdk_ready() -> tuple[bool, str]:
    """Check whether the OpenAI SDK can be imported."""
    try:
        from openai import OpenAI  # noqa: F401
    except ImportError as exc:
        return False, str(exc)
    return True, ""


def make_ai_client(*, api_key: str, provider: str | None = None):
    """Create an OpenAI SDK client for OpenAI or OpenRouter."""
    from openai import OpenAI

    normalized = normalize_ai_provider(provider or active_ai_provider())
    if normalized == PROVIDER_OPENROUTER:
        return OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "").strip() or "https://github.com/iranzi17/ibc-15kv-reporting",
                "X-Title": os.environ.get("OPENROUTER_APP_TITLE", "").strip() or OPENROUTER_APP_TITLE,
            },
        )
    return OpenAI(api_key=api_key)


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


def extract_chat_completion_text(response) -> str:
    """Read assistant text from a Chat Completions response."""
    choices = getattr(response, "choices", []) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    if message is None:
        return ""
    content = getattr(message, "content", "") or ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        fragments: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = str(item.get("text", "") or "").strip()
            else:
                text = str(getattr(item, "text", "") or "").strip()
            if text:
                fragments.append(text)
        return "\n".join(fragments).strip()
    return str(content or "").strip()


def request_openai_reply(
    prompt: str,
    *,
    api_key: str,
    model: str,
    provider: str | None = PROVIDER_OPENAI,
) -> tuple[str, str]:
    """Send one general assistant turn and return (reply_text, response_id)."""
    normalized_provider = normalize_ai_provider(provider)
    client = make_ai_client(api_key=api_key, provider=normalized_provider)

    if normalized_provider == PROVIDER_OPENROUTER:
        session_messages = st.session_state.get(OPENAI_CHAT_MESSAGES_KEY, [])
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "You are a concise reporting assistant for a construction supervision platform."}
        ]
        if isinstance(session_messages, list):
            for message in session_messages[-12:]:
                if not isinstance(message, dict):
                    continue
                role = str(message.get("role", "") or "").strip()
                content = str(message.get("content", "") or "").strip()
                if role in {"user", "assistant", "system"} and content:
                    messages.append({"role": role, "content": content})
        if len(messages) == 1:
            messages.append({"role": "user", "content": prompt})

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
            )
            reply_text = extract_chat_completion_text(response) or "No text response was returned."
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
        return reply_text, ""

    previous_response_id = st.session_state.get(OPENAI_PREVIOUS_RESPONSE_ID_KEY)
    request_kwargs = {
        "model": model,
        "input": [{"role": "user", "content": prompt}],
    }
    if previous_response_id:
        request_kwargs["previous_response_id"] = previous_response_id

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
    provider: str | None = PROVIDER_OPENAI,
    allow_web_research: bool = False,
    allow_file_search: bool = False,
    allow_code_interpreter: bool = False,
) -> str:
    """Return a tool-capable model when one is required."""
    if normalize_ai_provider(provider) == PROVIDER_OPENROUTER:
        return model or RESEARCH_OPENROUTER_MODEL
    if not any((allow_web_research, allow_file_search, allow_code_interpreter)):
        return model
    if str(model or "").startswith("gpt-5"):
        return model
    return RESEARCH_OPENAI_MODEL


def converter_model(
    model: str,
    *,
    provider: str | None = PROVIDER_OPENAI,
    allow_web_research: bool,
    allow_file_search: bool = False,
) -> str:
    """Return the most suitable model for contractor converter flows."""
    return tool_enabled_model(
        model,
        provider=provider,
        allow_web_research=allow_web_research,
        allow_file_search=allow_file_search,
    )


def provider_supports_openai_responses_tools(provider: str | None = None) -> bool:
    """Return whether OpenAI Responses tools are available for the provider."""
    return normalize_ai_provider(provider or active_ai_provider()) == PROVIDER_OPENAI

