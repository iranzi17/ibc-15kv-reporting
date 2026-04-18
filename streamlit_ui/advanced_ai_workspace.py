from __future__ import annotations

import os

import streamlit as st

from core.session_state import (
    GUIDANCE_TARGETS,
    OPENAI_API_KEY_SESSION_KEY,
    OPENAI_CHAT_MESSAGES_KEY,
    OPENAI_MODEL_SESSION_KEY,
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
    default_openai_model,
    load_openai_api_key,
    openai_sdk_ready,
    request_openai_reply,
    streamlit_secret,
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
    """Render the shared knowledge-base uploader used by AI workflows."""
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
        "Secondary helper for general reporting questions. It does not connect to personal ChatGPT history.",
    )
    with safe_expander("Assistant settings", expanded=False):
        entered_key = safe_text_input(
            "OpenAI API key (session only)",
            value="",
            type="password",
            key="openai_api_key_input",
            placeholder="sk-...",
        ).strip()
        if entered_key:
            st.session_state[OPENAI_API_KEY_SESSION_KEY] = entered_key

        active_key = load_openai_api_key()
        key_source = "session input"
        if not st.session_state.get(OPENAI_API_KEY_SESSION_KEY):
            if os.environ.get("OPENAI_API_KEY", "").strip():
                key_source = "environment variable"
            elif streamlit_secret("OPENAI_API_KEY"):
                key_source = "Streamlit secrets"
            else:
                key_source = "not configured"

        model_value = safe_text_input(
            "OpenAI model",
            value=default_openai_model(),
            key="openai_model_input",
            placeholder=DEFAULT_OPENAI_MODEL,
        ).strip()
        st.session_state[OPENAI_MODEL_SESSION_KEY] = model_value or DEFAULT_OPENAI_MODEL

        clear_key_col, clear_chat_col = safe_columns(2, gap="large")
        with clear_key_col:
            if st.button("Forget session API key"):
                st.session_state.pop(OPENAI_API_KEY_SESSION_KEY, None)
                st.session_state["openai_api_key_input"] = ""
        with clear_chat_col:
            if st.button("Clear assistant history"):
                st.session_state[OPENAI_CHAT_MESSAGES_KEY] = []
                st.session_state.pop("openai_previous_response_id", None)

        if active_key:
            st.success(f"OpenAI key loaded from {key_source}.")
        else:
            st.info("Add OPENAI_API_KEY to Streamlit secrets or the environment, or paste it above for this session.")

    sdk_ready, sdk_error = openai_sdk_ready()
    if not sdk_ready:
        st.warning(
            "OpenAI SDK is not installed yet. Run `pip install -r requirements.txt` and reload the app. "
            f"Detail: {sdk_error}"
        )
        return

    messages = st.session_state.setdefault(OPENAI_CHAT_MESSAGES_KEY, [])
    prompt = safe_chat_input("Ask a general reporting question.")
    if prompt:
        api_key = load_openai_api_key()
        if not api_key:
            st.warning("OpenAI API key is required before you can start chatting.")
        else:
            model = default_openai_model()
            messages.append({"role": "user", "content": prompt})
            try:
                with safe_spinner("Waiting for OpenAI..."):
                    reply_text, response_id = request_openai_reply(prompt, api_key=api_key, model=model)
            except Exception as exc:
                messages.pop()
                st.error(f"OpenAI request failed: {exc}")
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
                api_key = load_openai_api_key()
                if not api_key:
                    raise ValueError("OpenAI API key is required for the research assistant.")
                sdk_ready, sdk_error = openai_sdk_ready()
                if not sdk_ready:
                    raise ValueError(f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}")

                knowledge_vector_store_id = ""
                if knowledge_files:
                    with safe_spinner("Indexing project references..."):
                        knowledge_vector_store_id, _ = ensure_knowledge_vector_store(knowledge_files, api_key=api_key)

                with safe_spinner("Research assistant is working..."):
                    assistant_message, sources = request_research_assistant_reply(
                        api_key=api_key,
                        model=default_openai_model(),
                        discipline=discipline,
                        question=research_question,
                        conversation=research_messages,
                        allow_web_research=allow_web_research,
                        knowledge_vector_store_id=knowledge_vector_store_id,
                        persistent_guidance=research_guidance,
                        conversation_transcript=conversation_transcript(research_messages),
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
                api_key = load_openai_api_key()
                if not api_key:
                    raise ValueError("OpenAI API key is required for text-to-speech.")
                sdk_ready, sdk_error = openai_sdk_ready()
                if not sdk_ready:
                    raise ValueError(f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}")
                with safe_spinner("Generating research audio..."):
                    st.session_state[RESEARCH_ASSISTANT_AUDIO_KEY] = request_text_to_speech_with_openai(last_assistant_message, api_key=api_key)
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
                api_key = load_openai_api_key()
                if not api_key:
                    raise ValueError("OpenAI API key is required for spreadsheet analysis.")
                sdk_ready, sdk_error = openai_sdk_ready()
                if not sdk_ready:
                    raise ValueError(f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}")
                question = analysis_question or (
                    "Use the python tool to summarize the uploaded datasets, highlight anomalies, "
                    "flag missing values, and surface the most actionable reporting insights."
                )
                with safe_spinner("Analyzing spreadsheets..."):
                    analysis_text, artifacts = request_spreadsheet_analysis_with_openai(
                        api_key=api_key,
                        model=default_openai_model(),
                        uploaded_files=analysis_files,
                        question=question,
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
                api_key = load_openai_api_key()
                if not api_key:
                    raise ValueError("OpenAI API key is required for text-to-speech.")
                sdk_ready, sdk_error = openai_sdk_ready()
                if not sdk_ready:
                    raise ValueError(f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}")
                with safe_spinner("Generating spreadsheet analysis audio..."):
                    st.session_state[SHEET_ANALYST_AUDIO_KEY] = request_text_to_speech_with_openai(analysis_text, api_key=api_key)
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

