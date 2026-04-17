import app
import sys
import types
from pathlib import Path


HEADERS = [
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


class _ColumnContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _SidebarStub:
    def subheader(self, *_, **__):
        return None

    def slider(self, *_, value=None, **__):
        return value

    def selectbox(self, *_, options=None, index=0, **__):
        return options[index] if options else None

    def checkbox(self, *_, value=False, **__):
        return value

    def caption(self, *_, **__):
        return None


class _StreamlitStub:
    def __init__(self):
        self.session_state = {}
        self.sidebar = _SidebarStub()
        self.multiselect_calls = []
        self.uploader_labels = []
        self.dataframe_capture = None
        self.json_value = None
        self.text_area_value = ""
        self.text_area_calls = []
        self.warning_messages = []
        self.button_states = {
            "Sync cached data to Google Sheet": False,
            "Generate Reports": True,
            "Send to Google Sheet": False,
            "Clean & Structure Report": False,
        }

    def columns(self, *_):
        return (_ColumnContext(), _ColumnContext())

    def radio(self, _label, options, **__):
        return options[0] if options else None

    def button(self, label, *_, **__):
        return self.button_states.get(label, False)

    def multiselect(self, label, options, default, **__):
        self.multiselect_calls.append((label, options))
        return default

    def subheader(self, *_, **__):
        return None

    def header(self, *_, **__):
        return None

    def dataframe(self, df, *_, **__):
        self.dataframe_capture = df

    def file_uploader(self, label, *_, **__):
        self.uploader_labels.append(label)
        return []

    def download_button(self, *_, **__):
        self.download_called = True
        return None

    def json(self, data, *_, **__):
        self.json_value = data

    def info(self, *_, **__):
        return None

    def success(self, *_, **__):
        return None

    def error(self, *_, **__):
        return None

    def text_area(self, label, *_, **__):
        self.text_area_calls.append(label)
        return self.text_area_value

    def warning(self, message, *_, **__):
        self.warning_messages.append(message)
        return None


class _UploadedFileStub:
    def __init__(self, name, data, mime_type="application/octet-stream"):
        self.name = name
        self._data = data
        self.type = mime_type

    def getvalue(self):
        return self._data


def test_run_app_excludes_header_rows(monkeypatch):
    sheet_rows = [
        HEADERS,
        [
            "2024-01-01",
            "Site A",
            "District 1",
            "Work details A",
            "Crew A",
            "Supply A",
            "Executed A",
            "Comment A",
            "Another Executed A",
            "HSE A",
            "Recommendation A",
            "Non compliant A",
            "Reaction A",
            "Challenges A",
        ],
        [
            "2024-01-02",
            "Site B",
            "District 2",
            "Work details B",
            "Crew B",
            "Supply B",
            "Executed B",
            "Comment B",
            "Another Executed B",
            "HSE B",
            "Recommendation B",
            "Non compliant B",
            "Reaction B",
            "Challenges B",
        ],
    ]

    monkeypatch.setattr(app, "get_sheet_data", lambda: sheet_rows)
    monkeypatch.setattr(app, "load_offline_cache", lambda: None)
    monkeypatch.setattr(app, "generate_reports", lambda *_, **__: b"zip-bytes")
    monkeypatch.setattr(app, "set_background", lambda *_: None)
    monkeypatch.setattr(app, "render_workwatch_header", lambda *_: None)

    st_stub = _StreamlitStub()
    monkeypatch.setattr(app, "st", st_stub)

    app.run_app()

    site_multiselect = st_stub.multiselect_calls[0][1]
    date_multiselect = st_stub.multiselect_calls[1][1]

    assert "Site_Name" not in site_multiselect
    assert site_multiselect == ["All Sites", "Site A", "Site B"]

    assert "Date" not in date_multiselect
    assert date_multiselect == ["All Dates", "2024-01-01", "2024-01-02"]

    preview_df = st_stub.dataframe_capture
    assert preview_df.values.tolist() == [
        sheet_rows[1],
        sheet_rows[2],
    ]

    assert "Upload project knowledge files" in st_stub.uploader_labels
    assert "Upload spreadsheets or datasets" in st_stub.uploader_labels
    assert "Upload images for Site A - 2024-01-01" in st_stub.uploader_labels
    assert "Upload images for Site B - 2024-01-02" in st_stub.uploader_labels

    structured_report = st_stub.session_state.get("structured_report_data")
    assert isinstance(structured_report, list)
    assert [row["Site_Name"] for row in structured_report] == ["Site A", "Site B"]
    assert st_stub.json_value == structured_report


def test_run_app_generates_reports_when_button_clicked(monkeypatch):
    sheet_rows = [
        HEADERS,
        [
            "2024-01-01",
            "Site A",
            "District 1",
            "Work details A",
            "Crew A",
            "Supply A",
            "Executed A",
            "Comment A",
            "Another Executed A",
            "HSE A",
            "Recommendation A",
            "Non compliant A",
            "Reaction A",
            "Challenges A",
        ],
    ]

    monkeypatch.setattr(app, "get_sheet_data", lambda: sheet_rows)
    monkeypatch.setattr(app, "load_offline_cache", lambda: None)
    generated = {}

    def fake_generate(filtered_rows, *_args, **_kwargs):
        generated["rows"] = filtered_rows
        return b"zip-bytes"

    monkeypatch.setattr(app, "generate_reports", fake_generate)
    monkeypatch.setattr(app, "set_background", lambda *_: None)
    monkeypatch.setattr(app, "render_workwatch_header", lambda *_: None)

    st_stub = _StreamlitStub()
    st_stub.download_called = False
    st_stub.button_states["Generate Reports"] = True
    monkeypatch.setattr(app, "st", st_stub)

    app.run_app()

    assert generated["rows"] == [sheet_rows[1]]
    assert st_stub.download_called is True
    assert "Paste contractor report text" not in st_stub.text_area_calls


def test_load_openai_api_key_prefers_session_env_then_secrets(monkeypatch):
    st_stub = types.SimpleNamespace(
        session_state={app.OPENAI_API_KEY_SESSION_KEY: "session-key"},
        secrets={"OPENAI_API_KEY": "secret-key"},
    )
    monkeypatch.setattr(app, "st", st_stub)
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")

    assert app._load_openai_api_key() == "session-key"

    st_stub.session_state.clear()
    assert app._load_openai_api_key() == "env-key"

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert app._load_openai_api_key() == "secret-key"


def test_structured_report_rows_normalizes_wrapped_payload():
    wrapped = {
        "reports": [
            {
                "Date": "2024-04-01",
                "Site_Name": "Site A",
                "District": "Gasabo",
                "Work": "Trenching",
                "Human_Resources": "5 technicians",
                "Supply": "",
                "Work_Executed": "Excavated 50 m",
                "Comment_on_work": "Good progress",
                "Another_Work_Executed": "",
                "Comment_on_HSE": "PPE compliant",
                "Consultant_Recommandation": "Continue",
                "Non_Compliant_work": "",
                "Reaction_and_WayForword": "Proceed tomorrow",
                "challenges": "Rain",
            }
        ]
    }

    rows = app._structured_report_rows(wrapped)

    assert rows == wrapped["reports"]


def test_validate_structured_rows_for_sheet_flags_missing_required_fields():
    rows = [
        {header: "" for header in app.REPORT_HEADERS},
        {
            "Date": "2024-04-01",
            "Site_Name": "Site A",
            "District": "",
            "Work": "",
            "Human_Resources": "",
            "Supply": "",
            "Work_Executed": "",
            "Comment_on_work": "",
            "Another_Work_Executed": "",
            "Comment_on_HSE": "",
            "Consultant_Recommandation": "",
            "Non_Compliant_work": "",
            "Reaction_and_WayForword": "",
            "challenges": "",
        },
    ]

    errors = app._validate_structured_rows_for_sheet(rows)

    assert "Row 1 is missing required field(s): Date, Site_Name." in errors
    assert "Row 1 has no report content beyond date and site." in errors
    assert "Row 2 has no report content beyond date and site." in errors


def test_request_structured_reports_with_openai_parses_schema_response(monkeypatch):
    captured = {}

    report = {
        "Date": "2024-04-01",
        "Site_Name": "Site A",
        "District": "Gasabo",
        "Work": "Cable trenching",
        "Human_Resources": "8 workers",
        "Supply": "Cables",
        "Work_Executed": "Excavated and prepared route",
        "Comment_on_work": "Progress acceptable",
        "Another_Work_Executed": "",
        "Comment_on_HSE": "No incident reported",
        "Consultant_Recommandation": "Continue and maintain PPE compliance",
        "Non_Compliant_work": "",
        "Reaction_and_WayForword": "Proceed with cable laying next shift",
        "challenges": "Light rain",
    }

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                output_text=f'{{"reports": [{report!r}]}}'.replace("'", '"'),
                output=[],
            )

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))

    rows, sources = app._request_structured_reports_with_openai(
        "Raw contractor text",
        api_key="test-key",
        model="gpt-4o-mini",
        discipline="Electrical",
    )

    assert rows == [report]
    assert sources == []
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "gpt-4o-mini"
    assert captured["store"] is False
    assert captured["text"]["format"]["type"] == "json_schema"
    assert "tools" not in captured


def test_request_refined_structured_reports_with_openai_updates_rows(monkeypatch):
    captured = {}
    report = {
        "Date": "2024-04-15",
        "Site_Name": "KIBAGABAGA SMART CABIN",
        "District": "",
        "Work": "Connecting the existing MV and LV Lines",
        "Human_Resources": "1 Supervisor, 2 Technicians, 4 Helpers",
        "Supply": "MV cables, termination kits",
        "Work_Executed": "Executed MV cable termination for 2 sets and started MV cable laying.",
        "Comment_on_work": "Progress is aligned with the project schedule.",
        "Another_Work_Executed": "",
        "Comment_on_HSE": "PPE compliance observed.",
        "Consultant_Recommandation": "Continue with careful cable handling.",
        "Non_Compliant_work": "",
        "Reaction_and_WayForword": "Proceed with the remaining cable laying.",
        "challenges": "",
    }

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            payload = {
                "assistant_message": "I tightened the consultant language and updated the HSE wording.",
                "reports": [report],
            }
            return types.SimpleNamespace(output_text=str(payload).replace("'", '"'), output=[])

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))

    assistant_message, rows, sources = app._request_refined_structured_reports_with_openai(
        "Raw contractor text",
        api_key="test-key",
        model="gpt-4o-mini",
        discipline="Electrical",
        current_rows=[report],
        conversation=[{"role": "assistant", "content": "Tell me what to improve."}],
        latest_feedback="Make the HSE note shorter and more professional.",
    )

    assert assistant_message == "I tightened the consultant language and updated the HSE wording."
    assert rows == [report]
    assert sources == []
    assert captured["api_key"] == "test-key"
    assert captured["model"] == "gpt-4o-mini"
    assert captured["text"]["format"]["type"] == "json_schema"
    assert "Raw contractor text" in captured["input"]
    assert "Make the HSE note shorter and more professional." in captured["input"]


def test_prepare_refinement_inputs_merges_voice_notes_and_files(monkeypatch):
    captured = {}

    def _fake_transcription(audio_files, *, api_key, discipline):
        captured["audio_files"] = [uploaded_file.name for uploaded_file in audio_files]
        captured["api_key"] = api_key
        captured["discipline"] = discipline
        return "Voice note (site-note.m4a):\nShorten the work comment."

    monkeypatch.setattr(app, "_request_transcription_with_openai", _fake_transcription)

    feedback, files = app._prepare_refinement_inputs(
        "Make it more concise.",
        base_supporting_files=[_UploadedFileStub("base.pdf", b"pdf-bytes", "application/pdf")],
        refinement_supporting_files=[_UploadedFileStub("photo.jpg", b"image-bytes", "image/jpeg")],
        refinement_audio_files=[_UploadedFileStub("site-note.m4a", b"audio-bytes", "audio/m4a")],
        api_key="test-key",
        discipline="Electrical",
    )

    assert "Make it more concise." in feedback
    assert "Additional refinement voice notes:" in feedback
    assert "Shorten the work comment." in feedback
    assert [uploaded_file.name for uploaded_file in files] == ["base.pdf", "photo.jpg"]
    assert captured == {
        "audio_files": ["site-note.m4a"],
        "api_key": "test-key",
        "discipline": "Electrical",
    }


def test_refinement_request_preview_marks_voice_instruction():
    assert app._refinement_request_preview("Tighten the HSE wording.") == "Tighten the HSE wording."
    assert (
        app._refinement_request_preview(
            "Tighten the HSE wording.",
            include_voice_instruction=True,
        )
        == "Tighten the HSE wording.\n\n[Voice instruction attached]"
    )
    assert app._refinement_request_preview("", include_voice_instruction=True) == "[Voice instruction attached]"


def test_request_refined_structured_reports_with_openai_supports_image_inputs(monkeypatch):
    captured = {}
    report = {
        "Date": "2024-04-15",
        "Site_Name": "Site A",
        "District": "",
        "Work": "",
        "Human_Resources": "",
        "Supply": "",
        "Work_Executed": "",
        "Comment_on_work": "",
        "Another_Work_Executed": "",
        "Comment_on_HSE": "",
        "Consultant_Recommandation": "",
        "Non_Compliant_work": "",
        "Reaction_and_WayForword": "",
        "challenges": "",
    }

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            payload = {
                "assistant_message": "I used the attached photo to improve the wording.",
                "reports": [report],
            }
            return types.SimpleNamespace(output_text=str(payload).replace("'", '"'), output=[])

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))

    assistant_message, rows, sources = app._request_refined_structured_reports_with_openai(
        "Raw contractor text",
        api_key="test-key",
        model="gpt-4o-mini",
        discipline="Electrical",
        current_rows=[report],
        conversation=[],
        latest_feedback="Use the attached image to improve the work executed wording.",
        supporting_files=[_UploadedFileStub("site.jpg", b"image-bytes", "image/jpeg")],
    )

    assert assistant_message == "I used the attached photo to improve the wording."
    assert rows == [report]
    assert sources == []
    assert captured["api_key"] == "test-key"
    assert isinstance(captured["input"], list)
    content = captured["input"][0]["content"]
    assert content[0]["type"] == "input_text"
    assert "Use the attached image" in content[0]["text"]
    assert content[1]["type"] == "input_image"
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")


def test_clear_parsed_contractor_rows_clears_refinement_chat(monkeypatch):
    st_stub = types.SimpleNamespace(
        session_state={
            app.PARSED_CONTRACTOR_REPORTS_KEY: [{"Date": "2024-04-15"}],
            app.CONTRACTOR_CHAT_MESSAGES_KEY: [{"role": "assistant", "content": "Hello"}],
        }
    )
    monkeypatch.setattr(app, "st", st_stub)

    app._clear_parsed_contractor_rows()

    assert app.PARSED_CONTRACTOR_REPORTS_KEY not in st_stub.session_state
    assert app.CONTRACTOR_CHAT_MESSAGES_KEY not in st_stub.session_state


def test_converter_model_uses_gpt5_mini_for_web_research():
    assert app._converter_model("gpt-4o-mini", allow_web_research=True) == app.RESEARCH_OPENAI_MODEL
    assert app._converter_model("gpt-5.4", allow_web_research=True) == "gpt-5.4"
    assert app._converter_model("gpt-4o-mini", allow_web_research=False) == "gpt-4o-mini"
    assert (
        app._converter_model("gpt-4o-mini", allow_web_research=False, allow_file_search=True)
        == app.RESEARCH_OPENAI_MODEL
    )


def test_extract_web_search_sources_deduplicates_items():
    response = types.SimpleNamespace(
        output=[
            types.SimpleNamespace(
                type="web_search_call",
                action=types.SimpleNamespace(
                    sources=[
                        types.SimpleNamespace(title="Source A", url="https://example.com/a"),
                        types.SimpleNamespace(title="Source A", url="https://example.com/a"),
                        {"title": "Source B", "url": "https://example.com/b"},
                    ]
                ),
            )
        ]
    )

    sources = app._extract_web_search_sources(response)

    assert sources == [
        {"title": "Source A", "url": "https://example.com/a"},
        {"title": "Source B", "url": "https://example.com/b"},
    ]


def test_request_structured_reports_with_openai_enables_web_search(monkeypatch):
    captured = {}

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                output_text='{"reports": [{"Date": "", "Site_Name": "Site A", "District": "", "Work": "", "Human_Resources": "", "Supply": "", "Work_Executed": "", "Comment_on_work": "", "Another_Work_Executed": "", "Comment_on_HSE": "", "Consultant_Recommandation": "", "Non_Compliant_work": "", "Reaction_and_WayForword": "", "challenges": ""}]}',
                output=[
                    types.SimpleNamespace(
                        type="web_search_call",
                        action=types.SimpleNamespace(
                            sources=[types.SimpleNamespace(title="IEC note", url="https://example.com/iec")]
                        ),
                    )
                ],
            )

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))

    rows, sources = app._request_structured_reports_with_openai(
        "Raw contractor text",
        api_key="test-key",
        model="gpt-4o-mini",
        discipline="Electrical",
        allow_web_research=True,
    )

    assert rows[0]["Site_Name"] == "Site A"
    assert sources == [{"title": "IEC note", "url": "https://example.com/iec"}]
    assert captured["model"] == app.RESEARCH_OPENAI_MODEL
    assert captured["tools"] == [{"type": "web_search"}]
    assert captured["tool_choice"] == "auto"
    assert captured["include"] == ["web_search_call.action.sources"]


def test_uploaded_file_to_response_part_supports_image_and_file_inputs():
    image_part = app._uploaded_file_to_response_part(
        _UploadedFileStub("site.jpg", b"image-bytes", "image/jpeg")
    )
    file_part = app._uploaded_file_to_response_part(
        _UploadedFileStub("report.pdf", b"pdf-bytes", "application/pdf")
    )

    assert image_part["type"] == "input_image"
    assert image_part["image_url"].startswith("data:image/jpeg;base64,")
    assert file_part["type"] == "input_file"
    assert file_part["filename"] == "report.pdf"
    assert file_part["file_data"].startswith("data:application/pdf;base64,")


def test_request_transcription_with_openai_returns_joined_text(monkeypatch):
    captured = {}

    class _FakeTranscriptions:
        def create(self, **kwargs):
            captured.update(kwargs)
            captured["filename"] = kwargs["file"].name
            return "Transcribed field note"

    class _FakeAudio:
        def __init__(self):
            self.transcriptions = _FakeTranscriptions()

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.audio = _FakeAudio()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))

    transcript = app._request_transcription_with_openai(
        [_UploadedFileStub("voice-note.m4a", b"audio-bytes", "audio/m4a")],
        api_key="test-key",
        discipline="Electrical",
    )

    assert "Transcribed field note" in transcript
    assert captured["api_key"] == "test-key"
    assert captured["model"] == app.TRANSCRIPTION_OPENAI_MODEL
    assert captured["filename"] == "voice-note.m4a"


def test_request_research_assistant_reply_collects_web_and_file_sources(monkeypatch):
    captured = {}

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                output_text="Use the approved HSE wording from the project document.",
                output=[
                    types.SimpleNamespace(
                        type="file_search_call",
                        results=[types.SimpleNamespace(filename="HSE Procedure.pdf", score=0.91)],
                    ),
                    types.SimpleNamespace(
                        type="web_search_call",
                        action=types.SimpleNamespace(
                            sources=[types.SimpleNamespace(title="IEC guidance", url="https://example.com/iec")]
                        ),
                    ),
                ],
            )

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))

    reply, sources = app._request_research_assistant_reply(
        api_key="test-key",
        model="gpt-4o-mini",
        discipline="Electrical",
        question="Which wording should I use for HSE observations?",
        conversation=[],
        allow_web_research=True,
        knowledge_vector_store_id="vs_123",
    )

    assert reply == "Use the approved HSE wording from the project document."
    assert captured["api_key"] == "test-key"
    assert captured["model"] == app.RESEARCH_OPENAI_MODEL
    assert captured["tools"] == [
        {"type": "web_search"},
        {"type": "file_search", "vector_store_ids": ["vs_123"], "max_num_results": 5},
    ]
    assert sources == [
        {"title": "IEC guidance", "url": "https://example.com/iec"},
        {"title": "HSE Procedure.pdf", "url": "", "note": "Relevance 0.91"},
    ]


def test_request_spreadsheet_analysis_with_openai_uses_code_interpreter(monkeypatch):
    captured = {}

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                output_text="Site A has the highest progress and one missing date entry.",
                output=[
                    types.SimpleNamespace(
                        type="message",
                        content=[
                            types.SimpleNamespace(
                                annotations=[
                                    types.SimpleNamespace(
                                        type="container_file_citation",
                                        container_id="cont_1",
                                        file_id="file_1",
                                        filename="progress-chart.png",
                                    )
                                ]
                            )
                        ],
                    )
                ],
            )

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))

    analysis_text, artifacts = app._request_spreadsheet_analysis_with_openai(
        api_key="test-key",
        model="gpt-4o-mini",
        uploaded_files=[
            _UploadedFileStub(
                "progress.xlsx",
                b"spreadsheet-bytes",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        ],
        question="Summarize the progress and anomalies.",
    )

    assert analysis_text == "Site A has the highest progress and one missing date entry."
    assert captured["api_key"] == "test-key"
    assert captured["model"] == app.RESEARCH_OPENAI_MODEL
    assert captured["tools"] == [
        {"type": "code_interpreter", "container": {"type": "auto", "memory_limit": "4g"}}
    ]
    assert captured["tool_choice"] == "required"
    assert captured["input"][0]["content"][0]["type"] == "input_text"
    assert captured["input"][0]["content"][1]["type"] == "input_file"
    assert artifacts == [
        {"container_id": "cont_1", "file_id": "file_1", "filename": "progress-chart.png"}
    ]


def test_request_text_to_speech_with_openai_returns_audio_bytes(monkeypatch):
    captured = {}

    class _FakeSpeechResponse:
        def read(self):
            return b"mp3-bytes"

    class _FakeSpeech:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _FakeSpeechResponse()

    class _FakeAudio:
        def __init__(self):
            self.speech = _FakeSpeech()

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.audio = _FakeAudio()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))

    audio_bytes = app._request_text_to_speech_with_openai(
        "Professional summary text",
        api_key="test-key",
        voice="coral",
    )

    assert audio_bytes == b"mp3-bytes"
    assert captured["api_key"] == "test-key"
    assert captured["model"] == app.TTS_OPENAI_MODEL
    assert captured["voice"] == "coral"
    assert captured["response_format"] == "mp3"


def test_save_saved_guidance_item_and_active_guidance_text(monkeypatch, tmp_path):
    st_stub = types.SimpleNamespace(session_state={})
    monkeypatch.setattr(app, "st", st_stub)
    monkeypatch.setattr(app, "AI_MEMORY_FILE", tmp_path / "ai_memory.json")

    item = app._save_saved_guidance_item("Keep consultant comments concise.", target="converter")

    assert item["target"] == "converter"
    assert "Keep consultant comments concise." in app._active_guidance_text("converter")
    assert Path(app.AI_MEMORY_FILE).exists()


def test_request_image_captions_with_openai_returns_captions(monkeypatch):
    captured = {}

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                output_text='{"captions": ["Crew excavating trench.", "Cable laying in progress."]}',
            )

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))

    captions = app._request_image_captions_with_openai(
        [b"img-1", b"img-2"],
        api_key="test-key",
        model="gpt-4o-mini",
        discipline="Electrical",
        report_row=["2025-08-06", "Site A"] + [""] * 12,
        persistent_guidance="- Keep captions short.",
    )

    assert captions == ["Crew excavating trench.", "Cable laying in progress."]
    assert captured["api_key"] == "test-key"
    assert captured["text"]["format"]["type"] == "json_schema"
    assert len(captured["input"][0]["content"]) == 3


def test_request_self_healing_analysis_with_openai_returns_actions(monkeypatch):
    captured = {}

    class _FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                output_text=(
                    '{"assistant_message": "Clear the photo caption cache and retry.", '
                    '"recommended_actions": ["clear_photo_captions"], '
                    '"reusable_instruction": "Use shorter image captions.", '
                    '"maintenance_title": "Improve caption retry handling"}'
                ),
            )

    class _FakeClient:
        def __init__(self, api_key):
            captured["api_key"] = api_key
            self.responses = _FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=_FakeClient))

    result = app._request_self_healing_analysis_with_openai(
        "Photo captions are failing.",
        api_key="test-key",
        model="gpt-4o-mini",
        recent_issues=[{"area": "photo_captions", "message": "Caption generation failed."}],
        persistent_guidance="- Keep the app stable.",
    )

    assert result["recommended_actions"] == ["clear_photo_captions"]
    assert result["maintenance_title"] == "Improve caption retry handling"
    assert captured["api_key"] == "test-key"
    assert captured["text"]["format"]["type"] == "json_schema"


def test_generate_reports_with_gallery_options_passes_new_gallery_flag(monkeypatch):
    captured = {}

    def _fake_generate_reports(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return b"zip-bytes"

    monkeypatch.setattr(app, "generate_reports", _fake_generate_reports)

    result = app._generate_reports_with_gallery_options(
        [["2025-08-06", "Site A"] + [""] * 12],
        {},
        "Civil",
        185,
        148,
        5,
        add_border=True,
        show_photo_placeholders=False,
        image_caption_mapping={("Site A", "2025-08-06"): ["Caption 1"]},
    )

    assert result == b"zip-bytes"
    assert captured["kwargs"]["img_per_row"] == 2
    assert captured["kwargs"]["add_border"] is True
    assert captured["kwargs"]["show_photo_placeholders"] is False
    assert captured["kwargs"]["image_caption_mapping"] == {("Site A", "2025-08-06"): ["Caption 1"]}


def test_generate_reports_with_gallery_options_falls_back_for_legacy_signature(monkeypatch):
    captured = {}

    def _legacy_generate_reports(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        if "show_photo_placeholders" in kwargs:
            raise TypeError("generate_reports() got an unexpected keyword argument 'show_photo_placeholders'")
        return b"legacy-zip"

    monkeypatch.setattr(app, "generate_reports", _legacy_generate_reports)

    result = app._generate_reports_with_gallery_options(
        [["2025-08-06", "Site A"] + [""] * 12],
        {},
        "Civil",
        185,
        148,
        5,
        add_border=False,
        show_photo_placeholders=True,
        image_caption_mapping={("Site A", "2025-08-06"): ["Caption 1"]},
    )

    assert result == b"legacy-zip"
    assert captured["kwargs"] == {"img_per_row": 2, "add_border": False}
