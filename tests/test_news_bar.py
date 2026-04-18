from streamlit_ui import helpers
from streamlit_ui import news_bar


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _StreamlitStub:
    def __init__(self, *, show_updates=False):
        self.session_state = {}
        self.secrets = {}
        self.markdown_calls = []
        self.show_updates = show_updates

    def container(self, *_, **__):
        return _Context()

    def columns(self, spec, *_, **__):
        if isinstance(spec, int):
            count = spec
        else:
            count = len(spec)
        return tuple(_Context() for _ in range(count))

    def checkbox(self, _label, value=False, **__):
        return self.show_updates if self.show_updates is not None else value

    def markdown(self, content, **__):
        self.markdown_calls.append(content)
        return None


def test_load_live_updates_config_reads_env_values(monkeypatch):
    monkeypatch.setenv("REPORTING_LIVE_UPDATES_LABEL", "Sector updates")
    monkeypatch.setenv("REPORTING_LIVE_UPDATES_ITEMS", '["Grid outage watch","Weather advisory"]')
    monkeypatch.setenv("REPORTING_LIVE_UPDATES_ENABLED_BY_DEFAULT", "true")

    config = news_bar.load_live_updates_config()

    assert config["label"] == "Sector updates"
    assert config["enabled_by_default"] is True
    assert config["static_items"] == [
        {"title": "Grid outage watch", "context": ""},
        {"title": "Weather advisory", "context": ""},
    ]


def test_load_live_updates_items_prefers_static_items(monkeypatch):
    monkeypatch.setattr(
        news_bar,
        "fetch_feed_updates",
        lambda *_, **__: [{"title": "Should not be used", "context": ""}],
    )

    items = news_bar.load_live_updates_items(
        {
            "static_items": [
                {"title": "Infrastructure permit cleared", "context": "infrastructure"},
                {"title": "Rain alert for Kigali", "context": "weather"},
            ],
            "feed_url": "https://example.com/feed.xml",
            "max_items": 5,
        }
    )

    assert items == [
        {"title": "Infrastructure permit cleared", "context": "infrastructure"},
        {"title": "Rain alert for Kigali", "context": "weather"},
    ]


def test_render_live_updates_shell_shows_unavailable_state_when_enabled_without_source(monkeypatch):
    st_stub = _StreamlitStub(show_updates=True)
    monkeypatch.setattr(news_bar, "st", st_stub)
    monkeypatch.setattr(helpers, "st", st_stub)
    monkeypatch.delenv("REPORTING_LIVE_UPDATES_FEED_URL", raising=False)
    monkeypatch.delenv("REPORTING_LIVE_UPDATES_ITEMS", raising=False)

    news_bar.render_live_updates_shell()

    assert any("News unavailable" in content for content in st_stub.markdown_calls)
