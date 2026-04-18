import json

from services import usage_logging


def test_log_usage_event_and_readback(tmp_path, monkeypatch):
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setattr(usage_logging, "USAGE_LOG_FILE", log_path)

    usage_logging.log_usage_event(
        feature_name="contractor_conversion",
        model="gpt-5.4-mini",
        has_files=True,
        has_images=False,
        status="success",
    )
    usage_logging.log_usage_event(
        feature_name="research_assistant",
        model="gpt-5.4-mini",
        has_files=False,
        has_images=False,
        status="failed",
        error_summary="network",
    )

    events = usage_logging.read_usage_events(limit=10)

    assert len(events) == 2
    assert events[0]["feature_name"] == "research_assistant"
    assert events[1]["feature_name"] == "contractor_conversion"
    with open(log_path, "r", encoding="utf-8") as handle:
        raw_lines = [json.loads(line) for line in handle if line.strip()]
    assert raw_lines[0]["feature_name"] == "contractor_conversion"


def test_sanitize_error_summary_redacts_and_truncates():
    long_payload = (
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456 "
        "api_key=sk-1234567890abcdefghij "
        "data:image/png;base64," + "A" * 120 + " "
        "token=verysecretvalue "
        "user otp code 123456 "
        + "x" * 300
    )

    sanitized = usage_logging.sanitize_error_summary(long_payload)

    assert "topsecrettokenvalue" not in sanitized
    assert "sk-1234567890abcdefghij" not in sanitized
    assert "data:image/png;base64" not in sanitized
    assert "123456" not in sanitized
    assert "[REDACTED" in sanitized
    assert len(sanitized) <= usage_logging.MAX_ERROR_SUMMARY_LENGTH + 3


def test_log_usage_event_sanitizes_error_summary_before_write(tmp_path, monkeypatch):
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setattr(usage_logging, "USAGE_LOG_FILE", log_path)

    usage_logging.log_usage_event(
        feature_name="research_assistant",
        model="gpt-5.4-mini",
        has_files=False,
        has_images=False,
        status="failed",
        error_summary="authorization: Bearer topsecrettokenvalue",
    )

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert "topsecrettokenvalue" not in payload["error_summary"]
    assert "[REDACTED" in payload["error_summary"]


def test_usage_counts_summarizes_failures():
    summary = usage_logging.usage_counts(
        [
            {"feature_name": "contractor_conversion", "status": "success"},
            {"feature_name": "research_assistant", "status": "failed"},
            {"feature_name": "research_assistant", "status": "failed"},
        ]
    )

    assert summary["total"] == 3
    assert summary["success"] == 1
    assert summary["failed"] == 2
    assert summary["by_feature"]["research_assistant"] == 2
    assert summary["failures_by_feature"]["research_assistant"] == 2
