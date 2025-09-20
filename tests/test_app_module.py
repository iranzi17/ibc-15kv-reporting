import app


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
            "Clean & Structure with Hugging Face": False,
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

    assert st_stub.uploader_labels == [
        "Upload images for Site A - 2024-01-01",
        "Upload images for Site B - 2024-01-02",
    ]

    structured_report = st_stub.session_state.get("structured_report_data")
    assert isinstance(structured_report, list)
    assert [row["Site_Name"] for row in structured_report] == ["Site A", "Site B"]
    assert st_stub.json_value == structured_report


def test_run_app_uses_helper_when_button_clicked(monkeypatch):
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
        ],
    ]

    monkeypatch.setattr(app, "get_sheet_data", lambda: sheet_rows)
    monkeypatch.setattr(app, "load_offline_cache", lambda: None)
    monkeypatch.setattr(app, "generate_reports", lambda *_, **__: b"zip-bytes")
    monkeypatch.setattr(app, "set_background", lambda *_: None)
    monkeypatch.setattr(app, "render_workwatch_header", lambda *_: None)

    captured_text = []
    canned_payload = {header: f"value-{header}" for header in HEADERS}

    def fake_helper(raw_text):
        captured_text.append(raw_text)
        return canned_payload

    monkeypatch.setattr(app, "clean_and_structure_report", fake_helper)

    st_stub = _StreamlitStub()
    st_stub.text_area_value = "Sample contractor report"
    st_stub.button_states["Generate Reports"] = False
    st_stub.button_states["Clean & Structure with Hugging Face"] = True
    monkeypatch.setattr(app, "st", st_stub)

    app.run_app()

    assert captured_text == ["Sample contractor report"]
    assert st_stub.session_state["structured_report_data"] == canned_payload
    assert st_stub.json_value == canned_payload
