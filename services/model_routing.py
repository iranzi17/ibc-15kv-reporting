from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

PROVIDER_OPENROUTER = "openrouter"
PROVIDER_OPENAI = "openai"
SUPPORTED_AI_PROVIDERS = (PROVIDER_OPENROUTER, PROVIDER_OPENAI)
DEFAULT_AI_PROVIDER = PROVIDER_OPENROUTER

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
RESEARCH_OPENAI_MODEL = "gpt-5.4-mini"
TRANSCRIPTION_OPENAI_MODEL = "gpt-4o-transcribe"
TTS_OPENAI_MODEL = "gpt-4o-mini-tts"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"
RESEARCH_OPENROUTER_MODEL = "openai/gpt-4o-mini"
FALLBACK_OPENROUTER_MODEL = "openai/gpt-4o"
TRANSCRIPTION_OPENROUTER_MODEL = "openai/gpt-audio-mini"

PROFILE_CONVERSION_STRICT = "conversion_strict"
PROFILE_REFINEMENT_STRICT = "refinement_strict"
PROFILE_CAPTIONING_VISION = "captioning_vision"
PROFILE_GENERAL_CHAT_ECONOMY = "general_chat_economy"
PROFILE_RESEARCH_TOOLING = "research_tooling"
PROFILE_TRANSCRIPTION_AUDIO = "transcription_audio"


@dataclass(frozen=True)
class RoutingProfile:
    """Task-level routing policy before provider-specific resolution."""

    name: str
    primary_models: Mapping[str, str]
    fallback_models: Mapping[str, str]
    temperature: float | None = None
    max_tokens: int | None = None
    structured_output_required: bool = False
    web_research_allowed: bool = False
    file_parser_allowed: bool = False
    response_healing_allowed: bool = False


@dataclass(frozen=True)
class ResolvedRoutingProfile:
    """Provider-specific routing policy for one request."""

    name: str
    provider: str
    primary_model: str
    fallback_model: str
    temperature: float | None
    max_tokens: int | None
    structured_output_required: bool
    web_research_allowed: bool
    file_parser_allowed: bool
    response_healing_allowed: bool


ROUTING_PROFILES: dict[str, RoutingProfile] = {
    PROFILE_CONVERSION_STRICT: RoutingProfile(
        name=PROFILE_CONVERSION_STRICT,
        primary_models={
            PROVIDER_OPENROUTER: DEFAULT_OPENROUTER_MODEL,
            PROVIDER_OPENAI: DEFAULT_OPENAI_MODEL,
        },
        fallback_models={
            PROVIDER_OPENROUTER: FALLBACK_OPENROUTER_MODEL,
            PROVIDER_OPENAI: RESEARCH_OPENAI_MODEL,
        },
        temperature=0.2,
        max_tokens=6000,
        structured_output_required=True,
        web_research_allowed=False,
        file_parser_allowed=True,
        response_healing_allowed=True,
    ),
    PROFILE_REFINEMENT_STRICT: RoutingProfile(
        name=PROFILE_REFINEMENT_STRICT,
        primary_models={
            PROVIDER_OPENROUTER: DEFAULT_OPENROUTER_MODEL,
            PROVIDER_OPENAI: DEFAULT_OPENAI_MODEL,
        },
        fallback_models={
            PROVIDER_OPENROUTER: FALLBACK_OPENROUTER_MODEL,
            PROVIDER_OPENAI: RESEARCH_OPENAI_MODEL,
        },
        temperature=0.2,
        max_tokens=7000,
        structured_output_required=True,
        web_research_allowed=False,
        file_parser_allowed=True,
        response_healing_allowed=True,
    ),
    PROFILE_CAPTIONING_VISION: RoutingProfile(
        name=PROFILE_CAPTIONING_VISION,
        primary_models={
            PROVIDER_OPENROUTER: DEFAULT_OPENROUTER_MODEL,
            PROVIDER_OPENAI: DEFAULT_OPENAI_MODEL,
        },
        fallback_models={
            PROVIDER_OPENROUTER: FALLBACK_OPENROUTER_MODEL,
            PROVIDER_OPENAI: DEFAULT_OPENAI_MODEL,
        },
        temperature=0.1,
        max_tokens=1200,
        structured_output_required=True,
        web_research_allowed=False,
        file_parser_allowed=False,
        response_healing_allowed=True,
    ),
    PROFILE_GENERAL_CHAT_ECONOMY: RoutingProfile(
        name=PROFILE_GENERAL_CHAT_ECONOMY,
        primary_models={
            PROVIDER_OPENROUTER: DEFAULT_OPENROUTER_MODEL,
            PROVIDER_OPENAI: DEFAULT_OPENAI_MODEL,
        },
        fallback_models={
            PROVIDER_OPENROUTER: FALLBACK_OPENROUTER_MODEL,
            PROVIDER_OPENAI: DEFAULT_OPENAI_MODEL,
        },
        temperature=0.4,
        max_tokens=3000,
        structured_output_required=False,
        web_research_allowed=False,
        file_parser_allowed=False,
        response_healing_allowed=False,
    ),
    PROFILE_RESEARCH_TOOLING: RoutingProfile(
        name=PROFILE_RESEARCH_TOOLING,
        primary_models={
            PROVIDER_OPENROUTER: RESEARCH_OPENROUTER_MODEL,
            PROVIDER_OPENAI: RESEARCH_OPENAI_MODEL,
        },
        fallback_models={
            PROVIDER_OPENROUTER: FALLBACK_OPENROUTER_MODEL,
            PROVIDER_OPENAI: RESEARCH_OPENAI_MODEL,
        },
        temperature=0.2,
        max_tokens=5000,
        structured_output_required=False,
        web_research_allowed=True,
        file_parser_allowed=True,
        response_healing_allowed=False,
    ),
    PROFILE_TRANSCRIPTION_AUDIO: RoutingProfile(
        name=PROFILE_TRANSCRIPTION_AUDIO,
        primary_models={
            PROVIDER_OPENROUTER: TRANSCRIPTION_OPENROUTER_MODEL,
            PROVIDER_OPENAI: TRANSCRIPTION_OPENAI_MODEL,
        },
        fallback_models={
            PROVIDER_OPENROUTER: DEFAULT_OPENROUTER_MODEL,
            PROVIDER_OPENAI: TRANSCRIPTION_OPENAI_MODEL,
        },
        temperature=0,
        max_tokens=4000,
        structured_output_required=False,
        web_research_allowed=False,
        file_parser_allowed=False,
        response_healing_allowed=False,
    ),
}


def normalize_ai_provider(provider: str | None) -> str:
    value = str(provider or "").strip().lower()
    if value in SUPPORTED_AI_PROVIDERS:
        return value
    return DEFAULT_AI_PROVIDER


def provider_label(provider: str | None = None) -> str:
    return "OpenRouter" if normalize_ai_provider(provider) == PROVIDER_OPENROUTER else "OpenAI"


def _override_env_name(profile_name: str, provider: str, kind: str) -> str:
    return f"{provider}_{profile_name}_{kind}_model".upper()


def _model_override(profile_name: str, provider: str, kind: str) -> str:
    return os.environ.get(_override_env_name(profile_name, provider, kind), "").strip()


def resolve_routing_profile(
    profile_name: str,
    *,
    provider: str | None,
    primary_model_override: str = "",
    fallback_model_override: str = "",
    allow_web_research: bool | None = None,
    allow_file_parser: bool | None = None,
    allow_response_healing: bool | None = None,
) -> ResolvedRoutingProfile:
    """Resolve one task routing profile for a provider.

    Model override precedence is profile-specific environment override,
    explicit function override, profile default. Environment names use:
    `<PROVIDER>_<PROFILE>_PRIMARY_MODEL` and
    `<PROVIDER>_<PROFILE>_FALLBACK_MODEL`.
    """
    normalized_provider = normalize_ai_provider(provider)
    profile = ROUTING_PROFILES[profile_name]
    primary_model = (
        _model_override(profile_name, normalized_provider, "primary")
        or str(primary_model_override or "").strip()
        or profile.primary_models[normalized_provider]
    )
    fallback_model = (
        _model_override(profile_name, normalized_provider, "fallback")
        or str(fallback_model_override or "").strip()
        or profile.fallback_models[normalized_provider]
    )
    return ResolvedRoutingProfile(
        name=profile.name,
        provider=normalized_provider,
        primary_model=primary_model,
        fallback_model=fallback_model,
        temperature=profile.temperature,
        max_tokens=profile.max_tokens,
        structured_output_required=profile.structured_output_required,
        web_research_allowed=profile.web_research_allowed if allow_web_research is None else bool(allow_web_research),
        file_parser_allowed=profile.file_parser_allowed if allow_file_parser is None else bool(allow_file_parser),
        response_healing_allowed=profile.response_healing_allowed if allow_response_healing is None else bool(allow_response_healing),
    )


def model_attempts(route: ResolvedRoutingProfile) -> list[tuple[str, bool]]:
    attempts = [(route.primary_model, False)]
    if route.fallback_model and route.fallback_model != route.primary_model:
        attempts.append((route.fallback_model, True))
    return attempts


def openrouter_plugins_for_route(
    route: ResolvedRoutingProfile,
    *,
    include_web: bool = False,
    include_file_parser: bool = False,
    include_response_healing: bool = False,
) -> list[dict[str, object]]:
    """Return OpenRouter plugins allowed by the route and requested by context."""
    plugins: list[dict[str, object]] = []
    if route.web_research_allowed and include_web:
        plugins.append({"id": "web"})
    if route.file_parser_allowed and include_file_parser:
        plugins.append({"id": "file-parser", "pdf": {"engine": "cloudflare-ai"}})
    if route.response_healing_allowed and include_response_healing:
        plugins.append({"id": "response-healing"})
    return plugins


def plugin_flags_from_plugins(plugins: list[dict[str, object]] | None) -> dict[str, bool]:
    plugin_ids = {str(plugin.get("id", "") or "").strip() for plugin in plugins or []}
    return {
        "web": "web" in plugin_ids,
        "file_parser": "file-parser" in plugin_ids,
        "response_healing": "response-healing" in plugin_ids,
    }


def chat_completion_options(route: ResolvedRoutingProfile) -> dict[str, object]:
    options: dict[str, object] = {}
    if route.temperature is not None:
        options["temperature"] = route.temperature
    if route.max_tokens:
        options["max_tokens"] = route.max_tokens
    return options


def is_transient_ai_error(exc: Exception) -> bool:
    """Return whether a failed provider/model call is worth one fallback retry."""
    status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if isinstance(status_code, int) and status_code in {408, 409, 429, 500, 502, 503, 504}:
        return True

    message = str(exc or "").lower()
    transient_markers = (
        "rate limit",
        "timeout",
        "timed out",
        "temporar",
        "try again",
        "overloaded",
        "unavailable",
        "capacity",
        "no endpoints",
        "no available",
        "provider returned error",
        "model unavailable",
        "model not available",
        "model not found",
    )
    return any(marker in message for marker in transient_markers)
