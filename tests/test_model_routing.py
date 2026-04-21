from services.model_routing import (
    PROFILE_CAPTIONING_VISION,
    PROFILE_CONVERSION_STRICT,
    PROVIDER_OPENROUTER,
    is_transient_ai_error,
    model_attempts,
    openrouter_plugins_for_route,
    plugin_flags_from_plugins,
    resolve_routing_profile,
)


def test_routing_profile_resolution_uses_provider_defaults_and_env_override(monkeypatch):
    route = resolve_routing_profile(PROFILE_CONVERSION_STRICT, provider=PROVIDER_OPENROUTER)

    assert route.primary_model == "openai/gpt-4o-mini"
    assert route.fallback_model == "openai/gpt-4o"
    assert route.structured_output_required is True
    assert route.file_parser_allowed is True
    assert route.response_healing_allowed is True

    monkeypatch.setenv("OPENROUTER_CONVERSION_STRICT_PRIMARY_MODEL", "vendor/custom-model")
    overridden = resolve_routing_profile(
        PROFILE_CONVERSION_STRICT,
        provider=PROVIDER_OPENROUTER,
        primary_model_override="ui/session-model",
    )

    assert overridden.primary_model == "vendor/custom-model"
    assert model_attempts(overridden) == [
        ("vendor/custom-model", False),
        ("openai/gpt-4o", True),
    ]


def test_openrouter_plugin_policy_is_driven_by_profile_capabilities():
    route = resolve_routing_profile(
        PROFILE_CONVERSION_STRICT,
        provider=PROVIDER_OPENROUTER,
        allow_web_research=True,
        allow_file_parser=True,
    )

    plugins = openrouter_plugins_for_route(
        route,
        include_web=True,
        include_file_parser=True,
        include_response_healing=True,
    )

    assert {"id": "web"} in plugins
    assert {"id": "response-healing"} in plugins
    assert plugin_flags_from_plugins(plugins) == {
        "web": True,
        "file_parser": True,
        "response_healing": True,
    }

    caption_route = resolve_routing_profile(PROFILE_CAPTIONING_VISION, provider=PROVIDER_OPENROUTER)
    caption_plugins = openrouter_plugins_for_route(caption_route, include_web=True, include_file_parser=True)
    assert plugin_flags_from_plugins(caption_plugins) == {
        "web": False,
        "file_parser": False,
        "response_healing": False,
    }


def test_transient_error_detection_for_provider_fallbacks():
    transient = RuntimeError("Provider returned error: model unavailable")
    assert is_transient_ai_error(transient) is True

    schema_error = ValueError("Structured report payload must be a report object or list of reports.")
    assert is_transient_ai_error(schema_error) is False
