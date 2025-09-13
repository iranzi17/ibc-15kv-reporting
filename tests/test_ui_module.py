import io
from pathlib import Path

import streamlit as st

import ui


def test_set_background_calls_markdown(tmp_path, monkeypatch):
    img_path = tmp_path / "bg.jpg"
    img_path.write_bytes(b"fake")
    captured = {}

    def fake_markdown(content, unsafe_allow_html=True):
        captured["content"] = content
    monkeypatch.setattr(st, "markdown", fake_markdown)
    ui.set_background(str(img_path))
    assert "stAppViewContainer" in captured["content"]


def test_render_workwatch_header(monkeypatch):
    captured = {}

    def fake_markdown(content, unsafe_allow_html=True):
        captured["content"] = content
    monkeypatch.setattr(st, "markdown", fake_markdown)
    ui.render_workwatch_header(author="A", brand="B", subtitle="C", logo_path=None, tagline=None)
    assert "B" in captured["content"]
