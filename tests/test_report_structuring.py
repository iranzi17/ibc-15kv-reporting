import json
from typing import Any

import pytest

import report_structuring


class DummyResponse:
    def __init__(self, body: str, status: int = 200):
        self._body = body.encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "DummyResponse":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        return None


def test_clean_and_structure_report_huggingface_payload(monkeypatch):
    raw_report = "Crew installed transformers."
    prompt = report_structuring._PROMPT_TEMPLATE.format(
        headers=", ".join(report_structuring.REPORT_HEADERS),
        report_text=raw_report,
    )
    response_payload = {
        header: f"value-{index}"
        for index, header in enumerate(report_structuring.REPORT_HEADERS)
    }
    generated_text = prompt + json.dumps(response_payload)

    captured_request = {}

    def fake_urlopen(req, timeout):  # pragma: no cover - exercised via helper
        captured_request["data"] = req.data
        captured_request["headers"] = req.headers
        body = json.dumps([{"generated_text": generated_text}])
        return DummyResponse(body)

    monkeypatch.setattr(report_structuring.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        report_structuring.st,
        "secrets",
        {"HUGGINGFACE_API_KEY": "hf-test-token"},
        raising=False,
    )

    result = report_structuring.clean_and_structure_report(raw_report)

    assert result == response_payload

    sent_payload = json.loads(captured_request["data"].decode("utf-8"))
    assert sent_payload["inputs"] == prompt
    assert sent_payload["parameters"] == {"temperature": 0.0, "max_new_tokens": 800}
    assert sent_payload["options"] == {"wait_for_model": True}

    headers = {key.lower(): value for key, value in captured_request["headers"].items()}
    assert headers["content-type"] == "application/json"
    assert headers["authorization"] == "Bearer hf-test-token"


def test_clean_and_structure_report_missing_generated_text(monkeypatch):
    monkeypatch.setattr(report_structuring.st, "secrets", {"HUGGINGFACE_API_KEY": "hf-test-token"}, raising=False)

    def fake_urlopen(req, timeout):  # pragma: no cover - exercised via helper
        body = json.dumps([{"error": "Model is loading"}])
        return DummyResponse(body)

    monkeypatch.setattr(report_structuring.request, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError) as excinfo:
        report_structuring.clean_and_structure_report("data")

    assert "Model is loading" in str(excinfo.value)
