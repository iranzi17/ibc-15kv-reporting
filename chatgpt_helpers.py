"""Utilities for structuring contractor reports using Hugging Face text generation."""
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

MODEL_ID = "mistralai/Mistral-7B-Instruct"
_INFERENCE_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"
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
    """Use a Hugging Face text-generation model to structure a raw contractor report.

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
        If the API key is missing or the Hugging Face API request fails.
    ValueError
        If the raw report text is empty or the response cannot be normalised.
    """

    if not raw_report_text or not raw_report_text.strip():
        raise ValueError("Raw report text is empty.")

    try:
        api_key = st.secrets["HUGGINGFACE_API_KEY"]
    except Exception as exc:  # pragma: no cover - defensive access to secrets
        raise RuntimeError(
            "Hugging Face API key is not configured. Set HUGGINGFACE_API_KEY in Streamlit secrets."
        ) from exc
    prompt = _PROMPT_TEMPLATE.format(
        headers=", ".join(REPORT_HEADERS), report_text=raw_report_text
    )
    payload = {
        "inputs": prompt,
        "parameters": {"temperature": 0.0, "max_new_tokens": 800},
        "options": {"wait_for_model": True},
    }

    http_request = request.Request(
        _INFERENCE_URL,
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
        message = _extract_error_message(error_details) or exc.reason or str(exc.code)
        raise RuntimeError(f"Hugging Face API error ({exc.code}): {message}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Failed to contact Hugging Face API: {exc.reason}") from exc
    try:
        response_json = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Unexpected response from Hugging Face API.") from exc

    if isinstance(response_json, dict) and "error" in response_json:
        raise RuntimeError(f"Hugging Face API error: {response_json['error']}")

    if not isinstance(response_json, list) or not response_json:
        raise RuntimeError("Unexpected response from Hugging Face API.")

    first_item = response_json[0]
    if not isinstance(first_item, dict):
        raise RuntimeError("Unexpected response from Hugging Face API.")

    generated_text = first_item.get("generated_text")
    if not generated_text:
        error_message = _extract_error_message(raw_body) or "Missing generated_text in response."
        raise RuntimeError(f"Hugging Face API error: {error_message}")

    if generated_text.startswith(prompt):
        generated_text = generated_text[len(prompt) :]

    try:
        parsed_payload = _parse_json_content(generated_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Hugging Face response could not be parsed as JSON.") from exc

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
    raise ValueError("Model response must be a JSON object or list of objects.")


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


def _extract_error_message(body: str) -> str:
    if not body:
        return ""
    try:
        parsed_body = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()

    if isinstance(parsed_body, dict):
        error_message = parsed_body.get("error")
        if error_message:
            return str(error_message)
    if isinstance(parsed_body, list):
        for item in parsed_body:
            if isinstance(item, dict) and item.get("error"):
                return str(item["error"])
    return ""
