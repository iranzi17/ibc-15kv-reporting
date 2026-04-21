import sys
import types

from services import converter_service, media_service


class _UploadedFileStub:
    def __init__(self, name, data, mime_type):
        self.name = name
        self._data = data
        self.type = mime_type

    def getvalue(self):
        return self._data


def test_openrouter_structured_conversion_uses_chat_completions(monkeypatch):
    captured = {}
    report = {header: "" for header in converter_service.REPORT_HEADERS}
    report.update({"Date": "2026-04-21", "Site_Name": "Site A", "Work_Executed": "Crew completed trenching."})

    class _FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        message=types.SimpleNamespace(
                            content='{"reports": [' + str(report).replace("'", '"') + "]}"
                        )
                    )
                ]
            )

    class _FakeChat:
        def __init__(self):
            self.completions = _FakeCompletions()

    class _FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = _FakeChat()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))

    rows, sources = converter_service.request_structured_reports_with_openai(
        "Raw contractor text",
        api_key="openrouter-key",
        model="openai/gpt-4o-mini",
        discipline="Civil",
        allow_web_research=True,
        supporting_files=[_UploadedFileStub("site.jpg", b"image-bytes", "image/jpeg")],
        provider="openrouter",
    )

    assert rows == [report]
    assert sources == []
    assert captured["client_kwargs"]["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["messages"][1]["content"][0]["type"] == "text"
    assert captured["messages"][1]["content"][1]["type"] == "image_url"
    assert {"id": "web"} in captured["extra_body"]["plugins"]
    assert {"id": "response-healing"} in captured["extra_body"]["plugins"]


def test_openrouter_conversion_retries_once_on_transient_model_failure(monkeypatch):
    calls = []
    events = []
    report = {header: "" for header in converter_service.REPORT_HEADERS}
    report.update({"Date": "2026-04-21", "Site_Name": "Site A", "Work_Executed": "Crew completed trenching."})

    class _TransientModelError(RuntimeError):
        status_code = 503

    class _FakeCompletions:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise _TransientModelError("model unavailable")
            return types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        message=types.SimpleNamespace(
                            content='{"reports": [' + str(report).replace("'", '"') + "]}"
                        )
                    )
                ]
            )

    class _FakeChat:
        def __init__(self):
            self.completions = _FakeCompletions()

    class _FakeClient:
        def __init__(self, **_kwargs):
            self.chat = _FakeChat()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))
    monkeypatch.setattr(converter_service, "log_usage_event", lambda **kwargs: events.append(kwargs))

    rows, sources = converter_service.request_structured_reports_with_openai(
        "Raw contractor text",
        api_key="openrouter-key",
        model="",
        discipline="Civil",
        provider="openrouter",
    )

    assert rows == [report]
    assert sources == []
    assert [call["model"] for call in calls] == ["openai/gpt-4o-mini", "openai/gpt-4o"]
    assert events[0]["status"] == "failed"
    assert events[0]["fallback_used"] is False
    assert events[1]["status"] == "success"
    assert events[1]["fallback_used"] is True
    assert events[1]["routing_profile"] == "conversion_strict"


def test_openrouter_transcription_sends_input_audio(monkeypatch):
    captured = {}

    class _FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content="Transcribed field note"))]
            )

    class _FakeChat:
        def __init__(self):
            self.completions = _FakeCompletions()

    class _FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.chat = _FakeChat()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))

    transcript = media_service.request_transcription_with_openai(
        [_UploadedFileStub("voice-note.m4a", b"audio-bytes", "audio/m4a")],
        api_key="openrouter-key",
        discipline="Electrical",
        provider="openrouter",
    )

    audio_part = captured["messages"][1]["content"][1]
    assert "Transcribed field note" in transcript
    assert captured["model"] == "openai/gpt-audio-mini"
    assert audio_part["type"] == "input_audio"
    assert audio_part["input_audio"]["format"] == "m4a"
