from __future__ import annotations

import json
import re
import textwrap

import pandas as pd

from report_structuring import REPORT_HEADERS
from services.media_service import (
    has_pdf_files,
    has_image_files,
    request_transcription_with_openai,
    uploaded_file_names,
    uploaded_files_to_chat_content,
    uploaded_files_to_response_input,
)
from services.openai_client import (
    PROVIDER_OPENAI,
    PROVIDER_OPENROUTER,
    converter_model,
    extract_chat_completion_text,
    extract_openai_output_text,
    make_ai_client,
    normalize_ai_provider,
    provider_label,
)
from services.research_service import converter_response_options, extract_response_sources
from services.usage_logging import log_usage_event

EMPTY_PLACEHOLDERS = {"n/a", "na", "none", "null", "-", "--", "nil"}


def structured_report_rows(value: object) -> list[dict[str, str]]:
    """Normalize one or many structured reports into ordered row dicts."""
    if isinstance(value, dict):
        value = value.get("reports", [value]) if "reports" in value else [value]
    if not isinstance(value, list):
        raise ValueError("Structured report payload must be a report object or list of reports.")

    normalized_rows: list[dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("Each structured report must be an object.")
        normalized_rows.append({header: normalize_field_value(entry.get(header, "")) for header in REPORT_HEADERS})
    if not normalized_rows:
        raise ValueError("No structured reports were produced.")
    return normalized_rows


def structured_rows_to_sheet_rows(rows: list[dict[str, str]]) -> list[list[str]]:
    return [[normalize_field_value(row.get(header, "")) for header in REPORT_HEADERS] for row in rows]


def structured_rows_to_dataframe(rows: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(structured_rows_to_sheet_rows(rows), columns=REPORT_HEADERS)


def structured_rows_from_dataframe(df: pd.DataFrame) -> list[dict[str, str]]:
    if df is None or df.empty:
        return []
    normalized = df.reindex(columns=REPORT_HEADERS).fillna("")
    rows: list[dict[str, str]] = []
    for raw_row in normalized.values.tolist():
        rows.append(
            {
                header: normalize_field_value(value)
                for header, value in zip(REPORT_HEADERS, raw_row)
            }
        )
    return rows


def validate_structured_rows_for_sheet(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    for idx, row in enumerate(rows, start=1):
        missing = [field for field in ("Date", "Site_Name") if not normalize_field_value(row.get(field, "")).strip()]
        if missing:
            errors.append(f"Row {idx} is missing required field(s): {', '.join(missing)}.")
        content_fields = [field for field in REPORT_HEADERS if field not in {"Date", "Site_Name"}]
        if not any(normalize_field_value(row.get(field, "")).strip() for field in content_fields):
            errors.append(f"Row {idx} has no report content beyond date and site.")
    return errors


def consultant_report_row_schema() -> dict[str, object]:
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
            header: {"type": "string", "description": field_descriptions.get(header, header)}
            for header in REPORT_HEADERS
        },
        "required": REPORT_HEADERS,
        "additionalProperties": False,
    }


def consultant_report_response_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "reports": {
                "type": "array",
                "minItems": 1,
                "items": consultant_report_row_schema(),
            }
        },
        "required": ["reports"],
        "additionalProperties": False,
    }


def contractor_refinement_response_schema() -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "assistant_message": {
                "type": "string",
                "description": "Short natural-language reply describing what was improved.",
            },
            "reports": {
                "type": "array",
                "minItems": 1,
                "items": consultant_report_row_schema(),
            },
        },
        "required": ["assistant_message", "reports"],
        "additionalProperties": False,
    }


def openrouter_plugins(
    *,
    allow_web_research: bool = False,
    include_file_parser: bool = False,
    include_response_healing: bool = False,
) -> list[dict[str, object]]:
    """Return OpenRouter plugins for chat-completion workflows."""
    plugins: list[dict[str, object]] = []
    if allow_web_research:
        plugins.append({"id": "web"})
    if include_file_parser:
        plugins.append({"id": "file-parser", "pdf": {"engine": "cloudflare-ai"}})
    if include_response_healing:
        plugins.append({"id": "response-healing"})
    return plugins


def conversation_transcript(messages: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role", "assistant") or "assistant").strip().upper()
        content = str(message.get("content", "") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines).strip() or "No prior refinement chat."


def normalize_field_value(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"([!?.,:;])\1{1,}", r"\1", text)
    if text.lower() in EMPTY_PLACEHOLDERS:
        return ""
    return text


def normalize_structured_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for row in structured_report_rows(rows):
        normalized.append({header: normalize_field_value(row.get(header, "")) for header in REPORT_HEADERS})
    return normalized


def is_near_empty_text(value: str) -> bool:
    stripped = re.sub(r"[^A-Za-z0-9]+", "", str(value or ""))
    return len(stripped) < 8


def validate_conversion_source_inputs(raw_report_text: str, supporting_files: list[object] | None = None) -> list[str]:
    errors: list[str] = []
    has_text = bool(str(raw_report_text or "").strip())
    has_files = bool(supporting_files)
    if not has_text and not has_files:
        errors.append("Provide contractor text or attach source files before converting.")
    if has_text and is_near_empty_text(raw_report_text):
        errors.append("The pasted contractor text is too short to convert reliably.")
    return errors


def validate_refinement_request(
    prompt_text: str,
    *,
    has_voice_instruction: bool,
    has_supporting_files: bool,
    raw_report_text: str,
) -> list[str]:
    errors: list[str] = []
    if not str(raw_report_text or "").strip() and not has_supporting_files:
        errors.append("Refinement requires contractor source text or attached evidence.")
    if not str(prompt_text or "").strip() and not has_voice_instruction:
        errors.append("Enter a refinement instruction or provide a voice instruction.")
    if str(prompt_text or "").strip() and is_near_empty_text(prompt_text):
        errors.append("The refinement instruction is too short to apply reliably.")
    return errors


def prepare_refinement_inputs(
    latest_feedback: str,
    *,
    base_supporting_files: list[object] | None = None,
    refinement_supporting_files: list[object] | None = None,
    refinement_audio_files: list[object] | None = None,
    api_key: str = "",
    discipline: str = "",
    provider: str | None = PROVIDER_OPENAI,
) -> tuple[str, list[object]]:
    """Merge refinement attachments and voice notes into one refinement request."""
    combined_files = list(base_supporting_files or [])
    if refinement_supporting_files:
        combined_files.extend(refinement_supporting_files)

    feedback = str(latest_feedback or "").strip()
    if not refinement_audio_files:
        return feedback, combined_files
    if not api_key:
        raise ValueError(f"{provider_label(provider)} API key is required for refinement voice notes.")

    transcript = request_transcription_with_openai(
        list(refinement_audio_files),
        api_key=api_key,
        discipline=discipline,
        provider=provider,
    ).strip()
    if not transcript:
        return feedback, combined_files

    transcript_block = f"Additional refinement voice notes:\n{transcript}"
    feedback = f"{feedback}\n\n{transcript_block}".strip() if feedback else transcript_block
    return feedback, combined_files


def refinement_request_preview(latest_feedback: str, *, include_voice_instruction: bool = False) -> str:
    prompt = str(latest_feedback or "").strip()
    if prompt and include_voice_instruction:
        return f"{prompt}\n\n[Voice instruction attached]"
    if prompt:
        return prompt
    if include_voice_instruction:
        return "[Voice instruction attached]"
    return ""


def apply_field_locks(
    previous_rows: list[dict[str, str]],
    next_rows: list[dict[str, str]],
    *,
    locked_fields: list[str] | tuple[str, ...] | set[str],
) -> list[dict[str, str]]:
    """Keep locked fields from the prior rows when row counts align."""
    locked = {field for field in locked_fields if field in REPORT_HEADERS}
    if not locked or len(previous_rows) != len(next_rows):
        return normalize_structured_rows(next_rows)

    locked_rows: list[dict[str, str]] = []
    for prior_row, next_row in zip(normalize_structured_rows(previous_rows), normalize_structured_rows(next_rows)):
        merged = dict(next_row)
        for field in locked:
            merged[field] = prior_row.get(field, "")
        locked_rows.append(merged)
    return locked_rows


def summarize_row_changes(
    previous_rows: list[dict[str, str]],
    next_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Return a compact change summary for contractor refinements."""
    summaries: list[dict[str, object]] = []
    normalized_previous = normalize_structured_rows(previous_rows)
    normalized_next = normalize_structured_rows(next_rows)
    row_count = max(len(normalized_previous), len(normalized_next))

    for index in range(row_count):
        previous = normalized_previous[index] if index < len(normalized_previous) else {header: "" for header in REPORT_HEADERS}
        current = normalized_next[index] if index < len(normalized_next) else {header: "" for header in REPORT_HEADERS}
        changes = []
        for field in REPORT_HEADERS:
            old_value = previous.get(field, "")
            new_value = current.get(field, "")
            if old_value == new_value:
                continue
            changes.append({"field": field, "before": old_value, "after": new_value})
        if changes:
            summaries.append(
                {
                    "row_index": index + 1,
                    "site_name": current.get("Site_Name", "") or previous.get("Site_Name", ""),
                    "date": current.get("Date", "") or previous.get("Date", ""),
                    "changes": changes,
                }
            )
    return summaries


def request_structured_reports_with_openai(
    raw_report_text: str,
    *,
    api_key: str,
    model: str,
    discipline: str,
    allow_web_research: bool = False,
    strict_source_grounded: bool = True,
    supporting_files: list[object] | None = None,
    knowledge_vector_store_id: str = "",
    persistent_guidance: str = "",
    provider: str | None = PROVIDER_OPENAI,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Turn raw contractor text into consultant-style report rows using the configured AI provider."""
    normalized_provider = normalize_ai_provider(provider)

    source_file_names = uploaded_file_names(supporting_files)
    grounding_rule = (
        "- Strict source-grounded mode is enabled. Only include content clearly supported by the pasted text, uploaded files, visible image evidence, or transcribed voice notes.\n"
        "- If support is weak or absent, leave the field empty instead of inferring."
        if strict_source_grounded
        else "- Improve wording conservatively, but remain grounded in the available source material."
    )
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
        {grounding_rule}
        """
    ).strip()
    if persistent_guidance:
        instructions = f"{instructions}\n\nSaved reporting preferences:\n{persistent_guidance}"

    prompt_sections = []
    raw_text = raw_report_text.strip()
    if raw_text:
        prompt_sections.append(f"Primary contractor text:\n{raw_text}")
    else:
        prompt_sections.append("No primary contractor text was pasted. Use the attached documents and images as the source material.")
    if source_file_names:
        prompt_sections.append(f"Attached source files: {', '.join(source_file_names)}")
    prompt_sections.append("Use all attached evidence only when it supports the extracted report fields.")

    request_text = "\n\n".join(prompt_sections)

    resolved_model = converter_model(
        model,
        provider=normalized_provider,
        allow_web_research=allow_web_research,
        allow_file_search=bool(knowledge_vector_store_id),
    )
    response = None
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
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "consultant_daily_reports",
                        "strict": True,
                        "schema": consultant_report_response_schema(),
                    },
                },
            }
            plugins = openrouter_plugins(
                allow_web_research=allow_web_research,
                include_file_parser=has_pdf_files(supporting_files),
                include_response_healing=True,
            )
            if plugins:
                request_kwargs["extra_body"] = {"plugins": plugins}
            response = client.chat.completions.create(**request_kwargs)
            payload_text = extract_chat_completion_text(response)
        else:
            request_input: object = request_text
            if supporting_files:
                request_input = uploaded_files_to_response_input(request_text, uploaded_files=supporting_files)
            response = client.responses.create(
                model=resolved_model,
                instructions=instructions,
                input=request_input,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "consultant_daily_reports",
                        "strict": True,
                        "schema": consultant_report_response_schema(),
                    }
                },
                store=False,
                **converter_response_options(
                    allow_web_research=allow_web_research,
                    knowledge_vector_store_id=knowledge_vector_store_id,
                ),
            )
            payload_text = extract_openai_output_text(response)
        if not payload_text:
            raise ValueError(f"{provider_label(normalized_provider)} returned an empty structured output.")
        payload = json.loads(payload_text)
        rows = normalize_structured_rows(structured_report_rows(payload))
    except Exception as exc:
        log_usage_event(
            feature_name="contractor_conversion",
            model=resolved_model,
            has_files=bool(supporting_files),
            has_images=has_image_files(supporting_files),
            status="failed",
            error_summary=str(exc),
        )
        raise

    log_usage_event(
        feature_name="contractor_conversion",
        model=resolved_model,
        has_files=bool(supporting_files),
        has_images=has_image_files(supporting_files),
        status="success",
    )
    return rows, extract_response_sources(response) if normalized_provider == PROVIDER_OPENAI else []


def request_refined_structured_reports_with_openai(
    raw_report_text: str,
    *,
    api_key: str,
    model: str,
    discipline: str,
    current_rows: list[dict[str, str]],
    conversation: list[dict[str, str]],
    latest_feedback: str,
    allow_web_research: bool = False,
    strict_source_grounded: bool = True,
    supporting_files: list[object] | None = None,
    knowledge_vector_store_id: str = "",
    persistent_guidance: str = "",
    provider: str | None = PROVIDER_OPENAI,
) -> tuple[str, list[dict[str, str]], list[dict[str, str]]]:
    """Apply user chat feedback to converted consultant rows."""
    normalized_provider = normalize_ai_provider(provider)

    source_file_names = uploaded_file_names(supporting_files)
    grounding_rule = (
        "- Strict source-grounded mode is enabled. Only change content when the request is supported by the source text, files, images, or transcribed voice notes.\n"
        "- If support is missing, explain that briefly in assistant_message and keep the unsupported content unchanged."
        if strict_source_grounded
        else "- Improve wording conservatively, but stay grounded in the available source material."
    )
    instructions = textwrap.dedent(
        f"""
        You are an experienced consultant assistant revising a {discipline.lower()} daily consultant report.
        The user is chatting with you to improve the converted report through the app interface.

        Rules:
        - Return JSON that matches the schema exactly.
        - Update the reports directly to reflect the user's latest instruction.
        - Keep every field grounded in the contractor source text and the current structured rows.
        - Do not invent facts, dates, site names, manpower, materials, quality issues, or HSE events.
        - If web research is available, use it only to improve technical terminology, safety guidance, consultant wording, or general best-practice recommendations.
        - If file search is available, prefer uploaded project documents for terminology, standards, and internal wording.
        - If the user asks a question, answer it in assistant_message and still return the best current reports.
        - assistant_message should be concise and directly state what changed or why something could not be changed.
        {grounding_rule}
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
        {conversation_transcript(conversation)}

        Attached source files:
        {", ".join(source_file_names) if source_file_names else "None"}

        Latest user instruction:
        {latest_feedback}
        """
    ).strip()
    request_input: object = request_text
    if supporting_files and normalized_provider == PROVIDER_OPENAI:
        request_input = uploaded_files_to_response_input(request_text, uploaded_files=supporting_files)

    resolved_model = converter_model(
        model,
        provider=normalized_provider,
        allow_web_research=allow_web_research,
        allow_file_search=bool(knowledge_vector_store_id),
    )
    response = None
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
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "consultant_report_refinement",
                        "strict": True,
                        "schema": contractor_refinement_response_schema(),
                    },
                },
            }
            plugins = openrouter_plugins(
                allow_web_research=allow_web_research,
                include_file_parser=has_pdf_files(supporting_files),
                include_response_healing=True,
            )
            if plugins:
                request_kwargs["extra_body"] = {"plugins": plugins}
            response = client.chat.completions.create(**request_kwargs)
            payload_text = extract_chat_completion_text(response)
        else:
            response = client.responses.create(
                model=resolved_model,
                instructions=instructions,
                input=request_input,
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "consultant_report_refinement",
                        "strict": True,
                        "schema": contractor_refinement_response_schema(),
                    }
                },
                store=False,
                **converter_response_options(
                    allow_web_research=allow_web_research,
                    knowledge_vector_store_id=knowledge_vector_store_id,
                ),
            )
            payload_text = extract_openai_output_text(response)
        if not payload_text:
            raise ValueError(f"{provider_label(normalized_provider)} returned an empty refinement output.")
        payload = json.loads(payload_text)
        assistant_message = str(payload.get("assistant_message", "") or "").strip() or "I updated the converted consultant rows."
        rows = normalize_structured_rows(structured_report_rows(payload.get("reports", [])))
    except Exception as exc:
        log_usage_event(
            feature_name="contractor_refinement",
            model=resolved_model,
            has_files=bool(supporting_files),
            has_images=has_image_files(supporting_files),
            status="failed",
            error_summary=str(exc),
        )
        raise

    log_usage_event(
        feature_name="contractor_refinement",
        model=resolved_model,
        has_files=bool(supporting_files),
        has_images=has_image_files(supporting_files),
        status="success",
    )
    return assistant_message, rows, extract_response_sources(response) if normalized_provider == PROVIDER_OPENAI else []

