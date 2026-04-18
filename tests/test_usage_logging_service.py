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

