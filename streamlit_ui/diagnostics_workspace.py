from __future__ import annotations

import streamlit as st

from core.session_state import (
    AI_IMAGE_CAPTIONS_KEY,
    PROJECT_KNOWLEDGE_VECTOR_STORE_KEY,
    SELF_HEALING_ACTIONS,
    SELF_HEALING_RESULT_KEY,
    active_guidance_text,
    clear_ai_audio_cache,
    clear_openai_chat,
    clear_parsed_contractor_rows,
    clear_photo_caption_cache,
    clear_runtime_issues,
    maintenance_backlog_items,
    record_runtime_issue,
    runtime_issue_items,
    save_maintenance_item,
    save_saved_guidance_item,
    saved_guidance_items,
)
from services.openai_client import default_openai_model, load_openai_api_key, openai_sdk_ready
from services.self_healing_service import request_self_healing_analysis_with_openai
from services.usage_logging import read_usage_events, usage_counts
from sheets import get_sheet_data
from streamlit_ui.helpers import safe_columns, safe_markdown, safe_rerun, safe_text_area, safe_write
from streamlit_ui.layout import render_kpi_strip, render_note, render_section_header, render_subsection


def clear_cached_sheet_data() -> None:
    clear_fn = getattr(get_sheet_data, "clear", None)
    if callable(clear_fn):
        clear_fn()


def apply_self_healing_actions(actions: list[str]) -> list[str]:
    """Apply safe maintenance actions inside the running app session."""
    applied: list[str] = []
    for action in actions:
        if action == "clear_openai_chat":
            clear_openai_chat()
        elif action == "clear_converter_state":
            clear_parsed_contractor_rows()
        elif action == "clear_uploaded_images":
            st.session_state.pop("images", None)
        elif action == "clear_photo_captions":
            clear_photo_caption_cache()
        elif action == "clear_sheet_cache":
            clear_cached_sheet_data()
        elif action == "reset_knowledge_base":
            st.session_state.pop(PROJECT_KNOWLEDGE_VECTOR_STORE_KEY, None)
        elif action == "clear_audio_cache":
            clear_ai_audio_cache()
        elif action == "clear_runtime_issues":
            clear_runtime_issues()
        else:
            continue
        applied.append(action)
    return applied


def render_diagnostics_workspace() -> None:
    render_section_header(
        "4. System Diagnostics & Maintenance",
        "Review runtime issues, recent OpenAI usage, and safe maintenance actions. This is an operational console, not a development lab.",
    )

    usage_events = read_usage_events(limit=60)
    usage_summary = usage_counts(usage_events)
    render_kpi_strip(
        [
            ("Saved guidance", len(saved_guidance_items())),
            ("Runtime issues", len(runtime_issue_items())),
            ("Usage events", usage_summary.get("total", 0)),
            ("Usage failures", usage_summary.get("failed", 0)),
        ]
    )

    render_subsection("Runtime Status", "Current session and local maintenance indicators.")
    diagnostics = {
        "openai_sdk_ready": openai_sdk_ready()[0],
        "openai_key_loaded": bool(load_openai_api_key()),
        "uploaded_photo_groups": len(st.session_state.get("images", {}) or {}),
        "caption_cache_entries": len(st.session_state.get(AI_IMAGE_CAPTIONS_KEY, {}) or {}),
        "knowledge_base_cached": bool(st.session_state.get(PROJECT_KNOWLEDGE_VECTOR_STORE_KEY)),
    }
    safe_write(diagnostics)

    render_subsection("Recent Usage", "Recent OpenAI-powered actions captured in the local usage log.")
    safe_write(usage_summary)
    if usage_events:
        safe_write(usage_events[:12])
    else:
        render_note("No OpenAI usage events have been recorded yet.")

    issues = runtime_issue_items()
    render_subsection("Recent Runtime Issues", "Recent failures and warnings captured by the app.")
    if issues:
        for issue in issues[:10]:
            if not isinstance(issue, dict):
                continue
            safe_markdown(
                f"- [{issue.get('area', 'app')}] {issue.get('message', '')} ({issue.get('created_at', '')})"
            )
            details = str(issue.get("details", "") or "").strip()
            if details:
                safe_markdown(f"  - `{details}`")
    else:
        render_note("No runtime issues are currently recorded.")

    render_subsection("Safe Maintenance Actions", "Apply session-safe recovery actions directly from the app.")
    for label, action in [
        ("Clear general assistant chat", "clear_openai_chat"),
        ("Reset contractor converter", "clear_converter_state"),
        ("Clear uploaded report photos", "clear_uploaded_images"),
        ("Clear cached photo captions", "clear_photo_captions"),
        ("Clear cached sheet data", "clear_sheet_cache"),
        ("Reset knowledge-base cache", "reset_knowledge_base"),
        ("Clear generated audio", "clear_audio_cache"),
        ("Clear runtime issue log", "clear_runtime_issues"),
    ]:
        if st.button(label, key=f"self_heal_{action}"):
            apply_self_healing_actions([action])
            st.success(f"Applied: {SELF_HEALING_ACTIONS[action]}")
            safe_rerun()

    render_subsection("Maintenance Analysis", "Analyze an issue or improvement request and turn it into safe actions or backlog items.")
    request_text = safe_text_area(
        "Error or improvement request",
        value="",
        height=120,
        key="self_healing_request",
        placeholder="Paste an error message, traceback, or describe an improvement request.",
    ).strip()
    analyze_col, backlog_col = safe_columns(2, gap="large")
    with analyze_col:
        analyze_clicked = st.button("Analyze with OpenAI")
    with backlog_col:
        backlog_clicked = st.button("Save request to backlog")

    if backlog_clicked:
        try:
            entry = save_maintenance_item("User improvement request", request_text, source="diagnostics")
        except Exception as exc:
            st.warning(f"Unable to save backlog item: {exc}")
            record_runtime_issue("diagnostics", "Failed to save backlog item.", details=str(exc))
        else:
            st.success(f"Saved backlog item: {entry.get('title', '')}")

    if analyze_clicked:
        try:
            if not request_text:
                raise ValueError("Enter an error or improvement request before running analysis.")
            api_key = load_openai_api_key()
            if not api_key:
                raise ValueError("OpenAI API key is required for diagnostics analysis.")
            sdk_ready, sdk_error = openai_sdk_ready()
            if not sdk_ready:
                raise ValueError(f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}")
            result = request_self_healing_analysis_with_openai(
                request_text,
                api_key=api_key,
                model=default_openai_model(),
                recent_issues=issues,
                persistent_guidance=active_guidance_text("healing"),
            )
        except Exception as exc:
            st.warning(f"Diagnostics analysis failed: {exc}")
            record_runtime_issue("diagnostics", "Diagnostics analysis failed.", details=str(exc))
        else:
            st.session_state[SELF_HEALING_RESULT_KEY] = result

    result = st.session_state.get(SELF_HEALING_RESULT_KEY, {})
    if isinstance(result, dict) and result:
        safe_markdown("**Diagnostics analysis**")
        safe_write(str(result.get("assistant_message", "") or ""))
        recommended_actions = result.get("recommended_actions", [])
        if isinstance(recommended_actions, list) and recommended_actions:
            lines = ["Recommended safe actions:"]
            for action in recommended_actions:
                action_name = str(action or "").strip()
                if action_name in SELF_HEALING_ACTIONS:
                    lines.append(f"- {SELF_HEALING_ACTIONS[action_name]}")
            if len(lines) > 1:
                safe_markdown("\n".join(lines))
            if st.button("Apply recommended safe actions"):
                applied = apply_self_healing_actions([str(action or "").strip() for action in recommended_actions])
                if applied:
                    st.success("Applied recommended safe actions.")
                    safe_rerun()

        reusable_instruction = str(result.get("reusable_instruction", "") or "").strip()
        if reusable_instruction:
            safe_markdown("**Suggested reusable instruction**")
            safe_write(reusable_instruction)
            if st.button("Save suggested instruction to AI guidance"):
                save_saved_guidance_item(reusable_instruction, target="general")
                st.success("Saved suggested instruction.")
                safe_rerun()
        maintenance_title = str(result.get("maintenance_title", "") or "").strip()
        if maintenance_title and st.button("Add suggested maintenance item"):
            save_maintenance_item(maintenance_title, request_text, source="diagnostics")
            st.success("Added suggested maintenance item.")

    render_subsection("Maintenance Backlog", "Saved longer-term improvement requests for follow-up.")
    backlog = maintenance_backlog_items()
    if backlog:
        for item in backlog[:10]:
            if not isinstance(item, dict):
                continue
            safe_write(f"[{item.get('status', 'open')}] {item.get('title', '')}")
            details = str(item.get("details", "") or "").strip()
            if details:
                safe_markdown(f"- {details}")
    else:
        render_note("No maintenance items are currently saved.")
