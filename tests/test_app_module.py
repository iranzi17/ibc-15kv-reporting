import app


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
        self.button_states = {
            "Sync cached data to Google Sheet": False,
            "Generate Reports": True,
            "Send to Google Sheet": False,
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


def test_run_app_excludes_header_rows(monkeypatch):
    headers = [
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
    sheet_rows = [
        headers,
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

    chatgpt_report = st_stub.session_state.get("chatgpt_report_data")
    assert isinstance(chatgpt_report, list)
    assert [row["Site_Name"] for row in chatgpt_report] == ["Site A", "Site B"]
    assert st_stub.json_value == chatgpt_report
