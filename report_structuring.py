"""Utilities for structuring contractor reports locally without external APIs."""
from __future__ import annotations

from typing import Dict, List, Optional, Union

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
    "Non_Compliant_work",
    "Reaction_and_WayForword",
    "challenges",
]


def _normalise_header_key(raw_key: str) -> str:
    normalised_characters: List[str] = []
    pending_separator = False

    for character in str(raw_key or "").lower():
        if character.isalnum():
            if pending_separator and normalised_characters:
                normalised_characters.append("_")
            normalised_characters.append(character)
            pending_separator = False
            continue
        pending_separator = True

    return "".join(normalised_characters)


# Normalised header names mapped to the canonical header used in REPORT_HEADERS.
_HEADER_ALIASES = {
    _normalise_header_key(header): header for header in REPORT_HEADERS
}

# Common human-readable variants mapped to canonical headers.
_HEADER_ALIASES.update(
    {
        "site_name": "Site_Name",
        "site": "Site_Name",
        "site_names": "Site_Name",
        "comment_on_work": "Comment_on_work",
        "comments_on_work": "Comment_on_work",
        "comment_on_hse": "Comment_on_HSE",
        "comments_on_hse": "Comment_on_HSE",
        "recommendation": "Consultant_Recommandation",
        "recommendations": "Consultant_Recommandation",
        "consultant_recommendation": "Consultant_Recommandation",
        "consultant_recommendations": "Consultant_Recommandation",
        "work_executed": "Work_Executed",
        "another_work_executed": "Another_Work_Executed",
        "non_compliant_work": "Non_Compliant_work",
        "non_compliance_work": "Non_Compliant_work",
        "reaction_way_forword": "Reaction_and_WayForword",
        "reaction_way_forward": "Reaction_and_WayForword",
        "reaction_and_way_forward": "Reaction_and_WayForword",
        "reaction_and_wayforword": "Reaction_and_WayForword",
        "reaction_wayforward": "Reaction_and_WayForword",
        "reaction_wayforword": "Reaction_and_WayForword",
        "challenge": "challenges",
        "challenges": "challenges",
    }
)

def clean_and_structure_report(
    raw_report_text: str,
) -> Union[Dict[str, str], List[Dict[str, str]]]:
    """Parse contractor text and map it into :data:`REPORT_HEADERS`.

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
    TypeError
        If ``raw_report_text`` is not a string.
    ValueError
        If ``raw_report_text`` is empty or only whitespace.
    """

    if not isinstance(raw_report_text, str):
        raise TypeError("Raw report text must be a string.")

    sections = _split_into_sections(raw_report_text)
    if not sections:
        raise ValueError("Raw report text is empty.")

    parsed_rows = [_parse_section(section) for section in sections]
    if len(parsed_rows) == 1:
        return parsed_rows[0]
    return parsed_rows


def _split_into_sections(raw_report_text: str) -> List[str]:
    """Split the raw text into logical sections representing individual reports."""

    stripped = raw_report_text.strip()
    if not stripped:
        return []

    sections: List[str] = []
    current_lines: List[str] = []
    for line in stripped.splitlines():
        if _is_section_divider(line):
            section = "\n".join(current_lines).strip()
            if section:
                sections.append(section)
            current_lines = []
            continue
        current_lines.append(line)

    section = "\n".join(current_lines).strip()
    if section:
        sections.append(section)
    return sections


def _parse_section(section: str) -> Dict[str, str]:
    """Parse an individual section into the canonical report headers."""

    result: Dict[str, str] = {header: "" for header in REPORT_HEADERS}
    current_header: Optional[str] = None

    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        parsed_line = _split_key_value_line(line)
        if parsed_line:
            raw_key, value = parsed_line
            header = _resolve_header(raw_key)
            if header is None:
                header = "Comment_on_work"
            result[header] = _append_value(result[header], value)
            current_header = header
            continue

        if current_header:
            result[current_header] = _append_value(result[current_header], line)
        else:
            result["Comment_on_work"] = _append_value(result["Comment_on_work"], line)

    return result


def _resolve_header(raw_key: str) -> Optional[str]:
    """Return the canonical header name for the provided key string."""

    normalised_key = _normalise_header_key(raw_key)
    if not normalised_key:
        return None
    return _HEADER_ALIASES.get(normalised_key)


def resolve_report_header_name(raw_key: str) -> Optional[str]:
    """Public helper that exposes :func:`_resolve_header` for reuse."""

    return _resolve_header(raw_key)


def _append_value(current: str, addition: str) -> str:
    """Append ``addition`` to ``current`` separated by a newline if needed."""

    addition = addition.strip()
    if not addition:
        return current
    if not current:
        return addition
    return f"{current}\n{addition}"


def _is_section_divider(line: str) -> bool:
    stripped = line.strip()
    return len(stripped) >= 3 and set(stripped) == {"-"}


def _split_key_value_line(line: str) -> Optional[tuple[str, str]]:
    for separator in (":", " - "):
        if separator not in line:
            continue
        raw_key, value = line.split(separator, 1)
        raw_key = raw_key.strip()
        if _looks_like_header_key(raw_key):
            return raw_key, value.strip()
    return None


def _looks_like_header_key(raw_key: str) -> bool:
    candidate = raw_key.strip()
    if not candidate or len(candidate) > 80:
        return False
    return all(character.isalnum() or character in " _-/" for character in candidate)


__all__ = [
    "REPORT_HEADERS",
    "clean_and_structure_report",
    "resolve_report_header_name",
]
