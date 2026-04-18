from __future__ import annotations

import os

import streamlit as st

from core.session_state import (
    AI_MEMORY_FILE as CORE_AI_MEMORY_FILE,
    AI_IMAGE_CAPTIONS_KEY,
    AI_MEMORY_STATE_KEY,
    ANALYST_FILE_TYPES,
    AUDIO_FILE_TYPES,
    CONTRACTOR_CHAT_MESSAGES_KEY,
    CONTRACTOR_SUPPORTING_FILE_TYPES,
    GUIDANCE_TARGETS,
    OPENAI_API_KEY_SESSION_KEY,
    OPENAI_CHAT_MESSAGES_KEY,
    OPENAI_MODEL_SESSION_KEY,
    OPENAI_PREVIOUS_RESPONSE_ID_KEY,
    PARSED_CONTRACTOR_REPORTS_KEY,
    PROJECT_KNOWLEDGE_FILE_TYPES,
    PROJECT_KNOWLEDGE_VECTOR_STORE_KEY,
    RESEARCH_ASSISTANT_AUDIO_KEY,
    RESEARCH_ASSISTANT_MESSAGES_KEY,
    RUNTIME_ISSUES_KEY,
    SELF_HEALING_ACTIONS,
    SELF_HEALING_AUDIO_KEY,
    SELF_HEALING_RESULT_KEY,
    SHEET_ANALYST_AUDIO_KEY,
    SHEET_ANALYST_RESULT_KEY,
    CONVERTER_CHANGE_SUMMARY_KEY,
    CONVERTER_LOCKED_FIELDS_KEY,
    CONVERTER_STRICT_MODE_KEY,
    LOCKABLE_CONVERTER_FIELDS,
    active_guidance_text as _active_guidance_text,
    clear_ai_audio_cache as _clear_ai_audio_cache,
    clear_openai_chat as _clear_openai_chat,
    clear_parsed_contractor_rows as _clear_parsed_contractor_rows,
    clear_photo_caption_cache as _clear_photo_caption_cache,
    clear_runtime_issues as _clear_runtime_issues,
    delete_saved_guidance_item as _delete_saved_guidance_item,
    save_maintenance_item as _save_maintenance_item,
    saved_guidance_items as _saved_guidance_items,
    maintenance_backlog_items as _maintenance_backlog_items,
    runtime_issue_items as _runtime_issue_items,
    record_runtime_issue as _record_runtime_issue,
    utc_timestamp as _utc_timestamp,
)
import core.session_state as session_state_module
from report import generate_reports
from report_structuring import REPORT_HEADERS, clean_and_structure_report
from services.converter_service import (
    apply_field_locks as _apply_field_locks,
    consultant_report_response_schema as _consultant_report_response_schema,
    consultant_report_row_schema as _consultant_report_row_schema,
    contractor_refinement_response_schema as _contractor_refinement_response_schema,
    conversation_transcript as _conversation_transcript,
    normalize_field_value as _normalize_field_value,
    normalize_structured_rows as _normalize_structured_rows,
    prepare_refinement_inputs as _prepare_refinement_inputs,
    refinement_request_preview as _refinement_request_preview,
    request_refined_structured_reports_with_openai as _request_refined_structured_reports_with_openai,
    request_structured_reports_with_openai as _request_structured_reports_with_openai,
    structured_report_rows as _structured_report_rows,
    structured_rows_from_dataframe as _structured_rows_from_dataframe,
    structured_rows_to_dataframe as _structured_rows_to_dataframe,
    structured_rows_to_sheet_rows as _structured_rows_to_sheet_rows,
    summarize_row_changes as _summarize_row_changes,
    validate_conversion_source_inputs as _validate_conversion_source_inputs,
    validate_refinement_request as _validate_refinement_request,
    validate_structured_rows_for_sheet as _validate_structured_rows_for_sheet,
)
from services.media_service import (
    build_review_row_mapping as _build_review_row_mapping,
    data_url_for_bytes as _data_url_for_bytes,
    generate_ai_photo_captions_for_reports as _generate_ai_photo_captions_for_reports,
    has_image_files as _has_image_files,
    image_bytes_signature as _image_bytes_signature,
    image_mime_type_from_bytes as _image_mime_type_from_bytes,
    photo_caption_cache as _photo_caption_cache,
    photo_caption_response_schema as _photo_caption_response_schema,
    report_row_context_text as _report_row_context_text,
    request_image_captions_with_openai as _request_image_captions_with_openai,
    request_text_to_speech_with_openai as _request_text_to_speech_with_openai,
    request_transcription_with_openai as _request_transcription_with_openai,
    uploaded_file_bytes as _uploaded_file_bytes,
    uploaded_file_mime_type as _uploaded_file_mime_type,
    uploaded_file_name as _uploaded_file_name,
    uploaded_file_names as _uploaded_file_names,
    uploaded_file_to_response_part as _uploaded_file_to_response_part,
    uploaded_files_signature as _uploaded_files_signature,
    uploaded_files_to_response_input as _uploaded_files_to_response_input,
)
from services.openai_client import (
    DEFAULT_OPENAI_MODEL,
    RESEARCH_OPENAI_MODEL,
    TRANSCRIPTION_OPENAI_MODEL,
    TTS_OPENAI_MODEL,
    converter_model as _converter_model,
    default_openai_model as _default_openai_model,
    extract_openai_output_text as _extract_openai_output_text,
    load_openai_api_key as _load_openai_api_key,
    openai_sdk_ready as _openai_sdk_ready,
    request_openai_reply as _request_openai_reply,
    streamlit_secret as _streamlit_secret,
    tool_enabled_model as _tool_enabled_model,
)
from services.research_service import (
    converter_response_options as _converter_response_options,
    ensure_knowledge_vector_store as _ensure_knowledge_vector_store,
    extract_container_artifacts as _extract_container_artifacts,
    extract_file_search_sources as _extract_file_search_sources,
    extract_response_sources as _extract_response_sources,
    extract_web_search_sources as _extract_web_search_sources,
    knowledge_vector_store_cache as _knowledge_vector_store_cache,
    request_research_assistant_reply as _request_research_assistant_reply,
    request_spreadsheet_analysis_with_openai as _request_spreadsheet_analysis_with_openai,
)
from services.self_healing_service import (
    request_self_healing_analysis_with_openai as _request_self_healing_analysis_with_openai,
)
from sheets import append_rows_to_sheet, get_sheet_data, get_unique_sites_and_dates, load_offline_cache
from streamlit_ui.advanced_ai_workspace import (
    render_advanced_ai_workspace,
    render_project_knowledge_base_panel,
)
from streamlit_ui.diagnostics_workspace import (
    apply_self_healing_actions as _apply_self_healing_actions,
    render_diagnostics_workspace,
)
import streamlit_ui.reporting_workspace as reporting_workspace_module
from streamlit_ui.reporting_workspace import load_sheet_context as _load_sheet_context
from streamlit_ui.reporting_workspace import normalized_review_rows as _normalized_review_rows
from streamlit_ui.reporting_workspace import render_reporting_workspace
from streamlit_ui.reporting_workspace import rows_to_structured_data as _rows_to_structured_data
from streamlit_ui.converter_workspace import (
    append_contractor_chat_message as _append_contractor_chat_message,
    render_change_summary as _render_change_summary,
    render_contractor_chat_message as _render_contractor_chat_message,
    render_converter_workspace,
    reset_contractor_chat as _reset_contractor_chat,
)
from streamlit_ui.theme import apply_professional_theme, render_app_header
from ui import render_workwatch_header, set_background
from ui_hero import render_hero

st.set_page_config(page_title="IBC Reporting Platform", layout="wide")

AI_MEMORY_FILE = CORE_AI_MEMORY_FILE


def _streamlit_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default) or "").strip()
    except Exception:
        return str(default or "").strip()


def _load_openai_api_key() -> str:
    session_key = str(st.session_state.get(OPENAI_API_KEY_SESSION_KEY, "") or "").strip()
    if session_key:
        return session_key
    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key
    return _streamlit_secret("OPENAI_API_KEY")


def _default_openai_model() -> str:
    session_model = str(st.session_state.get(OPENAI_MODEL_SESSION_KEY, "") or "").strip()
    if session_model:
        return session_model
    env_model = os.environ.get("OPENAI_MODEL", "").strip()
    if env_model:
        return env_model
    secret_model = _streamlit_secret("OPENAI_MODEL")
    if secret_model:
        return secret_model
    return DEFAULT_OPENAI_MODEL


def _save_saved_guidance_item(instruction: str, *, target: str, title: str = "") -> dict[str, object]:
    session_state_module.AI_MEMORY_FILE = AI_MEMORY_FILE
    return session_state_module.save_saved_guidance_item(instruction, target=target, title=title)


def _active_guidance_text(*targets: str) -> str:
    session_state_module.AI_MEMORY_FILE = AI_MEMORY_FILE
    return session_state_module.active_guidance_text(*targets)


def _clear_parsed_contractor_rows() -> None:
    st.session_state.pop(PARSED_CONTRACTOR_REPORTS_KEY, None)
    st.session_state.pop(CONTRACTOR_CHAT_MESSAGES_KEY, None)
    st.session_state.pop(CONVERTER_CHANGE_SUMMARY_KEY, None)


def _prepare_refinement_inputs(
    latest_feedback: str,
    *,
    base_supporting_files: list[object] | None = None,
    refinement_supporting_files: list[object] | None = None,
    refinement_audio_files: list[object] | None = None,
    api_key: str = "",
    discipline: str = "",
) -> tuple[str, list[object]]:
    combined_files = list(base_supporting_files or [])
    if refinement_supporting_files:
        combined_files.extend(refinement_supporting_files)

    feedback = str(latest_feedback or "").strip()
    if not refinement_audio_files:
        return feedback, combined_files
    if not api_key:
        raise ValueError("OpenAI API key is required for refinement voice notes.")

    transcript = _request_transcription_with_openai(
        list(refinement_audio_files),
        api_key=api_key,
        discipline=discipline,
    ).strip()
    if not transcript:
        return feedback, combined_files

    transcript_block = f"Additional refinement voice notes:\n{transcript}"
    feedback = f"{feedback}\n\n{transcript_block}".strip() if feedback else transcript_block
    return feedback, combined_files


def _generate_reports_with_gallery_options(
    review_rows: list[list[str]],
    images: dict,
    discipline: str,
    img_width_mm: int,
    img_height_mm: int,
    spacing_mm: int,
    *,
    add_border: bool,
    show_photo_placeholders: bool,
    image_caption_mapping: dict | None = None,
):
    base_args = (
        review_rows,
        images,
        discipline,
        img_width_mm,
        img_height_mm,
        spacing_mm,
    )
    base_kwargs = {"img_per_row": 2, "add_border": add_border}
    try:
        return generate_reports(
            *base_args,
            **base_kwargs,
            show_photo_placeholders=show_photo_placeholders,
            image_caption_mapping=image_caption_mapping,
        )
    except TypeError as exc:
        if "show_photo_placeholders" not in str(exc) and "image_caption_mapping" not in str(exc):
            raise
        return generate_reports(*base_args, **base_kwargs)


def run_app():
    """Render the Streamlit interface."""
    apply_professional_theme()
    render_app_header()

    project_knowledge_files = render_project_knowledge_base_panel()
    render_reporting_workspace(
        record_runtime_issue=_record_runtime_issue,
        active_guidance_text=_active_guidance_text,
        get_sheet_data_fn=get_sheet_data,
        get_unique_sites_and_dates_fn=get_unique_sites_and_dates,
        load_offline_cache_fn=load_offline_cache,
        append_rows_to_sheet_fn=append_rows_to_sheet,
        generate_reports_fn=generate_reports,
    )
    discipline = str(st.session_state.get("discipline_radio", "Civil") or "Civil")
    render_converter_workspace(
        discipline,
        knowledge_files=project_knowledge_files,
        record_runtime_issue=_record_runtime_issue,
        active_guidance_text=_active_guidance_text,
    )
    render_advanced_ai_workspace(
        discipline,
        knowledge_files=project_knowledge_files,
        record_runtime_issue=_record_runtime_issue,
        active_guidance_text=_active_guidance_text,
    )
    render_diagnostics_workspace()


if __name__ == "__main__":
    run_app()
