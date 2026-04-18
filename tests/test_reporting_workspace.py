import types

from streamlit_ui import reporting_workspace


class _Spinner:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


class _SidebarStub:
    def subheader(self, *_, **__):
        return None

    def slider(self, *_, value=None, **__):
        return value

    def checkbox(self, *_, value=False, **__):
        return value

    def caption(self, *_, **__):
        return None


class _StreamlitStub:
    def __init__(self):
        self.session_state = {"images": {("Site A", "2026-04-18"): [b"img-1", b"img-2"]}}
        self.sidebar = _SidebarStub()
        self.warning_messages = []
        self.download_args = None

    def radio(self, _label, options, **__):
        return options[0]

    def multiselect(self, _label, _options, default, **__):
        return default

    def dataframe(self, *_, **__):
        return None

    def file_uploader(self, *_, **__):
        return []

    def button(self, label, *_, **__):
        return label == "Generate Reports"

    def warning(self, message, *_, **__):
        self.warning_messages.append(message)
        return None

    def download_button(self, *args, **kwargs):
        self.download_args = (args, kwargs)
        return None

    def expander(self, *_args, **_kwargs):
        return _Spinner()

    def error(self, *_, **__):
        return None

    def data_editor(self, df, *_, **__):
        return df


def test_render_reporting_workspace_caption_failure_uses_fallback_and_generates_zip(monkeypatch):
    st_stub = _StreamlitStub()
    recorded_issues = []
    captured_kwargs = {}

    monkeypatch.setattr(reporting_workspace, "st", st_stub)
    monkeypatch.setattr(reporting_workspace, "render_section_header", lambda *_, **__: None)
    monkeypatch.setattr(reporting_workspace, "render_subsection", lambda *_, **__: None)
    monkeypatch.setattr(reporting_workspace, "render_kpi_strip", lambda *_, **__: None)
    monkeypatch.setattr(reporting_workspace, "render_note", lambda *_, **__: None)
    monkeypatch.setattr(reporting_workspace, "safe_columns", lambda *_, **__: (_Spinner(), _Spinner()))
    monkeypatch.setattr(reporting_workspace, "safe_data_editor", lambda df, **__: df)
    monkeypatch.setattr(reporting_workspace, "safe_caption", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(reporting_workspace, "safe_image", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(reporting_workspace, "safe_markdown", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(reporting_workspace, "safe_spinner", lambda *_args, **_kwargs: _Spinner())
    monkeypatch.setattr(reporting_workspace, "openai_sdk_ready", lambda: (True, ""))
    monkeypatch.setattr(reporting_workspace, "load_openai_api_key", lambda: "key")
    monkeypatch.setattr(reporting_workspace, "default_openai_model", lambda: "gpt-4o-mini")
    monkeypatch.setattr(
        reporting_workspace,
        "generate_ai_photo_captions_for_reports",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("caption failure")),
    )

    def _fake_generate_reports(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return b"zip-bytes"

    reporting_workspace.render_reporting_workspace(
        record_runtime_issue=lambda area, msg, details="": recorded_issues.append((area, msg, details)),
        active_guidance_text=lambda *_args: "",
        get_sheet_data_fn=lambda: [["header"], ["2026-04-18", "Site A"] + [""] * 12],
        get_unique_sites_and_dates_fn=lambda rows: (["Site A"], ["2026-04-18"]),
        load_offline_cache_fn=lambda: {},
        append_rows_to_sheet_fn=lambda *_args, **_kwargs: None,
        generate_reports_fn=_fake_generate_reports,
    )

    assert st_stub.download_args is not None
    assert captured_kwargs["image_caption_mapping"] == {("Site A", "2026-04-18"): ["", ""]}
    assert any("captions failed and were skipped" in message for message in st_stub.warning_messages)
    assert any(issue[0] == "photo_captioning" for issue in recorded_issues)
