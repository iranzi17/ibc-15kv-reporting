from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from config import BASE_DIR
from core.session_state import utc_timestamp

USAGE_LOG_FILE = Path(os.environ.get("OPENAI_USAGE_LOG_FILE", str(BASE_DIR / "openai_usage_log.jsonl")))


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
        "model": str(model or "").strip(),
        "has_files": bool(has_files),
        "has_images": bool(has_images),
        "status": str(status or "").strip() or "success",
        "error_summary": str(error_summary or "").strip(),
    }
    USAGE_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USAGE_LOG_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True) + "\n")


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

