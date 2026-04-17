from __future__ import annotations

import base64
import hashlib
import io
import json
import mimetypes
import os
import textwrap
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from config import BASE_DIR
from PIL import Image
from sheets import (
    CACHE_FILE,
    append_rows_to_sheet,
    get_sheet_data,
    get_unique_sites_and_dates,
    load_offline_cache,
)
from report import generate_reports
from report_structuring import REPORT_HEADERS, clean_and_structure_report
from ui import render_workwatch_header, set_background
from ui_hero import render_hero

st.set_page_config(page_title="WorkWatch - Site Intelligence", layout="wide")

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
RESEARCH_OPENAI_MODEL = "gpt-5.4-mini"
TRANSCRIPTION_OPENAI_MODEL = "gpt-4o-transcribe"
TTS_OPENAI_MODEL = "gpt-4o-mini-tts"
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

AI_MEMORY_FILE = Path(os.environ.get("AI_MEMORY_FILE", str(BASE_DIR / "ai_memory_store.json")))
RUNTIME_ISSUE_LIMIT = 25
MAINTENANCE_ITEM_LIMIT = 50
GUIDANCE_TARGETS = ["general", "converter", "captions", "research", "healing"]
SELF_HEALING_ACTIONS = {
    "clear_openai_chat": "Clear ChatGPT chat state",
    "clear_converter_state": "Clear converter rows and chat",
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


def _safe_columns(*args, **kwargs):
    """Call st.columns falling back to positional-only call for stubs."""
    columns_fn = getattr(st, "columns", None)
    if not callable(columns_fn):
        return (nullcontext(), nullcontext())

    requested_count = None
    if args:
        first_arg = args[0]
        if isinstance(first_arg, int):
            requested_count = first_arg
        elif isinstance(first_arg, (list, tuple)):
            requested_count = len(first_arg)

    try:
        columns = columns_fn(*args, **kwargs)
    except TypeError:
        columns = columns_fn(*args)

    if requested_count is None:
        return columns

    columns_list = list(columns)
    while len(columns_list) < requested_count:
        columns_list.append(nullcontext())
    return tuple(columns_list)


def _safe_markdown(markdown: str, **kwargs) -> None:
    """Call st.markdown when available (tests provide a stub without it)."""
    markdown_fn = getattr(st, "markdown", None)
    if callable(markdown_fn):
        markdown_fn(markdown, **kwargs)


def _safe_checkbox(label: str, *, value=False, key=None):
    """Return st.checkbox value or default when unavailable."""
    checkbox_fn = getattr(st, "checkbox", None)
    if callable(checkbox_fn):
        return checkbox_fn(label, value=value, key=key)
    return value


def _safe_caption(text: str) -> None:
    """Call st.caption when available."""
    caption_fn = getattr(st, "caption", None)
    if callable(caption_fn):
        caption_fn(text)


def _safe_data_editor(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """Return data editor result, or input frame when editor is unavailable."""
    editor_fn = getattr(st, "data_editor", None)
    if not callable(editor_fn):
        return df

    try:
        edited = editor_fn(df, **kwargs)
    except TypeError:
        edited = editor_fn(df)

    if isinstance(edited, pd.DataFrame):
        return edited
    return df


def _safe_image(images, **kwargs) -> None:
    """Call st.image when available."""
    image_fn = getattr(st, "image", None)
    if callable(image_fn):
        image_fn(images, **kwargs)


def _safe_text_input(label: str, value: str = "", **kwargs) -> str:
    """Call st.text_input when available, falling back to the default value."""
    text_input_fn = getattr(st, "text_input", None)
    if callable(text_input_fn):
        try:
            return text_input_fn(label, value=value, **kwargs)
        except TypeError:
            return text_input_fn(label, value)
    return value


def _safe_text_area(label: str, value: str = "", **kwargs) -> str:
    """Call st.text_area when available, falling back to the default value."""
    text_area_fn = getattr(st, "text_area", None)
    if callable(text_area_fn):
        try:
            return text_area_fn(label, value=value, **kwargs)
        except TypeError:
            return text_area_fn(label, value)
    return value


def _safe_selectbox(label: str, options: list[str], index: int = 0, **kwargs):
    """Call st.selectbox when available, otherwise return the indexed option."""
    selectbox_fn = getattr(st, "selectbox", None)
    if callable(selectbox_fn):
        try:
            return selectbox_fn(label, options, index=index, **kwargs)
        except TypeError:
            return selectbox_fn(label, options, index)
    if not options:
        return None
    safe_index = max(0, min(index, len(options) - 1))
    return options[safe_index]


def _safe_file_uploader(label: str, **kwargs):
    """Call st.file_uploader when available, otherwise return an empty upload result."""
    uploader_fn = getattr(st, "file_uploader", None)
    if callable(uploader_fn):
        return uploader_fn(label, **kwargs)
    if kwargs.get("accept_multiple_files"):
        return []
    return None


def _safe_write(value: object) -> None:
    """Call st.write when available."""
    write_fn = getattr(st, "write", None)
    if callable(write_fn):
        write_fn(value)


def _safe_expander(label: str, *, expanded: bool = False):
    """Return st.expander context or a nullcontext fallback."""
    expander_fn = getattr(st, "expander", None)
    if callable(expander_fn):
        try:
            return expander_fn(label, expanded=expanded)
        except TypeError:
            return expander_fn(label)
    return nullcontext()


def _safe_chat_message(role: str):
    """Return st.chat_message context or a nullcontext fallback."""
    chat_message_fn = getattr(st, "chat_message", None)
    if callable(chat_message_fn):
        return chat_message_fn(role)
    return nullcontext()


def _safe_chat_input(prompt: str, **kwargs) -> str | None:
    """Return st.chat_input value or None when unavailable."""
    chat_input_fn = getattr(st, "chat_input", None)
    if callable(chat_input_fn):
        try:
            return chat_input_fn(prompt, **kwargs)
        except TypeError:
            return chat_input_fn(prompt)
    return None


def _safe_spinner(text: str):
    """Return st.spinner context or a nullcontext fallback."""
    spinner_fn = getattr(st, "spinner", None)
    if callable(spinner_fn):
        return spinner_fn(text)
    return nullcontext()


def _safe_audio(data, **kwargs) -> None:
    """Call st.audio when available."""
    audio_fn = getattr(st, "audio", None)
    if callable(audio_fn):
        audio_fn(data, **kwargs)


def _safe_audio_input(label: str, **kwargs):
    """Call st.audio_input when available, otherwise return None."""
    audio_input_fn = getattr(st, "audio_input", None)
    if callable(audio_input_fn):
        try:
            return audio_input_fn(label, **kwargs)
        except TypeError:
            return audio_input_fn(label)
    return None


def _utc_timestamp() -> str:
    """Return an ISO timestamp in UTC."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json_store(path: Path, default: dict[str, object]) -> dict[str, object]:
    """Load a small JSON store with graceful fallback."""
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                merged = dict(default)
                merged.update(payload)
                return merged
    except Exception:
        pass
    return dict(default)


def _save_json_store(path: Path, payload: dict[str, object]) -> bool:
    """Persist a small JSON store when the filesystem allows it."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2)
        return True
    except Exception:
        return False


def _default_ai_memory_state() -> dict[str, object]:
    """Return the initial structure for persisted AI memory."""
    return {
        "saved_guidance": [],
        "maintenance_backlog": [],
        "runtime_issues": [],
    }


def _ai_memory_state() -> dict[str, object]:
    """Return the current AI memory state from session or disk."""
    cached = st.session_state.get(AI_MEMORY_STATE_KEY)
    if isinstance(cached, dict):
        return cached

    state = _load_json_store(AI_MEMORY_FILE, _default_ai_memory_state())
    st.session_state[AI_MEMORY_STATE_KEY] = state
    return state


def _persist_ai_memory_state() -> bool:
    """Save the in-memory AI state to disk when possible."""
    state = _ai_memory_state()
    return _save_json_store(AI_MEMORY_FILE, state)


def _saved_guidance_items() -> list[dict[str, object]]:
    """Return saved reusable instructions."""
    items = _ai_memory_state().get("saved_guidance", [])
    return list(items) if isinstance(items, list) else []


def _maintenance_backlog_items() -> list[dict[str, object]]:
    """Return saved maintenance requests."""
    items = _ai_memory_state().get("maintenance_backlog", [])
    return list(items) if isinstance(items, list) else []


def _runtime_issue_items() -> list[dict[str, object]]:
    """Return recently recorded runtime issues."""
    session_items = st.session_state.get(RUNTIME_ISSUES_KEY)
    if isinstance(session_items, list):
        return list(session_items)

    persisted = _ai_memory_state().get("runtime_issues", [])
    items = list(persisted) if isinstance(persisted, list) else []
    st.session_state[RUNTIME_ISSUES_KEY] = items
    return items


def _save_saved_guidance_item(instruction: str, *, target: str, title: str = "") -> dict[str, object]:
    """Persist one reusable instruction for later AI workflows."""
    clean_instruction = str(instruction or "").strip()
    if not clean_instruction:
        raise ValueError("A reusable instruction is required before saving to AI memory.")

    clean_target = target if target in GUIDANCE_TARGETS else "general"
    item = {
        "id": hashlib.sha256(f"{clean_target}|{clean_instruction}".encode("utf-8")).hexdigest()[:12],
        "title": (title or clean_instruction[:80]).strip(),
        "instruction": clean_instruction,
        "target": clean_target,
        "enabled": True,
        "created_at": _utc_timestamp(),
    }

    state = _ai_memory_state()
    items = state.setdefault("saved_guidance", [])
    if not isinstance(items, list):
        items = []
        state["saved_guidance"] = items

    for existing in items:
        if isinstance(existing, dict) and existing.get("instruction") == clean_instruction and existing.get("target") == clean_target:
            existing["enabled"] = True
            existing["title"] = item["title"]
            existing["updated_at"] = _utc_timestamp()
            _persist_ai_memory_state()
            return existing

    items.append(item)
    _persist_ai_memory_state()
    return item


def _delete_saved_guidance_item(item_id: str) -> None:
    """Delete one reusable instruction by id."""
    state = _ai_memory_state()
    items = state.setdefault("saved_guidance", [])
    if isinstance(items, list):
        state["saved_guidance"] = [
            item for item in items if not isinstance(item, dict) or str(item.get("id", "")) != item_id
        ]
    _persist_ai_memory_state()


def _active_guidance_text(*targets: str) -> str:
    """Return enabled reusable instructions for the requested targets."""
    normalized_targets = set(targets) | {"general"}
    instructions: list[str] = []
    for item in _saved_guidance_items():
        if not isinstance(item, dict):
            continue
        if not bool(item.get("enabled", True)):
            continue
        target = str(item.get("target", "general") or "general")
        if target not in normalized_targets:
            continue
        instruction = str(item.get("instruction", "") or "").strip()
        if instruction:
            instructions.append(f"- {instruction}")
    return "\n".join(instructions).strip()


def _save_maintenance_item(title: str, details: str, *, source: str = "manual") -> dict[str, object]:
    """Persist one maintenance/backlog request."""
    clean_title = str(title or "").strip()
    clean_details = str(details or "").strip()
    if not clean_title and not clean_details:
        raise ValueError("A maintenance request needs a title or details.")

    entry = {
        "id": hashlib.sha256(f"{clean_title}|{clean_details}|{_utc_timestamp()}".encode("utf-8")).hexdigest()[:12],
        "title": clean_title or clean_details[:80],
        "details": clean_details,
        "source": source,
        "status": "open",
        "created_at": _utc_timestamp(),
    }

    state = _ai_memory_state()
    items = state.setdefault("maintenance_backlog", [])
    if not isinstance(items, list):
        items = []
        state["maintenance_backlog"] = items
    items.insert(0, entry)
    state["maintenance_backlog"] = items[:MAINTENANCE_ITEM_LIMIT]
    _persist_ai_memory_state()
    return entry


def _record_runtime_issue(area: str, message: str, *, details: str = "") -> None:
    """Store a recent runtime issue for the self-healing workspace."""
    entry = {
        "area": str(area or "app").strip(),
        "message": str(message or "").strip(),
        "details": str(details or "").strip(),
        "created_at": _utc_timestamp(),
    }
    if not entry["message"]:
        return

    issues = _runtime_issue_items()
    issues.insert(0, entry)
    trimmed = issues[:RUNTIME_ISSUE_LIMIT]
    st.session_state[RUNTIME_ISSUES_KEY] = trimmed

    state = _ai_memory_state()
    state["runtime_issues"] = trimmed
    _persist_ai_memory_state()


def _clear_runtime_issues() -> None:
    """Remove recorded runtime issues."""
    st.session_state[RUNTIME_ISSUES_KEY] = []
    state = _ai_memory_state()
    state["runtime_issues"] = []
    _persist_ai_memory_state()


def _streamlit_secret(name: str, default: str = "") -> str:
    """Read one Streamlit secret value without failing when secrets are unavailable."""
    try:
        secrets = getattr(st, "secrets", None)
        if secrets is None:
            return default
        if hasattr(secrets, "get"):
            value = secrets.get(name, default)
        elif name in secrets:
            value = secrets[name]
        else:
            value = default
    except Exception:
        return default

    if value is None:
        return default
    return str(value).strip()


def _load_openai_api_key() -> str:
    """Return the active OpenAI API key from session, env, or Streamlit secrets."""
    session_key = str(st.session_state.get(OPENAI_API_KEY_SESSION_KEY, "") or "").strip()
    if session_key:
        return session_key

    env_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if env_key:
        return env_key

    return _streamlit_secret("OPENAI_API_KEY")


def _default_openai_model() -> str:
    """Return the preferred chat model, allowing env or secrets overrides."""
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


def _openai_sdk_ready() -> tuple[bool, str]:
    """Check whether the OpenAI SDK can be imported."""
    try:
        from openai import OpenAI  # noqa: F401
    except ImportError as exc:
        return False, str(exc)
    return True, ""


def _uploaded_file_name(uploaded_file: object) -> str:
    """Return a best-effort filename for an uploaded file object."""
    name = str(getattr(uploaded_file, "name", "") or "").strip()
    return name or "upload.bin"


def _uploaded_file_mime_type(uploaded_file: object) -> str:
    """Return a MIME type for an uploaded file object."""
    explicit_type = str(getattr(uploaded_file, "type", "") or "").strip()
    if explicit_type:
        return explicit_type

    guessed_type, _ = mimetypes.guess_type(_uploaded_file_name(uploaded_file))
    return guessed_type or "application/octet-stream"


def _uploaded_file_bytes(uploaded_file: object) -> bytes:
    """Read uploaded file bytes without permanently moving the file pointer."""
    getvalue_fn = getattr(uploaded_file, "getvalue", None)
    if callable(getvalue_fn):
        data = getvalue_fn()
        return bytes(data or b"")

    read_fn = getattr(uploaded_file, "read", None)
    if not callable(read_fn):
        return b""

    tell_fn = getattr(uploaded_file, "tell", None)
    seek_fn = getattr(uploaded_file, "seek", None)
    position = None
    if callable(tell_fn):
        try:
            position = tell_fn()
        except Exception:
            position = None

    data = read_fn()
    if callable(seek_fn) and position is not None:
        try:
            seek_fn(position)
        except Exception:
            pass

    return bytes(data or b"")


def _data_url_for_bytes(data: bytes, *, mime_type: str) -> str:
    """Return a data URL for binary content."""
    encoded = base64.b64encode(data).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def _uploaded_file_to_response_part(uploaded_file: object) -> dict[str, str] | None:
    """Convert an uploaded file to a Responses API input part."""
    data = _uploaded_file_bytes(uploaded_file)
    if not data:
        return None

    filename = _uploaded_file_name(uploaded_file)
    mime_type = _uploaded_file_mime_type(uploaded_file)
    data_url = _data_url_for_bytes(data, mime_type=mime_type)

    if mime_type.startswith("image/"):
        return {
            "type": "input_image",
            "image_url": data_url,
        }

    return {
        "type": "input_file",
        "filename": filename,
        "file_data": data_url,
    }


def _uploaded_files_signature(files: list[object]) -> str:
    """Return a stable content signature for a list of uploaded files."""
    digest = hashlib.sha256()
    for uploaded_file in files:
        filename = _uploaded_file_name(uploaded_file)
        data = _uploaded_file_bytes(uploaded_file)
        digest.update(filename.encode("utf-8"))
        digest.update(len(data).to_bytes(8, "big", signed=False))
        digest.update(hashlib.sha256(data).digest())
    return digest.hexdigest()


def _uploaded_file_names(files: list[object] | None) -> list[str]:
    """Return non-empty filenames for uploaded files."""
    return [_uploaded_file_name(uploaded_file) for uploaded_file in files or [] if uploaded_file]


def _uploaded_files_to_response_input(
    prompt_text: str,
    *,
    uploaded_files: list[object] | None = None,
) -> list[dict[str, object]]:
    """Build one multimodal user message for the Responses API."""
    content: list[dict[str, str]] = [{"type": "input_text", "text": prompt_text.strip()}]
    for uploaded_file in uploaded_files or []:
        part = _uploaded_file_to_response_part(uploaded_file)
        if part:
            content.append(part)
    return [{"role": "user", "content": content}]


def _extract_openai_output_text(response) -> str:
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


def _request_openai_reply(prompt: str, *, api_key: str, model: str) -> tuple[str, str]:
    """Send one chat turn to OpenAI and return (reply_text, response_id)."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    request_kwargs = {
        "model": model,
        "input": [{"role": "user", "content": prompt}],
    }

    previous_response_id = st.session_state.get(OPENAI_PREVIOUS_RESPONSE_ID_KEY)
    if previous_response_id:
        request_kwargs["previous_response_id"] = previous_response_id

    response = client.responses.create(**request_kwargs)
    reply_text = _extract_openai_output_text(response)
    if not reply_text:
        reply_text = "No text response was returned."

    return reply_text, str(getattr(response, "id", "") or "")


def _tool_enabled_model(
    model: str,
    *,
    allow_web_research: bool = False,
    allow_file_search: bool = False,
    allow_code_interpreter: bool = False,
) -> str:
    """Return a tool-capable model for workflows that need OpenAI tools."""
    if not any((allow_web_research, allow_file_search, allow_code_interpreter)):
        return model
    if model.startswith("gpt-5"):
        return model
    return RESEARCH_OPENAI_MODEL


def _converter_model(
    model: str,
    *,
    allow_web_research: bool,
    allow_file_search: bool = False,
) -> str:
    """Return a model suitable for the contractor converter workflow."""
    return _tool_enabled_model(
        model,
        allow_web_research=allow_web_research,
        allow_file_search=allow_file_search,
    )


def _extract_web_search_sources(response) -> list[dict[str, str]]:
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


def _extract_file_search_sources(response) -> list[dict[str, str]]:
    """Extract unique file-search result references from a Responses API object."""
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
                filename = str(
                    getattr(result, "filename", "") or getattr(result, "file_id", "") or ""
                ).strip()
                score_value = getattr(result, "score", None)

            if not filename:
                continue

            score_text = ""
            if isinstance(score_value, (float, int)):
                score_text = f"Relevance {float(score_value):.2f}"

            key = (filename, score_text)
            if key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "title": filename,
                    "url": "",
                    "note": score_text,
                }
            )

    return sources


def _extract_container_artifacts(response) -> list[dict[str, str]]:
    """Extract files created by the Code Interpreter tool from a response."""
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


def _extract_response_sources(response) -> list[dict[str, str]]:
    """Collect web and file-search sources from one Responses API object."""
    return _extract_web_search_sources(response) + _extract_file_search_sources(response)


def _image_bytes_signature(images: list[bytes], *, guidance: str = "") -> str:
    """Return a stable signature for image bytes plus caption guidance."""
    digest = hashlib.sha256()
    for image_bytes in images or []:
        payload = bytes(image_bytes or b"")
        digest.update(len(payload).to_bytes(8, "big", signed=False))
        digest.update(hashlib.sha256(payload).digest())
    digest.update(guidance.encode("utf-8"))
    return digest.hexdigest()


def _image_mime_type_from_bytes(image_bytes: bytes) -> str:
    """Return a best-effort MIME type for raw image bytes."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            image_format = str(image.format or "").lower()
    except Exception:
        return "image/jpeg"

    return {
        "png": "image/png",
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "webp": "image/webp",
        "gif": "image/gif",
        "bmp": "image/bmp",
        "tiff": "image/tiff",
    }.get(image_format, "image/jpeg")


def _photo_caption_cache() -> dict[str, object]:
    """Return the session caption cache for uploaded site photos."""
    return st.session_state.setdefault(AI_IMAGE_CAPTIONS_KEY, {})


def _photo_caption_response_schema(expected_count: int) -> dict[str, object]:
    """Return the JSON schema used for photo caption generation."""
    return {
        "type": "object",
        "properties": {
            "captions": {
                "type": "array",
                "minItems": expected_count,
                "maxItems": expected_count,
                "items": {
                    "type": "string",
                    "description": "A short factual site-photo caption.",
                },
            }
        },
        "required": ["captions"],
        "additionalProperties": False,
    }


def _report_row_context_text(row: list[str] | tuple[str, ...]) -> str:
    """Return a compact textual context block for one report row."""
    padded = list(row) + [""] * max(0, len(REPORT_HEADERS) - len(row))
    padded = padded[: len(REPORT_HEADERS)]
    mapping = {header: str(value or "").strip() for header, value in zip(REPORT_HEADERS, padded)}
    return textwrap.dedent(
        f"""
        Date: {mapping.get("Date", "")}
        Site: {mapping.get("Site_Name", "")}
        District: {mapping.get("District", "")}
        Work: {mapping.get("Work", "")}
        Work executed: {mapping.get("Work_Executed", "")}
        Comment on work: {mapping.get("Comment_on_work", "")}
        Comment on HSE: {mapping.get("Comment_on_HSE", "")}
        Challenges: {mapping.get("challenges", "")}
        """
    ).strip()


def _request_image_captions_with_openai(
    images: list[bytes],
    *,
    api_key: str,
    model: str,
    discipline: str,
    report_row: list[str] | tuple[str, ...],
    persistent_guidance: str = "",
) -> list[str]:
    """Generate short site-photo captions using OpenAI vision."""
    from openai import OpenAI

    if not images:
        return []

    client = OpenAI(api_key=api_key)
    instructions = textwrap.dedent(
        f"""
        You are writing short captions for {discipline.lower()} daily report photos.

        Rules:
        - Return JSON matching the schema exactly.
        - Write one caption per image, in the same order as the images were provided.
        - Keep captions factual, concise, and professional.
        - Do not invent locations, equipment, hazards, or quantities not visible in the image or present in the report context.
        - Prefer consultant-style phrasing and action-oriented wording.
        - Each caption should usually be one sentence and under 18 words.
        """
    ).strip()

    if persistent_guidance:
        instructions = (
            f"{instructions}\n\nSaved caption and reporting preferences:\n{persistent_guidance}"
        )

    content: list[dict[str, str]] = [
        {
            "type": "input_text",
            "text": (
                "Report context:\n"
                f"{_report_row_context_text(report_row)}\n\n"
                "Generate captions for the attached site photos."
            ),
        }
    ]
    for image_bytes in images:
        content.append(
            {
                "type": "input_image",
                "image_url": _data_url_for_bytes(
                    bytes(image_bytes or b""),
                    mime_type=_image_mime_type_from_bytes(bytes(image_bytes or b"")),
                ),
            }
        )

    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=[{"role": "user", "content": content}],
        text={
            "format": {
                "type": "json_schema",
                "name": "site_photo_captions",
                "strict": True,
                "schema": _photo_caption_response_schema(len(images)),
            }
        },
        store=False,
    )

    payload_text = _extract_openai_output_text(response)
    if not payload_text:
        raise ValueError("OpenAI returned empty photo captions.")

    payload = json.loads(payload_text)
    captions = payload.get("captions", [])
    if not isinstance(captions, list):
        raise ValueError("OpenAI returned invalid photo captions.")
    return [str(caption or "").strip() for caption in captions]


def _request_self_healing_analysis_with_openai(
    issue_text: str,
    *,
    api_key: str,
    model: str,
    recent_issues: list[dict[str, object]],
    persistent_guidance: str = "",
) -> dict[str, object]:
    """Analyze an error or improvement idea and return safe healing guidance."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    action_names = list(SELF_HEALING_ACTIONS)
    response_schema = {
        "type": "object",
        "properties": {
            "assistant_message": {"type": "string"},
            "recommended_actions": {
                "type": "array",
                "items": {"type": "string", "enum": action_names},
            },
            "reusable_instruction": {"type": "string"},
            "maintenance_title": {"type": "string"},
        },
        "required": [
            "assistant_message",
            "recommended_actions",
            "reusable_instruction",
            "maintenance_title",
        ],
        "additionalProperties": False,
    }

    instructions = textwrap.dedent(
        """
        You are an app maintenance assistant for a Streamlit reporting system.

        Rules:
        - Diagnose the user's error or requested improvement succinctly.
        - Recommend only safe recovery actions from the allowed list.
        - If the user expresses a stable preference or reusable behavior, extract it into reusable_instruction.
        - If the issue sounds like a longer-term app improvement, suggest a short maintenance_title.
        - Do not claim that source code was changed automatically.
        """
    ).strip()

    if persistent_guidance:
        instructions = f"{instructions}\n\nSaved app preferences:\n{persistent_guidance}"

    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=textwrap.dedent(
            f"""
            Recent runtime issues:
            {json.dumps(recent_issues[:10], ensure_ascii=True, indent=2)}

            User issue or improvement request:
            {issue_text.strip()}
            """
        ).strip(),
        text={
            "format": {
                "type": "json_schema",
                "name": "self_healing_analysis",
                "strict": True,
                "schema": response_schema,
            }
        },
        store=False,
    )

    payload_text = _extract_openai_output_text(response)
    if not payload_text:
        raise ValueError("OpenAI returned an empty self-healing analysis.")

    payload = json.loads(payload_text)
    if not isinstance(payload, dict):
        raise ValueError("OpenAI returned an invalid self-healing analysis.")
    return payload


def _converter_response_options(
    *,
    allow_web_research: bool,
    knowledge_vector_store_id: str = "",
) -> dict[str, object]:
    """Build extra Responses API options for the contractor converter."""
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


def _knowledge_vector_store_cache() -> dict[str, object]:
    """Return the session cache entry used for uploaded project knowledge files."""
    return st.session_state.setdefault(PROJECT_KNOWLEDGE_VECTOR_STORE_KEY, {})


def _ensure_knowledge_vector_store(
    files: list[object],
    *,
    api_key: str,
) -> tuple[str, list[str]]:
    """Upload knowledge files to an ephemeral vector store and return its id."""
    if not files:
        return "", []

    filenames = _uploaded_file_names(files)
    signature = _uploaded_files_signature(files)
    cache = _knowledge_vector_store_cache()
    cached_signature = str(cache.get("signature", "") or "")
    cached_vector_store_id = str(cache.get("vector_store_id", "") or "")
    if signature and signature == cached_signature and cached_vector_store_id:
        return cached_vector_store_id, filenames

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    vector_store = client.vector_stores.create(
        name="WorkWatch Project Knowledge Base",
        expires_after={"anchor": "last_active_at", "days": 1},
    )

    upload_handles: list[io.BytesIO] = []
    for uploaded_file in files:
        file_data = _uploaded_file_bytes(uploaded_file)
        if not file_data:
            continue
        upload_handle = io.BytesIO(file_data)
        upload_handle.name = _uploaded_file_name(uploaded_file)
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


def _structured_report_rows(value: object) -> list[dict[str, str]]:
    """Normalize one or many structured reports into a list of row dicts."""
    if isinstance(value, dict):
        if "reports" in value:
            value = value.get("reports")
        else:
            value = [value]

    if not isinstance(value, list):
        raise ValueError("Structured report payload must be a report object or list of reports.")

    normalized_rows: list[dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("Each structured report must be an object.")
        normalized_rows.append(
            {header: str(entry.get(header, "") or "").strip() for header in REPORT_HEADERS}
        )

    if not normalized_rows:
        raise ValueError("No structured reports were produced.")

    return normalized_rows


def _structured_rows_to_sheet_rows(rows: list[dict[str, str]]) -> list[list[str]]:
    """Convert normalized report dicts into Google Sheet row lists."""
    return [[row.get(header, "").strip() for header in REPORT_HEADERS] for row in rows]


def _structured_rows_to_dataframe(rows: list[dict[str, str]]) -> pd.DataFrame:
    """Convert normalized rows into a dataframe in header order."""
    return pd.DataFrame(_structured_rows_to_sheet_rows(rows), columns=REPORT_HEADERS)


def _structured_rows_from_dataframe(df: pd.DataFrame) -> list[dict[str, str]]:
    """Convert an edited dataframe back into normalized structured rows."""
    return _structured_report_rows(_rows_to_structured_data(_normalized_review_rows(df)))


def _validate_structured_rows_for_sheet(rows: list[dict[str, str]]) -> list[str]:
    """Return validation errors for rows before appending them to Google Sheets."""
    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        missing = [field for field in ("Date", "Site_Name") if not row.get(field, "").strip()]
        if missing:
            errors.append(f"Row {idx} is missing required field(s): {', '.join(missing)}.")

        content_fields = [field for field in REPORT_HEADERS if field not in {"Date", "Site_Name"}]
        if not any(row.get(field, "").strip() for field in content_fields):
            errors.append(f"Row {idx} has no report content beyond date and site.")

    return errors


def _consultant_report_row_schema() -> dict[str, object]:
    """Return the JSON schema for one consultant report row."""
    field_descriptions = {
        "Date": "The report date exactly as stated in the source text. Empty string if unknown.",
        "Site_Name": "The site name or location name from the source text.",
        "District": "District or geographic area if stated.",
        "Work": "Planned or ongoing work scope for the day.",
        "Human_Resources": "Short summary of manpower or team composition.",
        "Supply": "Materials, equipment, or delivered items mentioned in the source text.",
        "Work_Executed": "Main work executed, rewritten in concise consultant-report language.",
        "Comment_on_work": "Consultant observation on progress, quality, blockers, or status.",
        "Another_Work_Executed": "Secondary work executed during the day, if any.",
        "Comment_on_HSE": "HSE observations, PPE, hazards, incidents, or safety status.",
        "Consultant_Recommandation": "Consultant recommendation grounded in the source text.",
        "Non_Compliant_work": "Any non-compliant or defective work explicitly indicated or strongly implied.",
        "Reaction_and_WayForword": "Immediate follow-up action or next step grounded in the source text.",
        "challenges": "Main constraints, delays, risks, or challenges mentioned.",
    }

    return {
        "type": "object",
        "properties": {
            header: {
                "type": "string",
                "description": field_descriptions.get(header, header),
            }
            for header in REPORT_HEADERS
        },
        "required": REPORT_HEADERS,
        "additionalProperties": False,
    }


def _consultant_report_response_schema() -> dict[str, object]:
    """Return the JSON schema used for AI-powered consultant report extraction."""
    return {
        "type": "object",
        "properties": {
            "reports": {
                "type": "array",
                "minItems": 1,
                "items": _consultant_report_row_schema(),
            }
        },
        "required": ["reports"],
        "additionalProperties": False,
    }


def _contractor_refinement_response_schema() -> dict[str, object]:
    """Return the JSON schema for chat-based contractor report refinements."""
    return {
        "type": "object",
        "properties": {
            "assistant_message": {
                "type": "string",
                "description": "Short natural-language reply to the user describing what was improved.",
            },
            "reports": {
                "type": "array",
                "minItems": 1,
                "items": _consultant_report_row_schema(),
            },
        },
        "required": ["assistant_message", "reports"],
        "additionalProperties": False,
    }


def _conversation_transcript(messages: list[dict[str, str]]) -> str:
    """Serialize chat history into a compact plain-text transcript."""
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role", "assistant") or "assistant").strip().upper()
        content = str(message.get("content", "") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines).strip() or "No prior refinement chat."


def _request_transcription_with_openai(
    audio_files: list[object],
    *,
    api_key: str,
    discipline: str,
) -> str:
    """Transcribe one or more uploaded voice notes into plain text."""
    from openai import OpenAI

    if not audio_files:
        raise ValueError("Upload at least one voice note before requesting transcription.")

    client = OpenAI(api_key=api_key)
    prompt = (
        f"This is a {discipline.lower()} construction site voice note for a daily report in Rwanda. "
        "Preserve site names, district names, acronyms, equipment names, cable sizes, 15kV notation, "
        "MV, LV, HSE, PPE, and quantities as accurately as possible."
    )

    transcripts: list[str] = []
    for uploaded_file in audio_files:
        file_data = _uploaded_file_bytes(uploaded_file)
        if not file_data:
            continue

        audio_stream = io.BytesIO(file_data)
        audio_stream.name = _uploaded_file_name(uploaded_file)
        try:
            transcription = client.audio.transcriptions.create(
                model=TRANSCRIPTION_OPENAI_MODEL,
                file=audio_stream,
                response_format="text",
                prompt=prompt,
            )
        finally:
            audio_stream.close()

        if isinstance(transcription, str):
            transcript_text = transcription.strip()
        else:
            transcript_text = str(getattr(transcription, "text", "") or "").strip()

        if transcript_text:
            transcripts.append(f"Voice note ({_uploaded_file_name(uploaded_file)}):\n{transcript_text}")

    if not transcripts:
        raise ValueError("OpenAI did not return any transcription text.")

    return "\n\n".join(transcripts)


def _prepare_refinement_inputs(
    latest_feedback: str,
    *,
    base_supporting_files: list[object] | None = None,
    refinement_supporting_files: list[object] | None = None,
    refinement_audio_files: list[object] | None = None,
    api_key: str = "",
    discipline: str = "",
) -> tuple[str, list[object]]:
    """Merge refinement attachments and voice notes into one refinement request."""
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
    if feedback:
        feedback = f"{feedback}\n\n{transcript_block}"
    else:
        feedback = transcript_block
    return feedback, combined_files


def _refinement_request_preview(
    latest_feedback: str,
    *,
    include_voice_instruction: bool = False,
) -> str:
    """Return a user-visible summary for one refinement request."""
    prompt = str(latest_feedback or "").strip()
    if prompt and include_voice_instruction:
        return f"{prompt}\n\n[Voice instruction attached]"
    if prompt:
        return prompt
    if include_voice_instruction:
        return "[Voice instruction attached]"
    return ""


def _request_structured_reports_with_openai(
    raw_report_text: str,
    *,
    api_key: str,
    model: str,
    discipline: str,
    allow_web_research: bool = False,
    supporting_files: list[object] | None = None,
    knowledge_vector_store_id: str = "",
    persistent_guidance: str = "",
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Turn raw contractor text into consultant-style report rows using OpenAI."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    source_file_names = _uploaded_file_names(supporting_files)
    instructions = textwrap.dedent(
        f"""
        You are an experienced consultant preparing a daily consultant report for {discipline.lower()} works.
        Convert the contractor's raw report and any attached source files into one or more consultant daily report rows.

        Rules:
        - Return JSON that matches the schema exactly.
        - Create multiple rows only when the input clearly contains multiple site/date reports.
        - Rewrite in concise professional consultant language.
        - Do not invent facts, names, quantities, dates, districts, or safety issues.
        - If a field is missing or unclear, return an empty string.
        - Keep Work_Executed factual and specific.
        - Put consultant judgement in Comment_on_work, Comment_on_HSE, Consultant_Recommandation, Non_Compliant_work, and Reaction_and_WayForword only when grounded in the source text.
        - If no grounded consultant recommendation exists, leave Consultant_Recommandation empty.
        - Preserve site names and dates exactly as written when possible.
        - Use attached images only for visible evidence, not for hidden assumptions.
        - If project knowledge files are available through file search, use them to improve terminology and consultant style without overriding the contractor facts.
        """
    ).strip()
    if persistent_guidance:
        instructions = f"{instructions}\n\nSaved reporting preferences:\n{persistent_guidance}"

    prompt_sections = []
    raw_text = raw_report_text.strip()
    if raw_text:
        prompt_sections.append(f"Primary contractor text:\n{raw_text}")
    else:
        prompt_sections.append(
            "No primary contractor text was pasted. Use the attached documents and images as the source material."
        )
    if source_file_names:
        prompt_sections.append(f"Attached source files: {', '.join(source_file_names)}")
    prompt_sections.append("Use all attached evidence only when it supports the extracted report fields.")

    request_input: object = "\n\n".join(prompt_sections)
    if supporting_files:
        request_input = _uploaded_files_to_response_input(
            str(request_input),
            uploaded_files=supporting_files,
        )

    response = client.responses.create(
        model=_converter_model(
            model,
            allow_web_research=allow_web_research,
            allow_file_search=bool(knowledge_vector_store_id),
        ),
        instructions=instructions,
        input=request_input,
        text={
            "format": {
                "type": "json_schema",
                "name": "consultant_daily_reports",
                "strict": True,
                "schema": _consultant_report_response_schema(),
            }
        },
        store=False,
        **_converter_response_options(
            allow_web_research=allow_web_research,
            knowledge_vector_store_id=knowledge_vector_store_id,
        ),
    )

    payload_text = _extract_openai_output_text(response)
    if not payload_text:
        raise ValueError("OpenAI returned an empty structured output.")

    payload = json.loads(payload_text)
    return _structured_report_rows(payload), _extract_response_sources(response)


def _request_refined_structured_reports_with_openai(
    raw_report_text: str,
    *,
    api_key: str,
    model: str,
    discipline: str,
    current_rows: list[dict[str, str]],
    conversation: list[dict[str, str]],
    latest_feedback: str,
    allow_web_research: bool = False,
    supporting_files: list[object] | None = None,
    knowledge_vector_store_id: str = "",
    persistent_guidance: str = "",
) -> tuple[str, list[dict[str, str]], list[dict[str, str]]]:
    """Apply user chat feedback to the converted consultant rows."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    source_file_names = _uploaded_file_names(supporting_files)
    instructions = textwrap.dedent(
        f"""
        You are an experienced consultant assistant revising a {discipline.lower()} daily consultant report.
        The user is chatting with you to improve the converted report as if speaking to normal ChatGPT.

        Rules:
        - Return JSON that matches the schema exactly.
        - Update the reports directly to reflect the user's latest instruction.
        - Keep every field grounded in the contractor source text and the current structured rows.
        - Do not invent facts, dates, site names, manpower, materials, quality issues, or HSE events.
        - If web research is available, use it only to improve technical terminology, safety guidance, consultant wording, or general best-practice recommendations.
        - If file search is available, prefer uploaded project documents for terminology, standards, and internal wording.
        - If the user requests a change that is not supported by the source text, explain that briefly in assistant_message and keep the unsupported part unchanged.
        - If the user asks a question, answer it in assistant_message and still return the best current reports.
        - assistant_message should be concise and directly state what changed or why something could not be changed.
        """
    ).strip()
    if persistent_guidance:
        instructions = f"{instructions}\n\nSaved reporting preferences:\n{persistent_guidance}"

    request_text = textwrap.dedent(
        f"""
        Raw contractor report:
        {raw_report_text}

        Current structured consultant rows (JSON):
        {json.dumps(current_rows, ensure_ascii=True, indent=2)}

        Prior refinement chat:
        {_conversation_transcript(conversation)}

        Attached source files:
        {", ".join(source_file_names) if source_file_names else "None"}

        Latest user instruction:
        {latest_feedback}
        """
    ).strip()

    request_input: object = request_text
    if supporting_files:
        request_input = _uploaded_files_to_response_input(
            request_text,
            uploaded_files=supporting_files,
        )

    response = client.responses.create(
        model=_converter_model(
            model,
            allow_web_research=allow_web_research,
            allow_file_search=bool(knowledge_vector_store_id),
        ),
        instructions=instructions,
        input=request_input,
        text={
            "format": {
                "type": "json_schema",
                "name": "consultant_report_refinement",
                "strict": True,
                "schema": _contractor_refinement_response_schema(),
            }
        },
        store=False,
        **_converter_response_options(
            allow_web_research=allow_web_research,
            knowledge_vector_store_id=knowledge_vector_store_id,
        ),
    )

    payload_text = _extract_openai_output_text(response)
    if not payload_text:
        raise ValueError("OpenAI returned an empty refinement output.")

    payload = json.loads(payload_text)
    assistant_message = str(payload.get("assistant_message", "") or "").strip()
    if not assistant_message:
        assistant_message = "I updated the converted consultant rows."
    return (
        assistant_message,
        _structured_report_rows(payload.get("reports", [])),
        _extract_response_sources(response),
    )


def _request_research_assistant_reply(
    *,
    api_key: str,
    model: str,
    discipline: str,
    question: str,
    conversation: list[dict[str, str]],
    allow_web_research: bool = False,
    knowledge_vector_store_id: str = "",
    persistent_guidance: str = "",
) -> tuple[str, list[dict[str, str]]]:
    """Answer a research or standards question using web/file search when enabled."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
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
        {_conversation_transcript(conversation)}

        Latest user question:
        {question.strip()}
        """
    ).strip()

    response = client.responses.create(
        model=_tool_enabled_model(
            model,
            allow_web_research=allow_web_research,
            allow_file_search=bool(knowledge_vector_store_id),
        ),
        instructions=instructions,
        input=request_text,
        store=False,
        **_converter_response_options(
            allow_web_research=allow_web_research,
            knowledge_vector_store_id=knowledge_vector_store_id,
        ),
    )

    reply_text = _extract_openai_output_text(response)
    if not reply_text:
        raise ValueError("OpenAI returned an empty research reply.")

    return reply_text, _extract_response_sources(response)


def _request_spreadsheet_analysis_with_openai(
    *,
    api_key: str,
    model: str,
    uploaded_files: list[object],
    question: str,
) -> tuple[str, list[dict[str, str]]]:
    """Analyze uploaded spreadsheets and datasets using the Code Interpreter tool."""
    from openai import OpenAI

    if not uploaded_files:
        raise ValueError("Upload at least one spreadsheet or dataset before running analysis.")

    client = OpenAI(api_key=api_key)
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

    response = client.responses.create(
        model=_tool_enabled_model(model, allow_code_interpreter=True),
        tools=[
            {
                "type": "code_interpreter",
                "container": {"type": "auto", "memory_limit": "4g"},
            }
        ],
        tool_choice="required",
        instructions=instructions,
        input=_uploaded_files_to_response_input(question.strip(), uploaded_files=uploaded_files),
        store=False,
    )

    analysis_text = _extract_openai_output_text(response)
    if not analysis_text:
        raise ValueError("OpenAI returned an empty spreadsheet analysis.")

    return analysis_text, _extract_container_artifacts(response)


def _request_text_to_speech_with_openai(
    text: str,
    *,
    api_key: str,
    voice: str = "coral",
    instructions: str = "Speak in a calm, professional consultant briefing tone.",
) -> bytes:
    """Convert assistant text into MP3 audio."""
    from openai import OpenAI

    speech_input = str(text or "").strip()
    if not speech_input:
        raise ValueError("Text is required before generating speech.")

    client = OpenAI(api_key=api_key)
    response = client.audio.speech.create(
        model=TTS_OPENAI_MODEL,
        voice=voice,
        input=speech_input[:4000],
        instructions=instructions,
        response_format="mp3",
    )
    return response.read()


def _reset_contractor_chat(rows: list[dict[str, str]], *, source_label: str) -> None:
    """Reset the contractor-refinement chat after a fresh conversion."""
    count = len(_structured_report_rows(rows))
    st.session_state[CONTRACTOR_CHAT_MESSAGES_KEY] = [
        {
            "role": "assistant",
            "content": (
                f"{source_label} produced {count} structured report row(s). "
                "Tell me what to improve, and I will update the converted rows directly."
            ),
            "sources": [],
        }
    ]


def _append_contractor_chat_message(
    role: str,
    content: str,
    *,
    sources: list[dict[str, str]] | None = None,
) -> None:
    """Append one message to the contractor-refinement chat transcript."""
    messages = st.session_state.setdefault(CONTRACTOR_CHAT_MESSAGES_KEY, [])
    messages.append(
        {
            "role": role,
            "content": content,
            "sources": list(sources or []),
        }
    )


def _render_contractor_chat_message(message: dict[str, object]) -> None:
    """Render one contractor-refinement chat message with optional sources."""
    with _safe_chat_message(str(message.get("role", "assistant"))):
        _safe_write(message.get("content", ""))
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
            if url:
                line = f"- [{title}]({url})"
            else:
                line = f"- {title}"
            if note:
                line = f"{line} ({note})"
            lines.append(line)
        if len(lines) > 1:
            _safe_markdown("\n".join(lines))


def _render_ai_memory_panel() -> None:
    """Render reusable AI instructions that persist across app usage."""
    st.subheader("AI Memory")
    _safe_caption(
        "Save stable instructions here so the converter, captions, research assistant, and self-healing workspace can reuse them."
    )

    target = _safe_selectbox(
        "Instruction target",
        GUIDANCE_TARGETS,
        index=0,
        key="ai_memory_target",
    )
    instruction = _safe_text_area(
        "Reusable instruction",
        value="",
        height=90,
        key="ai_memory_instruction",
        placeholder="Example: Keep consultant comments short and formal. Do not repeat schedule wording unless the source mentions it.",
    ).strip()

    save_col, clear_col = _safe_columns(2, gap="large")
    with save_col:
        save_clicked = st.button("Save to AI memory")
    with clear_col:
        clear_input_clicked = st.button("Clear memory input")

    if clear_input_clicked:
        st.session_state["ai_memory_instruction"] = ""
        _safe_rerun()

    if save_clicked:
        try:
            item = _save_saved_guidance_item(
                instruction,
                target=str(target or "general"),
            )
        except Exception as exc:
            st.warning(f"Unable to save AI memory instruction: {exc}")
            _record_runtime_issue("ai_memory", "Failed to save reusable instruction.", details=str(exc))
        else:
            st.success(f"Saved reusable instruction for {item.get('target', 'general')}.")
            st.session_state["ai_memory_instruction"] = ""
            _safe_rerun()

    items = _saved_guidance_items()
    if not items:
        _safe_caption("No reusable instructions saved yet.")
        return

    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "") or "Untitled instruction").strip()
        target = str(item.get("target", "general") or "general").strip()
        created = str(item.get("created_at", "") or "").strip()
        _safe_markdown(f"**{title}**")
        _safe_caption(f"Target: {target} | Saved: {created}")
        _safe_write(str(item.get("instruction", "") or ""))
        if st.button(
            f"Delete {item.get('id', '')}",
            key=f"delete_ai_memory_{item.get('id', '')}",
        ):
            _delete_saved_guidance_item(str(item.get("id", "") or ""))
            _safe_rerun()


def _render_self_healing_workspace() -> None:
    """Render diagnostics, issue logging, and safe recovery actions."""
    st.subheader("Self-Healing & Improvement Lab")
    _safe_caption(
        "This workspace can diagnose problems, apply safe session-level recovery actions, save reusable preferences, and store longer-term improvement requests."
    )

    diagnostics = {
        "openai_sdk_ready": _openai_sdk_ready()[0],
        "openai_key_loaded": bool(_load_openai_api_key()),
        "saved_guidance_count": len(_saved_guidance_items()),
        "runtime_issue_count": len(_runtime_issue_items()),
        "uploaded_photo_groups": len(st.session_state.get("images", {}) or {}),
        "caption_cache_entries": len(st.session_state.get(AI_IMAGE_CAPTIONS_KEY, {}) or {}),
        "knowledge_base_cached": bool(st.session_state.get(PROJECT_KNOWLEDGE_VECTOR_STORE_KEY)),
    }
    _safe_write(diagnostics)

    issues = _runtime_issue_items()
    if issues:
        _safe_markdown("**Recent runtime issues**")
        for issue in issues[:5]:
            if not isinstance(issue, dict):
                continue
            _safe_write(
                f"[{issue.get('area', 'app')}] {issue.get('message', '')} ({issue.get('created_at', '')})"
            )

    recovery_actions = list(SELF_HEALING_ACTIONS.items())
    for label, action in [
        ("Clear Chat State", "clear_openai_chat"),
        ("Reset Converter", "clear_converter_state"),
        ("Clear Uploaded Photos", "clear_uploaded_images"),
        ("Clear Caption Cache", "clear_photo_captions"),
        ("Clear Sheet Cache", "clear_sheet_cache"),
        ("Reset Knowledge Cache", "reset_knowledge_base"),
        ("Clear Audio Cache", "clear_audio_cache"),
        ("Clear Issue Log", "clear_runtime_issues"),
    ]:
        if st.button(label, key=f"self_heal_{action}"):
            _apply_self_healing_actions([action])
            st.success(f"Applied: {SELF_HEALING_ACTIONS[action]}")
            _safe_rerun()

    request_text = _safe_text_area(
        "Error or improvement request",
        value="",
        height=120,
        key="self_healing_request",
        placeholder="Paste an error message, traceback, or describe an improvement you want the app to remember.",
    ).strip()

    analyze_col, backlog_col = _safe_columns(2, gap="large")
    with analyze_col:
        analyze_clicked = st.button("Analyze with ChatGPT")
    with backlog_col:
        backlog_clicked = st.button("Save request to backlog")

    if backlog_clicked:
        try:
            entry = _save_maintenance_item("User improvement request", request_text, source="self_healing")
        except Exception as exc:
            st.warning(f"Unable to save backlog item: {exc}")
            _record_runtime_issue("self_healing", "Failed to save backlog item.", details=str(exc))
        else:
            st.success(f"Saved backlog item: {entry.get('title', '')}")

    if analyze_clicked:
        try:
            if not request_text:
                raise ValueError("Enter an error or improvement request before running analysis.")

            api_key = _load_openai_api_key()
            if not api_key:
                raise ValueError("OpenAI API key is required for self-healing analysis.")

            sdk_ready, sdk_error = _openai_sdk_ready()
            if not sdk_ready:
                raise ValueError(f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}")

            result = _request_self_healing_analysis_with_openai(
                request_text,
                api_key=api_key,
                model=_default_openai_model(),
                recent_issues=issues,
                persistent_guidance=_active_guidance_text("healing"),
            )
        except Exception as exc:
            st.warning(f"Self-healing analysis failed: {exc}")
            _record_runtime_issue("self_healing", "Self-healing analysis failed.", details=str(exc))
        else:
            st.session_state[SELF_HEALING_RESULT_KEY] = result

    result = st.session_state.get(SELF_HEALING_RESULT_KEY, {})
    if isinstance(result, dict) and result:
        _safe_markdown("**Self-healing analysis**")
        _safe_write(str(result.get("assistant_message", "") or ""))

        recommended_actions = result.get("recommended_actions", [])
        if isinstance(recommended_actions, list) and recommended_actions:
            lines = ["Recommended safe actions:"]
            for action in recommended_actions:
                action_name = str(action or "").strip()
                if action_name in SELF_HEALING_ACTIONS:
                    lines.append(f"- {SELF_HEALING_ACTIONS[action_name]}")
            if len(lines) > 1:
                _safe_markdown("\n".join(lines))
            if st.button("Apply recommended safe actions"):
                applied = _apply_self_healing_actions([str(action or "").strip() for action in recommended_actions])
                if applied:
                    st.success("Applied recommended safe actions.")
                    _safe_rerun()

        reusable_instruction = str(result.get("reusable_instruction", "") or "").strip()
        if reusable_instruction:
            _safe_markdown("**Suggested reusable instruction**")
            _safe_write(reusable_instruction)
            if st.button("Save suggested instruction to AI memory"):
                _save_saved_guidance_item(reusable_instruction, target="general")
                st.success("Saved suggested instruction.")
                _safe_rerun()

        maintenance_title = str(result.get("maintenance_title", "") or "").strip()
        if maintenance_title:
            if st.button("Add suggested maintenance item"):
                _save_maintenance_item(maintenance_title, request_text, source="self_healing")
                st.success("Added suggested maintenance item.")

    backlog = _maintenance_backlog_items()
    if backlog:
        _safe_markdown("**Saved backlog**")
        for item in backlog[:6]:
            if not isinstance(item, dict):
                continue
            _safe_write(f"[{item.get('status', 'open')}] {item.get('title', '')}")
            details = str(item.get("details", "") or "").strip()
            if details:
                _safe_caption(details)


def _persist_parsed_contractor_rows(
    rows: list[dict[str, str]],
    *,
    reset_chat: bool = False,
    source_label: str = "ChatGPT",
) -> None:
    """Store parsed contractor rows in session state."""
    normalized_rows = _structured_report_rows(rows)
    st.session_state[PARSED_CONTRACTOR_REPORTS_KEY] = normalized_rows
    st.session_state["structured_report_data"] = normalized_rows
    st.session_state["_structured_origin"] = "manual"
    if reset_chat:
        _reset_contractor_chat(normalized_rows, source_label=source_label)


def _clear_parsed_contractor_rows() -> None:
    """Remove parsed contractor rows from session state."""
    st.session_state.pop(PARSED_CONTRACTOR_REPORTS_KEY, None)
    st.session_state.pop(CONTRACTOR_CHAT_MESSAGES_KEY, None)


def _clear_cached_sheet_data() -> None:
    """Clear cached sheet reads when supported by the current callable."""
    clear_fn = getattr(get_sheet_data, "clear", None)
    if callable(clear_fn):
        clear_fn()


def _safe_rerun() -> None:
    """Trigger a Streamlit rerun when available."""
    rerun_fn = getattr(st, "rerun", None)
    if callable(rerun_fn):
        rerun_fn()


def _clear_openai_chat() -> None:
    """Reset the chat transcript and response threading state."""
    st.session_state[OPENAI_CHAT_MESSAGES_KEY] = []
    st.session_state.pop(OPENAI_PREVIOUS_RESPONSE_ID_KEY, None)


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
    """Call report generation with backwards-compatible gallery options."""
    base_args = (
        review_rows,
        images,
        discipline,
        img_width_mm,
        img_height_mm,
        spacing_mm,
    )
    base_kwargs = {
        "img_per_row": 2,
        "add_border": add_border,
    }

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


def _build_review_row_mapping(review_rows: list[list[str]]) -> dict[tuple[str, str], list[str]]:
    """Map site/date pairs to the edited review rows used for report generation."""
    mapping: dict[tuple[str, str], list[str]] = {}
    for row in review_rows:
        padded = (list(row) + [""] * len(REPORT_HEADERS))[: len(REPORT_HEADERS)]
        key = (str(padded[1] or "").strip(), str(padded[0] or "").strip())
        if all(key):
            mapping[key] = padded
    return mapping


def _generate_ai_photo_captions_for_reports(
    review_rows: list[list[str]],
    image_mapping: dict[tuple[str, str], list[bytes]],
    *,
    api_key: str,
    model: str,
    discipline: str,
) -> dict[tuple[str, str], list[str]]:
    """Generate or reuse AI captions for uploaded report photos."""
    caption_guidance = _active_guidance_text("captions", "converter")
    cache = _photo_caption_cache()
    row_mapping = _build_review_row_mapping(review_rows)
    caption_mapping: dict[tuple[str, str], list[str]] = {}

    for key, images in image_mapping.items():
        normalized_key = (str(key[0]).strip(), str(key[1]).strip())
        if normalized_key not in row_mapping or not images:
            continue

        signature = _image_bytes_signature(images, guidance=caption_guidance)
        cache_key = f"{normalized_key[0]}|{normalized_key[1]}"
        cached = cache.get(cache_key, {})
        if isinstance(cached, dict) and cached.get("signature") == signature:
            captions = cached.get("captions", [])
            if isinstance(captions, list):
                caption_mapping[normalized_key] = [str(item or "").strip() for item in captions]
                continue

        captions = _request_image_captions_with_openai(
            images,
            api_key=api_key,
            model=model,
            discipline=discipline,
            report_row=row_mapping[normalized_key],
            persistent_guidance=caption_guidance,
        )
        cache[cache_key] = {
            "signature": signature,
            "captions": captions,
            "created_at": _utc_timestamp(),
        }
        caption_mapping[normalized_key] = captions

    st.session_state[AI_IMAGE_CAPTIONS_KEY] = cache
    return caption_mapping


def _clear_photo_caption_cache() -> None:
    """Remove cached AI image captions."""
    st.session_state.pop(AI_IMAGE_CAPTIONS_KEY, None)


def _clear_ai_audio_cache() -> None:
    """Remove cached audio outputs generated by AI features."""
    st.session_state.pop(RESEARCH_ASSISTANT_AUDIO_KEY, None)
    st.session_state.pop(SHEET_ANALYST_AUDIO_KEY, None)
    st.session_state.pop(SELF_HEALING_AUDIO_KEY, None)


def _apply_self_healing_actions(actions: list[str]) -> list[str]:
    """Apply safe maintenance actions inside the running app session."""
    applied: list[str] = []
    for action in actions:
        if action == "clear_openai_chat":
            _clear_openai_chat()
        elif action == "clear_converter_state":
            _clear_parsed_contractor_rows()
        elif action == "clear_uploaded_images":
            st.session_state.pop("images", None)
        elif action == "clear_photo_captions":
            _clear_photo_caption_cache()
        elif action == "clear_sheet_cache":
            _clear_cached_sheet_data()
        elif action == "reset_knowledge_base":
            st.session_state.pop(PROJECT_KNOWLEDGE_VECTOR_STORE_KEY, None)
        elif action == "clear_audio_cache":
            _clear_ai_audio_cache()
        elif action == "clear_runtime_issues":
            _clear_runtime_issues()
        else:
            continue
        applied.append(action)
    return applied


def _render_project_knowledge_base_panel() -> list[object]:
    """Render the shared knowledge-base uploader used by AI workflows."""
    st.subheader("Project Knowledge Base")
    _safe_caption(
        "Upload standards, procedures, approved reports, or client instructions. "
        "The converter and research workspace will use them through OpenAI file search when needed."
    )

    uploaded_files = list(
        _safe_file_uploader(
            "Upload project knowledge files",
            accept_multiple_files=True,
            type=PROJECT_KNOWLEDGE_FILE_TYPES,
            key="project_knowledge_files",
        )
        or []
    )

    if uploaded_files:
        _safe_caption(f"Knowledge files ready: {', '.join(_uploaded_file_names(uploaded_files))}")
    else:
        st.session_state.pop(PROJECT_KNOWLEDGE_VECTOR_STORE_KEY, None)

    return uploaded_files


def _render_openai_chat_panel() -> None:
    """Render the ChatGPT-style assistant UI for the Streamlit app."""
    st.subheader("ChatGPT Assistant")
    _safe_caption(
        "This uses the OpenAI API from your app. It does not connect to your personal ChatGPT chat history."
    )

    with _safe_expander("Chat settings", expanded=False):
        entered_key = _safe_text_input(
            "OpenAI API key (session only)",
            value="",
            type="password",
            key="openai_api_key_input",
            placeholder="sk-...",
        ).strip()
        if entered_key:
            st.session_state[OPENAI_API_KEY_SESSION_KEY] = entered_key

        active_key = _load_openai_api_key()
        key_source = "session input"
        if not st.session_state.get(OPENAI_API_KEY_SESSION_KEY):
            if os.environ.get("OPENAI_API_KEY", "").strip():
                key_source = "environment variable"
            elif _streamlit_secret("OPENAI_API_KEY"):
                key_source = "Streamlit secrets"
            else:
                key_source = "not configured"

        model_value = _safe_text_input(
            "OpenAI model",
            value=_default_openai_model(),
            key="openai_model_input",
            placeholder=DEFAULT_OPENAI_MODEL,
        ).strip()
        st.session_state[OPENAI_MODEL_SESSION_KEY] = model_value or DEFAULT_OPENAI_MODEL

        clear_key_col, clear_chat_col = _safe_columns(2, gap="large")
        with clear_key_col:
            if st.button("Forget session API key"):
                st.session_state.pop(OPENAI_API_KEY_SESSION_KEY, None)
                st.session_state["openai_api_key_input"] = ""
        with clear_chat_col:
            if st.button("Clear ChatGPT history"):
                _clear_openai_chat()

        if active_key:
            st.success(f"OpenAI key loaded from {key_source}.")
        else:
            st.info(
                "Add OPENAI_API_KEY to .streamlit/secrets.toml or your environment, or paste it above for this browser session."
            )

    sdk_ready, sdk_error = _openai_sdk_ready()
    if not sdk_ready:
        st.warning(
            "OpenAI SDK is not installed yet. Run `pip install -r requirements.txt` and reload the app. "
            f"Detail: {sdk_error}"
        )
        return

    messages = st.session_state.setdefault(OPENAI_CHAT_MESSAGES_KEY, [])
    prompt = _safe_chat_input("Ask ChatGPT anything about your reports or field work.")

    if prompt:
        api_key = _load_openai_api_key()
        if not api_key:
            st.warning("OpenAI API key is required before you can start chatting.")
        else:
            model = _default_openai_model()
            messages.append({"role": "user", "content": prompt})
            try:
                with _safe_spinner("Waiting for OpenAI..."):
                    reply_text, response_id = _request_openai_reply(
                        prompt,
                        api_key=api_key,
                        model=model,
                    )
            except Exception as exc:
                messages.pop()
                st.error(f"OpenAI request failed: {exc}")
                _record_runtime_issue("chat_assistant", "ChatGPT assistant request failed.", details=str(exc))
            else:
                messages.append({"role": "assistant", "content": reply_text})
                if response_id:
                    st.session_state[OPENAI_PREVIOUS_RESPONSE_ID_KEY] = response_id

    for message in messages:
        with _safe_chat_message(str(message.get("role", "assistant"))):
            _safe_write(message.get("content", ""))


def _render_contractor_parser(
    discipline: str,
    *,
    knowledge_files: list[object] | None = None,
) -> None:
    """Render the AI/local contractor-report conversion workflow."""
    st.subheader("Contractor Report Converter")
    _safe_caption(
        "Paste raw contractor text, add contractor documents or site photos, transcribe voice notes, "
        "convert everything into consultant daily report fields, refine the result, then append it to Google Sheets."
    )

    enable_parser = _safe_checkbox(
        "Enable contractor report conversion", value=False, key="enable_parser"
    )

    if not enable_parser:
        return

    raw_report_text = st.text_area(
        "Paste contractor report text",
        height=220,
        key="contractor_report_text",
    )
    supporting_files = list(
        _safe_file_uploader(
            "Upload contractor documents or site photos (optional)",
            accept_multiple_files=True,
            type=CONTRACTOR_SUPPORTING_FILE_TYPES,
            key="contractor_supporting_files",
        )
        or []
    )
    audio_files = list(
        _safe_file_uploader(
            "Upload contractor voice notes (optional)",
            accept_multiple_files=True,
            type=AUDIO_FILE_TYPES,
            key="contractor_audio_files",
        )
        or []
    )

    if supporting_files:
        _safe_caption(f"Attached source files: {', '.join(_uploaded_file_names(supporting_files))}")
    if audio_files:
        _safe_caption(f"Voice notes ready: {', '.join(_uploaded_file_names(audio_files))}")
    if knowledge_files:
        _safe_caption(
            "Project knowledge base is available to the converter for internal wording, standards, and approved-report style."
        )
    converter_guidance = _active_guidance_text("converter")
    if converter_guidance:
        _safe_caption("Saved converter instructions are active for this workflow.")

    allow_web_research = _safe_checkbox(
        "Allow web research in converter chat",
        value=False,
        key="contractor_converter_web_research",
    )
    if allow_web_research:
        _safe_caption(
            "Research mode is slower and adds web-search tool cost. The converter will use web search when helpful and show clickable sources in the chat."
        )

    if st.button("Transcribe voice notes into report text"):
        try:
            if not audio_files:
                raise ValueError("Upload one or more voice notes before requesting transcription.")

            api_key = _load_openai_api_key()
            if not api_key:
                raise ValueError("OpenAI API key is required for voice transcription.")

            sdk_ready, sdk_error = _openai_sdk_ready()
            if not sdk_ready:
                raise ValueError(f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}")

            with _safe_spinner("Transcribing voice notes..."):
                transcript = _request_transcription_with_openai(
                    audio_files,
                    api_key=api_key,
                    discipline=discipline,
                )
        except Exception as exc:
            st.warning(f"Voice transcription failed: {exc}")
            _record_runtime_issue("converter", "Voice transcription failed.", details=str(exc))
        else:
            existing_text = str(st.session_state.get("contractor_report_text", "") or "").strip()
            merged_text = f"{existing_text}\n\n{transcript}".strip() if existing_text else transcript
            st.session_state["contractor_report_text"] = merged_text
            st.success("Voice notes were transcribed and appended to the contractor report text.")
            _safe_rerun()

    if st.button("Convert with ChatGPT"):
        try:
            has_source_material = bool(raw_report_text and raw_report_text.strip()) or bool(supporting_files)
            if not has_source_material:
                raise ValueError(
                    "Paste contractor report text, transcribe voice notes, or upload source files before converting."
                )

            api_key = _load_openai_api_key()
            if not api_key:
                raise ValueError("OpenAI API key is required for ChatGPT conversion.")

            sdk_ready, sdk_error = _openai_sdk_ready()
            if not sdk_ready:
                raise ValueError(f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}")

            knowledge_vector_store_id = ""
            if knowledge_files:
                with _safe_spinner("Indexing project knowledge base..."):
                    knowledge_vector_store_id, _ = _ensure_knowledge_vector_store(
                        knowledge_files,
                        api_key=api_key,
                    )

            with _safe_spinner("Converting contractor report with ChatGPT..."):
                parsed_rows, research_sources = _request_structured_reports_with_openai(
                    raw_report_text.strip(),
                    api_key=api_key,
                    model=_default_openai_model(),
                    discipline=discipline,
                    allow_web_research=allow_web_research,
                    supporting_files=supporting_files,
                    knowledge_vector_store_id=knowledge_vector_store_id,
                    persistent_guidance=converter_guidance,
                )
        except Exception as exc:
            st.warning(f"ChatGPT conversion failed: {exc}")
            _record_runtime_issue("converter", "ChatGPT conversion failed.", details=str(exc))
        else:
            _persist_parsed_contractor_rows(
                parsed_rows,
                reset_chat=True,
                source_label="ChatGPT",
            )
            if research_sources:
                st.session_state[CONTRACTOR_CHAT_MESSAGES_KEY][0]["content"] = (
                    st.session_state[CONTRACTOR_CHAT_MESSAGES_KEY][0]["content"]
                    + " Additional research sources were used where helpful."
                )
                st.session_state[CONTRACTOR_CHAT_MESSAGES_KEY][0]["sources"] = research_sources
            st.success(f"ChatGPT produced {len(parsed_rows)} structured report row(s).")

    if st.button("Use local parser"):
        try:
            parsed_rows = _structured_report_rows(clean_and_structure_report(raw_report_text))
        except (TypeError, ValueError) as exc:
            st.warning(f"Unable to structure report locally: {exc}")
        else:
            _persist_parsed_contractor_rows(
                parsed_rows,
                reset_chat=True,
                source_label="Local parser",
            )
            st.success(f"Local parser produced {len(parsed_rows)} structured report row(s).")

    if st.button("Clear parsed contractor result"):
        _clear_parsed_contractor_rows()

    parsed_rows = st.session_state.get(PARSED_CONTRACTOR_REPORTS_KEY, [])
    if not parsed_rows:
        return

    st.subheader("Review Converted Consultant Rows")
    _safe_caption(
        "Edit the converted fields before appending to Google Sheets. Date and Site_Name must be filled."
    )
    parsed_df = _structured_rows_to_dataframe(_structured_report_rows(parsed_rows))
    edited_df = _safe_data_editor(
        parsed_df,
        use_container_width=True,
        hide_index=True,
        key="parsed_contractor_reports_editor",
    )
    edited_rows = _structured_rows_from_dataframe(edited_df)
    st.session_state[PARSED_CONTRACTOR_REPORTS_KEY] = edited_rows
    st.session_state["structured_report_data"] = edited_rows

    st.subheader("Refine With ChatGPT")
    _safe_caption(
        "Chat with the converter like normal ChatGPT. Each accepted reply updates the converted rows directly."
    )
    recorded_refinement_audio = _safe_audio_input(
        "Record refinement instruction",
        key="contractor_refinement_audio_recording",
        help="Record a microphone instruction and apply it directly to the converted rows.",
    )
    if recorded_refinement_audio:
        _safe_caption(f"Recorded refinement audio ready: {_uploaded_file_name(recorded_refinement_audio)}")
        _safe_audio(recorded_refinement_audio, format=_uploaded_file_mime_type(recorded_refinement_audio))
    refinement_supporting_files = list(
        _safe_file_uploader(
            "Add refinement images or extra files (optional)",
            accept_multiple_files=True,
            type=CONTRACTOR_SUPPORTING_FILE_TYPES,
            key="contractor_refinement_supporting_files",
        )
        or []
    )
    refinement_audio_files = list(
        _safe_file_uploader(
            "Add refinement voice notes (optional)",
            accept_multiple_files=True,
            type=AUDIO_FILE_TYPES,
            key="contractor_refinement_audio_files",
        )
        or []
    )
    if refinement_supporting_files:
        _safe_caption(
            f"Refinement files ready: {', '.join(_uploaded_file_names(refinement_supporting_files))}"
        )
    if refinement_audio_files:
        _safe_caption(
            f"Refinement voice notes ready: {', '.join(_uploaded_file_names(refinement_audio_files))}"
        )

    refinement_messages = st.session_state.setdefault(CONTRACTOR_CHAT_MESSAGES_KEY, [])
    for message in refinement_messages:
        _render_contractor_chat_message(message)

    reset_chat_col, append_col = _safe_columns(2, gap="large")
    with reset_chat_col:
        if st.button("Reset refinement chat"):
            _reset_contractor_chat(edited_rows, source_label="Current converter")
            _safe_rerun()
    with append_col:
        if st.button("Append Converted Rows to Google Sheet"):
            validation_errors = _validate_structured_rows_for_sheet(edited_rows)
            if validation_errors:
                for error in validation_errors:
                    st.warning(error)
            else:
                try:
                    append_rows_to_sheet(_structured_rows_to_sheet_rows(edited_rows))
                    _clear_cached_sheet_data()
                except Exception as exc:
                    st.error(f"Failed to append converted rows to Google Sheet: {exc}")
                    _record_runtime_issue("converter", "Failed to append converted rows to Google Sheet.", details=str(exc))
                else:
                    st.success(f"Added {len(edited_rows)} row(s) to Google Sheet.")
                    _safe_rerun()

    refinement_prompt = _safe_chat_input(
        "Tell ChatGPT what to improve in the converted consultant report.",
        key="contractor_refinement_chat_input",
    )
    apply_voice_refinement = st.button("Apply voice refinement")
    voice_refinement_inputs = list(refinement_audio_files)
    if apply_voice_refinement and recorded_refinement_audio:
        voice_refinement_inputs.append(recorded_refinement_audio)

    if refinement_prompt or apply_voice_refinement:
        try:
            has_source_material = any(
                [
                    bool(raw_report_text and raw_report_text.strip()),
                    bool(supporting_files),
                    bool(refinement_supporting_files),
                    bool(voice_refinement_inputs),
                ]
            )
            if not has_source_material:
                raise ValueError(
                    "Paste contractor report text, transcribe voice notes, or upload source files before asking for refinements."
                )
            if not str(refinement_prompt or "").strip() and not voice_refinement_inputs:
                raise ValueError(
                    "Type a refinement request, record a microphone instruction, or upload a voice note before asking for refinements."
                )

            api_key = _load_openai_api_key()
            if not api_key:
                raise ValueError("OpenAI API key is required for refinement chat.")

            sdk_ready, sdk_error = _openai_sdk_ready()
            if not sdk_ready:
                raise ValueError(f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}")

            refinement_feedback, refinement_files = _prepare_refinement_inputs(
                str(refinement_prompt or "").strip(),
                base_supporting_files=supporting_files,
                refinement_supporting_files=refinement_supporting_files,
                refinement_audio_files=voice_refinement_inputs,
                api_key=api_key,
                discipline=discipline,
            )

            knowledge_vector_store_id = ""
            if knowledge_files:
                with _safe_spinner("Refreshing project knowledge base..."):
                    knowledge_vector_store_id, _ = _ensure_knowledge_vector_store(
                        knowledge_files,
                        api_key=api_key,
                    )

            with _safe_spinner("Applying your refinement request..."):
                assistant_message, refined_rows, research_sources = _request_refined_structured_reports_with_openai(
                    raw_report_text.strip(),
                    api_key=api_key,
                    model=_default_openai_model(),
                    discipline=discipline,
                    current_rows=edited_rows,
                    conversation=refinement_messages,
                    latest_feedback=refinement_feedback,
                    allow_web_research=allow_web_research,
                    supporting_files=refinement_files,
                    knowledge_vector_store_id=knowledge_vector_store_id,
                    persistent_guidance=converter_guidance,
                )
        except Exception as exc:
            st.warning(f"ChatGPT refinement failed: {exc}")
            _record_runtime_issue("converter", "ChatGPT refinement failed.", details=str(exc))
        else:
            user_message = _refinement_request_preview(
                refinement_prompt,
                include_voice_instruction=bool(voice_refinement_inputs),
            )
            _append_contractor_chat_message("user", user_message)
            _append_contractor_chat_message(
                "assistant",
                assistant_message,
                sources=research_sources,
            )
            _persist_parsed_contractor_rows(refined_rows)
            st.success("Converted rows updated from your instruction.")
            _safe_rerun()


def _render_ai_research_workspace(
    discipline: str,
    *,
    knowledge_files: list[object] | None = None,
) -> None:
    """Render research, analytics, and readback workflows powered by OpenAI."""
    st.subheader("AI Research Workspace")
    _safe_caption(
        "Use OpenAI file search, web research, code interpreter, and text-to-speech to support reporting and QA decisions."
    )

    with _safe_expander("Standards & Research Assistant", expanded=False):
        allow_web_research = _safe_checkbox(
            "Allow web research in research assistant",
            value=True,
            key="research_assistant_web_research",
        )
        research_guidance = _active_guidance_text("research")
        if knowledge_files:
            _safe_caption("The uploaded project knowledge base will be searched when relevant.")
        else:
            _safe_caption("Upload knowledge files above if you want the assistant to search project-specific documents.")
        if research_guidance:
            _safe_caption("Saved research instructions are active.")

        research_messages = st.session_state.setdefault(RESEARCH_ASSISTANT_MESSAGES_KEY, [])
        for message in research_messages:
            _render_contractor_chat_message(message)

        research_question = _safe_text_input(
            "Research question",
            value="",
            key="research_assistant_question",
            placeholder="Ask about standards, wording, compliance, or best-practice guidance.",
        ).strip()

        ask_col, clear_col, audio_col = _safe_columns(3, gap="large")
        with ask_col:
            ask_clicked = st.button("Ask Research Assistant")
        with clear_col:
            clear_clicked = st.button("Clear research chat")
        with audio_col:
            read_research_audio = st.button("Read last research answer aloud")

        if clear_clicked:
            st.session_state[RESEARCH_ASSISTANT_MESSAGES_KEY] = []
            st.session_state.pop(RESEARCH_ASSISTANT_AUDIO_KEY, None)
            st.session_state["research_assistant_question"] = ""
            _safe_rerun()

        if ask_clicked:
            try:
                if not research_question:
                    raise ValueError("Enter a research question before sending it to the assistant.")

                api_key = _load_openai_api_key()
                if not api_key:
                    raise ValueError("OpenAI API key is required for the research assistant.")

                sdk_ready, sdk_error = _openai_sdk_ready()
                if not sdk_ready:
                    raise ValueError(
                        f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}"
                    )

                knowledge_vector_store_id = ""
                if knowledge_files:
                    with _safe_spinner("Indexing project knowledge base..."):
                        knowledge_vector_store_id, _ = _ensure_knowledge_vector_store(
                            knowledge_files,
                            api_key=api_key,
                        )

                with _safe_spinner("Research assistant is thinking..."):
                    assistant_message, sources = _request_research_assistant_reply(
                        api_key=api_key,
                        model=_default_openai_model(),
                        discipline=discipline,
                        question=research_question,
                        conversation=research_messages,
                        allow_web_research=allow_web_research,
                        knowledge_vector_store_id=knowledge_vector_store_id,
                        persistent_guidance=research_guidance,
                    )
            except Exception as exc:
                st.warning(f"Research assistant failed: {exc}")
                _record_runtime_issue("research", "Research assistant failed.", details=str(exc))
            else:
                research_messages.append({"role": "user", "content": research_question, "sources": []})
                research_messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_message,
                        "sources": sources,
                    }
                )
                st.session_state["research_assistant_question"] = ""
                st.session_state.pop(RESEARCH_ASSISTANT_AUDIO_KEY, None)
                _safe_rerun()

        if read_research_audio:
            try:
                last_assistant_message = next(
                    (
                        str(message.get("content", "") or "").strip()
                        for message in reversed(research_messages)
                        if str(message.get("role", "") or "") == "assistant"
                        and str(message.get("content", "") or "").strip()
                    ),
                    "",
                )
                if not last_assistant_message:
                    raise ValueError("Ask the research assistant a question before generating readback audio.")

                api_key = _load_openai_api_key()
                if not api_key:
                    raise ValueError("OpenAI API key is required for text-to-speech.")

                sdk_ready, sdk_error = _openai_sdk_ready()
                if not sdk_ready:
                    raise ValueError(
                        f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}"
                    )

                with _safe_spinner("Generating research audio..."):
                    st.session_state[RESEARCH_ASSISTANT_AUDIO_KEY] = _request_text_to_speech_with_openai(
                        last_assistant_message,
                        api_key=api_key,
                    )
            except Exception as exc:
                st.warning(f"Audio generation failed: {exc}")
                _record_runtime_issue("research", "Research audio generation failed.", details=str(exc))

        research_audio = st.session_state.get(RESEARCH_ASSISTANT_AUDIO_KEY)
        if research_audio:
            _safe_audio(research_audio, format="audio/mp3")

    with _safe_expander("Spreadsheet Analyst", expanded=False):
        analysis_files = list(
            _safe_file_uploader(
                "Upload spreadsheets or datasets",
                accept_multiple_files=True,
                type=ANALYST_FILE_TYPES,
                key="spreadsheet_analyst_files",
            )
            or []
        )
        if analysis_files:
            _safe_caption(f"Analysis files ready: {', '.join(_uploaded_file_names(analysis_files))}")

        analysis_question = _safe_text_input(
            "Analysis request",
            value="",
            key="spreadsheet_analyst_question",
            placeholder="Summarize progress by site, detect missing dates, find anomalies, compare quantities...",
        ).strip()

        analyze_col, clear_result_col, audio_col = _safe_columns(3, gap="large")
        with analyze_col:
            analyze_clicked = st.button("Analyze spreadsheets with ChatGPT")
        with clear_result_col:
            clear_analysis_clicked = st.button("Clear spreadsheet analysis")
        with audio_col:
            read_analysis_audio = st.button("Read spreadsheet analysis aloud")

        if clear_analysis_clicked:
            st.session_state.pop(SHEET_ANALYST_RESULT_KEY, None)
            st.session_state.pop(SHEET_ANALYST_AUDIO_KEY, None)
            st.session_state["spreadsheet_analyst_question"] = ""
            _safe_rerun()

        if analyze_clicked:
            try:
                if not analysis_files:
                    raise ValueError("Upload one or more spreadsheets or datasets before running analysis.")

                api_key = _load_openai_api_key()
                if not api_key:
                    raise ValueError("OpenAI API key is required for spreadsheet analysis.")

                sdk_ready, sdk_error = _openai_sdk_ready()
                if not sdk_ready:
                    raise ValueError(
                        f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}"
                    )

                question = analysis_question or (
                    "Use the python tool to summarize the uploaded datasets, highlight anomalies, "
                    "flag missing values, and surface the most actionable reporting insights."
                )

                with _safe_spinner("Analyzing spreadsheets with the python tool..."):
                    analysis_text, artifacts = _request_spreadsheet_analysis_with_openai(
                        api_key=api_key,
                        model=_default_openai_model(),
                        uploaded_files=analysis_files,
                        question=question,
                    )
            except Exception as exc:
                st.warning(f"Spreadsheet analysis failed: {exc}")
                _record_runtime_issue("spreadsheet_analyst", "Spreadsheet analysis failed.", details=str(exc))
            else:
                st.session_state[SHEET_ANALYST_RESULT_KEY] = {
                    "text": analysis_text,
                    "artifacts": artifacts,
                }
                st.session_state.pop(SHEET_ANALYST_AUDIO_KEY, None)

        if read_analysis_audio:
            try:
                result = st.session_state.get(SHEET_ANALYST_RESULT_KEY, {})
                analysis_text = str(result.get("text", "") or "").strip()
                if not analysis_text:
                    raise ValueError("Run a spreadsheet analysis before generating readback audio.")

                api_key = _load_openai_api_key()
                if not api_key:
                    raise ValueError("OpenAI API key is required for text-to-speech.")

                sdk_ready, sdk_error = _openai_sdk_ready()
                if not sdk_ready:
                    raise ValueError(
                        f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}"
                    )

                with _safe_spinner("Generating spreadsheet analysis audio..."):
                    st.session_state[SHEET_ANALYST_AUDIO_KEY] = _request_text_to_speech_with_openai(
                        analysis_text,
                        api_key=api_key,
                    )
            except Exception as exc:
                st.warning(f"Audio generation failed: {exc}")
                _record_runtime_issue("spreadsheet_analyst", "Spreadsheet analysis audio generation failed.", details=str(exc))

        analysis_result = st.session_state.get(SHEET_ANALYST_RESULT_KEY, {})
        analysis_text = str(analysis_result.get("text", "") or "").strip()
        if analysis_text:
            _safe_markdown(analysis_text)

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
                _safe_markdown("\n".join(lines))

        analysis_audio = st.session_state.get(SHEET_ANALYST_AUDIO_KEY)
        if analysis_audio:
            _safe_audio(analysis_audio, format="audio/mp3")


def _load_sheet_context():
    """Return (data_rows, sites, error) while isolating failures."""
    try:
        rows = get_sheet_data()
        data_rows = rows[1:] if rows else []
        sites, _ = get_unique_sites_and_dates(data_rows)
        return data_rows, list(sites), None
    except Exception as exc:  # pragma: no cover - user notification
        return [], [], exc


def _rows_to_structured_data(rows: list[list[str]]) -> list[dict[str, str]]:
    """Convert row lists into dicts keyed by REPORT_HEADERS names."""
    structured = []
    header_count = len(REPORT_HEADERS)
    for row in rows:
        padded = (row + [""] * header_count)[:header_count]
        entry = {header: value for header, value in zip(REPORT_HEADERS, padded)}
        structured.append(entry)
    return structured


def _normalized_review_rows(df: pd.DataFrame) -> list[list[str]]:
    """Normalize edited table values back into report row lists."""
    if df is None or df.empty:
        return []

    normalized = df.reindex(columns=REPORT_HEADERS).fillna("")
    rows: list[list[str]] = []
    for row in normalized.values.tolist():
        rows.append([str(cell).strip() for cell in row])
    return rows


def run_app():
    """Render the Streamlit interface."""
    set_background("bg.jpg")
    render_hero(
        title="Smart Field Reporting for Electrical and Civil Works",
        subtitle="A modern reporting system for engineers, supervisors and consultants.",
        cta_primary="Generate Reports",
        cta_secondary="Upload Site Data",
        image_path="bg.jpg",
    )
    _safe_markdown('<div id="reports-section"></div>', unsafe_allow_html=True)
    render_workwatch_header()
    _render_openai_chat_panel()
    _render_ai_memory_panel()
    _render_self_healing_workspace()
    project_knowledge_files = _render_project_knowledge_base_panel()

    _safe_markdown(
        """
        <style>
        div[data-testid="stRadio"] label {
            font-size: 1rem;
            font-weight: 600;
        }
        div[data-testid="stMultiSelect"] label {
            font-size: 1rem;
            font-weight: 600;
        }
        div[data-testid="stMultiSelect"] input {
            min-height: 44px;
            font-size: 0.95rem;
        }
        div[data-baseweb="select"] > div {
            min-height: 46px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.subheader("Gallery Controls")
    img_width_mm = st.sidebar.slider(
        "Gallery width (mm)", min_value=120, max_value=250, value=185, step=5
    )
    img_height_mm = st.sidebar.slider(
        "Wide photo height (mm)", min_value=70, max_value=180, value=120, step=5
    )
    show_photo_placeholders = st.sidebar.checkbox(
        "Show placeholder when no photos are available",
        value=False,
    )
    auto_caption_images = st.sidebar.checkbox(
        "Auto-caption uploaded photos with AI",
        value=True,
    )
    st.sidebar.caption(
        "The gallery is composed as a report collage: two upper slots and one wide lower slot, matching the report style."
    )
    add_border = st.sidebar.checkbox("Add border to images", value=False)
    spacing_mm = st.sidebar.slider(
        "Gap between images (mm)", min_value=0, max_value=20, value=5, step=1
    )
    st.sidebar.caption(
        "For two-photo sets, the renderer prefers the portrait-plus-wide layout shown in your reference output when the images support it."
    )
    if auto_caption_images:
        st.sidebar.caption(
            "AI photo captions use the current report row context plus any saved caption instructions from AI Memory."
        )

    data_rows, sites, data_error = _load_sheet_context()

    if data_error is not None:  # pragma: no cover - user notification
        st.error(f"Failed to load site data: {data_error}")
        _record_runtime_issue("sheet_data", "Failed to load site data.", details=str(data_error))
        return

    container_fn = getattr(st, "container", None)
    filters_container = container_fn() if callable(container_fn) else nullcontext()
    with filters_container:
        discipline_column, selectors_column = _safe_columns((0.9, 1.8), gap="large")

        with discipline_column:
            discipline = st.radio(
                "Discipline",
                ["Civil", "Electrical"],
                key="discipline_radio",
            )

        with selectors_column:
            sites_column, dates_column = _safe_columns(2, gap="large")

            site_options = ["All Sites"] + sites if sites else ["All Sites"]
            default_sites = ["All Sites"] if site_options else []

            with sites_column:
                st.subheader("Select Sites")
                selected_sites_raw = st.multiselect(
                    "Choose sites:",
                    site_options,
                    default=default_sites,
                    key="sites_ms",
                )

            if "All Sites" in selected_sites_raw or not selected_sites_raw:
                selected_sites = sites.copy()
            else:
                selected_sites = selected_sites_raw

            available_dates = sorted(
                {
                    row[0].strip()
                    for row in data_rows
                    if not selected_sites or row[1].strip() in selected_sites
                }
            )

            date_options = ["All Dates"] + available_dates if available_dates else ["All Dates"]
            default_dates = ["All Dates"] if available_dates else []

            with dates_column:
                st.subheader("Select Dates")
                selected_dates_raw = st.multiselect(
                    "Choose dates:",
                    date_options,
                    default=default_dates,
                    key="dates_ms",
                )

            if "All Dates" in selected_dates_raw or not selected_dates_raw:
                selected_dates = available_dates
            else:
                selected_dates = selected_dates_raw

    cache = load_offline_cache()
    if cache and cache.get("rows"):
        st.info(
            "Cached offline data detected. Use the button below to sync back to the Google Sheet."
        )
        if st.button("Sync cached data to Google Sheet"):
            try:
                append_rows_to_sheet(cache.get("rows", []))
                CACHE_FILE.unlink()
                st.success("Cached data synced to Google Sheet.")
            except Exception as exc:  # pragma: no cover - user notification
                st.error(f"Sync failed: {exc}")
                _record_runtime_issue("sheet_sync", "Failed to sync cached data to Google Sheet.", details=str(exc))

    filtered_rows = [
        row
        for row in data_rows
        if row[1].strip() in selected_sites and row[0].strip() in selected_dates
    ]

    site_date_pairs = sorted({(row[1].strip(), row[0].strip()) for row in filtered_rows})

    st.subheader("Preview Reports to be Generated")
    df_preview = pd.DataFrame(filtered_rows, columns=REPORT_HEADERS)
    st.dataframe(df_preview)

    st.subheader("Review Before Download")
    _safe_caption(
        "Edit report text before generation. Date and Site_Name are locked so uploaded images stay linked."
    )

    review_df = _safe_data_editor(
        df_preview,
        use_container_width=True,
        hide_index=True,
        disabled=["Date", "Site_Name"],
        key="review_editor",
    )
    review_rows = _normalized_review_rows(review_df)

    if not review_rows:
        review_rows = [
            (row + [""] * len(REPORT_HEADERS))[: len(REPORT_HEADERS)]
            for row in filtered_rows
        ]

    structured_from_rows = _rows_to_structured_data(review_rows)
    if st.session_state.get("_structured_origin") != "manual":
        st.session_state["structured_report_data"] = structured_from_rows
        st.session_state["_structured_origin"] = "rows"

    _safe_markdown('<div id="upload-section"></div>', unsafe_allow_html=True)

    for site, date in site_date_pairs:
        files = st.file_uploader(
            f"Upload images for {site} - {date}",
            accept_multiple_files=True,
            type=["png", "jpg", "jpeg", "webp"],
            key=f"uploader_{site}_{date}",
        )
        if files:
            key = (site.strip(), date.strip())
            st.session_state.setdefault("images", {})[key] = [f.read() for f in files]
            _safe_image(st.session_state["images"][key], width=220)
            cached_captions = (st.session_state.get(AI_IMAGE_CAPTIONS_KEY, {}) or {}).get(
                f"{key[0]}|{key[1]}",
                {},
            )
            if isinstance(cached_captions, dict):
                captions = cached_captions.get("captions", [])
                if isinstance(captions, list) and captions:
                    _safe_caption("AI captions: " + " | ".join(str(caption or "").strip() for caption in captions))

    _render_contractor_parser(discipline, knowledge_files=project_knowledge_files)
    _render_ai_research_workspace(discipline, knowledge_files=project_knowledge_files)

    st.json(st.session_state.get("structured_report_data", structured_from_rows))

    if st.button("Generate Reports"):
        if not review_rows:
            st.warning("No data available for the selected sites and dates.")
            return

        try:
            image_mapping = st.session_state.get("images", {})
            image_caption_mapping = None
            if auto_caption_images and image_mapping:
                api_key = _load_openai_api_key()
                sdk_ready, sdk_error = _openai_sdk_ready()
                if api_key and sdk_ready:
                    try:
                        with _safe_spinner("Generating AI photo captions..."):
                            image_caption_mapping = _generate_ai_photo_captions_for_reports(
                                review_rows,
                                image_mapping,
                                api_key=api_key,
                                model=_default_openai_model(),
                                discipline=discipline,
                            )
                    except Exception as exc:
                        st.warning(f"Photo captions could not be generated. Reports will continue without them. {exc}")
                        _record_runtime_issue("photo_captions", "AI photo caption generation failed.", details=str(exc))
                elif not sdk_ready:
                    st.warning(f"Photo captions skipped because the OpenAI SDK is unavailable. {sdk_error}")
                else:
                    st.warning("Photo captions skipped because no OpenAI API key is configured.")

            zip_bytes = _generate_reports_with_gallery_options(
                review_rows,
                image_mapping,
                discipline,
                img_width_mm,
                img_height_mm,
                spacing_mm,
                add_border=add_border,
                show_photo_placeholders=show_photo_placeholders,
                image_caption_mapping=image_caption_mapping,
            )
        except Exception as exc:
            st.error(f"Failed to generate reports: {exc}")
            _record_runtime_issue("report_generation", "Report generation failed.", details=str(exc))
        else:
            st.download_button("Download ZIP", zip_bytes, "reports.zip")


if __name__ == "__main__":
    run_app()

