import pandas as pd

from streamlit_ui import helpers
from streamlit_ui import reporting_workspace


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _StreamlitStub:
    def __init__(self):
        self.session_state = {"images": {("Site A", "2026-04-18"): [b"img-1", b"img-2"]}}
        self.warning_messages = []
        self.download_args = None
        self.multiselect_calls = []
        self.metric_calls = []
        self.dataframe_capture = None
        self.button_states = {
            "Sync cached data to Google Sheet": False,
            "Reset filters": False,
            "Generate Reports": True,
        }

    def container(self, *_, **__):
        return _Context()

    def columns(self, spec, *_, **__):
        if isinstance(spec, int):
            count = spec
        else:
            count = len(spec)
        return tuple(_Context() for _ in range(count))

    def radio(self, _label, options, index=0, **__):
        return options[index]

    def multiselect(self, label, options, default=None, **kwargs):
        self.multiselect_calls.append(
            {
                "label": label,
                "options": list(options),
                "default": list(default or []),
                "placeholder": kwargs.get("placeholder"),
            }
        )
        return list(default or [])

    def slider(self, _label, min_value=None, max_value=None, value=None, step=None, **__):
        return value

    def checkbox(self, _label, value=False, **__):
        return value

    def dataframe(self, df, *_, **__):
        self.dataframe_capture = df.copy()
        return None

    def file_uploader(self, *_, **__):
        return []

    def button(self, label, *_, **__):
        return self.button_states.get(label, False)

    def warning(self, message, *_, **__):
        self.warning_messages.append(message)
        return None

    def download_button(self, *args, **kwargs):
        self.download_args = (args, kwargs)
        return None

    def expander(self, *_args, **_kwargs):
        return _Context()

    def error(self, *_, **__):
        return None

    def success(self, *_, **__):
        return None

    def data_editor(self, df, *_, **__):
        return df

    def metric(self, label, value, **__):
        self.metric_calls.append((label, value))
        return None

    def caption(self, *_, **__):
        return None

    def markdown(self, *_, **__):
        return None


def _patch_layout(monkeypatch):
    monkeypatch.setattr(helpers, "st", reporting_workspace.st)
    monkeypatch.setattr(reporting_workspace, "render_workspace_topbar", lambda *_, **__: None)
    monkeypatch.setattr(reporting_workspace, "render_live_updates_shell", lambda *_, **__: None)
    monkeypatch.setattr(reporting_workspace, "render_card_header", lambda *_, **__: None)
    monkeypatch.setattr(reporting_workspace, "render_kpi_strip", lambda *_, **__: None)
    monkeypatch.setattr(reporting_workspace, "render_note", lambda *_, **__: None)
    monkeypatch.setattr(reporting_workspace, "render_status_badges", lambda *_, **__: None)
    monkeypatch.setattr(reporting_workspace, "safe_image", lambda *_, **__: None)


def test_render_reporting_workspace_uses_empty_filter_defaults_and_preserves_all_scope(monkeypatch):
    st_stub = _StreamlitStub()
    st_stub.button_states["Generate Reports"] = False

    monkeypatch.setattr(reporting_workspace, "st", st_stub)
    _patch_layout(monkeypatch)

    reporting_workspace.render_reporting_workspace(
        record_runtime_issue=lambda *_, **__: None,
        active_guidance_text=lambda *_args: "",
        get_sheet_data_fn=lambda: [
            ["header"],
            ["2026-04-18", "Site A"] + [""] * 12,
            ["2026-04-19", "Site B"] + [""] * 12,
        ],
        get_unique_sites_and_dates_fn=lambda rows: (["Site A", "Site B"], ["2026-04-18", "2026-04-19"]),
        load_offline_cache_fn=lambda: {},
        append_rows_to_sheet_fn=lambda *_args, **_kwargs: None,
        generate_reports_fn=lambda *_args, **_kwargs: b"zip-bytes",
    )

    sites_call = next(call for call in st_stub.multiselect_calls if call["label"] == "Sites")
    dates_call = next(call for call in st_stub.multiselect_calls if call["label"] == "Dates")

    assert sites_call["options"] == ["Site A", "Site B"]
    assert sites_call["default"] == []
    assert sites_call["placeholder"] == "All sites"
    assert "All Sites" not in sites_call["options"]

    assert dates_call["options"] == ["2026-04-18", "2026-04-19"]
    assert dates_call["default"] == []
    assert dates_call["placeholder"] == "All dates"
    assert "All Dates" not in dates_call["options"]

    assert isinstance(st_stub.dataframe_capture, pd.DataFrame)
    assert len(st_stub.dataframe_capture) == 2


def test_render_reporting_workspace_caption_failure_uses_fallback_and_generates_zip(monkeypatch):
    st_stub = _StreamlitStub()
    recorded_issues = []
    captured_kwargs = {}

    monkeypatch.setattr(reporting_workspace, "st", st_stub)
    _patch_layout(monkeypatch)
    monkeypatch.setattr(reporting_workspace, "safe_spinner", lambda *_args, **_kwargs: _Context())
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
