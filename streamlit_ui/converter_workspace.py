from __future__ import annotations

import streamlit as st

from core.session_state import (
    AUDIO_FILE_TYPES,
    CONTRACTOR_CHAT_MESSAGES_KEY,
    CONTRACTOR_SUPPORTING_FILE_TYPES,
    CONVERTER_CHANGE_SUMMARY_KEY,
    CONVERTER_LOCKED_FIELDS_KEY,
    CONVERTER_STRICT_MODE_KEY,
    LOCKABLE_CONVERTER_FIELDS,
    PARSED_CONTRACTOR_REPORTS_KEY,
)
from report_structuring import REPORT_HEADERS, clean_and_structure_report
from services.converter_service import (
    apply_field_locks,
    prepare_refinement_inputs,
    refinement_request_preview,
    request_refined_structured_reports_with_openai,
    request_structured_reports_with_openai,
    structured_report_rows,
    structured_rows_from_dataframe,
    structured_rows_to_dataframe,
    summarize_row_changes,
    validate_conversion_source_inputs,
    validate_refinement_request,
    validate_structured_rows_for_sheet,
)
from services.openai_client import (
    PROVIDER_OPENROUTER,
    active_ai_provider,
    default_ai_model,
    load_ai_api_key,
    openai_sdk_ready,
    provider_label,
    provider_supports_openai_responses_tools,
)
from services.research_service import ensure_knowledge_vector_store
from sheets import append_rows_to_sheet, get_sheet_data
from streamlit_ui.helpers import (
    safe_audio,
    safe_audio_input,
    safe_caption,
    safe_chat_input,
    safe_chat_message,
    safe_columns,
    safe_data_editor,
    safe_expander,
    safe_file_uploader,
    safe_markdown,
    safe_rerun,
    safe_spinner,
    safe_text_area,
    safe_write,
)
from streamlit_ui.layout import render_note, render_section_header, render_subsection


def reset_contractor_chat(rows: list[dict[str, str]], *, source_label: str) -> None:
    count = len(structured_report_rows(rows))
    st.session_state[CONTRACTOR_CHAT_MESSAGES_KEY] = [
        {
            "role": "assistant",
            "content": (
                f"{source_label} produced {count} structured report row(s). "
                "Refinement instructions update the converted rows directly."
            ),
            "sources": [],
        }
    ]


def append_contractor_chat_message(
    role: str,
    content: str,
    *,
    sources: list[dict[str, str]] | None = None,
) -> None:
    messages = st.session_state.setdefault(CONTRACTOR_CHAT_MESSAGES_KEY, [])
    messages.append({"role": role, "content": content, "sources": list(sources or [])})


def render_contractor_chat_message(message: dict[str, object]) -> None:
    with safe_chat_message(str(message.get("role", "assistant"))):
        safe_write(message.get("content", ""))
        sources = message.get("sources", [])
        if not isinstance(sources, list) or not sources:
            return
        lines = ["Sources:"]
        for source in sources:
            if not isinstance(source, dict):
                continue
            url = str(source.get("url", "") or "").strip()
            title = str(source.get("title", "") or "").strip() or url
            note = str(source.get("note", "") or "").strip()
            line = f"- [{title}]({url})" if url else f"- {title}"
            if note:
                line = f"{line} ({note})"
            lines.append(line)
        if len(lines) > 1:
            safe_markdown("\n".join(lines))


def render_change_summary(summary: list[dict[str, object]]) -> None:
    if not summary:
        return
    render_note("Latest AI update summary")
    for row_summary in summary:
        if not isinstance(row_summary, dict):
            continue
        row_label = f"Row {row_summary.get('row_index', '')}"
        site = str(row_summary.get("site_name", "") or "").strip()
        date = str(row_summary.get("date", "") or "").strip()
        header = row_label
        if site or date:
            header = f"{row_label} | {site} | {date}".strip(" |")
        safe_markdown(f"**{header}**")
        for change in row_summary.get("changes", []):
            if not isinstance(change, dict):
                continue
            field = str(change.get("field", "") or "").strip()
            before = str(change.get("before", "") or "").strip() or "empty"
            after = str(change.get("after", "") or "").strip() or "empty"
            safe_markdown(f"- `{field}`: `{before}` -> `{after}`")


def persist_parsed_rows(
    rows: list[dict[str, str]],
    *,
    source_label: str,
    reset_chat: bool,
) -> None:
    normalized_rows = structured_report_rows(rows)
    st.session_state[PARSED_CONTRACTOR_REPORTS_KEY] = normalized_rows
    st.session_state["structured_report_data"] = normalized_rows
    st.session_state["_structured_origin"] = "manual"
    if reset_chat:
        reset_contractor_chat(normalized_rows, source_label=source_label)


def clear_parsed_rows() -> None:
    st.session_state.pop(PARSED_CONTRACTOR_REPORTS_KEY, None)
    st.session_state.pop(CONTRACTOR_CHAT_MESSAGES_KEY, None)
    st.session_state.pop(CONVERTER_CHANGE_SUMMARY_KEY, None)


def clear_cached_sheet_data() -> None:
    clear_fn = getattr(get_sheet_data, "clear", None)
    if callable(clear_fn):
        clear_fn()


def rows_for_sheet_append(rows: list[dict[str, str]]) -> list[list[str]]:
    """Return rows ordered by canonical report headers for Google Sheet append."""
    return [[str(row.get(header, "") or "").strip() for header in REPORT_HEADERS] for row in rows]


def render_converter_workspace(
    discipline: str,
    *,
    knowledge_files: list[object] | None,
    record_runtime_issue,
    active_guidance_text,
) -> None:
    render_section_header(
        "2. Contractor Conversion",
        "Convert raw contractor inputs into structured consultant rows, then refine the result with controlled AI assistance.",
    )

    render_subsection(
        "Source Intake",
        "Paste contractor text and add supporting files, photos, or voice notes before conversion.",
    )
    active_provider = active_ai_provider()
    provider_name = provider_label(active_provider)
    converter_guidance = active_guidance_text("converter")
    raw_report_text = safe_text_area("Paste contractor report text", height=220, key="contractor_report_text")
    supporting_files = list(
        safe_file_uploader(
            "Upload contractor documents or site photos (optional)",
            accept_multiple_files=True,
            type=CONTRACTOR_SUPPORTING_FILE_TYPES,
            key="contractor_supporting_files",
        )
        or []
    )
    audio_files = list(
        safe_file_uploader(
            "Upload contractor voice notes (optional)",
            accept_multiple_files=True,
            type=AUDIO_FILE_TYPES,
            key="contractor_audio_files",
        )
        or []
    )
    if supporting_files:
        safe_caption(f"Attached source files: {', '.join(file.name for file in supporting_files)}")
    if audio_files:
        safe_caption(f"Voice notes ready: {', '.join(file.name for file in audio_files)}")
    if knowledge_files:
        if provider_supports_openai_responses_tools(active_provider):
            safe_caption("Project knowledge files are available through OpenAI file search to improve terminology without replacing source facts.")
        else:
            safe_caption("Project knowledge files are available as direct OpenRouter attachments when the active model supports them.")
    if converter_guidance:
        safe_caption("Saved converter guidance is active.")

    strict_mode = st.checkbox(
        "Strict source-grounded mode",
        value=bool(st.session_state.get(CONVERTER_STRICT_MODE_KEY, True)),
        key=CONVERTER_STRICT_MODE_KEY,
    )
    safe_caption("When enabled, unsupported wording stays empty instead of being expanded or guessed.")

    allow_web_research = st.checkbox("Allow web research in converter workflow", value=False, key="contractor_converter_web_research")
    locked_fields = st.multiselect(
        "Lock fields before reconversion or refinement",
        LOCKABLE_CONVERTER_FIELDS,
        default=st.session_state.get(CONVERTER_LOCKED_FIELDS_KEY, ["Date", "Site_Name", "District"]),
        key=CONVERTER_LOCKED_FIELDS_KEY,
    )

    action_columns = safe_columns(4, gap="large")
    with action_columns[0]:
        transcribe_clicked = st.button("Transcribe voice notes into source text")
    with action_columns[1]:
        convert_clicked = st.button(f"Convert with {provider_name}")
    with action_columns[2]:
        local_parse_clicked = st.button("Use local parser")
    with action_columns[3]:
        clear_clicked = st.button("Clear converted result")

    if transcribe_clicked:
        try:
            if not audio_files:
                raise ValueError("Upload one or more voice notes before requesting transcription.")
            api_key = load_ai_api_key(active_provider)
            if not api_key:
                raise ValueError(f"{provider_name} API key is required for voice transcription.")
            sdk_ready, sdk_error = openai_sdk_ready()
            if not sdk_ready:
                raise ValueError(f"OpenAI-compatible SDK is not installed in the active Streamlit environment. {sdk_error}")
            from services.media_service import request_transcription_with_openai

            with safe_spinner(f"Transcribing voice notes with {provider_name}..."):
                transcript = request_transcription_with_openai(
                    audio_files,
                    api_key=api_key,
                    discipline=discipline,
                    provider=active_provider,
                )
        except Exception as exc:
            st.warning(f"Voice transcription failed: {exc}")
            record_runtime_issue("converter", "Voice transcription failed.", details=str(exc))
        else:
            existing_text = str(st.session_state.get("contractor_report_text", "") or "").strip()
            merged_text = f"{existing_text}\n\n{transcript}".strip() if existing_text else transcript
            st.session_state["contractor_report_text"] = merged_text
            st.success("Voice notes were transcribed and appended to the contractor report text.")
            safe_rerun()

    if convert_clicked:
        try:
            validation_errors = validate_conversion_source_inputs(raw_report_text, supporting_files)
            if validation_errors:
                raise ValueError(" ".join(validation_errors))
            api_key = load_ai_api_key(active_provider)
            if not api_key:
                raise ValueError(f"{provider_name} API key is required for conversion.")
            sdk_ready, sdk_error = openai_sdk_ready()
            if not sdk_ready:
                raise ValueError(f"OpenAI-compatible SDK is not installed in the active Streamlit environment. {sdk_error}")

            knowledge_vector_store_id = ""
            if knowledge_files and provider_supports_openai_responses_tools(active_provider):
                with safe_spinner("Indexing project knowledge files..."):
                    knowledge_vector_store_id, _ = ensure_knowledge_vector_store(
                        knowledge_files,
                        api_key=api_key,
                        provider=active_provider,
                    )

            previous_rows = st.session_state.get(PARSED_CONTRACTOR_REPORTS_KEY, [])
            with safe_spinner(f"Converting contractor inputs with {provider_name}..."):
                parsed_rows, research_sources = request_structured_reports_with_openai(
                    str(raw_report_text or "").strip(),
                    api_key=api_key,
                    model=default_ai_model(active_provider),
                    discipline=discipline,
                    allow_web_research=allow_web_research,
                    strict_source_grounded=strict_mode,
                    supporting_files=supporting_files + ((knowledge_files or []) if active_provider == PROVIDER_OPENROUTER else []),
                    knowledge_vector_store_id=knowledge_vector_store_id,
                    persistent_guidance=converter_guidance,
                    provider=active_provider,
                )
            parsed_rows = apply_field_locks(previous_rows, parsed_rows, locked_fields=locked_fields)
            change_summary = summarize_row_changes(previous_rows, parsed_rows) if previous_rows else []
        except Exception as exc:
            st.warning(f"Conversion failed: {exc}")
            record_runtime_issue("converter", f"{provider_name} conversion failed.", details=str(exc))
        else:
            st.session_state[CONVERTER_CHANGE_SUMMARY_KEY] = change_summary
            persist_parsed_rows(parsed_rows, source_label=provider_name, reset_chat=True)
            if research_sources:
                st.session_state[CONTRACTOR_CHAT_MESSAGES_KEY][0]["content"] += " External or knowledge-base sources were used where helpful."
                st.session_state[CONTRACTOR_CHAT_MESSAGES_KEY][0]["sources"] = research_sources
            st.success(f"{provider_name} produced {len(parsed_rows)} structured row(s).")
            safe_rerun()

    if local_parse_clicked:
        try:
            validation_errors = validate_conversion_source_inputs(raw_report_text, [])
            if validation_errors:
                raise ValueError(" ".join(validation_errors))
            previous_rows = st.session_state.get(PARSED_CONTRACTOR_REPORTS_KEY, [])
            parsed_rows = structured_report_rows(clean_and_structure_report(raw_report_text))
            parsed_rows = apply_field_locks(previous_rows, parsed_rows, locked_fields=locked_fields)
            st.session_state[CONVERTER_CHANGE_SUMMARY_KEY] = summarize_row_changes(previous_rows, parsed_rows) if previous_rows else []
        except Exception as exc:
            st.warning(f"Unable to structure report locally: {exc}")
        else:
            persist_parsed_rows(parsed_rows, source_label="Local parser", reset_chat=True)
            st.success(f"Local parser produced {len(parsed_rows)} structured row(s).")
            safe_rerun()

    if clear_clicked:
        clear_parsed_rows()
        safe_rerun()

    parsed_rows = st.session_state.get(PARSED_CONTRACTOR_REPORTS_KEY, [])
    if not parsed_rows:
        safe_markdown("---")
        return

    render_subsection("Review Converted Rows", "Review, edit, and lock critical fields before appending to Google Sheets.")
    change_summary = st.session_state.get(CONVERTER_CHANGE_SUMMARY_KEY, [])
    if isinstance(change_summary, list) and change_summary:
        render_change_summary(change_summary)
    parsed_df = structured_rows_to_dataframe(parsed_rows)
    edited_df = safe_data_editor(parsed_df, width="stretch", hide_index=True, key="parsed_contractor_reports_editor")
    edited_rows = structured_rows_from_dataframe(edited_df)
    st.session_state[PARSED_CONTRACTOR_REPORTS_KEY] = edited_rows
    st.session_state["structured_report_data"] = edited_rows

    render_subsection("Refinement", "Use typed, recorded, or uploaded instructions to improve the converted rows without leaving the workflow.")
    recorded_refinement_audio = safe_audio_input(
        "Record refinement instruction",
        key="contractor_refinement_audio_recording",
        help="Record a microphone instruction and apply it directly to the converted rows.",
    )
    if recorded_refinement_audio:
        safe_caption(f"Recorded refinement audio ready: {getattr(recorded_refinement_audio, 'name', 'voice-note.wav')}")
        safe_audio(recorded_refinement_audio, format=getattr(recorded_refinement_audio, 'type', 'audio/wav'))

    refinement_supporting_files = list(
        safe_file_uploader(
            "Add refinement images or extra files (optional)",
            accept_multiple_files=True,
            type=CONTRACTOR_SUPPORTING_FILE_TYPES,
            key="contractor_refinement_supporting_files",
        )
        or []
    )
    refinement_audio_files = list(
        safe_file_uploader(
            "Add refinement voice notes (optional)",
            accept_multiple_files=True,
            type=AUDIO_FILE_TYPES,
            key="contractor_refinement_audio_files",
        )
        or []
    )
    if refinement_supporting_files:
        safe_caption(f"Refinement files ready: {', '.join(file.name for file in refinement_supporting_files)}")
    if refinement_audio_files:
        safe_caption(f"Refinement voice notes ready: {', '.join(file.name for file in refinement_audio_files)}")

    refinement_messages = st.session_state.setdefault(CONTRACTOR_CHAT_MESSAGES_KEY, [])
    for message in refinement_messages:
        render_contractor_chat_message(message)

    reset_chat_col, append_col = safe_columns(2, gap="large")
    with reset_chat_col:
        if st.button("Reset refinement chat"):
            reset_contractor_chat(edited_rows, source_label="Current converter")
            safe_rerun()
    with append_col:
        if st.button("Append converted rows to Google Sheet"):
            validation_errors = validate_structured_rows_for_sheet(edited_rows)
            if validation_errors:
                for error in validation_errors:
                    st.warning(error)
            else:
                try:
                    append_rows_to_sheet(rows_for_sheet_append(edited_rows))
                    clear_cached_sheet_data()
                except Exception as exc:
                    st.error(f"Failed to append converted rows to Google Sheet: {exc}")
                    record_runtime_issue("converter", "Failed to append converted rows to Google Sheet.", details=str(exc))
                else:
                    st.success(f"Added {len(edited_rows)} row(s) to Google Sheet.")
                    safe_rerun()

    refinement_prompt = safe_chat_input(
        "Tell the converter what to improve in the structured consultant report.",
        key="contractor_refinement_chat_input",
    )
    apply_voice_refinement = st.button("Apply voice refinement")
    voice_refinement_inputs = list(refinement_audio_files)
    if apply_voice_refinement and recorded_refinement_audio:
        voice_refinement_inputs.append(recorded_refinement_audio)

    if refinement_prompt or apply_voice_refinement:
        try:
            validation_errors = validate_refinement_request(
                str(refinement_prompt or "").strip(),
                has_voice_instruction=bool(voice_refinement_inputs),
                has_supporting_files=bool(supporting_files or refinement_supporting_files),
                raw_report_text=raw_report_text,
            )
            if validation_errors:
                raise ValueError(" ".join(validation_errors))
            api_key = load_ai_api_key(active_provider)
            if not api_key:
                raise ValueError(f"{provider_name} API key is required for refinement.")
            sdk_ready, sdk_error = openai_sdk_ready()
            if not sdk_ready:
                raise ValueError(f"OpenAI-compatible SDK is not installed in the active Streamlit environment. {sdk_error}")

            refinement_feedback, refinement_files = prepare_refinement_inputs(
                str(refinement_prompt or "").strip(),
                base_supporting_files=supporting_files,
                refinement_supporting_files=refinement_supporting_files,
                refinement_audio_files=voice_refinement_inputs,
                api_key=api_key,
                discipline=discipline,
                provider=active_provider,
            )
            if active_provider == PROVIDER_OPENROUTER and knowledge_files:
                refinement_files.extend(knowledge_files)

            knowledge_vector_store_id = ""
            if knowledge_files and provider_supports_openai_responses_tools(active_provider):
                with safe_spinner("Refreshing project knowledge files..."):
                    knowledge_vector_store_id, _ = ensure_knowledge_vector_store(
                        knowledge_files,
                        api_key=api_key,
                        provider=active_provider,
                    )

            previous_rows = list(edited_rows)
            with safe_spinner(f"Applying refinement with {provider_name}..."):
                assistant_message, refined_rows, research_sources = request_refined_structured_reports_with_openai(
                    str(raw_report_text or "").strip(),
                    api_key=api_key,
                    model=default_ai_model(active_provider),
                    discipline=discipline,
                    current_rows=edited_rows,
                    conversation=refinement_messages,
                    latest_feedback=refinement_feedback,
                    allow_web_research=allow_web_research,
                    strict_source_grounded=strict_mode,
                    supporting_files=refinement_files,
                    knowledge_vector_store_id=knowledge_vector_store_id,
                    persistent_guidance=converter_guidance,
                    provider=active_provider,
                )
            refined_rows = apply_field_locks(previous_rows, refined_rows, locked_fields=locked_fields)
            st.session_state[CONVERTER_CHANGE_SUMMARY_KEY] = summarize_row_changes(previous_rows, refined_rows)
        except Exception as exc:
            st.warning(f"Refinement failed: {exc}")
            record_runtime_issue("converter", f"{provider_name} refinement failed.", details=str(exc))
        else:
            user_message = refinement_request_preview(
                str(refinement_prompt or "").strip(),
                include_voice_instruction=bool(voice_refinement_inputs),
            )
            append_contractor_chat_message("user", user_message)
            append_contractor_chat_message("assistant", assistant_message, sources=research_sources)
            persist_parsed_rows(refined_rows, source_label=provider_name, reset_chat=False)
            st.success("Converted rows updated.")
            safe_rerun()

    safe_markdown("---")
