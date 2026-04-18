from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from config import BASE_DIR
from services.local_state_store import (
    default_ai_memory_state,
    load_ai_memory_state,
    persist_ai_memory_state as persist_ai_memory_state_to_disk,
)

OPENAI_API_KEY_SESSION_KEY = "openai_api_key"
OPENAI_CHAT_MESSAGES_KEY = "openai_chat_messages"
OPENAI_PREVIOUS_RESPONSE_ID_KEY = "openai_previous_response_id"
OPENAI_MODEL_SESSION_KEY = "openai_model"
PARSED_CONTRACTOR_REPORTS_KEY = "parsed_contractor_reports"
CONTRACTOR_CHAT_MESSAGES_KEY = "contractor_converter_chat_messages"
PROJECT_KNOWLEDGE_VECTOR_STORE_KEY = "project_knowledge_vector_store"
RESEARCH_ASSISTANT_MESSAGES_KEY = "research_assistant_messages"
RESEARCH_ASSISTANT_AUDIO_KEY = "research_assistant_audio"
SHEET_ANALYST_RESULT_KEY = "sheet_analyst_result"
SHEET_ANALYST_AUDIO_KEY = "sheet_analyst_audio"
AI_MEMORY_STATE_KEY = "ai_memory_state"
AI_IMAGE_CAPTIONS_KEY = "ai_image_captions"
SELF_HEALING_RESULT_KEY = "self_healing_result"
RUNTIME_ISSUES_KEY = "runtime_issues"
SELF_HEALING_AUDIO_KEY = "self_healing_audio"
CONVERTER_CHANGE_SUMMARY_KEY = "converter_change_summary"
CONVERTER_LOCKED_FIELDS_KEY = "converter_locked_fields"
CONVERTER_STRICT_MODE_KEY = "converter_strict_mode"

AI_MEMORY_FILE = Path(os.environ.get("AI_MEMORY_FILE", str(BASE_DIR / "ai_memory_store.json")))
RUNTIME_ISSUE_LIMIT = 25
MAINTENANCE_ITEM_LIMIT = 50
GUIDANCE_TARGETS = ["general", "converter", "captions", "research", "healing"]
LOCKABLE_CONVERTER_FIELDS = [
    "Date",
    "Site_Name",
    "District",
    "Work_Executed",
    "Comment_on_work",
    "challenges",
]
SELF_HEALING_ACTIONS = {
    "clear_openai_chat": "Clear general assistant chat state",
    "clear_converter_state": "Clear contractor converter rows and chat",
    "clear_uploaded_images": "Clear uploaded report photos",
    "clear_photo_captions": "Clear cached AI photo captions",
    "clear_sheet_cache": "Clear cached sheet data",
    "reset_knowledge_base": "Reset knowledge-base search cache",
    "clear_audio_cache": "Clear generated audio",
    "clear_runtime_issues": "Clear runtime issue log",
}

PROJECT_KNOWLEDGE_FILE_TYPES = ["pdf", "txt", "md", "doc", "docx", "csv", "json", "xml"]
CONTRACTOR_SUPPORTING_FILE_TYPES = [
    "pdf",
    "txt",
    "md",
    "doc",
    "docx",
    "csv",
    "json",
    "xml",
    "xlsx",
    "xls",
    "png",
    "jpg",
    "jpeg",
    "webp",
]
AUDIO_FILE_TYPES = ["mp3", "mp4", "mpeg", "mpga", "m4a", "wav", "webm"]
ANALYST_FILE_TYPES = ["csv", "xlsx", "xls", "json", "pdf"]


def utc_timestamp() -> str:
    """Return an ISO timestamp in UTC."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ai_memory_state() -> dict[str, object]:
    """Return the cached AI-memory store from session state."""
    state = st.session_state.get(AI_MEMORY_STATE_KEY)
    if isinstance(state, dict):
        return state
    loaded = load_ai_memory_state(AI_MEMORY_FILE)
    st.session_state[AI_MEMORY_STATE_KEY] = loaded
    return loaded


def persist_ai_memory_state() -> bool:
    """Persist the current AI-memory store."""
    return persist_ai_memory_state_to_disk(AI_MEMORY_FILE, ai_memory_state())


def saved_guidance_items() -> list[dict[str, object]]:
    items = ai_memory_state().get("saved_guidance", [])
    return [item for item in items if isinstance(item, dict)]


def maintenance_backlog_items() -> list[dict[str, object]]:
    items = ai_memory_state().get("maintenance_backlog", [])
    return [item for item in items if isinstance(item, dict)]


def runtime_issue_items() -> list[dict[str, object]]:
    items = ai_memory_state().get("runtime_issues", [])
    return [item for item in items if isinstance(item, dict)]


def save_saved_guidance_item(instruction: str, *, target: str, title: str = "") -> dict[str, object]:
    """Persist one reusable AI instruction."""
    cleaned_instruction = str(instruction or "").strip()
    if not cleaned_instruction:
        raise ValueError("Instruction is required.")

    normalized_target = str(target or "general").strip().lower()
    if normalized_target not in GUIDANCE_TARGETS:
        normalized_target = "general"

    item = {
        "id": utc_timestamp().replace(":", "-"),
        "title": str(title or cleaned_instruction.splitlines()[0][:80]).strip() or "Saved instruction",
        "target": normalized_target,
        "instruction": cleaned_instruction,
        "created_at": utc_timestamp(),
    }
    state = ai_memory_state()
    items = saved_guidance_items()
    items.insert(0, item)
    state["saved_guidance"] = items[:100]
    persist_ai_memory_state()
    return item


def delete_saved_guidance_item(item_id: str) -> None:
    """Delete one saved AI instruction."""
    state = ai_memory_state()
    remaining = [
        item
        for item in saved_guidance_items()
        if str(item.get("id", "") or "").strip() != str(item_id or "").strip()
    ]
    state["saved_guidance"] = remaining
    persist_ai_memory_state()


def active_guidance_text(*targets: str) -> str:
    """Return the active reusable instructions for the requested targets."""
    normalized_targets = {str(target or "").strip().lower() for target in targets if target}
    normalized_targets.add("general")
    lines: list[str] = []
    for item in reversed(saved_guidance_items()):
        target = str(item.get("target", "general") or "general").strip().lower()
        if target not in normalized_targets:
            continue
        instruction = str(item.get("instruction", "") or "").strip()
        if instruction:
            lines.append(f"- {instruction}")
    return "\n".join(lines).strip()


def save_maintenance_item(title: str, details: str, *, source: str = "manual") -> dict[str, object]:
    """Persist a maintenance/backlog entry."""
    cleaned_title = str(title or "").strip()
    cleaned_details = str(details or "").strip()
    if not cleaned_title and not cleaned_details:
        raise ValueError("Maintenance item details are required.")

    item = {
        "id": utc_timestamp().replace(":", "-"),
        "title": cleaned_title or "Maintenance item",
        "details": cleaned_details,
        "source": str(source or "manual").strip(),
        "status": "open",
        "created_at": utc_timestamp(),
    }
    state = ai_memory_state()
    items = maintenance_backlog_items()
    items.insert(0, item)
    state["maintenance_backlog"] = items[:MAINTENANCE_ITEM_LIMIT]
    persist_ai_memory_state()
    return item


def record_runtime_issue(area: str, message: str, *, details: str = "") -> None:
    """Store one runtime issue for diagnostics."""
    state = ai_memory_state()
    issues = runtime_issue_items()
    issues.insert(
        0,
        {
            "area": str(area or "app").strip(),
            "message": str(message or "").strip(),
            "details": str(details or "").strip(),
            "created_at": utc_timestamp(),
        },
    )
    state["runtime_issues"] = issues[:RUNTIME_ISSUE_LIMIT]
    persist_ai_memory_state()


def clear_runtime_issues() -> None:
    """Clear persisted runtime issues."""
    state = ai_memory_state()
    state["runtime_issues"] = []
    persist_ai_memory_state()


def clear_openai_chat() -> None:
    """Reset the general assistant chat transcript and threading state."""
    st.session_state[OPENAI_CHAT_MESSAGES_KEY] = []
    st.session_state.pop(OPENAI_PREVIOUS_RESPONSE_ID_KEY, None)


def persist_parsed_contractor_rows(rows: list[dict[str, str]], *, reset_chat: bool = False) -> None:
    """Persist contractor converter rows in session state."""
    st.session_state[PARSED_CONTRACTOR_REPORTS_KEY] = list(rows)
    st.session_state["structured_report_data"] = list(rows)
    st.session_state["_structured_origin"] = "manual"
    if reset_chat:
        st.session_state[CONTRACTOR_CHAT_MESSAGES_KEY] = []


def clear_parsed_contractor_rows() -> None:
    """Remove parsed contractor rows and related converter state."""
    st.session_state.pop(PARSED_CONTRACTOR_REPORTS_KEY, None)
    st.session_state.pop(CONTRACTOR_CHAT_MESSAGES_KEY, None)
    st.session_state.pop(CONVERTER_CHANGE_SUMMARY_KEY, None)


def clear_photo_caption_cache() -> None:
    """Remove cached AI image captions."""
    st.session_state.pop(AI_IMAGE_CAPTIONS_KEY, None)


def clear_ai_audio_cache() -> None:
    """Remove cached AI audio outputs."""
    st.session_state.pop(RESEARCH_ASSISTANT_AUDIO_KEY, None)
    st.session_state.pop(SHEET_ANALYST_AUDIO_KEY, None)
    st.session_state.pop(SELF_HEALING_AUDIO_KEY, None)

