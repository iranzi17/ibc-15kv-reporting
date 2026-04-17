from __future__ import annotations

import json
import os
import textwrap
from contextlib import nullcontext
from pathlib import Path

import pandas as pd
import streamlit as st
from sheets import (
    CACHE_FILE,
    append_rows_to_sheet,
    get_sheet_data,
    get_unique_sites_and_dates,
    load_offline_cache,
)
from report import generate_reports, signatories_for_row
from report_structuring import REPORT_HEADERS, clean_and_structure_report
from ui import render_workwatch_header, set_background
from ui_hero import render_hero

st.set_page_config(page_title="WorkWatch - Site Intelligence", layout="wide")

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
OPENAI_API_KEY_SESSION_KEY = "openai_api_key"
OPENAI_CHAT_MESSAGES_KEY = "openai_chat_messages"
OPENAI_PREVIOUS_RESPONSE_ID_KEY = "openai_previous_response_id"
OPENAI_MODEL_SESSION_KEY = "openai_model"
PARSED_CONTRACTOR_REPORTS_KEY = "parsed_contractor_reports"
CONTRACTOR_CHAT_MESSAGES_KEY = "contractor_converter_chat_messages"


def _safe_columns(*args, **kwargs):
    """Call st.columns falling back to positional-only call for stubs."""
    columns_fn = getattr(st, "columns", None)
    if not callable(columns_fn):
        return (nullcontext(), nullcontext())

    try:
        return columns_fn(*args, **kwargs)
    except TypeError:
        return columns_fn(*args)


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


def _request_structured_reports_with_openai(
    raw_report_text: str,
    *,
    api_key: str,
    model: str,
    discipline: str,
) -> list[dict[str, str]]:
    """Turn raw contractor text into consultant-style report rows using OpenAI."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    instructions = textwrap.dedent(
        f"""
        You are an experienced consultant preparing a daily consultant report for {discipline.lower()} works.
        Convert the contractor's raw report into one or more consultant daily report rows.

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
        """
    ).strip()

    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=raw_report_text,
        text={
            "format": {
                "type": "json_schema",
                "name": "consultant_daily_reports",
                "strict": True,
                "schema": _consultant_report_response_schema(),
            }
        },
        store=False,
    )

    payload_text = _extract_openai_output_text(response)
    if not payload_text:
        raise ValueError("OpenAI returned an empty structured output.")

    payload = json.loads(payload_text)
    return _structured_report_rows(payload)


def _request_refined_structured_reports_with_openai(
    raw_report_text: str,
    *,
    api_key: str,
    model: str,
    discipline: str,
    current_rows: list[dict[str, str]],
    conversation: list[dict[str, str]],
    latest_feedback: str,
) -> tuple[str, list[dict[str, str]]]:
    """Apply user chat feedback to the converted consultant rows."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    instructions = textwrap.dedent(
        f"""
        You are an experienced consultant assistant revising a {discipline.lower()} daily consultant report.
        The user is chatting with you to improve the converted report as if speaking to normal ChatGPT.

        Rules:
        - Return JSON that matches the schema exactly.
        - Update the reports directly to reflect the user's latest instruction.
        - Keep every field grounded in the contractor source text and the current structured rows.
        - Do not invent facts, dates, site names, manpower, materials, quality issues, or HSE events.
        - If the user requests a change that is not supported by the source text, explain that briefly in assistant_message and keep the unsupported part unchanged.
        - If the user asks a question, answer it in assistant_message and still return the best current reports.
        - assistant_message should be concise and directly state what changed or why something could not be changed.
        """
    ).strip()

    request_text = textwrap.dedent(
        f"""
        Raw contractor report:
        {raw_report_text}

        Current structured consultant rows (JSON):
        {json.dumps(current_rows, ensure_ascii=True, indent=2)}

        Prior refinement chat:
        {_conversation_transcript(conversation)}

        Latest user instruction:
        {latest_feedback}
        """
    ).strip()

    response = client.responses.create(
        model=model,
        instructions=instructions,
        input=request_text,
        text={
            "format": {
                "type": "json_schema",
                "name": "consultant_report_refinement",
                "strict": True,
                "schema": _contractor_refinement_response_schema(),
            }
        },
        store=False,
    )

    payload_text = _extract_openai_output_text(response)
    if not payload_text:
        raise ValueError("OpenAI returned an empty refinement output.")

    payload = json.loads(payload_text)
    assistant_message = str(payload.get("assistant_message", "") or "").strip()
    if not assistant_message:
        assistant_message = "I updated the converted consultant rows."
    return assistant_message, _structured_report_rows(payload.get("reports", []))


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
        }
    ]


def _append_contractor_chat_message(role: str, content: str) -> None:
    """Append one message to the contractor-refinement chat transcript."""
    messages = st.session_state.setdefault(CONTRACTOR_CHAT_MESSAGES_KEY, [])
    messages.append({"role": role, "content": content})


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
            else:
                messages.append({"role": "assistant", "content": reply_text})
                if response_id:
                    st.session_state[OPENAI_PREVIOUS_RESPONSE_ID_KEY] = response_id

    for message in messages:
        with _safe_chat_message(str(message.get("role", "assistant"))):
            _safe_write(message.get("content", ""))


def _render_contractor_parser(discipline: str) -> None:
    """Render the AI/local contractor-report conversion workflow."""
    st.subheader("Contractor Report Converter")
    _safe_caption(
        "Paste raw contractor text, convert it into consultant daily report fields, review the result, then append it to Google Sheets."
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

    if st.button("Convert with ChatGPT"):
        try:
            if not raw_report_text or not raw_report_text.strip():
                raise ValueError("Paste contractor report text before converting.")

            api_key = _load_openai_api_key()
            if not api_key:
                raise ValueError("OpenAI API key is required for ChatGPT conversion.")

            if not _openai_sdk_ready()[0]:
                raise ValueError("OpenAI SDK is not installed in the active Streamlit environment.")

            with _safe_spinner("Converting contractor report with ChatGPT..."):
                parsed_rows = _request_structured_reports_with_openai(
                    raw_report_text.strip(),
                    api_key=api_key,
                    model=_default_openai_model(),
                    discipline=discipline,
                )
        except Exception as exc:
            st.warning(f"ChatGPT conversion failed: {exc}")
        else:
            _persist_parsed_contractor_rows(
                parsed_rows,
                reset_chat=True,
                source_label="ChatGPT",
            )
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

    refinement_messages = st.session_state.setdefault(CONTRACTOR_CHAT_MESSAGES_KEY, [])
    for message in refinement_messages:
        with _safe_chat_message(str(message.get("role", "assistant"))):
            _safe_write(message.get("content", ""))

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
                else:
                    st.success(f"Added {len(edited_rows)} row(s) to Google Sheet.")
                    _safe_rerun()

    refinement_prompt = _safe_chat_input(
        "Tell ChatGPT what to improve in the converted consultant report.",
        key="contractor_refinement_chat_input",
    )

    if refinement_prompt:
        try:
            if not raw_report_text or not raw_report_text.strip():
                raise ValueError("Paste contractor report text before asking for refinements.")

            api_key = _load_openai_api_key()
            if not api_key:
                raise ValueError("OpenAI API key is required for refinement chat.")

            sdk_ready, sdk_error = _openai_sdk_ready()
            if not sdk_ready:
                raise ValueError(f"OpenAI SDK is not installed in the active Streamlit environment. {sdk_error}")

            with _safe_spinner("Applying your refinement request..."):
                assistant_message, refined_rows = _request_refined_structured_reports_with_openai(
                    raw_report_text.strip(),
                    api_key=api_key,
                    model=_default_openai_model(),
                    discipline=discipline,
                    current_rows=edited_rows,
                    conversation=refinement_messages,
                    latest_feedback=refinement_prompt,
                )
        except Exception as exc:
            st.warning(f"ChatGPT refinement failed: {exc}")
        else:
            _append_contractor_chat_message("user", refinement_prompt)
            _append_contractor_chat_message("assistant", assistant_message)
            _persist_parsed_contractor_rows(refined_rows)
            st.success("Converted rows updated from your instruction.")
            _safe_rerun()


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
        "Image width (mm)", min_value=50, max_value=250, value=185, step=5
    )
    img_height_mm = st.sidebar.slider(
        "Image height (mm)", min_value=50, max_value=250, value=148, step=5
    )
    st.sidebar.caption(
        "Images default to 185 mm x 148 mm each, arranged two per row with a 5 mm gap."
    )
    add_border = st.sidebar.checkbox("Add border to images", value=False)
    spacing_mm = st.sidebar.slider(
        "Gap between images (mm)", min_value=0, max_value=20, value=5, step=1
    )

    data_rows, sites, data_error = _load_sheet_context()

    if data_error is not None:  # pragma: no cover - user notification
        st.error(f"Failed to load site data: {data_error}")
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

    cabin_rows = 0
    for row in review_rows:
        sign_info = signatories_for_row(
            discipline,
            row[1],
            row[3],
            row[6],
            row[8],
            row[7],
        )
        if sign_info.get("Contractor_Name") == "Rutarindwa Olivier":
            cabin_rows += 1

    if cabin_rows:
        st.info(
            f"{cabin_rows} report(s) include cabin activities. "
            "Contractor representative is set to Rutarindwa Olivier (Civil Engineer)."
        )

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

    _render_contractor_parser(discipline)

    st.json(st.session_state.get("structured_report_data", structured_from_rows))

    if st.button("Generate Reports"):
        if not review_rows:
            st.warning("No data available for the selected sites and dates.")
            return

        zip_bytes = generate_reports(
            review_rows,
            st.session_state.get("images", {}),
            discipline,
            img_width_mm,
            img_height_mm,
            spacing_mm,
            img_per_row=2,
            add_border=add_border,
        )
        st.download_button("Download ZIP", zip_bytes, "reports.zip")


if __name__ == "__main__":
    run_app()

