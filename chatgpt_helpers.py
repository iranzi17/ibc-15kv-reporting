"""Utilities for structuring contractor reports using OpenAI's Chat Completions API."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Union
from urllib import error, request

import streamlit as st

REPORT_HEADERS: List[str] = [
    "Date",
    "Site_Name",
    "District",
    "Work",
    "Human_Resources",
    "Supply",
    "Work_Executed",
    "Comment_on_work",
    "Another_Work_Executed",
    "Comment_on_HSE",
    "Consultant_Recommandation",
]

_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
_PROMPT_TEMPLATE = """You are a meticulous assistant that converts contractor site reports into
structured data. Map the provided text into the following columns exactly:
{headers}.

Respond ONLY with valid JSON. If there is a single report return a JSON object
with those keys. If multiple reports are present return a JSON array of objects
using the same keys. Leave any unavailable field as an empty string. Do not
include extra commentary.

Raw report:\n{report_text}
"""


def clean_and_structure_report(
    raw_report_text: str,
) -> Union[Dict[str, str], List[Dict[str, str]]]:
    """Use OpenAI Chat Completions to structure a raw contractor report.

    Parameters
    ----------
    raw_report_text:
        The unstructured contractor report text pasted by the user.

    Returns
    -------
    Union[Dict[str, str], List[Dict[str, str]]]
        A single structured report or a list of reports. Each report is a dict
        keyed by :data:`REPORT_HEADERS`.

    Raises
    ------
    RuntimeError
        If the API key is missing or the OpenAI API request fails.
    ValueError
        If the raw report text is empty or the response cannot be normalised.
    """

    if not raw_report_text or not raw_report_text.strip():
        raise ValueError("Raw report text is empty.")

    try:
        api_key = st.secrets["OPENAI_API_KEY"]
    except Exception as exc:  # pragma: no cover - defensive access to secrets
        raise RuntimeError(
            "OpenAI API key is not configured. Set OPENAI_API_KEY in Streamlit secrets."
        ) from exc

    payload = {
        "model": "gpt-4o-mini",
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": "You extract tabular data from contractor reports.",
            },
            {
                "role": "user",
                "content": _PROMPT_TEMPLATE.format(
                    headers=", ".join(REPORT_HEADERS), report_text=raw_report_text
                ),
            },
        ],
    }

    http_request = request.Request(
        _CHAT_COMPLETIONS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with request.urlopen(http_request, timeout=30) as response:
            raw_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        error_details = _read_error_body(exc)
        message = error_details or exc.reason or str(exc.code)
        raise RuntimeError(f"OpenAI API error ({exc.code}): {message}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Failed to contact OpenAI API: {exc.reason}") from exc

    try:
        response_json = json.loads(raw_body)
        content = response_json["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        raise RuntimeError("Unexpected response from OpenAI API.") from exc

    try:
        parsed_payload = _parse_json_content(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError("ChatGPT response could not be parsed as JSON.") from exc

    try:
        normalised_rows = _normalise_payload(parsed_payload)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    if len(normalised_rows) == 1:
        return normalised_rows[0]
    return normalised_rows


def _parse_json_content(content: str) -> Any:
    """Extract JSON data from the model response content."""

    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = _strip_code_fences(cleaned_content)
    return json.loads(cleaned_content)


def _strip_code_fences(content: str) -> str:
    lines = content.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].startswith("```"):
            lines = lines[:index]
            break
    return "\n".join(lines)


def _normalise_payload(data: Any) -> List[Dict[str, str]]:
    """Ensure the payload is a list of dictionaries with report headers."""

    if isinstance(data, dict):
        return [_normalise_row(data)]
    if isinstance(data, list):
        return [_normalise_row(item) for item in data]
    raise ValueError("ChatGPT response must be a JSON object or list of objects.")


def _normalise_row(item: Any) -> Dict[str, str]:
    if not isinstance(item, dict):
        raise ValueError("Each report must be represented as a JSON object.")

    normalised: Dict[str, str] = {}
    for header in REPORT_HEADERS:
        value = item.get(header, "")
        if value is None:
            value = ""
        normalised[header] = str(value)
    return normalised


def _read_error_body(exc: error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
    except Exception:  # pragma: no cover - fallback if body cannot be read
        return ""
    return body.strip()
