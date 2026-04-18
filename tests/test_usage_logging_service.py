import json
import builtins
import sys
import types

from services import openai_client
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
    assert "error_summary_present" not in events[0]
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


def test_log_usage_event_persists_only_safe_error_metadata(tmp_path, monkeypatch):
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
    assert "error_summary_present" not in payload
    assert "error_summary_category" not in payload
    assert "error_summary_fingerprint" not in payload
    assert "topsecrettokenvalue" not in log_path.read_text(encoding="utf-8")
    assert "[REDACTED" not in log_path.read_text(encoding="utf-8")


def test_log_usage_event_redacts_unexpected_model_identifiers(tmp_path, monkeypatch):
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setattr(usage_logging, "USAGE_LOG_FILE", log_path)

    usage_logging.log_usage_event(
        feature_name="research_assistant",
        model="gpt-5.4-mini secret=token",
        has_files=False,
        has_images=False,
        status="failed",
    )

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["model"] == "[CONFIGURED_MODEL]"


def test_log_usage_event_keeps_known_safe_model_identifiers(tmp_path, monkeypatch):
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setattr(usage_logging, "USAGE_LOG_FILE", log_path)

    usage_logging.log_usage_event(
        feature_name="research_assistant",
        model="gpt-5.4-mini",
        has_files=False,
        has_images=False,
        status="success",
    )

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["model"] == "gpt-5.4-mini"


def test_log_usage_event_uses_allowlisted_feature_and_status(tmp_path, monkeypatch):
    log_path = tmp_path / "usage.jsonl"
    monkeypatch.setattr(usage_logging, "USAGE_LOG_FILE", log_path)

    usage_logging.log_usage_event(
        feature_name="feature token=secret",
        model="gpt-5.4-mini",
        has_files=False,
        has_images=False,
        status="unexpected-status",
    )

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["feature_name"] == "[FEATURE]"
    assert payload["status"] == "success"


def test_log_usage_event_is_non_fatal_when_file_write_fails(monkeypatch):
    class _BrokenPath:
        parent = None

        def exists(self):
            return False

    class _BrokenParent:
        def mkdir(self, *_, **__):
            return None

    broken_file = _BrokenPath()
    broken_file.parent = _BrokenParent()
    monkeypatch.setattr(usage_logging, "USAGE_LOG_FILE", broken_file)
    monkeypatch.setattr(builtins, "open", lambda *_, **__: (_ for _ in ()).throw(OSError("readonly")))

    usage_logging.log_usage_event(
        feature_name="research_assistant",
        model="gpt-5.4-mini",
        has_files=False,
        has_images=False,
        status="failed",
        error_summary="Authorization: Bearer topsecrettokenvalue",
    )


def test_request_openai_reply_succeeds_when_usage_log_write_fails(monkeypatch):
    captured = {}

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(output_text="Reply text", output=[], id="resp_123")

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.responses = _FakeResponses()

    class _BrokenPath:
        parent = None

    class _BrokenParent:
        def mkdir(self, *_, **__):
            return None

    broken_file = _BrokenPath()
    broken_file.parent = _BrokenParent()

    monkeypatch.setattr(openai_client, "st", types.SimpleNamespace(session_state={}))
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))
    monkeypatch.setattr(usage_logging, "USAGE_LOG_FILE", broken_file)
    monkeypatch.setattr(builtins, "open", lambda *_, **__: (_ for _ in ()).throw(OSError("readonly")))

    reply_text, response_id = openai_client.request_openai_reply(
        "Summarize the report status.",
        api_key="test-key",
        model="gpt-4o-mini",
    )

    assert reply_text == "Reply text"
    assert response_id == "resp_123"
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "gpt-4o-mini"


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
