from __future__ import annotations

import io
import textwrap

import streamlit as st

from core.session_state import PROJECT_KNOWLEDGE_VECTOR_STORE_KEY
from services.media_service import (
    has_pdf_files,
    uploaded_file_bytes,
    uploaded_file_name,
    uploaded_file_names,
    uploaded_files_to_chat_content,
    uploaded_files_signature,
    uploaded_files_to_response_input,
)
from services.openai_client import (
    OPENAI_ONLY_RESPONSES_FEATURE_MESSAGE,
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
    extract_chat_completion_text,
    extract_openai_output_text,
    make_ai_client,
    normalize_ai_provider,
    provider_label,
    provider_supports_openai_responses_tools,
    tool_enabled_model,
)
from services.model_routing import (
    PROFILE_RESEARCH_TOOLING,
    chat_completion_options,
    openrouter_plugins_for_route,
    plugin_flags_from_plugins,
    resolve_routing_profile,
)
from services.usage_logging import log_usage_event


def extract_web_search_sources(response) -> list[dict[str, str]]:
    """Extract unique web-search sources from a Responses API object."""
    sources: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in getattr(response, "output", []) or []:
        if str(getattr(item, "type", "") or "") != "web_search_call":
            continue
        action = getattr(item, "action", None)
        action_sources = getattr(action, "sources", []) if action is not None else []
        for source in action_sources or []:
            if isinstance(source, dict):
                title = str(source.get("title", "") or "").strip()
                url = str(source.get("url", "") or "").strip()
            else:
                title = str(getattr(source, "title", "") or "").strip()
                url = str(getattr(source, "url", "") or "").strip()
            if not url:
                continue
            key = (title, url)
            if key in seen:
                continue
            seen.add(key)
            sources.append({"title": title, "url": url})
    return sources


def extract_file_search_sources(response) -> list[dict[str, str]]:
    """Extract unique file-search references from a Responses API object."""
    sources: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in getattr(response, "output", []) or []:
        if str(getattr(item, "type", "") or "") != "file_search_call":
            continue
        results = getattr(item, "results", []) or []
        for result in results:
            if isinstance(result, dict):
                filename = str(result.get("filename", "") or result.get("file_id", "") or "").strip()
                score_value = result.get("score")
            else:
                filename = str(getattr(result, "filename", "") or getattr(result, "file_id", "") or "").strip()
                score_value = getattr(result, "score", None)
            if not filename:
                continue
            score_text = f"Relevance {float(score_value):.2f}" if isinstance(score_value, (float, int)) else ""
            key = (filename, score_text)
            if key in seen:
                continue
            seen.add(key)
            sources.append({"title": filename, "url": "", "note": score_text})
    return sources


def extract_container_artifacts(response) -> list[dict[str, str]]:
    """Extract files created by Code Interpreter from a response."""
    artifacts: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in getattr(response, "output", []) or []:
        if str(getattr(item, "type", "") or "") != "message":
            continue
        for content in getattr(item, "content", []) or []:
            for annotation in getattr(content, "annotations", []) or []:
                if isinstance(annotation, dict):
                    annotation_type = str(annotation.get("type", "") or "")
                    container_id = str(annotation.get("container_id", "") or "").strip()
                    file_id = str(annotation.get("file_id", "") or "").strip()
                    filename = str(annotation.get("filename", "") or file_id).strip()
                else:
                    annotation_type = str(getattr(annotation, "type", "") or "")
                    container_id = str(getattr(annotation, "container_id", "") or "").strip()
                    file_id = str(getattr(annotation, "file_id", "") or "").strip()
                    filename = str(getattr(annotation, "filename", "") or file_id).strip()
                if annotation_type != "container_file_citation" or not file_id:
                    continue
                key = (container_id, file_id, filename)
                if key in seen:
                    continue
                seen.add(key)
                artifacts.append(
                    {
                        "container_id": container_id,
                        "file_id": file_id,
                        "filename": filename,
                    }
                )
    return artifacts


def extract_response_sources(response) -> list[dict[str, str]]:
    return extract_web_search_sources(response) + extract_file_search_sources(response)


def converter_response_options(
    *,
    allow_web_research: bool,
    knowledge_vector_store_id: str = "",
) -> dict[str, object]:
    """Build extra Responses API options for tool-enabled flows."""
    tools: list[dict[str, object]] = []
    include: list[str] = []
    if allow_web_research:
        tools.append({"type": "web_search"})
        include.append("web_search_call.action.sources")
    if knowledge_vector_store_id:
        tools.append(
            {
                "type": "file_search",
                "vector_store_ids": [knowledge_vector_store_id],
                "max_num_results": 5,
            }
        )
        include.append("file_search_call.results")
    if not tools:
        return {}
    return {
        "reasoning": {"effort": "low"},
        "tools": tools,
        "tool_choice": "auto",
        "include": include,
    }


def knowledge_vector_store_cache() -> dict[str, object]:
    return st.session_state.setdefault(PROJECT_KNOWLEDGE_VECTOR_STORE_KEY, {})


def ensure_knowledge_vector_store(
    files: list[object],
    *,
    api_key: str,
    provider: str | None = PROVIDER_OPENAI,
) -> tuple[str, list[str]]:
    """Upload knowledge files to an ephemeral vector store and return its id."""
    if not files:
        return "", []
    if not provider_supports_openai_responses_tools(provider):
        return "", uploaded_file_names(files)

    filenames = uploaded_file_names(files)
    signature = uploaded_files_signature(files)
    cache = knowledge_vector_store_cache()
    cached_signature = str(cache.get("signature", "") or "")
    cached_vector_store_id = str(cache.get("vector_store_id", "") or "")
    if signature and signature == cached_signature and cached_vector_store_id:
        return cached_vector_store_id, filenames

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    vector_store = client.vector_stores.create(
        name="IBC Reporting Knowledge Base",
        expires_after={"anchor": "last_active_at", "days": 1},
    )

    upload_handles: list[io.BytesIO] = []
    for uploaded_file in files:
        file_data = uploaded_file_bytes(uploaded_file)
        if not file_data:
            continue
        upload_handle = io.BytesIO(file_data)
        upload_handle.name = uploaded_file_name(uploaded_file)
        upload_handles.append(upload_handle)

    if not upload_handles:
        raise ValueError("No readable knowledge files were uploaded.")

    try:
        batch = client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store.id,
            files=upload_handles,
        )
    finally:
        for upload_handle in upload_handles:
            upload_handle.close()

    file_counts = getattr(batch, "file_counts", None)
    failed = int(getattr(file_counts, "failed", 0) or 0)
    cancelled = int(getattr(file_counts, "cancelled", 0) or 0)
    if failed or cancelled:
        raise ValueError(
            "Some knowledge files could not be indexed for file search. "
            f"Failed: {failed}, cancelled: {cancelled}."
        )

    st.session_state[PROJECT_KNOWLEDGE_VECTOR_STORE_KEY] = {
        "signature": signature,
        "vector_store_id": vector_store.id,
        "filenames": filenames,
    }
    return str(vector_store.id), filenames


def request_research_assistant_reply(
    *,
    api_key: str,
    model: str,
    discipline: str,
    question: str,
    conversation: list[dict[str, str]],
    allow_web_research: bool = False,
    knowledge_vector_store_id: str = "",
    persistent_guidance: str = "",
    conversation_transcript: str = "",
    supporting_files: list[object] | None = None,
    provider: str | None = PROVIDER_OPENAI,
) -> tuple[str, list[dict[str, str]]]:
    """Answer a research or standards question using web/file search when enabled."""
    normalized_provider = normalize_ai_provider(provider)

    instructions = textwrap.dedent(
        f"""
        You are a senior research assistant for {discipline.lower()} consultant reporting and site supervision.
        Answer the user's question clearly and practically.

        Rules:
        - Prefer uploaded project knowledge files when file search is available.
        - Use web research only when it adds current external context or technical best practice.
        - Do not invent standard names, clauses, regulations, or project requirements.
        - If the answer depends on an assumption, state it briefly.
        - Keep the response concise, concrete, and useful for field reporting decisions.
        """
    ).strip()
    if persistent_guidance:
        instructions = f"{instructions}\n\nSaved app preferences:\n{persistent_guidance}"

    request_text = textwrap.dedent(
        f"""
        Prior conversation:
        {conversation_transcript}

        Latest user question:
        {question.strip()}
        """
    ).strip()

    route = resolve_routing_profile(
        PROFILE_RESEARCH_TOOLING,
        provider=normalized_provider,
        primary_model_override=model,
        allow_web_research=allow_web_research,
        allow_file_parser=has_pdf_files(supporting_files),
    )
    resolved_model = tool_enabled_model(
        route.primary_model,
        provider=normalized_provider,
        allow_web_research=allow_web_research,
        allow_file_search=bool(knowledge_vector_store_id),
    )
    response = None
    plugin_flags = plugin_flags_from_plugins([])
    try:
        client = make_ai_client(api_key=api_key, provider=normalized_provider)
        if normalized_provider == PROVIDER_OPENROUTER:
            request_kwargs: dict[str, object] = {
                "model": resolved_model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {
                        "role": "user",
                        "content": uploaded_files_to_chat_content(
                            request_text,
                            uploaded_files=supporting_files,
                        ),
                    },
                ],
                **chat_completion_options(route),
            }
            plugins = openrouter_plugins_for_route(
                route,
                include_web=allow_web_research,
                include_file_parser=has_pdf_files(supporting_files),
            )
            plugin_flags = plugin_flags_from_plugins(plugins)
            if plugins:
                request_kwargs["extra_body"] = {"plugins": plugins}
            response = client.chat.completions.create(**request_kwargs)
            reply_text = extract_chat_completion_text(response)
        else:
            response = client.responses.create(
                model=resolved_model,
                instructions=instructions,
                input=request_text,
                store=False,
                **converter_response_options(
                    allow_web_research=allow_web_research,
                    knowledge_vector_store_id=knowledge_vector_store_id,
                ),
            )
            reply_text = extract_openai_output_text(response)
        if not reply_text:
            raise ValueError(f"{provider_label(normalized_provider)} returned an empty research reply.")
    except Exception as exc:
        log_usage_event(
            feature_name="research_assistant",
            model=resolved_model,
            has_files=bool(knowledge_vector_store_id or supporting_files),
            has_images=False,
            status="failed",
            error_summary=str(exc),
            provider=normalized_provider,
            routing_profile=route.name,
            resolved_model=resolved_model,
            fallback_used=False,
            plugin_flags=plugin_flags,
        )
        raise

    log_usage_event(
        feature_name="research_assistant",
        model=resolved_model,
        has_files=bool(knowledge_vector_store_id or supporting_files),
        has_images=False,
        status="success",
        provider=normalized_provider,
        routing_profile=route.name,
        resolved_model=resolved_model,
        fallback_used=False,
        plugin_flags=plugin_flags,
    )
    return reply_text, extract_response_sources(response) if normalized_provider == PROVIDER_OPENAI else []


def request_spreadsheet_analysis_with_openai(
    *,
    api_key: str,
    model: str,
    uploaded_files: list[object],
    question: str,
    provider: str | None = PROVIDER_OPENAI,
) -> tuple[str, list[dict[str, str]]]:
    """Analyze uploaded datasets using Code Interpreter."""
    normalized_provider = normalize_ai_provider(provider)
    if normalized_provider == PROVIDER_OPENROUTER:
        raise ValueError(OPENAI_ONLY_RESPONSES_FEATURE_MESSAGE)

    if not uploaded_files:
        raise ValueError("Upload at least one spreadsheet or dataset before running analysis.")

    instructions = textwrap.dedent(
        """
        You are a project controls and reporting analyst.
        Always use the python tool on the uploaded files before answering.

        Focus on:
        - progress totals and trends
        - anomalies, missing values, and duplicates
        - site/date mismatches
        - quantities, counts, and comparisons the user asks for
        - concise, actionable conclusions

        If it helps the answer, generate plots or export files in the container and mention them.
        """
    ).strip()
    resolved_model = tool_enabled_model(model, provider=normalized_provider, allow_code_interpreter=True)
    try:
        response = make_ai_client(api_key=api_key, provider=normalized_provider).responses.create(
            model=resolved_model,
            tools=[
                {
                    "type": "code_interpreter",
                    "container": {"type": "auto", "memory_limit": "4g"},
                }
            ],
            tool_choice="required",
            instructions=instructions,
            input=uploaded_files_to_response_input(question.strip(), uploaded_files=uploaded_files),
            store=False,
        )
        analysis_text = extract_openai_output_text(response)
        if not analysis_text:
            raise ValueError("OpenAI returned an empty spreadsheet analysis.")
    except Exception as exc:
        log_usage_event(
            feature_name="spreadsheet_analyst",
            model=resolved_model,
            has_files=True,
            has_images=False,
            status="failed",
            error_summary=str(exc),
            provider=normalized_provider,
            resolved_model=resolved_model,
            fallback_used=False,
            plugin_flags=plugin_flags_from_plugins([]),
        )
        raise

    log_usage_event(
        feature_name="spreadsheet_analyst",
        model=resolved_model,
        has_files=True,
        has_images=False,
        status="success",
        provider=normalized_provider,
        resolved_model=resolved_model,
        fallback_used=False,
        plugin_flags=plugin_flags_from_plugins([]),
    )
    return analysis_text, extract_container_artifacts(response)

