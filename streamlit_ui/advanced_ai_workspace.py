from __future__ import annotations

import streamlit as st

from core.session_state import (
    AI_PROVIDER_SESSION_KEY,
    GUIDANCE_TARGETS,
    OPENAI_API_KEY_SESSION_KEY,
    OPENAI_CHAT_MESSAGES_KEY,
    OPENAI_MODEL_SESSION_KEY,
    OPENROUTER_API_KEY_SESSION_KEY,
    OPENROUTER_MODEL_SESSION_KEY,
    PROJECT_KNOWLEDGE_FILE_TYPES,
    PROJECT_KNOWLEDGE_VECTOR_STORE_KEY,
    RESEARCH_ASSISTANT_AUDIO_KEY,
    RESEARCH_ASSISTANT_MESSAGES_KEY,
    SHEET_ANALYST_AUDIO_KEY,
    SHEET_ANALYST_RESULT_KEY,
    ANALYST_FILE_TYPES,
    delete_saved_guidance_item,
    save_saved_guidance_item,
    saved_guidance_items,
)
from services.converter_service import conversation_transcript
from services.media_service import request_text_to_speech_with_openai, uploaded_file_names
from services.openai_client import (
    DEFAULT_OPENAI_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
    SUPPORTED_AI_PROVIDERS,
    active_ai_provider,
    ai_api_key_source,
    default_ai_model,
    load_ai_api_key,
    openai_sdk_ready,
    provider_label,
    provider_supports_openai_responses_tools,
    request_openai_reply,
)
from services.research_service import ensure_knowledge_vector_store, request_research_assistant_reply, request_spreadsheet_analysis_with_openai
from streamlit_ui.helpers import (
    safe_audio,
    safe_caption,
    safe_chat_input,
    safe_chat_message,
    safe_columns,
    safe_expander,
    safe_file_uploader,
    safe_markdown,
    safe_rerun,
    safe_spinner,
    safe_text_area,
    safe_text_input,
    safe_write,
)
from streamlit_ui.layout import render_section_header, render_subsection


def render_project_knowledge_base_panel() -> list[object]:
    """Render the shared AI provider controls and knowledge-base uploader."""
    with safe_expander("AI Provider & Model", expanded=True):
        active_provider = active_ai_provider()
        provider_options = list(SUPPORTED_AI_PROVIDERS)
        selected_provider = st.selectbox(
            "AI provider",
            provider_options,
            index=provider_options.index(active_provider) if active_provider in provider_options else 0,
            format_func=provider_label,
            key="ai_provider_selector",
            help="OpenRouter is the default provider for conversion, refinement, captions, research, and diagnostics.",
        )
        st.session_state[AI_PROVIDER_SESSION_KEY] = selected_provider

        key_session_name = (
            OPENROUTER_API_KEY_SESSION_KEY
            if selected_provider == PROVIDER_OPENROUTER
            else OPENAI_API_KEY_SESSION_KEY
        )
        model_session_name = (
            OPENROUTER_MODEL_SESSION_KEY
            if selected_provider == PROVIDER_OPENROUTER
            else OPENAI_MODEL_SESSION_KEY
        )
        default_model = default_ai_model(selected_provider)
        entered_key = safe_text_input(
            f"{provider_label(selected_provider)} API key (session only)",
            value="",
            type="password",
            key=f"{selected_provider}_api_key_input",
            placeholder="sk-or-..." if selected_provider == PROVIDER_OPENROUTER else "sk-...",
        ).strip()
        if entered_key:
            st.session_state[key_session_name] = entered_key

        model_value = safe_text_input(
            f"{provider_label(selected_provider)} model",
            value=default_model,
            key=f"{selected_provider}_model_input",
            placeholder=DEFAULT_OPENROUTER_MODEL if selected_provider == PROVIDER_OPENROUTER else DEFAULT_OPENAI_MODEL,
        ).strip()
        st.session_state[model_session_name] = model_value or default_model

        active_key = load_ai_api_key(selected_provider)
        if active_key:
            st.success(f"{provider_label(selected_provider)} key loaded from {ai_api_key_source(selected_provider)}.")
        else:
            secret_name = "OPENROUTER_API_KEY" if selected_provider == PROVIDER_OPENROUTER else "OPENAI_API_KEY"
            st.info(f"Add {secret_name} to Streamlit secrets or the environment, or paste it above for this session.")

        if selected_provider == PROVIDER_OPENROUTER:
            safe_caption(
                "OpenRouter mode uses Chat Completions for text, JSON, images, PDFs, web plugin calls, and audio-input transcription on compatible models."
            )
        else:
            safe_caption("OpenAI mode remains available for Responses tools such as vector-store search and Code Interpreter.")

    with safe_expander("Shared Project References", expanded=False):
        safe_caption(
            "Upload standards, approved reports, procedures, or client instructions. "
            "These files can support contractor conversion and research responses."
        )
        uploaded_files = list(
            safe_file_uploader(
                "Upload project knowledge files",
                accept_multiple_files=True,
                type=PROJECT_KNOWLEDGE_FILE_TYPES,
                key="project_knowledge_files",
            )
            or []
        )
        if uploaded_files:
            safe_caption(f"Knowledge files ready: {', '.join(uploaded_file_names(uploaded_files))}")
            if not provider_supports_openai_responses_tools(active_ai_provider()):
                safe_caption(
                    "In OpenRouter mode, PDFs/images/text files are sent directly to the active request when supported; "
                    "OpenAI vector-store search is skipped."
                )
        else:
            st.session_state.pop(PROJECT_KNOWLEDGE_VECTOR_STORE_KEY, None)
        return uploaded_files


def render_ai_memory_panel(*, record_runtime_issue) -> None:
    render_subsection(
        "Saved AI Guidance",
        "Store reusable instructions so the converter, captions, research assistant, and maintenance workflows use consistent preferences.",
    )
    target = st.selectbox("Instruction target", GUIDANCE_TARGETS, index=0, key="ai_memory_target")
    instruction = safe_text_area(
        "Reusable instruction",
        value="",
        height=90,
        key="ai_memory_instruction",
        placeholder="Example: Keep consultant comments short and formal. Avoid schedule language unless the source mentions it.",
    ).strip()
    save_col, clear_col = safe_columns(2, gap="large")
    with save_col:
        save_clicked = st.button("Save guidance")
    with clear_col:
        clear_input_clicked = st.button("Clear guidance input")

    if clear_input_clicked:
        st.session_state["ai_memory_instruction"] = ""
        safe_rerun()

    if save_clicked:
        try:
            item = save_saved_guidance_item(instruction, target=str(target or "general"))
        except Exception as exc:
            st.warning(f"Unable to save guidance: {exc}")
            record_runtime_issue("ai_memory", "Failed to save reusable instruction.", details=str(exc))
        else:
            st.success(f"Saved guidance for {item.get('target', 'general')}.")
            st.session_state["ai_memory_instruction"] = ""
            safe_rerun()

    items = saved_guidance_items()
    if not items:
        safe_caption("No reusable guidance is saved yet.")
        return

    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "Untitled instruction").strip()
        target = str(item.get("target", "general") or "general").strip()
        created = str(item.get("created_at", "") or "").strip()
        safe_markdown(f"**{title}**")
        safe_caption(f"Target: {target} | Saved: {created}")
        safe_write(str(item.get("instruction", "") or ""))
        if st.button(f"Delete {item.get('id', '')}", key=f"delete_ai_memory_{item.get('id', '')}"):
            delete_saved_guidance_item(str(item.get("id", "") or ""))
            safe_rerun()


def render_general_chat_panel(*, record_runtime_issue) -> None:
    render_subsection(
        "General AI Assistant",
        "Secondary helper for general reporting questions. It does not connect to any personal chat history.",
    )
    with safe_expander("Assistant settings", expanded=False):
        active_provider = active_ai_provider()
        safe_caption(f"Active provider: {provider_label(active_provider)} | Model: {default_ai_model(active_provider)}")

        clear_key_col, clear_chat_col = safe_columns(2, gap="large")
        with clear_key_col:
            if st.button("Forget active provider session key"):
                if active_provider == PROVIDER_OPENROUTER:
                    st.session_state.pop(OPENROUTER_API_KEY_SESSION_KEY, None)
                    st.session_state[f"{PROVIDER_OPENROUTER}_api_key_input"] = ""
                else:
                    st.session_state.pop(OPENAI_API_KEY_SESSION_KEY, None)
                    st.session_state[f"{PROVIDER_OPENAI}_api_key_input"] = ""
        with clear_chat_col:
            if st.button("Clear assistant history"):
                st.session_state[OPENAI_CHAT_MESSAGES_KEY] = []
                st.session_state.pop("openai_previous_response_id", None)

        active_key = load_ai_api_key(active_provider)
        if active_key:
            st.success(f"{provider_label(active_provider)} key loaded from {ai_api_key_source(active_provider)}.")
        else:
            st.info("Configure the active provider key in the AI Provider & Model panel above.")

    sdk_ready, sdk_error = openai_sdk_ready()
    if not sdk_ready:
        st.warning(
            "OpenAI-compatible SDK is not installed yet. Run `pip install -r requirements.txt` and reload the app. "
            f"Detail: {sdk_error}"
        )
        return

    messages = st.session_state.setdefault(OPENAI_CHAT_MESSAGES_KEY, [])
    prompt = safe_chat_input("Ask a general reporting question.")
    if prompt:
        active_provider = active_ai_provider()
        api_key = load_ai_api_key(active_provider)
        if not api_key:
            st.warning(f"{provider_label(active_provider)} API key is required before you can start chatting.")
        else:
            model = default_ai_model(active_provider)
            messages.append({"role": "user", "content": prompt})
            try:
                with safe_spinner(f"Waiting for {provider_label(active_provider)}..."):
                    reply_text, response_id = request_openai_reply(
                        prompt,
                        api_key=api_key,
                        model=model,
                        provider=active_provider,
                    )
            except Exception as exc:
                messages.pop()
                st.error(f"{provider_label(active_provider)} request failed: {exc}")
                record_runtime_issue("general_chat", "General assistant request failed.", details=str(exc))
            else:
                messages.append({"role": "assistant", "content": reply_text})
                if response_id:
                    st.session_state["openai_previous_response_id"] = response_id

    for message in messages:
        with safe_chat_message(str(message.get("role", "assistant"))):
            safe_write(message.get("content", ""))


def render_advanced_ai_workspace(
    discipline: str,
    *,
    knowledge_files: list[object] | None,
    record_runtime_issue,
    active_guidance_text,
) -> None:
    render_section_header(
        "3. Advanced AI Tools",
        "Optional support tools for terminology, QA, research, and analysis. These workflows are secondary to reporting and conversion.",
    )

    render_ai_memory_panel(record_runtime_issue=record_runtime_issue)

    with safe_expander("Research Assistant", expanded=False):
        render_subsection(
            "Research Assistant",
            "Use this for terminology, standards, QA checks, and reporting decisions. Web research stays optional.",
        )
        allow_web_research = st.checkbox("Allow web research in research assistant", value=True, key="research_assistant_web_research")
        research_guidance = active_guidance_text("research")
        if knowledge_files:
            safe_caption("The uploaded project references will be searched when relevant.")
        else:
            safe_caption("Upload project references above if you want this assistant to search internal documents.")
        if research_guidance:
            safe_caption("Saved research guidance is active.")

        research_messages = st.session_state.setdefault(RESEARCH_ASSISTANT_MESSAGES_KEY, [])
        for message in research_messages:
            with safe_chat_message(str(message.get("role", "assistant"))):
                safe_write(message.get("content", ""))
                sources = message.get("sources", [])
                if isinstance(sources, list) and sources:
                    lines = ["Sources:"]
                    for source in sources:
                        if not isinstance(source, dict):
                            continue
                        title = str(source.get("title", "") or "").strip()
                        url = str(source.get("url", "") or "").strip()
                        note = str(source.get("note", "") or "").strip()
                        line = f"- [{title}]({url})" if url else f"- {title}"
                        if note:
                            line = f"{line} ({note})"
                        lines.append(line)
                    if len(lines) > 1:
                        safe_markdown("\n".join(lines))

        research_question = safe_text_input(
            "Research question",
            value="",
            key="research_assistant_question",
            placeholder="Ask about standards, wording, compliance, or best-practice guidance.",
        ).strip()
        ask_col, clear_col, audio_col = safe_columns(3, gap="large")
        with ask_col:
            ask_clicked = st.button("Ask research assistant")
        with clear_col:
            clear_clicked = st.button("Clear research chat")
        with audio_col:
            read_research_audio = st.button("Read last research answer aloud")

        if clear_clicked:
            st.session_state[RESEARCH_ASSISTANT_MESSAGES_KEY] = []
            st.session_state.pop(RESEARCH_ASSISTANT_AUDIO_KEY, None)
            st.session_state["research_assistant_question"] = ""
            safe_rerun()

        if ask_clicked:
            try:
                if not research_question:
                    raise ValueError("Enter a research question before sending it to the assistant.")
                active_provider = active_ai_provider()
                api_key = load_ai_api_key(active_provider)
                if not api_key:
                    raise ValueError(f"{provider_label(active_provider)} API key is required for the research assistant.")
                sdk_ready, sdk_error = openai_sdk_ready()
                if not sdk_ready:
                    raise ValueError(f"OpenAI-compatible SDK is not installed in the active Streamlit environment. {sdk_error}")

                knowledge_vector_store_id = ""
                research_supporting_files = knowledge_files if active_provider == PROVIDER_OPENROUTER else None
                if knowledge_files and provider_supports_openai_responses_tools(active_provider):
                    with safe_spinner("Indexing project references..."):
                        knowledge_vector_store_id, _ = ensure_knowledge_vector_store(
                            knowledge_files,
                            api_key=api_key,
                            provider=active_provider,
                        )

                with safe_spinner(f"{provider_label(active_provider)} research assistant is working..."):
                    assistant_message, sources = request_research_assistant_reply(
                        api_key=api_key,
                        model=default_ai_model(active_provider),
                        discipline=discipline,
                        question=research_question,
                        conversation=research_messages,
                        allow_web_research=allow_web_research,
                        knowledge_vector_store_id=knowledge_vector_store_id,
                        persistent_guidance=research_guidance,
                        conversation_transcript=conversation_transcript(research_messages),
                        supporting_files=research_supporting_files,
                        provider=active_provider,
                    )
            except Exception as exc:
                st.warning(f"Research assistant failed: {exc}")
                record_runtime_issue("research", "Research assistant failed.", details=str(exc))
            else:
                research_messages.append({"role": "user", "content": research_question, "sources": []})
                research_messages.append({"role": "assistant", "content": assistant_message, "sources": sources})
                st.session_state["research_assistant_question"] = ""
                st.session_state.pop(RESEARCH_ASSISTANT_AUDIO_KEY, None)
                safe_rerun()

        if read_research_audio:
            try:
                last_assistant_message = next(
                    (
                        str(message.get("content", "") or "").strip()
                        for message in reversed(research_messages)
                        if str(message.get("role", "") or "") == "assistant" and str(message.get("content", "") or "").strip()
                    ),
                    "",
                )
                if not last_assistant_message:
                    raise ValueError("Ask the research assistant a question before generating readback audio.")
                active_provider = active_ai_provider()
                api_key = load_ai_api_key(active_provider)
                if not api_key:
                    raise ValueError(f"{provider_label(active_provider)} API key is required for text-to-speech.")
                sdk_ready, sdk_error = openai_sdk_ready()
                if not sdk_ready:
                    raise ValueError(f"OpenAI-compatible SDK is not installed in the active Streamlit environment. {sdk_error}")
                with safe_spinner("Generating research audio..."):
                    st.session_state[RESEARCH_ASSISTANT_AUDIO_KEY] = request_text_to_speech_with_openai(
                        last_assistant_message,
                        api_key=api_key,
                        provider=active_provider,
                    )
            except Exception as exc:
                st.warning(f"Audio generation failed: {exc}")
                record_runtime_issue("research", "Research audio generation failed.", details=str(exc))

        research_audio = st.session_state.get(RESEARCH_ASSISTANT_AUDIO_KEY)
        if research_audio:
            safe_audio(research_audio, format="audio/mp3")

    with safe_expander("Spreadsheet Analyst", expanded=False):
        render_subsection(
            "Spreadsheet Analyst",
            "Advanced support workflow for uploaded datasets. Use when you need anomaly checks, totals, trends, or data QA.",
        )
        analysis_files = list(
            safe_file_uploader(
                "Upload spreadsheets or datasets",
                accept_multiple_files=True,
                type=ANALYST_FILE_TYPES,
                key="spreadsheet_analyst_files",
            )
            or []
        )
        if analysis_files:
            safe_caption(f"Analysis files ready: {', '.join(uploaded_file_names(analysis_files))}")

        analysis_question = safe_text_input(
            "Analysis request",
            value="",
            key="spreadsheet_analyst_question",
            placeholder="Summarize progress by site, detect missing dates, compare quantities, flag anomalies...",
        ).strip()

        analyze_col, clear_col, audio_col = safe_columns(3, gap="large")
        with analyze_col:
            analyze_clicked = st.button("Run spreadsheet analysis")
        with clear_col:
            clear_clicked = st.button("Clear spreadsheet analysis")
        with audio_col:
            read_analysis_audio = st.button("Read spreadsheet analysis aloud")

        if clear_clicked:
            st.session_state.pop(SHEET_ANALYST_RESULT_KEY, None)
            st.session_state.pop(SHEET_ANALYST_AUDIO_KEY, None)
            st.session_state["spreadsheet_analyst_question"] = ""
            safe_rerun()

        if analyze_clicked:
            try:
                if not analysis_files:
                    raise ValueError("Upload one or more spreadsheets or datasets before running analysis.")
                active_provider = active_ai_provider()
                if active_provider != PROVIDER_OPENAI:
                    raise ValueError("Spreadsheet Analyst currently requires OpenAI Responses Code Interpreter. Switch provider to OpenAI for this advanced tool.")
                api_key = load_ai_api_key(active_provider)
                if not api_key:
                    raise ValueError("OpenAI API key is required for spreadsheet analysis.")
                sdk_ready, sdk_error = openai_sdk_ready()
                if not sdk_ready:
                    raise ValueError(f"OpenAI-compatible SDK is not installed in the active Streamlit environment. {sdk_error}")
                question = analysis_question or (
                    "Use the python tool to summarize the uploaded datasets, highlight anomalies, "
                    "flag missing values, and surface the most actionable reporting insights."
                )
                with safe_spinner("Analyzing spreadsheets..."):
                    analysis_text, artifacts = request_spreadsheet_analysis_with_openai(
                        api_key=api_key,
                        model=default_ai_model(active_provider),
                        uploaded_files=analysis_files,
                        question=question,
                        provider=active_provider,
                    )
            except Exception as exc:
                st.warning(f"Spreadsheet analysis failed: {exc}")
                record_runtime_issue("spreadsheet_analyst", "Spreadsheet analysis failed.", details=str(exc))
            else:
                st.session_state[SHEET_ANALYST_RESULT_KEY] = {"text": analysis_text, "artifacts": artifacts}
                st.session_state.pop(SHEET_ANALYST_AUDIO_KEY, None)

        if read_analysis_audio:
            try:
                result = st.session_state.get(SHEET_ANALYST_RESULT_KEY, {})
                analysis_text = str(result.get("text", "") or "").strip()
                if not analysis_text:
                    raise ValueError("Run a spreadsheet analysis before generating readback audio.")
                active_provider = active_ai_provider()
                api_key = load_ai_api_key(active_provider)
                if not api_key:
                    raise ValueError(f"{provider_label(active_provider)} API key is required for text-to-speech.")
                sdk_ready, sdk_error = openai_sdk_ready()
                if not sdk_ready:
                    raise ValueError(f"OpenAI-compatible SDK is not installed in the active Streamlit environment. {sdk_error}")
                with safe_spinner("Generating spreadsheet analysis audio..."):
                    st.session_state[SHEET_ANALYST_AUDIO_KEY] = request_text_to_speech_with_openai(
                        analysis_text,
                        api_key=api_key,
                        provider=active_provider,
                    )
            except Exception as exc:
                st.warning(f"Audio generation failed: {exc}")
                record_runtime_issue("spreadsheet_analyst", "Spreadsheet analysis audio generation failed.", details=str(exc))

        analysis_result = st.session_state.get(SHEET_ANALYST_RESULT_KEY, {})
        analysis_text = str(analysis_result.get("text", "") or "").strip()
        if analysis_text:
            safe_markdown(analysis_text)
        artifacts = analysis_result.get("artifacts", [])
        if isinstance(artifacts, list) and artifacts:
            lines = ["Generated files:"]
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                filename = str(artifact.get("filename", "") or "").strip()
                if filename:
                    lines.append(f"- {filename}")
            if len(lines) > 1:
                safe_markdown("\n".join(lines))
        analysis_audio = st.session_state.get(SHEET_ANALYST_AUDIO_KEY)
        if analysis_audio:
            safe_audio(analysis_audio, format="audio/mp3")

    with safe_expander("General AI Assistant", expanded=False):
        render_general_chat_panel(record_runtime_issue=record_runtime_issue)

    safe_markdown("---")

