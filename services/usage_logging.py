from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

from config import BASE_DIR
from core.session_state import utc_timestamp

USAGE_LOG_FILE = Path(os.environ.get("OPENAI_USAGE_LOG_FILE", str(BASE_DIR / "openai_usage_log.jsonl")))
MAX_ERROR_SUMMARY_LENGTH = 180
MAX_MODEL_LOG_LENGTH = 64
_SAFE_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-+/=]{8,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b(sk-[A-Za-z0-9]{10,}|rk-[A-Za-z0-9]{10,})\b"), "[REDACTED_API_KEY]"),
    (
        re.compile(
            r"(?i)\b(api(?:_|\s*)key|token|secret|password|passwd|authorization)\b\s*[:=]\s*['\"]?[^\s,'\"}]{4,}"
        ),
        "[REDACTED_CREDENTIAL]",
    ),
    (re.compile(r"(?i)data:[^\s,;]{1,64};base64,[A-Za-z0-9+/=]{24,}"), "[REDACTED_DATA_URL]"),
    (re.compile(r"\b[A-Za-z0-9+/]{64,}={0,2}\b"), "[REDACTED_LONG_TOKEN]"),
    (re.compile(r"(?i)(?:\b(?:code|otp|token)\b\s*[:#-]?\s*)\d{6,8}\b"), "[REDACTED_CODE]"),
    (re.compile(r"(?i)\b\d{6,8}\b(?=\s*(?:code|otp|token)\b)"), "[REDACTED_CODE]"),
]


def sanitize_error_summary(error_summary: str) -> str:
    """Return a compact and redacted error summary safe for local logging."""
    text = str(error_summary or "").strip()
    if not text:
        return ""

    sanitized = " ".join(text.split())
    for pattern, replacement in _SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    if len(sanitized) > MAX_ERROR_SUMMARY_LENGTH:
        sanitized = f"{sanitized[:MAX_ERROR_SUMMARY_LENGTH].rstrip()}..."
    return sanitized


def sanitize_model_for_logging(model: str) -> str:
    """Return a safe model identifier for local logging."""
    value = str(model or "").strip()
    if not value:
        return "[REDACTED_MODEL]"

    if len(value) > MAX_MODEL_LOG_LENGTH:
        value = value[:MAX_MODEL_LOG_LENGTH]

    if not _SAFE_MODEL_PATTERN.fullmatch(value):
        return "[REDACTED_MODEL]"

    return value


def fingerprint_error_summary(error_summary: str) -> str:
    """Return a deterministic non-reversible fingerprint for a sanitized summary."""
    sanitized = sanitize_error_summary(error_summary)
    if not sanitized:
        return ""
    return hashlib.sha256(sanitized.encode("utf-8")).hexdigest()[:16]


def classify_error_summary(error_summary: str) -> str:
    """Return a coarse error category without persisting any raw failure text."""
    sanitized = sanitize_error_summary(error_summary)
    if not sanitized:
        return ""

    lowered = sanitized.lower()
    if "[redacted" in lowered:
        return "redacted_sensitive_content"
    if "rate limit" in lowered:
        return "rate_limit"
    if "timeout" in lowered:
        return "timeout"
    if any(token in lowered for token in ("unauthorized", "forbidden", "authentication", "invalid_api_key")):
        return "authentication"
    if any(token in lowered for token in ("connection", "network", "dns", "socket")):
        return "network"
    return "general_error"


def error_summary_metadata(error_summary: str) -> dict[str, object]:
    """Return safe log fields derived from an error summary."""
    sanitized = sanitize_error_summary(error_summary)
    return {
        "error_summary_present": bool(sanitized),
        "error_summary_category": classify_error_summary(sanitized),
        "error_summary_fingerprint": fingerprint_error_summary(sanitized),
    }


def log_usage_event(
    *,
    feature_name: str,
    model: str,
    has_files: bool,
    has_images: bool,
    status: str,
    error_summary: str = "",
) -> None:
    """Append one OpenAI usage event to the local JSONL log."""
    event = {
        "timestamp": utc_timestamp(),
        "feature_name": str(feature_name or "").strip(),
        "model": sanitize_model_for_logging(model),
        "has_files": bool(has_files),
        "has_images": bool(has_images),
        "status": str(status or "").strip() or "success",
        **error_summary_metadata(error_summary),
    }
    try:
        USAGE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(USAGE_LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True) + "\n")
    except Exception:
        # Logging must never break primary app workflows.
        return


def read_usage_events(*, limit: int = 100) -> list[dict[str, object]]:
    """Read recent usage events from the local JSONL log."""
    if not USAGE_LOG_FILE.exists():
        return []

    events: list[dict[str, object]] = []
    with open(USAGE_LOG_FILE, "r", encoding="utf-8") as handle:
        for line in handle:
            payload = line.strip()
            if not payload:
                continue
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
    return list(reversed(events[-limit:]))


def usage_counts(events: list[dict[str, object]] | None = None) -> dict[str, object]:
    """Return simple usage counts for diagnostics panels."""
    materialized = events if events is not None else read_usage_events(limit=500)
    feature_counter = Counter()
    status_counter = Counter()
    failure_counter = Counter()

    for event in materialized:
        if not isinstance(event, dict):
            continue
        feature = str(event.get("feature_name", "") or "").strip()
        status = str(event.get("status", "") or "").strip() or "unknown"
        if feature:
            feature_counter[feature] += 1
        status_counter[status] += 1
        if status != "success" and feature:
            failure_counter[feature] += 1

    return {
        "total": sum(status_counter.values()),
        "success": status_counter.get("success", 0),
        "failed": sum(count for key, count in status_counter.items() if key != "success"),
        "by_feature": dict(feature_counter),
        "failures_by_feature": dict(failure_counter),
    }
